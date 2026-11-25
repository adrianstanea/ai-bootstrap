# 1. Split personal AI tooling from project configuration

## Context

AI-agent configuration grew inside one project's config repository. It mixed three kinds of
content: personal workflow rules (approval gates, draft pull requests, no tool attribution,
subagent model choice), generic tooling (a hooks engine, ShellCheck, zizmor and gitleaks gates,
git and CI skills), and rules only that project needs (its language subset, build presets,
documentation toolchain). Reusing the workflow in another repository meant copying the whole
config repository or doing without.

## Decision

- **Two layers.** This repository holds everything project-neutral and is installed once per
  machine (`ai-bootstrap user`, driven by the dotfiles). A project provides only its own
  layer: `.ai-hooks.toml`, `.ai-hooks/checks/`, its rules and its plugins, either tracked in the
  project or kept in a separate config repo that `sync/` links in.
- **Configuration, not forks.** Project specifics the engine used to hardcode (container,
  workspace, root variable, env script, policy document, gitleaks branches) are keys in
  `.ai-hooks.toml`; without the file the engine runs only generic checks and never probes
  docker.
- **Opt-in enforcement.** Pull request policy applies everywhere the user-level hook runs.
  Commit policy and `core.hooksPath` activation apply only in repositories that opt in, so
  contributing to an unrelated project never rewrites its hooks or demands DCO sign-off.
- **Do not displace a project's hooks.** The `core.hooksPath` shims chain to the repository's
  own `.git/hooks/<name>`; repositories that prefer the pre-commit framework use
  `.pre-commit-hooks.yaml` instead.
- **Run from a checkout, not a package.** `ai-hooks` stays a dependency-free launcher run from
  this checkout. `core.hooksPath` and the Claude Code hook commands need a stable path, and the
  launcher imports little because it runs on every tool call.
- **The dotfiles stay the only tool installer.** They install gh, uv, pre-commit and the
  Copilot CLI and pin this repository's ref; `ai-bootstrap` only checks versions.

## Consequences

- A project's checks live with the project, and so do their tests.
- Personal rules reach Claude Code through `~/.claude/CLAUDE.md`; a project's `AGENTS.md`
  overrides them where they conflict.
- A repository that has neither `.ai-hooks.toml` nor a synced config gets the pull request
  policy and nothing else.
