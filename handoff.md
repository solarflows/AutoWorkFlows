# Handoff — AutoWorkFlows 项目交接文档

> 生成日期：2026-09-06
> 用途：供下一个 agent 对话接手本项目，避免依赖过长上下文。
> 对象：`solarflows/AutoWorkFlows` 仓库（注意仓库名大写 **W**，git remote 仍指向旧名 `AutoWorkflows.git`，GitHub 自动转发）。

---

## 1. 当前状态总览（已核实）

- **当前分支**：`fix/maintenance-workflows-safety-speed`（最新工作流修复提交为 `fafc2e1`，本文件更新后与其一并推送，推送后工作区应保持干净）
- **最新工作流修复提交**：`fafc2e1` — `fix(workflows): 修复摘要解析与同步失败传播`
- **与 main 的关系**：最新 `origin/main = f7750c0`；功能提交相对 `origin/main` **ahead 4、behind 1**，加上本次交接文档提交后分支总计 ahead 5。当前分支包含：
  - `e51ca35` — config(ipq807x) 同步 RBR750 构建配置并接入标准 packages feed
  - `52c027e` — fix(workflows) 加固同步/构建/geodata 链路安全与速度
  - `12f0900` — fix(rust) 更新 Rust 包版本和修复构建脚本（这是**更早**的提交，在 e51ca35 之前，由之前会话完成，非本次手改）
  - `fafc2e1` — fix(workflows) 修复摘要/README 解析、同步浅克隆竞态和 hanwckf 失败传播
- **最新运行结果**：
  - run `33959795219`（当前特性分支，统一构建）✅ 成功：Plan、`qualcommax-ipq807x` 全量固件编译、Persist state 均成功。
  - run `33971151213`（main，OpenWRT Packages Updater）✅ 成功：main/qt6/mt798x/qualcommax 全部成功。
  - run `33971446715`（main，Sync_Push）✅ 成功：Lede/Luci/Packages/VIKINGYFY/清理旧运行记录全部成功。
  - run `33960716537`（main，v2ray-geodata Updater）✅ 成功。
  - `fafc2e1` 推送后产生的特性分支 CI 尚待确认。

---

## 2. 必须遵守的项目约束（重要）

1. **不得 export `TARGET`、`HOST`、`BUILD`** 到任何 OpenWrt 相关进程（会泄漏进构建环境破坏编译）。
2. **全局并发组保持 `firmware-build-v2` 固定**，不要按分支/PR 加作用域。
3. **构建状态持久化**到 `IMMWRT_BUILD_STATE` Repository Variable（需 `secrets.ACCESS_TOKEN` PAT；`GITHUB_TOKEN` 不能写 Variable）。
4. 不要隐藏关键失败：禁止宽泛 `|| true`、丢弃 stderr、无条件成功兜底；覆写/补丁提交失败必须硬失败。
5. **不要回退用户未由自己创建的改动**；`.gitignore` 的用户改动（`.mimosa/`、`.zcode/`）保持不动。
6. 修改后验证顺序：YAML parse → 所有 `run:` 块 `bash -n` → patch `git apply --check` → 命名/SHA/路径/IO 契约 → `git diff --check`。
7. 不 commit/push/rebase/tag/触发远程 workflow/写 Release，除非用户明确要求且单独复核（**注：本 document 生成时已获用户授权提交+推送+触发一次 CI**）。
8. Windows 本地工具链：Python、gh、Git Bash（`C:/Program Files/Git/bin/bash.exe`）可用；本机无系统 `jq`、`rsync`（fixture 需在 Git Bash 内用函数替身）；PowerShell 多行 here-string 传 Git Bash 会破坏 `$` 转义，长脚本写临时文件再执行。

---

## 3. 本次分支改动内容（相对 origin/main 的 3 个提交）

### 3.1 `e51ca35` — config(ipq807x)

- `openwrt-configs/immortalwrt/ipq807x/01-base.seed`：
  - 移除 `CONFIG_SIGNED_PACKAGES=y`
  - 新增 `CONFIG_IB_STANDALONE=y`
- `02-pkgs.seed`：
  - 新增 `haproxy`、`simple-obfs-client`、`vlmcsd`、`unzip`、`coreutils-timeout`、`ucode-mod-math`、`luci-i18n-vlmcsd-zh-cn`
  - 移除 `nmap-full`、`smartdns-ui`、`luci-app-smartdns_INCLUDE_smartdns_ui`
- `03-passwall.seed`：
  - 新增 passwall + passwall2 的 `INCLUDE_Haproxy`、`INCLUDE_Simple_Obfs`
- `targets.json`：三个 target 补 `standard_packages_repo`/`standard_packages_branch`（mt798x=hanwckf；qualcommax/qualcommax-ipq807x=qualcommax）
- `README.md`：同步标准 feed 字段与显式注入行为说明

