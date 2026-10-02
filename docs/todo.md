# 功能实现状态台账

回答"这件事做没做、验证到哪一步、为什么不做"的单一事实来源，避免同一问题反复讨论。

**维护流程**：改动使某行状态变化时，在同一提交内更新该行；证据用 run ID / commit SHA / 文件行，写不出证据的记 🟨 而不是 ✅；🚫 行不得无新证据重复提议，❓ 行在其选项上继续。

优先级定义：**P0** = 可能造成数据损坏/错误结果；**P1** = 确定性问题；**P2** = 性能与维护性优化。

| 状态 | 含义 |
|---|---|
| ✅ | 已实现，真实运行验证过 |
| 🟨 | 已实现，仅本地校验 |
| ⬜ | 已确认要做，未实现 |
| ❓ | 待决：附选项，讨论不从头开始 |
| 🚫 | 已否决：保留理由，防止重复提议 |

最后核对：2026-09-24

---

## A. 缓存治理

| ID | P | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|---|
| C1 | P2 | 工具链快照命中即跳过重复 save | 🟨 | `compile-firmware.yml` `Check existing toolchain snapshot` | 修复前每轮固定报 `Unable to reserve cache`（内容寻址 key 不可覆盖，与配额无关） |
| C2 | P2 | 全量执行器收敛自己写入的 sdk-hostpkg 种子快照 | 🟨 | `compile-firmware.yml` `Purge stale SDK hostpkg snapshots` | 修复前该 namespace 只写不清理，每轮净增 0.5~1.7GB/target |
| C3 | P2 | 三个命名空间均为"每 target 最新 1 份" | ✅ | 两个 executor 各自的 purge 步骤 | 锚定正则 + 显式排除当前 key |
| C4 | P2 | 保存顺序保持 save → purge | 🚫 | pitfalls § Cache Quota and Eviction | 否决"先删后存"：会破坏"新快照保存成功后才删旧"的兜底 |
| C5 | P2 | 平台驱逐机制（配额驱动 + last-access 有序） | ✅ | run `35313768877` 配额时间线 | 平台不是乱删，但只认"最近是否被读过"，故写入方仍须自约束 |
| C6 | P2 | 可缓存路径逐项体量诊断 | 🟨 | `compile-firmware.yml` `📦 可缓存路径体量` | 为 C7 提供实测数据 |
| C7 | P1 | 裁剪 `dl/rustc` / `dl/cargo` / `tmp/go-build` | ❓ | 待决 1 | |
| C8 | P1 | 仓库缓存配额（10GB）逼近策略 | ❓ | 待决 2 | |
| C9 | P2 | 7 天未访问自动过期（低频 target） | ⬜ | 官方规则 | 目前仅靠每轮 restore 被动刷新 |
| C10 | P2 | SDK 与全量共享 ccache 命名空间 | ✅ | commit `b57d87d` | |

## B. Release 与产物

| ID | P | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|---|
| R1 | P1 | 固件目录排除 `*-sdk-*` / `*-imagebuilder-*` | ✅ | commit `ae76ca7` | 修复前 SDK/IB 混入固件 Release，致上传 43 分钟后 502 |
| R2 | P1 | Release 资产上传逐文件重试（3 次退避） | ✅ | commit `ae76ca7` | 覆盖固件、Passwall、SDK/IB、index.json |
| R3 | P1 | 空固件目录拒绝创建 Release | ✅ | `compile-firmware.yml` `Publish firmware release` | |
| R4 | P1 | SDK/IB 版本索引与保留数 | ✅ | `compile-firmware.yml`；`ARTIFACTS_KEEP_VERSIONS=7` | |

## C. 构建正确性

