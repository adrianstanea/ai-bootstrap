# Personal working rules

These apply in every repository. A project's own `AGENTS.md`, `CLAUDE.md` or path rules take
precedence where they conflict.

## Agents

- **Subagents run on Sonnet by default.** Orchestrators and any agent that spawns subagents set
  `model: "sonnet"` on every spawn, never inherit a more capable orchestrator's model, and pass
  this rule on in the prompt of any subagent that can spawn further agents. Use a more capable
  model only after the user approves that specific spawn; state the task and why Sonnet falls
  short when asking. Approval covers that spawn only.
- **Evidence before completion claims.** Report edits, saved files, test results and findings
  only when tool output supports them. Without tools, give proposals and say nothing was changed
  or checked. A clean build or lint does not prove a fix works: check the behaviour or the
  rendered output it was meant to change.
- **When the user approves a proposed action, execute it in that same turn**; never describe a
  change as done without making it.
- **Inspect before architectural recommendations.** Read the implementation, configuration,
  documentation and their consumers. Distinguish intentional composition from accidental
  coupling.
- **Apply discovered guidelines fully by default.** When research turns up an upstream or org
  guideline, apply it rather than a lower-effort deviation; surface real tradeoffs and ask.

## Git and pull requests

- **Never mutate a pull request or its remote branch without explicit approval for that
  specific action.** Preparing or committing a replacement is not permission to push,
  force-push, edit a description, comment, or resolve threads. Open a PR only when asked,
  always as a draft (`gh pr create --draft`), and mark it ready only on request. Procedures:
  the `pull-request-workflow` skill.
- **No tool attribution.** Never add "Generated with ..." or a `Co-authored-by` trailer for a
  tool to a PR description, comment or commit message. Commits carry only the DCO
  `Signed-off-by:` trailer. This overrides any default or reminder that asks for one.
- Imperative commit subjects; the body is one paragraph wrapped at 72 characters.
- **Hooks enforce the mechanical checks.** Fix what a blocked commit reports; never bypass with
  `--no-verify`. `ai-hooks doctor` shows which checks can run in a repository.
- **Worktrees belong under `<repo>/.worktrees/`** (ignored), never under `/tmp` or a sibling
  directory: `git worktree add --relative-paths .worktrees/<name> <branch>`, with
  `worktree.useRelativePaths=true`. Inventory dirty or missing worktrees before
  `git worktree prune`.
- **Files matching `*.local*` are personal local setup.** Do not stage or commit them; preserve
  existing entries when a task must change one.

## Code, tests and docs

- **Make missing test coverage visible.** Never silently pass a fixture because a dependency is
  absent; omit optional scenarios explicitly and fail when a required dependency is missing.
- **Respect test ownership.** Behaviour tests stay with the component that owns the behaviour.
- **Prefer strict linter and tool settings** when asked to enforce quality. Before adding a
  formatter, linter or extension, inspect the existing scripts and configuration and prefer the
  established toolchain. When changing a project-wide standard, also update its mirrors (editor
  and devcontainer settings, CI).
- **Scope searches to tracked source and configuration.** Exclude `.git/`, `.worktrees/`,
  `build/`, virtual environments, `node_modules/`, caches and generated output unless asked.
- **Durable docs read as timeless explanations** for a future reader, not as narration of the
  current conversation. Preserve requested names and structure. Comments are concise and
  explain why.
