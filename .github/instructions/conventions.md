---
description: AutoWorkflows 仓库约定（seed 文件编码、配置结构、构建产物、代理等）。编辑本仓库任何文件前请遵守。
applyTo: "**"
---

# AutoWorkflows Repo Conventions

## Seed config files (openwrt-configs/)

- Files must use **LF line endings + no BOM** (`.gitignore` enforces `eol=lf working-tree-encoding=UTF-8`).
- Structure: `<target>/NN-*.seed` merged in numeric order (01-base → 02-pkgs → 03-mtk → 04-passwall → 05-extras);
  workflows merge them via `find | sort` into `.config`.
- Key switches: `CONFIG_SDK=y` (produces SDK), `CONFIG_IB=y` (produces ImageBuilder),
  `CONFIG_CCACHE=y` (ccache controlled by seed; wrapper layer controlled by workflow), `CONFIG_BUILD_LOG=y` (generates logs/).
- Each target directory has a companion `sdk.config` (trimmed config for SDK builds).

## targets.json (openwrt-configs/)

- Fields: `target` / `repo` / `ref` / `config` / `apk_signing` / `sdk_release_tag` / `ib_release_tag`, etc.
- Key note: `src-git packages` points to `solarflows/packages.git;hanwckf` (mt798x) — libffi comes from this feed; see openwrt-build.md pitfall #2.

## Build artifact naming

- SDK: `sdk-<target>-<version>-<arch>.tar.xz`; IB: `ib-<target>-<version>-<arch>.tar.xz`.
- `<version>` comes from `include/version.mk` `VERSION_NUMBER` (appends date when SNAPSHOT).
- Firmware tarball: `<target>-release.tar.gz` (release/firmware + release/passwall).
- passwall dependency chain (DEPS array) must match sdk.config's `CONFIG_PACKAGE_*=y`:
  chinadns-ng/dns2socks/geoview/.../xray-core (passwall2 additionally requires v2ray-geoip/v2ray-geosite).

## CI secrets

- Workflows use `secrets.ACCESS_TOKEN` (GH_TOKEN env) for GitHub API calls.

## Archives

- Deprecated workflows go into `.github/archive/workflows/` — do not delete directly (preserve audit trail).
