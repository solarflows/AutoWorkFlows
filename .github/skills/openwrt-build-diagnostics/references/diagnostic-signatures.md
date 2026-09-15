# Diagnostic Signatures

## `time:` Line Cannot Identify Failed Packages

Evidence:

- A failed `compile.txt` ends with `time: package/.../compile#...`
- A job or summary claims no failed package was found, but the build clearly failed

Interpretation: `scripts/time.pl` prints its timing line **regardless of the command's exit status** — it computes the elapsed time, prints `%s#%.2f#%.2f#%.2f\n`, and only then exits with the child's status. A failed build therefore also ends with a `time:` line. The authoritative failed-package source is `logs*/<pkg>/error.txt` (`ERROR: <pkg> failed to build.`). Treat the last-line check as a fallback for interrupted logs only.

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

## Non-Executable `src/configure` Silently Skips Configure

Evidence:

- `make[4]: *** No targets specified and no makefile found. Stop.` in the compile phase, the only package with this signature in the whole build
- First-pass `compile.txt` shows patch + autoreconf, then jumps straight to `make[4]` with no `checking for...` configure output
- The package Makefile has no `PKG_SOURCE_URL`; sources come from the repository `src/` directory (`unpack.mk` treats an empty `PKG_SOURCE` as `PKG_UNPACK=true`; `package-defaults.mk` copies `src/.` into the build dir)
- `src/configure` is mode 100644 in the feed git tree (verify via the GitHub trees API)

Interpretation: `Build/Configure/Default` guards on `if [ -x ./configure ]`; a non-executable configure is silently skipped (no output, exit 0, `.configured` stamp still created), so the compile phase finds no Makefile. With `PKG_FIXUP:=autoreconf`, the root `autoconf` step can also be skipped when a quilt patch re-touches the configure file (`|| true` swallows the error), so the stale configure is never regenerated. `chmod +x` alone is insufficient if the configure content is stale (e.g. pcre v1 detection while the dependency is `+libpcre2`): it then fails with a visible configure error. Fix: register a `Hooks/Prepare/Post` in the package Makefile that removes `$(PKG_BUILD_DIR)/configure` after quilt applies all patches, forcing autoreconf to regenerate from `configure.ac` (correct content, executable bit set by autoconf). Do not delete `src/configure` in the feed directly: the 0001 quilt patch patches that file during the build, so removal breaks patch application. Verified case: run 31559354153 (mt798x), package `shadowsocksr-libev` from `Openwrt-Passwall/openwrt-passwall-packages`.

## Toolchain Rebuild Despite Cache Hit

Evidence:

- `Restore toolchain cache` logs `Cache restored from key: immwrt-v2-toolchain-...` (a real hit, not a prefix miss)
- The `Prepare toolchain & ccache` step still shows `make[2] -C tools/... compile` and `make[2] -C toolchain/... compile` lines and takes tens of minutes
- Warm-cache and cold-run `Prepare` durations are comparable (verified run 34805493661: ipq807x 40m 28s warm vs 46m 37s cold; GCC 14 targets are worst)

Interpretation: a restored toolchain cache contains only `staging_dir/host*` + `staging_dir/tool*`, not `build_dir/`, where each host tool's `.built` marker lives (`HOST_STAMP_BUILT` in `include/host-build.mk`). Running a subdirectory goal (`make tools/compile toolchain/compile`) bypasses the top-level `$(tools/stamp-compile)` / `$(toolchain/stamp-compile)` gate, so make checks every tool's `.built` dependency against the empty `build_dir` and rebuilds the whole toolchain. Only the default `make` goal (`world` → `prepare`) consults the stamps via `timestamp.pl` and skips the whole subtree in seconds. Fix direction: never call subdirectory goals on warm cache; rely on top-level stamps; build only `tools/ccache/compile` when `staging_dir/host/bin/ccache` is genuinely missing.

## Recursive `dl` Cleanup Corrupts Go/Rust Module Caches

Evidence:

- Go packages fail with `pattern <file>.binpb: no matching files found` inside `dl/go-mod-cache/<module>@<version>/` (verified: protobuf `editions_defaults.binpb`, run 34940720655)
- Rust fails with `failed to calculate checksum of: .../vendor/<crate>/Cargo.toml.orig` / `No such file or directory` (verified: `cc-1.2.28`)
- Failures cluster on Go/Rust-heavy packages (`sing-box`, `hysteria`, `v2ray-plugin`, `xray-core`, `geoview`, `rust [host]`) while C/C++ packages in the same run succeed

Interpretation: a residual download cleanup ran `find dl -size -1024c` without `-maxdepth`, recursing into `dl/go-mod-cache` and `dl/cargo` (shared module caches that contain many legitimate sub-1KB files: Go `//go:embed` assets, cargo checksum companions). Each loop iteration re-deletes, so one retry poisons every later Go/Rust package. Scope such cleanups to `find dl -maxdepth 1 -type f -size -1024c`.