# Rubric: commits and PR

Scope: always. Reviews the commit log (`git log <base>..HEAD`) and the PR title and body.

Authority, open first: the project's commit instructions (`CONTRIBUTING`, `AGENTS.md`,
`.github/instructions/`) if any. Skill `git-commit-messages` is a helper only. Where the two
disagree, the project's instructions win.

Checks, per non-merge commit (the skill already excludes merge commits from the log):

1. **Signed off** - a `Signed-off-by:` trailer. `blocker`.
2. **No `Co-authored-by:` trailer** when the project forbids it, even where a tool adds one
   by default. `blocker`.
3. **Subject form** - `type(scope): summary` with a meaningful scope, otherwise
   `type: summary`; imperative mood; lowercase after the prefix; no trailing period; 50
   characters preferred, 72 maximum. Invented scopes such as `stage3` or `pr1` are not allowed.
   `minor`; over 72 characters is `major`.
4. **Body** - separated from the subject by one blank line, wrapped at 72 characters, explains
   why rather than restating the diff, and omitted only when the subject is enough. `minor`.
5. **One coherent concern per commit** - clearly unrelated changes in one commit should be
   split. Do not report borderline groupings. `major`.

Checks, for the PR as a whole:

6. **Title** follows the project's PR-title validation workflow if one exists; if the title format is unclear, put it under
   "Questions" rather than guessing the rule.
7. **Body describes why and how it was verified**, and links the tracked issue when one
   exists. `minor`.
