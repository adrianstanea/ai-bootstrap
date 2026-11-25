# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""merge_settings: local choices survive, re-runs are no-ops, a moved checkout is replaced."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from merge_settings import merge  # noqa: E402

OLD = "/home/u/dev/ai-bootstrap/hooks/bin/ai-hooks"
NEW = "/home/u/.local/share/ai-bootstrap/hooks/bin/ai-hooks"


def pre_tool(launcher, args="hook PreToolUse"):
    return {"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": f"{launcher} {args}"}]}
    ]}}


class MergeTest(unittest.TestCase):
    def test_existing_scalars_and_disabled_plugins_win(self):
        current = {"model": "opus", "enabledPlugins": {"a@m": False}}
        wanted = {"model": "sonnet", "enabledPlugins": {"a@m": True, "b@m": True}}
        self.assertEqual(
            merge(current, wanted), {"model": "opus", "enabledPlugins": {"a@m": False, "b@m": True}}
        )

    def test_lists_gain_only_missing_items(self):
        merged = merge({"permissions": {"ask": ["x"]}}, {"permissions": {"ask": ["x", "y"]}})
        self.assertEqual(merged["permissions"]["ask"], ["x", "y"])

    def test_second_run_changes_nothing(self):
        once = merge({}, pre_tool(OLD))
        self.assertEqual(merge(once, pre_tool(OLD)), once)

    def test_moved_checkout_replaces_its_hook(self):
        merged = merge(pre_tool(OLD), pre_tool(NEW))
        commands = [h["command"] for e in merged["hooks"]["PreToolUse"] for h in e["hooks"]]
        self.assertEqual(commands, [f"{NEW} hook PreToolUse"])

    def test_other_hooks_are_kept(self):
        current = pre_tool(OLD)
        current["hooks"]["PreToolUse"].append(
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-guard"}]}
        )
        merged = merge(current, pre_tool(NEW))
        commands = [h["command"] for e in merged["hooks"]["PreToolUse"] for h in e["hooks"]]
        self.assertEqual(commands, ["my-own-guard", f"{NEW} hook PreToolUse"])

    def test_different_ai_hooks_actions_are_independent(self):
        current = pre_tool(OLD, "graphify-guard search")
        merged = merge(current, pre_tool(NEW))
        commands = [h["command"] for e in merged["hooks"]["PreToolUse"] for h in e["hooks"]]
        self.assertEqual(commands, [f"{OLD} graphify-guard search", f"{NEW} hook PreToolUse"])


if __name__ == "__main__":
    unittest.main()
