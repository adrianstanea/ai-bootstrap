# Output contract

Produce one report with these sections, in this order. Omit a section only when empty,
except "Scope" and "Verdict".

## Scope

Base ref, number of commits, number of changed files, and the rubrics loaded (with the path
pattern that matched each).

## Deterministic checks

One line per tool: `ran: pass`, `ran: <n> issues` (summarize, do not paste logs), or
`not run: <reason>`.

## Findings

One entry per finding:

```text
[<severity>] <path>:<line> - <one-line problem>
  Rule: <authority path or skill> - <section or rule name>
  Why: <one sentence on the consequence>
  Fix: <concrete suggestion, a snippet if short>
  Confidence: <high|medium>
```

Severity:

- `blocker` - breaks a hard project rule (for example `std::` in framework code, a missing
  SPDX header, an exception used for error handling) or is incorrect.
- `major` - violates a documented convention with real maintenance cost.
- `minor` - a documented convention that is cosmetic or easy to fix.

Only `high` and `medium` confidence findings appear here. A finding needs all of: a
`file:line` in the diff, a cited rule you opened, and a fix. Anything weaker belongs in
"Questions" or is dropped; a finding with no rule behind it is never padded in.

The one exception is a verified correctness defect (a referenced file, symbol, or signature
that does not exist, or code that cannot compile). Write `Rule: correctness - <the evidence you checked>` and cite the file you read. Never use this for taste or likely-but-unchecked
problems.

## PR readiness

For a GitHub PR, state the current head, draft state, fresh hosted-check status and any
checklist/prose discrepancies. Separate passing reported checks from missing expected
coverage. Cite metadata issues by PR URL rather than inventing a diff line. This section
does not authorize metadata edits or constitute approval to merge.

## Questions

Items you could not decide: ambiguous intent, a rule that may not apply, or code outside the
diff that the change may affect. Phrase each as a question to the author.

## Skipped

Checks not performed and why (authority file missing, tool unavailable, no matching rubric for
a changed file).

## Verdict

One of `no blockers`, `blockers found`, or `incomplete review` (when material checks were
skipped), followed by a one-sentence summary. Never write "approved"; approval is a human
decision.

## Rules

- Do not report formatting or lint issues that a deterministic tool in the SKILL covers. A
  failing tool is reported only under "Deterministic checks", never again under "Findings".
- Do not report pre-existing problems in lines the diff did not touch.
- Do not pad the report: no praise, no restating the diff, no more than 20 findings. If there
  are more, report the highest severity ones and say how many were omitted.
