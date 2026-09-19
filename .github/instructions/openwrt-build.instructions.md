---
description: "修改 OpenWrt/ImmortalWrt GitHub Actions 构建、缓存、SDK、ImageBuilder、固件发布或错误诊断时使用。"
applyTo: [".github/workflows/compile-*.yml", ".github/workflows/firmware-build-unified.yml"]
---

# OpenWrt Build Workflows

## Architecture

- `firmware-build-unified.yml` is the only active orchestrator. Its `plan` job owns trigger, version, change-detection, cache, build, and publish decisions.
- `compile-firmware.yml` and `compile-packages.yml` are the active reusable executors; do not add fallback or escalation decisions to them.
- Keep `run-firmware`, `run-sdk-ib`, and `run-packages` controlled by explicit `plan` outputs. `run-sdk-ib` uses `compile-packages.yml` with `matrix_build_sdk_ib=true`.

## Required Behavior

- A job that needs a skipped job is skipped implicitly. Do not place a possibly skipped job in `needs`; use `always()` with explicit `needs.<job>.result` checks when its result is required.
- Do not export generic workflow, job, or shell environment variables named `TARGET`, `HOST`, or `BUILD`. Use scoped inputs such as `matrix_target` inline or domain-specific names.
- Keep cache strategies `smart`, `clean-toolchain`, `clean-ccache`, `clean-all`, and `no-cache` behaviorally distinct.
- Save the current toolchain and ccache snapshots only after the build has succeeded; a failed build must not replace an existing cache. Save the current key before purging old entries, and exclude the current key from purge. This keeps a usable old cache if save or purge fails.
- After a successful save, purge all older entries for the current target under `immwrt-v2-toolchain-<target>-*` and `immwrt-v2-ccache-<target>-*`. The v2 policy is latest-only per target; it does not clean v1 or unrelated workflow caches.
- Give every cache namespace a bounded retention limit; never leave a rolling per-run namespace unbounded. `immwrt-v2-toolchain-<target>-*` and `immwrt-v2-ccache-<target>-*` keep only the latest snapshot per target, and whoever writes `immwrt-v2-sdk-hostpkg-<target>-<run_id>` (full executor or SDK path) must converge that namespace to the newest single snapshot for its target, so a full-build-only period cannot grow it. GitHub's own eviction is *not* the reason: on overage it saves the new cache first and then evicts by last-access, oldest first, which on run 35313768877 removed exactly the previous generation's never-read `sdk-hostpkg` snapshots (3.10GB) — the same set a latest-only policy deletes. The reason for writer-side purging is control: it frees space in a step we own, keeps the "purge only after the new snapshot is saved" fallback, and stops eviction from having to choose at all — because when the stale generation is too small (or absent, e.g. after 7-day expiry) the next candidates are the toolchain snapshots, at a 40-minute rebuild cost.
- The toolchain snapshot key is content-addressed (`tools`/`toolchain` tree hash). When that exact key already exists, skip the save instead of letting it fail with `Unable to reserve cache ...` (Actions Cache keys are immutable); the purge step must still treat the existing snapshot as usable rather than requiring the save step's outcome.
- Both executors restore and save the shared `immwrt-v2-ccache-<target>-<run_id>` namespace and purge older snapshots down to the latest one per target; `source_sha` is artifact/SDK-IB matching metadata, not part of the SDK hostpkg key.
- The `plan` job routes every non-`smart` cache strategy to the full-build executor. Executors retain the cache operations for the selected strategy: restore, save, and purge happen in the reusable workflows after `plan` has made the routing decision.
- 工具链缓存命中时禁止显式调用 `make tools/compile toolchain/compile` 或其它子目录目标：工具链缓存只含 `openwrt/staging_dir/host*` 与 `openwrt/staging_dir/tool*`，而各 host 工具的 `.built` 标记位于 `build_dir/`（`include/host-build.mk` 的 `HOST_STAMP_BUILT`）。显式传入子目录目标会绕过顶层 stamp 守门（`timestamp.pl` 不再运行），make 转而逐工具检查 `build_dir` 中缺失的 `.built`，使缓存命中时仍全量重编（实测 warm-cache 的 `Prepare` 步骤在 GCC 14 目标上仍耗 40+ 分钟）。工具链主体编译必须交由默认目标 `world` 调度；仅当 `staging_dir/host/bin/ccache` 缺失/不可执行时才允许显式 `make tools/ccache/compile` 以提供 ccache 命令。
- `dl/` 残损下载清理必须限定深度：使用 `find dl -maxdepth 1 -type f -size -1024c`，禁止递归。`dl/go-mod-cache`（Go module）与 `dl/cargo`（crate）内含大量合法的小于 1KB 的文件，递归删除会破坏 Go `//go:embed` 资源（如 protobuf `editions_defaults.binpb`）与 cargo checksum（`Cargo.toml.orig`），导致整批 Go/Rust 包编译失败。
- In `no-cache` mode, skip Actions Cache restore/save/purge. Do not export workflow-level ccache `CC` or `CXX` wrappers; configure ccache when available, and let in-build behavior follow the seed's `CONFIG_CCACHE`.
- Do not export `CC`/`CXX` wrappers at the workflow level at all: seeds set `CONFIG_CCACHE=y`, so `rules.mk` auto-wraps compiler commands (OpenWrt 21.02 设置 `TARGET_CC:=ccache_cc`，新版/SNAPSHOT 设置 `TARGET_CC:=ccache $(TARGET_CC)`)，且 `HOSTCC:=ccache $(HOSTCC)`。Environment `CC`/`CXX` exports are redundant and can leak the system `gcc` into packages that do not read `TARGET_CONFIGURE_OPTS`. The `no-cache` strategy therefore disables remote cache persistence without forcibly disabling the build system's native ccache setting.
- SDK 增量构建环境下：系统未全局安装 ccache 时，配置和统计命令必须显式定位 SDK 自带的 `staging_dir/host/bin/ccache`（或在 PATH 中探测），禁止假设系统 PATH 中存在裸 `ccache` 命令。
- Do not set ccache `compiler_check` via `--set-config`: `rules.mk` exports `CCACHE_COMPILERCHECK` and ccache resolves environment variables over config files, so the file value is silently ignored. Set only `hash_dir` and the currently validated `sloppiness` options in the workflow; do not force ccache compression because qualcommax may export `CCACHE_NOCOMPRESS`, and Actions Cache archive compression is independent. `base_dir` is exported natively by `rules.mk` (`CCACHE_BASEDIR=$(TOPDIR)`).
- Feed patches under `.github/diy/packages/patches/` (applied by `Sync_Push.yml` via `git apply`) must be validated with `git apply --check` before merging. Every content line inside a hunk must start with `+`, `-`, or a space; a missing `+` prefix on an added line makes `git apply` report `corrupt patch`. `Sync_Push.yml` is also triggered by `push.paths` on these patches — pushing a patch change re-runs the sync automatically.
- The SDK+IB path must build firmware per device: extract all device names from the seeds (`CONFIG_TARGET_(DEVICE_)?*_DEVICE_<name>=y`) and run `make image PROFILE=<name>` for each. Without `PROFILE`, `USER_PROFILE ?= $(firstword $(PROFILE_NAMES))` (imagebuilder `files/Makefile`) selects only the first device and `include/image.mk` (`DEVICE_CHECK_PROFILE`) disables the rest — mt798x would silently lose devices.
- Keep the global concurrency group `firmware-build-v2` fixed. Do not scope it per-ref; two parallel runs would write the same `sdk-*`/`ib-*`/`packages` tags and pollute remote repos.
- Store SDK and ImageBuilder versions under the shared `artifacts-<target>` release tag. Keep `sdk-index.json` and `ib-index.json` separate, replace same-version files, and retain the configured number of distinct versions for each artifact type.
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
- Optional diagnostic pipelines inside `set -euo pipefail` steps must end with `|| true` (SIGPIPE 141 when `head` truncates). Rationale, correct/wrong examples: `project-constraints.instructions.md` § Optional diagnostic pipelines.
- Cache cleanup is an observable operation: do not silence `gh cache list` / `gh cache delete` failures with `2>/dev/null` or bare `|| true`. Capture the list command's exit status, report failures on stderr, and skip deletion on list failure (an empty result is a normal rc=0 not-found, distinct from an execution error). Report delete failures explicitly.
- Preserve the established numbered step names and diagnostic heading format unless the workflow presentation is intentionally redesigned.

See `docs/openwrt-build-pitfalls.md` for verified root causes and investigation evidence.
