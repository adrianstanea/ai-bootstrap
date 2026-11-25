#!/usr/bin/env python3
# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Run plugins/*/evals/*/case.yaml through headless `claude -p` sessions and grade them.

`claude plugin eval` loads plugins with --plugin-dir, which organizations can disable
(disableSideloadFlags). This runner instead uses the adrianstanea plugins as installed from the
registered marketplace (installed via the sync tooling), so every case sees all plugins at once and
measures routing between them. The "without" arm disables the adrianstanea plugins via --settings.

Usage:
  tools/eval-headless.py --label baseline [--tag trigger --tag no-trigger] [--plugin dev-practices]
  tools/eval-headless.py --compare reports/evals/baseline.json reports/evals/after.json
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NONFATAL_ERRORS = {"error_max_turns"}
DENY = "Bash Edit Write MultiEdit NotebookEdit WebFetch WebSearch Task Agent"
JUDGE_PROMPT = """You grade an AI assistant's answer against criteria. Do not use tools.
Criteria:
{criteria}

Answer to grade:
<<<
{answer}
>>>
Reply with exactly one JSON object and nothing else: {{"pass": true|false, "reason": "<short>"}}"""


def claude_bin() -> str:
    return os.environ.get("CLAUDE_BIN") or os.environ.get("CLAUDE_CODE_EXECPATH") or "claude"


def load_cases(plugins: list[str], tags: list[str], case_glob: str | None) -> list[dict]:
    cases = []
    for path in sorted(ROOT.glob("plugins/*/evals/*/case.yaml")):
        plugin = path.parts[-4]
        if plugins and plugin not in plugins:
            continue
        case = json.loads(path.read_text())
        if tags and not set(tags) & set(case.get("tags", [])):
            continue
        if case_glob and not fnmatch.fnmatch(case["name"], case_glob):
            continue
        case["plugin"] = plugin
        cases.append(case)
    return cases


def disabled_settings() -> str:
    catalog = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    names = {f"{p['name']}@{catalog['name']}": False for p in catalog["plugins"]}
    return json.dumps({"enabledPlugins": names})


def run_claude(prompt: str, model: str, max_turns: int, allowed: list[str], settings: str | None,
               timeout: int) -> dict:
    """Run one headless session in an empty directory and return its tool calls and answer."""
    with tempfile.TemporaryDirectory(prefix="ai-eval-") as cwd:
        cmd = [claude_bin(), "-p", prompt, "--model", model, "--max-turns", str(max_turns),
               "--output-format", "stream-json", "--verbose", "--disallowedTools", DENY]
        if allowed:
            cmd += ["--allowedTools", " ".join(allowed)]
        if settings:
            cmd += ["--settings", settings]
        timed_out = False
        try:
            proc = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, timeout=timeout)
            out, err = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            raw = exc.stdout or ""
            out = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
            err, timed_out = "timeout", True
    calls, texts, answer, cost, error = [], [], "", 0.0, None
    got_result = False
    for line in (out or "").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    calls.append({"name": block.get("name"), "input": block.get("input", {})})
                elif block.get("type") == "text":
                    texts.append(block.get("text", ""))
        elif event.get("type") == "result":
            got_result = True
            answer = event.get("result") or ""
            cost = float(event.get("total_cost_usd") or 0.0)
            if event.get("is_error"):
                error = str(event.get("subtype"))
    if not answer and texts:
        answer = texts[-1]
    if timed_out:
        error = "timeout"
    elif not out:
        error = (err or "no output").strip()[:300]
    elif not got_result and error is None:
        error = "no_result"
    return {"calls": calls, "answer": answer, "trace": "\n".join(texts), "cost": cost,
            "error": error}


def grade_tool(grader: dict, result: dict) -> tuple[bool, str]:
    pattern = re.compile(grader["input_match"]) if grader.get("input_match") else None
    count = sum(
        1 for c in result["calls"]
        if c["name"] == grader.get("tool")
        and (pattern is None or pattern.search(json.dumps(c["input"])))
    )
    lo, hi = grader.get("min", 1), grader.get("max")
    ok = count >= lo and (hi is None or count <= hi)
    return ok, f"{grader.get('tool')} matched {count}x"


