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

The `plan` job in `firmware-build.yml` owns all decisions: trigger mode, change detection, versioning, cache strategy. The three reusable workflows (`compile-firmware.yml`, `compile-packages.yml`, `build-via-ib.yml`) only execute. **Never add fallback or escalation logic to reusable workflows.**

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

See [`.github/instructions/openwrt-config.instructions.md`](.github/instructions/openwrt-config.instructions.md) for seed file format, sdk.config usage, and target configuration rules.

## Modifying Workflows

See [`.github/instructions/openwrt-build.instructions.md`](.github/instructions/openwrt-build.instructions.md) and [`docs/openwrt-build-pitfalls.md`](docs/openwrt-build-pitfalls.md) for workflow architecture, diagnostic requirements, and verified failure patterns.

## Artifact Naming

See [`.github/instructions/build-artifacts.instructions.md`](.github/instructions/build-artifacts.instructions.md) for SDK, ImageBuilder, and firmware naming conventions, checksum format, and release management.

## Build Diagnostics

On build failure, use the `openwrt-build-diagnostics` skill for read-only diagnosis. Do not modify workflows or configs directly. The skill analyzes `error.txt`, `compile.txt`, `logs.1/`, and produces an evidence-backed report.

Before investigating, check `docs/openwrt-build-pitfalls.md` and the skill's `references/diagnostic-signatures.md` for a known signature (e.g. `TARGET` env leakage, libffi, stamp-skipped retry, ccache mismatch). Reuse the verified root cause instead of re-deriving it.

## General Conventions

- Move deprecated workflows to `.github/archive/workflows/` instead of deleting them
- GitHub API operations use `secrets.ACCESS_TOKEN` via `GH_TOKEN` env variable
- Workflow triggers: `workflow_dispatch` (manual) + `schedule` (cron)
