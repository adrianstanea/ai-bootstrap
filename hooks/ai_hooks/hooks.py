# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Stage dispatchers: what runs for an agent event, a git hook, or a task-system call."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import gitutil
from .context import Context
from .execenv import ExecEnv
from .harness import Event
from .model import FAIL, PASS, SKIP, Check, Outcome, Result
from .registry import checks_for_stage, execute
from .state import SessionState

DEFAULT_MAX_STOP_BLOCKS = 3

Results = List[Tuple[str, Result]]

# Set when a Stop check overran the wait budget and its worker thread is still running.
stragglers = False


def session_repo(event: Event) -> Optional[Path]:
    base = os.environ.get("CLAUDE_PROJECT_DIR") or event.cwd or os.getcwd()
    return gitutil.toplevel(base)


def _group_by_worktree(session_repo: Path, absolute_paths: Sequence[str]) -> Dict[Path, List[Tuple[str, str]]]:
    """Group files by the worktree that owns them as (relative, absolute) pairs. Files that
    belong to a different repository are dropped; linked worktrees of this one are kept."""
    home = gitutil.common_dir(str(session_repo))
    owners: Dict[str, Optional[Path]] = {}
    groups: Dict[Path, List[Tuple[str, str]]] = {}
    for absolute in absolute_paths:
        directory = os.path.dirname(absolute)
        if directory not in owners:
            top = gitutil.toplevel(directory)
            owners[directory] = top if top is not None and gitutil.common_dir(str(top)) == home else None
        root = owners[directory]
        if root is None:
            continue
        rel = os.path.relpath(os.path.realpath(absolute), str(root))
        if rel.startswith(".."):
            continue
        groups.setdefault(root, []).append((rel, absolute))
    return groups


MAX_TOTAL_CHARS = 4000
STOP_CHECK_TIMEOUT = 200.0  # per check; checks run concurrently, under the 300 s hook timeout
STOP_WAIT_BUDGET = 250.0
STOP_WORKERS = 4
GRAPHIFY_CONTEXT = (
    "A graphify knowledge graph exists at graphify-out/graph.json. "
    "`graphify query \"<question>\"`, `graphify path \"<A>\" \"<B>\"` and `graphify explain "
    "\"<concept>\"` return a scoped subgraph that is usually much smaller than grep output or "
    "GRAPH_REPORT.md. `graphify update .` refreshes the graph after code changes (AST-only). "
    "A committed graph.json is rewritten whole on every build, so a large diff to it is expected."
)


def cap_failures(failures: Sequence[str], limit: int = MAX_TOTAL_CHARS) -> str:
    """Join failure messages, truncating so the total stays within limit characters."""
    text = "\n\n".join(failures)
    if len(text) <= limit:
        return text
    note = "\n... output truncated"
    return text[: limit - len(note)] + note


def _collect(results: Results, blocked_stage: bool, state: Optional[SessionState] = None) -> Outcome:
    failures = [f"[{name}] {r.message}" for name, r in results if r.status == FAIL]
    warnings: List[str] = []
    for name, r in results:
        if r.status != SKIP or not r.message or r.silent:
            continue
        if r.env and state is not None and not state.notify_env_once(name):
            continue
        warnings.append(r.message)
    if blocked_stage and failures:
        return Outcome(blocked=True, message=cap_failures(failures), warnings=warnings, detail=results)
    return Outcome(warnings=warnings + [cap_failures(failures, 1000)] * bool(failures), detail=results)


def dispatch(event: Event, registry: Dict[str, Check], env: ExecEnv) -> Outcome:
    repo = session_repo(event)
    if repo is None:
        return Outcome()
    env.repo = repo
    base = Context(repo=repo, env=env, session_id=event.session_id)
    if event.session_id:
        common = gitutil.common_dir(str(repo))
        if common is not None:
            env.cache_file = common / "ai-hooks" / "state" / f"env-{event.session_id}.json"
    if event.stage == "session-start":
        return _session_start(base, registry)
    if event.stage == "pre-tool":
        return _pre_tool(base, registry, event)
    if event.stage == "post-tool":
        return _post_tool(base, registry, event)
    if event.stage == "stop":
        return _stop(base, registry, event)
    return Outcome()


def _session_start(base: Context, registry: Dict[str, Check]) -> Outcome:
    state = SessionState.for_repo(base.repo, base.session_id)
    if state is not None:
        state.prune_stale()
    results: Results = []
    for check in checks_for_stage(registry, "session-start"):
        ctx = base.derive(base.repo, stage="session-start")
        results.append((check.name, execute(check, ctx, [], check.stages["session-start"])))
    # Session start never blocks, and a missing devcontainer there is not worth a warning.
    failures = [f"[{n}] {r.message}" for n, r in results if r.status == FAIL]
    context = GRAPHIFY_CONTEXT if (base.repo / "graphify-out" / "graph.json").is_file() else ""
    return Outcome(warnings=failures, detail=results, context=context)


def _pre_tool(base: Context, registry: Dict[str, Check], event: Event) -> Outcome:
    if not event.is_shell:
        return Outcome()
    ctx = base.derive(base.repo, stage="pre-tool", command=event.command, cwd=event.cwd)
    results = [
        (c.name, execute(c, ctx, [], c.stages["pre-tool"])) for c in checks_for_stage(registry, "pre-tool")
    ]
    return _collect(results, blocked_stage=True)


