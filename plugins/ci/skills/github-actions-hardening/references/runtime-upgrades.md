# Runtime upgrades

Use when workflow logs report an action running on a deprecated runtime, or when bumping action
versions in `.github/workflows/*.yml` while preserving behavior.

## Rules

- Upgrade to the latest stable **major** version of each action that is compatible.
- Pin to the full commit SHA of the target release, with a version comment. Do not recommend
  mutable tags or branches (`@v4`, `@main`).
- Upgrade one action (or one tightly related group) per commit so failures are easy to isolate.
- Keep triggers, permissions and behavior unchanged unless the change is intentional.
- Review first: any `actions/*` action, especially `actions/setup-*`, and any action named by
  the deprecation warning.

```yaml
steps:
  - uses: actions/checkout@8ade135a41bc03ea155e62e844d188df1ea18608 # v4.3.1
  - uses: actions/setup-node@60edb5dd545a775178f52524783378180af0d1f8 # v4.0.4
```

Identify the latest compatible release first, then use its commit SHA.

## Verification

1. Edited workflows still parse and keep the same triggers and permissions.
2. Run the affected workflows (or equivalent local build/test) and confirm upgraded steps pass.
3. Release, signing and artifact steps still produce the expected outputs.
4. Run logs show no new deprecation warnings.

## PR notes

List which actions moved (from -> to), any action that could not move to a new major and why,
and which workflows were re-run. Useful even with Dependabot: it may be off for workflows, or
the warning may precede an automated update.
