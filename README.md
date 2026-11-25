# ai-bootstrap

Personal, project-neutral tooling for AI coding agents (Claude Code, GitHub Copilot) and the git
hooks that keep their work honest. One checkout serves every repository; a project adds only
what is specific to it.

| Layer | Lives in | Holds |
| --- | --- | --- |
| Machine | this repo, installed by `ai-bootstrap user` | personal rules, user settings, plugins, skills, the `ai-hooks` engine |
| Project | the project, or a separate config repo synced into it | `.ai-hooks.toml`, project checks, project rules and plugins |

Project rules override personal ones where they conflict.

## Install

[dotfiles](https://github.com/adrianstanea/dotfiles) clones this repository to
`~/.local/share/ai-bootstrap` at a pinned ref and runs `ai-bootstrap user`. By hand:

```sh
git clone https://github.com/adrianstanea/ai-bootstrap ~/.local/share/ai-bootstrap
~/.local/share/ai-bootstrap/bin/ai-bootstrap user
```

`ai-bootstrap user` is safe to re-run. It:

1. links `hooks/bin/ai-hooks` to `~/.local/bin/ai-hooks`;
2. imports [claude/CLAUDE.md](claude/CLAUDE.md) from a managed block in `~/.claude/CLAUDE.md`;
3. merges [claude/settings.fragment.json](claude/settings.fragment.json) into
   `~/.claude/settings.json`, adding missing keys and keeping existing values;
4. registers this checkout as the `adrianstanea` plugin marketplace and installs its plugins;
5. installs [external-skills.json](external-skills.json) at user scope (`gh` 2.90 or newer);
6. registers a SessionStart hook that re-syncs linked worktrees of synced projects.

Pass `--dry-run`, `--skip-plugins`, `--skip-skills` or `--skip-worktree-sync` to limit it.

## Plugins

| Plugin | Skills | Agents |
| --- | --- | --- |
| `git-workflow` | `gh`, `git-commit-messages`, `interactive-commit-planning`, `pr-review`, `pull-request-workflow` | `pr-reviewer` |
| `agent-workflow` | `subagent-driven-development` | `implementer`, `validator` |
| `ci` | `create-github-action-workflow-specification`, `github-actions-efficiency`, `github-actions-hardening` | |
| `dev-practices` | `cpp-code-style`, `fuzz-finding-to-regression`, `python-like-rust` | `shell-reviewer` |
| `diagrams` | `graphviz-diagrams`, `mermaid-diagrams` | |

`plugins/<id>/plugin.json` is the source of truth. `tools/build_marketplace.py` generates
`.claude-plugin/marketplace.json` and each plugin's `.claude-plugin/plugin.json` from it and from
[marketplace-source.json](marketplace-source.json); `--check` reports drift.

## ai-hooks

`ai-hooks` runs the same checks from Claude Code and Copilot hooks, git hooks and the command
line. With no configuration it runs only the generic checks:

| Check | Stage | What it does |
| --- | --- | --- |
| `remote-policy` | pre-tool | Denies non-draft PRs, remote `gh stack` commands and raw `gh api` PR writes |
| `commit-policy` | pre-tool | Denies `git commit` without `--signoff` or with a `Co-authored-by` trailer (opted-in repositories only) |
| `commit-trailers` | commit-msg | Strips `Co-authored-by` trailers |
| `githooks-path` | session-start | Points `core.hooksPath` at [githooks/](githooks/) (opted-in repositories only) |
| `shellcheck` | edit, pre-commit | ShellCheck at warning and above |
| `zizmor` | pre-commit | Audits staged GitHub Actions workflows |
| `docs`, `license-header` | edit, stop, pre-commit | Run when the repository provides `scripts/docs-tooling.sh` or `scripts/check_license_headers.py` |

`ai-hooks doctor` shows the configuration in force and which checks can run.

### Opting a repository in

A repository opts in with `.ai-hooks.toml` at its root (an empty file is enough). Every key is
optional:

```toml
[container]            # run tools in a devcontainer through docker exec
name = "my-project"    # docker ps name filter; empty: never use docker
workspace = "/workspaces/my-project"

[env]                  # prepared before every tool runs
root_var = "MY_PROJECT_ROOT"
script = "scripts/worktree-env.sh"
unset = ["MyProject_DIR"]

[policy]
commit_doc = "docs/commits.md"            # cited when a commit is denied
pr_workflow = "the pull-request-workflow skill"

[git]
hooks_path = ""        # empty: this repo's githooks/

[checks]
paths = []             # more project check directories (.ai-hooks/checks is always read)

[gitleaks]             # pre-push scan of matching branches
config = "release/gitleaks.toml"
branches = ["release-*"]
```

`~/.config/ai-hooks/config.toml` holds user defaults with the same keys; the repository's file
wins. A linked worktree without the file uses its main checkout's copy.

### Project checks

Put Python modules in `.ai-hooks/checks/`. Each defines `CHECK` or `CHECKS`:

```python
from ai_hooks.model import Check, Result


def run(ctx, files):
    rc, out = ctx.tool(["clang-format", "--dry-run", "--Werror", *files])
    return Result.ok() if rc == 0 else Result.fail(out)


CHECK = Check(
    name="clang-format",
    description="clang-format on edited C++",
    run=run,
    stages={"edit": "check", "pre-commit": "check"},
    patterns=("*.cpp", "*.hpp"),
    needs_container=True,
)
```

`ctx.tool` runs in the devcontainer when one is configured, `ctx.local` on this machine.
`.ai-hooks/invariants.md`, when present, replaces the generic list restated after context
compaction.

### Git hooks

Two ways to run the checks on commit:

- **`core.hooksPath`** (no file in the repository): `sync/install-git-hooks.sh <repo>`, or the
  `githooks-path` check in an opted-in repository. The shims run `ai-hooks`, then the hook the
  repository installed itself in `.git/hooks/`, so a project's own hooks keep working.
- **pre-commit framework**: add this repository to the project's `.pre-commit-config.yaml`:

  ```yaml
  - repo: https://github.com/adrianstanea/ai-bootstrap
    rev: <tag>
    hooks: [{id: ai-checks}, {id: ai-commit-msg}]
  ```

## Project config repos

A separate config repo keeps AI configuration out of a project's history: its files are
symlinked into the checkout and excluded from git. It lists them in `ai-config.paths`, one
repo-relative path per line:

```sh
ai-bootstrap project --config ~/src/my-project-ai-config --target ~/src/my-project
```

This links the listed paths, installs the config repo's `external-skills.json` and plugin
marketplace, and installs the git hooks. See `sync/bootstrap.sh --help`.

## Development

```sh
(cd hooks && python3 -m unittest discover -s tests)
bash sync/tests/test_sync.sh
python3 tools/check_skills.py plugins --strict-budget
python3 tools/build_marketplace.py --check
shellcheck -x -S warning githooks/* sync/*.sh tools/*.sh bin/ai-bootstrap
```

The design is recorded in [docs/adr/0001-layering.md](docs/adr/0001-layering.md).

## License

[BSD-3-Clause](LICENSE).