| ID | P | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|---|
| B1 | P1 | 工具链缓存命中时不得显式调子目录目标 | ✅ | commit `273fc79` | 显式 `make tools/compile toolchain/compile` 绕过 stamp → 重编 40+ 分钟 |
| B2 | P1 | `dl/` 残损清理限定 `-maxdepth 1` | ✅ | commit `273fc79` | 递归破坏 `dl/go-mod-cache`、`dl/cargo` |
| B3 | P1 | defconfig 后刷新工具链 stamp 时间戳 | ✅ | commit `530bb50` | 否则 stamp 早于 `.config`，缓存命中失效 |
| B4 | P1 | ccache 包装器变量级验证（`make val.*`） | ✅ | `compile-firmware.yml` `🔨 5. Build Firmware` | 校验通过才保存共享 ccache |
| B5 | P1 | persist-state 不使用 `merge-multiple` | ✅ | `firmware-build-unified.yml` | 同名 `build-info.json` 会互相覆盖 |
| B6 | P1 | 版本号解析 4 级纯字符串顺序 + make 表达式防御 | ✅ | `version-extraction.instructions.md` | exit 127 根因 |
| C7 | P1 | 编译后 custom-feed 追平重编（全量 + SDK 增量） | 🟨 | `compile-firmware.yml` / `compile-packages.yml` `🔄 Rebuild on feed update`（`validate-workflows.py` 全过：YAML + 97 bash 块 + 指纹回归）；待真实 run 验证 | 编译成功后触发 custom-feed 更新本 target 分支并等待完成，`ls-remote` 对比 HEAD 前进则 fetch+reset 拉新 feed 原地增量重编一轮（最多 1 轮，再更新留待下次构建），防构建周期内 feed 更新没跟上。产物只保留最终轮（打包/发布/缓存保存均在重编之后）。SDK 路径按 feed 目录 tree SHA 对比变更包 clean 强制失效（U12 教训：同版本内容变更不可依赖 stamp）+ 硬链接 feed 重新复制；全量路径依赖 `STAMP_PREPARED` 内嵌 `find_md5` 哈希自动拾取（已对照 `solarflows/immortalwrt-mt798x@test` `include/package.mk` 验证）。追平触发/等待/拉取失败仅告警跳过（首轮产物仍自洽）；重编失败硬失败（bin/ 已混入新旧产物）且缓存保存以 `outcome != 'failure'` 联动跳过。`skip_upstream=true` 时经 `skip_feed_catchup` 接线跳过 |
| C8 | P2 | mt798x 默认禁用（`disabled: true`）+ 清理其 Actions Cache | 🟨 | `targets.json` mt798x 条目、`firmware-build-unified.yml` 两处 jq 过滤（`Resolve packages updater targets` / `Load targets & check changes`）；cache 清理见本地终端执行记录 | 上游 `solarflows/immortalwrt-mt798x@test` 停止维护，设备已转普通 AP/路由，固件功能稳定。`all`/`both`/周日 cron 不再构建 mt798x、不再触发其 feed 更新；显式 `target=mt798x` 保留手动构建能力。seed/overlay/补丁/custom-feed 分支全保留，`IMMWRT_BUILD_STATE` 旧条目无害保留 |
| C9 | P2 | dispatch 输入裁剪：`cache_strategy` 5 选项 → `clean_cache` 布尔；删 `no-cache` 模式 | 🟨 | 三个 workflow + `validate-workflows.py` 残留 token 检查（本地全绿）；smart 默认路径已真实 run 验证（run `37017884610`）；待 clean_cache=true 路径验证 | `clean_cache=true` = 旧 `clean-all` 语义（跳过全部 restore、toolchain hash 加 force 前缀、plan 强制全量路由）；`clean-toolchain`/`clean-ccache` 中间态与 `no-cache` 不持久化模式移除（历史 run 全为默认值，从未单独使用）；`sdk-packages` 保留（跳过 upstream-sync 等待等 3 处真实消费）。save/purge 不再按策略过滤（smart 与 clean_cache 均维护快照） |
| C10 | P1 | `firmware-repack` 手动强制 SDK+IB 增量组装固件 | 🟨 | `firmware-build-unified.yml`（dispatch 选项 + probe + 决策分支 + repack_mode 落盘）、`compile-packages.yml`（`matrix_repack_mode` 输入 + 5 个 IB 步骤条件放行 + 纯组装 build-info 不回写指纹）；待真实 run 验证 | 前史：f3d11091 的 `sdk-config` 选项从未接线，6e67204 误删后用户报无法手动出增量固件；e7f2cf0 恢复时误实现为 sdk.config 全集编译（run 37042782304 实证数小时，已取消）。最终语义（复用 smart 增量逻辑）：有变更包 → SDK 只编译变更集后 IB 组装；无变更 → 空集纯 IB 重组装（最快）；config/source 漂移仅 notice；SDK/IB 缺失回退全量。纯组装不回写指纹基线与 deferred（persist 哨兵 `__KEEP__`），`sdk-packages`（仅编译包不组装固件）保留 |

## D. 上游同步与 Feed

