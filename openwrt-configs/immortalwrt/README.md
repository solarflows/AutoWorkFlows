# ImmortalWrt Builder — 配置说明

本目录下的 `targets.json` 是 `firmware-build-unified.yml` 工作流（及一组 reusable workflow）的 **target 控制文件**。

设计目标是 **「工作流 ↔ 目标」分离**：

- **默认值**（仓库地址、feed 名称、统一 SDK/IB 发布仓库、版本保留数等）集中在 `firmware-build-unified.yml` 的 `env` 块与各 reusable workflow 的 `inputs.default` 中——改默认值只需动 workflow，不用动 JSON。
- `targets.json` **只存每个 target 的差异化字段**，不含 `defaults` 块；target 缺省的字段由 `plan` job 的 jq 合并自动填充（`//` 兜底）。

修改 targets.json 后提交，下次 workflow 运行即生效。

---

## 总体结构

```json
{
  "_comment": "...",
  "targets": [
    {
      "target": "mt798x",
      "repo": "solarflows/immortalwrt-mt798x",
      "ref": "test",
      "config": "mt798x"
    }
  ]
}
```

`targets.json` 中的条目不需要写全所有字段。`plan` job 的 jq 脚本会从 workflow `env` 注入默认值并合并：

```jq
map(. + {
  packages_branch:   (.packages_branch   // .target),
  packages_feed_repo: (.packages_feed_repo // $pkg_repo),
  packages_feed_name: (.packages_feed_name // $pkg_name),
  release_repo:      (.release_repo      // .repo),
  target_family:     (.target_family     // .target),
  firmware_release_tag_prefix: (.firmware_release_tag_prefix // ""),
  passwall_repo:     (.passwall_repo     // $pkg_repo),
  passwall_tag:      (.passwall_tag      // "packages"),
  sdk_packages:      (.sdk_packages      // "*"),
  artifacts_release_repo: (.artifacts_release_repo // $artifacts_repo),
  artifacts_release_tag:  (.artifacts_release_tag  // ("artifacts-" + .target)),
  artifacts_keep_versions: (.artifacts_keep_versions // $artifacts_keep)
})
```

### 默认值来源（workflow `env` 块）

| env 变量 | 默认值 | 说明 |
|----------|--------|------|
| `DEFAULTS_REPO` | `solarflows/AutoWorkflows` | 本仓库（默认值仓库 / SDK/IB 发布仓库） |
| `PACKAGES_FEED_REPO` | `solarflows/openwrt-packages` | 插件 overlay 仓库；标准源码 feed 由各源码仓库的 `feeds.conf.default` 决定 |
| `PACKAGES_FEED_NAME` | `solarflows` | feed 在源码树中的目录名（`package/<feed_name>`） |
| `ARTIFACTS_RELEASE_REPO` | `solarflows/AutoWorkflows` | SDK/IB 统一 tarball 发布仓库 |
| `ARTIFACTS_KEEP_VERSIONS` | `7` | 每个 SDK/IB 索引保留最近 N 个版本 |

target 可在 `targets.json` 中用同名 key 覆盖其中任意一项（如 `artifacts_release_tag` 等）。包格式（APK/IPK）与签名机制由构建时自动探测，无需在此配置。

## 必填字段（每个 target）

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `target` * | string | 目标标识符，用作构建目录名和 `workflow_dispatch` 过滤关键字 | `mt798x` |
| `repo` * | string | 源码仓库（`owner/repo` 格式） | `solarflows/immortalwrt-mt798x` |
| `ref` * | string | 源码分支或 tag | `test` |
| `config` * | string | 种子配置目录名，对应 `openwrt-configs/immortalwrt/{config}/` | `mt798x` |

可选的 `target_family` 用于 executor 的目标家族分类和显式超时路由，例如两个 Qualcomm target 都设置为 `qualcommax`。

---

