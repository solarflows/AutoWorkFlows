## Project Status

- Before answering "is X implemented?", "wasn't this already fixed?", or proposing a change to an existing mechanism, read `docs/todo.md` — the single source of truth for feature status (✅/🟨/⬜/❓/🚫) with run/commit/file evidence. Do not re-derive status from workflow YAML.
- `🚫` rows must not be re-proposed without new evidence; `❓` rows continue from their listed options. Update the matching row in the same commit as any status change.
- Status flips (not new entries) also require one appended line in the `进展记录` section at the end of `docs/todo.md` (date + ID + old→new + evidence). New entries must fill the `P` column (P0/P1/P2 defined at the top of the ledger). Evidence arbitration (whether evidence qualifies for a status bump) is defined in the `improvement-ledger` skill.
- Keep the rule here only: this file is always loaded and inherited by custom agents, so do not copy it into other customization files.

## Agent Routing

- Use `OpenWrt Build Orchestrator` for `firmware-build-unified.yml`, build planning, matrices, change detection, cache strategy, and build-state decisions.
- Use `OpenWrt Build Executor and Release` for `compile-firmware.yml`, `compile-packages.yml`, SDK/ImageBuilder, signing, diagnostics, and artifact publication.
- Use `Upstream Fork Sync` for `upstream-sync.yml`, source-fork synchronization, rebase, patch application, overlay layers, and branch safety.
- Use `OpenWrt Packages Feed Publisher` for `custom-feed.yml`, declarative package manifests, overlay layers, and feed generation.
- Use `Geodata Release Publisher` for `geodata-updater.yml`, geodata updates, checksums, and release assets.
- Use `openwrt-build-diagnostics` for real OpenWrt build logs and Actions build artifacts.
