# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Command line entry point.

    ai-hooks list [--json]
    ai-hooks doctor
    ai-hooks run [CHECK...] [--stage S] [--files F... | --files-from - | --staged | --since BASE | --all]
                 [--mode fix|check] [--env auto|local|docker|none] [--json]
    ai-hooks hook EVENT [--block-mode json|exit2] [--record DIR]      (agent hook registrations)
    ai-hooks git pre-commit | commit-msg FILE                          (.githooks shims)

Exit status: 0 passed or skipped, 1 a check failed, 2 usage or tooling error.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import gitutil, harness, hooks
from .context import Context
from . import config as repo_config
from .execenv import ENV_MODES, ExecEnv
from .model import MODES, STAGES
from .registry import available, load_checks


def _parser():
    import argparse

    parser = argparse.ArgumentParser(prog="ai-hooks", description="Run AI-agent, git, and task checks.")
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="list registered checks")
    listing.add_argument("--json", action="store_true")

    doctor = sub.add_parser("doctor", help="show the environment and which checks can run here")
    doctor.add_argument("--env", choices=ENV_MODES, default=None)

    run = sub.add_parser("run", help="run checks over files (for tasks and CI)")
    run.add_argument("checks", nargs="*", help="check names; default: every applicable check")
    run.add_argument("--stage", choices=STAGES, help="run the checks registered for this stage")
    run.add_argument("--mode", choices=MODES, default=None, help="default: check")
    run.add_argument("--env", choices=ENV_MODES, default=None)
    run.add_argument("--json", action="store_true")
    source = run.add_mutually_exclusive_group()
    source.add_argument("--files", nargs="+", metavar="FILE")
    source.add_argument("--files-from", metavar="PATH", help="newline separated list; - for stdin")
    source.add_argument("--staged", action="store_true", help="files staged in the git index")
    source.add_argument("--since", metavar="BASE", help="files changed from BASE to HEAD")
    source.add_argument("--all", action="store_true", help="every tracked file")

    hook = sub.add_parser("hook", help="handle an agent hook event read from stdin")
    hook.add_argument("event", help="SessionStart, PreToolUse, PostToolUse, or Stop")
    hook.add_argument(
        "--block-mode",
        choices=("json", "exit2"),
        default=os.environ.get("AI_HOOKS_BLOCK_MODE", "json"),
        help="how a block is reported: JSON decision (default) or exit status 2 with stderr",
    )
    hook.add_argument(
        "--emit-invariants",
        action="store_true",
        help="print context/critical-invariants.md as SessionStart additionalContext and exit",
    )
    hook.add_argument("--record", metavar="DIR", help="save the raw payload there, to build fixtures")

    guard = sub.add_parser("graphify-guard", help="run `graphify hook-guard` only when a graph exists")
    guard.add_argument("mode", choices=("search", "read"))

    config = sub.add_parser("config", help="print a value from .ai-hooks.toml (dotted key)")
    config.add_argument("key", help="for example gitleaks.branches")

    git = sub.add_parser("git", help="handle a git hook")
    git.add_argument("hook", choices=("pre-commit", "commit-msg"))
    git.add_argument("message_file", nargs="?")
    return parser


def _repo(path: Optional[str] = None) -> Optional[Path]:
    return gitutil.toplevel(path or os.getcwd())


def _read_stdin_json() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def cmd_list(args) -> int:
    registry = load_checks(repo=_repo())
    if args.json:
        rows = [
            {
                "name": c.name,
                "description": c.description,
                "stages": c.stages,
                "modes": list(c.modes),
                "patterns": list(c.patterns),
                "requires": list(c.requires),
                "needs_container": c.needs_container,
            }
            for c in registry.values()
        ]
        print(json.dumps(rows, indent=2))
        return 0
    for check in registry.values():
        stages = ", ".join(f"{s}:{m}" for s, m in check.stages.items())
        print(f"{check.name:16} {stages:40} {check.description}")
    return 0


def cmd_doctor(args) -> int:
    repo = _repo()
    if repo is None:
        print("not inside a git repository", file=sys.stderr)
        return 2
    env = ExecEnv.detect(args.env)
    env.repo = repo
    cfg = repo_config.load(repo)
    print(f"repo         {repo}")
    print(f"config       {repo / repo_config.FILE_NAME if cfg.present else 'none (defaults)'}")
    print(f"environment  {env.describe()}")
    ctx = Context(repo=repo, env=env)
    for check in load_checks(repo=repo).values():
        reason = available(check, ctx)
        state = "ready" if reason is None else f"unavailable ({reason.message})"
        if reason is None and check.needs_container and not env.has_tools:
            state = "needs the devcontainer"
        print(f"  {check.name:16} {state}")
    return 0


def _select_files(args, repo: Path) -> Optional[List[str]]:
    if args.staged:
        return gitutil.staged_files(repo)
    if args.since:
        return gitutil.changed_since(repo, args.since)
    if args.all:
        return gitutil.tracked_files(repo)
    if args.files_from:
        text = sys.stdin.read() if args.files_from == "-" else Path(args.files_from).read_text()
        return [line.strip() for line in text.splitlines() if line.strip()]
    if args.files:
        return list(args.files)
    return None


def _relative(repo: Path, files: Sequence[str]) -> List[str]:
    out = []
    for item in files:
        rel = gitutil.relative_to(repo, item) if os.path.isabs(item) else item
        if rel and not rel.startswith(".."):
            out.append(rel)
    return out