## 可选字段 — 固件发布相关

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `packages_branch` | `target` 的值 | 克隆 `openwrt-packages` 时使用的分支名 |
| `release_repo` | `repo` 的值 | 固件 GitHub Release 发布到的仓库 |
| `firmware_release_tag_prefix` | `""` | 固件 Release tag 前缀；用于同一仓库内按 target 隔离固件 Release |
| `passwall_repo` | `${{ env.PACKAGES_FEED_REPO }}` | Passwall 包发布到的仓库（默认复用软件包仓库） |
| `passwall_tag` | `"packages"` | Passwall 固定 Release 的 Tag 名。同名文件替换，不同名文件保留 |

> **签名机制自动探测**：包格式（APK vs IPK）与签名方式不再由 target 静态配置，而是从实际构建配置自动判断。全量构建读取 `.config` 的 `CONFIG_USE_APK`，SDK 增量构建读取 SDK 的 `Config-build.in`。APK 使用 `APK_BUILD_KEY`（PEM），IPK 使用 `USIGN_KEY`（usign 私钥）。

---


## 可选字段 — 软件包 feed 相关

默认值位于 workflow `env`（`PACKAGES_FEED_REPO` / `PACKAGES_FEED_NAME`），target 可通过同名 key 覆盖：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `packages_branch` | `.target` | feed 仓库分支名（也可不写，见必填字段表） |


两类仓库职责不同：

- `solarflows/packages` 是 OpenWrt/ImmortalWrt 的标准 packages feed。
- `solarflows/openwrt-packages` 是本项目维护的插件 overlay，仍由 `OpenWRT_Packages_Updater.yml` 更新。

Qualcomm 的 `VIKINGYFY-main` 源码由 `Sync_Push.yml` 持久化使用 `solarflows/packages.git;qualcommax`，该分支同时应用 net-snmp 的 `interface.*` trigger 修复。编译 workflow 只消费已经同步到远端的源码和 feed，不在编译工作树临时改写 feed 内容。

mt798x 的 active 源是 `solarflows/immortalwrt-mt798x@test`，其中 `test` 分支由人工维护，不由 `Sync_Push.yml` 自动同步；`solarflows/lede` 仍是 legacy 镜像，不代表 mt798x 当前构建源。

---

## 可选字段 — SDK / IB 统一产物

> unified 工作流不使用 `ghcr.io/openwrt/sdk:*` Docker 镜像。SDK 与 IB 均由全量编译产出，发布到同一个 `artifacts-<target>` Release tag 中，分别由 `sdk-index.json` 与 `ib-index.json` 索引。

默认值位于 workflow `env`（见上表），target 可在 `targets.json` 中覆盖：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `artifacts_release_repo` | `${{ env.ARTIFACTS_RELEASE_REPO }}` | SDK/IB 统一 tarball 发布仓库 |
| `artifacts_release_tag` | `artifacts-<target>` | SDK/IB 共享的多版本 Release tag；不同逻辑 target 必须隔离 |
| `artifacts_keep_versions` | `${{ env.ARTIFACTS_KEEP_VERSIONS }}` | SDK/IB 各自索引保留最近 N 个版本 |
| `sdk_packages` | `"*"` | SDK 编译时收集的软件包清单模式 |

> **保留字段**：`sdk_container` 仍保留供 v1 工作流兼容。v2 中由自建 SDK 替代，不再使用。

### SDK / IB 版本号规则

来自 ImmortalWrt `include/version.mk` 的 `VERSION_NUMBER`：

- mt798x (21.02 分支)：`21.02.7` 等点版本
- qualcommax / ipq60xx 兼容 target (SNAPSHOT)：自动追加日期后缀 → `SNAPSHOT-20260801`
- qualcommax-ipq807x (SNAPSHOT)：使用独立 target 前缀发布，避免与旧 target 的固件 Release 混写

文件名格式：
```
sdk-<target>-<version>-<arch>.tar.xz
ib-<target>-<version>-<arch>.tar.xz
```

