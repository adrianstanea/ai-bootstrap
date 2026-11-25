---
name: pull-request-workflow
description: Owns approval gates, branch topology, local-only gh stack policy, worktrees and PR creation when splitting work into branches and opening or updating PRs. Use for stacking, restacking, pushing, PR descriptions, mapping PR numbers to branches, worktree builds, or hidden skip-worktree changes. Not for message wording (git-commit-messages), commit grouping alone (interactive-commit-planning) or reviews (pr-review).
argument-hint: 'optional: areas, paths, or desired PR split'
user-invocable: true
---

# Pull Request Workflow

Turn the current working tree into a small set of reviewable commits, branches,
and pull requests. This skill is the single owner of approval gates and the
local-only stack policy; other git skills point here. Use stacked branches locally
only when the changes genuinely depend on one another.

## Approval gates

Each gate below is independent. Approval for one gate never implies approval
for any other gate — always pause and obtain the specific phrase for the gate
you are about to act on.

| Gate                         | Authorizes                                                                      | Required phrase                                    |
| ---------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------- |
| Plan approval (step 4)       | Grouping, branch topology, commit messages, PR titles/descriptions as presented | Explicit approval of the presented plan            |
| Per-commit approval (step 5) | Committing the exact staged file list and message just shown                    | Explicit approval of that specific commit          |
| Push approval (step 7)       | Pushing the exact branches/remotes/bases just listed                            | Explicit approval of that specific push checkpoint |
| Per-PR approval (step 8)     | Opening the exact PR (title/body/head/base) just presented                      | Explicit approval of that specific PR              |

## Local stacks only (`gh stack` policy)

The `gh-stack` skill is installed from upstream at bootstrap; this repository restricts it:

- Use `gh stack` only to manage local branch dependencies and ease rebasing.
- Never run `gh stack push`, `submit`, `sync`, `link`, or `merge`.
- Never create or link stacked PRs on `origin`, publish stack metadata, or retarget PRs to
  reproduce local branch ancestry.
- Push individually approved branches with ordinary `git push`; manage ordinary PRs with
  `gh pr`. Local stack management does not grant permission to rewrite or push any branch.
- Every layer must merge bottom-to-top and keep `main` working without a higher layer; validate
  each layer independently before opening its PR.
- A request to restack or sync locally does not authorize remote operations. Honor requests to
  limit work to local operations; stop remote, PR, or patch-comparison investigation unless a
  concrete safety precondition requires it.
- Before any remote mutation (push, force-push, PR edit, comment, resolving threads), state the
  exact PR and action, present force-push or replacement-PR consequences, and wait for approval.
  After each remote operation verify GitHub's state and stop if it differs from expectations.
  Preserve ordinary PRs rather than creating a remote stack.

## Identify the PR branch first

When asked to commit or push to an existing PR, identify its branch before staging. Prefer PR
metadata; without GitHub auth, map PR numbers to branch heads with
`git ls-remote origin refs/pull/<n>/head`, `git branch -vv`, and `git worktree list`. Before
changing the remote, inspect each PR's base, head, and branch ancestry.

## 1. Inspect the repository

Before proposing changes:

1. Run `git status --short`.
2. Inspect both `git diff` and `git diff --cached` when applicable.
3. Inspect the current branch, remote tracking state, and recent graph.
4. Compare the current work with the intended base, normally `main`.
5. Identify mixed commits, unrelated source changes, generated files, instruction
   files, and scratch files.

If `git status` shows a clean working tree with no unpushed commits, report
this and ask the user what work they intended to organize before proceeding.

Never assume old commit hashes or an earlier conversation still describe the
current branch.

Preserve the user's existing/source branch. Use fresh branches or worktrees
when reorganizing history; do not rewrite a shared branch unless the user
explicitly requests it.

## 2. Group the work

Group files by logical concern and reviewability, not merely by directory.
Typical groups include:

- Functional implementation and its required tests/configuration.
- Documentation tooling and CI enforcement.
- Pure documentation formatting and rule-compliance fixes.
- User-facing documentation content and navigation.
- Unrelated source, generated, instruction, or scratch files, which should be
  excluded or called out separately.

Do not force a fixed number of groups. If a commit mixes concerns, explain how
it will be split or why it must remain together.

Keep mechanical relocations separate from behavioral refactoring when both are
present: preserve file contents and modes in the move commit, then isolate the
functional changes. Verify the move with identical tree/blob objects rather than
assuming rename detection proves it.

Every commit must have a self-contained technical rationale. Name the concrete
tool contract or behavioral requirement that motivates it, including exact
required paths where relevant. Do not justify a commit by referring to upcoming
commits, stack review order, or later work. Before committing, apply the
git-commit-messages checklist to the final message, not just its subject.

