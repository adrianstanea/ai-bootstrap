# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Repository setup and commit policy checks that need no devcontainer."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from .. import config as repo_config
from ..model import Check, Result

SIGNOFF = re.compile(r"(--signoff|-s\b)")
# Global options may precede the subcommand (git -C dir -c k=v commit); group 1 holds them.
GIT_COMMIT = re.compile(r"\bgit((?:\s+(?:-C|-c)\s+\S+|\s+--[\w-]+(?:=\S+)?)*)\s+commit\b")
# An actual trailer line, not the phrase appearing in prose such as a message that documents
# this very rule.
CO_AUTHOR = re.compile(r"^\s*co-authored-by\s*:", re.I | re.M)
# ai-bootstrap's own githooks/: this file is <root>/hooks/ai_hooks/checks/policy.py.
BUNDLED_HOOKS = Path(__file__).resolve().parents[3] / "githooks"


def _see_policy(ctx) -> str:
    doc = repo_config.load(ctx.repo).commit_policy_doc if ctx.repo else ""
    return f" (see {doc})" if doc else ""


def hooks_path_for(repo: Path) -> Path:
    """core.hooksPath to activate: git.hooks_path from .ai-hooks.toml, else bundled githooks."""
    configured = repo_config.load(repo).hooks_path
    if not configured:
        return BUNDLED_HOOKS
    path = Path(os.path.expanduser(configured))
    return path if path.is_absolute() else repo / path


