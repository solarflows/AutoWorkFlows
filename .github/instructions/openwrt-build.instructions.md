---
description: "修改 OpenWrt/ImmortalWrt GitHub Actions 构建、缓存、SDK、ImageBuilder、固件发布或错误诊断时使用。"
applyTo: [".github/workflows/compile-*.yml", ".github/workflows/firmware-build-unified.yml"]
---

# OpenWrt 构建工作流

## 架构

- `firmware-build-unified.yml` 是唯一活跃的编排器。其 `plan` job 负责触发、版本、变更检测、缓存、构建与发布决策。
- `compile-firmware.yml` 与 `compile-packages.yml` 是活跃的 reusable executor；不要向它们添加兜底或升级决策。
- `run-firmware`、`run-sdk-ib`、`run-packages` 由 `plan` 的显式输出控制。`run-sdk-ib` 调用 `compile-packages.yml` 并传 `matrix_build_sdk_ib=true`。

## 必要行为

- 依赖了被跳过 job 的 job 会被隐式跳过。不要把可能被跳过的 job 放进 `needs`；需要其结果时用 `always()` 加显式 `needs.<job>.result` 判断。
- 不要导出名为 `TARGET`、`HOST`、`BUILD` 的通用 workflow、job 或 shell 环境变量（详见 [project-constraints.instructions.md](project-constraints.instructions.md) § 环境变量禁令）。使用 `matrix_target` 内联或领域特定命名。
- 保持缓存策略 `smart`、`clean-toolchain`、`clean-ccache`、`clean-all`、`no-cache` 行为互不相同。
- 仅当构建成功后才保存当前 toolchain 与 ccache 快照；失败的构建不得替换已有缓存。先保存当前 key 再清理旧条目，并把当前 key 排除在清理范围外。这样即使保存或清理失败，仍保留可用的旧缓存。
- 保存成功后，清理当前 target 下 `immwrt-v2-toolchain-<target>-*` 与 `immwrt-v2-ccache-<target>-*` 的所有旧条目。v2 策略为每 target 只保留最新一份；不清理 v1 或无关 workflow 的缓存。
- 每个缓存命名空间都要有有限的保留上限；绝不能让按 run 滚动的命名空间无界增长。`immwrt-v2-toolchain-<target>-*` 与 `immwrt-v2-ccache-<target>-*` 每 target 只保留最新快照；写入 `immwrt-v2-sdk-hostpkg-<target>-<run_id>` 的一方（全量 executor 或 SDK 路径）必须把该命名空间收敛为当前 target 的最新单份快照，避免只跑全量构建的时期无限增长。GitHub 自身驱逐**不是**原因：超配额时平台先保存新缓存，再按 last-access 从旧到新驱逐——run 35313768877 中被驱逐的恰是上一代、从未被读过的 `sdk-hostpkg` 快照（3.10GB），与 latest-only 策略删除的集合相同。写入方主动清理的意义在于可控性：在我们自己的步骤里释放空间、保留「新快照保存成功后才清理」的兜底，并让驱逐根本无需发生——因为当旧代太小（或 7 天过期后不存在）时，下一个候选就是 toolchain 快照，代价是 40 分钟重建。
- toolchain 快照 key 是内容寻址的（`tools`/`toolchain` 树哈希）。当完全相同的 key 已存在时，跳过保存而不是让它报 `Unable to reserve cache ...`（Actions Cache key 不可变）；清理步骤必须把已存在的快照视为可用，而不是依赖保存步骤的结果。
- 两个 executor 都恢复并保存共享的 `immwrt-v2-ccache-<target>-<run_id>` 命名空间，并把旧快照清理到每 target 最新一份；`source_sha` 是产物/SDK-IB 匹配元数据，不属于 SDK hostpkg key。
- `plan` job 把 `smart` 以外的所有缓存策略路由到全量构建 executor。executor 负责所选策略的缓存操作：restore、save、purge 都在 reusable workflow 中、`plan` 做出路由决策之后执行。
- 工具链缓存命中时禁止显式调用 `make tools/compile toolchain/compile` 或其它子目录目标：工具链缓存只含 `openwrt/staging_dir/host*` 与 `openwrt/staging_dir/tool*`，而各 host 工具的 `.built` 标记位于 `build_dir/`（`include/host-build.mk` 的 `HOST_STAMP_BUILT`）。显式传入子目录目标会绕过顶层 stamp 守门（`timestamp.pl` 不再运行），make 转而逐工具检查 `build_dir` 中缺失的 `.built`，使缓存命中时仍全量重编（实测 warm-cache 的 `Prepare` 步骤在 GCC 14 目标上仍耗 40+ 分钟）。工具链主体编译必须交由默认目标 `world` 调度；仅当 `staging_dir/host/bin/ccache` 缺失/不可执行时才允许显式 `make tools/ccache/compile` 以提供 ccache 命令。
- `dl/` 残损下载清理必须限定深度：使用 `find dl -maxdepth 1 -type f -size -1024c`，禁止递归。`dl/go-mod-cache`（Go module）与 `dl/cargo`（crate）内含大量合法的小于 1KB 的文件，递归删除会破坏 Go `//go:embed` 资源（如 protobuf `editions_defaults.binpb`）与 cargo checksum（`Cargo.toml.orig`），导致整批 Go/Rust 包编译失败。
- `no-cache` 模式下跳过 Actions Cache 的 restore/save/purge。不要导出 workflow 级 ccache `CC`/`CXX` 包装器；ccache 可用时正常配置，构建内行为跟随 seed 的 `CONFIG_CCACHE`。
- 完全不要在 workflow 级导出 `CC`/`CXX` 包装器：seed 已设 `CONFIG_CCACHE=y`，`rules.mk` 会自动包装编译器命令（OpenWrt 21.02 设置 `TARGET_CC:=ccache_cc`，新版/SNAPSHOT 设置 `TARGET_CC:=ccache $(TARGET_CC)`），且 `HOSTCC:=ccache $(HOSTCC)`。环境 `CC`/`CXX` 导出是冗余的，还可能把系统 `gcc` 泄漏进不读 `TARGET_CONFIGURE_OPTS` 的包。`no-cache` 策略因此只关闭远端缓存持久化，而不强制关闭构建系统原生的 ccache 设置。
- SDK 增量构建环境下：系统未全局安装 ccache 时，配置和统计命令必须显式定位 SDK 自带的 `staging_dir/host/bin/ccache`（或在 PATH 中探测），禁止假设系统 PATH 中存在裸 `ccache` 命令。
- 不要通过 `--set-config` 设置 ccache `compiler_check`：`rules.mk` 导出 `CCACHE_COMPILERCHECK`，而 ccache 的环境变量优先级高于配置文件，文件值会被静默忽略。workflow 中只设置 `hash_dir` 与已验证的 `sloppiness` 选项；不要强制 ccache 压缩，因为 qualcommax 可能导出 `CCACHE_NOCOMPRESS`，而 Actions Cache 的归档压缩与之独立。`base_dir` 由 `rules.mk` 原生导出（`CCACHE_BASEDIR=$(TOPDIR)`）。
- `.github/upstream-sync/patches/packages/` 下的 feed 补丁（由 `upstream-sync.yml` 通过 `git apply` 应用）合并前必须用 `git apply --check` 验证。hunk 内的每个内容行必须以 `+`、`-` 或空格开头；新增行缺 `+` 前缀会让 `git apply` 报 `corrupt patch`。`upstream-sync.yml` 也由这些补丁的 `push.paths` 触发——推送补丁改动会自动重跑同步。
- SDK+IB 路径必须逐设备构建固件：从 seed 提取所有设备名（`CONFIG_TARGET_(DEVICE_)?*_DEVICE_<name>=y`），对每个设备执行 `make image PROFILE=<name>`。不传 `PROFILE` 时，`USER_PROFILE ?= $(firstword $(PROFILE_NAMES))`（imagebuilder `files/Makefile`）只选第一个设备，`include/image.mk`（`DEVICE_CHECK_PROFILE`）会禁用其余设备——mt798x 会静默丢失设备。
- 全局并发组 `firmware-build-v2` 保持固定。不要按 ref 加作用域；两个并行 run 会写同一个 `sdk-*`/`ib-*`/`packages` tag 并污染远端仓库。
- SDK 与 ImageBuilder 版本存放在共享的 `artifacts-<target>` release tag 下。`sdk-index.json` 与 `ib-index.json` 分开维护，同版本文件替换，每类产物保留配置数量的不同版本。
- 版本排序保持数值序，并识别 SNAPSHOT 与 `V<n>` 记号。
- 用 `*-sdk-*.tar.*` / `*-imagebuilder-*.tar.*` 匹配 SDK/ImageBuilder 产物（上游命名为 `<dist>-sdk-*` / `<dist>-imagebuilder-*`）；提取 arch 时用不带日期的 `patched_version`（SNAPSHOT 替换后、tarball 实际构建所用的版本）剥离内嵌版本前缀，绝不用带日期的 `source_version`。
- 版本解析为纯字符串的规则见 [version-extraction.instructions.md](version-extraction.instructions.md)（`include/version.mk` 的 `VERSION_NUMBER` 可能是 make 表达式；严禁把表达式注入 shell 步骤或 `index.json` key）。
- SDK/ImageBuilder 校验和写成两列 `.sha256`（`<hash>  <filename>`），重命名后重新计算；消费方运行 `sha256sum -c`，单列哈希或文件名不匹配都会失败。
- 构建状态持久化到 `IMMWRT_BUILD_STATE` repository variable（详见 [project-constraints.instructions.md](project-constraints.instructions.md) § 构建状态持久化）。这里的禁令针对**构建状态**持久化；ccache 的 `run_id` key 是缓存数据（累积的编译器对象缓存），采用平台标准的按 run 快照模式，其积累由 purge 每 target 只保留最新一份约束——不受该规则覆盖。