来源：用户提供的 `config (4).buildinfo`（RBR750 ipq807x 实际构建配置），已逐项对齐（去注释后 DIFF_CLEAR）。

### 3.2 `52c027e` — fix(workflows)（15 文件，+785/-397）

| 文件 | 要点 |
|---|---|
| `Sync_Push.yml` | 定向 fetch（替换 `git fetch --all`）；hanwckf 只取存在的 `openwrt-21.02`（修复 100% 失败 bug）；所有 push 改 askpass + `--force-with-lease`，移除 token URL；覆写失败硬失败；Qualcomm `blob:none`；删 watch/owner guard；固定 delete-workflow-runs commit |
| `OpenWRT_Packages_Updater.yml` | 动态矩阵 prepare（去重+白名单）；全步骤 `set -euo pipefail`；提交前 `diff --cached --check`；askpass+lease 推送 |
| `firmware-build-unified.yml` | 标准 packages feed SHA 检测；变更强制全量；plan/executor/persist-state 全链路标准 feed metadata；`CURR_SRC` 空值 guard；updater targets 按 target 解析 |
| `compile-firmware.yml` | 标准 feed inputs；构建前改写 `feeds.conf.default`；读 `feeds/packages` 实际 SHA；build-info 写入 |
| `compile-packages.yml` | 同上（SDK 路径），`steps.compile.outputs.standard_packages_sha` |
| `core` | 源码缓存（repo+branch 的 SHA-256 key）；`checkout_partial_code` 支持 `--warn-on-missing`（默认仍硬失败，已 fixture 验证） |
| `main.sh`/`qt6.sh` 等 | 严格模式；去重复 `-b 21.02 -b 18.06`；`modify.sh` 安全清理；`convert_translation.sh` 断链符号链接 |
| `v2ray-geodataUpdater.yaml` + patch | 固定 geoview 0.2.6+SHA；API digest 校验；patch blob 二次验证；lease 推送 release/main；资产白名单；修复 jq 多余括号 |

### 3.3 `12f0900` — fix(rust)

- 早期提交（本分支基线上），更新 Rust 包版本与构建脚本修复；非本次手改，保留即可。

### 3.4 `fafc2e1` — fix(workflows)

- `OpenWRT_Packages_Updater.yml`：插件来源摘要和 README 生成改为逐行 Bash 条件解析，避免 `set -euo pipefail` 下 `grep` 无匹配导致误失败。
- `Sync_Push.yml`：Lede/Luci/Packages 同步统一使用 `--filter=blob:none` 的非浅克隆，消除多次 fetch 修改 `.git/shallow` 的竞态。
- `Sync_Push.yml`：普通目标补丁/推送失败时记录失败并继续处理 `hanwckf` 覆写层，最后统一显式失败，不隐藏原始错误。
- 已验证全部 workflow YAML、95 个 `run:` 块、摘要/README 解析行为和 `git diff --check`。

---

## 4. CI 验证结论（已完成）

run `33959795219` 的新架构关键链路**已在真实环境验证通过**：

1. `Resolve packages updater targets` → `本次只更新插件 feed 分支: qualcommax` ✅
2. `Restore build state` → 从 `IMMWRT_BUILD_STATE` 读到 mt798x/qualcommax/qualcommax-ipq807x 三条记录 ✅
3. `Load targets & check changes` → 正确加载 `standard_packages_*` ✅
4. 标准 packages 检测：
   `🟠 [qualcommax-ipq807x] 标准 packages feed 变更: 无 → c3971cc` ✅
5. 路由决策：`标准 packages feed 已变更,强制全量编译` → `BUILD_MODE=firmware` → `compile-firmware` ✅
6. `Compile Firmware / qualcommax-ipq807x` ✅ 成功完成。
7. `Persist build state` ✅ 成功；`IMMWRT_BUILD_STATE` 中 `qualcommax-ipq807x.standard_packages_sha` 为 `c3971cc2a6d3150ae765fd331ce9f40bdde74e80`，与 `solarflows/packages@qualcommax` HEAD 一致。
8. 构建 artifacts `qualcommax-ipq807x-release`、`qualcommax-ipq807x-passwall`、build-info 和 published-state 均已生成。

main 上后续验证运行也已成功：Packages updater run `33971151213` 四个目标全成功；Sync_Push run `33971446715` 五个 job 全成功；geodata run `33960716537` 成功。

**仍待确认**：当前特性分支新增的 `fafc2e1` 推送后 CI，以及该提交是否能将本地 Rust 覆写同步到 `solarflows/packages@hanwckf`。

---

## 5. 已知风险 / 关注点（接手后优先检查）