同 `(target, version)` 组合：`--clobber` 覆盖；不同版本共存。每个 `artifacts-<target>` Release 内含 `sdk-index.json` 和 `ib-index.json`，分别描述 SDK 与 IB 版本清单。

---

## 添加新目标

### 步骤 1：在 `targets.json` 添加条目

```json
{
  "target": "newdevice",
  "repo": "solarflows/immortalwrt-newdevice",
  "ref": "main",
  "config": "newdevice",
  "packages_branch": "newdevice"
}
```
}

最少只需 4 个必填字段，其余缺省字段由 `plan` job 从 workflow `env` 注入的默认值自动填充（jq `//` 兜底）。

### 步骤 2：创建种子配置目录

```
openwrt-configs/immortalwrt/newdevice/
├── 01-base.seed     ← 必须：至少一个 .seed 文件（含 CONFIG_TARGET_*）
├── 02-pkgs.seed     ← 可选：按需拆分
├── sdk.config       ← 可选：SDK-only 或 SDK+IB 路径的软件包清单
└── ...
```
`.seed` 文件按**文件名排序**后依次拼接形成全量编译的 `.config`。01-base.seed 中**必须**包含：
```
CONFIG_SDK=y
CONFIG_IB=y
```

全量编译工作流会在编译末尾打包并发布 SDK/IB tarball 到统一 artifacts Release；缺少这两项时，packages-only 路径会升级为全量编译。

### SDK 编译配置（`sdk.config`）

`compile-packages.yml` 使用 `sdk.config` 指定要编译的软件包清单。此文件与 `.seed` 文件**完全独立**，用于 SDK-only 和 SDK+IB 快速路径。


### Qualcomm target 拆分与缓存边界

Qualcomm 现在是两个独立的逻辑 target。它们复用同一源码仓库、源码 ref 和 `qualcommax` 软件包分支，但各自合并配置、编译、缓存、状态和发布资产。

| target | 配置目录 | 设备 | cache/state 命名空间 | 固件 Release | Passwall Release | SDK/IB Release |
|--------|----------|------|----------------------|--------------|------------------|----------------|
| `qualcommax` | `qualcommax` | `link_nn6000-v2` | 保留 `qualcommax`，继续命中 `immwrt-v2-*-qualcommax-*` | 保留 `<version>` | `packages` | `artifacts-qualcommax` |
| `qualcommax-ipq807x` | `ipq807x` | `netgear_rbr750` | 新建 `qualcommax-ipq807x`，不写入旧 namespace | `qualcommax-ipq807x-<version>` | `packages-qualcommax-ipq807x` | `artifacts-qualcommax-ipq807x` |

两个条目都使用 `solarflows/ImmortalWrt-QualcommAX` 的 `VIKINGYFY-main` 和 `solarflows/packages` 的 `qualcommax` 分支；它们只共享源码与 feed 的来源，不共享构建结果。

旧 `qualcommax` 的 cache/state 只服务 ipq60xx 兼容 target；新 target 不复用或写入旧 cache、state、固件 Release、Passwall Release 或 SDK/IB Release。`both` 会把两个条目作为两个矩阵 target 分别规划和执行，同一源码仓库不会导致产物共享。

### 步骤 3：更新 `workflow_dispatch` 的 `target` 选项（可选）

如果需要在手动触发时单独选择新目标，编辑 `firmware-build-unified.yml` 中 `on.workflow_dispatch.inputs.target.options`。当前可选值为 `mt798x`、`qualcommax`、`qualcommax-ipq807x` 和 `both`；`both` 会包含两个 Qualcomm target。

---

