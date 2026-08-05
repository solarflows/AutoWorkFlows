---
description: "修改 OpenWrt/ImmortalWrt GitHub Actions 构建、缓存、SDK、ImageBuilder、固件发布或错误诊断时使用。"
applyTo: [".github/workflows/compile-*.yml", ".github/workflows/repack-*.yml", ".github/workflows/firmware-build.yml"]
---

# OpenWrt Build Workflows

## Architecture

- `firmware-build.yml` is the orchestrator. Its `plan` job owns trigger, version, change-detection, cache, build, and publish decisions.
- `compile-firmware.yml`, `compile-packages.yml`, and `build-via-ib.yml` are reusable executors; do not add fallback or escalation decisions to them.
- Keep `run-firmware`, `run-imagebuilder`, and `run-packages` controlled by explicit `plan` outputs; `release` publishes only after a planned task succeeds.

## Required Behavior

- A job that needs a skipped job is skipped implicitly. Do not place a possibly skipped job in `needs`; use `always()` with explicit `needs.<job>.result` checks when its result is required.
- Do not export generic workflow, job, or shell environment variables named `TARGET`, `HOST`, or `BUILD`. Use scoped inputs such as `matrix_target` inline or domain-specific names.
- Keep cache strategies `smart`, `clean-toolchain`, `clean-ccache`, `clean-all`, and `no-cache` behaviorally distinct.
- The toolchain cache save must run **after** the Purge step, never before: `actions/cache/save@v5` is a synchronous main step, so a purge that precedes the save can never delete the current run's just-built cache (the same ordering that makes combined `actions/cache@v5` post-action saves and ccache safe). A save placed before the purge lets a smart-mode miss branch delete the just-saved cache and prevent accumulation.
- In `smart` mode, cache cleanup must keep the most recent N versions (N=3) of `immwrt-v2-toolchain-<target>-*` and `immwrt-v2-ccache-<target>-*`; only `clean-all` / `clean-toolchain` / `clean-ccache` may delete them all.
- In `no-cache` mode, do not export ccache `CC` or `CXX` wrappers. Configure ccache unconditionally when ccache is enabled, but export wrappers only when the selected strategy permits them.
- Keep the global concurrency group `firmware-build-v2` fixed. Do not scope it per-ref; two parallel runs would write the same `sdk-*`/`ib-*`/`packages` tags and pollute remote repos.
- Store SDK and ImageBuilder versions under `sdk-<target>` and `ib-<target>` release tags. Replace same-version files and retain the configured number of distinct versions.
- Keep version sorting numeric and aware of SNAPSHOT and `V<n>` tokens.
- Match SDK/ImageBuilder artifacts with `*-sdk-*.tar.*` / `*-imagebuilder-*.tar.*` (upstream names are `<dist>-sdk-*` / `<dist>-imagebuilder-*`); strip the embedded version prefix with the non-dated `patched_version` (post-SNAPSHOT-substitution, the version the tarball was actually built with), never the dated `source_version`, when extracting the arch.
- Resolve the source version to a plain string before using it in shell scripts or `index.json` keys. `include/version.mk` may define `VERSION_NUMBER` as a make expression (`$(call qstrip,$(CONFIG_VERSION_NUMBER))` + a `$(if ...)` fallback); do not `grep`/`cut` that line directly — the expression would be injected into shell steps and fail with `command not found` (exit 127). Resolve in order: `.config`'s `CONFIG_VERSION_NUMBER`, then literal `VERSION_NUMBER:=`, then the `$(if ...)` fallback literal, then `SNAPSHOT`.
- Write SDK/ImageBuilder checksums as two-column `.sha256` (`<hash>  <filename>`) recomputed after rename; consumers run `sha256sum -c`, which fails on single-column hashes or filenames that do not match the downloaded file.
- Persist build state to the `IMMWRT_BUILD_STATE` repository variable, one copy, via `secrets.ACCESS_TOKEN` (PAT). `GITHUB_TOKEN` cannot write repository variables. Do not revert to per-run cache keys; they accumulate and consume the 10 GB cache quota. This rule targets **build-state** persistence; the ccache `run_id` key is cache data (cumulative compiler-object cache) using the platform's standard per-run-snapshot pattern, whose accumulation is bounded by the purge keep-most-recent-3 rule — not covered by this rule.

## Diagnosis First

- Before investigating a build failure, match the evidence against `docs/openwrt-build-pitfalls.md` and `openwrt-build-diagnostics`' `references/diagnostic-signatures.md`. Reuse the verified root cause instead of re-deriving it.
- Use the `openwrt-build-diagnostics` skill for read-only diagnosis before changing workflows or configs.

## Diagnostic Invariants

- Preserve four-stage disk monitoring and its summary deltas.
- Preserve build-log counts, incomplete and empty log detection, and the slowest-build summary.
- Preserve automatic failed-package diagnostics and include `.config` in failure artifacts.
- Treat `logs*/<pkg>/error.txt` as the authoritative failed-package source (`ERROR: <pkg> failed to build.`). Do not judge failure by whether a `compile.txt` ends with a `time:` line: `scripts/time.pl` prints that line regardless of the exit status, so failed logs also end with `time:`. Keep the last-line check only as a fallback for interrupted logs (e.g. OOM).
- Output failed-package logs in full instead of filtering or truncating; cap only oversized files (>300 KB) to their tail and point to the artifact.
- Move first-pass `logs` to `logs.1`; never delete the evidence before the single-thread retry.
- Keep the `make -j1 V=sc -k` retry for complete configure and compiler diagnostics.
- Preserve ccache statistics and cleanup, release-root listings, and diagnostic verification steps that intentionally use `continue-on-error`.
- Keep feed updates fail-fast with `set -euo pipefail`.
- Optional diagnostic pipelines (directory trees, listing probes) must end with `|| true` when placed inside `set -euo pipefail` steps: a `find | head -N` pipe returns SIGPIPE 141 when head truncates, and `set -e` would then fail the build step.
- Cache cleanup is an observable operation: do not silence `gh cache list` / `gh cache delete` failures with `2>/dev/null` or bare `|| true`. Capture the list command's exit status, report failures on stderr, and skip deletion on list failure (an empty result is a normal rc=0 not-found, distinct from an execution error). Report delete failures explicitly.
- Preserve the established numbered step names and diagnostic heading format unless the workflow presentation is intentionally redesigned.

See `docs/openwrt-build-pitfalls.md` for verified root causes and investigation evidence.