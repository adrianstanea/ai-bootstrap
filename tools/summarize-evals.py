#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Summarize `claude plugin eval --json` results written by tools/run-evals.sh.

Usage:
  tools/summarize-evals.py <label> [--reports reports/evals]
  tools/summarize-evals.py --compare <labelA> <labelB> [--reports reports/evals]

Per case it prints the pass rate and mean score over runs. For ablation cases it prints the
with-plugin and without-plugin scores and their delta. --compare shows the change per case
between two labels (B minus A) and flags regressions.
"""

import argparse
import json
import sys
from pathlib import Path


def mean(values):
    return sum(values) / len(values) if values else None


def fmt(value, pct=False):
    if value is None:
        return "  n/a"
    return f"{value * 100:4.0f}%" if pct else f"{value:5.2f}"


def arm_stats(runs):
    """Return (mean score, pass rate, n runs) for the runs of one arm."""
    runs = [r for r in runs or [] if isinstance(r, dict)]
    scores = [r.get("score", 0) for r in runs]
    passed = [bool(r.get("passed")) for r in runs]
    return mean(scores), mean([1.0 if p else 0.0 for p in passed]), len(runs)


def load_label(reports: Path, label: str) -> dict:
    """Map "<plugin>/<case>" to {tags, with, without, errors} for one label."""
    rows = {}
    files = sorted((reports / label).glob("*.json"))
    if not files:
        sys.exit(f"error: no result JSON under {reports / label}")
    for path in files:
        data = json.loads(path.read_text())
        plugin = path.stem
        for case in data.get("cases", []):
            arms = case.get("arms", {})
            with_runs, without_runs = arms.get("with", []), arms.get("without", [])
            w_score, w_pass, n = arm_stats(with_runs)
            o_score, o_pass, _ = arm_stats(without_runs)
            errors = sorted({r["error"][:80] for r in with_runs if r.get("error")})
            rows[f"{plugin}/{case['name']}"] = {
                "with": (w_score, w_pass, n),
                "without": (o_score, o_pass),
                "errors": errors,
                "ablation": bool(without_runs),
            }
    return rows


def print_label(rows: dict) -> None:
    print(f"{'case':58} {'runs':>4} {'pass':>5} {'score':>5} {'w/o':>5} {'delta':>6}")
    for key, row in rows.items():
        w_score, w_pass, n = row["with"]
        o_score = row["without"][0]
        delta = None if o_score is None or w_score is None else w_score - o_score
        delta_text = "   n/a" if delta is None else f"{delta:+6.2f}"
        print(f"{key:58} {n:4d} {fmt(w_pass, True)} {fmt(w_score)} {fmt(o_score)} {delta_text}")
        for error in row["errors"]:
            print(f"    error: {error}")
    scored = [r["with"][1] for r in rows.values() if r["with"][1] is not None]
    deltas = [r["with"][0] - r["without"][0] for r in rows.values()
              if r["ablation"] and r["with"][0] is not None and r["without"][0] is not None]
    print(f"\ncases: {len(rows)}  mean pass rate: {fmt(mean(scored), True)}")
    if deltas:
        print(f"ablation cases: {len(deltas)}  mean with/without delta: {mean(deltas):+.2f}")


def compare(a: dict, b: dict, label_a: str, label_b: str) -> None:
    print(f"{'case':58} {label_a[:8]:>8} {label_b[:8]:>8} {'change':>7}")
    regressions = 0
    for key in sorted(set(a) | set(b)):
        pa = a.get(key, {}).get("with", (None, None, 0))[1]
        pb = b.get(key, {}).get("with", (None, None, 0))[1]
        change = None if pa is None or pb is None else pb - pa
        flag = ""
        if change is not None and change <= -0.2:
            flag, regressions = "  REGRESSION", regressions + 1
        change_text = "    n/a" if change is None else f"{change * 100:+6.0f}%"
        print(f"{key:58} {fmt(pa, True):>8} {fmt(pb, True):>8} {change_text}{flag}")
    print(f"\nregressions (pass rate down 20 points or more): {regressions}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("label", nargs="?")
    parser.add_argument("--reports", type=Path, default=Path("reports/evals"))
    parser.add_argument("--compare", nargs=2, metavar=("LABEL_A", "LABEL_B"))
    args = parser.parse_args()
    if args.compare:
        compare(load_label(args.reports, args.compare[0]), load_label(args.reports, args.compare[1]),
                *args.compare)
    elif args.label:
        print_label(load_label(args.reports, args.label))
    else:
        parser.error("give a label or --compare A B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
