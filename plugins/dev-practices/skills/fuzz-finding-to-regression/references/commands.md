# Commands for a fuzz finding

Generic libFuzzer and sanitizer commands. Replace `<build>` with the project's build directory
and `<name>` with the fuzz target; the project's `AGENTS.md`, `README` or build presets name the
real build and test commands. Run from the repository or worktree root, and make sure the build
directory belongs to this checkout.

## Build

Build the fuzz target with Clang and `-fsanitize=fuzzer,address,undefined`, and build the
replay binary (a plain `main()` that feeds files to the same entry point) with every compiler
the project supports.

## Reproduce

```bash
B=<build>/fuzz
$B/<name>_replay $B/artifacts/<name>-crash-<hash>          # replay binary, plain main()
$B/<name>_fuzzer -runs=1 $B/artifacts/<name>-crash-<hash>  # libFuzzer, full report
```

A hang never returns from the replay binary: wrap it in `timeout 10`. For a manual run use
`-close_fd_mask=3` to avoid multi-gigabyte logs; it also closes stderr, so replay the saved
file to read the sanitizer report.

## Minimise

```bash
ASAN_OPTIONS=dedup_token_length=3 $B/<name>_fuzzer -minimize_crash=1 -runs=100000 \
    -exact_artifact_path=/tmp/min-crash <crash-file>
$B/<name>_replay /tmp/min-crash
```

Use a delta script (drop chunks, keep the input only when the replay output still contains the
original sanitizer message and top project frame) for hangs and property traps.

## Run the fuzzer by hand

```bash
$B/<name>_fuzzer $B/corpus/<name> <checked-in-corpus>/<name> \
    -max_total_time=600 -timeout=2 -close_fd_mask=3 -print_final_stats=1 \
    -artifact_prefix=$B/artifacts/<name>-
```

The first directory receives new inputs; the checked-in corpus stays read-only. To collect many
crashes in one run add `-fork=2 -ignore_crashes=1`.

## Replay all saved crashes, then a fresh run

One replay invocation takes many files and exits non-zero at the first failing one.

```bash
for t in <name1> <name2>; do
    ls $B/artifacts/$t-* >/dev/null 2>&1 && timeout 600 $B/${t}_replay $B/artifacts/$t-*
done
```

Then rerun the affected fuzzer for 10 minutes. The seed corpus should also replay as ordinary
tests in the project's test suite.

## Regression test and reverted-fix check

```bash
<run the new test>                                   # passes with the fix
git checkout <base> -- <fixed-source-file>           # restore the UNFIXED source only
<rebuild and rerun the new test>                     # must FAIL
git checkout HEAD -- <fixed-source-file>             # back to the fix; rebuild and rerun
```

Do not use bare `git stash` (the stash stack is shared between worktrees). Use the paths of
the files the fix changed, and keep the test and seed files in place.

## Configurations to run before handing over

Run the project's test workflow under each supported compiler and sanitizer: GCC with
ASan+UBSan, Clang with the fuzz targets, and TSan with a stress loop for threaded code. A new
threaded test must match any name filter the TSan stress configuration uses.

## Static analysis

Run clang-tidy on the changed files with the project's wrapper or `run-clang-tidy`, with
warnings as errors as in CI. Harness files are linted too. To look for the pattern behind a
finding, survey extra checks (`bugprone-*,clang-analyzer-*`) in report-only mode and enable a
check by name only when the survey is clean.

## Python findings (Hypothesis)

Run the project's property-based tests with its test runner. The profile should be
derandomized so CI runs repeat. A disagreement that is a matter of policy (inf, nan, Unicode
digits, escapes in quoted strings) is recorded as an expected failure with the reason, not
"fixed".
