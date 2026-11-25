Critical workflow invariants (restated after context compaction):

- Pushing, or mutating a pull request or its remote branch, needs explicit user approval for that action.
- Pull requests open only when the user asks, always as drafts (`gh pr create --draft`); `gh pr ready` only on request.
- Commits carry only the `Signed-off-by:` trailer; no `Co-authored-by` and no tool attribution.
- Subagents default to model `sonnet`.
