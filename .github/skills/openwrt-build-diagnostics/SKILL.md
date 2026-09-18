---
name: openwrt-build-diagnostics
description: "诊断 AutoWorkflows 的 OpenWrt/ImmortalWrt 构建失败、GitHub Actions artifact、error.txt、compile.txt、logs/logs.1、ccache、stamp skip 或 TARGET 环境变量泄漏时使用。严格只读并生成证据化报告。"
argument-hint: "Log directory, GitHub Actions run URL/ID, or pasted key log excerpt"
user-invocable: true
disable-model-invocation: false
---

# OpenWrt Build Diagnostics

只读诊断构建失败：不修改 workflow、seed、package、源码、日志或构建状态。产出证据、置信度、备选假设与验证步骤；修复必须在单独任务中、经新计划与用户确认后执行。

## 输入门（Input Gate）

case 目录固定为 `.diagnostics/openwrt-build/<case-id>/`（已 gitignore）；下载、解压、粘贴的输入都放这里，即使存在其它可用来源也优先此位置。

有效输入 = 至少一个非空 `error.txt`、`compile.txt`、Actions job log 或用户提供的构建日志；目录存在但为空不算通过。

缺少有效输入时停止诊断，让用户四选一：

1. 用户自行把日志放入上方 case 目录，放入后回复继续。
2. 授权自动取回指定的 GitHub Actions run 或 artifact。
3. 粘贴一段有界的关键日志。
4. 取消诊断。

推荐第 1 项。等待 = 在输入门结束本次执行，等用户下一条消息继续；不得轮询、sleep 或挂起终端进程等待文件。

## 固定命令

终端操作只有以下脚本命令，一步一条、逐条执行；禁止管道 `|`、`&&`、`;`、重定向、命令替换或临时自造命令（会破坏 VS Code terminal auto-approve 的整行匹配，配置见 [references/auto-approve.md](./references/auto-approve.md)）。命令在仓库根目录执行，使用仓库相对路径；若终端 cwd 不在仓库根目录，先单独 `cd` 到仓库根目录。取回统一走脚本内部只读 `gh` 调用，不要手写 `gh run`、`Expand-Archive`、`tar` 等命令。若当前环境已提供 GitHub MCP 工具，可用它读取 run/artifact 元数据（不占用终端批准）；下载与解压仍必须走脚本，以保留 Windows 解压防护与写入边界。

1. 列出最近失败 run（有界，默认 20 条）：

   ```text
   python .github/skills/openwrt-build-diagnostics/scripts/fetch_build_logs.py list
   ```

2. 查看所选 run 的 artifact（名称、大小、是否过期）：

   ```text
   python .github/skills/openwrt-build-diagnostics/scripts/fetch_build_logs.py artifacts --run-id <id>
   ```

3. 取回（选项 2 授权后执行；下载到 `.diagnostics/openwrt-build/<case-id>/artifacts/<name>/`，缺省选中 `*-build-log`，无可用日志 artifact 时自动保存 failed-step job log）：

   ```text
   python .github/skills/openwrt-build-diagnostics/scripts/fetch_build_logs.py fetch --run-id <id> [--artifact <name>] [--pattern <glob>] [--case <case-id>]
   ```

4. 用户手动下载了 zip：安全解压进 case（跳过 symlink 成员与 `build_dir/` 子树，默认上限 2048 MB）：

   ```text
   python .github/skills/openwrt-build-diagnostics/scripts/fetch_build_logs.py extract --archive <zip-path> --case <case-id>
   ```

5. 分析并生成 `report/summary.md` 与 `analysis.json`：

   ```text
   python .github/skills/openwrt-build-diagnostics/scripts/analyze_build_logs.py .diagnostics/openwrt-build/<case-id>
   ```

阅读报告、检查有界片段使用 read/search 工具，不产生终端命令。命令中的 `<...>` 与 `[...]` 仅为占位说明，实际执行时替换为具体值或整体省略。

## 流程

1. 确认输入门与 case 目录。
2. 取回：命令 1 → 用户选定 run（不得假定最新失败即目标）→ 命令 2 → 命令 3；用户自行放入的输入直接进入下一步。下载、认证、解压、编码错误必须显式报告；case 目录非空时命令 3/4 会拒绝，需换 case 或显式 `--force`。
3. 命令 5 生成报告；阅读 `report/summary.md`，需要结构化证据时读取 `analysis.json`。
4. 只读取验证主假设与备选假设所需的最小片段；命中已知特征时查 [diagnostic-signatures.md](./references/diagnostic-signatures.md)。
5. 输出报告：汇总 / 主假设 / 证据（附来源路径，run 与 artifact 来源引用 case 内 `fetch.json`）/ 备选假设 / 置信度 / 缺失证据 / 建议修复 / 验证步骤。

## 只读边界

- 不编辑 workflow、seed、package、源码；不清理、改名、移动 case 内已有证据文件。
- 未经授权不触发 rerun、不下载 artifact；远端只允许读取类 `gh` 调用。
- 脚本写入仅限 `.diagnostics/openwrt-build/`。
- 不把建议描述为已应用的修复；证据留在文件中，终端与工具输出保持有界。