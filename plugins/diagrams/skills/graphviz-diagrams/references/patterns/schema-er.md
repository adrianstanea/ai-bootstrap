# Pattern: schema / entity-relationship (tables, config schemas, message structs)

Answers: which entities exist, their key fields, and which field references which.

## Template

```dot
// Purpose: package manifest schema and its references.
digraph manifest_schema {
    graph [rankdir=LR, fontname="Helvetica,Arial,sans-serif", nodesep=0.5, ranksep=0.9];
    node  [shape=plain, fontname="Helvetica,Arial,sans-serif", fontsize=10];
    edge  [arrowhead=crow, arrowtail=tee, dir=both, color="gray30"];

    package [label=<
      <table border="0" cellborder="1" cellspacing="0" cellpadding="3">
        <tr><td colspan="2" bgcolor="gray90"><b>package</b></td></tr>
        <tr><td port="name" align="left"><u>name</u></td><td align="left">string</td></tr>
        <tr><td align="left">version</td><td align="left">semver</td></tr>
      </table>>];

    component [label=<
      <table border="0" cellborder="1" cellspacing="0" cellpadding="3">
        <tr><td colspan="2" bgcolor="gray90"><b>component</b></td></tr>
        <tr><td align="left"><u>id</u></td><td align="left">string</td></tr>
        <tr><td port="package" align="left"><i>package</i></td><td align="left">ref</td></tr>
        <tr><td port="provides" align="left">provides</td><td align="left">capability[]</td></tr>
      </table>>];

    capability [label=<
      <table border="0" cellborder="1" cellspacing="0" cellpadding="3">
        <tr><td colspan="2" bgcolor="gray90"><b>capability</b></td></tr>
        <tr><td port="name" align="left"><u>name</u></td><td align="left">string</td></tr>
      </table>>];

    // one package has many components (tee = one, crow = many)
    package:name:e -> component:package:w;
    component:provides:e -> capability:name:w [arrowtail=crow, label="many-to-many"];
}
```

## Rules

- One HTML table per entity: a header row with the name, then one row per **key or relevant** field. Mark primary keys with `<u>` and foreign keys/references with `<i>`, and say so in the caption.
- Connect **field to field via ports** (`a:field:e -> b:field:w`), so readers see which column links.
- Crow's-foot cardinality: `arrowhead`/`arrowtail` with `tee` (one), `crow` (many), `odot` (zero). Combine them, for example `arrowhead=crowodot` for zero-or-many and `teetee` for exactly one. Set `dir=both`.
- `rankdir=LR` with referenced (parent) entities on the left.
- More than about 8 entities: split by bounded context or subsystem.
- If no build step can render Graphviz, a Mermaid `erDiagram` may be the simpler choice.