## 种子配置拆分建议
| 文件名 | 内容 |
|--------|------|
| `01-base.seed` | `CONFIG_TARGET_*` + 构建选项 + **`CONFIG_SDK=y CONFIG_IB=y`** |
| `02-pkgs.seed` | `CONFIG_PACKAGE_*` 软件包列表 |
| `03-<vendor>.seed` | 厂商无线驱动（MTK / QCA） |
| `04-passwall.seed` | passwall 相关包（也可拆到 sdk.config） |
| `05-extras.seed` | 杂项 |
| `sdk.config` | SDK-only / SDK+IB 快速路径的软件包清单 |

---


## 构建环境

| 项目 | 值 |
|------|-----|
| Runner | `ubuntu-24.04`（4 vCPU，16G RAM，约 14G 可用 SSD） |
| 全量编译超时 | 480 分钟（8 小时） |
| SDK-only / SDK+IB 超时 | `target_family=qualcommax` 时 240 分钟，其余 120 分钟 |
| 并发 | 全局固定 `firmware-build-v2`；各 target executor 发布互斥，`cancel-in-progress: false` |
| 定时触发 | 每周一、六 UTC 00:06 |

测试分支由调用方将当前 `${{ github.ref }}` 传给 reusable workflow 的可选 `defaults_ref`；因此 defaults checkout 与 `plan` 的 sparse checkout 都读取调用方分支。未传入时默认为 `main`，主分支行为保持不变。

---

## Smart 模式触发矩阵

`firmware-build-unified.yml` 中 `plan` job 自动决策：

| 条件 | `run-firmware` | `run-sdk-ib` | `run-packages` | 发布结果 |
|------|:--:|:--:|:--:|:--|
| 无任何变更 | ❌ | ❌ | ❌ | 仅 summary |
| 仅软件包变更，SDK/IB 已存在 | ❌ | ✅ | ❌ | packages + 快速重打包固件 |
| 仅软件包变更，SDK 或 IB 缺失 | ✅ | ❌ | ❌ | 全量固件、SDK、IB |
| 源码、kernel 或 toolchain 变化 | ✅ | ❌ | ❌ | 全量固件、SDK、IB |
| 手动 `trigger=full` | ✅ | ❌ | ❌ | 全量固件、SDK、IB |
| 手动 `trigger=sdk-packages` | ❌ | ❌ | ✅ | packages |

`plan` job 的变更检测策略：
1. 通过 GitHub `compare` API 取上游 commit 文件变更范围（首选）
2. compare API 失败时熔断降级浅克隆本地 `git diff`（无需认证）
3. 本地 diff 仍失败时降级为保守走全量

---

## 手动触发参数

| 参数 | 说明 |
|------|------|
| `target` | 构建目标：`mt798x` / `qualcommax` / `qualcommax-ipq807x` / `both` |
| `trigger` | 触发模式：`smart` / `full` / `sdk-packages` |
| `cache_strategy` | 缓存策略：`smart` / `clean-toolchain` / `clean-ccache` / `clean-all` / `no-cache` |
| `skip_upstream` | 跳过上游同步工作流触发（节省时间） |
| `free_disk_space` | 清理磁盘空间（仅 `full` 路径生效） |

---

## 当前架构摘要

- `firmware-build-unified.yml` 的 `plan` job 负责触发、变更检测、版本和路由决策。
- `compile-firmware.yml` 负责全量固件编译，并生成 SDK/IB tarball。
- `compile-packages.yml` 同时承载 SDK-only 与 SDK+IB 快速路径，由 `matrix_build_sdk_ib` 区分。
- 全量产物发布到每个 target 的统一 `artifacts-<target>` tag；SDK 和 IB 分别使用 `sdk-index.json` 与 `ib-index.json`。
- 独立 ImageBuilder workflow 和旧 v1 主 workflow 已移动到 `.github/archive/workflows/`，仅保留历史审计用途。
- `targets.json` 只保留 target 差异化字段；默认值由 unified workflow 的 `env` 和 reusable workflow 的 `inputs.default` 提供。
- reusable workflow 的 defaults checkout 显式使用调用方 ref；默认 ref 为 `main`。
