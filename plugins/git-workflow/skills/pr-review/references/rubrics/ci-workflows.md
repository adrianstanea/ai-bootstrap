# Rubric: CI workflows

Scope: `.github/workflows/**`.

Authority, open first: skill `github-actions-hardening` (security), `github-actions-efficiency`
(cost); runtime and action versions follow the `github-actions-hardening` runtime-upgrade
reference.

Checks, applied to added or changed lines only:

1. **No untrusted input interpolated into `run:`** - `${{ github.event.* }}` values such as PR
   titles, branch names, or comment bodies must go through `env:` first. `blocker`.
2. **No `pull_request_target` or `workflow_run` that checks out or executes PR code with
   secrets or write tokens.** `blocker`.
3. **`permissions:` is set and least-privilege** at workflow or job level. `major`.
4. **Third-party actions are pinned** to a full commit SHA, not a mutable tag or branch.
   `major`.
5. **Secrets are not echoed, written to `GITHUB_ENV`, or passed to untrusted steps.** `blocker`.
6. **Efficiency** - `concurrency` with cancel-in-progress for PR runs, path filters where the
   job does not apply to every change, caching where a restore is clearly missing. `minor`.
7. **Self-hosted runners** are not exposed to fork PRs. `blocker`.
