# Style conventions (house style)

Contents: Principles · Default preamble · Semantic encoding table · Colour · Legends · Shared style across files

## Principles

- Every visual variable (shape, line style, arrowhead, colour, peripheries) encodes **one** meaning, applied the same way across the whole documentation set.
- The diagram must still work in greyscale and on dark backgrounds. Encode with shape and line style first, and colour second.
- Before adding a new style, check the repo's existing diagrams (`grep -r "node \[" docs/`) and reuse their conventions.

## Default preamble

Copy this unless the repo already has its own:

```dot
digraph name {
    graph [fontname="Helvetica,Arial,sans-serif", fontsize=12, newrank=true,
           nodesep=0.4, ranksep=0.5, bgcolor="transparent"];
    node  [fontname="Helvetica,Arial,sans-serif", fontsize=11,
           shape=box, style="rounded", color="gray30", penwidth=1.2];
    edge  [fontname="Helvetica,Arial,sans-serif", fontsize=9,
           color="gray30", arrowsize=0.7];
    // ...
}
```

`bgcolor="transparent"` lets SVG output blend with light and dark doc themes. Mid-grey strokes stay visible on both.

## Semantic encoding table

These are the recommended defaults. Document any deviation in the legend.

| Meaning | Encoding |
|---|---|
| Component / module / service (owned) | `shape=box, style=rounded` |
| External system / third party | `shape=box, style="rounded,dashed"` |
| Data store / DB / file storage | `shape=cylinder` |
| Queue / topic / bus | `shape=box, style="rounded", peripheries=2` or `shape=cds` |
| Document / config file / artefact | `shape=note` (file), `shape=folder` (directory), `shape=component` (library/package) |
| Person / role | `shape=box, style=rounded` with "(role)" in the label. Graphviz has no actor shape |
| Decision | `shape=diamond` (keep labels short) |
| Start / end (flows, states) | `shape=circle, style=filled, fillcolor=black, width=0.15, label=""` / `shape=doublecircle` |
| Interface / abstract | Italic name in an HTML label, or `style="rounded,dashed"` |
| Synchronous call / hard dependency | Solid edge, `arrowhead=normal` |
| Async message / event / optional dependency | `style=dashed` |
| Data flow (payload moves) | Solid, `penwidth=2` for the main path only |
| Build-time vs runtime dependency | Build: `style=dotted`. Runtime: solid |
| Inheritance / realisation (UML) | `arrowhead=empty` solid / dashed |
| Composition / aggregation (UML) | `dir=back, arrowtail=diamond` / `odiamond` on the whole-to-part edge |
| Highlight ("new in this change") | `penwidth=2.5` plus a "(new)" label suffix, not colour alone |

## Colour

- Use colour **only** for a categorical meaning (layer, ownership, status), with at most 3–4 categories, each named in the legend.
- Use light fills with a dark stroke: `style="rounded,filled", fillcolor="#dbeafe", color="#1e3a8a"`. The text stays black, which is readable on any page background because the fill is behind it.
- Prefer colour-blind-safe palettes. Graphviz's built-in Brewer schemes work: `colorscheme=set28` or `pastel28`, then `fillcolor=1..8`.
- Never encode meaning by red/green alone.

## Legends

Add a legend when you use 2 or more encodings. Put it in its own cluster at the bottom or side so it isn't connected to the main graph. It needs `newrank=true`, which is part of the default preamble:

```dot
subgraph cluster_legend {
    label="Legend"; fontsize=10; style="rounded,dashed"; color="gray60";
    node [fontsize=9, width=0.3, height=0.2];
    lg_int [label="Owned component"];
    lg_ext [label="External system", style="rounded,dashed"];
    lg_db  [label="Data store", shape=cylinder];
    lg_a [shape=point, width=0.01]; lg_b [shape=point, width=0.01];
    lg_a -> lg_b [style=dashed, xlabel="async"];
    { rank=same; lg_int; lg_ext; lg_db; }
}
```

Alternatively, describe the encodings in one sentence of prose below the diagram. That's often enough, and you don't need to maintain a legend.

## Shared style across files

- Sphinx: put global defaults in `graphviz_dot_args = ["-Gfontname=...", "-Nfontname=...", "-Efontname=..."]` in `conf.py` (see `embedding.md`). Then each diagram only carries what's specific to it.
- Command-line rendering: pass the same `-G/-N/-E` flags in the Makefile/CMake target.
- Don't duplicate long preambles in dozens of inline diagrams. Centralise the defaults.
