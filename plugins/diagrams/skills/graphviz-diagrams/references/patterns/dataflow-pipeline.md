# Pattern: data flow / pipeline / CI flow

Answers: how data or work moves through stages, what each stage produces, and where it branches, merges, or stores.

## Template

```dot
// Purpose: code generation pipeline from YAML descriptors to build artefacts.
digraph codegen_pipeline {
    graph [rankdir=LR, newrank=true, fontname="Helvetica,Arial,sans-serif", nodesep=0.3];
    node  [fontname="Helvetica,Arial,sans-serif", fontsize=10];
    edge  [fontname="Helvetica,Arial,sans-serif", fontsize=9];

    // Artefacts (data) vs processes (transformations)
    node [shape=note];
    yaml     [label="app.yaml"];
    manifest [label="package\nmanifests"];
    ir       [label="resolved model\n(JSON)"];
    sources  [label="generated\nC sources"];

    node [shape=box, style=rounded];
    parse    [label="Parse &\nvalidate"];
    resolve  [label="Resolve\nproviders"];
    render   [label="Render\ntemplates"];

    schema   [label="Schemas", shape=cylinder];

    // Main path: weighted and grouped to stay straight
    yaml    -> parse   [weight=10, group=main];
    parse   -> resolve [weight=10];
    resolve -> ir      [weight=10];
    ir      -> render  [weight=10];
    render  -> sources [weight=10];
    // Side inputs
    manifest -> resolve;
    schema   -> parse  [style=dashed, label="validates"];
}
```

## Rules

- `rankdir=LR`, so the flow reads like text. Use `TB` only for long, narrow pipelines.
- **Separate artefacts from processes:** artefacts (files, messages) are `note`/`cylinder`, and processes are rounded boxes. Alternating artefact and process makes the diagram self-explanatory. For pure CI job flows, process nodes alone are fine.
- Keep the main path straight with `weight` on its edges, and declare it first. Side inputs come after.
- Loops (retry, feedback): `constraint=false`, or `dir=back` on a reversed edge, so they don't fold the layout.
- Parallel stages: put them in `{ rank=same; a; b; }`, with explicit fan-out and fan-in nodes (`shape=point` works as a join bar).
- CI-specific: one cluster per stage (build/test/deploy), jobs as nodes, and dashed edges for `needs`/artefact handoff vs solid edges for sequence.

## Data flow diagram (DFD) notation

If the doc uses DFD vocabulary: external entities as `box`, processes as `ellipse` or `Mrecord`, data stores as `cylinder`, flows labelled with the data name. Don't connect two stores or two external entities directly.
