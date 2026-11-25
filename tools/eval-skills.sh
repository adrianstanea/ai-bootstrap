#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
# Static skill evaluation: no model calls, no API keys.
#
# Usage: tools/eval-skills.sh [--llm] [--jobs N] [--ci]
#   --llm     also run the LLM checks of skillevaluator tier1 (needs SKILL_EVAL_LLM_PROVIDER)
#   --jobs N  parallel tier1 runs (default 4)
#   --ci      skip `claude plugin validate` (a separate CI job runs it); prints SKIPPED
# Output: reports/static/ (summary.md, per-skill tier1 JSON, harness-<plugin>.json)
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

use_llm=0
jobs=4
ci=0
while [ $# -gt 0 ]; do
    case "$1" in
        --llm) use_llm=1 ;;
        --ci) ci=1 ;;
        --jobs) jobs="${2:?--jobs needs a value}"; shift ;;
        -h | --help) sed -n '2,9p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

out="reports/static"
rm -rf "$out"
mkdir -p "$out"
failures=0
claude_bin="${CLAUDE_CODE_EXECPATH:-$(command -v claude || true)}"

step() { printf '\n== %s\n' "$*"; }

step "check_skills.py"
python3 tools/check_skills.py --json >"$out/check_skills.json" || failures=$((failures + 1))
python3 tools/check_skills.py || true

step "claude plugin validate"
if [ "$ci" = 1 ]; then
    echo "SKIPPED: --ci (claude plugin validate runs in the claude-validate job)"
elif [ -n "$claude_bin" ]; then
    for target in . plugins/*/; do
        if ! "$claude_bin" plugin validate "$target"; then
            failures=$((failures + 1))
        fi
    done
else
    echo "SKIPPED: claude binary not found (set CLAUDE_CODE_EXECPATH)"
fi

llm_flag="--no-llm"
if [ "$use_llm" = 1 ]; then
    if [ -n "${SKILL_EVAL_LLM_PROVIDER:-}" ]; then
        llm_flag="--llm"
    else
        echo "NOTE: --llm requested but SKILL_EVAL_LLM_PROVIDER is not set; LLM checks skipped"
    fi
fi

if command -v skillevaluator >/dev/null 2>&1; then
    step "skillevaluator tier1 ($llm_flag, $jobs parallel)"
    # tier1 exits nonzero on findings; the summary reports status instead of aborting here
    printf '%s\n' plugins/*/skills/*/ | xargs -P "$jobs" -I{} bash -c '
        skill_dir="${1%/}"; name="$(basename "$skill_dir")"
        skillevaluator tier1 "$skill_dir" '"$llm_flag"' \
            --quality-config eval/skillevaluator-quality.yaml -r json \
            -o "'"$out"'/$name" >"'"$out"'/$name.log" 2>&1 || true
        echo "tier1 done: $name"' _ {}

    step "skillevaluator harness-check"
    for plugin_dir in plugins/*/; do
        plugin="$(basename "$plugin_dir")"
        skillevaluator harness-check "${plugin_dir}skills" \
            --harness claude-code,copilot-cli,codex \
            --json "$out/harness-$plugin.json" >"$out/harness-$plugin.log" 2>&1 || true
        echo "harness-check: $plugin"
    done
else
    echo "SKIPPED: skillevaluator not installed; tier1 and harness-check were not run"
fi

step "summary"
python3 - "$out" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
check = json.loads((out / "check_skills.json").read_text())
rows = []
for skill in check["skills"]:
    name = skill["skill"]
    tier1 = out / name / "skillevaluator-tier1.json"
    score, status = "n/a", "not run"
    if tier1.is_file():
        data = json.loads(tier1.read_text())
        quality = data.get("quality_summary") or []
        if quality:
            score = f"{quality[0]['overall_score']:.1f} ({quality[0]['grade']})"
        status = data.get("overall_status", "?")
        status += f" ({data.get('total_errors', 0)}E/{data.get('total_warnings', 0)}W)"
    rows.append((name, score, status, skill.get("description_chars", 0), skill.get("lines", 0),
                 len(skill["errors"])))

lines = ["# Static skill evaluation", "",
         f"Description budget (model-invocable): {check['description_budget']}/"
         f"{check['budget_limit']} chars", ""]
lines += ["| skill | quality score | tier1 status | desc chars | lines | check_skills errors |",
          "| --- | --- | --- | ---: | ---: | ---: |"]
lines += [f"| {n} | {q} | {t} | {d} | {ln} | {e} |" for n, q, t, d, ln, e in rows]
problems = [f"- {s['skill']}: {e}" for s in check["skills"] for e in s["errors"]]
if problems:
    lines += ["", "## check_skills findings", *problems]
for warning in check["warnings"]:
    lines += ["", f"WARNING: {warning}"]
text = "\n".join(lines) + "\n"
(out / "summary.md").write_text(text)
print(text)
PY

echo "summary: $out/summary.md"
[ "$failures" -eq 0 ] || { echo "$failures hard check(s) failed" >&2; exit 1; }