| ID | P | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|---|
| U1 | P1 | `upstream-sync` 定向 fetch + `--force-with-lease` + askpass | ✅ | `upstream-sync.yml` | |
| U2 | P1 | `custom-feed` 提交前 `diff --cached --check` | ✅ | `custom-feed.yml` | trailing whitespace 仅 warning |
| U3 | P1 | `checkout_partial_code` 缺失路径硬失败 | 🚫 | `openwrt-packages/core` | 刻意为：硬失败才能让上游删包立刻暴露，不要改成告警 |
| U4 | P1 | geodata 固定 geoview 版本 + SHA256 校验 | ✅ | `geodata-updater.yml` | `latest` 不可复现 |
| U5 | P1 | smartdns H2 补丁（qualcommax）+ 101~105 完整修护链 | 🟨 | `upstream-sync/overlay/packages/qualcommax/net/smartdns/patches/{100,101,102,103,104,105}`（本地 git apply 在 Release48.4 源树 100→105 依次应用全部通过） | 补丁链完整修护：① 100：ENOSPC 重置连接 + 死亡连接直接销毁流；② 101：重构延迟关闭逻辑，5s 超期与不可恢复写错误优先清理并回收 `active_local_streams`，饱和连接抛 `ECONNRESET` 触发即时重连；③ 102（PR #2458+扩充）：避免 HTTP 429/502/503/504 瞬态错误设置 `prohibit=1` 禁用上游 60s 引发连锁卡死（czw.lan 实机日志证实 doh.pub 频繁 429/502 致全部 DoH 封禁）；④ 103（commit `b59606ea`）：HTTP2/QUIC 轮询循环增加 `_dns_client_process_guard` 避免重试回调提前释放 socket 导致 UAF 崩溃/卡死；⑤ 104（commit `e01b9385`）：`request_pending` 哈希桶由 16 扩至 4096，消除高并发下的锁竞争；⑥ 105：修复 `package/openwrt/files/etc/init.d/smartdns` 中 `enable_auto_update` 的 `grep -F` 正则转义缺陷与 `updatefiles()` 期间 `restart_crond` 自杀调用，解决每日 5 点自动更新后 smartdns 进程消失的问题。初版 105 因 fake diff 行（`-return`/`+return`）无法应用，已基于 Release48.4 源树重新生成。待真实构建验证 |
| U6 | P1 | mt798x smartdns bump 48.4 + 同补丁链 | 🟨 | `custom-feed/patches/mt798x/0009-smartdns-bump-48.4.patch`（git→tarball 48.4，`PKG_HASH=b07abba9…`，与 qualcommax 同源同版本）、`custom-feed/overlay/mt798x/smartdns/patches/{100,101,102,103,104,105}`（与 qualcommax 版逐字节一致）、`custom-feed/patches/mt798x/0007-fix-smartdns.patch`（conffiles 扩充，mt798x 专属）；已失效的 `temp-fix-smartdns-hash.patch` 移入 `patches-remove` | mt798x 的 smartdns 来自 `package/solarflows/smartdns`（pymumu 源，core 包不被 feeds 覆盖），此前停在 48.2 且无补丁——48.3 才引入流上限强制（`6f9da63`）故旧版症状隐蔽。**版本升级为手动控制**：唯一控制点 = 编辑 `0009` 的版本/哈希字段（mt798x 分支每轮被脚本全量重生成，直接改分支持久不了）；已验证 100~105 对 48.4 基线均可无偏移应用，故升级版本不阻塞补丁；pymumu Makefile 的 `Build/Prepare` 调用 `Default`，`smartdns/patches/` 会被构建系统自动应用。待真实构建验证 |
| U7 | P1 | `upstream-sync` VIKINGYFY 声明式同步与快照安全推送（方向 1） | 🟨 | `upstream-sync.yml` `sync_vikingyfy`：以 `upstream/main` 声明式基线重置 + 纯补丁应用 + 内容树比对跳过空推送 + 快照 tag 保护 + `--force-with-lease` | 彻底废除旧的 `LOCAL_COMMITS` 累积 cherry-pick 与变基循环，避免已剔除补丁死灰复燃与上游改写时的变基地狱；与 `sync_lede`/`sync_luci`/`sync_packages` 对齐为统一的声明式架构 |
| U8 | P1 | `custom-feed` 增量跳过模式下补丁幂等与包存在性检查 | ✅ | commit `27ba75d1`, run `35557363052`, run `35557361719` | 修复前增量跳过保留已打补丁文件致 patch --forward 报 Reversed (or previously applied) 退出 1；增加正向/反向 dry-run 双向探测与包目录存在性检查 |
| U10 | P1 | `custom-feed` 跨仓库多文件补丁部分应用状态修复 | ✅ | commit `ed35aabb`+`e4d38328`，run `35755020516`（全量 5/5 success）、run `35755197154`（增量模式 success，0006/0007 幂等跳过且无 .rej 残留）；本地 GNU patch 2.7.6 实测 6/6 用例通过 | 修复前 `0006-filebrowser.patch` 跨 `immortalwrt/packages` 与 `immortalwrt/luci` 两仓库，增量模式下前者重拉（未打补丁）后者跳过（已打补丁），整体双向探测双失败误判真实冲突，连续 3 次 run 失败（`35633843900`/`35681463052`/`35752106631`）。修复：① `apply_patch_file` 用 awk 按 `diff --git` 头拆分为单文件补丁逐个走双向探测（单文件内不会部分应用），失败分支即时清理 `.rej`/`.orig`（否则被提交前检查拦截，见 run `35754763032` 教训）；② `0006` 拆分为 `0006-filebrowser` + `0007-luci-app-filebrowser` 各对应一个包。注意：GNU patch `--forward` 对 reversed hunk 也写 `.rej` 且中止后续文件，故 `.rej` 检测不可行（本地实测推翻）；awk 段头须兼容无 `diff --git` 头的传统格式（`7279cba0`，否则 `fix-shadowsocksr-libev-configure.patch` 被静默丢弃，曾致 feed mt798x 分支 Fixup 段丢失、run `35757189235` shadowsocksr-libev 构建失败） |
| U11 | P1 | mt798x rust 工具链修复（vendor .orig + GCC 8.4 flag）| ✅ | commit `bb1e3120`（rust Makefile Host/Patch，openwrt/packages#27485/#27487）、commit `eacc826f`（rust-values.mk `-mno-outline-atomics` 加 GCC>=10 条件），run `35826391595` 证实 aws-lc-sys C 代码编译通过 | 两层根因：① `scripts/patch-kernel.sh` 删 `*.orig` 与 rust tarball vendor 自带 `Cargo.toml.orig` 冲突（上游已知，overlay rust Makefile 覆盖 Host/Patch 跳过清理）；② overlay `rust-values.mk` aarch64 无条件 `RUSTC_CFLAGS:=-mno-outline-atomics`（GCC 10+ 选项）毒死 21.02 GCC 8.4 的所有 target 侧 C 依赖（aws-lc-sys 与 ring 同样中招——这解释了为何换后端无效）。教训：`TARGET_CFLAGS` 污染是系统性问题，不是单个 crate 的问题 |
| U12 | P1 | mt798x passwall 启用 ss-rust（shadowsocks-crypto 0.8.0 后端 bug 绕过）| ✅ | commit `6933e334`（seed：passwall INCLUDE_Shadowsocks_Rust_Client=y + sslocal=y/ssserver=m + sdk.config）、commit `3320805b`（100-disable-broken-crypto-backend.patch 纯 Rust fallback + PKG_RELEASE=2），run `35834497780` success，产物 `shadowsocks-rust-sslocal_1.25.0-2_aarch64_cortex-a53.ipk` | 本地 cargo 复现实证：shadowsocks-crypto 0.8.0 的 ring 与 aws-lc 后端分支均有发布 bug（ring 分支仅改名导入未定义 Aes128Gcm 类型，aws-lc 分支同样 E0432），唯一可编译路径是纯 Rust fallback（删除三处 `shadowsocks-crypto/aws-lc` feature）。附带发现：feed Makefile 变更不触发 prepare 重跑（stamp 机制），PKG_RELEASE bump 是可靠失效手段。纯 Rust 实现性能略低但无 C 代码，天然规避 GCC 8.4 兼容问题 |
| U9 | P2 | Fork 分支自动化补丁指纹追踪与 Revert 机制（方向 2 储备） | ❓ | 见待决 5 | 针对需严格保留下游线性历史的分支，通过 CI 追踪补丁清单并自动生成 revert 提交。目前 VIKINGYFY 选用方向 1（声明式），本方案作为储备设计 |

