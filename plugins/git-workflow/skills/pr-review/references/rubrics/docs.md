# Rubric: docs

Scope: Markdown, reStructuredText, and anything under a docs directory (`doc/`, `docs/`).

Authority, open first: the project's docs style instructions if any (`AGENTS.md`,
`CONTRIBUTING`, docs guide). Lint and format are covered by the deterministic checks; this
rubric covers what those tools cannot see.

Checks, applied to added or changed lines only:

1. **Durable docs read as timeless explanations** - flag narration of the current conversation
   or PR ("found and fixed this while responding to feedback"). `major`.
2. **Requested names and structure are preserved** - a heading, page, or term renamed without
   the PR stating why. Also preserve semantic distinctions such as Note versus Tip. `major`.
3. **New pages are reachable** - added to the docs index or `toctree` and cross-referenced
   with targets that exist. The docs build catches some of this; report it under
   "Questions" if it was not run. `major`.
4. **Links resolve and render** - a broken link can render as plain text silently, so
   check the target path in changed links. `major`.
5. **Docs match behaviour** - a changed option, preset, command, or default that is
   documented elsewhere in the repo without a matching doc update. `major`.
6. **Concise** - no padding, duplicated explanations, or session-specific context. `minor`.
7. **Public APIs, commands, and options are documented** where the project documents them.
   `major`.
