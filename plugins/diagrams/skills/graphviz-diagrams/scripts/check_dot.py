#!/usr/bin/env python3
"""Validate and lint Graphviz DOT diagrams.

Usage:
    python check_dot.py FILE [FILE ...] [--render] [--max-nodes N]

Inputs:
    .dot / .gv          whole file is one or more graphs
    .rst                `.. graphviz::` (inline or external file), `.. digraph:: name`, `.. graph:: name`
    .md                 fences ```dot / ```graphviz / ```gv and MyST ```{graphviz} [file]

Checks: full DOT grammar parse (pure Python, no Graphviz needed), HTML-label XML
well-formedness, edge-operator/graph-type mismatch, cluster/compound/lhead usage,
best-practice warnings. --render also runs `dot` (if installed) and reports its
errors/warnings. Exit code 1 if any ERROR.
"""
import argparse
import html.entities
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

KEYWORDS = {"strict", "graph", "digraph", "node", "edge", "subgraph"}


class Finding:
    def __init__(self, src, line, level, msg):
        self.src, self.line, self.level, self.msg = src, line, level, msg

    def __str__(self):
        return f"{self.src}:{self.line}: {self.level}: {self.msg}"


class DotSyntaxError(Exception):
    def __init__(self, line, msg):
        super().__init__(msg)
        self.line, self.msg = line, msg


# ----------------------------------------------------------------- tokenizer
class Tok:
    __slots__ = ("kind", "val", "line")

    def __init__(self, kind, val, line):
        self.kind, self.val, self.line = kind, val, line

    def __repr__(self):
        return f"{self.kind}:{self.val!r}@{self.line}"


def tokenize(text):
    toks, i, n, line = [], 0, len(text), 1
    at_line_start = True
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            at_line_start = True
            continue
        if c in " \t\r\f\v":
            i += 1
            continue
        if c == "#" and at_line_start:
            while i < n and text[i] != "\n":
                i += 1
            continue
        at_line_start = False
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise DotSyntaxError(line, "unterminated /* comment")
            line += text.count("\n", i, j)
            i = j + 2
            continue
        if c == '"':
            start_line, j, buf = line, i + 1, []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    if text[j + 1] == "\n":  # line continuation
                        line += 1
                        j += 2
                        continue
                    buf.append(text[j:j + 2])
                    j += 2
                    continue
                if text[j] == "\n":
                    line += 1
                buf.append(text[j])
                j += 1
            if j >= n:
                raise DotSyntaxError(start_line, "unterminated quoted string")
            toks.append(Tok("QSTR", "".join(buf), start_line))
            i = j + 1
            continue
        if c == "<":
            start_line, depth, j = line, 0, i
            while j < n:
                if text[j] == "<":
                    depth += 1
                elif text[j] == ">":
                    depth -= 1
                    if depth == 0:
                        break
                elif text[j] == "\n":
                    line += 1
                j += 1
            if j >= n:
                raise DotSyntaxError(start_line, "unterminated HTML string (unbalanced < >)")
            toks.append(Tok("HTML", text[i + 1:j], start_line))
            i = j + 1
            continue
        if text.startswith("->", i) or text.startswith("--", i):
            toks.append(Tok("EDGEOP", text[i:i + 2], line))
            i += 2
            continue
        if c in "{}[]=;,:+":
            toks.append(Tok(c, c, line))
            i += 1
            continue
        m = re.compile(r"-?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)").match(text, i)
        if m:
            end = m.end()
            if end < n and (text[end].isalpha() or text[end] == "_"):
                raise DotSyntaxError(line, f"badly delimited number/ID near '{text[i:end + 8].split()[0]}' "
                                           "(quote IDs that start with digits or contain '-' or '.')")
            toks.append(Tok("ID", m.group(0), line))
            i = end
            continue
        m = re.compile(r"[A-Za-z_\u0080-\uffff][A-Za-z0-9_\u0080-\uffff]*").match(text, i)
        if m:
            toks.append(Tok("ID", m.group(0), line))
            i = m.end()
            continue
        hint = " (unquoted ID containing '-'? quote it or use '_')" if c == "-" else ""
        raise DotSyntaxError(line, f"unexpected character '{c}'{hint}")
    toks.append(Tok("EOF", "", line))
    return toks


