---
description: OpenWrt/ImmortalWrt 构建工作流的刻意设计与已知坑位（libffi、needs 隐式跳过、SDK/IB 版本保留、诊断设计意图）。修改 .github/workflows/*.yml 前必读。
applyTo: ".github/workflows/**"
---

# OpenWrt Build Workflows — Design Intent & Known Pitfalls

> This file documents **deliberate design decisions** (so maintainers don't mistakenly remove them)
> and **verified pitfalls** (so we don't repeat them). Read before editing any workflow.

## Architecture (v2, refactored 2026-08)

- `firmware-build.yml` = orchestrator: `plan` job makes all decisions (trigger / version / change detection / cache strategy),
  outputs `should_build_*` / `should_publish_*` flags; `run-firmware` / `run-imagebuilder` / `run-packages`
  are three reusable execution jobs; `release` publishes at the end.
- `compile-firmware.yml` (reusable) = full firmware build + SDK/IB tarball upload to Release.
- `compile-packages.yml` (reusable) = compile packages using published SDK.
- `repack-imagebuilder.yml` (reusable) = repack using published IB.
- Principle: **all decisions in plan**; reusable workflows only execute — no fallback or escalation logic.

## Known Pitfalls (verified)

### 1. GitHub needs implicit skip (2026-08-03)
- If job A's `needs` includes job B and B is skipped, GitHub **implicitly skips A**
  (even if A's `if` is true), unless `if` uses `always()` style.
- Fix: `run-firmware` must use `needs: plan` + `if: should_build_firmware == 'true'` —
  **never** put a possibly-skipped job in `needs`.
- Lesson: use `if: always()` style + `needs.X.result` when you need another job's result; don't depend directly.

### 2. `env: TARGET` pollutes autoconf → libffi InstallDev fails (2026-08-04, fixed)
- **Forbidden** bareword uppercase env names with autoconf reserved semantics in workflow/job/step `env`:
  `TARGET` `HOST` `BUILD` `ARCH` `CC` `CXX` `CFLAGS` `LDFLAGS` `PREFIX` `VERSION` `PACKAGE` `SUB` `SED` `MAKE` `SHELL`.
  These propagate into every package's `./configure` via `make`.
- Case: v2 once set `env: TARGET: mt798x`. libffi 3.3's `AX_ENABLE_BUILDDIR` macro:
  `test ".$TARGET" = "." && TARGET="$target"` → `SUB="$TARGET"` → build tree goes to
  `libffi-3.3/mt798x/` instead of `libffi-3.3/aarch64-openwrt-linux-gnu/`.
  But Makefile's `Build/InstallDev` hardcodes `$(PKG_BUILD_DIR)/$(GNU_TARGET_NAME)/fficonfig.h`.
- Symptom: `cp: cannot stat '.../libffi-3.3/aarch64-openwrt-linux-gnu/fficonfig.h'`,
  while compile itself succeeded (`.so`/`.a`/`.pc` all installed). v1 has no such env, so only v2 repros.
- **Diagnosis**: grep `continue configure in default builddir` in `logs.1/**/compile.txt`;
  if parenthesis contains custom value instead of `$host` triplet → env pollution.
  Retry-round compile.txt being tiny (0.2s) is because configure/compile stamps exist,
  make jumps straight to InstallDev and fails again — not "stamp skipped".
- Fix: v2 unified to `IMMWRT_TARGET` prefix. Self-check against reserved list before adding new job-level env.

### 3. Cache strategy & ccache (refactored 2026-08)
- v1/v2 cache keys must be fully isolated: v1 uses `immwrt-toolchain-` / `immwrt-ccache-` / `immwrt-state-`,
  v2 uses `immwrt-v2-toolchain-` / `immwrt-v2-ccache-` / `immwrt-v2-state-`.
  `gh cache delete --key` is **prefix match** — v2's earlier `immwrt-state-v2-` got wiped by v1's `immwrt-state-` purge.
  Put every new cache key under the `immwrt-v2-` namespace and keep the monthly-flush prefix list in sync.
- `cache_strategy` options: `smart` / `clean-toolchain` / `clean-ccache` / `clean-all` / `no-cache`.
- no-cache = skip all ccache wrapping + cache restore/stats/cleanup; used to verify "is cache to blame?".
- ccache config must run **unconditionally** (`--max-size 10G` + compiler_check=content etc.);
  only `CC`/`CXX` export is conditional — this is a v1 deliberate design, once mistakenly removed causing half-broken env.

### 4. SDK/IB version retention (v2 new)
- Stored as release tags (`sdk-<target>` / `ib-<target>`) with `index.json` tracking.
- Same-version files: `--clobber` replace. Different versions: keep latest `SDK_KEEP_VERSIONS`/`IB_KEEP_VERSIONS` (default 7) groups.
- Version sort must be robust: numeric fields by value, SNAPSHOT→-1, `V<n>` parsed as number (`vtok` function).

## Deliberate design (do not remove)

| Step / logic | Why it's deliberate |
|---|---|
| job env named `IMMWRT_TARGET`, not `TARGET` | Bare name pollutes autoconf configure (pitfall §2) — never revert |
| 4-stage disk monitoring (disk-1~4) + Summary delta table | Diagnoses low space / cache bloat; per-stage delta pinpoints the spike |
| Build Log Analysis (compile.txt total/incomplete/empty + Top5 duration) | Locates compile bottlenecks |
| Build Error Diagnostics (auto-find failed packages) | Last line without `time:` marks failure — no manual build.log digging; prefers error.txt |
| Failure artifact includes `.config` | Reproducing a failure requires the final config |
| `mv logs logs.1` (not rm) | Preserves first-pass errors; retry pass may have a different context |
| Single-thread retry `make -j1 V=sc -k` | V=sc prints full compile commands so real configure errors aren't truncated |
| ccache Stats & Cleanup (hit rate / compression) | Key signal for "is the cache actually effective?" |
| Post-package `release/` tree listing (tree -L 1 / ls -al) | Fast manual sanity check of artifact completeness |
| release runs only when ≥1 planned job actually succeeded | Avoids idle runs + empty releases |
| Verify step `continue-on-error: true` | Diagnostic only; cache restore failure must not block the build |
| `set -euo pipefail` before feed updates | No silent error suppression (global rule) |

## Conventions

- No silent errors: `|| true`, `2>/dev/null` swallowing real failures, dropping PIPESTATUS, deleting logs.
- Every `||` fallback prints why it failed (`echo "⚠️ xxx failed: $?"`).
- Step names carry emoji + number (v1 legacy); key steps use a `╔═╗` banner.