def _post_tool(base: Context, registry: Dict[str, Check], event: Event) -> Outcome:
    if not event.touches:
        return Outcome()
    created = {path: was_created for path, was_created in event.touches if was_created}
    state = SessionState.for_repo(base.repo, base.session_id)
    groups = _group_by_worktree(base.repo, [path for path, _ in event.touches])
    results: Results = []
    for root, items in groups.items():
        for _, absolute in items:
            if state is not None:
                state.touch(absolute)
        for check in registry.values():
            stage = "edit" if "edit" in check.stages else "create" if "create" in check.stages else None
            if stage is None:
                continue
            pool = [rel for rel, absolute in items if stage == "edit" or absolute in created]
            files = check.select(pool)
            if files:
                ctx = base.derive(root, stage=stage)
                results.append((check.name, execute(check, ctx, files, check.stages[stage])))
    outcome = _collect(results, blocked_stage=True, state=state)
    if state is not None:
        state.save()
    return outcome


def _stop(base: Context, registry: Dict[str, Check], event: Event) -> Outcome:
    state = SessionState.for_repo(base.repo, base.session_id)
    if state is None or not state.files:
        return Outcome()
    limit = int(os.environ.get("AI_HOOKS_MAX_STOP_BLOCKS", DEFAULT_MAX_STOP_BLOCKS))
    fp = gitutil.fingerprint(base.repo, state.files)
    unchanged = bool(state.last_block_fp) and fp == state.last_block_fp
    if unchanged and (event.stop_hook_active or state.stop_blocks >= limit):
        names = ", ".join(state.last_failing) or "stop checks"
        return Outcome(warnings=[f"ai-hooks: still failing and unchanged since the last block: {names}"])
    if not unchanged:
        state.stop_blocks = 0

    tasks: List[Tuple[Check, Context, List[str], List[str]]] = []
    for root, items in _group_by_worktree(base.repo, state.files).items():
        by_rel = {rel: absolute for rel, absolute in items}
        for check in checks_for_stage(registry, "stop"):
            if state.passed_at(check.name, fp):
                continue
            pending_abs = state.pending(check.name, [by_rel[r] for r in check.select(list(by_rel))])
            if not pending_abs:
                continue
            rels = [rel for rel, absolute in items if absolute in pending_abs]
            tasks.append((check, base.derive(root, stage="stop"), rels, pending_abs))

    base.env.timeout = STOP_CHECK_TIMEOUT
    if any(check.needs_container for check, _, _, _ in tasks):
        base.env.has_tools  # resolve once, before the worker threads share the environment
    results = _run_concurrently(tasks)
    for (check, task_ctx, _, pending_abs), (_, result) in zip(tasks, results):
        if result.status == PASS:
            state.mark_passed(check.name, pending_abs)
        if result.status in (PASS, FAIL):
            state.record(check.name, fp, result.status, str(task_ctx.repo))
    outcome = _collect(results, blocked_stage=True, state=state)
    if outcome.blocked:
        state.stop_blocks += 1
        state.last_block_fp = fp
        state.last_failing = [name for name, r in results if r.status == FAIL]
    else:
        state.stop_blocks = 0
        state.last_block_fp = ""
        state.last_failing = []
    state.save()
    return outcome


def _run_task(check: Check, ctx: Context, rels: List[str], mode: str) -> Result:
    ctx.env.start_check_deadline(STOP_CHECK_TIMEOUT)
    return execute(check, ctx, rels, mode)


def _run_concurrently(tasks) -> Results:
    """Run independent checks in parallel; a check that overruns the budget is reported skipped."""
    if not tasks:
        return []
    from concurrent.futures import ThreadPoolExecutor, wait

    pool = ThreadPoolExecutor(max_workers=min(STOP_WORKERS, len(tasks)))
    futures = [pool.submit(_run_task, check, ctx, rels, check.stages["stop"]) for check, ctx, rels, _ in tasks]
    wait(futures, timeout=STOP_WAIT_BUDGET)
    global stragglers
    results: Results = []
    for (check, _, _, _), future in zip(tasks, futures):
        if future.done():
            results.append((check.name, future.result()))
        else:
            stragglers = True
            results.append((check.name, Result.skip(f"{check.name} skipped: exceeded time budget", env=True)))
    pool.shutdown(wait=False, cancel_futures=True)
    return results


def run_checks(
    registry: Dict[str, Check],
    ctx: Context,
    names: Sequence[str],
    files: Sequence[str],
    mode: Optional[str],
) -> Results:
    """Run named checks (or every check usable in the mode) over files, for git hooks and tasks."""
    results: Results = []
    chosen = [registry[n] for n in names] if names else list(registry.values())
    for check in chosen:
        selected = check.select(files)
        if not selected:
            results.append((check.name, Result.skip("no matching files", silent=True)))
            continue
        results.append((check.name, execute(check, ctx, selected, mode or "check")))
    return results


def run_stage(registry: Dict[str, Check], ctx: Context, stage: str, files: Sequence[str]) -> Results:
    """Run every check registered for stage, each in the mode that stage declares."""
    results: Results = []
    for check in checks_for_stage(registry, stage):
        selected = check.select(files)
        if not selected and (files or check.patterns):
            continue
        results.append((check.name, execute(check, ctx.derive(ctx.repo, stage=stage), selected, check.stages[stage])))
    return results


def format_results(results: Results) -> str:
    lines = []
    for name, result in results:
        if result.status == SKIP and result.silent:
            continue
        lines.append(f"[{result.status}] {name}" + (f": {result.message}" if result.message else ""))
    return "\n".join(lines)


def exit_code(results: Results) -> int:
    return 1 if any(r.status == FAIL for _, r in results) else 0