# ------------------------------------------------------------------- parser
class Model:
    def __init__(self):
        self.directed = None
        self.graph_attrs = {}            # root-level graph attrs
        self.nodes = {}                  # id -> merged attrs (explicit decls)
        self.node_lines = {}
        self.edges = []                  # (tail, head, attrs, line)
        self.subgraphs = []              # (name, attrs, line, parent_is_cluster)
        self.html_labels = []            # (html, line)
        self.quoted_labels = []          # (value, line)
        self.rank_same_in_cluster = []   # lines
        self.node_defaults_font = False
        self.edge_defaults_font = False


class Parser:
    def __init__(self, toks):
        self.t, self.i, self.m = toks, 0, Model()
        self.cluster_depth = 0

    def peek(self, k=0):
        return self.t[self.i + k]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expect(self, kind, what=None):
        tok = self.next()
        if tok.kind != kind:
            raise DotSyntaxError(tok.line, f"expected {what or kind}, got '{tok.val or tok.kind}'")
        return tok

    def is_kw(self, tok, kw):
        return tok.kind == "ID" and tok.val.lower() == kw

    def parse_id(self):
        tok = self.next()
        if tok.kind == "QSTR":
            val = tok.val
            while self.peek().kind == "+":
                self.next()
                val += self.expect("QSTR", "quoted string after '+'").val
            return ("QSTR", val, tok.line)
        if tok.kind == "HTML":
            return ("HTML", tok.val, tok.line)
        if tok.kind == "ID":
            if tok.val.lower() in KEYWORDS:
                raise DotSyntaxError(tok.line, f"keyword '{tok.val}' used as ID: quote it")
            return ("ID", tok.val, tok.line)
        raise DotSyntaxError(tok.line, f"expected ID, got '{tok.val or tok.kind}'")

    def parse_file(self):
        graphs = 0
        while self.peek().kind != "EOF":
            self.parse_graph()
            graphs += 1
        if graphs == 0:
            raise DotSyntaxError(1, "no graph found (expected 'graph' or 'digraph')")
        return self.m

    def parse_graph(self):
        tok = self.peek()
        if self.is_kw(tok, "strict"):
            self.next()
            tok = self.peek()
        if self.is_kw(tok, "digraph"):
            self.m.directed = True
        elif self.is_kw(tok, "graph"):
            self.m.directed = False
        else:
            raise DotSyntaxError(tok.line, f"expected 'graph' or 'digraph', got '{tok.val or tok.kind}'")
        self.next()
        if self.peek().kind != "{":
            self.parse_id()
        self.expect("{", "'{'")
        self.parse_stmt_list(scope="root", in_cluster=False)
        self.expect("}", "'}'")

    def parse_stmt_list(self, scope, in_cluster, sub_attrs=None):
        while self.peek().kind not in ("}", "EOF"):
            self.parse_stmt(scope, in_cluster, sub_attrs)
            if self.peek().kind == ";":
                self.next()

    def parse_attr_list(self):
        attrs = {}
        while self.peek().kind == "[":
            self.next()
            while self.peek().kind != "]":
                k = self.parse_id()
                if self.peek().kind != "=":
                    raise DotSyntaxError(k[2], f"attribute '{k[1]}' missing '=value'")
                self.next()
                v = self.parse_id()
                attrs[k[1]] = v
                if self.peek().kind in (",", ";"):
                    self.next()
                if self.peek().kind == "EOF":
                    raise DotSyntaxError(k[2], "unterminated attribute list")
            self.next()
        return attrs

    def record_labels(self, attrs):
        for key in ("label", "xlabel", "headlabel", "taillabel"):
            if key in attrs:
                kind, val, line = attrs[key]
                if kind == "HTML":
                    self.m.html_labels.append((val, line))
                elif kind == "QSTR":
                    self.m.quoted_labels.append((val, line))

    def parse_node_id(self):
        nid = self.parse_id()
        if nid[0] == "QSTR" and " " in nid[1]:
            self.m.node_lines.setdefault(("spaceid", nid[1]), nid[2])
        if self.peek().kind == ":":
            self.next()
            self.parse_id()
            if self.peek().kind == ":":
                self.next()
                self.parse_id()
        return nid

    def parse_endpoint(self, scope, in_cluster):
        """node_id or subgraph; returns list of node ids."""
        tok = self.peek()
        if tok.kind == "{" or self.is_kw(tok, "subgraph"):
            return self.parse_subgraph(scope, in_cluster)
        return [self.parse_node_id()]

    def parse_subgraph(self, scope, in_cluster):
        name, line = None, self.peek().line
        if self.is_kw(self.peek(), "subgraph"):
            self.next()
            if self.peek().kind != "{":
                name = self.parse_id()[1]
        self.expect("{", "'{' after subgraph")
        is_cluster = bool(name and name.lower().startswith("cluster"))
        sub_attrs = {}
        before = set(self.m.nodes) | {e[0] for e in self.m.edges} | {e[1] for e in self.m.edges}
        start_edges = len(self.m.edges)
        self.parse_stmt_list(scope=name or "anon", in_cluster=in_cluster or is_cluster, sub_attrs=sub_attrs)
        self.expect("}", "'}' closing subgraph")
        self.m.subgraphs.append((name, sub_attrs, line, in_cluster))
        if sub_attrs.get("rank", ("", "", 0))[1] == "same" and in_cluster and not is_cluster:
            self.m.rank_same_in_cluster.append(line)
        members = [(k, k, line) for k in self.m.nodes if k not in before]
        for e in self.m.edges[start_edges:]:
            for x in (e[0], e[1]):
                if x not in [mm[1] for mm in members]:
                    members.append(("ID", x, line))
        return [("ID", m[1], line) for m in members] or [("ID", f"__sub_{line}", line)]

    def parse_stmt(self, scope, in_cluster, sub_attrs):
        tok = self.peek()
        # attr_stmt
        for kw in ("graph", "node", "edge"):
            if self.is_kw(tok, kw) and self.peek(1).kind == "[":
                self.next()
                attrs = self.parse_attr_list()
                if kw == "graph":
                    self.apply_graph_attrs(scope, attrs, sub_attrs)
                elif kw == "node" and "fontname" in attrs:
                    self.m.node_defaults_font = True
                elif kw == "edge" and "fontname" in attrs:
                    self.m.edge_defaults_font = True
                return
        # ID = ID
        if tok.kind in ("ID", "QSTR") and self.peek(1).kind == "=":
            k = self.parse_id()
            self.next()
            v = self.parse_id()
            self.apply_graph_attrs(scope, {k[1]: v}, sub_attrs)
            return
        # node or edge stmt
        left = self.parse_endpoint(scope, in_cluster)
        if self.peek().kind == "EDGEOP":
            chain = [left]
            ops = []
            while self.peek().kind == "EDGEOP":
                op = self.next()
                ops.append(op)
                chain.append(self.parse_endpoint(scope, in_cluster))
            attrs = self.parse_attr_list()
            self.record_labels(attrs)
            for op in ops:
                if self.m.directed and op.val == "--":
                    raise DotSyntaxError(op.line, "'--' used in a digraph (use '->')")
                if self.m.directed is False and op.val == "->":
                    raise DotSyntaxError(op.line, "'->' used in an undirected graph (use '--' or 'digraph')")
            for a, b in zip(chain, chain[1:]):
                for x in a:
                    for y in b:
                        self.m.edges.append((x[1], y[1], attrs, ops[0].line))
            return
        # node stmt
        if len(left) == 1 and left[0][1].startswith("__sub_"):
            return
        attrs = self.parse_attr_list()
        self.record_labels(attrs)
        for nid in left:
            if not nid[1].startswith("__sub_"):
                self.m.nodes.setdefault(nid[1], {}).update(attrs)
                self.m.node_lines.setdefault(nid[1], nid[2])

    def apply_graph_attrs(self, scope, attrs, sub_attrs):
        self.record_labels(attrs)
        if scope == "root":
            self.m.graph_attrs.update(attrs)
        elif sub_attrs is not None:
            sub_attrs.update(attrs)


