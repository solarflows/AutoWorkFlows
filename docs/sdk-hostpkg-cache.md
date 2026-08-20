# SDK Hostpkg Cache Sharing Plan

This document explains why the SDK incremental path needs its own host/tool cache, how it falls back to the full-build toolchain cache, and how both paths share ccache. It mirrors the implementation in `.github/workflows/compile-packages.yml` and `.github/workflows/compile-firmware.yml`.

## Background

The SDK incremental path (`compile-packages.yml`) compiles ~19 passwall-chain packages per target. On qualcommax (SNAPSHOT), each cold run spent ~1h33m bootstrapping a host **rustc 1.96.0** from source (plus golang host toolchain and npm dependency downloads). Full builds with cache finished mt798x in 30-40min and qualcommax in 1h30-2h, because the full-build `immwrt-v2-toolchain-<target>-*` cache restored prebuilt host tools.

## Attempt 1: Share the full-build toolchain cache (rejected)

The historical SDK job added `Restore toolchain cache`, restoring `immwrt-v2-toolchain-<target>-*` into `staging_dir/host*` and `staging_dir/tool*`. That path list was part of the rejected design and is retained here only to explain the failure.

### Verified failure (run 31926183611)

The cache **hit** (`Cache hit for restore-key: immwrt-v2-toolchain-qualcommax-force-1f96307`) but the qualcommax build still exceeded 2h. Root cause: the historical full-build cache `path` only contained:

- `openwrt/staging_dir/host*` (generic host tools)
- `openwrt/staging_dir/tool*` (cross toolchain)

It does **not** contain the SDK's actual cold spots:

| Tool | Install location | In full-build cache? |
|------|------------------|----------------------|
| rustc | `staging_dir/target-<arch>/host/` | ❌ (`target-*` not cached) |
| golang | `build_dir/hostpkg/go-*` + `staging_dir/hostpkg/` | ⚠️ build_dir not cached |
| node | `build_dir/hostpkg/node-*` + `staging_dir/hostpkg/` | ⚠️ build_dir not cached |
| GOCACHE | `tmp/go-build` | ❌ |
| cargo crates | `dl/cargo`, `dl/rustc` | ❌ |

So the shared restore restored cross toolchain the SDK tarball already ships, and missed everything the SDK actually rebuilds. Hit ≠ speedup.

## Attempt 2: SDK-owned host/tool cache (current)

Use a dedicated immutable-snapshot namespace `immwrt-v2-sdk-hostpkg-<target>-<sdk_source_sha>-<run_id>`. The SDK executor owns restore, save, and retention; the full executor may produce the same snapshot after a successful full build but never purges this namespace:

```yaml
# SDK restore: source-specific prefix, run_id only for the new immutable snapshot
key: immwrt-v2-sdk-hostpkg-${{ env.IMMWRT_TARGET }}-${{ steps.resolve.outputs.sdk_source_sha }}-${{ github.run_id }}
restore-keys: |
  immwrt-v2-sdk-hostpkg-${{ env.IMMWRT_TARGET }}-${{ steps.resolve.outputs.sdk_source_sha }}-
path: |
  openwrt/staging_dir/hostpkg
  openwrt/staging_dir/target-*/host
  openwrt/dl/cargo
  openwrt/dl/rustc
  openwrt/tmp/go-build

# Separate fallback restore; it must use the full cache's exact paths.
key: immwrt-v2-toolchain-${{ env.IMMWRT_TARGET }}-sdk-fallback-${{ github.run_id }}
restore-keys: |
  immwrt-v2-toolchain-${{ env.IMMWRT_TARGET }}-
path: |
  openwrt/staging_dir/host*
  openwrt/staging_dir/tool*
```

- `key` binds to `sdk_source_sha` and appends `github.run_id`; the source-specific restore prefix reuses the newest snapshot for that SDK, while every save is a new immutable key. SDK has no `.git`, so it cannot compute the full-build `git log tools toolchain` hash.
- `save` runs only after SDK package compilation succeeds and is `continue-on-error`; a cache API failure must not invalidate the package/IB result. The SDK purge keeps three snapshots per target in total (the current snapshot plus at most two older snapshots) and explicitly excludes the current key.
- The full-toolchain fallback is a **separate restore action**, not another `restore-keys` entry. The workflow first queries accessible immutable keys with `gh cache list`, then restores the selected SDK snapshot exactly. If that lookup misses or fails, the SDK restore is not assumed to have succeeded and the fallback uses the full producer's path list (`staging_dir/host*` and `staging_dir/tool*`; `host*` may include `staging_dir/hostpkg`). The full fallback then uses its own prefix as a best-effort lookup; `cache-hit == false` is not treated as proof that no prefix snapshot was restored.
- A full build may produce an SDK snapshot with the same path/key scheme. It does not purge the SDK namespace; SDK runs own retention. The full-build `immwrt-v2-toolchain-*` and `immwrt-v2-ccache-*` namespaces remain maintained by `compile-firmware.yml`.

## Cache strategy routing

`firmware-build-unified.yml` normalizes the selected strategy in `plan`. `smart` may route to SDK-only or SDK+IB; every other supported strategy routes to the full executor. The reusable executor still performs the selected cache operations: clean strategies skip the relevant restore and rebuild/save a fresh snapshot, while `no-cache` skips Actions Cache persistence but does not forcibly override `CONFIG_CCACHE` inside OpenWrt.

## Related SDK-path changes (same commit)

- Compile loop output `V=s` → `V=sc`: per-package logs already go to `logs/<pkg>/compile.txt` via `BUILD_LOG=1`; the terminal keeps summaries/commands only (was 56-84MB of redundant CI logs).
- `Purge stale ccache caches` renamed to `Purge stale ccache snapshots` (clears stale cache snapshots, not the ccache data itself).
- Summary note now shows cache hit tables (ccache + SDK host/tool restore source / fallback / save key) and ccache hit-rate (compatible with ccache 5.x `cache hit rate` and 6.x `Hits: x/y`); raw `ccache -s` output stays in the terminal.
- Workflow-level ccache compression and `time_macros` are not forced; the remaining sloppiness options require A/B validation before further changes.

## ccache sharing boundary

Both executors restore the same `openwrt/.ccache` path and use the target-specific `immwrt-v2-ccache-<target>-<run_id>` namespace. OpenWrt's `rules.mk` supplies `CCACHE_DIR=$(TOPDIR)/.ccache` and `CCACHE_BASEDIR=$(TOPDIR)`; both workflows use `openwrt` as `TOPDIR`. This makes sharing structurally valid, but hit rate still depends on compiler version, target triple, flags, configuration, source, and wrapper form. SDK consumes the shared ccache and does not save or purge it.

## Verification

- First SDK/IB run after this change: expect an SDK-specific miss followed, only then, by a separate full-toolchain fallback restore; a successful compile saves `immwrt-v2-sdk-hostpkg-<target>-<sha>-<run_id>`.
- Subsequent runs with the same SDK source SHA: expect an SDK-specific prefix hit and no repeated cold host-tool bootstrap for cached paths.
- A full build may create the SDK snapshot, while retention is performed only by the SDK executor.
