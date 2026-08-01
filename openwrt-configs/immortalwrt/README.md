# ImmortalWrt Builder — 配置说明

本目录下的 `targets.json` 是 `firmware_builder_v2.yml` 工作流（及一组 reusable workflow）的 **target 控制文件**。

设计目标是 **「工作流 ↔ 目标」分离**：

- **默认值**（仓库地址、feed 名称、SDK/IB 发布仓库、版本保留数等）集中在 `firmware_builder_v2.yml` 的 `env` 块与各 reusable workflow 的 `inputs.default` 中——改默认值只需动 workflow，不用动 JSON。
- `targets.json` **只存每个 target 的差异化字段**，不含 `defaults` 块；target 缺省的字段由 `plan` job 的 jq 合并自动填充（`//` 兜底）。

修改 targets.json 后提交，下次 workflow 运行即生效。

---

## 总体结构

```jsonc
{
  "_comment": "...",
  "targets": [ ... ]       // 目标列表（只含差异化字段）
}
```

`targets.json` 中的条目不需要写全所有字段。`plan` job 的 jq 脚本会从 workflow `env` 注入默认值并合并：

```jq
map(. + {
  packages_branch:   (.packages_branch   // .target),
  release_repo:      (.release_repo      // .repo),
  passwall_repo:     (.passwall_repo     // $pkg_repo),
  ...
})
```

### 默认值来源（workflow `env` 块）

| env 变量 | 默认值 | 说明 |
|----------|--------|------|
| `DEFAULTS_REPO` | `solarflows/AutoWorkflows` | 本仓库（默认值仓库 / SDK/IB 发布仓库） |
| `PACKAGES_FEED_REPO` | `solarflows/openwrt-packages` | openwrt 软件包源（feed）仓库 |
| `PACKAGES_FEED_NAME` | `solarflows` | feed 在源码树中的目录名（`package/<feed_name>`） |
| `SDK_RELEASE_REPO` | `solarflows/AutoWorkflows` | 自建 SDK tarball 发布仓库 |
| `IB_RELEASE_REPO` | `solarflows/AutoWorkflows` | 自建 IB tarball 发布仓库 |
| `IB_KEEP_VERSIONS` | `3` | 同 tag 保留最近 N 个版本 |
| `IB_PROFILE` | `''` | build-via-ib 的 `make image PROFILE=` 值；空 = 多 profile |

target 可在 `targets.json` 中用同名 key 覆盖其中任意一项（如 `sdk_release_tag`、`ib_release_tag`、`apk_signing` 等）。

## 必填字段（每个 target）

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `target` * | string | 目标标识符，用作构建目录名和 `workflow_dispatch` 过滤关键字 | `mt798x` |
| `repo` * | string | 源码仓库（`owner/repo` 格式） | `solarflows/immortalwrt-mt798x` |
| `ref` * | string | 源码分支或 tag | `test` |
| `config` * | string | 种子配置目录名，对应 `openwrt-configs/immortalwrt/{config}/` | `mt798x` |

---

## 可选字段 — 固件发布相关

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `packages_branch` | `target` 的值 | 克隆 `openwrt-packages` 时使用的分支名 |
| `release_repo` | `repo` 的值 | 固件 GitHub Release 发布到的仓库 |
| `passwall_repo` | `${{ env.PACKAGES_FEED_REPO }}` | Passwall 包发布到的仓库（默认复用软件包仓库） |
| `passwall_tag` | `"packages"` | Passwall 固定 Release 的 Tag 名。同名文件替换，不同名文件保留 |
| `apk_signing` | `false` | 是否需要 APK 签名密钥（OpenWrt ≥ 25.12 改用 APK 时需要设为 `true`，影响 mt798x ipk ↔ qualcommax apk 分流） |

---

## 可选字段 — 软件包 feed 相关

默认值位于 workflow `env`（`PACKAGES_FEED_REPO` / `PACKAGES_FEED_NAME`），target 可通过同名 key 覆盖：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `packages_branch` | `.target` | feed 仓库分支名（也可不写，见必填字段表） |

