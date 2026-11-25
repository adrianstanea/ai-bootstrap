# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Translate agent hook payloads into events and outcomes back into hook output.

Claude Code, VS Code (Local agent), and Copilot CLI/cloud agent send similar JSON with
different field and tool names, and VS Code ignores matchers, so the harness is not configured:
it is read from the payload. Blocking is rendered as JSON `decision: block` (documented for
Stop and PostToolUse by all three) unless a registration pins `--block-mode exit2`. A pre-tool
deny carries the decision both in Claude's hookSpecificOutput and at the top level, where Copilot
CLI's camelCase hook format reads it.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, TextIO, Tuple

from .model import Outcome
from .record import factory, record

EVENTS = {
    "sessionstart": "session-start",
    "pretooluse": "pre-tool",
    "posttooluse": "post-tool",
    "stop": "stop",
    "agentstop": "stop",
}

SHELL_TOOLS = {"bash", "powershell", "run_in_terminal", "runinterminal", "run_command"}
CREATE_TOOLS = {"write", "create_file", "create"}
EDIT_TOOLS = {
    "edit",
    "multiedit",
    "replace_string_in_file",
    "multi_replace_string_in_file",
    "str_replace_editor",
    "insert_edit_into_file",
}
PATCH_TOOLS = {"apply_patch"}
PATCH_FILE = re.compile(r"\*\*\* (Add|Update) File: ([^\n]+)")


@record
class Event:
    stage: str
    session_id: str = ""
    cwd: str = ""
    tool: str = ""
    command: str = ""
    stop_hook_active: bool = False
    # (absolute path, created) for every file the tool wrote
    touches: List[Tuple[str, bool]] = factory(list)

    @property
    def is_shell(self) -> bool:
        return self.tool in SHELL_TOOLS


def _first(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if payload.get(key) not in (None, ""):
            return payload[key]
    return None


def _tool_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = _first(payload, "tool_input", "toolInput", "toolArgs", "input", "parameters")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {"command": raw}
    return raw if isinstance(raw, dict) else {}


def tool_key(name: str) -> str:
    return name.lower().rsplit(".", 1)[-1]


def _touches(tool: str, tool_input: Dict[str, Any], cwd: str) -> List[Tuple[str, bool]]:
    found: List[Tuple[str, bool]] = []
    if tool in PATCH_TOOLS:
        text = str(_first(tool_input, "input", "patch") or "")
        found = [(m.group(2).strip(), m.group(1) == "Add") for m in PATCH_FILE.finditer(text)]
    elif tool in CREATE_TOOLS or tool in EDIT_TOOLS:
        created = tool in CREATE_TOOLS
        direct = _first(tool_input, "file_path", "filePath", "path")
        if isinstance(direct, str):
            found.append((direct, created))
        for item in tool_input.get("replacements") or tool_input.get("edits") or []:
            if isinstance(item, dict):
                path = _first(item, "filePath", "file_path", "path")
                if isinstance(path, str):
                    found.append((path, created))
    absolute = []
    for path, created in found:
        absolute.append((path if os.path.isabs(path) else os.path.join(cwd, path), created))
    return absolute


def normalize(event_name: str, payload: Dict[str, Any]) -> Optional[Event]:
    stage = EVENTS.get(re.sub(r"[^a-z]", "", event_name.lower()))
    if stage is None:
        return None
    cwd = str(_first(payload, "cwd") or "")
    tool = tool_key(str(_first(payload, "tool_name", "toolName") or ""))
    tool_input = _tool_input(payload)
    event = Event(
        stage=stage,
        session_id=str(_first(payload, "session_id", "sessionId") or ""),
        cwd=cwd,
        tool=tool,
        stop_hook_active=bool(_first(payload, "stop_hook_active", "stopHookActive")),
    )
    if tool in SHELL_TOOLS:
        event.command = str(_first(tool_input, "command", "cmd") or "")
    event.touches = _touches(tool, tool_input, cwd or os.getcwd())
    return event


MAX_SYSTEM_MESSAGE = 600


def _system_message(warnings) -> str:
    text = "\n".join(w for w in warnings if w)
    return text if len(text) <= MAX_SYSTEM_MESSAGE else text[: MAX_SYSTEM_MESSAGE - 3] + "..."


def render(outcome: Outcome, stage: str, block_mode: str, out: TextIO, err: TextIO) -> int:
    """Write the hook response and return the process exit code.

    One channel per hook: exit 2 with stderr when blocking in exit2 mode, otherwise exit 0 with
    a single JSON object on stdout (decision, systemMessage, additionalContext).
    """
    if outcome.blocked and stage != "pre-tool" and block_mode == "exit2":
        print(outcome.message, file=err)
        return 2
    payload: Dict[str, Any] = {}
    if outcome.blocked:
        if stage == "pre-tool":
            payload["hookSpecificOutput"] = {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": outcome.message,
            }
            # Copilot CLI hooks in its camelCase format read the decision at the top level;
            # Claude Code and VS Code read hookSpecificOutput and ignore these keys.
            payload["permissionDecision"] = "deny"
            payload["permissionDecisionReason"] = outcome.message
        else:
            payload["decision"] = "block"
            payload["reason"] = outcome.message
    if outcome.context and stage == "session-start":
        payload["hookSpecificOutput"] = {
            "hookEventName": "SessionStart",
            "additionalContext": outcome.context,
        }
    message = _system_message(outcome.warnings)
    if message:
        payload["systemMessage"] = message
    if payload:
        print(json.dumps(payload), file=out)
    return 0
