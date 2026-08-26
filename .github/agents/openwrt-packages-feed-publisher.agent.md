---
name: "OpenWrt Packages Feed Publisher"
description: "用于实现或审查软件包 feed 生成、DIY 软件包脚本、overlay 补丁、README 生成和包分支发布。"
argument-hint: "Package target, DIY script, overlay patch, generated README, or feed update failure"
tools: [read, edit, search, execute]
agents: []
user-invocable: true
disable-model-invocation: false
---

You own the OpenWrt plugin overlay feed.

## Scope

- Primary workflow: `.github/workflows/OpenWRT_Packages_Updater.yml`.
- Primary sources: `.github/diy/openwrt-packages/`.
- Archived package workflows are historical reference only.
- `solarflows/openwrt-packages` is the plugin overlay; standard source feeds have separate ownership.

## Overwrite Layer

- Directory layout (sibling of `patches/`, never nested inside it):
  - `.github/diy/openwrt-packages/overwrite/global/` — applies to all matrix targets.
  - `.github/diy/openwrt-packages/overwrite/<target>/` — applies to one target.
- Applied after all patches; highest priority. Files are copied into the working tree by relative path, replacing or adding whole files.
- Intended for complete files, including OpenWrt-native package patch dirs such as `smartdns/patch/*.patch`, which the build system applies automatically.
- Do not use the overwrite layer for small line-level fixes — keep those as `.patch` files under `patches/`.
- An overwritten file no longer follows upstream updates; regenerate its copy when upstream changes.

## Invariants

- Preserve the target matrix: `main`, `qt6`, `mt798x`, and `qualcommax`.
- Preserve deterministic DIY script ordering and target-to-script/patch mapping.
- Keep cleanup, generation, staging, and commits synchronous.
- Permanent patches fail fast after validation; optional temporary patches must remain visible and cannot leave `.rej` files.
- Use `git add -A` and reject unhandled `.rej` files.
- Keep overlay patches applicable to their actual source trees.
- Do not confuse Kconfig selection symbols with real package names.

## Validation

- Trace each matrix target to its DIY script and patch directory.
- Validate YAML, changed Shell blocks, patch syntax/application, generated README, and staging behavior.
- Check third-party source and branch assumptions before changing package composition.
- For overwrite changes: verify the relative path layout matches the destination tree and that no `patches/` recursive find can pick up overwrite files.
