# ImmortalWrt Builder — 配置说明

本目录下的 `targets.json` 是 `firmware_builder.yml` 工作流的**唯一控制文件**。

修改此文件后提交，下次 workflow 运行即生效，无需改动 `.yml`。

---

## `targets.json` 字段说明

### 必填字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `target` * | string | 目标标识符，用作构建目录名和 `workflow_dispatch` 过滤关键字 | `mt798x` |
| `repo` * | string | 源码仓库（`owner/repo` 格式） | `solarflows/immortalwrt-mt798x` |
| `ref` * | string | 源码分支或 tag | `test` |
| `config` * | string | 种子配置目录名，对应 `openwrt-configs/immortalwrt/{config}/` | `mt798x` |

### 可选字段（未填时 jq 自动补默认值）

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `packages_branch` | `target` 的值 | 克隆 `openwrt-packages` 时使用的分支名 |
| `release_repo` | `repo` 的值 | GitHub Release 发布到的仓库 |
| `release_tag_prefix` | `""` (无前缀) | Release 版本 Tag 的前缀。同一仓库有多个构建时用于区分，例如 `mt798x-` 生成 `mt798x-v20260505-1430` |
| `passwall_tag` | `"passwall-{target}"` | Passwall 固定 Release 的 Tag 名 |

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

最少只需 4 个必填字段，其余自动取默认值。

### 步骤 2：创建种子配置目录

```
openwrt-configs/immortalwrt/newdevice/
├── 00-target.seed     ← 必须：至少一个 .seed 文件
├── 01-packages.seed   ← 可选：按需拆分
└── ...
```

`.seed` 文件按**文件名排序**后依次拼接，序号建议使用 `00-`、`01-` 前缀控制顺序。

### 步骤 3：更新 `workflow_dispatch` 的 `target` 选项（可选）

如果需要在手动触发时单独选择新目标，编辑 `firmware_builder.yml` 中 `on.workflow_dispatch.inputs.target.options`，添加新的值。

不更新的情况下仍可通过 `both` 模式触发（所有目标并行构建）。

---

## 种子配置拆分建议

| 文件名 | 内容 |
|--------|------|
| `00-target.seed` | `CONFIG_TARGET_*` 架构和芯片选择 |
| `10-device.seed` | `CONFIG_TARGET_DEVICE_*` 设备型号 |
| `20-kernel.seed` | `CONFIG_KERNEL_*` 内核特性 |
| `30-libs.seed` | `CONFIG_LIBCURL_*`、`CONFIG_MBEDTLS_*` 等库配置 |
| `40-wifi.seed` | MTK / QCA 无线驱动配置 |
| `50-packages.seed` | `CONFIG_PACKAGE_*` 软件包列表 |
| `60-kmod.seed` | `CONFIG_PACKAGE_kmod-*` 内核模块 |
| `99-misc.seed` | 其余杂项 |

---

## 构建环境

| 项目 | 值 |
|------|-----|
| Runner | `ubuntu-24.04` (4 vCPU, 16G RAM, 14G SSD) |
| 超时 | 360 分钟（6 小时） |
| 并发 | 同 branch 互斥 (`cancel-in-progress: false`) |
| 定时触发 | 每周三、六 UTC 3:00 |

---

## 手动触发参数

| 参数 | 说明 |
|------|------|
| `target` | 构建目标：`mt798x` / `qualcommax` / `both` |
| `release` | 是否发布到 GitHub Release |
| `use_ccache` | 是否启用 ccache 编译缓存（`make` 重编译时跳过未改文件） |
| `force_rebuild` | 强制全量重编（忽略所有缓存，用于修复工具链损坏） |