## 3. Decide independent versus locally stacked branches

Prefer independent PRs targeting `main` when every group is complete and
reviewable on its own. Related subject matter alone is not a reason to stack.

Use local branch stacks only when:

- a later group depends on files or behavior introduced by an earlier group;
- splitting the dependency would leave an incomplete or misleading change; or
- the user explicitly requests a stack.

Partial local stacks are valid: stack only the dependent groups and keep independent
groups based on `main`. Use `gh stack` only to manage and rebase local branches.
Explain dependencies before creating branches, but publish ordinary PRs individually,
not a GitHub stack. Never publish stack metadata or retarget PRs to mirror local
branch ancestry. If a change cannot be reviewed independently against the intended
integration branch, wait for its prerequisite to merge rather than opening a stacked PR.

Design the sequence to merge bottom-to-top. Every layer must be a working increment
that preserves a working `main` after its prerequisites merge; it must never need a
higher layer to restore behavior or make its tests pass. Validate each intermediate
stage independently, not only the full feature at the stack tip. Before opening each
ordinary PR on `origin`, merge its prerequisites, rebase onto current `main`, and
validate that the PR targets `main` and can merge independently.

Use descriptive branch names without PR numbers or artificial stage labels,
for example:

- `refactor/devcontainer-setup`
- `docs/tooling-and-enforcement`
- `docs/environment-and-setup-guides`

### Stack history operations

- Treat stack preparation as inspection first: identify the target branch, its saved parent and
  descendants, and its difference from the remote tip. Do not reset or rebase a branch to another
  tip merely to resolve divergence; change only the requested layer.
- Squash a stack branch by squashing only that branch's commits, then replay dependents with
  local `gh stack rebase`.
- Before rebasing onto an updated base, compare patches with `git cherry` or `git range-diff`.
  Preserve original tips first; skip commits only when patch equivalence shows they are upstream.
- Before restacking, inventory affected worktrees and their changes. Never move or rewrite a
  branch while its worktree has uncommitted changes; keep them on their branch and verify the
  diff after restoring. When restoring after a history change, restore only in-scope changes.
- Keep edits to the requested concern; a docs reorganization includes no unrelated stack cleanup.
- For history-only tasks, verify commit count, stack topology, and worktree cleanliness, then
  report. Do not run unrelated builds.

## Worktrees

- Create them under `.worktrees/` with `git worktree add --relative-paths .worktrees/<name> <branch>`, keeping `worktree.useRelativePaths=true`. After preserving local changes and
  inventorying dirty or missing worktrees, run `git worktree prune` and
  `git worktree list --porcelain`; do not prune before the inventory.
- Leave a durable branch-to-PR map that survives devcontainer rebuilds; `/tmp` paths and current
  branch names are not a source of truth. Before moving commits, verify PR heads with
  `git ls-remote origin refs/pull/<n>/head` against branch heads.
- **Building from a worktree:** the shell environment may point project variables at the main
  checkout. If the project provides a worktree env script (documented in `AGENTS.md` or `README`
  ), source it from the worktree root before building or testing.
  Verify the root variable it sets equals `git rev-parse --show-toplevel`. Preset build
  directories may derive from that variable; use a fresh directory if `CMakeCache.txt` was
  configured against another checkout, and read the actual error rather than non-fatal noise.
- A child non-interactive Bash may have the environment's `BASH_ENV` reapply main-checkout
  variables: source the helper inside the child, or run `env -u BASH_ENV bash <script>` after
  sourcing it.

## Hidden local changes

If a tracked file looks unchanged but the user says local changes exist, check `git ls-files -v`
for `skip-worktree` or `assume-unchanged` before concluding there is no diff. Distinguish `HEAD`,
the index, and the working tree, and clear the flag only for the requested file.

## 4. Obtain plan approval

Present, before creating branches or rewriting commits:

- group names and exact paths or commit ranges;
- branch names and each branch's base;
- independent/stacked topology and why it was selected;
- proposed commit messages;
- proposed PR titles and descriptions;
- excluded files and any intentional remaining work.

Pause for explicit feedback or approval. Do not infer approval from a general
request to continue if the grouping or topology is still under discussion.

## 5. Create and validate commits

When commits must be created or reorganized:

1. Stage only one approved group at a time.
2. Show the exact staged file list, diff/stat, and commit message.
3. Obtain explicit approval for that commit.
4. Commit with `git commit --signoff`.
5. Never add a `Co-authored-by:` trailer.
6. Load the [Git Commit Messages](../git-commit-messages/SKILL.md) skill and
   apply its template and checklist to draft the commit message.
