# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Units: the check model, payload normalization, hook output, and the policy checks."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from ai_hooks import harness
from ai_hooks.checks import policy
from ai_hooks.context import Context
from ai_hooks.execenv import ExecEnv
from ai_hooks.model import Check, Outcome, Result


def _noop(ctx, files):
    return Result.ok()


class CheckModelTest(unittest.TestCase):
    def test_patterns_match_nested_paths(self):
        check = Check("c", "d", _noop, patterns=("*/CMakeLists.txt", "cli/src/*.py"))
        self.assertTrue(check.matches("lib/modules/CMakeLists.txt"))
        self.assertTrue(check.matches("cli/src/pkg/mod.py"))
        self.assertFalse(check.matches("lib/modules/foo.cpp"))

    def test_no_patterns_matches_everything(self):
        self.assertTrue(Check("c", "d", _noop).matches("anything/at/all.bin"))

    def test_validate_rejects_unsupported_mode_and_unknown_stage(self):
        with self.assertRaises(ValueError):
            Check("c", "d", _noop, stages={"edit": "fix"}).validate()
        with self.assertRaises(ValueError):
            Check("c", "d", _noop, stages={"nope": "check"}).validate()


class NormalizeTest(unittest.TestCase):
    def test_claude_edit(self):
        event = harness.normalize(
            "PostToolUse",
            {"session_id": "a", "cwd": "/r", "tool_name": "Edit", "tool_input": {"file_path": "/r/x.cpp"}},
        )
        self.assertEqual((event.stage, event.session_id), ("post-tool", "a"))
        self.assertEqual(event.touches, [("/r/x.cpp", False)])

    def test_claude_write_is_a_creation(self):
        event = harness.normalize("PostToolUse", {"tool_name": "Write", "tool_input": {"file_path": "/r/n.cpp"}})
        self.assertEqual(event.touches, [("/r/n.cpp", True)])

    def test_vscode_local_camelcase_paths_and_create(self):
        event = harness.normalize(
            "PostToolUse", {"cwd": "/r", "tool_name": "create_file", "tool_input": {"filePath": "/r/a.md"}}
        )
        self.assertEqual(event.touches, [("/r/a.md", True)])

    def test_multi_replace_collects_every_file(self):
        event = harness.normalize(
            "PostToolUse",
            {
                "cwd": "/r",
                "tool_name": "multi_replace_string_in_file",
                "tool_input": {"replacements": [{"filePath": "/r/a.cpp"}, {"filePath": "/r/b.cpp"}]},
            },
        )
        self.assertEqual([p for p, _ in event.touches], ["/r/a.cpp", "/r/b.cpp"])

    def test_apply_patch_add_update_delete(self):
        patch = "*** Begin Patch\n*** Add File: new.cpp\n*** Update File: old.cpp\n*** Delete File: gone.cpp\n"
        event = harness.normalize(
            "PostToolUse", {"cwd": "/r", "tool_name": "functions.apply_patch", "tool_input": {"input": patch}}
        )
        self.assertEqual(event.touches, [("/r/new.cpp", True), ("/r/old.cpp", False)])

    def test_copilot_tool_args_json_string(self):
        event = harness.normalize(
            "preToolUse", {"toolName": "bash", "toolArgs": json.dumps({"command": "git commit -m x"})}
        )
        self.assertEqual((event.stage, event.is_shell, event.command), ("pre-tool", True, "git commit -m x"))

    def test_read_tools_touch_nothing(self):
        event = harness.normalize("PostToolUse", {"tool_name": "Read", "tool_input": {"file_path": "/r/x"}})
        self.assertEqual(event.touches, [])

    def test_unknown_event_is_ignored(self):
        self.assertIsNone(harness.normalize("Notification", {}))


class RenderTest(unittest.TestCase):
    def _render(self, outcome, stage, mode="json"):
        out, err = io.StringIO(), io.StringIO()
        return harness.render(outcome, stage, mode, out, err), out.getvalue(), err.getvalue()

    def test_stop_block_is_a_json_decision_with_exit_zero(self):
        rc, out, _ = self._render(Outcome(blocked=True, message="boom"), "stop")
        self.assertEqual((rc, json.loads(out)), (0, {"decision": "block", "reason": "boom"}))

    def test_exit2_mode_uses_stderr(self):
        rc, out, err = self._render(Outcome(blocked=True, message="boom"), "stop", "exit2")
        self.assertEqual((rc, out, err.strip()), (2, "", "boom"))

    def test_pre_tool_deny(self):
        rc, out, _ = self._render(Outcome(blocked=True, message="no"), "pre-tool", "exit2")
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual((rc, decision["permissionDecision"]), (0, "deny"))

    def test_warnings_are_a_system_message_without_blocking(self):
        rc, out, err = self._render(Outcome(warnings=["careful"]), "post-tool")
        self.assertEqual((rc, json.loads(out), err), (0, {"systemMessage": "careful"}, ""))


