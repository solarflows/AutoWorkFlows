# OpenWrt Build Pitfalls

This document preserves detailed evidence behind the short rules in `.github/instructions/openwrt-build.instructions.md`.

## CONFIG_PACKAGE 选择项误识别为软件包

### Symptom

v2 工作流会尝试编译不存在的目标，例如：

```text
make: *** No rule to make target 'package/luci-app-passwall2_INCLUDE_Hysteria/compile'.  Stop.
```

或者 IB 的 `PACKAGES` 参数中出现 `luci-app-passwall2_Basic_Core_SingBox`、`luci-app-smartdns_INCLUDE_smartdns_ui` 等字符串。

### Verified Root Cause

SDK 和 IB 路径原先都用宽匹配读取 `CONFIG_PACKAGE_`：

```text
CONFIG_PACKAGE_.*=[ym]
```

但这个前缀同时用于真正的软件包和 Kconfig 选择项。选择项通常包含大写的 `INCLUDE_*`、`Basic_Core_*` 或 `Enable_*` 后缀，不对应 `package/<name>` 目录，因此会被错误传给 `make package/...`。

### Fix

两个提取点现在只接受大小写敏感的小写包名字符集，同时保留合法的小写下划线包名：

```text
^CONFIG_PACKAGE_[a-z0-9][a-z0-9+._-]*=[ym]$
```

因此 `msd_lite`、`libopenssl-afalg_sync` 等真实包仍会保留，而 `INCLUDE_*`、`Basic_Core_*` 和 `Enable_*` 选择项会被排除。

### Verification

```text
rg --pcre2 '^CONFIG_PACKAGE_[a-z0-9][a-z0-9+._-]*=[ym]$' openwrt-configs/immortalwrt
```

重新触发 v2 后，`待编译` 和 IB `PACKAGES` 列表不应再出现含大写选择后缀的条目。

## GitHub Actions `needs` Implicit Skip

If job A includes job B in `needs` and B is skipped, GitHub implicitly skips A even when A's own condition is true. A job that only needs a plan decision should depend on `plan` and test the corresponding output. When another job's result is genuinely required, use an `always()` condition and check `needs.<job>.result` explicitly.

## libffi InstallDev Failure

### Symptom

The package install step fails with an error similar to:

```text
cp: cannot stat '.../libffi-3.3/aarch64-openwrt-linux-gnu/fficonfig.h'
```

The `solarflows/packages` hanwckf branch contains an ImmortalWrt-specific libffi Makefile line that copies:

```makefile
$(PKG_BUILD_DIR)/$(GNU_TARGET_NAME)-gnu/fficonfig.h
```

Upstream later used a `$(GNU_TARGET_NAME)*/fficonfig.h` wildcard.

### Verified Root Cause

A job-level `env: TARGET` leaked into the build. libffi 3.3 uses `AX_ENABLE_BUILDDIR`; its build directory defaults to the shell variable `$TARGET` and only falls back to Autoconf's `$target` when the environment value is empty. With `TARGET=mt798x`, configure re-entered `./mt798x` and generated `fficonfig.h` there:

```text
continue configure in default builddir "./mt798x"
config.status: creating fficonfig.h
```

The package Makefile expected an architecture-specific GNU target directory, so InstallDev could not find the generated header.

### Fix

Do not set workflow-level, job-level, or exported shell variables named `TARGET`, `HOST`, or `BUILD`. Use `${{ inputs.matrix_target }}` inline, as the previous workflow used `${{ matrix.target }}`, or use a scoped name such as `FIRMWARE_TARGET`. Cache keys, artifact names, and tarball names must not depend on an exported generic `TARGET` variable.

## persist-state merge-multiple Overwrites Same-named Artifact Files

### Symptom

`Persist build state` reported `✅ 已合并 1 个成功 target` while both targets (mt798x + qualcommax) succeeded and uploaded their `*-published-state` artifacts (run 31878516045). The `IMMWRT_BUILD_STATE` repository variable kept the stale state for qualcommax (`last_mode: firmware`, old `source_sha`/`packages_sha`).

### Verified Root Cause

The `persist-state` job downloaded artifacts with:

```yaml
uses: actions/download-artifact@v8
with:
  path: published-state
  pattern: '*-published-state'
  merge-multiple: true
```

Each executor uploads a differently-named artifact (`mt798x-published-state`, `qualcommax-published-state`) but the file inside is always `build-info.json`. With `merge-multiple: true`, download-artifact flattens all artifacts into one directory, so the second `build-info.json` silently overwrote the first; `for info in published-state/*.json` then iterated only one file. Downloading each artifact separately confirmed both files were individually correct — the bug was purely in the merge side.

### Fix

Remove `merge-multiple: true` so download-artifact keeps artifact-name subdirectories (`published-state/<artifact-name>/build-info.json`), then iterate with `find`:

```bash
while IFS= read -r info; do
  ...
done < <(find published-state -name 'build-info.json' -type f 2>/dev/null | sort)
```

