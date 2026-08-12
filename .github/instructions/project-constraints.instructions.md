---
description: "AutoWorkflows 项目特有的约束、已知陷阱和经验教训。处理本项目的任何文件时优先加载。"
---

# AutoWorkflows Project Constraints

## Environment Variable Restrictions

Never export variables named `TARGET`, `HOST`, or `BUILD` in GitHub Actions workflows. They leak into the OpenWrt build environment and break package compilation (particularly libffi and other autoconf-based packages).

Use scoped alternatives:
- `FIRMWARE_TARGET` or `matrix_target` instead of `TARGET`
- `BUILD_HOST` instead of `HOST`
- `BUILD_TYPE` instead of `BUILD`

Verification: When a build fails, check `logs/package/<pkg>/compile.txt` for `checking host system type` or `checking target system type`. If output contains workflow variable values, environment leakage occurred.

Reference: [docs/openwrt-build-pitfalls.md](../docs/openwrt-build-pitfalls.md) § TARGET 环境变量泄漏

## Known Package Build Traps

### libffi (mt798x)

libffi fails repeatedly under certain cache strategies with `configure: error: cannot run C compiled programs`. The mt798x feed (`solarflows/packages;hanwckf`) contains a libffi package extremely sensitive to `TARGET`/`HOST` environment variables.

Mitigation:
- Clear toolchain stamps when using `clean-toolchain` or `clean-all` strategies
- Ensure no forbidden environment variables are exported in workflows
- Use `make -j1 V=sc` retry for complete diagnostic output

Reference: [docs/openwrt-build-pitfalls.md](../docs/openwrt-build-pitfalls.md) § libffi 构建失败

## Build System Behavior

### Single-thread retry (logs.1)

Multi-threaded builds (`-j$(nproc)`) produce interleaved logs difficult to diagnose. On failure, workflows move `logs/` to `logs.1/` as evidence, then retry with `make -j1 V=sc -k` to produce complete configure and compiler output in a new `logs/`. Both log sets are uploaded to artifacts. Never delete `logs/` or `logs.1/` before retry completes.

### Optional diagnostic pipelines

Diagnostic commands in `set -euo pipefail` steps that use pipes must end with `|| true` to prevent SIGPIPE 141 from terminating the step.

Correct: `find build_dir -maxdepth 3 -type d | head -50 || true`
Wrong: `find build_dir -maxdepth 3 -type d | head -50` (SIGPIPE kills the step)

## Workflow Infrastructure

### Build state persistence

Store last build commit SHA and artifact versions in the `IMMWRT_BUILD_STATE` repository variable using `secrets.ACCESS_TOKEN` (PAT). `GITHUB_TOKEN` cannot write repository variables. This avoids per-run cache keys that accumulate and exhaust the 10 GB cache quota.

### Concurrency control

Use the fixed global concurrency group `firmware-build-v2` for compatibility with the existing concurrency namespace. Never scope by branch or PR (`firmware-build-${{ github.ref }}`). Parallel runs would write the same `artifacts-<target>` release tag simultaneously, causing artifact corruption and race conditions.

### Authentication

- `secrets.ACCESS_TOKEN`: GitHub PAT for repository variable writes and cross-repo operations
- `GH_TOKEN` env var: Set via `env: GH_TOKEN: ${{ secrets.ACCESS_TOKEN }}` for `gh` CLI

## Diagnostic Workflow

On build failure, follow this investigation sequence:

1. Check [docs/openwrt-build-pitfalls.md](../docs/openwrt-build-pitfalls.md) for known failure signatures
2. Run `openwrt-build-diagnostics` skill for read-only analysis
3. Check `logs/package/error.txt` and `logs.1/package/error.txt`
4. Check `logs.1/<pkg>/compile.txt` for complete single-thread retry output
5. Search workflows for `TARGET=`, `HOST=`, `BUILD=` export statements
6. Review `ccache -s` output in build steps

## Configuration Conventions

### Seed file merge order

- mt798x: `01-base` → `02-pkgs` → `03-mtk` → `04-passwall` → `05-extras`
- qualcommax: `01-base` → `02-pkgs` → `03-passwall` → `04-extras`

`03-mtk.seed` contains closed-source MTK Wi-Fi drivers and must remain stable.

## Related Documentation

- [.github/instructions/openwrt-build.instructions.md](openwrt-build.instructions.md) — Workflow architecture and diagnostic requirements
- [.github/instructions/openwrt-config.instructions.md](openwrt-config.instructions.md) — Configuration file format and constraints
- [.github/instructions/build-artifacts.instructions.md](build-artifacts.instructions.md) — Artifact naming and release management
- [docs/openwrt-build-pitfalls.md](../docs/openwrt-build-pitfalls.md) — Verified failure patterns and root cause analysis
- [.github/skills/openwrt-build-diagnostics/SKILL.md](../skills/openwrt-build-diagnostics/SKILL.md) — Diagnostic skill definition
