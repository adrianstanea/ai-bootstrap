---
description: Runs GitHub CLI (gh) queries for issues, PRs, reviews, workflow runs and REST endpoints with structured --json/--jq output, including in restricted shells. Use for any gh command or GitHub lookup from the shell. Not for plain git operations or PR approval and push rules (pull-request-workflow).
license: MIT
metadata:
  github-path: gh
  github-ref: refs/heads/main
  github-repo: https://github.com/Cogni-AI-OU/cogni-ai-agent-skills
  github-tree-sha: 759eb864c6e540c2c961a600a2e8967e2c741703
name: gh
---

<!-- markdownlint-disable MD013 MD023 MD031 MD032 -->

# gh

Use `gh` as a structured client first. Prefer native fields, explicit routing,
and bounded fallbacks over brittle shell post-processing.

## When to Use

- User asks to use `gh`, GitHub CLI, or to query GitHub from shell.
- Task involves issues, PRs, reviews, workflow runs, jobs, discussions, or GitHub REST endpoints.
- Execution is inside CI, Codespaces, or another restricted shell.

For subcommands and flags run `gh <command> --help`; do not guess flags.

## Repository policy

Creating, editing, commenting on, or pushing to a PR is a remote mutation: follow the
approval gates in [pull-request-workflow](../pull-request-workflow/SKILL.md). Never run
`gh stack push|submit|sync|link|merge`.

## Limitations

- Not for raw git operations, non-GitHub hosts, or bulk data sync better done with an SDK.

## Common Pitfalls

- **Paginating Endlessly**: Using `gh api` to fetch thousands of records without a `--jq` filter or `--paginate` limit, causing out-of-memory errors or API rate limits.
- **Shell Pipeline Brittleness**: Piping `gh` JSON output through `grep` and `awk` instead of natively querying with `--jq`, leading to broken scripts when GitHub's API response order shifts.
- **Interactive Hangs**: Running commands like `gh pr create --draft` without the `--fill` or `--body` flags in a headless environment, causing the workflow to stall indefinitely waiting for a TTY editor.

## Core Process

1. Verify availability and auth first: `gh --version`, then `gh auth status`.
2. Choose the narrowest native `gh` surface before reaching for `gh api`:
   - `gh issue view/comment` for issues; see the `gh-issue` and `github-issue` skills
     for issue-specific guidance and runtime routing
   - `gh pr view/comment/review` for pull requests; see the `gh-pr` and `github-pr` skills
     for PR-specific guidance and runtime routing
   - `gh api` only when native subcommands do not expose the needed field
3. Prefer structured output over shell filtering:
   - use `--json`, `--jq`, or `--template` instead of `grep`/`rg`
   - use `gh api` for metadata, not ad hoc HTML scraping
4. Query the smallest object that answers the question:
   - issue metadata before comments
5. After each command, verify progress explicitly:
   - non-empty stdout or expected JSON field
   - output free of semantic-change notices
   - result actually answers the current question
6. If the same normalized command shape fails twice with the same warning,
   error, or empty result, pivot strategy instead of retrying.

## Structured Query Patterns

- Use `gh pr view <number> --json headRefName,baseRefName,commits` to extract PR commit history
  (e.g. for visualization to generate topology data like `mermaid` `gitGraph` diagrams without cloning explicitly)
- Prefer native JSON first:
  - `gh issue view <number> --json comments,number,title,state,author,url`
  - `gh pr view <number> --json number,title,state,reviewDecision,url`
  - `gh pr view <number> --json comments,reviews`
- Use `gh api` for objects that native subcommands do not expose cleanly (load `gh-api` skill for details).
- Use `--jq` or `--template` before external filters.

## Preferred Patterns

- Comment directly without touching workspace files:
  `gh issue comment <number> --body "..."`
- Reply through the originating GitHub surface:
  - issue thread -> `gh issue comment`; see `gh-issue` or `github-issue` for routing
  - pull request comment/review thread -> see `gh-pr` or `github-pr` for PR routing
  - inline review thread -> `gh api .../replies`
- For long comments, avoid heredocs which can cause hangs. Write to a temporary file and use `--body-file`:
  `gh issue comment <number> --body-file /tmp/comment.md`
- For GraphQL mutations with large bodies from files:
  `gh api graphql -f query='mutation($body: String!) { ... }' -F body=@file.md`
- For non-code-change tasks, verify workspace cleanliness after posting.

## GitHub Actions Runtime

For high-level routing guidance, response detection, workspace invariants, and branch sync policies
in GitHub Actions, refer to the **github-issue** and **github-pr** skills.

### GitHub Runtime Decision Policy

- **Default to Best Practice:** Implement the most recommended path autonomously when multiple options exist.
- **Document Trade-offs:** Capture unresolved decisions, explicit options, and impacts in the PR description.
- **Keep Moving:** Proceed with safe defaults and request preference feedback in the PR instead of waiting.
- **Report Defensively:** Present recommended option first; list alternatives only if they alter scope or risk.

## Restricted Shell Rules

- In allowlisted shells, do not assume `grep`, `rg`, or complex pipelines are
  permitted just because `gh` is permitted.
- Prefer `gh --json/--jq/--template` over external text filters.
- Probe one command shape first before parallel fan-out.
- If a shell policy blocks a `gh`-adjacent command shape, classify it as
  `POLICY_DENIED` and pivot immediately.

## Failure Signatures

- Empty stdout from a supposedly successful `gh` query is a signal, not a
  success. Check whether the subcommand supports the requested mode in this
  environment.
- If a shell policy blocks a `gh`-adjacent command shape, classify it as
  `POLICY_DENIED` and pivot immediately.

## What to Avoid

- Do not use `-f` (`--raw-field`) when you intend to read a value from a file
  using `@`; always use `-F` (`--field`) for file expansion.
- Do not build `gh ... | grep ... | grep ...` chains as the default diagnostic
  path.
- Do not retry the same `gh` command shape after semantic warnings.
- Do not create temp files for comments or analysis when direct `gh`
  subcommands are available.

## Related Skills

- **gh-api**:
  Load when working with the `gh api` command.
- **gh-issue**:
  Load when working with the `gh issue` command.
- **gh-pr**:
  Load when working with the `gh pr` command.
- **gh-run**:
  Load when working with the `gh run` and the `gh workflow` commands.
- **gh-search**:
  Load when working with the `gh search` command.
- **gh-skill**:
  Load when working with the `gh skill` command.
- **gh-models**:
  Load when working with the `gh models` command.
- **github-issue**:
  Load when working with issues or when the runtime was triggered by an issue comment.
- **github-pr**:
  Load when working with changes associated with a pull request or when the runtime was triggered by a PR comment.
- **github-topics**:
  Load when searching for relevant tools, libraries, or curated resources.
