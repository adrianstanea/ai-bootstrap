---
name: fuzz-finding-to-regression
description: >-
  Turns a fuzzer crash, sanitizer report, hang or failed property check in a C or C++ project
  into a reproduced, minimised, root-caused fix with a regression test and corpus seed. Use to
  triage a crash-/timeout- file, a libFuzzer, ASan, UBSan or TSan report, a Hypothesis failure or
  a __builtin_trap in a fuzz harness, or to turn a fuzz finding into a fix or PR. Not for fuzzer or
  sanitizer setup, or commit wording alone (git-commit-messages).
argument-hint: path of the crash file or the sanitizer report
user-invocable: true
---

# Fuzz finding to regression

Take one finding from "the fuzzer reported something" to "a merged fix that can never silently
return". Tool setup (presets, sanitizer flags, adding a target) is project-specific; this skill is
the workflow after a tool reports. Exact commands: [commands.md](references/commands.md). Harness mistakes:
[harness-pitfalls.md](references/harness-pitfalls.md).

## Ground rules

- **A finding counts only when reproduced.** A suspicion from reading code is a hypothesis:
  write the input or test that triggers it before calling it a bug or fixing it.
- **Harness and fix are separate changes on separate branches.** The harness is test
  infrastructure; the fix is product code. See "Where each change goes".
- **Never commit a seed that crashes unfixed code with the harness alone.** Every
  `<name>_fuzz_replay` test runs in every `tests-linux` build, so the harness branch would be
  red.
- **Fix the code under test, not the harness**, unless the harness called the code in an order
  the runtime never uses (see harness-pitfalls.md).
- Fuzzing finds no data races. A race needs ThreadSanitizer plus a host test that exercises the
  cross-thread pattern; see `tests-linux-tsan` below.

## 1. Reproduce and classify

Run the saved input through the replay binary (GCC or Clang, no libFuzzer needed) and read the
first report. Confirm it twice. If it does not reproduce, it is not a finding yet.

| Class | Signature | Typical cause here |
| --- | --- | --- |
| Memory safety | ASan `heap-buffer-overflow`, `SEGV`, `use-after-free` | peer length/index/size used unchecked |
| Undefined behaviour | UBSan `runtime error:`; float casts need `float-cast-overflow` | shifts, overflow, NaN/inf to int |
| Hang | libFuzzer `ALARM`, `timeout-` file, replay never returns | loop bound from peer or float value |
| Resource exhaustion | `oom-`/`slow-unit-` file, minutes in a loop that copies nothing | peer sizes an allocation or iteration count |
| Remotely reachable `assert()` | `assert_fail` message with an expression | check on a peer value (see below) |
| Property failure | `Illegal instruction` at `__builtin_trap()`, or `property check failed at line N` (`ILL` in the ASan summary) | wrong result, round trip or reference mismatch |
| Harness bug | trap in harness code, impossible call order, false positive | fix the harness, say so in the harness commit |

An `assert()` on a peer-controlled value is a denial of service in debug builds and compiles
to `((void) 0)` under `NDEBUG` , so release builds proceed into an
out-of-bounds access. The fix validates and fails through the existing error path
(an error return, a dropped message, a send reporting no room), not a different assert.

## 2. Minimise

Shrink the input before reading code, so the root cause is visible in a few bytes.

1. `-minimize_crash=1` with the `_fuzzer` binary (`-exact_artifact_path=` for the output).
   Set `ASAN_OPTIONS=dedup_token_length=3` so the minimised input keeps the same crash.
2. For hangs and property failures, or when libFuzzer drifts to another crash, write a delta
   script that removes bytes and keeps a crash only if it has the original signature (same
   sanitizer message and top project frame).
3. Re-run the minimised file with the replay binary. Name it for what it does, for example
   `repro_r5_zero_len` (crashers) or `min_substr_huge_count`, as in the project's fuzz corpus.

## 3. Root cause by reading

Open the top project frame and state, in one sentence, **what the peer sends and which check
is missing or wrong**. Examples: "a data message whose three 32-bit dimensions multiply to
16 modulo 2^32 passes the length check"; "a ring read index outside the ring is used as a
byte offset". If you cannot state it, the minimised input is not small enough yet.

## 4. Variant hunt

The same pattern almost always exists elsewhere. Before writing the fix, list and check:

- other products of 32-bit fields (size, stride and offset helpers), and every consumer of a
  config (a message with data, a message with a config and no data);
- every other path to the same decoder (transports that share a codec), and
  the same field on the other direction (RX and TX);
- every other peer-written index, length or flag that is re-read after validation;
- the same loop or arithmetic in sibling types, other-language bindings, code generators and config readers.

Each variant becomes either a fix in the same change or a written follow-up.

## 5. Where each change goes (the two-branch rule)