# ------------------------------------------------------------------ checks
def check_html(html_text):
    def repl(m):
        name = m.group(1)
        if name in ("amp", "lt", "gt", "quot", "apos"):
            return m.group(0)
        if name in html.entities.name2codepoint:
            return chr(html.entities.name2codepoint[name])
        return m.group(0)
    xml = re.sub(r"&([A-Za-z][A-Za-z0-9]*);", repl, html_text)
    try:
        ET.fromstring(f"<root>{xml}</root>")
    except ET.ParseError as e:
        return str(e)
    return None


def val(attrs, key, default=None):
    v = attrs.get(key)
    return v[1] if v else default


def lint_model(m, add, max_nodes, layout_hint):
    ga = m.graph_attrs
    layout = (layout_hint or val(ga, "layout", "dot")).lower()
    clusters = {s[0] for s in m.subgraphs if s[0] and s[0].lower().startswith("cluster")}

    for html_text, line in m.html_labels:
        err = check_html(html_text)
        if err:
            add(line, "ERROR", f"HTML label is not well-formed XML ({err}); escape & < > and close all tags")
    for text, line in m.quoted_labels:
        if re.search(r"</?(b|i|u|table|tr|td|font|br)\b", text, re.I):
            add(line, "WARN", "quoted label contains HTML tags; use label=< ... > for HTML-like labels")

    uses_compound = False
    for tail, head, attrs, line in m.edges:
        for k in ("lhead", "ltail"):
            if k in attrs:
                uses_compound = True
                if attrs[k][1] not in clusters:
                    add(line, "ERROR", f"{k}={attrs[k][1]} does not name a cluster subgraph")
        if val(ga, "splines") == "ortho" and "label" in attrs:
            add(line, "WARN", "edge `label` with splines=ortho is placed poorly; use xlabel")
    if uses_compound and val(ga, "compound", "false").lower() != "true":
        add(1, "ERROR", "lhead/ltail used but graph lacks compound=true")

    for name, attrs, line, _ in m.subgraphs:
        if name and not name.lower().startswith("cluster") and ("label" in attrs or "style" in attrs):
            add(line, "WARN", f"subgraph '{name}' has label/style but no 'cluster' prefix: it will not be drawn")
        if name and name.lower().startswith("cluster") and "label" not in attrs:
            add(line, "WARN", f"cluster '{name}' has no label")
        if name and name.lower().startswith("cluster") and layout not in ("dot", "fdp", "osage", "patchwork"):
            add(line, "INFO", f"layout '{layout}' ignores clusters")
    if m.rank_same_in_cluster and val(ga, "newrank", "false").lower() != "true":
        for line in m.rank_same_in_cluster:
            add(line, "WARN", "rank=same inside a cluster needs newrank=true on the root graph")

    if "fontname" not in ga and not m.node_defaults_font:
        add(1, "WARN", "no fontname set (defaults to Times); ignore if set globally via graphviz_dot_args/-G/-N/-E")
    for nid, attrs in m.nodes.items():
        shape = val(attrs, "shape", "")
        if shape in ("record", "Mrecord"):
            add(m.node_lines.get(nid, 1), "INFO", f"node '{nid}' uses {shape}; prefer shape=plain + HTML table")
        if layout == "dot" and ("pos" in attrs or "pin" in attrs):
            add(m.node_lines.get(nid, 1), "WARN", f"node '{nid}': pos/pin are ignored by dot")
    for key, line in m.node_lines.items():
        if isinstance(key, tuple):
            add(line, "WARN", f"node ID \"{key[1]}\" looks like a label; use a short snake_case ID + label=")

    all_nodes = set(m.nodes) | {e[0] for e in m.edges} | {e[1] for e in m.edges}
    all_nodes = {x for x in all_nodes if not x.startswith("__sub_")}
    if len(all_nodes) > max_nodes or len(m.edges) > int(max_nodes * 1.5):
        add(1, "WARN", f"large diagram ({len(all_nodes)} nodes, {len(m.edges)} edges): split, collapse, or filter "
                       f"(budget ~{max_nodes})")
    implicit = sorted(x for x in all_nodes if x not in m.nodes)
    labelled = sum(1 for a in m.nodes.values() if "label" in a)
    if implicit and labelled and len(implicit) <= 8:
        add(1, "INFO", f"nodes used in edges but never declared: {', '.join(implicit)}")