## E. 文档体系

| ID | P | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|---|
| D1 | P2 | `handoff.md`（一次性交接文档） | 🚫 | 2026-09-19 核对后删除 | 不再重建：状态进本台账、结构进 `ci-flow.md`、故障进 pitfalls |
| D2 | P2 | 全局规则只写在 `AGENTS.md` | ✅ | 2026-09-19 实测自定义 agent 继承 AGENTS.md | 不要复制进 `.github/agents/*` 或 instructions |

## F. 固件功能配置（seeds）

| ID | P | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|---|
| F1 | P2 | ipq60xx / ipq807x 启用 SONiC fullcone | 🟨 | `ipq60xx/04-extras.seed`、`ipq807x/04-extras.seed`（后端 + LuCI）、两处 `02-pkgs.seed` 加中文包 | 必须显式 `=y`：IB 路径的 PACKAGES 只从 seed 提取，Kconfig `default` 不生效。待真实构建验证 |
| F2 | P2 | mt798x 无法使用 SONiC fullcone | 🚫 | 仓库 `solarflows/immortalwrt-mt798x@test` 为 `KERNEL_PATCHVER:=5.4`，无 `hack-6.18`；包带 `@LINUX_6_18` | 已有旧版 `fullconenat`/`kmod-ipt-fullconenat`（fw3），继续保留；不要提议给 mt798x 加 sonic |
| F3 | P1 | LuCI feed 耦合风险（sonic 补丁桥） | ❓ | `fullconenat-sonic/patches/apply-luci-feed.sh` 在补丁上下文不匹配时 `exit 1` | 见待决 4 |