class PolicyTest(unittest.TestCase):
    def _run(self, command):
        ctx = Context(repo=None, env=ExecEnv("none"), command=command)
        return policy.run_commit_policy(ctx, []).status

    def test_signed_commit_passes(self):
        self.assertEqual(self._run('git commit --signoff -m "x"'), "pass")

    def test_unsigned_commit_fails(self):
        self.assertEqual(self._run('git commit -m "x"'), "fail")

    def test_trailer_line_fails_but_prose_passes(self):
        self.assertEqual(self._run("git commit -s -m 'a\n\nCo-authored-by: A <a@b.c>'"), "fail")
        self.assertEqual(self._run('git commit -s -m "never add Co-authored-by: trailers"'), "pass")

    def test_other_commands_pass(self):
        self.assertEqual(self._run("git status"), "pass")

    def _in(self, cwd, command):
        ctx = Context(repo=None, env=ExecEnv("none"), command=command, cwd=str(cwd))
        return policy.run_commit_policy(ctx, []).status

    def _repos(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        for name in ("configured", "other"):
            (root / name / ".git").mkdir(parents=True)
        (root / "configured" / ".agents" / "hooks").mkdir(parents=True)
        return root / "configured", root / "other"

    def test_policy_applies_only_to_repos_using_the_config(self):
        configured, other = self._repos()
        self.assertEqual(self._in(configured, 'git commit -m "x"'), "fail")
        self.assertEqual(self._in(other, 'git commit -m "x"'), "pass")
        self.assertEqual(self._in(configured, f'cd {other} && git commit -m "x"'), "pass")
        self.assertEqual(self._in(other, f'cd {configured} && git commit -m "x"'), "fail")
        self.assertEqual(self._in(other, f'git -C {configured} commit -m "x"'), "fail")

    def test_commit_text_inside_quotes_is_not_a_commit(self):
        configured, _ = self._repos()
        self.assertEqual(self._in(configured, "grep -n 'git commit' notes.md"), "pass")
        heredoc = "python3 - <<'EOF'\nprint('git commit -m x')\nEOF"
        self.assertEqual(self._in(configured, heredoc), "pass")
        trailer = "git commit -s -F - <<'EOF'\nsubject\n\nCo-authored-by: A <a@b.c>\nEOF"
        self.assertEqual(self._in(configured, trailer), "fail")

    def _remote(self, command):
        ctx = Context(repo=None, env=ExecEnv("none"), command=command)
        return policy.run_remote_policy(ctx, []).status

    def test_pr_create_must_be_draft(self):
        self.assertEqual(self._remote('gh pr create --title t --body b'), "fail")
        self.assertEqual(self._remote('git push -u origin x && gh pr create -t t -b b'), "fail")
        self.assertEqual(self._remote('gh pr create --draft --title t --body b'), "pass")
        self.assertEqual(self._remote('GH_TOKEN=x gh pr create -d -t t'), "pass")
        # --draft elsewhere in the command does not excuse a later non-draft create.
        self.assertEqual(self._remote('gh pr list --draft; gh pr create -t t'), "fail")

    def test_remote_stack_commands_are_denied(self):
        for sub in ("push", "submit", "sync", "merge"):
            self.assertEqual(self._remote(f"gh stack {sub}"), "fail", sub)
        self.assertEqual(self._remote("gh stack rebase"), "pass")

    def test_gh_api_pull_writes_are_denied(self):
        self.assertEqual(self._remote("gh api -X PATCH repos/o/r/pulls/3 -f draft=false"), "fail")
        self.assertEqual(self._remote("gh api --method POST repos/o/r/pulls -f title=t"), "fail")
        self.assertEqual(self._remote("gh api repos/o/r/pulls/3"), "pass")
        self.assertEqual(self._remote("gh api -X POST repos/o/r/issues/3/labels"), "pass")

    def _review(self, command, payload):
        """Run the remote policy on *command* with *payload* written to review.json in cwd."""
        with tempfile.TemporaryDirectory() as tmp:
            if payload is not None:
                Path(tmp, "review.json").write_text(payload, encoding="utf-8")
            ctx = Context(repo=None, env=ExecEnv("none"), command=command, cwd=tmp)
            return policy.run_remote_policy(ctx, []).status

    def test_gh_api_may_create_only_a_pending_review(self):
        create = "gh api -X POST repos/o/r/pulls/3/reviews --input review.json"
        pending = json.dumps({"commit_id": "abc", "comments": [{"path": "a", "line": 1}]})
        self.assertEqual(self._review(create, pending), "pass")
        self.assertEqual(self._review(f"{create} --jq '.html_url'", pending), "pass")
        self.assertEqual(self._review(create.replace("-X POST", "--method=POST"), pending), "pass")
        # An "event" submits the review immediately, so it is denied whatever its value.
        for event in ("COMMENT", "APPROVE", "REQUEST_CHANGES", ""):
            self.assertEqual(self._review(create, json.dumps({"event": event})), "fail", event)
        # Unverifiable or malformed input is denied.
        self.assertEqual(self._review(create, None), "fail")
        self.assertEqual(self._review(create, "not json"), "fail")
        self.assertEqual(self._review(create, "[]"), "fail")
        self.assertEqual(self._review(create.replace("review.json", "-"), pending), "fail")
        quoted = create.replace("review.json", "'review.json'")
        self.assertEqual(self._review(quoted, pending), "fail")
        # Fields could set "event"; other endpoints submit, edit or delete.
        self.assertEqual(self._review(f"{create} -f event=APPROVE", pending), "fail")
        self.assertEqual(self._review(f"{create} -F event=APPROVE", pending), "fail")
        submit = "gh api -X POST repos/o/r/pulls/3/reviews/9/events --input review.json"
        self.assertEqual(self._review(submit, pending), "fail")
        self.assertEqual(self._review(create.replace("POST", "PUT"), pending), "fail")
        self.assertEqual(self._review(create.replace("/reviews", "/comments"), pending), "fail")
        # A pending review does not excuse another write in the same command.
        merge = "gh api -X PUT repos/o/r/pulls/3/merge"
        self.assertEqual(self._review(f"{create} && {merge}", pending), "fail")

    def test_gh_api_graphql_may_only_reply_to_and_resolve_review_threads(self):
        call = "gh api graphql --input review.json"
        reply = "mutation($t: ID!, $b: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $t, body: $b}) { comment { id } } }"
        both = "mutation { r: addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: \"T\", body: \"a } b\"}) { comment { id } } resolveReviewThread(input: {threadId: \"T\"}) { thread { isResolved } } }"
        for query in (reply, both):
            payload = json.dumps({"query": query, "variables": {"t": "T", "b": "x"}})
            self.assertEqual(self._review(call, payload), "pass", query)
            self.assertEqual(self._review(f"{call} --jq ''", payload), "pass", query)
        # Any other mutation, a second operation, fragments or a non-mutation are denied.
        for query in (
            "mutation { mergePullRequest(input: {pullRequestId: \"P\"}) { clientMutationId } }",
            "mutation { resolveReviewThread(input: {threadId: \"T\"}) { thread { id } } "
            "markPullRequestReadyForReview(input: {pullRequestId: \"P\"}) { clientMutationId } }",
            "mutation { resolveReviewThread(input: {threadId: \"T\"}) { thread { id } } } "
            "mutation m { mergePullRequest(input: {pullRequestId: \"P\"}) { clientMutationId } }",
            "mutation { ...F } fragment F on Mutation { mergePullRequest(input: {}) { clientMutationId } }",
            "query { viewer { login } }",
        ):
            self.assertEqual(self._review(call, json.dumps({"query": query})), "fail", query)
        payload = json.dumps({"query": reply})
        self.assertEqual(self._review(call, None), "fail")
        self.assertEqual(self._review(call, "not json"), "fail")
        self.assertEqual(self._review(call.replace("review.json", "-"), payload), "fail")
        self.assertEqual(self._review(call.replace("review.json", "'review.json'"), payload), "fail")
        self.assertEqual(self._review(f"{call} -f query=x", payload), "fail")
        # Inline mutations and queries read from a file are denied even without -X.
        inline = "gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: \"T\"}) { thread { id } } }'"
        self.assertEqual(self._review(inline, None), "fail")
        self.assertEqual(self._review("gh api graphql -F query=@q.graphql", None), "fail")
        # Read-only queries still pass.
        self.assertEqual(self._review("gh api graphql -f query='query { viewer { login } }'", None), "pass")
        # A thread write does not excuse another write in the same command.
        merge = "gh api -X PUT repos/o/r/pulls/3/merge"
        self.assertEqual(self._review(f"{call} && {merge}", payload), "fail")

    def test_unrelated_commands_pass(self):
        self.assertEqual(self._remote("gh pr view 3 --json state"), "pass")
        self.assertEqual(self._remote('echo "gh pr create" > notes.txt'), "pass")
        self.assertEqual(self._remote("grep -E 'draft|gh pr create' SKILL.md"), "pass")
        self.assertEqual(
            self._remote("python3 - <<'EOF'\nx = 1\ngh pr create --title t\nEOF\necho done"),
            "pass",
        )
        self.assertEqual(self._remote('cat <<EOF\ngh pr create\nEOF\ngh pr create -t "a|b"'), "fail")

    def test_trailer_stripping(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".msg", delete=False) as handle:
            handle.write("subject\n\nbody\n\nCo-authored-by: A <a@b.c>\n\n")
            path = handle.name
        self.addCleanup(os.unlink, path)
        result = policy.run_trailers(Context(repo=None, env=ExecEnv("none"), message_file=path), [])
        self.assertEqual(result.status, "pass")
        with open(path) as handle:
            self.assertEqual(handle.read(), "subject\n\nbody\n")


class ExecEnvTest(unittest.TestCase):
    def test_local_tools_see_login_profile_path(self):
        # git and IDEs can start hooks with a bare PATH; tools such as uv are only on the PATH
        # a login profile adds.
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home)
        tools = os.path.join(home, "tools")
        os.mkdir(tools)
        with open(os.path.join(tools, "profile-tool"), "w") as handle:
            handle.write("#!/bin/sh\necho found\n")
        os.chmod(os.path.join(tools, "profile-tool"), 0o755)
        with open(os.path.join(home, ".bash_profile"), "w") as handle:
            handle.write(f'export PATH="{tools}:$PATH"\n')
        env = {"HOME": home, "PATH": "/usr/bin:/bin"}
        rc, out = ExecEnv("local").run_tool(Path(home), ["profile-tool"], env=env)
        self.assertEqual((rc, out.strip()), (0, "found"))