1. **特性分支新增 CI 待确认**：`33959795219` 和 main 后续验证运行均已成功；推送 `fafc2e1` 后检查 updater/Sync_Push 是否成功，以及 `hanwckf` Rust 覆写是否生效。
2. **仓库名不一致**：git remote 是 `solarflows/AutoWorkflows.git`，实际仓库是 `AutoWorkFlows.git`。功能上 GitHub 转发，但建议后续 `git remote set-url origin https://github.com/solarflows/AutoWorkFlows.git`。
3. **`checkout_partial_code` 硬失败风险**：4 个生成脚本 99 处调用，路径均已抽查存在；新增 `--warn-on-missing` 逃生口，但活跃调用未加该标志。若上游删包/改名，feed 生成 job 会红。
4. **`v2ray-geodata`**：main 上 run `33960716537` 已成功，固定版本/SHA 校验和资产更新链路已得到真实运行验证。
5. **`Sync_Push`**：main 上 run `33971446715` 已真实成功；当前分支 `fafc2e1` 的 blobless fetch 和失败传播修改仍需推送后验证。
6. **未合并主线**：当前分支功能提交相对最新 main（`f7750c0`）ahead 4、behind 1，加上本次交接文档提交后分支总计 ahead 5，尚未开 PR/合入。合入前建议再确认 `IMMWRT_BUILD_STATE` 中 qualcommax（旧）与 qualcommax-ipq807x（新）命名空间隔离符合预期。
7. **Passwall 精简策略**：ipq807x 只保留 sing-box + rust-ss + ssr，剔除 xray/hysteria/naiveproxy/shadow-tls；`sdk.config` 未随 buildinfo 变更（它是独立清单，只列 Makefile 目录级包名）。

---

## 6. 常用命令速查（PowerShell，本机）

```powershell
# 查看 CI
gh run view 33959795219 --repo solarflows/AutoWorkFlows
gh run view 33971151213 --repo solarflows/AutoWorkFlows
gh run view 33971446715 --repo solarflows/AutoWorkFlows

# 查看 run 日志关键段
gh api repos/solarflows/AutoWorkFlows/actions/jobs/<jobid>/logs 2>&1 | Select-String -Pattern "标准 packages|BUILD_MODE|强制全量|error|Error"

# 验证全部 workflow
python -c "import yaml,sys; [print(f) for f in [] ]"  # 或用既有脚本

# 脚本语法
& 'C:/Program Files/Git/bin/bash.exe' -lc 'for f in .github/diy/openwrt-packages/core .github/diy/openwrt-packages/*.sh; do bash -n "$f"; done'

# 切 remote（建议）
git remote set-url origin https://github.com/solarflows/AutoWorkFlows.git
```

---

## 7. 决策记录（为什么这么做）

- **为何移除 `CONFIG_SIGNED_PACKAGES`**：buildinfo（权威运行配置）没有它；qualcommax 用 APK 格式，签名由构建时从 `.config`/SDK `Config-build.in` 自动探测 `CONFIG_USE_APK`，无需静态配置。
- **为何标准 feed 显式注入**：之前构建用哪个 `packages` feed 完全不可知（由各源码 `feeds.conf.default` 决定）；现在由 targets.json 指定 → plan 检测 SHA → 变更强制全量 → 写回状态，闭环可控。
- **为何 `--warn-on-missing` 默认不启用**：活跃 partial 路径全部存在，硬失败能保证漏包立刻暴露；逃生口留给未来可缺失的可选路径。
- **为何 geodata 固定 geoview 版本**：`latest` 不可复现且 SHA 无法预先验证；固定 0.2.6 + SHA 后可强制校验下载。

---

## 8. 交接待办清单

- [x] 观察 CI run `33959795219` 至完成；编译、产物和状态持久化均成功
- [x] 验证 main 上 Packages updater run `33971151213` 四个目标全部成功
- [x] 验证 main 上 Sync_Push run `33971446715` 全部 job 成功
- [x] 验证 main 上 v2ray-geodata run `33960716537` 成功
- [ ] 推送 `fafc2e1` 后检查特性分支 CI，并确认 `solarflows/packages@hanwckf` 的 Rust Makefile 变为 `PKG_RELEASE:=2` 且移除 `--config .../config.toml`
- [ ] 若特性分支 CI 失败：按 `docs/openwrt-build-pitfalls.md` 诊断，不改动未证实根因
- [ ] 建议把 remote 改为 `AutoWorkFlows.git`
- [ ] 与用户确认是否开 PR 合入 main（当前分支功能提交相对最新 main ahead 4、behind 1，含交接文档提交总计 ahead 5）
- [ ] 若需触发特性分支的 `Sync_Push`/`v2ray-geodata`，注意这些会推远端分支/写 Release，需用户授权