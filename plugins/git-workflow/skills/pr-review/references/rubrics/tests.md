# Rubric: tests

Scope: test code in the diff, and behaviour changes that should be covered by a test.

Authority, open first: the project's testing guide (`AGENTS.md`, `CONTRIBUTING`, `docs/`) when
it has one; otherwise the rules below.

Checks, applied to added or changed lines only:

1. **Uses the project's test framework and conventions**, not an ad-hoc one. `major`.
2. **Negative cases assert both the failure and the intended diagnostic.** Expecting only a
   nonzero exit or any exception is insufficient. `major`.
3. **Positive cases assert their expected values, state, or side effects**, not only that the
   code ran without error. `major`.
4. **Missing dependencies are never silent** - a test must not pass or return early because a
   dependency is absent; optional scenarios are skipped explicitly and visibly, required ones
   fail. `major`.
5. **Test ownership**: tests live with the component whose behaviour they check, and generic
   tests do not require a specific consumer layout. `major`.
6. **Behaviour changes ship with tests**: new public behaviour with no test change in the diff
   goes under "Questions" unless the PR description explains why.
7. **Deterministic** - no reliance on wall-clock timing, ordering, network, or shared global
   state without isolation. `minor`.

Do not run the test suites unless the user asked; report the command to run instead.
