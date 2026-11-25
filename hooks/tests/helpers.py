# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Shared fixtures: throwaway git repos, a fake `docker`, and a hook-process runner."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HOOKS_DIR = Path(__file__).resolve().parent.parent
# Checks of a sample C++/Python project, installed as the repo's .ai-hooks/checks.
PROJECT_CHECKS = Path(__file__).resolve().parent / "fixtures" / "project_checks"
AI_HOOKS_TOML = """[container]
name = "example-devcontainer"
workspace = "/workspaces/example"
"""
LAUNCHER = HOOKS_DIR / "bin" / "ai-hooks"

FAKE_DOCKER = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
stdin = "" if argv[:1] == ["ps"] else sys.stdin.read() if "test" not in argv[:6] else ""
with open(os.environ["FAKE_DOCKER_LOG"], "a") as log:
    log.write(json.dumps({"argv": argv, "stdin": stdin}) + "\\n")
if argv[:1] == ["ps"]:
    print("example-devcontainer-1")
elif argv[:1] == ["exec"] and "test" not in argv[:6]:
    rc = int(os.environ.get("FAKE_DOCKER_RC", "0"))
    if rc:
        print(os.environ.get("FAKE_DOCKER_OUT", "tool failed"))
    sys.exit(rc)
"""

STUB = """#!/usr/bin/env bash
printf '%s\\n' "$(basename "$0") $*" >> "$STUB_LOG"
if [ -n "${STUB_RC:-}" ]; then echo "${STUB_OUT:-stub failed}"; exit "$STUB_RC"; fi
"""


def write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class RepoTestCase(unittest.TestCase):
    """A host-like checkout in a temp dir, with fake docker and stub tools on PATH."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-hooks-test-")).resolve()
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        self.repo = self.tmp / "example"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        # Synced checkouts carry this marker; commit policy applies only to such repositories.
        (self.repo / ".ai-config-source").write_text("test\n")
        with open(self.repo / ".git" / "info" / "exclude", "a", encoding="utf-8") as handle:
            handle.write("/.ai-config-source\n")
        self.bin = self.tmp / "bin"
        write_executable(self.bin / "docker", FAKE_DOCKER)
        self.docker_log = self.tmp / "docker.log"
        self.stub_log = self.tmp / "stub.log"
        for rel in (
            "scripts/run-clang-tidy.sh",
            "scripts/check_license_headers.py",
            "scripts/docs-tooling.sh",
        ):
            write_executable(self.repo / rel, STUB)
        write_executable(self.bin / "uvx", STUB)
        write_executable(self.bin / "shellcheck", STUB)
        (self.repo / ".pre-commit-config.yaml").write_text(
            "repos:\n"
            "  - repo: https://github.com/zizmorcore/zizmor-pre-commit\n"
            "    rev: v1.31.1\n"
            "    hooks:\n"
            "      - id: zizmor\n"
        )
        (self.repo / ".ai-hooks.toml").write_text(AI_HOOKS_TOML)
        checks = self.repo / ".ai-hooks" / "checks"
        checks.mkdir(parents=True)
        for path in PROJECT_CHECKS.glob("*.py"):
            shutil.copy(path, checks / path.name)
        (self.repo / "cli").mkdir()
        (self.repo / "cli" / "pyproject.toml").write_text("")
        (self.repo / "CMakePresets.json").write_text("{}")
        (self.repo / ".clang-format").write_text("BasedOnStyle: LLVM\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")

    def git(self, *args: str, cwd: Optional[Path] = None) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd or self.repo), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, check=True,
        )
        return proc.stdout

    def env(self, **extra: str) -> Dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "AI_HOOKS_", "BASH_ENV"))}
        env.update(
            PATH=f"{self.bin}{os.pathsep}{env['PATH']}",
            AI_HOOKS_ENV="docker",
            FAKE_DOCKER_LOG=str(self.docker_log),
            STUB_LOG=str(self.stub_log),
            CLAUDE_PROJECT_DIR=str(self.repo),
        )
        env.update(extra)
        return env

    def run_hook(self, event: str, payload: dict, *flags: str, cwd: Optional[Path] = None, **env) -> Tuple[int, str, str]:
        payload = dict(payload)
        payload.setdefault("session_id", "s1")
        payload.setdefault("cwd", str(cwd or self.repo))
        proc = subprocess.run(
            [sys.executable, str(LAUNCHER), "hook", event, *flags],
            input=json.dumps(payload), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, env=self.env(**env), cwd=str(cwd or self.repo),
        )
        return proc.returncode, proc.stdout, proc.stderr

    def run_cli(self, *args: str, stdin: str = "", **env) -> Tuple[int, str, str]:
        proc = subprocess.run(
            [sys.executable, str(LAUNCHER), *args], input=stdin, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, universal_newlines=True, env=self.env(**env), cwd=str(self.repo),
        )
        return proc.returncode, proc.stdout, proc.stderr

    def docker_calls(self) -> List[dict]:
        """docker exec calls that ran a tool: root, cwd relative to root, command, stdin."""
        if not self.docker_log.exists():
            return []
        calls = []
        for line in self.docker_log.read_text().splitlines():
            entry = json.loads(line)
            argv = entry["argv"]
            if argv[:1] == ["exec"] and "-lc" in argv:
                tail = argv[argv.index("-lc") + 3:]
                calls.append({"root": tail[0], "cwd": tail[1], "command": tail[2:], "stdin": entry["stdin"]})
        return calls

    def stub_calls(self) -> List[str]:
        return self.stub_log.read_text().splitlines() if self.stub_log.exists() else []

    def touch_file(self, rel: str, text: str = "x\n") -> str:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return str(path)