7. Run `git show --check` after committing, plus the validation for the
   changed file types:
   - `.md`/`.rst`: the project's docs lint command, if it has one
   - `.sh`: `bash -n <file>.sh`
   - code changes: run only the unit tests directly associated with the
     changed files.

For documentation changes, use the repository's scripts rather than invoking formatters
directly.

For shell changes, run `bash -n` and relevant sourced-mode checks. Keep
`.devcontainer/docker/compose.local.yml` commented by default unless the user
explicitly requests the local override.

## 6. Create branches

After plan approval and commit preparation:

1. Create branches in dependency order.
2. Validate each branch's commit range and changed-file summary.
3. Confirm each branch has the intended base and a clean working tree.
4. Report exact branch tips and any intentional untracked files.

If a rebase or cherry-pick conflict occurs while creating a stacked branch,
pause, report the conflicting files and hunks, and ask the user how to resolve
before continuing.

Do not push or create PRs yet.

## 7. Push branches

Present a separate push checkpoint listing every branch, remote, and expected
base. Ask for explicit approval before pushing.

Push in dependency order. Use a normal push for new branches. If rewriting an
existing remote branch was explicitly approved, use `--force-with-lease`, never
blind `--force`. Do not force-push merely because a stacked base moved; explain
the consequences and ask first.

Use ordinary `git push`, not `gh stack push`, `submit`, or `sync`. Pushing branches
does not authorize creating a GitHub stack or changing any PR's base.

On push failure (non-fast-forward, missing remote, authentication error, or
any other error), stop the push sequence, report the exact git error, and ask
the user how to proceed. Do not attempt `--force` or `--force-with-lease`
unless explicitly approved for that branch.

Report successful pushes and remote warnings or failures.

## 8. Create pull requests

### Titles and descriptions

Apply these rules when creating a PR or editing an existing PR's metadata:

- Read the target repository's PR template before drafting. Use its headings
  and checklist; remove inapplicable sections and instructional comments.
  Do not substitute a generic Summary/Validation layout.
- Follow the template's title convention. Keep the title short and specific
  to the change; retain the real Jira key when required, never invent one.
- Keep the description reviewer-focused: one short paragraph explaining the
  problem and outcome, with at most three bullets for distinct changes.
  Avoid file inventories, implementation narration, session history,
  repeated rationale, and claims such as "all checks pass" without evidence.
- Put concise validation results and unverified limits in the template's
  checklist section. Mark checkboxes only when verified for the published
  revision; local replacement work is not evidence for an existing PR.
- Never describe merge order, stack sequencing, or the target branch in a
  PR title or body. GitHub already exposes the base and stacked relationships.
  Keep topology explanations in the approval checkpoint, not the PR.
- Use Review Notes only for actionable review guidance or a significant caveat.
  Omit the section when neither applies. Link detailed logs or discussion
  instead of copying them into the body.
- Describe the actual published diff against the PR's current base, not
  planned or uncommitted changes. Re-read the title and body from GitHub
  after updating them to verify the saved result.
- After a follow-up push, refresh CI for the new head before final handoff.
  Clear a previously checked "All CI checks pass" item while applicable
  checks are pending or failing. When authorized to maintain the PR,
  check it again once fresh results confirm success and remove stale
  "CI is running" prose. Do not leave completed validation marked pending.
- Report missing expected workflows and skipped/cancelled checks explicitly;
  do not treat an empty or green subset of checks as full validation.
  If checks are still running at handoff, state that clearly without
  promising unattended monitoring or changing draft/merge state.

Present a separate PR checkpoint for every PR with its exact:

- title;
- body;
- head branch;
- base branch;
- dependency and merge order.

Open a PR only after the user explicitly approves that checkpoint; a request to
commit, push or "prepare" a PR is not approval to open it. Create approved PRs in
dependency order, always as drafts (`gh pr create --draft`), and mark one ready
(`gh pr ready`) only when the user asks for that PR. Report every PR URL and
base/head relationship. The `remote-policy` hook denies a non-draft
`gh pr create`, and the shared settings make Claude Code ask before every
`gh pr` mutation and `git push`.

If `gh pr create` fails, report the exact error, do not retry with modified
parameters, and ask the user for guidance. If a PR already exists for the head
branch, report its URL instead of creating a new one.

## Completion checklist

Before declaring completion, verify:

- all intended files belong to the correct group;
- unrelated source and scratch changes were excluded or identified;
- every commit has a sign-off and no co-author trailer;
- documentation and shell validation passed where applicable;
- branch bases and tips match the approved topology;
- pushes and PRs were performed only after their separate approvals; and
- the final status clearly distinguishes clean, modified, staged, and untracked
  files.

## Limitations

- Does not write commit message text (git-commit-messages) or review diffs (pr-review).
- Does not cover `gh` query syntax (gh) or CI debugging.
