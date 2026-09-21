# 功能实现状态台账

回答"这件事做没做、验证到哪一步、为什么不做"的单一事实来源，避免同一问题反复讨论。

**维护流程**：改动使某行状态变化时，在同一提交内更新该行；证据用 run ID / commit SHA / 文件行，写不出证据的记 🟨 而不是 ✅；🚫 行不得无新证据重复提议，❓ 行在其选项上继续。

| 状态 | 含义 |
|---|---|
| ✅ | 已实现，真实运行验证过 |
| 🟨 | 已实现，仅本地校验 |
| ⬜ | 已确认要做，未实现 |
| ❓ | 待决：附选项，讨论不从头开始 |
| 🚫 | 已否决：保留理由，防止重复提议 |

最后核对：2026-09-19

---

## A. 缓存治理

| ID | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| C1 | 工具链快照命中即跳过重复 save | 🟨 | `compile-firmware.yml` `Check existing toolchain snapshot` | 修复前每轮固定报 `Unable to reserve cache`（内容寻址 key 不可覆盖，与配额无关） |
| C2 | 全量执行器收敛自己写入的 sdk-hostpkg 种子快照 | 🟨 | `compile-firmware.yml` `Purge stale SDK hostpkg snapshots` | 修复前该 namespace 只写不清理，每轮净增 0.5~1.7GB/target |
| C3 | 三个命名空间均为"每 target 最新 1 份" | ✅ | 两个 executor 各自的 purge 步骤 | 锚定正则 + 显式排除当前 key |
| C4 | 保存顺序保持 save → purge | 🚫 | pitfalls § Cache Quota and Eviction | 否决"先删后存"：会破坏"新快照保存成功后才删旧"的兜底 |
| C5 | 平台驱逐机制（配额驱动 + last-access 有序） | ✅ | run `35313768877` 配额时间线 | 平台不是乱删，但只认"最近是否被读过"，故写入方仍须自约束 |
| C6 | 可缓存路径逐项体量诊断 | 🟨 | `compile-firmware.yml` `📦 可缓存路径体量` | 为 C7 提供实测数据 |
| C7 | 裁剪 `dl/rustc` / `dl/cargo` / `tmp/go-build` | ❓ | 待决 1 | |
| C8 | 仓库缓存配额（10GB）逼近策略 | ❓ | 待决 2 | |
| C9 | 7 天未访问自动过期（低频 target） | ⬜ | 官方规则 | 目前仅靠每轮 restore 被动刷新 |
| C10 | SDK 与全量共享 ccache 命名空间 | ✅ | commit `b57d87d` | |

## B. Release 与产物

| ID | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| R1 | 固件目录排除 `*-sdk-*` / `*-imagebuilder-*` | ✅ | commit `ae76ca7` | 修复前 SDK/IB 混入固件 Release，致上传 43 分钟后 502 |
| R2 | Release 资产上传逐文件重试（3 次退避） | ✅ | commit `ae76ca7` | 覆盖固件、Passwall、SDK/IB、index.json |
| R3 | 空固件目录拒绝创建 Release | ✅ | `compile-firmware.yml` `Publish firmware release` | |
| R4 | SDK/IB 版本索引与保留数 | ✅ | `compile-firmware.yml`；`ARTIFACTS_KEEP_VERSIONS=7` | |

## C. 构建正确性

| ID | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| B1 | 工具链缓存命中时不得显式调子目录目标 | ✅ | commit `273fc79` | 显式 `make tools/compile toolchain/compile` 绕过 stamp → 重编 40+ 分钟 |
| B2 | `dl/` 残损清理限定 `-maxdepth 1` | ✅ | commit `273fc79` | 递归破坏 `dl/go-mod-cache`、`dl/cargo` |
| B3 | defconfig 后刷新工具链 stamp 时间戳 | ✅ | commit `530bb50` | 否则 stamp 早于 `.config`，缓存命中失效 |
| B4 | ccache 包装器变量级验证（`make val.*`） | ✅ | `compile-firmware.yml` `🔨 5. Build Firmware` | 校验通过才保存共享 ccache |
| B5 | persist-state 不使用 `merge-multiple` | ✅ | `firmware-build-unified.yml` | 同名 `build-info.json` 会互相覆盖 |
| B6 | 版本号解析 4 级纯字符串顺序 + make 表达式防御 | ✅ | `version-extraction.instructions.md` | exit 127 根因 |

