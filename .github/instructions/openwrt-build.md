---
description: OpenWrt/ImmortalWrt 构建工作流的刻意设计与已知坑位（libffi、needs 隐式跳过、SDK/IB 版本保留、诊断设计意图）。修改 .github/workflows/*.yml 前必读。
applyTo: ".github/workflows/**"
---

# OpenWrt Build Workflows — Design Intent & Known Pitfalls

> This file documents **deliberate design decisions** (so maintainers don't mistakenly remove them)
> and **verified pitfalls** (so we don't repeat them). Read before editing any workflow.

## Architecture (v2, refactored 2026-08)

- `firmware-build.yml` = orchestrator: `plan` job makes all decisions (trigger / version / change detection / cache strategy),
  outputs `should_build_*` / `should_publish_*` flags; `run-firmware` / `run-imagebuilder` / `run-packages`
  are three reusable execution jobs; `release` publishes at the end.
- `compile-firmware.yml` (reusable) = full firmware build + SDK/IB tarball upload to Release.
- `compile-packages.yml` (reusable) = compile packages using published SDK.
- `repack-imagebuilder.yml` (reusable) = repack using published IB.
- Principle: **all decisions in plan**; reusable workflows only execute — no fallback or escalation logic.

## Known Pitfalls (verified)

### 1. GitHub needs implicit skip (2026-08-03)
- If job A's `needs` includes job B and B is skipped, GitHub **implicitly skips A**
  (even if A's `if` is true), unless `if` uses `always()` style.
- Fix: `run-firmware` must use `needs: plan` + `if: should_build_firmware == 'true'` —
  **never** put a possibly-skipped job in `needs`.
- Lesson: use `if: always()` style + `needs.X.result` when you need another job's result; don't depend directly.

### 2. libffi InstallDev pitfall (2026-08-03, pending test verification)
- `solarflows/packages` hanwckf branch libffi Makefile has an immortalwrt-specific line:
  `$(CP) $(PKG_BUILD_DIR)/$(GNU_TARGET_NAME)-gnu/fficonfig.h $(1)/usr/include/`
  (added 2022-04-18 for node-ffi-napi). Upstream fixed with `$(GNU_TARGET_NAME)*/fficonfig.h` wildcard.
- Symptom: `cp: cannot stat '.../libffi-3.3/aarch64-openwrt-linux-gnu/fficonfig.h'`.
- **Diagnosis**: if libffi compile.txt is tiny (~461B, 0.2s) the build was stamp-skipped;
  check `logs.1` (first-pass logs) for the real configure error. A half-broken ccache env
  (empty cache + still exporting `CC="ccache gcc"` + seed `CONFIG_CCACHE=y` double-wrapping) is the prime suspect.
- Current code guarantees: no-cache mode does NOT export CC/CXX; first-pass logs preserved via `mv logs logs.1`.

### 3. Cache strategy & ccache (refactored 2026-08)
- `cache_strategy` options: `smart` / `clean-toolchain` / `clean-ccache` / `clean-all` / `no-cache`.
- no-cache = skip all ccache wrapping + cache restore/stats/cleanup; used to verify "is cache to blame?".
- ccache config must run **unconditionally** (`--max-size 10G` + compiler_check=content etc.);
  only `CC`/`CXX` export is conditional — this is a v1 deliberate design, once mistakenly removed causing half-broken env.

### 4. SDK/IB version retention (v2 new)
- Stored as release tags (`sdk-<target>` / `ib-<target>`) with `index.json` tracking.
- Same-version files: `--clobber` replace. Different versions: keep latest `SDK_KEEP_VERSIONS`/`IB_KEEP_VERSIONS` (default 7) groups.
- Version sort must be robust: numeric fields by value, SNAPSHOT→-1, `V<n>` parsed as number (`vtok` function).

## 刻意设计清单（勿删）

| 步骤/逻辑 | 为什么刻意 |
|---|---|
| 磁盘空间 4 阶段监控（disk-1~4）+ Summary 变化表 | 诊断空间不足/缓存膨胀；阶段消耗差值定位暴涨点 |
| Build Log Analysis（compile.txt 总计/未完成/空 + Top5 耗时）| 统计工具是必要分析手段；Top5 定位编译瓶颈 |
| Build Error Diagnostics（错误包自动查找）| 末行非 `time:` 判定失败包，免人工翻 build.log；优先 error.txt |
| 失败 artifact 带 `.config` | 复现失败必须知道最终配置 |
| `mv logs logs.1`（非 rm）| 保留初次轮真实错误，重试轮可能已变上下文 |
| 单线程重试 `make -j1 V=sc -k` | V=sc 输出完整编译命令，确保 configure 真实报错不被并行截断 |
| ccache Stats & Cleanup（命中率/压缩比）| 判断"缓存是否有效"的关键指标 |
| 打包后输出 release/ 根目录结构（tree -L 1 / ls -al）| 人工快速核验产物完整性 |
| release 仅在"至少一个被计划任务真正成功"时运行 | 避免空转 + 误建空 release |
| Verify 步骤 `continue-on-error: true` | 诊断性质，缓存恢复失败不应阻塞构建 |
| 更新 feed 前 `set -euo pipefail` | 禁止静默吞错（全局规则） |

## 通用约定

- 禁止静默错误：`|| true` / `2>/dev/null` 吞真实错误 / 丢 PIPESTATUS / 删日志 均为禁止。
- 所有 `||` 回退必须显式打印失败原因（`echo "⚠️ xxx failed: $?"`）。
- 步骤名带 emoji + 编号（v1 遗产），关键步骤内用 `╔═╗` 标题框。