class LauncherTest(unittest.TestCase):
    LAUNCHER = Path(__file__).resolve().parent.parent / "bin" / "ai-hooks"

    def _run(self, project: Path, *args: str):
        import subprocess
        import sys

        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        env["CLAUDE_PROJECT_DIR"] = str(project)
        return subprocess.run(
            [sys.executable, "-X", "importtime", str(self.LAUNCHER), *args],
            input="{}", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, env=env,
        )

    def test_graphify_guard_without_graph_skips_the_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".git").mkdir()
            proc = self._run(Path(tmp), "graphify-guard", "search")
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("ai_hooks", proc.stderr)

    def test_pycache_prefix_is_inside_the_git_dir(self):
        import importlib.machinery
        import importlib.util

        loader = importlib.machinery.SourceFileLoader("ai_hooks_launcher", str(self.LAUNCHER))
        spec = importlib.util.spec_from_loader("ai_hooks_launcher", loader)
        launcher = importlib.util.module_from_spec(spec)
        loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.realpath(tmp)
            main = Path(root) / "main"
            (main / ".git").mkdir(parents=True)
            (main / "bin").mkdir()
            self.assertEqual(
                launcher.pycache_prefix(str(main / "bin" / "ai-hooks")),
                str(main / ".git" / "ai-hooks" / "pycache"),
            )
            worktree = Path(root) / "wt"
            (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
            (main / ".git" / "worktrees" / "wt" / "commondir").write_text("../..\n")
            worktree.mkdir()
            (worktree / ".git").write_text(f"gitdir: {main}/.git/worktrees/wt\n")
            self.assertEqual(
                launcher.pycache_prefix(str(worktree / "x")),
                str(main / ".git" / "ai-hooks" / "pycache"),
            )


if __name__ == "__main__":
    unittest.main()
