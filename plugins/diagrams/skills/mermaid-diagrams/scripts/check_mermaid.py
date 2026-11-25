#!/usr/bin/env python3
"""Lint Mermaid diagrams in Markdown (```mermaid blocks) or .mmd files.

Usage:
    python check_mermaid.py FILE [FILE ...] [--render] [--max-nodes N]

Static checks catch common parse breakers and best-practice violations.
--render additionally parses each block with mermaid-cli (mmdc, or `npx -y @mermaid-js/mermaid-cli`)
when available. Exit code: 1 if any ERROR, else 0.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HEADERS = {
    "flowchart": "flowchart", "graph": "flowchart",
    "sequenceDiagram": "sequence", "classDiagram": "class", "classDiagram-v2": "class",
    "stateDiagram": "state", "stateDiagram-v2": "state", "erDiagram": "er",
    "gantt": "gantt", "pie": "pie", "journey": "journey", "gitGraph": "gitgraph",
    "mindmap": "mindmap", "timeline": "timeline", "quadrantChart": "quadrant",
    "requirementDiagram": "requirement", "C4Context": "c4", "C4Container": "c4",
    "C4Component": "c4", "C4Dynamic": "c4", "C4Deployment": "c4",
    "xychart-beta": "xychart", "xychart": "xychart", "sankey-beta": "sankey", "sankey": "sankey",
    "block-beta": "block", "block": "block", "packet-beta": "packet", "packet": "packet",
    "architecture-beta": "architecture", "kanban": "kanban", "info": "info",
}
NON_BETA = {"xychart": "xychart-beta", "sankey": "sankey-beta", "block": "block-beta", "packet": "packet-beta"}
ACC_TYPES = {"flowchart", "sequence", "class", "state", "er", "gantt", "pie", "journey", "requirement"}
COUNT_TYPES = {"flowchart", "class", "state", "er"}
BLOCK_CLOSERS = {"end", "end note"}


class Finding:
    def __init__(self, path, line, level, msg):
        self.path, self.line, self.level, self.msg = path, line, level, msg

    def __str__(self):
        return f"{self.path}:{self.line}: {self.level}: {self.msg}"


def extract_blocks(path: Path):
    """Yield (start_line_1based, [lines]) for each Mermaid block."""
    text = path.read_text(encoding="utf-8").splitlines()
    if path.suffix in {".mmd", ".mermaid"}:
        yield 1, text
        return
    i = 0
    while i < len(text):
        m = re.match(r"^(\s*)(`{3,}|~{3,})\s*mermaid\b", text[i])
        if m:
            fence = m.group(2)
            start = i + 2
            body = []
            i += 1
            while i < len(text) and not text[i].strip().startswith(fence):
                body.append(text[i])
                i += 1
            yield start, body
        i += 1


def strip_quoted(s: str) -> str:
    s = re.sub(r'"[^"]*"', '""', s)
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}", "_", s)
    return s


def lint_block(path, start, lines, max_nodes):
    out = []
    add = lambda off, lvl, msg: out.append(Finding(path, start + off, lvl, msg))

    # Skip front matter
    idx = 0
    if lines and lines[0].strip() == "---":
        idx = 1
        while idx < len(lines) and lines[idx].strip() != "---":
            idx += 1
        if idx >= len(lines):
            add(0, "ERROR", "unterminated front matter (missing closing ---)")
            return out
        idx += 1
    # First meaningful line = header
    while idx < len(lines) and (not lines[idx].strip() or lines[idx].strip().startswith("%%")):
        if lines[idx].strip().startswith("%%{init"):
            add(idx, "WARN", "%%{init}%% directive: prefer front matter `config:`; avoid themes for GitHub")
        idx += 1
    if idx >= len(lines):
        add(0, "ERROR", "empty diagram")
        return out
    header_tok = lines[idx].strip().split()[0].rstrip(":")
    dtype = HEADERS.get(header_tok)
    if dtype is None:
        add(idx, "ERROR", f"unknown diagram header '{header_tok}'")
        return out
    if dtype == "info":
        return out
    if header_tok == "graph":
        add(idx, "WARN", "use `flowchart` instead of legacy `graph`")
    if header_tok == "stateDiagram":
        add(idx, "WARN", "use `stateDiagram-v2`")
    if header_tok in NON_BETA:
        add(idx, "INFO", f"`{header_tok}` needs a recent Mermaid; use `{NON_BETA[header_tok]}` for portability")
    if header_tok in {"architecture-beta", "kanban"} or dtype == "c4":
        add(idx, "INFO", f"`{header_tok}` is beta/experimental: verify the target renderer (```mermaid info```)")

    body = lines[idx + 1:]
    joined = "\n".join(body)
    if dtype in ACC_TYPES and "accTitle" not in joined and "accDescr" not in joined:
        add(idx, "WARN", "missing accTitle/accDescr (accessibility)")

    nodes, edges = set(), 0
    for off, raw in enumerate(body, start=idx + 1):
        line = raw.rstrip()
        s = line.strip()
        if not s or s.startswith("%%"):
            continue
        if "\t" in raw and dtype in {"mindmap", "kanban"}:
            add(off, "ERROR", "tab indentation in indentation-sensitive diagram")
        if re.match(r"^\s*click\b", line):
            add(off, "WARN", "`click` interactions are disabled/sanitised on GitHub")
        if re.search(r"(fill|color|background)\s*:\s*#", line):
            add(off, "WARN", "hard-coded colour; may be unreadable in dark mode")
        # lowercase `end` used as identifier/label (not a block closer)
        if dtype in {"flowchart", "sequence", "state"} and s not in BLOCK_CLOSERS:
            bare = strip_quoted(s)
            if re.search(r"(?<![\w-])end(?![\w-])", bare) and not re.match(r"^end\b", s):
                add(off, "ERROR", "lowercase `end` used as an id/label: write End/END or quote/bracket it")
        if dtype == "flowchart":
            if re.search(r"(---|-->|==>|-\.->)[ox][A-Za-z0-9_]", s):
                add(off, "WARN", "`o`/`x` right after a link creates a circle/cross edge; add a space or capitalise")
            for m in re.finditer(r"(?:^|[\s&>|-])([A-Za-z_][\w-]*)\s*(\[|\(|\{|>)(?!\|)", s):
                if m.group(1) not in {"subgraph", "classDef", "class", "style", "linkStyle", "direction"}:
                    nodes.add(m.group(1))
            edges += len(re.findall(r"-->|---|==>|-\.->|-\.-|<-->|--[ox]\b", s))
            unq = re.search(r"\[([^\]\"]*[():;#][^\]\"]*)\]", s)
            shape = unq and re.fullmatch(r"\(.*\)|\[.*|/.*/|\\.*\\", unq.group(1).strip())
            if unq and not shape and not s.startswith(("classDef", "style", "linkStyle", "acc")):
                add(off, "WARN", f"label with special characters should be quoted: [{unq.group(1)}]")
        elif dtype in {"class", "er", "state"}:
            edges += len(re.findall(r"<\|--|\*--|o--|-->|\.\.>|\.\.\|>|--|\|\|--|\}o--|\}\|--|\|o--", s))
            m = re.match(r"^(class|state)\s+([\w]+)", s)
            if m:
                nodes.add(m.group(2))
            m = re.match(r"^([A-Za-z_][\w-]*)\s*\{\s*$", s)
            if m and dtype == "er":
                nodes.add(m.group(1))
        if dtype == "sequence" and not s.startswith("acc") and ";" in re.sub(r"#\d+;", "", s.split(":", 1)[-1]) and ":" in s:
            add(off, "WARN", "`;` in message text acts as a separator; use #59;")

    if dtype in COUNT_TYPES and (len(nodes) > max_nodes or edges > int(max_nodes * 1.4)):
        add(idx, "WARN", f"large diagram (~{len(nodes)} nodes, ~{edges} edges): split or group (budget ~{max_nodes})")

    if dtype == "sequence":
        opens = len(re.findall(r"^\s*(alt|opt|loop|par|critical|break|rect|box)\b", joined, re.M))
        closes = len(re.findall(r"^\s*end\s*$", joined, re.M))
        if opens != closes:
            add(idx, "ERROR", f"unbalanced blocks: {opens} opened vs {closes} `end`")
        plus = len(re.findall(r"->>\+|-->>\+|-\)\+|^\s*activate\b", joined, re.M))
        minus = len(re.findall(r"->>-|-->>-|-\)-|^\s*deactivate\b", joined, re.M))
        if plus != minus:
            add(idx, "WARN", f"activations may be unbalanced: {plus} activate vs {minus} deactivate")
    if dtype == "flowchart":
        opens = len(re.findall(r"^\s*subgraph\b", joined, re.M))
        closes = len(re.findall(r"^\s*end\s*$", joined, re.M))
        if opens != closes:
            add(idx, "ERROR", f"unbalanced subgraphs: {opens} subgraph vs {closes} `end`")
    if dtype == "gitgraph":
        ids = re.findall(r'\bcommit\b[^\n]*\bid:\s*"([^"]+)"', joined)
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            add(idx, "ERROR", f"duplicate commit ids: {', '.join(sorted(dup))}")
    return out


def find_renderer():
    if shutil.which("mmdc"):
        return ["mmdc"]
    if shutil.which("npx"):
        return ["npx", "-y", "@mermaid-js/mermaid-cli"]
    return None


def render_block(cmd, path, start, lines):
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d, "in.mmd"), Path(d, "out.svg")
        src.write_text("\n".join(lines), encoding="utf-8")
        try:
            r = subprocess.run(cmd + ["-q", "-i", str(src), "-o", str(dst)],
                               capture_output=True, text=True, timeout=180)
        except (subprocess.TimeoutExpired, OSError) as e:
            return [Finding(path, start, "INFO", f"render skipped: {e}")]
        if r.returncode != 0:
            if "npm error" in r.stderr or "npm ERR" in r.stderr:
                return None  # renderer could not be installed/started
            msg = (r.stderr or r.stdout).strip().splitlines()
            detail = next((l for l in msg if "Error" in l or "Parse" in l), msg[0] if msg else "unknown error")
            return [Finding(path, start, "ERROR", f"mermaid-cli: {detail.strip()}")]
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--render", action="store_true", help="also parse with mermaid-cli if available")
    ap.add_argument("--max-nodes", type=int, default=15)
    args = ap.parse_args()

    findings, blocks = [], 0
    cmd = find_renderer() if args.render else None
    if args.render and not cmd:
        print("INFO: mermaid-cli not found; static checks only", file=sys.stderr)
    for f in args.files:
        if not f.exists():
            findings.append(Finding(f, 0, "ERROR", "file not found"))
            continue
        for start, lines in extract_blocks(f):
            blocks += 1
            findings += lint_block(f, start, lines, args.max_nodes)
            if cmd:
                res = render_block(cmd, f, start, lines)
                if res is None:
                    print("INFO: mermaid-cli unavailable (npm failed); static checks only", file=sys.stderr)
                    cmd = None
                else:
                    findings += res
    for x in findings:
        print(x)
    errs = sum(x.level == "ERROR" for x in findings)
    warns = sum(x.level == "WARN" for x in findings)
    print(f"checked {blocks} diagram(s): {errs} error(s), {warns} warning(s)")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