## 先诊断

- 排查构建失败前，先用证据对照 `docs/openwrt-build-pitfalls.md` 与 `openwrt-build-diagnostics` 的 `references/diagnostic-signatures.md`。复用已验证的根因，不要重新推导。
- 改动 workflow 或配置前，先用 `openwrt-build-diagnostics` skill 做只读诊断。

## 诊断不变量

- 保留四阶段磁盘监控及其摘要增量。
- 保留构建日志计数、不完整与空日志检测、最慢构建摘要。
- 保留失败包自动诊断，失败产物中包含 `.config`。
- 以 `logs*/<pkg>/error.txt` 为失败包的权威来源（`ERROR: <pkg> failed to build.`）。不要用 `compile.txt` 是否以 `time:` 结尾判断失败：`scripts/time.pl` 无论退出状态如何都会打印该行，失败日志也以 `time:` 结尾。末行检查仅作为中断日志（如 OOM）的兜底。
- 失败包日志完整输出，不过滤不截断；仅对超大文件（>300 KB）截取尾部并指向 artifact。
- 首轮 `logs` 移到 `logs.1`；单线程重试前绝不删除证据。
- 保留 `make -j1 V=sc -k` 重试以获得完整的 configure 与编译器诊断。
- 保留 ccache 统计与清理、release 根目录列表，以及有意使用 `continue-on-error` 的诊断验证步骤。
- feed 更新保持 fail-fast（`set -euo pipefail`）。
- `set -euo pipefail` 步骤内的可选诊断管道必须以 `|| true` 结尾（`head` 截断时的 SIGPIPE 141）。原理与正误示例见 [project-constraints.instructions.md](project-constraints.instructions.md) § 可选诊断管道。
- 缓存清理是可观测操作：不要用 `2>/dev/null` 或裸 `|| true` 静默 `gh cache list` / `gh cache delete` 的失败。捕获 list 命令的退出码，失败时向 stderr 报告，且 list 失败时跳过删除（空结果是正常的 rc=0 未找到，与执行错误不同）。删除失败要显式报告。
- 除非有意重设计 workflow 展示，保留既定的编号步骤名与诊断标题格式。

已验证根因与排查证据见 `docs/openwrt-build-pitfalls.md`。
