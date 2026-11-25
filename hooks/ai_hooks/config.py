# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Per-repository settings from `.ai-hooks.toml`, layered over the user's
`~/.config/ai-hooks/config.toml`.

Every value has a project-neutral default, so a repository without the file gets the generic
checks only, runs tools on this machine, and never looks for a devcontainer.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .record import factory, record

FILE_NAME = ".ai-hooks.toml"
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "ai-hooks" / "config.toml"


@record(frozen=True)
class Config:
    # Docker container whose name contains this text runs the tools; empty disables docker.
    container_name: str = ""
    # Where the main checkout is mounted in that container; empty means /workspaces/<name>.
    container_workspace: str = ""
    # Exported as the repository root before a tool runs, and checked again after env_script.
    root_var: str = ""
    # Repo-relative script sourced before each tool when it exists.
    env_script: str = ""
    # Variables removed from the tool environment.
    unset: Tuple[str, ...] = ()
    # Repo-relative document the commit policy cites.
    commit_policy_doc: str = ""
    pr_workflow: str = "the pull-request-workflow skill"
    # Absolute or repo-relative core.hooksPath to activate; empty uses ai-bootstrap's githooks.
    hooks_path: str = ""
    # Extra directories of project checks, repo-relative or absolute.
    check_paths: Tuple[str, ...] = ()
    gitleaks_config: str = ""
    gitleaks_branches: Tuple[str, ...] = ()
    present: bool = False
    raw: Dict[str, Any] = factory(dict)


def _read_toml(path: Path) -> Dict[str, Any]:
    try:
        import tomllib
    except ImportError:  # Python < 3.11
        return {}
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def _merge(base: Dict[str, Any], top: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in top.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _strings(value: Any, where: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{FILE_NAME}: {where} must be a string or a list of strings")
    return tuple(value)


def _name(value: Any, where: str) -> str:
    text = str(value or "")
    if text and not NAME.match(text):
        raise ValueError(f"{FILE_NAME}: {where} {text!r} is not a shell variable name")
    return text


def parse(data: Dict[str, Any], present: bool) -> Config:
    container = data.get("container", {})
    env = data.get("env", {})
    policy = data.get("policy", {})
    git = data.get("git", {})
    checks = data.get("checks", {})
    gitleaks = data.get("gitleaks", {})
    unset = _strings(env.get("unset"), "env.unset")
    for name in unset:
        _name(name, "env.unset entry")
    return Config(
        container_name=str(container.get("name", "")),
        container_workspace=str(container.get("workspace", "")),
        root_var=_name(env.get("root_var"), "env.root_var"),
        env_script=str(env.get("script", "")),
        unset=unset,
        commit_policy_doc=str(policy.get("commit_doc", "")),
        pr_workflow=str(policy.get("pr_workflow", Config.pr_workflow)),
        hooks_path=str(git.get("hooks_path", "")),
        check_paths=_strings(checks.get("paths"), "checks.paths"),
        gitleaks_config=str(gitleaks.get("config", "")),
        gitleaks_branches=_strings(gitleaks.get("branches"), "gitleaks.branches"),
        present=present,
        raw=data,
    )


@lru_cache(maxsize=32)
def _load(repo_key: str, user_key: str) -> Config:
    repo_file = Path(repo_key) / FILE_NAME if repo_key else None
    user = _read_toml(Path(user_key))
    project = _read_toml(repo_file) if repo_file else {}
    return parse(_merge(user, project), present=bool(repo_file and repo_file.exists()))


@lru_cache(maxsize=64)
def owning_root(repo: Path, rel: str) -> Path:
    """repo, or its main checkout when only the main checkout has rel. Project files such as
    .ai-hooks.toml are often untracked links, so a new linked worktree lacks them until the
    next config sync; falling back keeps its checks and settings in force meanwhile."""
    if (repo / rel).exists():
        return repo
    from . import gitutil

    common = gitutil.common_dir(str(repo))
    main = common.parent if common else repo
    return main if (main / rel).exists() else repo


def load(repo: Optional[Path]) -> Config:
    """Settings for repo (a working-tree root), or the user defaults when repo is None."""
    root = owning_root(repo, FILE_NAME) if repo else None
    return _load(str(root) if root else "", str(user_config_path()))


def lookup(cfg: Config, dotted: str) -> Any:
    """A raw value by dotted key (gitleaks.branches), or None."""
    node: Any = cfg.raw
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node
