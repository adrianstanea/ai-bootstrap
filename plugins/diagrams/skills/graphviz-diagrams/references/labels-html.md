# Labels: text, HTML-like tables, records

Contents: Plain labels · Edge labels · HTML-like labels · Ports in tables · Records (legacy) · Pitfalls

## Plain labels

- `label="Order service\nGo, gRPC"`: use `\n` to put a second line with a technology or role.
- Left-aligned multi-line (code, lists): `label="init()\lrun()\lstop()\l"`. Every line ends with `\l`, including the last.
- Keep node labels to 3 lines or fewer and about 30 characters per line. Move detail into prose or tooltips.
- `tooltip="..."` and `URL`/`href` only work in SVG output (see `embedding.md`).

## Edge labels

| Attribute | Placement | Use for |
|---|---|---|
| `label` | Mid-edge, takes part in layout | Normal labels (`dot` makes room) |
| `xlabel` | Placed after layout, near the edge | Dense graphs, `splines=ortho` |
| `headlabel` / `taillabel` | At the ends | Cardinalities (`1`, `0..*`), port numbers |
| `labelfontsize`, `labeldistance`, `labelangle` | Head/tail labels | Fine-tuning |

Keep edge labels to 1–3 words (verbs or protocols: `calls`, `gRPC`, `publishes`).

## HTML-like labels

Use these for UML classes, schemas, multi-section boxes, and coloured headers.

```dot
order [shape=plain, label=<
  <table border="0" cellborder="1" cellspacing="0" cellpadding="4">
    <tr><td bgcolor="gray90"><b>Order</b></td></tr>
    <tr><td align="left" balign="left">+ id: UUID<br/>+ placed_at: Time</td></tr>
    <tr><td align="left" balign="left">+ total(): Money</td></tr>
  </table>
>];
```

- Delimit with `< >`, **not quotes**. The content must be well-formed XML: close every tag, write `<br/>`, and escape `&amp; &lt; &gt; &quot;` (so `vector<int>` becomes `vector&lt;int&gt;`).
- Pair with `shape=plain` (or `shape=none, margin=0`) so the table is the node.
- Table attributes: `border` (outer), `cellborder`, `cellspacing="0"` (shared borders), `cellpadding`, `bgcolor`, `color`, `style="rounded"`.
- Cell attributes: `align="left|center|right"`, `balign="left"` (alignment of `<br/>` lines), `colspan`, `rowspan`, `port`, `bgcolor`, `href`, `tooltip`.
- Text tags: `<b> <i> <u> <s> <sub> <sup> <font point-size="9" color="gray40" face="...">`, plus `<br align="left"/>`, `<hr/>` between rows, and `<vr/>` between cells.
- Only a subset of HTML is supported (no CSS, no `<div>`/`<span>`, no `class` attribute).

## Ports in tables

```dot
customer:id -> order:customer_id;   // cell-to-cell edge
```

Put `port="id"` on the `<td>`. Edges then attach to that row, which is essential for schemas. Add a compass point to pick the side: `customer:id:e -> order:customer_id:w`.

## Records (legacy)

`shape=record, label="{Order|+ id\l+ total()\l}"`, where `|` separates fields, `{}` flips orientation, and `<p>` names a port. Records flip orientation with `rankdir`, which is confusing. **Prefer HTML tables for new diagrams.** Keep records only when editing existing diagrams that use them.

## Pitfalls

- A `&`, `<`, or `>` in plain text inside HTML labels causes a syntax error. Escape them.
- Writing `label="<b>x</b>"` (quotes) shows the raw tags. HTML labels need `label=< ... >`.
- Mixing `shape=box` with an HTML table creates a double border. Use `shape=plain`.
- Wide tables in `LR` layouts make diagrams huge. Show only the key columns.