def grade_regex(grader: dict, result: dict) -> tuple[bool, str]:
    text = result["trace"] + "\n" + result["answer"] if grader.get("target") == "trace" \
        else result["answer"]
    if grader.get("target") == "trace":
        text += "\n" + json.dumps(result["calls"])
    flags = re.I if "i" in grader.get("flags", "") else 0
    hits = len(re.findall(grader["pattern"], text, flags))
    mode = grader.get("match", "contains")
    if mode == "not_contains":
        return hits == 0, f"{hits} hits"
    if mode.startswith("count:"):
        return hits == int(mode.split(":", 1)[1]), f"{hits} hits"
    return hits > 0, f"{hits} hits"


def grade_llm(grader: dict, result: dict, judge_model: str, timeout: int) -> tuple[bool, str, float]:
    prompt = JUDGE_PROMPT.format(criteria=grader["criteria"], answer=result["answer"][:12000])
    judged = run_claude(prompt, judge_model, 1, [], None, timeout)
    match = re.search(r"\{.*\}", judged["answer"], re.S)
    try:
        verdict = json.loads(match.group(0)) if match else {}
    except ValueError:
        verdict = {}
    return bool(verdict.get("pass")), str(verdict.get("reason", judged["error"] or "unparsed")), \
        judged["cost"]


def grade(case: dict, arm: str, result: dict, judge_model: str, timeout: int) -> dict:
    scored, total_w, got_w, extra_cost = [], 0.0, 0.0, 0.0
    for grader in case.get("graders", []):
        if grader["type"] == "tool_used" and arm == "without" and grader.get("arm") != "both":
            continue  # the skill cannot fire without its plugin; only the outcome is comparable
        if grader["type"] == "tool_used":
            ok, why = grade_tool(grader, result)
        elif grader["type"] == "regex":
            ok, why = grade_regex(grader, result)
        elif grader["type"] == "llm":
            ok, why, cost = grade_llm(grader, result, judge_model, timeout)
            extra_cost += cost
        else:
            continue
        weight = float(grader.get("weight", 1))
        total_w += weight
        got_w += weight if ok else 0.0
        scored.append({"name": grader["name"], "passed": ok, "why": why})
    # Hitting max_turns after doing the graded work is not a failure; graders decide.
    fatal = result["error"] and result["error"] not in NONFATAL_ERRORS
    passed = bool(scored) and all(g["passed"] for g in scored) and not fatal
    return {"passed": passed, "score": got_w / total_w if total_w else 0.0, "graders": scored,
            "cost": result["cost"] + extra_cost, "error": result["error"]}


