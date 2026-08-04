# AGENTS.md — AutoWorkflows

Automated CI/CD workflows for [solarflows/openwrt-packages](https://github.com/solarflows/openwrt-packages): plugin collection, ImmortalWrt firmware builds, and upstream sync.

## Directory Map

| Path | Purpose |
|:-----|:--------|
| `.github/workflows/` | GitHub Actions workflows (orchestrator + reusable executors) |
| `openwrt-configs/immortalwrt/` | Build target configs (seed files, sdk.config, targets.json) |
| `.github/instructions/` | File-scoped Agent behaviour rules |
| `.github/skills/` | Agent skill definitions (build diagnostics) |
| `docs/` | Pitfall records and root-cause analysis |
| `scripts/` | Helper scripts and build-log samples |

## Core Architecture

### Decision vs. Execution

The `plan` job in `firmware-build.yml` owns all decisions: trigger mode, change detection, versioning, cache strategy. The three reusable workflows (`compile-firmware.yml`, `compile-packages.yml`, `repack-imagebuilder.yml`) only execute. **Never add fallback or escalation logic to reusable workflows.**

### Workflow ↔ Target Separation

`targets.json` stores only per-target deltas. Defaults live in the workflow `env` block and `inputs.default`. There is no `defaults` JSON block — jq fills missing fields via `//`. See [`openwrt-configs/immortalwrt/README.md`](openwrt-configs/immortalwrt/README.md).

### Two Hardware Platforms

| | mt798x | qualcommax |
|:--|:--|:--|
| SoC | MT7981 (Filogic 820) | IPQ60xx |
| ImmortalWrt branch | 21.02 | SNAPSHOT (main) |
| Package / firewall | IPK + iptables | APK + nftables |
| Storage | NAND-constrained → slim backends | Ample → full preinstall |

Platform differences are encoded in the respective seed directories.

## Modifying Build Configs

When editing files under `openwrt-configs/immortalwrt/`:
- **Seed files** (`NN-name.seed`) are concatenated in numeric filename order to produce `.config`; must be UTF-8 without BOM, LF line endings
- **sdk.config** is for SDK incremental builds only; write `CONFIG_PACKAGE_*=y`, never `INCLUDE_*`
- The MTK closed-source Wi-Fi driver seed (`03-mtk.seed`) must not be modified casually
- See [`.github/instructions/openwrt-config.instructions.md`](.github/instructions/openwrt-config.instructions.md)

## Modifying Workflows

When editing files under `.github/workflows/`:
- **Never** export variables named `TARGET`, `HOST`, or `BUILD` (they leak into the build environment and break packages like libffi). Use `matrix_target` or `FIRMWARE_TARGET`
- If job A's `needs` includes a job B that may be skipped, always use `always()` + explicit `needs.<job>.result` checks
- Preserve diagnostic invariants: four-stage disk monitoring, `logs/` → `logs.1/` evidence retention, `make -j1 V=sc -k` single-thread retry
- See [`.github/instructions/openwrt-build.instructions.md`](.github/instructions/openwrt-build.instructions.md) and [`docs/openwrt-build-pitfalls.md`](docs/openwrt-build-pitfalls.md)

## Artifact Naming

- SDK: `sdk-<target>-<version>-<arch>.tar.xz`
- ImageBuilder: `ib-<target>-<version>-<arch>.tar.xz`
- Firmware: `<target>-release.tar.gz`
- Version source: `VERSION_NUMBER` from `include/version.mk`; append date for SNAPSHOT
- See [`.github/instructions/build-artifacts.instructions.md`](.github/instructions/build-artifacts.instructions.md)

## Build Diagnostics

On build failure, use the `openwrt-build-diagnostics` skill for read-only diagnosis. Do not modify workflows or configs directly. The skill analyzes `error.txt`, `compile.txt`, `logs.1/`, and produces an evidence-backed report.

## General Conventions

- Move deprecated workflows to `.github/archive/workflows/` instead of deleting them
- GitHub API operations use `secrets.ACCESS_TOKEN` via `GH_TOKEN` env variable
- Workflow triggers: `workflow_dispatch` (manual) + `schedule` (cron)