def run_hooks_path(ctx, files):
    repo = str(ctx.repo)
    hooks_path = str(hooks_path_for(ctx.repo))
    if not os.path.isdir(hooks_path):
        return Result.fail(f"git hooks directory {hooks_path} does not exist")
    current = subprocess.run(
        ["git", "-C", repo, "config", "--local", "--get", "core.hooksPath"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        universal_newlines=True,
    ).stdout.strip()
    if current == hooks_path:
        return Result.ok()
    result = subprocess.run(
        ["git", "-C", repo, "config", "--local", "core.hooksPath", hooks_path],
        capture_output=True, text=True,
    )
    if result.returncode:
        return Result.fail(f"could not activate Git hooks: {result.stderr}")
    return Result.ok(f"core.hooksPath set to {hooks_path}")


GIT_C = re.compile(r"-C\s+(\S+)")
CD = re.compile(r"(?:^|&&|;|\n)\s*cd\s+(\S+)")
# A repository follows this policy when it is the config repo or a checkout synced from it.
CONFIG_MARKERS = (
    ".ai-bootstrap-repo-marker",
    ".ai-config-repo-marker",
    ".ai-hooks.toml",
    ".agents/hooks",
    ".ai-config-source",
)


def _commit_dir(ctx, code, commit):
    """Directory the commit runs in: its git -C, else the last cd before it, else the cwd."""
    base = Path(ctx.cwd or (str(ctx.repo) if ctx.repo else "") or os.getcwd())
    target = GIT_C.search(commit.group(1) or "")
    if target:
        return base / os.path.expanduser(target.group(1).strip("'\""))
    moves = CD.findall(code[: commit.start()])
    if moves:
        return base / os.path.expanduser(moves[-1].strip("'\""))
    return base


def _uses_ai_config(directory):
    directory = directory.resolve()
    for parent in (directory, *directory.parents):
        if (parent / ".git").exists():
            return any((parent / marker).exists() for marker in CONFIG_MARKERS)
    return True  # no repository found: keep enforcing


def run_commit_policy(ctx, files):
    command = ctx.command
    code = _shell_code(command)
    commit = GIT_COMMIT.search(code)
    if not commit or not _uses_ai_config(_commit_dir(ctx, code, commit)):
        return Result.ok()
    reasons = []
    if not SIGNOFF.search(code):
        reasons.append(f"git commit must include --signoff{_see_policy(ctx)}")
    if CO_AUTHOR.search(command):
        reasons.append("git commit must not add a Co-authored-by trailer")
    return Result.fail("; ".join(reasons)) if reasons else Result.ok()


# Pull requests open as drafts and the remote stack commands stay forbidden. Human approval for
# creating, readying, merging or pushing comes from the permissions.ask rules in
# .claude/settings.json, which still prompt in bypassPermissions mode; a hook can only deny.
SEGMENT = re.compile(r"&&|\|\||;|\||\n")
GH_PR_CREATE = re.compile(r"^\s*(?:\S+=\S+\s+)*gh\s+pr\s+create\b")
DRAFT = re.compile(r"(?:^|\s)(?:--draft|-d)(?:\s|=|$)")
GH_STACK_REMOTE = re.compile(r"^\s*(?:\S+=\S+\s+)*gh\s+stack\s+(push|submit|sync|merge)\b")
GH_API = re.compile(r"^\s*(?:\S+=\S+\s+)*gh\s+api\b")
API_WRITE = re.compile(r"(?:-X|--method)[\s=]*(POST|PATCH|PUT|DELETE)\b", re.I)
API_PULLS = re.compile(r"/pulls\b|/merges\b|graphql")
# The one pull-request write gh api may make: creating a review from a JSON file. GitHub keeps a
# review created without an "event" PENDING, visible only to its author until they submit it in
# the web UI, so the user still reviews, edits and submits it. The shape is exact: no -f/-F
# fields (they could set "event"), no stdin input, and no /reviews/<id>/events submit endpoint.
# Quoted arguments are blanked by _shell_code, so the input path must be unquoted.
PENDING_REVIEW = re.compile(
    r"^\s*gh\s+api\s+(?:-X|--method)[\s=]*POST\s+/?repos/[\w.-]+/[\w.-]+/pulls/\d+/reviews"
    r"\s+--input[\s=]+(?P<input>[^\s'\"-][^\s'\"]*)(?:\s+(?:--jq|-q)[\s=]+'')?\s*$"
)
# The review-thread writes gh api may make: replying to a review thread and resolving it. The
# mutation is read from a JSON file ({"query": ..., "variables": ...}) so this hook can check it;
# permissions.ask in .claude/settings.json still prompts for every `gh api graphql --input`.
THREAD_WRITE = re.compile(
    r"^\s*gh\s+api\s+graphql\s+--input[\s=]+(?P<input>[^\s'\"-][^\s'\"]*)"
    r"(?:\s+(?:--jq|-q)[\s=]+'')?\s*$"
)
THREAD_MUTATIONS = frozenset({"addPullRequestReviewThreadReply", "resolveReviewThread"})
GH_GRAPHQL = re.compile(r"^\s*(?:\S+=\S+\s+)*gh\s+api\s+graphql\b")
# A GraphQL write needs no -X (gh api graphql always POSTs): treat a command that mentions a
# mutation, or a query read from a file or stdin, as a write.
MUTATION = re.compile(r"\bmutation\b")
QUERY_FROM_FILE = re.compile(r"--input\b|=@")


def _workflow(ctx) -> str:
    return repo_config.load(ctx.repo).pr_workflow if ctx.repo else repo_config.Config.pr_workflow


def _is_pending_review(ctx, segment):
    """Return True if *segment* creates a pending PR review from a JSON file with no "event"."""
    match = PENDING_REVIEW.match(segment)
    if not match:
        return False
    path = Path(match.group("input"))
    if not path.is_absolute():
        path = Path(ctx.cwd or os.getcwd()) / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(payload, dict) and "event" not in payload


def _mutation_fields(query):
    """Return the top-level field names of a single-mutation GraphQL document, or None."""
    text = query.strip()
    if not text.startswith("mutation") or "..." in text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    fields, depth, parens, i, token = [], 0, 0, start, ""
    while i < len(text):
        ch = text[i]
        if ch == '"':
            end = text.find('"', i + 1)
            while end > 0 and text[end - 1] == "\\":
                end = text.find('"', end + 1)
            if end < 0:
                return None
            i = end + 1
            continue
        if ch.isalnum() or ch == "_":
            token += ch
        else:
            if token and depth == 1 and parens == 0:
                fields.append(token)
            token = ""
            if ch == ":" and depth == 1 and parens == 0 and fields:
                fields.pop()  # an alias, not a field
            elif ch == "(":
                parens += 1
            elif ch == ")":
                parens -= 1
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return fields if not text[i + 1 :].strip() else None
        i += 1
    return None


def _is_thread_write(ctx, segment):
    """Return True if *segment* only replies to or resolves PR review threads, from a JSON file."""
    match = THREAD_WRITE.match(segment)
    if not match:
        return False
    path = Path(match.group("input"))
    if not path.is_absolute():
        path = Path(ctx.cwd or os.getcwd()) / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(payload, dict) or not isinstance(payload.get("query"), str):
        return False
    fields = _mutation_fields(payload["query"])
    return bool(fields) and set(fields) <= THREAD_MUTATIONS


HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\b", re.S)
QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")


def _shell_code(command):
    """Drop heredoc bodies and quoted strings so text inside them is not read as commands."""
    return QUOTED.sub("''", HEREDOC.sub(" ", command))


def run_remote_policy(ctx, files):
    reasons = []
    for segment in SEGMENT.split(_shell_code(ctx.command)):
        if GH_PR_CREATE.search(segment) and not DRAFT.search(segment):
            reasons.append(
                "gh pr create must open a draft: add --draft; mark it ready only when the user "
                f"asks (see {_workflow(ctx)})"
            )
        stack = GH_STACK_REMOTE.search(segment)
        if stack:
            reasons.append(
                f"gh stack {stack.group(1)} publishes the stack to the remote, which is not "
                f"allowed; push approved branches with git push (see {_workflow(ctx)})"
            )
        graphql_write = GH_GRAPHQL.search(segment) and (
            MUTATION.search(ctx.command) or QUERY_FROM_FILE.search(segment)
        )
        if graphql_write and not _is_thread_write(ctx, segment):
            reasons.append(
                "gh api graphql mutations bypass the approval prompt; the only allowed one is "
                "gh api graphql --input <file.json> whose query only calls "
                "addPullRequestReviewThreadReply or resolveReviewThread"
            )
        elif (
            GH_API.search(segment)
            and API_WRITE.search(segment)
            and API_PULLS.search(segment)
            and not _is_pending_review(ctx, segment)
            and not _is_thread_write(ctx, segment)
        ):
            reasons.append(
                "gh api writes to pull requests bypass the approval prompt; use gh pr commands, "
                "which ask the user first. The only exception is a pending review: "
                "gh api -X POST repos/<o>/<r>/pulls/<n>/reviews --input <file.json> "
                "with no 'event' in the JSON"
            )
    return Result.fail("; ".join(reasons)) if reasons else Result.ok()


def run_trailers(ctx, files):
    path = ctx.message_file
    if not path:
        return Result.skip("no commit message file given")
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    kept = [line for line in lines if not CO_AUTHOR.match(line)]
    while kept and not kept[-1].strip():
        kept.pop()
    if kept == lines:
        return Result.ok()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(kept) + "\n")
    return Result.ok("removed Co-authored-by trailer")


CHECKS = [
    Check(
        name="githooks-path",
        description="Point core.hooksPath at the ai-bootstrap git hooks in opted-in repositories",
        run=run_hooks_path,
        stages={"session-start": "fix"},
        modes=("fix",),
        # Only repositories that opt in with .ai-hooks.toml; never the config repos themselves.
        requires=(".ai-hooks.toml",),
        unless=(".ai-config-repo-marker", ".ai-bootstrap-repo-marker"),
    ),
    Check(
        name="commit-policy",
        description="Deny git commit without --signoff or with a Co-authored-by trailer",
        run=run_commit_policy,
        stages={"pre-tool": "check"},
    ),
    Check(
        name="remote-policy",
        description="Deny non-draft PRs, remote gh stack commands and raw gh api PR writes",
        run=run_remote_policy,
        stages={"pre-tool": "check"},
    ),
    Check(
        name="commit-trailers",
        description="Strip Co-authored-by trailers from the commit message",
        run=run_trailers,
        stages={"commit-msg": "fix"},
        modes=("fix",),
    ),
]