def run_suite(args: argparse.Namespace) -> int:
    cases = load_cases(args.plugin, args.tag, args.case)
    if not cases:
        print("no cases selected", file=sys.stderr)
        return 1
    without = disabled_settings()
    jobs = []
    for case in cases:
        arms = ["with", "without"] if "ablation" in case.get("tags", []) else ["with"]
        for arm in arms:
            for i in range(args.runs):
                jobs.append((case, arm, i))
    spent, lock, stop = [0.0], threading.Lock(), threading.Event()
    results: dict[tuple[str, str], list[dict]] = {}

    def work(job):
        case, arm, _ = job
        with lock:
            if spent[0] >= args.max_cost_usd:
                stop.set()
        if stop.is_set():
            return job, None
        ex = case.get("execution", {})
        result = run_claude(ex["prompt"], args.model, int(ex.get("max_turns", 8)),
                            ex.get("allowed_tools", []), without if arm == "without" else None,
                            args.timeout)
        graded = grade(case, arm, result, args.judge_model, args.timeout)
        with lock:
            spent[0] += graded["cost"]
        return job, graded

    print(f"{len(jobs)} runs over {len(cases)} cases, cap ${args.max_cost_usd:.2f}", flush=True)
    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for job, graded in pool.map(work, jobs):
            if graded is None:
                continue
            case, arm, _ = job
            results.setdefault((case["name"], arm), []).append(graded)
            mark = "PASS" if graded["passed"] else "FAIL"
            print(f"  {mark} {case['plugin']}/{case['name']} [{arm}] ${graded['cost']:.3f}"
                  + (f" error={graded['error']}" if graded["error"] else ""), flush=True)
    summary = {"label": args.label, "model": args.model, "runs": args.runs,
               "cost_usd": round(spent[0], 4), "partial": stop.is_set(), "cases": {}}
    for case in cases:
        entry = {"plugin": case["plugin"], "tags": case.get("tags", [])}
        for arm in ("with", "without"):
            runs = results.get((case["name"], arm))
            if runs:
                entry[arm] = {"pass_rate": sum(r["passed"] for r in runs) / len(runs),
                              "score": sum(r["score"] for r in runs) / len(runs), "runs": runs}
        summary["cases"][case["name"]] = entry
    out = Path(args.out or ROOT / "reports" / "evals" / f"{args.label}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print_table(summary)
    print(f"cost ${spent[0]:.2f}{' (PARTIAL: cost cap hit)' if stop.is_set() else ''}; wrote {out}")
    return 0


def print_table(summary: dict) -> None:
    print("\n| case | with pass | without pass | delta score |\n|---|---|---|---|")
    for name, e in sorted(summary["cases"].items()):
        w, wo = e.get("with"), e.get("without")
        delta = f"{w['score'] - wo['score']:+.2f}" if w and wo else ""
        print(f"| {name} | {w['pass_rate']:.2f} | " if w else f"| {name} | - | ", end="")
        print(f"{wo['pass_rate']:.2f} | {delta} |" if wo else f"- | {delta} |")


def compare(a_path: str, b_path: str, allow_missing: list[str]) -> int:
    a, b = (json.loads(Path(p).read_text()) for p in (a_path, b_path))
    for report in (a, b):
        if report.get("partial"):
            print(f"warning: {report['label']} is partial (cost cap hit); missing cases count as "
                  "regressions", file=sys.stderr)
    print(f"| case | {a['label']} | {b['label']} | change |\n|---|---|---|---|")
    regressions = 0
    for name in sorted(set(a["cases"]) | set(b["cases"])):
        ra = a["cases"].get(name, {}).get("with", {}).get("pass_rate")
        rb = b["cases"].get(name, {}).get("with", {}).get("pass_rate")
        if ra is not None and rb is None:
            allowed = any(fnmatch.fnmatch(name, g) for g in allow_missing)
            change = "removed" if allowed else "MISSING"
        else:
            change = "" if ra is None or rb is None else f"{rb - ra:+.2f}"
        regressions += change.startswith("-") or change == "MISSING"
        fmt = lambda r: "-" if r is None else f"{r:.2f}"  # noqa: E731
        print(f"| {name} | {fmt(ra)} | {fmt(rb)} | {change} |")
    print(f"\ncost {a['label']} ${a['cost_usd']:.2f}, {b['label']} ${b['cost_usd']:.2f}; "
          f"{regressions} case(s) regressed")
    return 1 if regressions else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--label", help="name for reports/evals/<label>.json")
    ap.add_argument("--plugin", action="append", default=[])
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--case", help="glob on case names")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--judge-model", default="haiku")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--max-cost-usd", type=float, default=8.0)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--out")
    ap.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"))
    ap.add_argument("--allow-missing", action="append", default=[], metavar="GLOB",
                    help="with --compare: case names deliberately removed in B")
    args = ap.parse_args()
    if args.compare:
        return compare(*args.compare, args.allow_missing)
    if not args.label:
        ap.error("--label is required unless --compare is given")
    return run_suite(args)


if __name__ == "__main__":
    sys.exit(main())
