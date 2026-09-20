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

自定义内容直接在 `.github/` 下扁平化组织，两类机制互不干扰：

| 机制 | 目录 | 用途 |
|:-----|:-----|:-----|
| **上游同步资源** | `.github/sync-push/` | `Sync_Push` 专用的补丁（`patches/{qualcommax,lede,packages,luci}/`）与覆写层（`overwrite/`） |
| **插件源发布资源** | `.github/packages-updater/` | `OpenWRT_Packages_Updater` 专用声明式清单（`packages.yaml`）、专用补丁、覆写层与收集引擎 |
| **自研工作流动作** | `.github/actions/` | 复合 Action（`git-auth`、`apply-patches`、`apply-overwrite`） |
| **工作流自动化** | `.github/workflows/` | GitHub Actions 工作流核心入口 |

- 源码树主工程补丁存放于 `.github/sync-push/patches/<repo>/`（例如 `qualcommax/` 独立成一级目录）。
- 覆写层目录结构与目标仓库相对路径一致，CI 直接复制落位。
- 被覆写的文件不再跟随上游自动更新，需手动维护。
- `temp*.patch` 为临时补丁：应用失败仅告警跳过；其余补丁失败会中断流程。
