---
description: "修改 OpenWrt/ImmortalWrt seed、sdk.config、targets.json、目标配置或包依赖时使用。"
applyTo: "openwrt-configs/**"
---

# OpenWrt 配置

- seed 文件保持 UTF-8 无 BOM、LF 行尾。
- 按数字序合并 `<target>/NN-*.seed`；各 target 的文件集不同：
  - mt798x：`01-base` → `02-pkgs` → `03-mtk` → `04-passwall` → `05-extras`
  - ipq60xx / ipq807x：`01-base` → `02-pkgs` → `03-passwall` → `04-extras`
- 各 target 的 `sdk.config` 与 SDK 构建所需包保持对齐。
- 保持 `CONFIG_SDK`、`CONFIG_IB`、`CONFIG_CCACHE`、`CONFIG_BUILD_LOG` 的语义；workflow 改动不得静默覆盖 seed 意图。
- `targets.json` 字段与 workflow 消费方保持兼容，包括 `target`、`repo`、`ref`、`artifacts_release_tag`。种子配置目录名恒等于 `target`（`openwrt-configs/immortalwrt/<target>/`），不存在独立的 `config` 字段。包格式/签名机制不再由 target 静态配置（无 `apk_signing` 字段），由构建时从 `.config`/SDK `Config-build.in` 自动探测 `CONFIG_USE_APK`。
- mt798x 的 packages feed 使用 `solarflows/packages.git;hanwckf`；其 libffi 行为记录在 `docs/openwrt-build-pitfalls.md`。
- Passwall 依赖列表与 `sdk.config` 的包选择保持对齐；Passwall2 还需要 `v2ray-geoip` 与 `v2ray-geosite`。