## G. 包粒度增量编译（按需编译演进计划）

设计文档：`docs/pkg-incremental-build.md`（P1/P2/P3 全貌与数据流）

| ID | P | 项目 | 状态 | 证据 | 备注 |
|---|---|---|---|---|---|
| G1 | P2 | 移除 sdk-cache-lookup 冗余预查步骤 | ✅ | commit `4c0d45c4`，run `35861454202` | 修复前每次 run 先预查 SDK 缓存再被正式 restore 覆盖 |
| G2 | P2 | SDK 编译前屏蔽 kmod 包（防内核全模块重编） | 🟨 | commit `455421e0`，`compile-packages.yml` `🔒 Freeze kernel modules` | 修复前 SDK `.config` 保留 `CONFIG_PACKAGE_kmod-*=y`，任一 make 触发 stale-stamp 内核重编摧毁预编译 kmod ipk（ipq807x 根因，见 pitfalls） |
| G3 | P2 | 包级指纹变更检测（plan 侧） | 🟨 | `firmware-build-unified.yml` `Load targets & check changes`（tree SHA 版，2026-09-26 重构） | custom feed 顶层目录 tree SHA 对比（内容寻址，上游无关提交不再触碰指纹）；空集撤销 feed 变更信号。前史：`1dad4519` lock 逐包 commit 方案 → run `36130960021` 键错配、run `36211341719` 锚上游 HEAD 误报（tailscale 被 rsync/banip 翻转），待构建验证 |
| G4 | P2 | plan 下传变更包子集 + sdk.config 交集 | 🟨 | commit `87473989`（2026-09-26 变更包来源扩源） | 变更包 ∩ sdk.config；有包在 sdk.config 之外→升级全量（SDK 无该包目录）。集合来源 = custom feed Δ ∪ 标准/上游 feed Δ'（剔除被 custom feed 覆盖的包），待构建验证 |
| G5 | P2 | 逐包编译数据采集与报表 | 🟨 | commit `1dad4519`，`compile-packages.yml` 编译循环 | wall_sec/exit/compile_time/version/artifacts；报表写 step summary |
| G6 | P2 | 状态回写闭环（feed_trees/feeds_sha 字段） | 🟨 | `persist-state` merge 步骤（2026-09-26 重构） | executor 记录 custom feed 目录 tree SHA（`git ls-tree`）+ 各 feed 实际消费 commit（`rev-parse`）→ build-info.json → IMMWRT_BUILD_STATE；persist-state 同时清除旧 `.packages` 字段。前史：`1dad4519` `.packages` 逐包上游 commit 方案因锚上游 HEAD 误报废弃（run `36211341719`），待构建验证 |
| G7 | P2 | IB 组装参数由 plan 下传 | 🟨 | commit `87473989`，`run-sdk-ib` 传 `ib_packages`/`ib_profiles` | 为空时 executor 回退 seed 提取（向后兼容） |
| G8 | P2 | P2：SDK/IB 文件解析上移 plan | 🟨 | commit（本组提交），`firmware-build-unified.yml` `Decide build mode` 提取 `selected.json` → `run-sdk-ib`/`run-packages` 新 matrix 字段；`compile-packages.yml` `Resolve SDK file name`/`Resolve IB file` 改为透传（保留本地回退） | plan 已用 `probe_index` 校验 file/sha256/source_sha 与资产存在性；executor 不再自行选文件 |
| G9 | P1 | sdk-ib 真实构建验证（变更包子集 + IB 注入） | ⬜ | 无 run 证据 | 验证项见 `pkg-incremental-build.md` § 待验证项：smart 无变更跳过 / sdk.config 之外变更包升级全量 / P2 透传路径 |
| G10 | P2 | PKG_ARTIFACTS 采集时机修复 | 🚫 | `compile-packages.yml` 编译循环（`1dad4519` 起即在 `make compile` 之后 `find`，注释「编译后查询」） | 误判：代码自 1dad4519 起已正确放在编译后（2026-09-24 复查确认） |
| G11 | P2 | 上游 feeds 变更检测（luci/routing/telephony/video） | 🟨 | 本提交，`firmware-build-unified.yml` plan 侧 | 解析源码分支 `feeds.conf.default`（有锁分支按锁、无锁按默认 HEAD）→ ls-remote 比 state.feeds_sha → compare 包级 diff → 剔除被 custom feed 覆盖的包（scripts/feeds 本地优先语义）；diff 不可测回退全量。修复此前上游 feeds 完全漏检 |
| G12 | P1 | IB 组装两阶段包选择（seed 请求 vs IB 实际索引） | 🟨 | 本提交，`compile-packages.yml` `Build firmware via IB` | run `36211341719` ipq807x 实证：seed `=y` 请求含全量构建 kconfig 丢弃的包（内核 6.18 触发器内建，5 个 led kmod 无产出），apk `unable to select packages` 致 IB 失败；全量固件 config.buildinfo 同样不含这些包。修复：apk 选择失败→解析缺失清单→剔除直接请求项重试（≤3 轮，warning），依赖缺失硬失败。待回归验证 |
| G13 | P1 | plan 巨型 step 拆分（GitHub 21000 字符上限） | 🟨 | 本提交，`firmware-build-unified.yml` plan 三 step | push/dispatch 422 `Exceeded max expression length 21000`（run `36222463066`，本地 YAML/bash -n 不报错）；拆为 Load targets(11231) / Detect package-level(9569) / Extract IB & finalize(3303)，中间结果经 `/tmp/target_stage.jsonl`→`/tmp/target_pkg_stage.jsonl`→`target_changes.json` 传递。详见 pitfalls § 单 step run: 块超 21000。待 dispatch 验证 |
| G14 | P1 | 产物发布归一：发布 tag 统一 + 同包多版本收敛 | 🟨 | 本提交，`targets.json` + 两个 executor Publish 步骤 + plan prefix 默认值 | ① mt798x 补 `passwall_tag: packages-mt798x`（此前用默认 `packages`，与 ipq 系 `packages-<target>` 不统一）；② 两个 Publish 步骤末尾加同包收敛：按 apk/ipk 文件名解析包名分组，按 updated_at 留最新 3 版（含 .sha256），公钥/无版本结构文件永不清，失败只告警（修复 packages-ipq807x luci-app-passwall 3 版共存类无限累积）；③ 固件 release tag 统一 `<target>-<version>`：plan 侧 prefix 默认值 `""`→`.target`（mt798x 此前裸 `V*` 与 ipq 系不统一；同仓库多 target 必须分开 release 防同名资产覆盖）；④ 一次性清理：删陈旧 tag（artifacts-qualcommax、artifacts-qualcommax-ipq807x、packages-qualcommax-ipq807x、packages + 孤儿 git tag ib/sdk-qualcommax）。待下轮发布验证 |
| G15 | P1 | 统一 input_trees 指纹 + deferred 搁置路由 + run-sdk 合并 | 🟨 | 本提交，plan step B 重构 + 两个 executor + persist-state | ① 逐包 tree SHA 短哈希（7 位）扩展到标准/上游 feed（compare API 退役，免疫 250 上限），seed 引用过滤（方案 A）控制 state 体积；② outside-sdk 变更不再升级全量 → deferred_pkgs 搁置累计（等手动 full/源码变更收编），砍掉最大不必要 CI 触发源（run 36363278098: v2ray-geodata 触发 3 目标全量）；③ run-sdk-ib/run-packages 合并为单 run-sdk job（build_sdk_ib 字段区分 IB 组装）。首轮需全量建新基线。待构建验证 |