## D. 上游同步与 Feed

| ID | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| U1 | `Sync_Push` 定向 fetch + `--force-with-lease` + askpass | ✅ | `Sync_Push.yml` | |
| U2 | `OpenWRT_Packages_Updater` 提交前 `diff --cached --check` | ✅ | `OpenWRT_Packages_Updater.yml` | trailing whitespace 仅 warning |
| U3 | `checkout_partial_code` 缺失路径硬失败 | 🚫 | `openwrt-packages/core` | 刻意为：硬失败才能让上游删包立刻暴露，不要改成告警 |
| U4 | geodata 固定 geoview 版本 + SHA256 校验 | ✅ | `v2ray-geodataUpdater.yaml` | `latest` 不可复现 |
| U5 | smartdns H2 补丁（qualcommax）+ 101 流槽位回收 | 🟨 | `packages/overwrite/qualcommax/net/smartdns/patches/100-fix-h2-hang.patch`（已同步，feed blob `79b8a106` 与本地逐字节一致）、新增 `101-reap-stalled-http2-streams.patch`（本地 GNU patch 在 48.4 源树 100→101 依次应用通过） | 101 修两处：① `http2_stream_close` 延迟关闭加 5s 时限（发送窗口永不恢复时回收 `active_local_streams` 槽位）；② 饱和连接以 `ECONNRESET` 返回，走 `_dns_client_send_one_packet` 的立即重建分支（裸 `ENOSPC` 只会 `prohibit=1` 屏蔽上游 60s）。上游 master 未修（开放 PR #2458/#2422 均未合），待真实构建验证 |
| U6 | mt798x smartdns bump 48.4 + 同补丁 | 🟨 | `openwrt-packages/patches/mt798x/0009-smartdns-bump-48.4.patch`（git→tarball 48.4，`PKG_HASH=b07abba9…`，与 qualcommax 同源同版本）、`openwrt-packages/overwrite/mt798x/smartdns/patches/{100,101}`（与 qualcommax 版逐字节一致）；已失效的 `temp-fix-smartdns-hash.patch` 移入 `patches_remove` | mt798x 的 smartdns 来自 `package/solarflows/smartdns`（pymumu 源，core 包不被 feeds 覆盖），此前停在 48.2 且无补丁——48.3 才引入流上限强制（`6f9da63`）故旧版症状隐蔽。**版本升级为手动控制**：唯一控制点 = 编辑 `0009` 的版本/哈希字段（mt798x 分支每轮被脚本全量重生成，直接改分支持久不了）；已验证 100/101 对 48.2 与 48.4 基线均可应用（GNU patch 行号偏移自动适配），故升级版本不阻塞补丁；pymumu Makefile 的 `Build/Prepare` 调用 `Default`，`smartdns/patches/` 会被构建系统自动应用。待真实构建验证 |
| U7 | `Sync_Push` VIKINGYFY 快照 tag + 强行同步 | 🟨 | `Sync_Push.yml` `sync_vikingyfy`：`保存未同步快照 tag` + `尝试变基` + `强同步并导出被丢弃提交` + `上传强同步被丢弃提交证据` | 背景：上游 `VIKINGYFY/immortalwrt` 在 2026-09-18 改写 sonic 提交（`304ac1defd`→`87b57bffcc`，author/parent 一致、committer date 不同，po 路径注释微调，旧提交仍可达=force push），致 run `35415796699` `同步VIKINGYFY` 变基 add/add 冲突失败。机制：**仅当触发上游 rebase（`has_update=true`）**时保存快照——**按内容去重**（先查同名 tag，再 `git ls-remote refs/tags/*` 搜索是否有任意远端 tag 已指向相同 commit，命中即跳过），无重复则打快照 tag `YYMMDD-beforerebase-<HEAD 短SHA8>` 并推远端（tag 指向 commit，完整保留现场含 `feeds.conf.default` 定制；与其它固定版本发版 CI 的 tag 命名区分）；rebase 冲突时不再 abort 退出，改 `reset --hard upstream/main` + 按序 `git cherry-pick -n` 重放本地专属提交（内容已被上游等效包含/冲突的自动跳过），被丢弃提交导出 `.patch` + `summary.txt` 并上传 artifact 供 debug。安全：`--force-with-lease` 仍保留（`retry_push` 用 `expected_remote_sha`），本地 sonic 旧提交会被跳过、feed 定制会保留。仅本地校验（YAML 解析 + `bash -n`，heredoc EOF 顶格确认），待真实 run 验证 |
| U8 | `custom-feed` 增量跳过模式下补丁幂等与包存在性检查 | ✅ | commit `27ba75d1`, run `35557363052`, run `35557361719` | 修复前增量跳过保留已打补丁文件致 patch --forward 报 Reversed (or previously applied) 退出 1；增加正向/反向 dry-run 双向探测与包目录存在性检查 |