---

## 可选字段 — SDK / ImageBuilder（v2 新增）

> v2 工作流不再使用 `ghcr.io/openwrt/sdk:*` Docker 镜像。SDK 与 IB 均由本工作流全量编译后产出，发布到 GitHub Release 中持久化，后续通过 `build-via-sdk` / `build-via-ib` 两个可复用 workflow 引用。

默认值位于 workflow `env`（见上表），target 可在 `targets.json` 中覆盖：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `sdk_release_repo` | `${{ env.SDK_RELEASE_REPO }}` | 自建 SDK tarball 发布到的仓库 |
| `sdk_release_tag` | `sdk-<target>` | 单 tag 下多版本共存（asset 文件名带版本号区分） |
| `ib_release_repo` | `${{ env.IB_RELEASE_REPO }}` | 自建 IB tarball 发布到的仓库 |
| `ib_release_tag` | `ib-<target>` | 同上，单 tag 多版本 |
| `ib_profile` | `${{ env.IB_PROFILE }}` | build-via-ib 的 `make image PROFILE=` 值；空 = 走 multi-profile 生成所有 device profile |
| `ib_keep_versions` | `${{ env.IB_KEEP_VERSIONS }}` | 同 tag 保留最近 N 个版本（按 `index.json` 中版本号排序，超过的自动清理） |
| `sdk_packages` | `"*"` | build-via-sdk 编译时收集的软件包 glob 模式 |

> **保留字段**：`sdk_container` 仍保留供 v1 工作流兼容。v2 中由自建 SDK 替代，不再使用。

### SDK / IB 版本号规则

来自 ImmortalWrt `include/version.mk` 的 `VERSION_NUMBER`：

- mt798x (21.02 分支)：`21.02.7` 等点版本
- qualcommax (SNAPSHOT)：自动追加日期后缀 → `SNAPSHOT-20260801`，便于多版本共存

文件名格式：
```
sdk-<target>-<version>-<arch>.tar.xz
ib-<target>-<version>-<arch>.tar.xz
```

同 `(target, version)` 组合：`--clobber` 覆盖；不同版本共存。每个 `sdk-<target>` / `ib-<target>` Release 内含一份 `index.json` 描述已发布版本清单，供 `build-via-ib` / `build-via-sdk` 选用。

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

最少只需 4 个必填字段，其余缺省字段由 `plan` job 从 workflow `env` 注入的默认值自动填充（jq `//` 兜底）。

### 步骤 2：创建种子配置目录

```
openwrt-configs/immortalwrt/newdevice/
├── 01-base.seed     ← 必须：至少一个 .seed 文件（含 CONFIG_TARGET_*）
├── 02-pkgs.seed     ← 可选：按需拆分
├── sdk.config       ← 可选：build-via-sdk 的软件包清单
└── ...
```

`.seed` 文件按**文件名排序**后依次拼接形成全量编译的 `.config`。01-base.seed 中**必须**包含：

```
CONFIG_SDK=y
CONFIG_IB=y
```

v2 工作流会在全量编译末尾打包并发布 SDK/IB tarball 到本仓库 Release，缺这两项时 SDK/IB 步骤会被跳过。

### SDK 编译配置（`sdk.config`）

`build-via-sdk` 可复用 workflow 使用 `sdk.config` 指定要编译的软件包清单。此文件与 `.seed` 文件**完全独立**，仅用于 SDK 编译场景。

典型用途：从 `.seed` 中提取 passwall 相关的 `CONFIG_PACKAGE_*` 选项。SDK 编译时此文件中的 `CONFIG_PACKAGE_*=y` 会被自动转为 `=m`（编译为独立 ipk/apk，不内建到固件）。

### 步骤 3：更新 `workflow_dispatch` 的 `target` 选项（可选）

如果需要在手动触发时单独选择新目标，编辑 `firmware_builder_v2.yml` 中 `on.workflow_dispatch.inputs.target.options`，添加新的值；不更新时仍可通过 `both` 模式触发（所有目标并行构建）。

---

## 种子配置拆分建议

