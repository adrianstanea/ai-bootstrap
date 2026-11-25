---
name: interactive-commit-planning
description: Groups a dirty working tree into logical commits and commits each group only after the user reviews its diff and message. Use when asked to split, organize, or commit accumulated changes. Not for one message on one change (git-commit-messages) or branches, pushes and PRs (pull-request-workflow).
user-invocable: true
---

# Interactive Commit Planning

Turn an unstructured set of working-tree changes into a small number of
reviewable, signed-off commits -- without ever committing something the user
hasn't explicitly approved.

## When to Use

- The user asks to commit a batch of accumulated changes.
- The user asks to split working-tree changes into multiple logical commits.
- The user asks to "prepare commits" or "stage this for review" before a PR.

Not for a single, obviously-atomic change the user has already described --
just commit that directly with a normal message. Branches, pushes, and PRs belong to
[pull-request-workflow](../pull-request-workflow/SKILL.md), which owns the approval gates.

## Hard Constraints (never violate)

- Every commit uses `git commit --signoff`.
- Never add a `Co-authored-by:` trailer, under any circumstance.
- Never run `git commit` without first showing the user the exact commit
  message and the staged diff for that group, and getting an explicit
  go-ahead. Silence is not approval.
- Never bundle unrelated changes into one commit for convenience -- split
  further rather than mix concerns.
- If [scripts/interactive-commit.sh](./scripts/interactive-commit.sh) or the
  plan file is unavailable, or the script errors out partway through, fall
  back to manually running `git add <paths>` and
  `git commit --signoff --file=<message>` for each group, still requiring
  explicit user approval before each commit.

## Procedure

1. **Survey the repository state.**
   Run `git status --short` and `git diff` (and `git diff --cached` if
   anything is already staged). Read enough of each diff to understand why
   the change was made, not just which lines changed. For untracked files
   identified in `git status`, review their contents with
   `git diff --no-index /dev/null <file>` or `cat` before grouping, and
   include them in the appropriate group. If the repository is mid-merge,
   mid-rebase, or in a detached HEAD state, stop and ask the user how to
   proceed before grouping changes.

2. **Propose a grouping.**
   Cluster files by logical concern, not by directory or file type alone.
   Typical clusters: a core/library change plus its tests, a docs update
   paired with the code it documents, a generated/config file paired with
   the script that produces it. Order groups so foundational changes (a
   shared macro or API change) come before the code that depends on them.
   Present the grouping as a short list (paths -> one-line rationale) and
   get confirmation before drafting full messages if the grouping is
   non-obvious.

3. **Draft one commit message per group.**
   Load the [Git Commit Messages](../git-commit-messages/SKILL.md) skill and
   apply its template and checklist with the repository commit instructions.

4. **Write the grouping as a plan file** (see
   [assets/commit-plan.example.txt](./assets/commit-plan.example.txt) for the
   exact format: blocks separated by a line containing only `---`, first
   line of each block is the space-separated paths, the rest is the commit
   message).

5. **Run [scripts/interactive-commit.sh](./scripts/interactive-commit.sh)
   against the plan file.** For each group it stages only those paths,
   shows the staged diff and drafted message, then prompts:
   `y` commit as-is, `e` edit the message first, `s` skip (unstages,
   revisit later), `q` abort (leaves remaining changes untouched). It only
   ever calls `git commit --signoff --file=<message>` after a `y`/`e`
   response -- it never adds a co-author trailer. If the script is
   unavailable or errors out, fall back to the manual staging/commit
   procedure described in Hard Constraints above.

6. **Verify and summarize.**
   After the last group, run `git status --short` and
   `git log --oneline -n <count>` to confirm the tree is clean (or
   intentionally left with remaining changes) and show the final commit
   list.

## Example prompts that trigger this skill

- "Help me commit all this work -- group it sensibly and let me review each
  commit message first."
- "Split these changes into logical commits and sign off each one."
- "I have a bunch of uncommitted changes across the logging and node files,
  prepare commits for them."
