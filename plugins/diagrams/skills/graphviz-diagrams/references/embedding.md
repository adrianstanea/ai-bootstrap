# Embedding and toolchains

Contents: Sphinx (reST) · Sphinx with MyST Markdown · conf.py settings · Doxygen · Command line / CI · Generated graphs · GitHub

## Sphinx (reST): `sphinx.ext.graphviz`

Requires the `dot` binary on the build machine (CI image included).

```rst
.. graphviz:: diagrams/architecture.dot
   :caption: Framework layers and their dependencies.
   :alt: Layered diagram: application, runtime, drivers, HAL.
   :align: center
   :name: fig-architecture

.. graphviz::
   :caption: Inline example.

   digraph example {
       a -> b;
   }

.. digraph:: build_flow
   :caption: Shorthand: content is wrapped in "digraph build_flow { ... }".

   configure -> build -> test;

.. graph:: links

   a -- b;
```

| Option | Use |
|---|---|
| `:caption:` | Always set it. It makes the diagram a numbered figure |
| `:alt:` | Always set it. Otherwise the alt text is the raw DOT source |
| `:name:` | Label for `:ref:` / `:numref:` cross-references |
| `:align:` | `left` / `center` / `right` |
| `:layout:` | Engine (`neato`, `fdp`, …). Default is `dot` |
| `:class:` | CSS classes on the output (for example, for dark-mode CSS) |

- External file paths are relative to the current document, or to the source directory if they start with `/`. Prefer external `.dot` files for anything over about 15 lines: you get editor support, reuse, and standalone rendering.
- The `.. digraph:: name` / `.. graph:: name` names are passed through unchanged. Quote them if they contain non-alphanumeric characters such as `-`.

## Sphinx with MyST Markdown

````markdown
```{graphviz} diagrams/architecture.dot
:caption: Framework layers and their dependencies.
:alt: Layered diagram of the framework.
```
````

The inline form puts the DOT source in the fence body.

## conf.py settings

```python
extensions = ["sphinx.ext.graphviz"]
graphviz_output_format = "svg"   # default is "png"; SVG scales, is searchable, and supports links/tooltips
graphviz_dot_args = [            # global defaults = house style in one place
    "-Gfontname=Helvetica,Arial,sans-serif",
    "-Nfontname=Helvetica,Arial,sans-serif",
    "-Efontname=Helvetica,Arial,sans-serif",
    "-Gbgcolor=transparent",
]
```

- `graphviz_dot` sets the path to the `dot` executable. Set it on the command line (`-D graphviz_dot=...`), not in `conf.py`, because it's machine-specific.
- With SVG output, node `URL`/`href` and `tooltip` become clickable links and hover text. Use relative links to other doc pages.
- `sphinx.ext.inheritance_diagram` generates Python class hierarchies automatically. Use it instead of hand-drawing Python class trees.

## Doxygen

- `HAVE_DOT = YES` enables dot-based class, collaboration, include, and call graphs (`CALL_GRAPH`, `CALLER_GRAPH`, `INCLUDE_GRAPH` …). Set `DOT_IMAGE_FORMAT = svg` and `INTERACTIVE_SVG = YES` for large graphs.
- Inline in comments: `\dot ... \enddot`. Use a file from `DOTFILE_DIRS` with `\dotfile name.dot "Caption"`.
- `DOT_COMMON_ATTR` / `DOT_EDGE_ATTR` (newer Doxygen) apply house fonts globally.

## Command line / CI

```bash
dot -Tsvg docs/diagrams/architecture.dot -o build/architecture.svg
dot -Tsvg -Kneato net.dot -o net.svg          # other engine
dot -Tcanon in.dot > out.dot                    # normalise/pretty-print (review diffs)
dot -Tsvg -Gfontname=Helvetica in.dot -o out.svg
```

- Run `dot -Tsvg -o /dev/null file.dot` in CI as a syntax/render check. Treat `Warning:` lines as review items.
- Pin the Graphviz version in the docs container, because layouts change between versions.

## Generated graphs

| Source | Command | Notes |
|---|---|---|
| CMake target dependencies | `cmake --graphviz=deps.dot <build-dir>` | Produces one global file plus per-target files. Filter with `CMakeGraphVizOptions.cmake` (`GRAPHVIZ_IGNORE_TARGETS`, `GRAPHVIZ_EXTERNAL_LIBS` …) |
| Doxygen | Automatic (see above) | Set the scope limits (`DOT_GRAPH_MAX_NODES`, `MAX_DOT_GRAPH_DEPTH`) |
| Python packages / imports | Tools such as `pydeps` or `pipdeptree` | Output is DOT. Post-process before publishing |

Rules for generated graphs:
- Commit the **generator command** (script or Make/CMake target), not just its output. Mark generated `.dot` files with a header comment.
- Post-process with a small script (filter nodes, add `rankdir`, apply the house preamble) instead of hand-editing the output.
- Generated graphs are usually too big. Filter them to the question being asked (one subsystem, direct dependencies only).

## GitHub

GitHub Markdown does **not** render DOT. For README-level docs, either commit the rendered SVG next to the `.dot` source (and regenerate it in CI or a pre-commit hook), or use Mermaid instead.
