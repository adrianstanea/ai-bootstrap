---
name: cpp-code-style
description: 'C++ naming and member-organization conventions for writing and reviewing code: snake_case locals, no vendor/library function-name prefix clashes, _cb suffix for callbacks, nested structs for related state, class members over globals, member ordering, and flagging unclear dead code. Use when writing or reviewing C++ or wrapping a vendor C API.'
user-invocable: true
---

# C++ Code Style

General conventions for writing and reviewing C++ code, independent of any specific
library or platform.

## Naming

- Never reuse a vendor/library's function-name prefix (e.g. `foo_*` from a `libfoo` C API) for a
  local method or free function — it reads as a call into that library. Pick a name that clearly
  belongs to the calling code instead.
- Give IRQ/event/async callback functions a `_cb` suffix (e.g. `on_data_ready_cb`).
- Local variables use snake_case, not camelCase, even when mirroring a vendor's parameter names
  (vendor `p_data`, not `pData`).

## Member organization

- Group cohesive per-instance state into small nested structs (e.g. `Config`, `ChannelAlignment`)
  instead of parallel loose members. Give the struct and the member field a one-line role comment.
- Prefer class members over free/global variables for per-instance state. Only fall back to
  free/global storage when the underlying API requires a stable address that outlives the
  member's natural scope (e.g. a struct registered with an interrupt/callback subsystem); a
  one-shot init-param struct that's only read during a single init call can just be a local.
- Order members by role with a one-line grouping comment per block (e.g. "hardware handles",
  "runtime state"), not alphabetically or grouped purely by type.

## Code review habits

- Don't silently delete code whose purpose is unclear (e.g. a flag or branch that looks
  currently unused) — flag it and confirm with the author before removing. If asked to keep it,
  add a short inline `// NOTE:` comment explaining the ambiguity instead of leaving it unexplained.

## Comments

- Default to a single short line. Only use multiple lines when the rationale genuinely can't fit
  in one — that should be the exception, not the norm.
- State only what the code can't show on its own (the "why", not the "what"). Don't restate what
  the next line already says, and don't write a comment addressed to a reviewer explaining a change.

## Limitations

- Style only; formatting is enforced by `.clang-format` and checks by `.clang-tidy`, not here.
- Does not cover project-specific library or platform restrictions (see the project's
  `AGENTS.md` or style guide).
