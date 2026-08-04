# Diagnostic Signatures

## Generic Environment Variable Leakage

Evidence:

- `continue configure in default builddir "./<matrix-target>"`
- `--enable-builddir=<matrix-target>`
- A workflow or process exports a generic `TARGET`, `HOST`, or `BUILD` value

Interpretation: an inherited environment variable changed Autoconf or another build tool's documented input. Verify the source environment before changing package code.

## libffi InstallDev Header Missing

Evidence:

- `cp: cannot stat .../<gnu-target>/fficonfig.h`
- First-pass configure selected a directory named after the firmware matrix target
- The retry `compile.txt` is very small or immediately reaches InstallDev

Interpretation: libffi generated `fficonfig.h` under the wrong build directory. In the verified mt798x case, job-level `TARGET=mt798x` overrode the expected Autoconf target directory.

## Stamp-Skipped Retry

Evidence:

- Retry log is much smaller than the matching first-pass log
- Retry reaches staging or InstallDev without configure and compile output
- `logs.1` contains the earlier configure or compiler activity

Interpretation: the retry reused stamps and does not contain the original cause. Diagnose `logs.1` first.

## ccache Environment Mismatch

Evidence:

- Wrapper variables remain exported while cache restore or ccache setup is disabled
- Compiler commands are unexpectedly double-wrapped
- An empty or incompatible cache coincides with wrapper configuration changes

Interpretation: inspect seed-level `CONFIG_CCACHE`, workflow wrapper export, restore behavior, and strategy selection independently. Do not infer causation from low cache hit rate alone.

## GitHub `needs` Skip

Evidence:

- A downstream job is skipped without running its own condition
- Its `needs` includes a job that was skipped

Interpretation: GitHub implicitly skips jobs that depend on skipped jobs. Use `always()` and explicit result checks only when that dependency result is required.