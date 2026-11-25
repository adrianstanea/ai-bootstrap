---
name: git-commit-messages
description: Drafts and reviews a single Git commit message (subject, body, sign-off) using the repository convention. Use when asked to write, fix, or check a commit message for a change. Not for grouping a dirty tree into several commits (interactive-commit-planning) or branches and PRs (pull-request-workflow).
argument-hint: describe the change or provide a draft message
user-invocable: true
---

# Git Commit Messages

Use this skill when drafting or reviewing commit messages. Committing itself needs the
approval gates in [pull-request-workflow](../pull-request-workflow/SKILL.md).

## Template

```text
type(scope): Summarize the change

Explain the problem and why this change is needed. Describe the prior behavior,
the intended outcome, or a relevant trade-off; do not repeat implementation
details that the diff already makes clear.

Optional additional context goes in separate paragraphs.
```

Use `type: Summarize the change` when no meaningful scope applies. Omit the body
only when the subject alone gives enough context.

## Checklist

- Leave one blank line between a subject and its body.
- Make the subject imperative, capitalized, and free of trailing punctuation.
- Target a 50-character subject; 72 characters is the maximum.
- Wrap body paragraphs at 72 characters.
- Explain why the change is needed rather than how it was implemented.
- Name the concrete constraint that makes the change necessary. For a tool's
  required layout, state the exact directory or filename it expects and the
  behavior that fails without it; do not substitute generic cleanup rationale.
- Make each message self-contained and atomic. Do not refer to previous,
  upcoming, or follow-up commits, stack layers, review sequencing, or the
  conversation. Explain this commit's reason and outcome on their own.
- Use a meaningful scope only; never invent `stage3`, `pr1`, or `pr2` scopes.
- Use `git commit --signoff` and never add a `Co-authored-by:` trailer.

## Review a draft

Before presenting a message for approval, verify that it:

1. Describes one coherent change.
2. Makes sense after "If applied, this commit will ...".
3. Adds context not already obvious from the diff.
4. Uses a body only when that context is useful.
5. States a verified technical reason, not a speculative benefit or a plan for
   later work.
6. Contains no dependency on another commit's narrative to explain this change.

For example, a move required by CIM should explain that the CLI discovers named
manifests at `targets/<name>/sdk.yml` from the source root, allowing a repository
URL to be used without a manual clone. It should not say that the move prepares
for a later refactoring commit.
