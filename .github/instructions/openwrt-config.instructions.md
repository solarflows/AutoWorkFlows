---
description: "修改 OpenWrt/ImmortalWrt seed、sdk.config、targets.json、目标配置或包依赖时使用。"
applyTo: "openwrt-configs/**"
---

# OpenWrt Configuration

- Keep seed files UTF-8 without BOM and with LF line endings.
- Merge `<target>/NN-*.seed` files in numeric order: `01-base`, `02-pkgs`, `03-mtk`, `04-passwall`, then `05-extras`.
- Keep each target's `sdk.config` aligned with the packages required by SDK builds.
- Preserve the meanings of `CONFIG_SDK`, `CONFIG_IB`, `CONFIG_CCACHE`, and `CONFIG_BUILD_LOG`; workflow changes must not silently override seed intent.
- Keep `targets.json` fields compatible with workflow consumers, including `target`, `repo`, `ref`, `config`, and `artifacts_release_tag`. 包格式/签名机制不再由 target 静态配置（无 `apk_signing` 字段），由构建时从 `.config`/SDK `Config-build.in` 自动探测 `CONFIG_USE_APK`。
- The mt798x packages feed uses `solarflows/packages.git;hanwckf`; its libffi behavior is documented in `docs/openwrt-build-pitfalls.md`.
- Keep the Passwall dependency list aligned with `sdk.config` package selections; Passwall2 also requires `v2ray-geoip` and `v2ray-geosite`.