## 待决

1. **裁 `sdk-hostpkg` 快照里的 `dl/rustc` / `dl/cargo` / `tmp/go-build`** — 单代 3.10GB，是稳态 8.51GB 的大头。选项：A 只裁 `dl/rustc`（只在 rust 重建时被读，可重新下载）；B 先看 C6 实测数据再定；C 不动。注意：改 path 列表会改 cache version，三处声明必须同步（`compile-packages.yml` restore + save、`compile-firmware.yml` save）。
2. **10GB 配额逼近** — 稳态 8.51GB/10GB，余量约 1.4GB。选项：A 提高仓库上限（~$2.8/50GB/月）；B 减量（联合待决 1）；C 维持现状靠平台 LRU 兜底。
3. **是否用 hooks 做确定性拦截** — 台账目前靠 `AGENTS.md` 指令，非强制。选项：A 不做（倾向，指令已够）；B 加 `SessionStart` 提醒；C `PreToolUse` 拦截 workflow 编辑（易误报）。
4. **SONiC fullcone 对 LuCI feed 的硬耦合** — `include/toplevel.mk` 的 `prepare-tmpinfo` 会调用 `apply-luci-feed.sh`，向 `feeds/luci` 的两个文件打补丁（`luci-base` 的 `rpcd/ucode/luci` 删一行、`luci-app-firewall` 的 `zones.js` 删一段）；补丁已应用则跳过，**上下文不匹配则 `exit 1` 直接中断构建**。而我们的 luci feed 是上游滚动的 `immortalwrt/luci`（`feeds.conf.default`，未经我们固化）。选项：A 接受风险，失败时按日志手修（当前）；B 在 `upstream-sync.yml` 里把 luci feed 固定到已验证的 commit（改 `feeds.conf.default` 的 luci 行）；C 向 fork 提上游反馈要求降耦合。
5. **方向 2 备选架构：Fork 分支自动化补丁指纹追踪与 Revert 机制** — 针对未来若有需要严格保留下游 commit 历史的分支：CI 维护补丁应用清单，当检测到本地补丁删除时自动触发 `git revert` 逆向消除，避免手写反向补丁与变基地狱。目前作为备选架构方案储备，未来如需持久化分支历史时启用。

