#!/usr/bin/env python3
"""Validate plugins/*/skills/*/SKILL.md against the Agent Skills specification.

Usage: tools/check_skills.py [--json] [--strict-budget] [skills-dir]
       (default skills-dir: <repo>/plugins)

Checks the rules every agent relies on for discovery (https://agentskills.io/specification):
  - SKILL.md has YAML frontmatter
  - `name` is lowercase-hyphen, at most 64 characters, and equals the directory name
  - `description` is a non-empty string of at most 1024 characters
  - `compatibility`, when present, is at most 500 characters
  - SKILL.md stays within 500 lines (move detail into references/ instead)
  - frontmatter has only known keys (spec keys plus Claude Code keys)
  - relative markdown links and backticked references/, scripts/, assets/ paths exist
  - `description` (plus `when_to_use`) is at most 600 characters and contains no XML-like <tag>
  - total description size of model-invocable skills is reported; above 8000 characters it is a
    warning, or an error with --strict-budget
  - --json prints a machine-readable report on stdout

Exit status: 0 clean, 1 violations found, 2 tooling problem (e.g. PyYAML missing).
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
MAX_LINES = 500
MAX_DESCRIPTION_SOFT = 600
MAX_BUDGET = 8000
ALLOWED_KEYS = {
    "name", "description", "license", "compatibility", "metadata", "allowed-tools",
    "when_to_use", "disable-model-invocation", "user-invocable", "disallowed-tools", "model",
    "effort", "context", "agent", "hooks", "paths", "argument-hint", "arguments",
}
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
TICK_PATH_RE = re.compile(r"`((?:references|scripts|assets)/[^`\s*<>{}]+)`")
TAG_RE = re.compile(r"</?[A-Za-z][\w-]*(?:\s[^<>]*)?/?>")
FENCE_RE = re.compile(r"^(```|~~~).*?^\1", re.DOTALL | re.MULTILINE)


def read_frontmatter(text: str):
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not match:
        return None
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        problem = str(getattr(exc, "problem", None) or exc).splitlines()[0]
        raise ValueError(f"SKILL.md frontmatter is not valid YAML: {problem}") from exc
    return data if isinstance(data, dict) else None


def check_skill(skill_dir: Path) -> tuple[list[str], dict]:
    skill_file = skill_dir / "SKILL.md"
    info = {"description_chars": 0, "lines": 0, "model_invocable": False}
    if not skill_file.is_file():
        return ["missing SKILL.md"], info

    text = skill_file.read_text(encoding="utf-8")
    try:
        front = read_frontmatter(text)
    except ValueError as exc:
        return [str(exc)], info
    if front is None:
        return ["SKILL.md has no valid YAML frontmatter"], info

    errors = []
    for key in sorted(set(front) - ALLOWED_KEYS):
        errors.append(f"unknown frontmatter key `{key}`")
    name = front.get("name")
    if not isinstance(name, str) or not name:
        errors.append("frontmatter `name` is missing")
    else:
        if len(name) > MAX_NAME or not NAME_RE.match(name):
            errors.append(f"`name` {name!r} must be lowercase-hyphen, <= {MAX_NAME} chars")
        if name != skill_dir.name:
            errors.append(f"`name` {name!r} must match the directory name {skill_dir.name!r}")

    description = front.get("description")
    when_to_use = front.get("when_to_use")
    if when_to_use is not None and not isinstance(when_to_use, str):
        errors.append("`when_to_use` must be a string")
        when_to_use = None
    if not isinstance(description, str) or not description.strip():
        errors.append("frontmatter `description` is missing or empty")
    else:
        # Claude Code lists description and when_to_use together, so both count.
        description = "\n".join(filter(None, [description.strip(), (when_to_use or "").strip()]))
        length = len(description)
        info["description_chars"] = length
        if length > MAX_DESCRIPTION:
            errors.append(f"`description` is {length} chars, max {MAX_DESCRIPTION}")
        elif length > MAX_DESCRIPTION_SOFT:
            errors.append(f"`description` is {length} chars, max {MAX_DESCRIPTION_SOFT} for routing")
        if TAG_RE.search(description):
            errors.append("`description` contains an XML-like <tag>")

    compatibility = front.get("compatibility")
    if isinstance(compatibility, str) and len(compatibility) > MAX_COMPATIBILITY:
        errors.append(f"`compatibility` is {len(compatibility)} chars, max {MAX_COMPATIBILITY}")

    info["model_invocable"] = front.get("disable-model-invocation") is not True

    lines = text.count("\n") + 1
    info["lines"] = lines
    if lines > MAX_LINES:
        errors.append(f"SKILL.md is {lines} lines, max {MAX_LINES}; move detail to references/")
    errors.extend(check_links(skill_dir, text))
    return errors, info


def check_links(skill_dir: Path, text: str) -> list[str]:
    """Report relative links and backticked bundled paths that do not exist."""
    body = FENCE_RE.sub("", text.split("\n---\n", 1)[-1])
    # Skills without a bundled scripts/ dir cite the host repo's scripts/, which must not fail.
    targets = {
        t
        for t in TICK_PATH_RE.findall(body)
        if not t.startswith("scripts/") or (skill_dir / "scripts").is_dir()
    }
    for raw in LINK_RE.findall(body):
        if re.match(r"^(?:[a-z][a-z0-9+.-]*:|#|/)", raw):
            continue
        targets.add(raw.split("#", 1)[0])
    errors = []
    for target in sorted(t for t in targets if t):
        if not (skill_dir / target).exists():
            errors.append(f"referenced path does not exist: {target}")
    return errors


def main() -> int:
    default = Path(__file__).resolve().parent.parent / "plugins"
    parser = argparse.ArgumentParser(description="Validate SKILL.md files.")
    parser.add_argument("skills_root", nargs="?", type=Path, default=default)
    parser.add_argument("--json", action="store_true", help="print a JSON report on stdout")
    parser.add_argument("--strict-budget", action="store_true",
                        help=f"fail when model-invocable descriptions exceed {MAX_BUDGET} chars")
    args = parser.parse_args()
    skills_root = args.skills_root
    if not skills_root.is_dir():
        print(f"error: skills directory not found: {skills_root}", file=sys.stderr)
        return 2

    plugin_skills = sorted(p for p in skills_root.glob("*/skills/*") if p.is_dir())
    if plugin_skills:  # plugins/ layout: plugins/<id>/skills/<skill>[/SKILL.md]
        skill_dirs = plugin_skills
    else:
        skill_dirs = sorted(p for p in skills_root.iterdir() if p.is_dir())

    skills = []
    budget = 0
    for skill_dir in skill_dirs:
        errors, info = check_skill(skill_dir)
        if info["model_invocable"]:
            budget += info["description_chars"]
        skills.append({"skill": skill_dir.name, "path": str(skill_dir), "errors": errors, **info})

    problems = sum(len(s["errors"]) for s in skills)
    warnings = []
    if budget > MAX_BUDGET:
        message = f"model-invocable description budget is {budget} chars, max {MAX_BUDGET}"
        if args.strict_budget:
            problems += 1
            skills.append({"skill": "(budget)", "path": "", "errors": [message]})
        else:
            warnings.append(message)

    if args.json:
        report = {"ok": problems == 0, "problems": problems, "description_budget": budget,
                  "budget_limit": MAX_BUDGET, "warnings": warnings, "skills": skills}
        print(json.dumps(report, indent=2))
        return 1 if problems else 0

    for entry in skills:
        for error in entry["errors"]:
            print(f"{entry['skill']}: {error}", file=sys.stderr)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(f"description budget (model-invocable): {budget}/{MAX_BUDGET} chars")
    if problems:
        print(f"{problems} problem(s) in {len(skill_dirs)} skill(s)", file=sys.stderr)
        return 1
    print(f"ok: {len(skill_dirs)} skills valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
