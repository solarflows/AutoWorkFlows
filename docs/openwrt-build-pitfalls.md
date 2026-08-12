# OpenWrt Build Pitfalls

This document preserves detailed evidence behind the short rules in `.github/instructions/openwrt-build.instructions.md`.

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

在 `OpenWRT_Packages_Updater.yml` 的全局补丁目录 `.github/diy/openwrt-packages/patches/` 添加 `fix-shadowsocksr-libev-configure.patch`, 修改包 Makefile, 注册一个 `Hooks/Prepare/Post` hook:

```makefile
define ShadowsocksR/Fixup/Prepare
	rm -f $(PKG_BUILD_DIR)/configure
endef
Hooks/Prepare/Post += ShadowsocksR/Fixup/Prepare
```

`Hooks/Prepare/Post` 在 `Build/Prepare` (quilt 应用全部 patch) 之后执行, 此时 configure 已被 0001 patch 修改过 (quilt 应用成功), 删除后 `PKG_FIXUP:=autoreconf` 看到 configure 缺失必然从 configure.ac 重新生成 (configure.ac 已被 0001 + 105 patch 更新为 pcre2, autoconf 生成的 configure 自带执行位且内容正确)。不要动 `src/libsodium/configure` (其 autoreconf 正常, 日志证明被完整重建)。

验证证据 (run #31559354153, commit bfb4c8b) — GitHub trees API: `100644 blob shadowsocksr-libev/src/configure`; 上游 `Openwrt-Passwall/openwrt-passwall-packages` 同名文件同样 100644; feed `main`/`qt6`/`mt798x`/`qualcommax` 四分支均受影响且该包 Makefile SHA 一致 (a7c20c1), 故用全局补丁一次覆盖。

## Cache Strategy

The supported strategies are `smart`, `clean-toolchain`, `clean-ccache`, `clean-all`, and `no-cache`. `no-cache` skips ccache wrapping, restore, statistics, and cleanup so it can answer whether cache state contributes to a failure. When ccache is enabled, configure its size and compiler checks unconditionally; only wrapper export is conditional.

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
- v2 splits restore and save; save becomes an explicit main step placed **before** the Purge step. Chain: miss → compile → save (now saved) → Purge's miss branch deletes every cache including the just-saved one → zero caches remain → next run misses again → full `tools/*` rebuild forever.

## v2 Cache Lifecycle

The v2 firmware executor keeps toolchain and ccache snapshots separate per target. Both snapshots are saved only after the build job remains successful. The current key is saved first, then older entries under the same v2 target prefix are deleted while the current key is explicitly excluded.

This ordering means:

- a compile or diagnostic failure skips both saves and purge, so an existing cache is not replaced;
- a save failure skips purge, so an existing cache remains available;
- a purge/API failure may temporarily leave more than one entry, but cannot delete the current result;
- `ccache --max-size 10G` and compression manage the contents of one ccache snapshot, not the number of remote Actions cache entries;
- the v2 workflow no longer performs a monthly full flush, and does not remove v1 or unrelated workflow caches.

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


### v2 ccache and cache lifecycle

ccache remains a **cumulative** cache: every compile adds objects and its invalidation factors cannot be represented by one content hash. It therefore keeps a per-run `run_id` key and restores from the target prefix, so every successful build can publish a fresh snapshot.

The v2 executor uses explicit `actions/cache/restore@v5` and `actions/cache/save@v5` for both toolchain and ccache. The save steps run only after the build and diagnostics have succeeded. The current snapshot is saved first; the purge then deletes older entries under the same target prefix while excluding the current key.

This gives the following guarantees:

- a compile or diagnostic failure skips save and purge, so an existing cache is not replaced;
- a save failure prevents purge, so an existing cache remains available;
- a purge/API failure may temporarily leave older entries, but cannot delete the current result;
- `ccache --max-size 10G` and compression bound the contents of one ccache snapshot, not the number of remote snapshots;
- v2 no longer performs a monthly full flush and does not remove v1 or unrelated workflow caches.

### Diagnostic Notes

- Tools recompilation is not an architecture bug. First check whether a toolchain cache exists at all.
- Distinguish `Cache restored from key: ...` (hit) from `Cache not found for input keys: ...` (miss).
- If a cache API call fails, the workflow reports it and preserves the current and existing cache entries.

## SDK and ImageBuilder Retention

SDK and ImageBuilder archives are stored under `sdk-<target>` and `ib-<target>` release tags with an `index.json`. Replace files for the same version with `--clobber`. For different versions, retain the configured number of version groups. Sorting must compare numeric fields numerically, map SNAPSHOT to a stable sentinel, and parse `V<n>` as a number.

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