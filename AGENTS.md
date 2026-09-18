## Agent Routing

- Use `OpenWrt Build Orchestrator` for `firmware-build-unified.yml`, build planning, matrices, change detection, cache strategy, and build-state decisions.
- Use `OpenWrt Build Executor and Release` for `compile-firmware.yml`, `compile-packages.yml`, SDK/ImageBuilder, signing, diagnostics, and artifact publication.
- Use `Upstream Fork Sync` for `Sync_Push.yml`, source-fork synchronization, rebase, patch application, overwrite layers, and branch safety.
- Use `OpenWrt Packages Feed Publisher` for `OpenWRT_Packages_Updater.yml`, DIY package scripts, overlay patches, overwrite layers, and feed generation.
- Use `Geodata Release Publisher` for `v2ray-geodataUpdater.yaml`, geodata updates, checksums, and release assets.
- Use `openwrt-build-diagnostics` for real OpenWrt build logs and Actions build artifacts.
