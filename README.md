# Auto WorkFlows

自动化工作流集合，用于管理 [solarflows/openwrt-packages](https://github.com/solarflows/openwrt-packages) 仓库的插件采集、固件构建和上游同步。

> 📖 完整插件列表和来源请查看 [openwrt-packages 仓库 README](https://github.com/solarflows/openwrt-packages)

## Workflows

| 工作流 | 说明 |
|:-------|:-----|
| **custom-feed** | 自建插件源更新：每 12 小时自动采集第三方插件并推送到 openwrt-packages 仓库各分支 |
| **firmware-build-unified** | 统一固件与 SDK 增量构建流水线并发布 Release |
| **geodata-updater** | 每周六自动更新 Loyalsoldier / MetaCubeX 规则数据 |
| **upstream-sync** | 官方上游代码库同步：同步 lean / immortalwrt 等上游仓库并应用补丁 |

## 补丁与叠加层 (Patches & Overlay)

自定义内容直接在 `.github/` 下扁平化组织，两类机制互不干扰：

| 机制 | 目录 | 用途 |
|:-----|:-----|:-----|
| **上游同步资源** | `.github/upstream-sync/` | `upstream-sync` 专用的补丁（`patches/{qualcommax,lede,packages,luci}/`）与叠加层（`overlay/`） |
| **插件源发布资源** | `.github/custom-feed/` | `custom-feed` 专用声明式清单（`packages.yaml`）、专用补丁、叠加层与收集引擎 |
| **自研工作流动作** | `.github/actions/` | 复合 Action（`git-auth`、`apply-patches`、`apply-overlay`） |
| **工作流自动化** | `.github/workflows/` | GitHub Actions 工作流核心入口 |

- 源码树主工程补丁存放于 `.github/upstream-sync/patches/<repo>/`（例如 `qualcommax/` 独立成一级目录）。
- 叠加层目录结构与目标仓库相对路径一致，CI 直接复制落位。
- 被叠加覆盖的文件不再跟随上游自动更新，需手动维护。
- `temp*.patch` 为临时补丁：应用失败仅告警跳过；其余补丁失败会中断流程。