| Change | Branch | Content |
| --- | --- | --- |
| Harness (`<name>_fuzzer.cpp`, build rule, corpus of valid seeds) | harness branch | no input that crashes unfixed code |
| Product fix | fix branch off `main` | the fix, a unit test that fails without it |
| Minimised crasher as corpus seed | whichever of the two merges second | `<corpus>/<name>/repro_<what>` |

Example: a harness branch and a fix branch. The harness branch carried a local merge of the fix branch ("drop this merge by rebasing") only so its
corpus could hold the reproducers. A seed added after the fix landed has its own small commit
(`test: add the size overflow input to the StreamLink corpus`). Commit nothing until the user
asks, and never push or edit a PR without approval.

## 6. Regression test and seed

1. **Unit test** in the project's unit-test directory, using its test framework. Name it for
   the behaviour (`link_drops_a_zero_length_packet`). Register a new file in the test build. It must **fail without the fix**
   (step 7).
2. **Test the bypasses**, not only the crasher: boundary values (exactly `UINT32_MAX`, one over),
   the wrapped-in-64-bits case, zero dimensions, both paths (with data / config only).
3. **Corpus seed**: the minimised file in the fuzz corpus directory for the target. Keep it tiny; one seed per
   bug. Valid-input seeds keep the `seed_` prefix.
4. When the harness expressed the property (round trip, wider-type arithmetic, reference),
   keep that property; do not weaken it to make the finding go away.

## 7. Check the fix against its own bypasses

A size or bounds fix is itself attacker-facing code. Re-read it asking:

- Does the check wrap too? a first fix that multiplied in 64 bits is bypassed by a product that wraps there too, and `0xC717A08D * 0xA496448A * 2` is 2^64 + 4. It now checks step by step.
- Does it guard every path? The first fix guarded data messages with data; a config-only
  message may also size the receiver's buffers, and a sibling transport may share the hole.
- Is the validated value the one used? Never re-read a length from shared memory after
  validating it; keep the validated copy (test it, for example `keeps_the_ring_length_it_validated`).
- What does the rejection do? Drop and warn once, not spin, not leave the link stalled.

## 8. Validate

Run in this order; the commands are in [commands.md](references/commands.md).

1. **Reverted-fix check**: restore the unfixed source files only, rebuild, and confirm the new
   unit test and the seed's replay both fail; then restore the fix.
2. **Replay every saved crash file** (often thousands in `artifacts/`) with the `_replay`
   binary. All must pass.
3. **Fresh timed run**: 10 minutes per affected target. The first fix usually unmasks the next
   bug (it did twice: 32-bit size, then its 64-bit bypass, then the config-only path); each new
   crash restarts at step 1.
4. **Every supported compiler and sanitizer configuration** (for example GCC, Clang, and TSan
   if any threaded or shared state is touched).
5. **Static analysis** (clang-tidy or the project's linter) on the changed files; it applies
   to harnesses too.
6. Python findings: the project's property-based (Hypothesis) tests.

## 9. Commit message

Follow the `git-commit-messages` skill:
`type(scope): Imperative subject` (about 50 characters, 72 maximum), body wrapped at 72, sign-off
with `git commit --signoff`, no tool-attribution line or `Co-authored-by`. For a fix
the body states, in this order:

1. what the peer could do, concretely ("a config of 4 x 4 x 0x80000001 elements with 16 bytes of
   data was accepted for a buffer that claims 32 GiB");
2. what a consumer then did (read out of bounds, spin, stall);
3. what is rejected or bounded now, and what happens instead (dropped, one warning logged);
4. how it was found, in one clause ("libFuzzer found it as a SEGV in the StreamLink decoder").

Harness commits say what property is checked and which inputs reach the code, not the bugs.
Example subjects: `fix(core): reject data configs whose size overflows`,
`fix(link): validate what the peer writes into the rings`,
`test: fuzz the link rings as the peer`.

## Checklist

- [ ] Reproduced with the replay binary, twice; classified.
- [ ] Minimised; named for what it does.
- [ ] Root cause stated as "the peer sends X, the check Y is missing".
- [ ] Variants searched (other products, paths, rings, languages).
- [ ] Harness and fix on separate branches; no crashing seed with the harness alone.
- [ ] Unit test fails without the fix; seed added to the fuzz corpus.
- [ ] Fix checked for 64-bit wrap, second path, re-read of shared memory, assert replaced.
- [ ] All saved crashes replayed; fresh 10-minute run clean.
- [ ] All compiler and sanitizer configurations green; static analysis clean.
- [ ] Commit message states peer action and what is rejected now.

## Limitations

Covers host-side findings. Target-only code (interrupt handlers, device callbacks) has no fuzz
or sanitizer path: review it by reading.
