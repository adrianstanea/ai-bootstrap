#!/usr/bin/env python3
# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Merge settings.fragment.json into a Claude Code settings file without losing local choices.

Missing keys are added and existing scalar values win, so a plugin the user disabled stays
disabled. String lists (permissions) gain missing items. Hook entries are added unless an entry
with the same matcher already runs the same command; an ai-hooks command from another checkout
path is replaced rather than duplicated. Running it twice changes nothing.

Usage: merge_settings.py FRAGMENT TARGET --set NAME=VALUE ... [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import re
import tempfile
from typing import Any, Dict, List, Optional


def substitute(value: Any, names: Dict[str, str]) -> Any:
    if isinstance(value, str):
        for name, text in names.items():
            value = value.replace(f"@{name}@", text)
        return value
    if isinstance(value, list):
        return [substitute(v, names) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, names) for k, v in value.items()}
    return value


def _commands(entry: Dict[str, Any]) -> List[str]:
    return [h.get("command", "") for h in entry.get("hooks", []) if isinstance(h, dict)]


# A hook command this tool manages: the ai-hooks launcher of some checkout, then its arguments.
MANAGED = re.compile(r"^\S*/hooks/bin/ai-hooks (?P<args>.*)$")


def _managed_args(command: str) -> Optional[str]:
    match = MANAGED.match(command)
    return match.group("args") if match else None


def _drop_moved(have: List[Dict[str, Any]], entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Remove ai-hooks commands with the same arguments but another launcher path, so moving
    the checkout replaces its hooks instead of adding a second copy."""
    wanted = {c: _managed_args(c) for c in _commands(entry)}
    stale = {a for a in wanted.values() if a is not None}
    if not stale:
        return have
    kept = []
    for existing in have:
        hooks = [
            h for h in existing.get("hooks", [])
            if not (
                isinstance(h, dict)
                and _managed_args(h.get("command", "")) in stale
                and h.get("command") not in wanted
            )
        ]
        if hooks or not existing.get("hooks"):
            kept.append({**existing, "hooks": hooks} if "hooks" in existing else existing)
    return kept


def merge_hooks(current: Dict[str, Any], wanted: Dict[str, Any]) -> Dict[str, Any]:
    out = {event: list(entries) for event, entries in current.items()}
    for event, entries in wanted.items():
        have = out.setdefault(event, [])
        for entry in entries:
            have = out[event] = _drop_moved(have, entry)
            matcher = entry.get("matcher")
            present = any(
                e.get("matcher") == matcher and set(_commands(entry)) <= set(_commands(e))
                for e in have
            )
            if not present:
                have.append(entry)
    return out


def merge(current: Any, wanted: Any, path: str = "") -> Any:
    if path == "hooks" and isinstance(current, dict) and isinstance(wanted, dict):
        return merge_hooks(current, wanted)
    if isinstance(current, dict) and isinstance(wanted, dict):
        out = dict(current)
        for key, value in wanted.items():
            if key.startswith("$"):
                continue
            child = f"{path}.{key}" if path else key
            out[key] = merge(current[key], value, child) if key in current else value
        return out
    if isinstance(current, list) and isinstance(wanted, list):
        return current + [item for item in wanted if item not in current]
    return current


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fragment")
    parser.add_argument("target")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    names = dict(item.split("=", 1) for item in args.set)
    with open(args.fragment) as handle:
        wanted = substitute(json.load(handle), names)
    try:
        with open(args.target) as handle:
            current = json.load(handle)
    except FileNotFoundError:
        current = {}
    merged = merge(current, wanted)
    if merged == current:
        print(f"{args.target}: up to date")
        return 0
    if args.dry_run:
        print(f"{args.target}: would change")
        return 0
    directory = os.path.dirname(os.path.abspath(args.target))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".settings.", suffix=".json")
    with os.fdopen(fd, "w") as handle:
        json.dump(merged, handle, indent=2)
        handle.write("\n")
    os.replace(tmp, args.target)
    print(f"{args.target}: updated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