def render(text, layout, add):
    exe = shutil.which("dot")
    if not exe:
        return False
    r = subprocess.run([exe, f"-K{layout}", "-Tsvg", "-o", "/dev/null" if sys.platform != "win32" else "NUL"],
                       input=text, capture_output=True, text=True, timeout=120)
    for ln in r.stderr.splitlines():
        m = re.search(r"line (\d+)", ln)
        lvl = "ERROR" if (r.returncode != 0 or ln.lower().startswith("error")) else "WARN"
        add(int(m.group(1)) if m else 1, lvl, f"dot: {ln.strip()}")
    return True


# -------------------------------------------------------------- extraction
def extract(path: Path):
    """Yield dict(text, line_offset, layout, src_label, meta_findings)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".dot", ".gv"):
        yield dict(text=text, offset=0, layout=None, meta=[])
        return
    lines = text.splitlines()
    if path.suffix == ".rst":
        i = 0
        while i < len(lines):
            m = re.match(r"^(\s*)\.\.\s+(graphviz|digraph|graph)::\s*(\S*)", lines[i])
            if not m:
                i += 1
                continue
            indent, kind, arg = len(m.group(1)), m.group(2), m.group(3)
            start, i = i, i + 1
            opts, body, body_start = {}, [], None
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
                s = lines[i].strip()
                om = re.match(r"^:([\w-]+):\s*(.*)$", s)
                if om and body_start is None:
                    opts[om.group(1)] = om.group(2)
                elif s or body_start is not None:
                    if body_start is None:
                        body_start = i
                    body.append(lines[i])
                i += 1
            meta = []
            if "caption" not in opts:
                meta.append((start + 1, "WARN", "graphviz directive without :caption:"))
            if "alt" not in opts:
                meta.append((start + 1, "WARN", "graphviz directive without :alt: (alt text defaults to DOT source)"))
            layout = opts.get("layout")
            if kind == "graphviz" and arg:
                ext = (path.parent / arg) if not arg.startswith("/") else None
                if ext and ext.exists():
                    yield dict(text=ext.read_text(encoding="utf-8"), offset=0, layout=layout, meta=meta,
                               src=str(ext))
                else:
                    meta.append((start + 1, "ERROR" if ext else "INFO",
                                 f"external file '{arg}' " + ("not found" if ext else "is source-dir relative; not checked")))
                    yield dict(text=None, offset=0, layout=layout, meta=meta)
                continue
            content = "\n".join(l[indent:] if len(l) > indent else l.strip() for l in body)
            content = re.sub(r"(?m)^\s{1,8}", lambda mm: mm.group(0), content)
            if kind in ("digraph", "graph"):
                content = f"{kind} {arg or 'G'} {{\n{content}\n}}"
                off = (body_start or start) - 1
            else:
                off = body_start or start
            yield dict(text=content, offset=off, layout=layout, meta=meta)
        return
    if path.suffix in (".md", ".markdown"):
        i = 0
        while i < len(lines):
            m = re.match(r"^\s*(`{3,}|~{3,})\s*(\{graphviz\}|dot|graphviz|gv)(?=\s|$)\s*(\S*)", lines[i])
            if not m:
                other = re.match(r"^\s*(`{3,}|~{3,})", lines[i])
                i += 1
                if other:  # skip unrelated fenced blocks (they may contain example fences)
                    f = other.group(1)
                    while i < len(lines) and not re.match(rf"^\s*{re.escape(f[0])}{{{len(f)},}}\s*$", lines[i]):
                        i += 1
                    i += 1
                continue
            fence, myst, arg = m.group(1), m.group(2) == "{graphviz}", m.group(3)
            start, i = i, i + 1
            body, opts = [], {}
            while i < len(lines) and not lines[i].strip().startswith(fence):
                om = re.match(r"^:([\w-]+):\s*(.*)$", lines[i].strip())
                if myst and om and not body:
                    opts[om.group(1)] = om.group(2)
                else:
                    body.append(lines[i])
                i += 1
            i += 1
            meta = []
            if myst and "caption" not in opts:
                meta.append((start + 1, "WARN", "{graphviz} directive without :caption:"))
            if myst and arg:
                ext = path.parent / arg
                if ext.exists():
                    yield dict(text=ext.read_text(encoding="utf-8"), offset=0, layout=opts.get("layout"),
                               meta=meta, src=str(ext))
                else:
                    meta.append((start + 1, "ERROR", f"external file '{arg}' not found"))
                    yield dict(text=None, offset=0, layout=None, meta=meta)
                continue
            yield dict(text="\n".join(body), offset=start + 1 + len(opts), layout=opts.get("layout"), meta=meta)
        return
    raise ValueError(f"unsupported file type: {path.suffix}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--render", action="store_true", help="also run `dot -Tsvg` if Graphviz is installed")
    ap.add_argument("--max-nodes", type=int, default=20)
    args = ap.parse_args()

    findings, count, rendered = [], 0, False
    for f in args.files:
        if not f.exists():
            findings.append(Finding(f, 0, "ERROR", "file not found"))
            continue
        try:
            items = list(extract(f))
        except ValueError as e:
            findings.append(Finding(f, 0, "ERROR", str(e)))
            continue
        for item in items:
            src = item.get("src", str(f))
            off = item["offset"]
            for line, lvl, msg in item["meta"]:
                findings.append(Finding(f, line, lvl, msg))
            if item["text"] is None:
                continue
            count += 1
            add = lambda line, lvl, msg, _s=src, _o=off: findings.append(Finding(_s, line + _o, lvl, msg))
            text = item["text"]
            if not re.match(r"\s*(?:(?://|#)[^\n]*\n\s*|/\*.*?\*/\s*)*(?:strict\s+)?(?:di)?graph\b[^\[;=]*\{",
                            text, re.S | re.I):
                # Fragment (statements only): wrap so it can still be validated.
                kind = "graph" if ("--" in re.sub(r'"[^"]*"', "", text) and "->" not in text) else "digraph"
                text = f"{kind} _fragment {{\n{text}\n}}"
                off -= 1
                add = lambda line, lvl, msg, _s=src, _o=off: findings.append(Finding(_s, line + _o, lvl, msg))
                add(1, "INFO", "fragment (no graph header): validated inside a wrapper graph")
                item = dict(item, fragment=True)
            try:
                model = Parser(tokenize(text)).parse_file()
                if item.get("fragment"):
                    model.graph_attrs.setdefault("fontname", ("ID", "fragment", 0))
                lint_model(model, add, args.max_nodes, item["layout"])
            except DotSyntaxError as e:
                add(e.line, "ERROR", f"syntax: {e.msg}")
                continue
            if args.render:
                rendered = render(text, item["layout"] or "dot", add) or rendered
    if args.render and not rendered:
        print("INFO: Graphviz `dot` not found; static checks only", file=sys.stderr)
    for x in findings:
        print(x)
    errs = sum(x.level == "ERROR" for x in findings)
    warns = sum(x.level == "WARN" for x in findings)
    print(f"checked {count} graph(s): {errs} error(s), {warns} warning(s)")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
