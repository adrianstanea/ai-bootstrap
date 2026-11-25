# Rubric index

Load a rubric when at least one changed file matches its patterns. Several can match. A rubric
cites its authority; open the authority before reporting a finding that depends on it.

These are the generic rubrics. Project-specific rubrics come from the repository under review:
see "Project rubrics" in `SKILL.md`.

| Rubric                             | Changed paths (any match)                                     | Authority                                                         |
| ---------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------- |
| [comments.md](comments.md)         | any changed source or config file that adds or edits a comment | the project's comment style guide, if any                         |
| [docs.md](docs.md)                 | `**/*.md`, `**/*.rst`, `doc/**`, `docs/**`                    | the project's docs instructions, if any                           |
| [tests.md](tests.md)               | `tests/**`, `**/test_*`, `**/*_test.*`, `**/*.test.*`         | the project's testing guide, if any                               |
| [commits-pr.md](commits-pr.md)     | always (commit log and PR title/body)                         | the project's commit instructions; skill `git-commit-messages`    |
| [ci-workflows.md](ci-workflows.md) | `.github/workflows/**`                                        | skills `github-actions-hardening`, `github-actions-efficiency`    |

## Adding a rubric

1. Create `<name>.md` here. Keep it under about 60 lines: a short scope line, the authority to
   open first, then 3-8 concrete, checkable items. Each item says what to look for in a diff
   and its severity.
2. Add one row above. Use the narrowest path patterns that still catch the relevant changes.
3. Run `tools/check_skills.py`. It does not read rubrics, but it catches a broken skill.

Do not copy rules out of the authority. If the authority is missing or wrong, fix the
authority and cite it.
