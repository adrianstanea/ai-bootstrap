#!/usr/bin/env python3
# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Time each ai-hooks event with synthetic payloads and print median and p90 in milliseconds.

The benchmark uses a unique session id and deletes its state files, so it leaves nothing behind.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path


def _payloads(root: Path, session: str) -> dict:
    target = str(root / "bench-target.md")
    base = {"session_id": session, "cwd": str(root)}
    return {
        "SessionStart": dict(base, source="startup"),
        "PreToolUse": dict(base, tool_name="Bash", tool_input={"command": "git status"}),
        "PostToolUse": dict(base, tool_name="Read", tool_input={"file_path": target}),
        "Stop": dict(base, stop_hook_active=False),
        "graphify-guard": dict(base, tool_name="Grep", tool_input={"pattern": "x"}),
    }


def _argv(event: str) -> list:
    """Launcher arguments; graphify-guard is a top-level command, the rest are hook events."""
    return ["graphify-guard", "search"] if event == "graphify-guard" else ["hook", event]


def _time_event(launcher: Path, event: str, payload: dict, root: Path, runs: int) -> list:
    env = {k: v for k, v in os.environ.items() if k != "BASH_ENV"}
    env["CLAUDE_PROJECT_DIR"] = str(root)
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        subprocess.run(
            [sys.executable, str(launcher), *_argv(event)],
            input=json.dumps(payload), universal_newlines=True, env=env, cwd=str(root),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        samples.append((time.perf_counter() - start) * 1000)
    return samples


def _p90(samples: list) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))]


def _delete_state(root: Path, session: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True,
    )
    if proc.returncode != 0:
        return
    state = Path(proc.stdout.strip()) / "ai-hooks" / "state"
    for name in (f"{session}.json", f"env-{session}.json", f"{session}.tmp"):
        try:
            (state / name).unlink()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=os.getcwd(), help="repository to run against")
    parser.add_argument("-n", type=int, default=10, help="runs per event")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    # The launcher of this checkout, run against --root.
    launcher = Path(__file__).resolve().parents[1] / "hooks" / "bin" / "ai-hooks"
    if not launcher.exists():
        print(f"no launcher at {launcher}", file=sys.stderr)
        return 2
    session = f"bench-{uuid.uuid4().hex[:12]}"
    print(f"{'event':15} {'median ms':>10} {'p90 ms':>10}")
    try:
        for event, payload in _payloads(root, session).items():
            samples = _time_event(launcher, event, payload, root, args.n)
            print(f"{event:15} {statistics.median(samples):10.1f} {_p90(samples):10.1f}")
    finally:
        _delete_state(root, session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
