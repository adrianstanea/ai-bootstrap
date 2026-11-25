# Pattern: architecture / component view

Answers: which components exist, how they are grouped (layers, processes, deployables), and how they talk to each other.

## Template

```dot
// Purpose: runtime components of the framework and how they communicate.
// Source of truth: src/ module layout; update when modules are added/removed.
digraph architecture {
    graph [rankdir=TB, newrank=true, compound=true,
           fontname="Helvetica,Arial,sans-serif", nodesep=0.4, ranksep=0.6];
    node  [shape=box, style="rounded", fontname="Helvetica,Arial,sans-serif", fontsize=11];
    edge  [fontname="Helvetica,Arial,sans-serif", fontsize=9];

    subgraph cluster_app {
        label="Application"; style="rounded"; color="gray50";
        app_main [label="App entry\n(generated)"];
        app_cfg  [label="app.yaml", shape=note];
    }

    subgraph cluster_runtime {
        label="Framework runtime"; style="rounded"; color="gray50";
        scheduler [label="Scheduler"];
        registry  [label="Component registry"];
        bus       [label="Message bus", peripheries=2];
    }

    subgraph cluster_platform {
        label="Platform layer"; style="rounded"; color="gray50";
        hal   [label="HAL", shape=component];
        osal  [label="OSAL", shape=component];
    }

    sensor_fw [label="Sensor firmware", style="rounded,dashed"];   // external

    // Main control path
    app_main  -> scheduler [label="starts"];
    scheduler -> registry  [label="resolves"];
    registry  -> bus;
    // Platform usage
    scheduler -> osal;
    bus       -> hal;
    hal       -> sensor_fw [style=dashed, label="SPI"];
    // Configuration (does not affect ranking)
    app_cfg   -> registry  [style=dotted, constraint=false, label="configures"];
}
```

## Rules

- **One level of abstraction per diagram.** Don't mix deployables with classes. Do an overview first, then one detail diagram per cluster if needed (C4-style zoom).
- **Clusters = a real boundary** (process, binary, layer, repository, network zone). Name the boundary type in the label if ambiguous ("Backend (container)").
- Layered stacks: `rankdir=TB`, with dependencies pointing **down**. Request paths: `rankdir=LR`, with the caller on the left.
- Label edges with **intent or protocol**, not both, unless both are short (`calls (gRPC)`).
- External systems: dashed outline and outside all owned clusters.
- To show "this whole subsystem depends on X", use one edge from a representative node with `ltail=cluster_x` (requires `compound=true`) instead of N edges.

## Common fixes

- Layers not stacked cleanly: put `{ rank=same; ... }` subgraphs inside each layer cluster (with `newrank=true`), or add invisible edges between layers, commented as `// layout`.
- Config/cross-cutting edges pull nodes around: use `constraint=false`.
- Too many edges: collapse them into "uses" edges between clusters, and move details to a per-cluster diagram.