- `docs/ci-flow.md` 讲"怎么跑"，`docs/openwrt-build-pitfalls.md` 讲"为什么坏过"，本文件讲"现在到底有没有"。

## 进展记录

> 只追加、不修改、不删除。状态翻转而非新建条目时记录一行（日期 + ID + 旧→新 + 证据）；新建条目直接进表，不在此记录。2026-09-24 前的关键翻转为回填。

- 2026-09-21：U8 ⬜→✅（commit `27ba75d1`，run `35557363052`/`35557361719`）。
- 2026-09-23：U10 ⬜→✅（commit `ed35aabb`+`e4d38328`，run `35755020516` 全量 5/5、run `35755197154` 增量幂等跳过）。
- 2026-09-23：U11 ⬜→✅（commit `bb1e3120`+`eacc826f`，run `35826391595` aws-lc-sys 编译通过）。
- 2026-09-23：U12 ⬜→✅（commit `6933e334`+`3320805b`，run `35834497780`，产物 `shadowsocks-rust-sslocal_1.25.0-2_aarch64_cortex-a53.ipk`）。
- 2026-09-23：G1 ⬜→✅（commit `4c0d45c4`，run `35861454202`）；G3/G5/G6 ⬜→🟨（commit `1dad4519`，无 run 证据保持 🟨）。
- 2026-09-24：G10 🚫（新证据：复查确认代码自 `1dad4519` 起已正确放在编译后，原报告为误判）。
- 2026-09-24：improvement-ledger skill Mount 挂载——全表注入 P 列（P0/P1/P2 定义见文首），新增本进展记录区；AGENTS.md 已有 Project Status 段，按第 0 步规则不覆盖、未改动。
- 2026-09-25：G3/G4/G6 缺陷修复（状态保持 🟨 待验证）：run `36130960021` 实证两处逻辑陷阱——① lock 查询键 target/feed 分支名错配（plan + compile-packages，qualcomm 双目标必然 miss 回退全量）；② compile-firmware 全量路径不写逐包基线（基线缺失死锁，mt798x 误报 17 包全量，真实变更仅 passwall/naiveproxy/sing-box 3 包且均在 sdk.config 内）。修复后待 smart 触发实证 G9。
- 2026-09-26：G3/G4/G6 指纹源重构 + G11 新增（均 🟨 待验证）：run `36211341719` 实证 lock 逐包指纹锚上游仓库 HEAD——openwrt/packages master 的 rsync/banip 无关提交翻转 tailscale 指纹致 mt798x 误判全量（net/tailscale 自 09-02 未动）。重构为构建输入真值锁：custom feed 顶层目录 tree SHA（内容寻址）+ feeds.conf.default 上游 feeds HEAD/compare 包级 diff（剔除 custom feed 覆盖，scripts/feeds 本地优先），state 字段 `packages`→`feed_trees`/`feeds_sha`；标准 feed 变更不再一刀切全量，折入变更包集合走 sdk.config 交集路由。验证工具沉淀为可复用脚本 `.github/scripts/validate-workflows.py`（YAML+bash -n+语义回归），已挂载到 workflow-agent-common 与 orchestrator/executor agent。
- 2026-09-26：G12+G13 新增（🟨 待验证）：① run `36211341719` ipq807x sdk-ib 首跑失败——IB `unable to select packages`（5 个 led kmod），根因 seed `=y` 原文提取含 kconfig 丢弃包（内核 6.18 触发器内建，全量 config.buildinfo 同样不含），修复为 IB 两阶段包选择（apk 权威解析缺失→剔除重试）；② run `36222463066` push 422 `Exceeded max expression length 21000`——单 step run: 块超平台上限（本地不报错），plan 拆为三 step（中间结果 JSONL 传递），验证脚本补 2b 大小告警。
- 2026-09-26：G13 拆分首跑失败修复（run `36226606223`）：stage 落盘 `jq -n` 对多行 filter 字面量保留 pretty-print 多行输出（每 target 22 行碎片），下游 `while read` 读出非法 JSON 致 finalize step 失败。本地 jq 1.8.2 逐字节复现实证；修复 = 两处落盘加 `-c`（紧凑单行 JSONL），验证脚本补 4h 静态回归（`jq -n` 无 `-c` 写 `.jsonl` 即报错），pitfalls 新增条目。
- 2026-09-26：G14 新增（🟨 待验证）：产物发布归一——mt798x 发布 tag 统一为 `packages-mt798x`；两个 executor Publish 步骤加同包保留 3 版收敛（jq 分组语义本地实证：apk/ipk 双格式、公钥/无版本结构保护）；待下轮发布验证后执行一次性远端清理（4 个陈旧 tag）。
- 2026-09-28：G15 新增（🟨 待验证）：统一 input_trees 指纹 + deferred 搁置路由 + run-sdk 合并。讨论收敛：包选择优先级（scripts/feeds 本地优先，L548 实证）是变更检测语义正确性的根基；逐包 tree SHA 短哈希（7 位）从 custom feed 扩展到标准/上游 feed（compare API 退役，免疫 250 文件上限），seed 引用过滤（方案 A）+ 短哈希控制 state 体积（实测 10KB→预计 ~25KB，48KB 上限内）；outside-sdk 变更从"升级全量"改为 deferred_pkgs 搁置累计（v2ray-geodata 类数据包更新不再触发 3 目标全量，等手动 full/源码变更收编）；run-sdk-ib/run-packages 合并为单 run-sdk job（本就同一 reusable workflow，仅 build_sdk_ib 布尔差异）。验证脚本新增 4i（短哈希同规则）/4j（deferred 分流）回归项。首轮需全量重建基线（input_trees/std_input_trees/upstream_input_trees 新字段）。
- 2026-09-29：G15 指纹管道四处缺陷修复（状态保持 🟨 待验证）：run 36519189440 全绿但闭环验证发现基线恒空——① plan 侧 fetch_pkg_trees 用 `gh api --jq --argjson`（gh 不支持，同文件 run list 查询处已记录的坑重蹈）兜底恒空 → 旧基线全包误判删除（mt798x 42 个假变更包）；② executor 侧 `ls-tree -r` 缺 `-t`（递归默认只出 blob 行）→ std/upstream_input_trees 恒空（ipq 系每轮"无逐包基线"全量死循环）；③ FTREES jq `map(. + {depth:...})` 数组加 object 语法错误（被空输入掩盖）；④ INPUT_TREES 非递归顶层键集与 plan 侧深度≤2 不对齐 → 每轮 11 个幽灵子目录键误判新增滞留 deferred。修复：SHORT 纯数字内嵌双引号表达式 + `ls-tree -r -t` + 深度内联 select + INPUT_TREES 统一深度≤2；删除死代码 ls_tree_short（未调用且 --directory 为无效选项）；本地实证两侧 53 键逐项一致（键集+SHA）；验证脚本 4c 更新为深度管道 + 新增 4k（FTREES 语义）/4l（命令防退化静态检查）。修复后首轮需全量重建基线（含幽灵子目录键，两侧对齐后语义自洽）。
- 2026-09-29：G15 追平闸门 + deferred 清零修复（状态保持 🟨 待验证）：run 36557139597（full）实证两处缺陷——① 追平重编闸门比较 commit SHA，而 custom-feed 每次运行 README 时间戳必提交 → feed HEAD 必前进 → 每次构建后空转一轮 make（ipq60xx：diff 仅 README+lock，313 个 stamp 检查 0 真实编译 224s；三 target 全中）；修复 = 闸门改用包目录 tree 表 diff（复用 input_trees 内容寻址语义，BEFORE 构建起点 / AFTER 追平后现算，变更包目录非空才重编；仅元数据变更只更新 packages_sha 跳过；双向 < / > 计入删除）。本地四场景实测（元数据跳过 / 包变更 / 删除 / 新增）；初版 grep 漏 diff 前缀空格（永不匹配 → 恒跳过 = 真实包变更静默漏检，比空转更糟）被本地测试拦截后修正；验证脚本新增 4m（语义 + 静态防退化）。② persist 合并 deferred_pkgs 的 length>0 守卫丢弃全量收编清零信号（mt798x 28 条 Bug A 时代脏 deferred 全量后仍滞留）→ 改无条件写入（空数组 = 清零是合法语义，与指纹字段空 = 计算失败的保守保留语义不同）。
