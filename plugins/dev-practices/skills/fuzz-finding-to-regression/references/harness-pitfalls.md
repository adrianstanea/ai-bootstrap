# Harness pitfalls and rules

What tends to go wrong when writing fuzz harnesses. Tool setup is project-specific.

## Build

- **Build with every supported compiler.** The replay binary is part of the normal test build
  and may compile with strict warnings as errors. Bare `__int128` is rejected under
  `-Wpedantic`: write `__extension__ using Wide = unsigned __int128;`. Clang-only pragmas must
  sit under `#if defined(__clang__)`.
- **Static analysis applies to harnesses.** Run it on the harness.
- A harness that must force compile definitions on the code under test compiles that source
  into its own target with `target_compile_definitions`. Add sanitizer checks outside
  `-fsanitize=undefined` the same way (`-fsanitize=float-cast-overflow` for a narrowing cast).
- Register the target through the project's fuzz-target helper; never hand-roll executables.

## Harness body

- **Heap-allocate at the exact size** the production code is told it has, so ASan sees every
  byte past the end. A stack or oversized buffer hides the overflow.
- **Bound the work**: cap steps and operations, inputs, and allocation; set timeouts to zero
  where the code would block.
- **Make the input structured**: decode bytes into steps or fields so the fuzzer does not stop
  at the first check; wrap records in valid frames to pass a CRC; let a dimension byte choose
  between a small value and a raw 32-bit value so wrapping products are reachable.
- **Reset all state per call**; do not leak (LSan), do not print.
- **Call the code the way the runtime does.** A harness that calls in an order the runtime
  never uses produces false findings. Check the real caller before reporting.
- Document the input format in the header comment, with the property list.

## Properties

"Does not crash" finds little. Stronger properties, checked with `__builtin_trap()` (or a
macro that names the line first), find most bugs:

| Property | Finds |
| --- | --- |
| Round trip: decode, encode, decode equals first decode | encoder overruns, field drift |
| Wider-type arithmetic: geometry in 128 bits vs the code | 32-bit size wrap, stride wrap |
| Narrow parse equals wide parse and is in range | integer parser disagreements |
| Differential against libc (`strtof`, `strtod`) | float parser and formatter UB |
| Reference implementation (standard library semantics) | `substr` wrap, empty `rfind` |
| Peer plays the other side of a ring or link | OOB reads/writes, endless `poll()` |
| Differential against a reference library (Hypothesis) | dropped content, mis-split keys |

A property must be exact where the code is exact and carry a documented tolerance where it
is not.

## When one bug blocks exploration

Add a compile-time skip switch, **default off**, documented in the header, so the other
properties keep running while the bug waits for its fix. Pass it as `-D<SKIP_FLAG>=1` in a
scratch build, never in a preset. A known issue that the harness does not check is stated in
a comment, never left implicit.

## Corpus rules

- Valid seeds are small and few (`seed_*`); reproducers of fixed bugs are `repro_*`; minimised
  inputs `min_*`.
- A seed that crashes unfixed code goes in with the fix, never with the harness alone: the
  replay test runs in every build.
- Corpus files are read-only inputs; libFuzzer writes new inputs to the build tree.
