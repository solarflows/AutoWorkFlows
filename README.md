# Auto WorkFlows

自动化工作流集合，用于管理 [solarflows/openwrt-packages](https://github.com/solarflows/openwrt-packages) 仓库的插件采集、固件构建和上游同步。

> 📖 完整插件列表和来源请查看 [openwrt-packages 仓库 README](https://github.com/solarflows/openwrt-packages)

## Workflows

| 工作流 | 说明 |
|:-------|:-----|
| **OpenWRT Packages Updater** | 每 12 小时自动采集插件并推送到 openwrt-packages 仓库各分支 |
| **ImmortalWrt Builder** | 构建 mt798x / qualcommax 固件并发布 Release |
| **SDK Package Builder** | 使用 SDK 编译指定架构的 ipk 包 |
| **v2ray-geodata Updater** | 每周六更新 geodata 路由数据 |
| **Sync_Push** | 同步 lean / immortalwrt 等上游仓库并应用补丁 |

## 补丁与覆写层

自定义内容按仓库存放在 `.github/diy/<repo>/` 下，两类机制互不干扰：

| 机制 | 目录 | 用途 |
|:-----|:-----|:-----|
| **补丁（patches）** | `patches/` 或 `patches/<target>/` | 对上游文件的小型行级修改，按顺序应用 |
| **覆写层（overwrite）** | `overwrite/global/` 或 `overwrite/<target>/` | 整文件替换或新增（含 OpenWrt 原生包补丁目录如 `smartdns/patches/*.patch`），在所有补丁之后应用，优先级最高 |

- 覆写层目录结构与目标仓库相对路径一致，CI 直接复制落位。
- 被覆写的文件不再跟随上游自动更新，需手动维护。
- `temp*.patch` 为临时补丁：应用失败仅告警跳过；其余补丁失败会中断流程。
