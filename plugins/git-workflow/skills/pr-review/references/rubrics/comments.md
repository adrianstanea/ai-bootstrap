# Rubric: comments

Scope: comments added or changed in any source, CMake, script, or YAML file in the diff.

Authority, open first: the project's comment style guide when it has one; otherwise the
rules below.

Checks, applied to added or changed comments only:

1. **Explains why, not what** - flag comments that restate the next line or narrate the
   operation. `minor`.
2. **Never contains secrets or sensitive operational detail** - passwords, tokens, keys,
   internal hostnames. `blocker`.
3. **Workarounds and surprising code state the condition and the failure prevented.** A bare
   "hack" or "do not change" comment is `minor`.
4. **No unexplained `TODO` or `FIXME`** - each needs the limitation and the work, ideally an
   issue link. `minor`.
5. **Comments stay accurate** - when code changed, a nearby comment that still describes the old
   behaviour is `major`.
6. **Lines respect the project's line limit.** Formatters enforce this for code; report only
   for comments in files they do not cover. `minor`.
7. **Overlong comments** that need background belong in design or user docs with a link.
   `minor`.

Do not ask for more comments: do not add boilerplate documentation solely to
make every declaration look documented.