The `find`-based loop is immune to same-name collisions and to future changes in artifact naming/count.

### Verification

Rerun a two-target SDK/IB build: `Persist build state` should log `✅ 已合并 2 个成功 target` and both targets' `last_build`/`last_mode` must update in `IMMWRT_BUILD_STATE`.

### Diagnostic Notes

If libffi `compile.txt` is very small, approximately 461 bytes and 0.2 seconds in the observed failure, the retry was stamp-skipped. Inspect `logs.1` for the first-pass configure error.

A half-configured ccache environment was an earlier hypothesis: an empty cache combined with exported `CC="ccache gcc"` and seed-level `CONFIG_CCACHE=y` could double-wrap compilers. It was not the verified cause of this failure. The workflow still guarantees that `no-cache` mode does not export `CC` or `CXX`, and first-pass logs remain available under `logs.1`.

## shadowsocksr-libev src/configure 无执行位 (静默跳过 configure)

### Symptom

mt798x 构建在 `package/solarflows/shadowsocksr-libev` 失败, 两次尝试 (首轮 + 重试) 同一错误:

```text
make[4]: *** No targets specified and no makefile found.  Stop.
```

全构建 796 个日志中该签名只出现在这一个包。`logs.1/package/solarflows/shadowsocksr-libev/compile.txt` 中 patch (9 个) + autoreconf 之后**没有任何 `checking for...` configure 输出**, 直接进入 `make[4]`。

### Verified Root Cause

1. feed (`solarflows/openwrt-packages`) 的 `shadowsocksr-libev` 来自 `Openwrt-Passwall/openwrt-passwall-packages` (整体 clone + mvdir), 包 Makefile 无 `PKG_SOURCE_URL`, 源码在 `src/` 目录。
2. 上游 `src/configure` 在 git 树中 mode=100644 (无执行位), 经 `cp`/rsync 复制保留 644。
3. `Build/Configure/Default` 用 `if [ -x ./configure ]` 判断, 为假时**静默跳过 configure** (无输出、退出 0, `.configured` stamp 照常生成)。
4. `PKG_FIXUP:=autoreconf` 注册的 `Hooks/Configure/Pre` 中, 根目录 `autoconf`/`automake` 未执行 (0001 patch 已把 configure 文件改新 → autoreconf 跳过; 命令尾 `|| true` 吞错), 旧 configure 无法被重新生成。
5. compile 阶段 `make -C $(PKG_BUILD_DIR)` 找不到 Makefile → 报错。

仅 `chmod +x configure` 不够: 旧 configure 仍是 pcre v1 检测 (patch 105 已把 configure.ac 升级到 PCRE2), 运行时会以可见的 "Package requirements (libpcre) were not met" 失败。也不能在 feed 里直接删除 `src/configure`: 构建时 quilt 应用的 `0001-Add-ss-server-and-ss-check.patch` 会 patch configure 文件, 删除后 quilt 应用失败。

### Fix

在 `custom-feed.yml` 的全局补丁目录 `.github/custom-feed/patches/` 添加 `fix-shadowsocksr-libev-configure.patch`, 修改包 Makefile, 注册一个 `Hooks/Prepare/Post` hook:

```makefile
define ShadowsocksR/Fixup/Prepare
	rm -f $(PKG_BUILD_DIR)/configure
endef
Hooks/Prepare/Post += ShadowsocksR/Fixup/Prepare
```

`Hooks/Prepare/Post` 在 `Build/Prepare` (quilt 应用全部 patch) 之后执行, 此时 configure 已被 0001 patch 修改过 (quilt 应用成功), 删除后 `PKG_FIXUP:=autoreconf` 看到 configure 缺失必然从 configure.ac 重新生成 (configure.ac 已被 0001 + 105 patch 更新为 pcre2, autoconf 生成的 configure 自带执行位且内容正确)。不要动 `src/libsodium/configure` (其 autoreconf 正常, 日志证明被完整重建)。

