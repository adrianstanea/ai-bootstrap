# Delegation brief template

A subagent starts with fresh context and knows only this brief. Fill every field.

```text
Objective: <one sentence: the outcome, not the steps>
Context: <what the worker cannot infer: why, related decisions, links>
Owned files: <exact paths it may edit; everything else is read-only; "none" for read-only>
Out of scope: <non-goals, files and actions not to touch>
Acceptance criteria: <observable conditions; commands that must pass>
Output contract: first line `Verdict: <enum>`, <= 300 words, evidence as command + trimmed
  output or file:line. Write anything longer to <scratch dir>/<name>.md and return the path.
Budget: <maxTurns, or "stop after N tool calls and report PARTIAL">
Rules to pass on: run `graphify query` before searching code (if graphify-out exists);
  any agent you spawn must set model: "sonnet" (AGENTS.md); never commit, push or touch PRs.
```

Verdict enums: implementer `DONE|PARTIAL|BLOCKED`; validator `PASS|FAIL|BLOCKED`;
`pr-reviewer` `APPROVE|CHANGES_REQUESTED|BLOCKED`.

## Examples

```text
Objective: Move the set_param() calls in src/gain/gain_node.cpp into configure().
Owned files: src/gain/gain_node.cpp, src/gain/gain_node.hpp
Out of scope: public header API, other modules.
Acceptance criteria: unconsumed-parameter warning still fires; gain unit test passes.
```

```text
Objective: Confirm the gain change meets the criteria.
Acceptance criteria: the project's test command passes;
  `ai-hooks run --files src/gain/gain_node.cpp` passes.
```

## Reading the report

Accept a report only if its evidence is quoted from tool output. "Should work" or "tests
pass" without a command is missing evidence. Rerun a decisive check yourself if in doubt.