## E. 文档体系

| ID | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| D1 | `handoff.md`（一次性交接文档） | 🚫 | 2026-09-19 核对后删除 | 不再重建：状态进本台账、结构进 `ci-flow.md`、故障进 pitfalls |
| D2 | 全局规则只写在 `AGENTS.md` | ✅ | 2026-09-19 实测自定义 agent 继承 AGENTS.md | 不要复制进 `.github/agents/*` 或 instructions |

## F. 固件功能配置（seeds）

| ID | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| F1 | ipq60xx / ipq807x 启用 SONiC fullcone | 🟨 | `ipq60xx/04-extras.seed`、`ipq807x/04-extras.seed`（后端 + LuCI）、两处 `02-pkgs.seed` 加中文包 | 必须显式 `=y`：IB 路径的 PACKAGES 只从 seed 提取，Kconfig `default` 不生效。待真实构建验证 |
| F2 | mt798x 无法使用 SONiC fullcone | 🚫 | 仓库 `solarflows/immortalwrt-mt798x@test` 为 `KERNEL_PATCHVER:=5.4`，无 `hack-6.18`；包带 `@LINUX_6_18` | 已有旧版 `fullconenat`/`kmod-ipt-fullconenat`（fw3），继续保留；不要提议给 mt798x 加 sonic |
| F3 | LuCI feed 耦合风险（sonic 补丁桥） | ❓ | `fullconenat-sonic/patches/apply-luci-feed.sh` 在补丁上下文不匹配时 `exit 1` | 见待决 4 |

## 待决

1. **裁 `sdk-hostpkg` 快照里的 `dl/rustc` / `dl/cargo` / `tmp/go-build`** — 单代 3.10GB，是稳态 8.51GB 的大头。选项：A 只裁 `dl/rustc`（只在 rust 重建时被读，可重新下载）；B 先看 C6 实测数据再定；C 不动。注意：改 path 列表会改 cache version，三处声明必须同步（`compile-packages.yml` restore + save、`compile-firmware.yml` save）。
2. **10GB 配额逼近** — 稳态 8.51GB/10GB，余量约 1.4GB。选项：A 提高仓库上限（~$2.8/50GB/月）；B 减量（联合待决 1）；C 维持现状靠平台 LRU 兜底。
3. **是否用 hooks 做确定性拦截** — 台账目前靠 `AGENTS.md` 指令，非强制。选项：A 不做（倾向，指令已够）；B 加 `SessionStart` 提醒；C `PreToolUse` 拦截 workflow 编辑（易误报）。
4. **SONiC fullcone 对 LuCI feed 的硬耦合** — `include/toplevel.mk` 的 `prepare-tmpinfo` 会调用 `apply-luci-feed.sh`，向 `feeds/luci` 的两个文件打补丁（`luci-base` 的 `rpcd/ucode/luci` 删一行、`luci-app-firewall` 的 `zones.js` 删一段）；补丁已应用则跳过，**上下文不匹配则 `exit 1` 直接中断构建**。而我们的 luci feed 是上游滚动的 `immortalwrt/luci`（`feeds.conf.default`，未经我们固化）。选项：A 接受风险，失败时按日志手修（当前）；B 在我们的 `Sync_Push` 里把 luci feed 固定到已验证的 commit（改 `feeds.conf.default` 的 luci 行）；C 向 fork 提上游反馈要求降耦合。

- `docs/ci-flow.md` 讲"怎么跑"，`docs/openwrt-build-pitfalls.md` 讲"为什么坏过"，本文件讲"现在到底有没有"。
