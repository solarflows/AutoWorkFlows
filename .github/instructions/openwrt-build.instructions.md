---
description: "修改 OpenWrt/ImmortalWrt GitHub Actions 构建、缓存、SDK、ImageBuilder、固件发布或错误诊断时使用。"
applyTo: ".github/workflows/**"
---

# OpenWrt Build Workflows

## Architecture

- `firmware-build.yml` is the orchestrator. Its `plan` job owns trigger, version, change-detection, cache, build, and publish decisions.
- `compile-firmware.yml`, `compile-packages.yml`, and `repack-imagebuilder.yml` are reusable executors; do not add fallback or escalation decisions to them.
- Keep `run-firmware`, `run-imagebuilder`, and `run-packages` controlled by explicit `plan` outputs; `release` publishes only after a planned task succeeds.

## Required Behavior

- A job that needs a skipped job is skipped implicitly. Do not place a possibly skipped job in `needs`; use `always()` with explicit `needs.<job>.result` checks when its result is required.
- Do not export generic workflow, job, or shell environment variables named `TARGET`, `HOST`, or `BUILD`. Use scoped inputs such as `matrix_target` inline or domain-specific names.
- Keep cache strategies `smart`, `clean-toolchain`, `clean-ccache`, `clean-all`, and `no-cache` behaviorally distinct.
- In `no-cache` mode, do not export ccache `CC` or `CXX` wrappers. Configure ccache unconditionally when ccache is enabled, but export wrappers only when the selected strategy permits them.
- Store SDK and ImageBuilder versions under `sdk-<target>` and `ib-<target>` release tags. Replace same-version files and retain the configured number of distinct versions.
- Keep version sorting numeric and aware of SNAPSHOT and `V<n>` tokens.

## Diagnostic Invariants

- Preserve four-stage disk monitoring and its summary deltas.
- Preserve build-log counts, incomplete and empty log detection, and the slowest-build summary.
- Preserve automatic failed-package diagnostics and include `.config` in failure artifacts.
- Move first-pass `logs` to `logs.1`; never delete the evidence before the single-thread retry.
- Keep the `make -j1 V=sc -k` retry for complete configure and compiler diagnostics.
- Preserve ccache statistics and cleanup, release-root listings, and diagnostic verification steps that intentionally use `continue-on-error`.
- Keep feed updates fail-fast with `set -euo pipefail`.
- Preserve the established numbered step names and diagnostic heading format unless the workflow presentation is intentionally redesigned.

See `docs/openwrt-build-pitfalls.md` for verified root causes and investigation evidence.