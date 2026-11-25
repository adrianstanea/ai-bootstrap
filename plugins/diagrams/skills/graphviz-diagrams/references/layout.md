# Layout control

Contents: Engines · dot attributes cheat sheet · Fixing common layout problems · Edge routing · Size and spacing · Non-dot engines

## Engines

| Engine | Layout | Use for | Clusters |
|---|---|---|---|
| `dot` | Hierarchical / layered | Anything with direction: dependencies, flows, states, trees, UML. **The default choice** | Yes |
| `neato` | Spring model (stress majorisation) | Small undirected networks (≤ ~100 nodes) | No |
| `fdp` | Force-directed | Undirected networks that need grouping | Yes |
| `sfdp` | Scalable force-directed | Large graphs (hundreds+), overview only | No |
| `circo` | Circular | Rings, cyclic structures, bus/ring topologies | No |
| `twopi` | Radial | One central node with layers around it (`root=` sets the centre) | No |
| `osage` | Packed clusters | Showing group membership, not connections | Yes |
| `patchwork` | Squarified treemap | Sizes of nested groups (`area` attribute) | Yes |

Select the engine with `layout=neato` in the graph, the Sphinx `:layout:` option, or `dot -K neato` / `neato` on the command line.

## dot attributes cheat sheet

| Attribute | On | Effect |
|---|---|---|
| `rankdir=TB\|LR\|BT\|RL` | graph | Main flow direction |
| `newrank=true` | graph | Global ranking: `rank=same` works across clusters. Set it by default when using clusters |
| `rank=same\|min\|max\|source\|sink` | subgraph | Put the subgraph's nodes on one rank / the top / the bottom |
| `ordering=out` | graph/node | Keep out-edges in declaration order (left-to-right) |
| `group=name` | node | Same group: straighter, aligned edges between those nodes (a "spine") |
| `weight=N` | edge | Higher is shorter and straighter. Use for the main path (integer, ≥ 0) |
| `constraint=false` | edge | Edge doesn't affect ranking (back-edges, cross-references) |
| `minlen=N` | edge | Minimum rank distance (spread out sections) |
| `compound=true` + `lhead`/`ltail` | graph / edge | Clip edges at cluster borders |
| `concentrate=true` | graph | Merge parallel edge segments (dense dependency graphs) |
| `clusterrank=local` | graph | Default. `none` disables cluster drawing |

## Fixing common layout problems

| Symptom | Fix (in this order) |
|---|---|
| Main path zig-zags | Declare main-path nodes/edges first. Add `weight=10` on main edges and `group=main` on main nodes |
| Peers on different levels | `{ rank=same; a; b; c; }`. Add `newrank=true` if they're in different clusters |
| Back-edge (retry, feedback) distorts ranks | `constraint=false` on the back-edge, or reverse it: `b -> a [dir=back]` |
| Siblings in the wrong order | Reorder declarations. Use `ordering=out` on the parent |
| Labels collide with edges | Use `xlabel` instead of `label`, or increase `nodesep`/`ranksep`. Shorten labels |
| Too wide | Switch `rankdir`, use `concentrate=true`, split the diagram, or use `ratio`/`size` (last resort) |
| Clusters overlap or have odd shapes | Declare each node inside its cluster only. Don't mention cluster nodes in edges before the cluster block |
| Need exact alignment | Invisible edge `a -> b [style=invis]`. Comment why. Use it as a last resort |

## Edge routing

- `splines=spline` (default) curved, `polyline`, `ortho` (right angles), `line`/`false` straight, `curved`.
- `ortho`: looks like architecture drawings, but ignores ports and places edge `label`s poorly. Use `xlabel` or `headlabel`/`taillabel`. Avoid it in dense graphs.
- `headport`/`tailport` (`e`, `s` …) control where edges attach, which helps keep `LR` pipelines tidy.
- `dir=back|both|none` changes arrowhead placement without changing the ranking direction.

## Size and spacing

- `nodesep` (inches between nodes on a rank, default 0.25), `ranksep` (between ranks, default 0.5; `"0.8 equally"` makes ranks even).
- `margin`/`pad` around the drawing. Avoid `size`/`ratio` in docs and let the HTML/CSS scale the SVG.
- `fixedsize=true` + `width`/`height` gives uniform node sizes (state circles, icons).

## Non-dot engines

- `neato`/`fdp`: `overlap=false` (or `overlap=prism`) and `splines=true` to avoid overlaps. Use `len=` per edge for preferred length. Use `sep="+10"` for padding.
- `neato` honours `pos="x,y!"` (pinned). Use it only for physical layouts (boards, racks), and add `notranslate`/`inputscale` as needed.
- `twopi`: `root=node_id`, `ranksep` controls ring distance.
- `circo`: `mindist` controls spacing.
- Layouts from force-directed engines can change between Graphviz versions. Don't rely on exact placement in docs.
