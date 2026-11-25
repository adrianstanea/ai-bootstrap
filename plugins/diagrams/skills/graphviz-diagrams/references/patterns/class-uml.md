# Pattern: class / UML-style structure

Answers: which types and interfaces exist, and how they relate (inherit, implement, own, use). For Python classes in Sphinx, prefer the generated `sphinx.ext.inheritance_diagram` over hand-drawn graphs.

## Template

```dot
// Purpose: provider abstraction and its implementations.
digraph providers {
    graph [rankdir=BT, fontname="Helvetica,Arial,sans-serif", nodesep=0.6];
    node  [shape=plain, fontname="Helvetica,Arial,sans-serif", fontsize=10];
    edge  [fontname="Helvetica,Arial,sans-serif", fontsize=9, arrowsize=0.8];

    provider [label=<
      <table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td><i>&laquo;interface&raquo;</i><br/><b>Provider</b></td></tr>
        <tr><td align="left" balign="left">+ resolve(name: str): Package<br/>+ capabilities(): set&lt;str&gt;</td></tr>
      </table>>];

    local_provider [label=<
      <table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td><b>LocalProvider</b></td></tr>
        <tr><td align="left" balign="left">- root: Path</td></tr>
        <tr><td align="left" balign="left">+ resolve(name: str): Package</td></tr>
      </table>>];

    registry [label=<
      <table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td><b>Registry</b></td></tr>
        <tr><td align="left" balign="left">+ add(p: Provider)</td></tr>
      </table>>];

    // Realisation: dashed + hollow triangle, pointing to the interface
    local_provider -> provider [style=dashed, arrowhead=empty];
    // Aggregation: hollow diamond at the whole (Registry)
    registry -> provider [dir=back, arrowtail=odiamond, headlabel="*", taillabel="1"];
}
```

## UML edge mapping

| Relationship | DOT (edge written from child/part to parent/whole unless noted) |
|---|---|
| Inheritance (extends) | `child -> parent [arrowhead=empty]` |
| Realisation (implements) | `impl -> iface [arrowhead=empty, style=dashed]` |
| Association (navigable) | `a -> b [arrowhead=vee]` |
| Dependency (uses) | `a -> b [arrowhead=vee, style=dashed]` |
| Aggregation | `whole -> part [dir=back, arrowtail=odiamond]` |
| Composition | `whole -> part [dir=back, arrowtail=diamond]` |
| Multiplicity | `headlabel` / `taillabel` (`1`, `0..*`) |

`dir=back` keeps the whole above or before the part in the ranking while drawing the diamond at the whole.

## Rules

- `rankdir=BT`, so arrows to base classes point **up**.
- Three sections: name / attributes / operations. Omit empty sections. Show only members relevant to the point being made.
- Visibility markers `+ - # ~`. Italic for abstract and interface names. Stereotypes as `&laquo;interface&raquo;`.
- Escape generics: `set&lt;str&gt;`.
- Keep it to about 10 classes or fewer. Group by module with clusters if needed.