| 文件名 | 内容 |
|--------|------|
| `01-base.seed` | `CONFIG_TARGET_*` + 构建选项 + **`CONFIG_SDK=y CONFIG_IB=y`** |
| `02-pkgs.seed` | `CONFIG_PACKAGE_*` 软件包列表 |
| `03-<vendor>.seed` | 厂商无线驱动（MTK / QCA） |
| `04-passwall.seed` | passwall 相关包（也可拆到 sdk.config） |
| `05-extras.seed` | 杂项 |

---

## 构建环境

| 项目 | 值 |
|------|-----|
| Runner | `ubuntu-24.04` (4 vCPU, 16G RAM, 14G SSD) |
| 全量编译超时 | 480 分钟（8 小时） |
| build-via-ib 超时 | 60 分钟 |
| build-via-sdk 超时 | 60 分钟 |
| 并发 | 同 branch × target 互斥 (`cancel-in-progress: false`) |
| 定时触发 | 每周一、六 UTC 00:06 |

---

## Smart 模式触发矩阵

`firmware_builder_v2.yml` 中 `plan` job 自动决策：

| 条件 | build-firmware | build-via-ib | build-via-sdk | release |
|------|:--:|:--:|:--:|:--:|
| 无任何变更 | ❌ | ❌ | ❌ | ❌（仅 summary） |
| 仅软件包变 | ❌ | ❌ | ✅ | ✅（仅 packages Release） |
| 上游变（kernel/toolchain） | ✅ | ❌ | ✅（固件已含全包，可跳过） | ✅ |
| 上游变（仅 feed/package） | ❌ | ✅ | 视情况 | ✅ |
| 手动 `trigger=firmware` | ✅ | ❌ | ❌ | ✅ |
| 手动 `trigger=packages` | ❌ | ❌ | ✅ | ✅ |
| 手动 `trigger=ib` | ❌ | ✅ | ❌ | ✅ |
| 首次构建（无 SDK/IB cache） | ✅ | ❌ | ❌ | ✅ |
| build-via-ib 失败 | ✅（自动回退全量） | — | ❌ | ✅ |

`plan` job 的变更检测策略：
1. 通过 GitHub `compare` API 取上游 commit 文件变更范围（首选）
2. compare API 失败时熔断降级浅克隆本地 `git diff`（无需认证）
3. 本地 diff 仍失败时降级为保守走全量

---

## 手动触发参数

| 参数 | 说明 |
|------|------|
| `target` | 构建目标：`mt798x` / `qualcommax` / `both` |
| `trigger` | 触发模式：`smart` / `firmware` / `ib` / `packages` |
| `cache_strategy` | 缓存策略：`smart` / `clean-toolchain` / `clean-ccache` / `clean-all` |
| `skip_upstream` | 跳过上游同步工作流触发（节省时间） |
| `use_ccache` | 启用 ccache（仅 build-firmware 生效） |
| `force_rebuild` | 强制全量重编（忽略所有缓存） |

---

## v1 → v2 变更摘要

| v1 | v2 |
|----|----|
| `firmware_builder.yml` 单文件 2258 行 | `firmware_builder_v2.yml`（主编排）+ `.github/workflows/build/` 下多个 reusable workflow |
| `compile-firmware` （单 job） | `build-firmware`（全量编译 + 末尾打包 SDK/IB 上传） |
| `compile-passwall` 单独 job | **删除**，合并到 `build-via-sdk` |
| `compile-packages` 单独 job（用上游 Docker） | **`build-via-sdk`**（用自建 SDK，下载后本地编译） |
| — | **`build-via-ib`** 新增（用自建 IB 重新打包固件，失败自动回退 build-firmware） |
| `ghcr.io/openwrt/sdk:*` 上游 Docker 容器 | 自建 SDK tarball，存储在 `sdk-<target>` tag 下多版本共存 |
| `targets.json` 含 `defaults` 块承载全部默认值 | 默认值移入 `firmware_builder_v2.yml` 的 `env` 块与 reusable workflow 的 `inputs.default`；`targets.json` 只保留差异化字段 |