def cmd_run(args) -> int:
    repo = _repo()
    if repo is None:
        print("not inside a git repository", file=sys.stderr)
        return 2
    registry = load_checks(repo=repo)
    unknown = [n for n in args.checks if n not in registry]
    if unknown:
        print(f"unknown check(s): {', '.join(unknown)}; see `ai-hooks list`", file=sys.stderr)
        return 2
    files = _select_files(args, repo)
    if files is None:
        print("choose files with --files, --files-from, --staged, --since, or --all", file=sys.stderr)
        return 2
    files = _relative(repo, files)
    env = ExecEnv.detect(args.env)
    env.repo = repo
    ctx = Context(repo=repo, env=env, staged=args.staged)
    if args.stage:
        results = hooks.run_stage(registry, ctx, args.stage, files)
    else:
        results = hooks.run_checks(registry, ctx, args.checks, files, args.mode)
    if args.json:
        print(json.dumps([{"check": n, "status": r.status, "message": r.message} for n, r in results], indent=2))
    else:
        report = hooks.format_results(results)
        if report:
            print(report)
    return hooks.exit_code(results)


INVARIANTS = Path(__file__).resolve().parent.parent / "context" / "critical-invariants.md"
PROJECT_INVARIANTS = ".ai-hooks/invariants.md"


def _invariants_text() -> str:
    """The project's .ai-hooks/invariants.md when present, else the bundled generic list."""
    repo = _repo(os.environ.get("CLAUDE_PROJECT_DIR"))
    for path in ([repo / PROJECT_INVARIANTS] if repo else []) + [INVARIANTS]:
        try:
            return path.read_text().strip()
        except OSError:
            continue
    return ""


def cmd_config(args) -> int:
    """Print one .ai-hooks.toml value: a list one item per line, a table as JSON."""
    repo = _repo()
    value = repo_config.lookup(repo_config.load(repo), args.key)
    if value is None:
        return 1
    if isinstance(value, list):
        for item in value:
            print(item)
    elif isinstance(value, dict):
        print(json.dumps(value))
    else:
        print(value)
    return 0


def cmd_graphify_guard(args) -> int:
    """exec `graphify hook-guard MODE` when the repo has a graph and graphify is installed."""
    repo = gitutil.toplevel(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    import shutil

    executable = shutil.which("graphify")
    if repo is None or executable is None or not (repo / "graphify-out" / "graph.json").is_file():
        return 0
    os.execv(executable, [executable, "hook-guard", args.mode])
    return 0  # unreachable


def cmd_hook(args) -> int:
    if args.emit_invariants:
        text = _invariants_text()
        if not text:
            return 0
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
        print(json.dumps(out))
        return 0
    payload = _read_stdin_json()
    if args.record:
        directory = Path(args.record)
        directory.mkdir(parents=True, exist_ok=True)
        import time

        stamp = f"{args.event}-{int(time.time() * 1000)}.json"
        (directory / stamp).write_text(json.dumps(payload, indent=2))
    try:
        event = harness.normalize(args.event, payload)
        if event is None:
            return 0
        if event.stage == "pre-tool" and not event.is_shell:
            return 0
        repo = hooks.session_repo(event)
        only = ("policy",) if event.stage == "pre-tool" else None
        registry = load_checks(only=only, repo=repo)
        outcome = hooks.dispatch(event, registry, ExecEnv.detect())
    except Exception:  # a hook bug must never take the agent session down
        import traceback

        traceback.print_exc(file=sys.stderr)
        return 0
    code = harness.render(outcome, event.stage, args.block_mode, sys.stdout, sys.stderr)
    if hooks.stragglers:
        # Interpreter exit would join the overrunning worker threads and defeat the wait budget.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
    return code


def cmd_git(args) -> int:
    repo = _repo()
    if repo is None:
        return 0
    registry = load_checks(repo=repo)
    env = ExecEnv.detect()
    env.repo = repo
    if args.hook == "commit-msg":
        if not args.message_file:
            print("commit-msg needs the message file path", file=sys.stderr)
            return 2
        ctx = Context(repo=repo, env=env, message_file=args.message_file)
        results = hooks.run_stage(registry, ctx, "commit-msg", [])
        return hooks.exit_code(results)

    files = gitutil.staged_files(repo)
    if not files:
        return 0
    ctx = Context(repo=repo, env=env, staged=True)
    results = hooks.run_stage(registry, ctx, "pre-commit", files)
    report = hooks.format_results(results)
    if report:
        print(report, file=sys.stderr)
    for _, result in results:
        if result.status == "fail":
            print(result.message, file=sys.stderr)
        elif result.status == "skip" and result.message and not result.silent:
            print(f"warning: {result.message}; skipped (CI will still enforce it)", file=sys.stderr)
    if hooks.exit_code(results):
        print(
            "pre-commit checks failed on staged changes. Fix the issues above, re-stage,\n"
            "and commit again (or git commit --no-verify to bypass, not recommended).",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    handlers = {"list": cmd_list, "doctor": cmd_doctor, "run": cmd_run, "hook": cmd_hook, "git": cmd_git, "graphify-guard": cmd_graphify_guard, "config": cmd_config}
    try:
        return handlers[args.command](args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
