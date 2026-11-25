#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
# Model-backed plugin evals via `claude plugin eval`. Costs money: never run automatically.
#
# Usage: tools/run-evals.sh --label <name> [--suite triggers|ablation|all] [--plugin <id>]...
#   --label   name of this run; results go to reports/evals/<label>/ (required)
#   --suite   triggers: trigger and no-trigger cases, no baseline arm (default: all)
#             ablation: outcome cases with a no-plugin baseline arm
#   --plugin  restrict to a plugin id under plugins/ (repeatable; default: every plugin)
# Environment: CONCURRENCY (3), RUNS (2), MAX_COST_USD (4, per plugin and suite), MODEL (sonnet)
# Reports are never published (--no-publish). Summarize with tools/summarize-evals.py.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

label=""
suite="all"
plugins=()
while [ $# -gt 0 ]; do
    case "$1" in
        --label) label="${2:?--label needs a value}"; shift ;;
        --suite) suite="${2:?--suite needs a value}"; shift ;;
        --plugin) plugins+=("${2:?--plugin needs a value}"); shift ;;
        -h | --help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

[ -n "$label" ] || { echo "error: --label is required" >&2; exit 2; }
case "$suite" in triggers | ablation | all) ;; *) echo "error: bad --suite: $suite" >&2; exit 2 ;; esac

claude_bin="${CLAUDE_CODE_EXECPATH:-$(command -v claude || true)}"
[ -n "$claude_bin" ] || { echo "error: claude binary not found" >&2; exit 2; }

if [ "${#plugins[@]}" -eq 0 ]; then
    for dir in plugins/*/; do
        [ -d "${dir}evals" ] && plugins+=("$(basename "$dir")")
    done
fi

run_suite() {
    local plugin="$1" suite_name="$2"
    shift 2
    local dest="reports/evals/$label"
    mkdir -p "$dest"
    echo "== $plugin ($suite_name)"
    "$claude_bin" plugin eval "plugins/$plugin" \
        --no-publish --trust-plugin \
        --json "$dest/$plugin-$suite_name.json" \
        --output-dir "$dest/$plugin-$suite_name" \
        --concurrency "${CONCURRENCY:-3}" \
        --runs "${RUNS:-2}" \
        --max-cost-usd "${MAX_COST_USD:-4}" \
        --model "${MODEL:-sonnet}" \
        --threshold 0 \
        "$@" || echo "warning: $plugin ($suite_name) exited with $?" >&2
}

for plugin in "${plugins[@]}"; do
    if [ "$suite" = triggers ] || [ "$suite" = all ]; then
        run_suite "$plugin" triggers --tag trigger --tag no-trigger --ablation none
    fi
    if [ "$suite" = ablation ] || [ "$suite" = all ]; then
        if compgen -G "plugins/$plugin/evals/*-ablation" >/dev/null; then
            run_suite "$plugin" ablation --tag ablation --ablation with-without
        fi
    fi
done

echo
echo "results: reports/evals/$label/"
echo "summary: python3 tools/summarize-evals.py $label"
