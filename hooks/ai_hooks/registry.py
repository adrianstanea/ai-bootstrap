# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Check discovery and the single place where a check is executed."""

from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import checks as builtin_checks
from . import config as repo_config
from .context import Context
from .execenv import ToolTimeout, tail
from .model import Check, Result


MAX_FAIL_LINES = 40


def dedupe_fix_hint(text: str) -> str:
    """Keep only the last `Fix with:` line of a failure message."""
    lines = text.splitlines()
    hints = [i for i, line in enumerate(lines) if line.startswith("Fix with:")]
    drop = set(hints[:-1])
    return "\n".join(line for i, line in enumerate(lines) if i not in drop)


def _module_checks(module) -> List[Check]:
    found = getattr(module, "CHECKS", None)
    if found is None:
        single = getattr(module, "CHECK", None)
        found = [single] if single is not None else []
    return list(found)


def _builtin_names(only: Optional[Sequence[str]]) -> List[str]:
    """Built-in check module names, sorted. Lists the directory directly: pkgutil imports inspect."""
    names = set()
    for directory in builtin_checks.__path__:
        for entry in os.listdir(directory):
            if entry.endswith(".py"):
                names.add(entry[:-3])
            elif os.path.isfile(os.path.join(directory, entry, "__init__.py")):
                names.add(entry)
    names.discard("__init__")
    return sorted(n for n in names if only is None or n in only)


PROJECT_CHECKS = ".ai-hooks/checks"


def project_check_dirs(repo: Optional[Path]) -> List[str]:
    """Project check directories: .ai-hooks/checks, checks.paths from .ai-hooks.toml, and
    AI_HOOKS_CHECKS_PATH (os.pathsep separated), in that order."""
    dirs: List[str] = []
    if repo is not None:
        default = repo_config.owning_root(repo, PROJECT_CHECKS) / PROJECT_CHECKS
        if default.is_dir():
            dirs.append(str(default))
        for rel in repo_config.load(repo).check_paths:
            path = Path(os.path.expanduser(rel))
            if not path.is_absolute():
                path = repo_config.owning_root(repo, rel) / path
            dirs.append(str(path))
    dirs += [d for d in os.environ.get("AI_HOOKS_CHECKS_PATH", "").split(os.pathsep) if d]
    return dirs


def load_checks(
    extra_dirs: Optional[Sequence[str]] = None,
    only: Optional[Sequence[str]] = None,
    repo: Optional[Path] = None,
) -> Dict[str, Check]:
    """Built-in checks plus the project checks of repo (see project_check_dirs).

    `only` restricts the built-in modules (by module name), so a hot path such as PreToolUse
    imports a single built-in module; project checks still load, since a project may add
    pre-tool policy of its own.
    """
    collected: List[Check] = []
    for name in _builtin_names(only):
        module = importlib.import_module(f"{builtin_checks.__name__}.{name}")
        collected += _module_checks(module)

    dirs = list(extra_dirs or []) + project_check_dirs(repo)
    for directory in dirs:
        for path in sorted(Path(directory).glob("*.py")):
            spec = importlib.util.spec_from_file_location(f"ai_hooks_ext_{path.stem}", str(path))
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            collected += _module_checks(module)

    registry: Dict[str, Check] = {}
    for check in collected:
        check.validate()
        if check.name in registry:
            raise ValueError(f"duplicate check name {check.name!r}")
        registry[check.name] = check
    return registry


def checks_for_stage(registry: Dict[str, Check], stage: str) -> List[Check]:
    return [c for c in registry.values() if stage in c.stages]


def available(check: Check, ctx: Context) -> Optional[Result]:
    """None when the check can run here, else the silent skip explaining why not."""
    for rel in check.requires:
        if not ctx.exists(rel):
            return Result.skip(f"{rel} not found", silent=True)
    for rel in check.unless:
        if ctx.exists(rel):
            return Result.skip(f"{rel} present", silent=True)
    return None


def execute(check: Check, ctx: Context, files: Sequence[str], mode: str) -> Result:
    """Run one check against files, applying the preconditions every check shares."""
    unavailable = available(check, ctx)
    if unavailable is not None:
        return unavailable
    if mode not in check.modes:
        return Result.skip(f"{check.name} has no {mode} mode", silent=True)
    if check.needs_container and not ctx.env.has_tools:
        if ctx.stage == "pre-commit":
            return Result.fail(f"{check.name}: devcontainer not running; start it and try again")
        # The agent cannot start the devcontainer, so this never blocks it.
        return Result.skip(f"{check.name} skipped: devcontainer not running", env=True)
    run_ctx = ctx.derive(ctx.repo, mode=mode)
    try:
        result = check.run(run_ctx, list(files))
    except ToolTimeout as exc:
        return Result.skip(f"{check.name} skipped: {exc}", env=True)
    except Exception as exc:  # a broken check must not take the agent session down
        if ctx.stage == "pre-commit":
            return Result.fail(f"{check.name} crashed: {type(exc).__name__}: {exc}")
        return Result.skip(f"{check.name} crashed: {type(exc).__name__}: {exc}")
    if result.status == "fail":
        result.message = dedupe_fix_hint(tail(result.message, MAX_FAIL_LINES))
    return result
