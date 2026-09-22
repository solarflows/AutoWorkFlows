---
description: "AutoWorkflows 项目特有的约束、已知陷阱和经验教训。处理本项目的任何文件时优先加载。"
---

# AutoWorkflows 项目约束

## 状态台账

Status rules live in `AGENTS.md` § Project Status (always loaded). Knowledge routing:
`docs/todo.md` (status) · `docs/ci-flow.md` (structure) · `docs/openwrt-build-pitfalls.md` (failure archive).

## 环境变量禁令

绝不在 GitHub Actions workflow 中导出名为 `TARGET`、`HOST`、`BUILD` 的变量。它们会泄漏进 OpenWrt 构建环境，破坏包编译（尤其是 libffi 等基于 autoconf 的包）。

使用有作用域的替代名：
- `TARGET` → `FIRMWARE_TARGET` 或 `matrix_target`
- `HOST` → `BUILD_HOST`
- `BUILD` → `BUILD_TYPE`

验证方法：构建失败时检查 `logs/package/<pkg>/compile.txt` 中的 `checking host system type` 或 `checking target system type`。若输出含 workflow 变量值，即发生了环境泄漏。

参考：[docs/openwrt-build-pitfalls.md](../../docs/openwrt-build-pitfalls.md) § TARGET 环境变量泄漏

## 已知包构建陷阱

### libffi（mt798x）

libffi 在特定缓存策略下反复失败，报 `configure: error: cannot run C compiled programs`。mt798x feed（`solarflows/packages;hanwckf`）中的 libffi 包对 `TARGET`/`HOST` 环境变量极度敏感。

缓解措施：
- 使用 `clean-toolchain` 或 `clean-all` 策略时清理 toolchain stamp
- 确保 workflow 中不导出禁用变量
- 用 `make -j1 V=sc` 重试以获得完整诊断输出

参考：[docs/openwrt-build-pitfalls.md](../../docs/openwrt-build-pitfalls.md) § libffi 构建失败

## 构建系统行为

### 单线程重试（logs.1）

多线程构建（`-j$(nproc)`）产生的交错日志难以诊断。失败时 workflow 把 `logs/` 移为 `logs.1/` 留证，再用 `make -j1 V=sc -k` 重试，在新的 `logs/` 中产生完整的 configure 与编译器输出。两份日志都上传到 artifact。重试完成前绝不删除 `logs/` 或 `logs.1/`。

### 可选诊断管道

`set -euo pipefail` 步骤中使用管道的诊断命令必须以 `|| true` 结尾，防止 SIGPIPE 141 终止步骤。

正确：`find build_dir -maxdepth 3 -type d | head -50 || true`
错误：`find build_dir -maxdepth 3 -type d | head -50`（SIGPIPE 杀死步骤）

## Workflow 基础设施

### 构建状态持久化

把最近构建的 commit SHA 与产物版本存入 `IMMWRT_BUILD_STATE` repository variable，使用 `secrets.ACCESS_TOKEN`（PAT）。`GITHUB_TOKEN` 无法写 repository variable。这避免了按 run 递增的缓存 key 耗尽 10 GB 缓存配额。

### 并发控制

使用固定的全局并发组 `firmware-build-v2` 以兼容现有并发命名空间。绝不按分支或 PR 加作用域（`firmware-build-${{ github.ref }}`）。并行 run 会同时写同一个 `artifacts-<target>` release tag，造成产物损坏与竞态。

### 认证

- `secrets.ACCESS_TOKEN`：GitHub PAT，用于 repository variable 写入与跨仓库操作
- `GH_TOKEN` 环境变量：通过 `env: GH_TOKEN: ${{ secrets.ACCESS_TOKEN }}` 设置供 `gh` CLI 使用

### 远端推送竞态

远端会因 cron 提交自行前进。push 被拒时，先 diff 确认无文件冲突，再 rebase 到远端 head 后重新 push。绝不 force push。

## 诊断流程

构建失败时按以下顺序排查：

1. 查 [docs/openwrt-build-pitfalls.md](../../docs/openwrt-build-pitfalls.md) 的已知故障特征
2. 运行 `openwrt-build-diagnostics` skill 做只读分析
3. 查 `logs/package/error.txt` 与 `logs.1/package/error.txt`
4. 查 `logs.1/<pkg>/compile.txt` 获取完整的单线程重试输出
5. 在 workflow 中搜索 `TARGET=`、`HOST=`、`BUILD=` 导出语句
6. 查看构建步骤中的 `ccache -s` 输出

## Windows 环境与产物处理

在 Windows 主机上诊断或检查 Linux 构建的 SDK/ImageBuilder 归档时：
- 始终使用工作区诊断目录 `.diagnostics/`（已 gitignore）下载、存放和解压临时检查文件，绝不污染 `%TEMP%` 或系统目录。
- 始终排除含 POSIX 相对 symlink 的目录（特别是 `build_dir/` 与中间内核源码树）。
- POSIX 跨层级相对 symlink（如 `../../../arch/...`）会在 Windows 文件系统上导致挂起、死锁或权限错误（各解压工具均如此）。
- 在 Windows 解压归档时，严格过滤/排除 `*build_dir*`（或只解压目标子目录如 `staging_dir/host/` 与顶层配置文件）。

## 配置约定

### Seed 文件合并顺序

seed 合并顺序按 target 分列，见 [openwrt-config.instructions.md](openwrt-config.instructions.md)。`03-mtk.seed` 含闭源 MTK Wi-Fi 驱动，必须保持稳定。

### Fork 与上游（强制证据来源）

引用 OpenWrt/ImmortalWrt 源码作行为论断时，一律对照 `targets.json` 中的**实际构建仓库**（`repo`/`ref`）验证，而不是上游项目：

- mt798x 构建自 `solarflows/immortalwrt-mt798x`（`ref: test`），不是上游 `immortalwrt/immortalwrt`。
- ipq60xx 与 ipq807x 构建自 `solarflows/ImmortalWrt-QualcommAX`（`ref: VIKINGYFY-main`）。
- packages feed 是 `solarflows/packages`（分支 `mt798x`/`qualcommax`），由 `upstream-sync.yml` 打补丁——不是上游 `openwrt/packages`。

上游与 fork 经常分叉（如 `CONFIG_IB_STANDALONE` 默认值、rust 包版本、IB tarball 压缩格式）。基于上游源码而未对照 fork 验证的论断曾导致错误结论（IB 预设包范围、PROFILE 行为、rust 版本）。

## 相关文档

- [.github/instructions/openwrt-build.instructions.md](openwrt-build.instructions.md) — Workflow 架构与诊断要求
- [.github/instructions/openwrt-config.instructions.md](openwrt-config.instructions.md) — 配置文件格式与约束
- [.github/instructions/build-artifacts.instructions.md](build-artifacts.instructions.md) — 产物命名与 release 管理
- [.github/instructions/version-extraction.instructions.md](version-extraction.instructions.md) — 版本解析顺序与 `patched_version` 用法
- [.github/instructions/workflow-agent-common.instructions.md](workflow-agent-common.instructions.md) — 工作流/agent 编辑与 secret 安全通用规则
- [docs/todo.md](../../docs/todo.md) — 功能/实现状态台账（单一事实来源）
- [docs/openwrt-build-pitfalls.md](../../docs/openwrt-build-pitfalls.md) — 已验证故障模式与根因分析
- [.github/skills/openwrt-build-diagnostics/SKILL.md](../skills/openwrt-build-diagnostics/SKILL.md) — 诊断 skill 定义
