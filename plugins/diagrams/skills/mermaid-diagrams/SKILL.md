---
name: mermaid-diagrams
description: Selects, writes, reviews and fixes Mermaid diagrams (flowchart, sequence, state, class, ER, timeline, packet layout) for Markdown, .rst (.. mermaid::), READMEs and design docs. Use when a diagram is requested, the type is unclear, or Mermaid fails to render. Not for Graphviz/DOT, which is manual-only (graphviz-diagrams).
metadata:
  version: 1.0.0
  mermaid-docs: https://mermaid.js.org/intro/
---

# Mermaid Diagrams

This file is the control plane: it picks the diagram type and holds the rules that apply to every diagram. Syntax lives in `references/`. **Load only the reference for the type you chose.** Don't load all of them.

## Workflow

1. **Name the reader's question.** One diagram answers one question, for example "who calls whom, in what order?" or "what states can a job be in?".
2. **Pick the type** with the [selection table](#selection-table). If two types fit, use the [tie-breakers](#tie-breakers). If the request is vague, go to [suggestion mode](#suggestion-mode).
3. **Load the reference** for that type (and `references/styling.md` only if styling or theming is really needed).
4. **Write the diagram** following the [universal rules](#universal-rules) and the reference's checklist.
5. **Validate** with `python scripts/check_mermaid.py <file.md|file.mmd>` (static lint; add `--render` to parse with mermaid-cli when available). Fix every `ERROR` and review each `WARN`.

## Selection table

| Reader's question                                                                | Diagram                  | Header keyword                | Reference                    | Portability  |
| -------------------------------------------------------------------------------- | ------------------------ | ----------------------------- | ---------------------------- | ------------ |
| How does the process / algorithm / decision logic go?                            | Flowchart                | `flowchart`                   | `references/flowchart.md`    | Stable       |
| Which components exist and how do they connect (no strict layout)?               | Flowchart with subgraphs | `flowchart`                   | `references/flowchart.md`    | Stable       |
| Who talks to whom, in what order (API calls, protocols, handshakes)?             | Sequence                 | `sequenceDiagram`             | `references/sequence.md`     | Stable       |
| What types/modules exist, and how do they relate (inherit, own, depend)?         | Class                    | `classDiagram`                | `references/class.md`        | Stable       |
| Which states can X be in, and what triggers each transition?                     | State                    | `stateDiagram-v2`             | `references/state.md`        | Stable       |
| What is the data/persistence schema and its cardinalities?                       | Entity-relationship      | `erDiagram`                   | `references/er.md`           | Stable       |
| What is the system context / container / component view (C4 model)?              | C4                       | `C4Context`, `C4Container`, … | `references/c4.md`           | Experimental |
| What cloud/infra services are deployed and wired together?                       | Architecture             | `architecture-beta`           | `references/architecture.md` | Beta, v11.1+ |
| Hardware/system block layout where position matters (pipelines, stacks, layers)? | Block                    | `block-beta`                  | `references/block.md`        | Beta         |
| How do branches, merges, and releases flow?                                      | Git graph                | `gitGraph`                    | `references/gitgraph.md`     | Stable       |
| What happens when, with durations and dependencies (plan, schedule)?             | Gantt                    | `gantt`                       | `references/gantt.md`        | Stable       |
| What happened / will happen in which period (history, roadmap)?                  | Timeline                 | `timeline`                    | `references/timeline.md`     | Stable       |
| How does a topic break down hierarchically (brainstorm, feature tree)?           | Mindmap                  | `mindmap`                     | `references/mindmap.md`      | Stable       |
| What is the bit/byte layout of a frame, header, or register?                     | Packet                   | `packet-beta`                 | `references/packet.md`       | Beta, v11.0+ |
| Which requirements exist, and what satisfies/verifies them?                      | Requirement              | `requirementDiagram`          | `references/requirement.md`  | Stable       |
| What is the user's experience, step by step, with satisfaction?                  | User journey             | `journey`                     | `references/journey.md`      | Stable       |
| What is the work-item status board?                                              | Kanban                   | `kanban`                      | `references/kanban.md`       | Newer        |
| How does a numeric value change across categories or over time?                  | XY chart (bar/line)      | `xychart-beta`                | `references/xychart.md`      | Beta         |
| What share of a whole does each part take (≤ 6 slices)?                          | Pie                      | `pie`                         | `references/pie.md`          | Stable       |
| Where do items fall on two axes (prioritisation, effort/impact)?                 | Quadrant                 | `quadrantChart`               | `references/quadrant.md`     | Newer        |
| How does a quantity flow and split between stages (budget, energy, traffic)?     | Sankey                   | `sankey-beta`                 | `references/sankey.md`       | Beta         |

**Portability:** *Stable* types render on virtually every host. For *Beta/Newer/Experimental* types, confirm the target renderer supports them (see [Rendering targets](#rendering-targets)) or fall back as shown in each reference.

## Tie-breakers

- **Flowchart vs sequence:** if time order between ≥ 2 actors matters (request/response, async callbacks), use sequence. If it's one actor's logic with branches, use flowchart.
- **Flowchart vs state:** if nodes are *conditions the system rests in* and edges are *events*, use state. If nodes are *actions*, use flowchart.
- **Class vs ER:** use class for code structure (methods, interfaces, visibility). Use ER for persisted data and cardinality.
- **C4 vs architecture vs flowchart:** use C4 when the doc follows the C4 model (levels, people, system boundaries). Use architecture for cloud/infra topology with icons. Otherwise, use a flowchart with subgraphs: it's the most portable and the easiest to maintain.
- **Block vs flowchart:** use block only when author-controlled placement matters (layer stacks, signal chains, memory maps). Otherwise use flowchart and let auto-layout handle placement.
- **Gantt vs timeline:** use Gantt when durations and dependencies matter. Use timeline for milestones and periods only.
- **XY vs pie:** prefer bar charts. Use pie only for a few parts of one whole.
- **Many concerns in one picture:** split it. Use one context diagram, then one diagram per detail (one sequence per scenario, one state machine per entity).

## Don't draw a diagram when

- The content is a linear list of ≤ 5 steps: use a numbered list.
- The content is a lookup or comparison: use a table.
- A diagram would have < 3 nodes or no relationships.
- The data changes often and nobody owns updating the diagram.

## Suggestion mode

Use this when the user is unsure, the request is vague ("diagram this module"), or the source material supports several views. Reply with **at most 3 options**, ranked, in this format, and then ask which one to draw (or draw option 1 if the user wants you to proceed):

```
1. <Diagram type> — answers "<reader question>". Shows: <what>. Best if: <condition>.
2. ...
Recommendation: <option> because <one-line reason tied to the user's goal>.
```

Derive the options from the source material's signals:

| Signal in the material                                              | Likely views                             |
| ------------------------------------------------------------------- | ---------------------------------------- |
| Handlers, endpoints, message passing, callbacks                     | sequence                                 |
| Enums like `status`, `phase`, `mode`; `switch` on state             | state                                    |
| Classes, interfaces, inheritance, DI wiring                         | class                                    |
| Tables, schemas, ORM models, foreign keys                           | ER                                       |
| Services, queues, deployments, Docker Compose, Kubernetes manifests | flowchart+subgraphs, C4, or architecture |
| `if`/`else` chains, pipelines, CI jobs                              | flowchart                                |
| Branching/release policy                                            | gitGraph                                 |
| Milestones, dates, roadmaps                                         | timeline or Gantt                        |
| Struct/bit-field/register definitions                               | packet                                   |

## Universal rules

Apply these to every diagram, whatever the type.

**Content and scope**

- One diagram, one question. Add a title (front matter `title:` or a heading right above the code block) and one sentence of prose before the diagram that says what to look for.
- Budget about **15 nodes / 20 edges** (flowchart, class, ER, state). Past that, split it into an overview plus detail diagrams, or group with subgraphs/namespaces.
- Use the reader's vocabulary: label with domain names from the code or docs, not invented abbreviations.
- Label edges whenever the relationship isn't obvious (`-->|validates|`, `: places`, `: submit()`).

**Identifiers and labels**

- Keep short, stable, ASCII **IDs** separate from human **labels**: `authSvc["Auth service"]`. IDs never show to readers and keep diffs small.
- Quote labels that contain spaces plus punctuation, brackets, `:`, `;`, `#`, `|`, or non-ASCII: `A["Parse (v2) config"]`.
- Never use lowercase `end` as an ID or bare label (it breaks flowcharts, sequence, and state). Write `End`, `END`, or `done`.
- In flowcharts, a node ID that starts with `o` or `x` right after a link (`A---oB`) becomes a circle/cross edge. Add a space or capitalise.
- Use `<br>` for line breaks in labels. Avoid other HTML.

**Layout**

- Pick the direction from the content: `LR` for pipelines and request paths, `TB`/`TD` for hierarchies and decision trees. Keep the direction consistent across related diagrams in one doc.
- Declare nodes in reading order. Mermaid lays out roughly in declaration order.
- Don't fight the auto-layout with invisible links or spacer nodes. If placement matters, switch to `block-beta`.

**Styling (minimal by default)**

- Use no colours or themes by default. GitHub renders in light *and* dark mode, and hard-coded fills often become unreadable.
- If emphasis carries meaning (for example, "new in this PR" or "external"), use one or two `classDef` classes and explain them in a legend or the text. See `references/styling.md`.
- Don't use `click`, callbacks, tooltips, or links in diagrams meant for GitHub. They are disabled or sanitised there.

**Accessibility and maintainability**

- Add `accTitle:` and `accDescr:` to diagram types that support them (most do). Screen readers get no other description.
- Comment with `%%` on its own line to explain non-obvious modelling choices.
- Keep diagrams as text in the Markdown file, never as exported images only. Put large shared diagrams in a `.mmd` file only if your toolchain embeds them.

## Rendering targets

- **GitHub/GitLab Markdown:** use a fenced block with the `mermaid` language. GitHub pins a specific Mermaid version. To check it, render a block that contains only `info`. Assume newer syntax (anything marked `v11.x+` in a reference) might not render until you've verified it.
- **Mermaid v12 changes the defaults** for several types (`neo` look, `redux-color` theme, ELK layout). Never rely on the default look for meaning. If you need the classic look on v12, set `look: classic` / `theme: default` in front matter.
- **Beta keywords:** newer Mermaid also accepts names without `-beta` (`xychart`, `block`, `packet`), but older renderers accept only the `-beta` form. Use the `-beta` form for portability unless the target is confirmed to be v12+.
- **Fallback:** if the target can't render the chosen beta/experimental type, use the fallback listed in that type's reference (usually a flowchart).

## Reviewing or fixing an existing diagram

1. Run `scripts/check_mermaid.py` on the file.
2. Load the reference only for the diagram types you find in the file.
3. Report problems in this order: wrong diagram type for the question, then rendering errors, then rule violations, then style issues. Propose a corrected block, not just comments.