验证证据 (run #31559354153, commit bfb4c8b) — GitHub trees API: `100644 blob shadowsocksr-libev/src/configure`; 上游 `Openwrt-Passwall/openwrt-passwall-packages` 同名文件同样 100644; feed `main`/`qt6`/`mt798x`/`qualcommax` 四分支均受影响且该包 Makefile SHA 一致 (a7c20c1), 故用全局补丁一次覆盖。

## Cache Strategy

The supported strategies are `smart`, `clean-toolchain`, `clean-ccache`, `clean-all`, and `no-cache`. `plan` routes every non-`smart` strategy to the full-build executor; the executor then performs the selected restore/save/purge behavior. `no-cache` skips Actions Cache restore, save, statistics, and purge, but does not forcibly disable OpenWrt's in-build ccache when the seed retains `CONFIG_CCACHE=y`. ccache configuration remains guarded by the discovered build support.

## Toolchain Cache Self-Deletion

### Symptom

The v2 workflow (`firmware-build.yml` → `compile-firmware.yml`) rebuilds host tools on every run — `make[3] -C tools/xxx compile` appears every time — while v1 (`firmware_builder.yml`) does not. Build time is dominated by the tools compilation phase.

### Verified Root Cause

The toolchain cache is deleted by its own Purge step immediately after it is saved, so the cache never accumulates.

The toolchain cache uses separate `actions/cache/restore@v5` and `actions/cache/save@v5` steps; the save executes synchronously **before** the Purge step. The Purge step's smart-mode branch deleted every `immwrt-v2-toolchain-<target>-*` cache whenever the exact restore key missed:

```bash
TC_EXACT_HIT="${{ steps.cache-tc-restore.outputs.cache-hit || 'false' }}"
if [ "$CACHE_STRATEGY" = "clean-all" ] || [ "$CACHE_STRATEGY" = "clean-toolchain" ] || [ "$TC_EXACT_HIT" != "true" ]; then
  gh cache list --repo ... --key "immwrt-v2-toolchain-${IMMWRT_TARGET}-" ... | xargs ... gh cache delete ...
fi
```

On a miss, the branch deleted every toolchain cache — including the one the preceding Save step had just written. The chain: restore miss → no `staging_dir` stamps → `TOOLCHAIN_RESTORED=false` → bare `make` sees no host-tool stamps → full rebuild of `tools/*` → save → purge deletes it.

Evidence (run #30977360580, commit 3ee7999) — `actions/cache/restore@v5` logs:

```text
key: immwrt-v2-toolchain-mt798x-65f3799
restore-keys: immwrt-v2-toolchain-mt798x-
Cache not found for input keys: immwrt-v2-toolchain-mt798x-65f3799, immwrt-v2-toolchain-mt798x-
```

Even the restore-keys **prefix** missed, proving zero caches existed under that prefix. The ccache restore in the same run hit, in contrast:

```text
Cache hit for restore-key: immwrt-v2-ccache-mt798x-30882709710
```

Why ccache survived while toolchain did not: ccache uses the combined `actions/cache@v5`, whose save runs as a post action **after** all main steps, so the purge could never delete the just-saved ccache. ccache's exact key is unique per run (`github.run_id`), so `cache-hit` was always `false` and the old purge did delete all ccache caches too — but the post-save re-created one, keeping ccache functional. The toolchain split save/restore had no such protection.

Why v1 did not exhibit this — **save ordering, not hash stability**. Both v1 and v2 check out the same `targets.json` refs (`test` / `VIKINGYFY-main`, rolling branches), so their toolchain hashes are equally unstable. The real difference is where the save runs relative to the purge:

- v1 uses the combined `actions/cache@v5`, whose save runs as a **post action after all main steps** — i.e. after the Purge step. Chain: miss → compile → Purge deletes old caches (the just-built result is not yet saved, so it is untouchable) → post-action save writes the fresh cache → next run's `restore-keys` prefix hits it → stamps are touched → `tools/*` is skipped. The cache accumulates one entry per run.
- v2 splits restore and save; save becomes an explicit main step placed **before** the Purge step. Chain: miss → compile → save (now saved) → Purge's miss branch deletes every cache including the just-saved one → zero caches remain → next run misses again → `tools/*` rebuild repeats every run.

### Fix (已修复)

The purge no longer keys off the restore result at all. It selects by anchored regex on the key itself and excludes the current key, so the snapshot written moments earlier can never be its target:

```bash
TC_CURRENT="${TC_PREFIX}${{ steps.toolchain_hash.outputs.hash }}"
TC_PATTERN="^immwrt-v2-toolchain-${IMMWRT_TARGET}-(force-[0-9a-f]{16}-[0-9]+|[0-9a-f]{16})$"
# purge: keep TC_CURRENT, delete the rest under this target's prefix only
```

The same structure now guards ccache and the SDK hostpkg namespace. 2026-09-18 补充:内容寻址的 key(同一源码树哈希)已存在时,save 会被新的预检步骤跳过(见 `## GitHub Actions Cache Quota and Eviction`);purge 条件同时接受 "save 成功" 与 "快照已存在",因此清理不会因跳过 save 而连带失效。

### Verification

后续运行中 `Restore toolchain cache` 稳定出现 `Cache hit for: immwrt-v2-toolchain-<target>-<hash>`(run 35313768877 三个 target 全部精确命中),`🔧 Prepare toolchain & ccache` 在 ccache 可用且工具链已恢复时接近 0 秒(`✅ 已发现可用的 OpenWrt ccache 且工具链已恢复，完全复用缓存，跳过预编译`)。

## v2 Cache Lifecycle

ccache remains a **cumulative** cache: every compile adds objects and its invalidation factors cannot be represented by one content hash. It therefore keeps a per-run `run_id` key and restores from the target prefix, so every successful build can publish a fresh snapshot; `ccache --max-size 10G` bounds the contents of one snapshot, not the number of remote snapshots.

The v2 firmware executor keeps toolchain and ccache snapshots separate per target. Both snapshots are saved only after the build job remains successful. The current key is saved first, then older entries under the same v2 target prefix are deleted while the current key is explicitly excluded.

This ordering means:

- a compile or diagnostic failure skips both saves and purge, so an existing cache is not replaced;
- a save failure skips purge, so an existing cache remains available;
- a purge/API failure may temporarily leave more than one entry, but cannot delete the current result;
- `ccache --max-size 10G` manages the contents of one ccache snapshot; ccache's internal compression and Actions Cache archive compression are separate controls, so workflows do not force a compression mode;
- the v2 workflow no longer performs a monthly full flush, and does not remove v1 or unrelated workflow caches;
- every namespace converges to the newest single snapshot per target. Both executors write the `immwrt-v2-sdk-hostpkg-<target>-<run_id>` namespace (the full build seeds it so the SDK path starts warm) and both purge it to their own newest snapshot; the full executor used to write it without any purge, so a full-build-only period grew the namespace by 0.5–1.7GB per target per run with no reader ever refreshing it (see `## GitHub Actions Cache Quota and Eviction`);
- the toolchain snapshot key is content-addressed, so an already-present key makes `actions/cache/save` fail with `Unable to reserve cache ...`; a pre-check step skips that save and the purge proceeds on "snapshot already exists" instead of requiring the save step's outcome.

## GitHub Actions Cache Quota and Eviction (平台行为, 已核查)

### Verified Platform Behavior

官方 caching reference (`Usage limits and eviction policy`):

- 默认每仓库 10 GB;超限时**新缓存仍会保存成功**,随后按 `last access date` 从旧到新驱逐,直到总量低于上限;
- 超过 7 天未被访问的条目无条件删除(与配额无关)。

### Evidence (run 35313768877, 2026-09-18)

三个 target 的全量构建,按保存时刻还原配额变化 (GiB;上限 10 GB ≈ 9.31 GiB):

| 时刻 | 事件 | 保存后累计 | 越限 | 平台驱逐 |
|---|---|---|---|---|
| 起始 | toolchain×3 = 1.48,上一代 ccache 3.31,上一代 sdk-hostpkg 3.10 | 7.89 | — | — |
| 06:58 | mt798x save ccache 0.56 / hostpkg 0.46;purge 释放旧 ccache 0.56 | 8.35 | 否 | — |
| 07:36 | ipq807x save ccache 1.05 | 9.40 | **+0.09** | 上一代 hostpkg (mt798x) 0.46 |
| 07:37 | ipq807x purge 释放旧 ccache 1.05;save hostpkg 1.02 | 8.92 | 否 | — |
| 08:11 | ipq60xx save ccache 1.73 | 10.65 | **+1.33** | 上一代 hostpkg (ipq807x) 1.02 → 仍超 → 上一代 hostpkg (ipq60xx) 1.61 |
| 08:11 | ipq60xx save hostpkg 1.61 | 7.92 | 否 | — |

被驱逐的三条恰好是上一代、创建后从未被读取的 `immwrt-v2-sdk-hostpkg-*`(合计 3.10 GiB),与"每 target 仅留最新 1 份"策略要删的集合完全一致;`immwrt-v2-toolchain-*` 的 `last_access` 在本轮开头被 restore 刷新过,因此未被波及。

### Rules Derived From This Evidence

- 平台驱逐**不是乱删**:它按 `last-access` 有序进行,稳定状态下等价于"每命名空间每 target 只留最新 1 代",因此可以依赖它作为兜底,但不能把它当保留策略。
- `last-access` 只反映"谁最近被读过",不反映"谁可以重建":全量执行器只写不读 sdk-hostpkg 种子快照,其 `last_access` 永远等于创建时间,配额紧张时它必然是第一顺位受害者(本轮如此,除非写入方自己清理)。
- 尾部风险:当陈旧代不足以吸收本轮增量、或根本不存在(例如 7 天过期后、只有部分 target 构建)时,下一批候选就是 `toolchain` 快照(代价 40 分钟全量重编),并可能引发 cache thrashing。因此写入方仍必须自约束保留量。
- 峰值的主导因素是"每个滚动 namespace 的两代并存":稳态 7.92 GiB,理论峰值(稳态 + 全量上一代 6.41 GiB)14.33 GiB,本轮实际观测峰值 10.65 GiB(save 与 purge 交错执行)。压缩峰值只能靠减小单代体量或提高仓库配额,而不是取消清理。

### Content-Addressed Key Cannot Be Re-Saved

`immwrt-v2-toolchain-<target>-<hash>` 的 key 由 `tools`/`toolchain` 源码树哈希决定,同一源码修订只对应同一 key。Actions Cache 的 key 不可覆盖,重复 save 必然以如下信息结束(run 35313768877 三个 target 均出现):

```text
Failed to save: Unable to reserve cache with key immwrt-v2-toolchain-mt798x-dcf4ec5a69fea0fa, another job may be creating this cache.
```

这是"缓存已存在"的正常表现,与配额、并发均无关。修复:save 前用 `gh cache list --key <exact>` 预检,精确命中则跳过 save;purge 条件同时接受 "save 成功" 或 "快照已存在",避免清理被连带跳过。查询失败时按未命中处理并继续保存(不静默降级)。

## Make 表达式版本号注入 Shell (SDK/IB 打包崩溃)

### Symptom

`📦 Package SDK & IB tarballs` 步骤在脚本第 14 行失败, exit code 127:

```text
/home/runner/work/_temp/cc7632cc-eacd-4799-8a6c-66f9a5e9136c.sh: line 14: CONFIG_VERSION_NUMBER: command not found
/home/runner/work/_temp/cc7632cc-eacd-4799-8a6c-66f9a5e9136c.sh: line 14: callqstrip,: command not found
```

### Verified Root Cause

两个平台的源码仓库 `include/version.mk` 都把 `VERSION_NUMBER` 写成 make 表达式 (两行结构相同, 仅兜底值不同):

```makefile
VERSION_NUMBER:=$(call qstrip,$(CONFIG_VERSION_NUMBER))
VERSION_NUMBER:=$(if $(VERSION_NUMBER),$(VERSION_NUMBER),21.02-SNAPSHOT)   # qualcommax: ...,SNAPSHOT)
```

`Apply Configuration` 步骤用 `grep -m1 '^VERSION_NUMBER:=' include/version.mk | cut -d= -f2 | tr -d '[:space:]'` 提取版本号, 得到:

```text
$(callqstrip,$(CONFIG_VERSION_NUMBER))     # tr -d '[:space:]' 连 "call qstrip," 里的空格一起删掉
```

该字符串被写入 `steps.apply_config.outputs.source_version` / `original_version`, 再被 SDK/IB 打包步骤注入 shell 脚本:

```bash
SDK_VERSION="$(callqstrip,$(CONFIG_VERSION_NUMBER))"    # 4 个变量全部被污染
```

bash 把 `$(...)` 当命令替换执行: `$(CONFIG_VERSION_NUMBER)` 运行命令 `CONFIG_VERSION_NUMBER` 报 "command not found", `$(callqstrip,...)` 运行命令 `callqstrip,` 同样报错, 步骤以 127 退出, SDK/IB 无法打包上传。

Evidence (run #30992926916, commit 8c1fa4e) — `Apply Configuration` 输出:

```text
🏷️ source_version: $(callqstrip,$(CONFIG_VERSION_NUMBER))
```

随后 SDK/IB 打包步骤展开为:

```text
SDK_VERSION="$(callqstrip,$(CONFIG_VERSION_NUMBER))"
SDK_ORIG_VER="$(callqstrip,$(CONFIG_VERSION_NUMBER))"
IB_VERSION="$(callqstrip,$(CONFIG_VERSION_NUMBER))"
IB_ORIG_VER="$(callqstrip,$(CONFIG_VERSION_NUMBER))"
```

注意: 直接解析 version.mk 的 `VERSION_NUMBER:=` 行不可行, 因为它是 make 表达式; `.config` 里也没有 `CONFIG_VERSION_NUMBER` (只在 version.mk 的 `PKG_CONFIG_DEPENDS` 引用, defconfig 不落盘)。

### Fix

`Apply Configuration` 按顺序解析纯字符串版本号, 任何 make 表达式一律不采用:

1. `.config` 的 `CONFIG_VERSION_NUMBER="..."` (若存在)
2. version.mk 首行 `VERSION_NUMBER:=` 字面量 (不含 `$(` 表达式)
3. `$(if $(VERSION_NUMBER),$(VERSION_NUMBER),<fallback>)` 的兜底字面量 (如 `21.02-SNAPSHOT` / `SNAPSHOT`)
4. 兜底 `SNAPSHOT`

另输出 `patched_version` (对原始版本号做与 version.mk sed 相同的 `s/SNAPSHOT/${VERSION}/g` 变换) —— 上游 SDK/IB tarball 由本次构建生成, 内嵌的 `<version>-` 前缀是 patch 后的值 (如 `21.02-V260805`), 剥离前缀必须用它匹配, 而不是 patch 前的原始值。

SDK/IB 打包步骤对注入的版本号加防御检查: 若含 `$(` 残留 make 表达式, 显式 `::error::` 报错并退出, 避免静默污染文件名与 index.json key。

### Diagnostic Notes

- Tools recompilation is not an architecture bug. First check whether a toolchain cache exists at all.
- Distinguish `Cache restored from key: ...` (hit) from `Cache not found for input keys: ...` (miss).
- If a cache API call fails, the workflow reports it and preserves the current and existing cache entries.

## SDK and ImageBuilder Retention

SDK and ImageBuilder archives are stored under `sdk-<target>` and `ib-<target>` release tags with an `index.json`. Replace files for the same version with `--clobber`. For different versions, retain the configured number of version groups. Sorting must compare numeric fields numerically, map SNAPSHOT to a stable sentinel, and parse `V<n>` as a number.

## Release 资产上传失败 (HTTP 500/502) 与固件目录误含 SDK/IB

### Symptom

`Publish firmware release` 以 exit 1 结束,mt798x 与 ipq60xx 各报一次服务端错误 (run 35264715561):

```text
HTTP 500: Error creating asset temp dir (https://uploads.github.com/repos/solarflows/immortalwrt-mt798x/releases/391031423/assets?label=&name=immortalwrt-21.02-v260918-...-initramfs-kernel.bin)
```

```text
HTTP 502: Error uploading (https://uploads.github.com/repos/solarflows/ImmortalWrt-QualcommAX/releases/391075016/assets?label=&name=immortalwrt-sdk-qualcommax-ipq60xx_gcc-14.4.0_musl.Linux-x86_64.tar.zst)
```

### Verified Root Cause

两个独立缺陷叠加:

1. 固件打包用 `find bin/targets -type f -not -path "*/packages/*"` 收集产物,未排除 `*-sdk-*` / `*-imagebuilder-*`。种子开启 `CONFIG_SDK=y` / `CONFIG_IB=y` 时,约 130 MB 的 SDK 与 ImageBuilder 归档会被一并复制进 `release/firmware/`,再由 `gh release create/upload "$FIRMWARE_DIR"/*` 一次性批量上传。ipq60xx 的 SDK 归档上传持续约 43 分钟后被网关以 HTTP 502 断开;mt798x 则在创建资产临时目录时收到 HTTP 500。
2. 批量上传没有重试:`set -euo pipefail` 下单个资产的 500/502 直接终止整个步骤,后续 SDK/IB 发布全部被跳过。

### Fix

- 两处收集命令增加 `-not -name "*-sdk-*" -not -name "*-imagebuilder-*"`;SDK/IB 归档仍由专门的 `artifacts-<target>` 通道发布,不再混入固件 Release。
- Release 改为"先确保 Release 存在(create 或 edit),再逐文件上传",每个文件带 3 次重试(5/10/15 秒退避)与 `--clobber`;SDK/IB 的 index.json 上传同样使用该重试封装。

### Verification

下一次全量构建:`release/firmware` 与 `release/` 目录树中不应再出现 `*-sdk-*` / `*-imagebuilder-*`(mt798x 的固件文件数应从 16 回到 14,大小约 514M);`Publish firmware release` 遇到瞬时失败时应先打印 `⚠️ 资产上传失败 [尝试 n/3]` 并最终成功,而不是直接 exit 1。

## `time:` Line Cannot Identify Failed Packages

### Symptom

A failed package log such as `logs/package/feeds/packages/libffi/compile.txt` ends with a `time:` line:

```text
time: package/feeds/packages/libffi/compile#0.11#0.15#0.23
```

Judging failure by "last line is not `time:`" misses this failure, so the diagnostics step falls back to scanning `build.log` and loses the package name and the real compiler/configure error.

### Verified Root Cause

`scripts/time.pl` wraps every make command and prints the timing line **regardless of the command's exit status** — it computes the elapsed time, prints `%s#%.2f#%.2f#%.2f\n` to STDOUT, and only then `exit $exitcode`. A failed build therefore also ends with a `time:` line.

### Fix

The authoritative failed-package source is `error.txt`:

```text
   ERROR: package/feeds/packages/libffi failed to build.
```

Written by make's `ERROR` macro (see `include/verbose.mk`). Extract the package path between `ERROR:` and `failed to build`, strip any ` [host]`-style suffix, and map it to `logs*/<pkg>/compile.txt` / `host-compile.txt` / `download.txt`. Keep the "last line is not `time:`" check only as a fallback for interrupted logs (e.g. OOM kills the wrapper before it prints).

## 工具链缓存命中后仍全量重编 (显式子目标绕过顶层 stamp)

### Symptom

工具链缓存确认命中, 但 `🔧 Prepare toolchain & ccache` 仍然耗时数十分钟, 日志中逐条出现 `make[2] -C tools/... compile` 与 `make[2] -C toolchain/... compile`。warm-cache 与冷启动耗时接近, 缓存几乎没有节省时间。

Evidence (run #34805493661, commit f65f35c):

| Target | 缓存命中 | `Prepare toolchain & ccache` | `5. Build Firmware` |
|---|---|---|---|
| mt798x (GCC 11) | ✅ `immwrt-v2-toolchain-mt798x-dcf4ec5a69fea0fa` (538 MB) | 9m 14s | 34m 48s |
| ipq807x (GCC 14) | ✅ `immwrt-v2-toolchain-ipq807x-488e2adfc91d2d8d` | 40m 28s | — |
| ipq60xx (GCC 14) | ✅ 同上 key | 44m 15s | — |

对比完全冷缓存的 run #34753810756 (ipq807x `Prepare` 46m 37s): 命中缓存仅节省约 6 分钟。GCC 14 (qualcommax) 自身的 C++ 前端与 libstdc++ 体量远大于 mt798x 的 GCC 11, 因此重编代价差异巨大。

### Verified Root Cause

工具链缓存路径只有编译产物, 没有构建中间目录:

```yaml
path: |
  openwrt/staging_dir/host*
  openwrt/staging_dir/tool*
```

而 OpenWrt host 工具的构建门禁位于 `build_dir/` (源码依据: fork `include/host-build.mk`):

```makefile
HOST_STAMP_BUILT:=$(HOST_BUILD_DIR)/.built
$(_host_target)host-compile: $(HOST_STAMP_BUILT) $(HOST_STAMP_INSTALLED)
```

顶层 `Makefile` 用 stamp 目标守门整个子树:

```makefile
world: prepare $(target/stamp-compile) ...
prepare: .config $(tools/stamp-compile) $(toolchain/stamp-compile)
$(toolchain/stamp-compile): $(tools/stamp-compile) ...
```

`include/subdir.mk` 的 `stampfile` 定义让 `$(tools/stamp-compile)` 先跑 `timestamp.pl -n <stamp> tools ...`, stamp 比源目录新时直接成功返回 —— **整个 `tools`/`toolchain` 子树在秒级内被跳过**。

显式在命令行传入子目录目标 `make tools/compile toolchain/compile` 会绕过这层 stamp 守门: make 直接求值子目录目标, 不再经过 `$(tools/stamp-compile)`, `timestamp.pl` 从未运行; 于是每个 host 工具的 `build_dir/host/<pkg>/.built` 依赖被逐个检查, 而 `build_dir` 不在缓存路径内 (干净 Runner 上为空)。make 判定所有工具未构建, 把整套 host 工具与交叉编译器重新全量编译了一遍。

### Fix

commit 273fc79 (`fix(ci): 避免绕过工具链顶层缓存并修复 dl 残损文件递归误删`):

- 严禁显式调用 `make tools/compile toolchain/compile`; 工具链主体编译统一交由 `5. Build Firmware` 的默认目标 `world` 调度, 由顶层 stamp 守门。
- 工具链缓存已恢复且 `staging_dir/host/bin/ccache` 可用时, `Prepare` 步骤刷新 stamp 时间戳后直接 `exit 0`, 完全复用缓存。
- 仅当 `ccache` 缺失/不可执行时, 才显式执行 `make tools/ccache/compile` (连同 tar/xz/patch/libdeflate/sed/flock/zstd 依赖约 2 分钟, 失败回退 `make -j1 V=sc`), 以提供 `5. Build Firmware` 需要的 ccache 命令。

### Verification

warm-cache 全量构建中 `🔧 Prepare toolchain & ccache` 应接近 0 秒; `5. Build Firmware` 的日志 (构建以默认 silent 模式运行, `make -C tools/...` 行会照常打印) 不应再出现被缓存覆盖的 host 工具重编。

## `find dl -size -1024c` 递归误删模块缓存 (SDK 编译大面积失败)

### Symptom

SDK+IB 运行中三个 target 全部在 `Build packages via SDK` 失败 (run #34940720655, commit af3e8ff), 失败包集中在 Go/Rust 系:

```text
mt798x:  hysteria geoview sing-box v2ray-plugin xray-core + package/feeds/packages/rust [host]
ipq807x: sing-box
ipq60xx: hysteria sing-box v2ray-plugin xray-core
```

Go 语言包统一报同一个错误 (以 sing-box 为例):

```text
../../../../../dl/go-mod-cache/google.golang.org/protobuf@v1.36.11/internal/editiondefaults/defaults.go:11:12: pattern editions_defaults.binpb: no matching files found
make[2]: *** [Makefile:137: .../sing-box-1.14.1/.built] Error 1
```

Rust host 包报 checksum 校验失败:

```text
error: failed to calculate checksum of: .../vendor/cc-1.2.28/Cargo.toml.orig
Caused by:
  failed to open file `.../vendor/cc-1.2.28/Cargo.toml.orig`
Caused by:
  No such file or directory (os error 2)
```

### Verified Root Cause

commit 530bb50 为下载重试引入的残损文件清理命令没有限制深度:

```bash
find dl -size -1024c -exec rm -f {} + 2>/dev/null || true
```

它递归扫描整个 `dl/`, 而 OpenWrt 把两类模块缓存也放在 `dl/` 下:

- `dl/go-mod-cache/` — Go module 缓存: protobuf 的 `editions_defaults.binpb` 通过 `//go:embed` 编译进二进制, 该文件小于 1KB, 被删除后编译立刻崩溃;
- `dl/cargo/` — crate 缓存: cargo 依据 `Cargo.toml.orig` 计算/校验 checksum, 文件缺失直接报上表错误。

循环里每个包编译前都执行一次清理, 且是同一份共享的 `dl/go-mod-cache`, 因此破坏是累积且全局的: 任何一个包有一次下载重试或清理即可污染后续全部 Go/Rust 包。

### Fix

commit 273fc79: 两处清理 (编译前 + 下载重试分支) 收窄为只在 `dl/` 根目录删除普通文件:

```bash
find dl -maxdepth 1 -type f -size -1024c -exec rm -f {} + 2>/dev/null || true
```

`compile-firmware.yml` 的 `📥 Download Source Packages` 同类清理也已同步收窄 (`.github/archive/workflows/firmware_builder.yml` 中的旧命令为历史参考, 不再维护)。

### Verification

重跑 SDK+IB: Go/Rust 包应正常完成; 可检查 `dl/go-mod-cache/google.golang.org/protobuf@<ver>/internal/editiondefaults/` 下载后包含 `editions_defaults.binpb`。

## smartdns HTTP/2 流槽位泄漏 (DoH 假死, 进程存活但解析停滞)

### Symptom

ipq60xx / ipq807x 上 smartdns 进程存活、CPU 正常, 但 DoH 上游解析持续无响应; `logread` 可见 `http2 peer stream limit reached` 或 `send http2 stream failed, connection is unavailable.` 反复出现。

### Verified Root Cause

`http2_stream_close()` 对仍有 pending body 的流走"延迟关闭"路径 (`ex_data = NULL; close_after_send = 1`), 只有在 `_http2_stream_flush_pending_send()` 成功后才 `_http2_remove_stream()`。该 flush 在 `send_window_size <= 0 || ctx->send_conn_window_size <= 0` 时永远返回 `EAGAIN`, 只能靠对端 WINDOW_UPDATE 重试; 一旦对端不再补窗口, 流就永久留在 `ctx->streams`, **持续占用 `active_local_streams` 槽位**。

配套的两处放大效应:

- `_http2_ctx_poll()` 中 `conn_stream == NULL` 分支只 `http2_stream_put()` 不移除, 而该流因 `state == CLOSED && !end_stream_read_handled` 每轮都被判定 readable → 既泄漏槽位又挤占 `poll_items[128]`;
- 槽位耗尽后 `_http2_create_stream()` 返回 `errno = ENOSPC`, 而 `_dns_client_send_one_packet()` 的 default 分支只置 `prohibit = 1` (窗口 60s/5s) 并 `shutdown` 套接字, **不重建连接**, 于是僵尸连接一直存活。

版本分水岭: `6f9da63` ("enforce directional HTTP2 stream limits", 首个含它的 tag 为 Release48.3) 引入 `active_local_streams` / `peer_max_concurrent_streams`; 48.2 用混合计数 `active_streams` 且未收到对端 SETTINGS 前不受限, 故旧版症状隐蔽但机制同样存在。

### Fix

- `.github/upstream-sync/overlay/packages/qualcommax/net/smartdns/patches/100-fix-h2-hang.patch` (已随 `solarflows/packages@qualcommax` 生效): `ctx->status < 0` 时不再延迟关闭, 并把 ENOSPC 上报为连接错误。
- `.github/upstream-sync/overlay/packages/qualcommax/net/smartdns/patches/101-reap-stalled-http2-streams.patch` (commit bebecee): ① 延迟关闭增加 `close_defer_tick` + `HTTP2_STREAM_CLOSE_DEFER_TIMEOUT_MS` (5s), 超时即清 pending 并 `_http2_remove_stream(stream, 1)` 回收槽位; ② ENOSPC 分支置 `errno = ECONNRESET`, 命中 `case ECONNRESET` 走立即重建而非 60s prohibit。
- mt798x 同补丁走 openwrt-packages 链路: `.github/custom-feed/overlay/mt798x/smartdns/patches/{100,101}` + `patches/mt798x/0009-smartdns-bump-48.4.patch` (该 target 的 smartdns 来自 `package/solarflows/smartdns` core 包, feeds 同名包不生效)。

### Verification

两补丁对 48.2 (`2b2b31f1`) 与 48.4 源码基线均可用 GNU `patch -p1` 干净应用 (行号 offset 自动适配), 版本升级与补丁互不阻塞; 0009 模拟 CI 顺序 `0007 → 0009 → overlay` 全通过。真机侧观察 `logread` 是否出现 `http2 stream ... closed without sending pending data, drop it.`。

### Diagnostic Notes

上游 48.4 之后 master 未修此泄漏 (仅 b59606e HTTP2/QUIC 轮询内重入 close 的 UAF、e01b938 request_pending 桶数、webui); 相关开放 PR #2458 (429/503 不应 prohibit)、#2422 (TLS/HTTP3 泄漏) 均未合入。