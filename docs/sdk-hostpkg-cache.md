# SDK Hostpkg Cache Sharing Plan

This document explains why the SDK incremental path needs its own host/tool cache, how it falls back to the full-build toolchain cache, and how its compiler ccache snapshots remain separate from the full-build shared ccache. It mirrors the implementation in `.github/workflows/compile-packages.yml` and `.github/workflows/compile-firmware.yml`.

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

Use a dedicated immutable-snapshot namespace `immwrt-v2-sdk-hostpkg-<target>-<run_id>`. The target and run ID make each save immutable and allow the newest snapshot to roll automatically. Both executors write this namespace (the full executor seeds it after a successful full build so the SDK path starts warm) and **both converge it to the newest single snapshot**, so a full-build-only period can no longer grow the namespace without bound:

```yaml
# SDK restore: target prefix, run_id only for the new immutable snapshot
key: immwrt-v2-sdk-hostpkg-${{ env.IMMWRT_TARGET }}-${{ github.run_id }}
restore-keys: |
  immwrt-v2-sdk-hostpkg-${{ env.IMMWRT_TARGET }}-
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

- `key` uses the target and `github.run_id`; the target restore prefix reuses the newest immutable snapshot, while every save is a new rolling key. The selected SDK artifact's `source_sha` remains recorded and checked when resolving SDK/IB, but it is not part of the cache key. SDK has no `.git`, so it cannot compute the full-build `git log tools toolchain` hash.
- `save` runs only after SDK package compilation succeeds and is `continue-on-error`; a cache API failure must not invalidate the package/IB result. The SDK purge keeps one snapshot per target in total (the current snapshot) and explicitly excludes the current key.
- The full-toolchain fallback is a **separate restore action**, not another `restore-keys` entry. The workflow first queries accessible immutable keys with `gh cache list`, then restores the selected SDK snapshot exactly. If that lookup misses or fails, the SDK restore is not assumed to have succeeded and the fallback uses the full producer's path list (`staging_dir/host*` and `staging_dir/tool*`; `host*` may include `staging_dir/hostpkg`). The full fallback then uses its own prefix as a best-effort lookup; `cache-hit == false` is not treated as proof that no prefix snapshot was restored.
- A full build also produces an SDK host/tool snapshot with the same path/key scheme, and it bounds that namespace to its own newest snapshot (`Purge stale SDK hostpkg snapshots`). Without that bound, a full-build-only period grows the namespace by 0.5–1.7GB per target per run: the full executor never restores this namespace, so no reader ever refreshes it and no SDK run exists to purge it.
- The bound belongs to the writer because it keeps the release deterministic (delete only after the new snapshot is saved) and keeps platform eviction from having to choose at all. Quota arithmetic and the verified eviction behaviour are recorded in `openwrt-build-pitfalls.md` § GitHub Actions Cache Quota and Eviction; the full-build `immwrt-v2-toolchain-*` and shared `immwrt-v2-ccache-*` namespaces remain maintained by `compile-firmware.yml`.

## Cache strategy routing

`firmware-build-unified.yml` normalizes the selected strategy in `plan`. `smart` may route to SDK-only or SDK+IB; every other supported strategy routes to the full executor. The reusable executor still performs the selected cache operations: clean strategies skip the relevant restore and rebuild/save a fresh snapshot, while `no-cache` skips Actions Cache persistence but does not forcibly override `CONFIG_CCACHE` inside OpenWrt.

## Related SDK-path changes (same commit)

Compile output `V=s` → `V=sc` (per-package logs still go to `logs/<pkg>/compile.txt` via `BUILD_LOG=1`); `Purge stale ccache caches` renamed to `Purge stale ccache snapshots`; Summary shows cache hit tables and ccache hit-rate. ccache compression, `time_macros`, and the remaining sloppiness options require A/B validation before changing.

## ccache sharing boundary

Both executors use the same `openwrt/.ccache` path and 100% share the unified `immwrt-v2-ccache-<target>-<run_id>` namespace. OpenWrt's `rules.mk` supplies `CCACHE_DIR=$(TOPDIR)/.ccache` and `CCACHE_BASEDIR=$(TOPDIR)`; both workflows use `openwrt` as `TOPDIR`. Full builds and SDK incremental builds restore from `immwrt-v2-ccache-<target>-` prefix, write back to `immwrt-v2-ccache-<target>-<run_id>`, and purge older snapshots to retain only the newest 1 snapshot per target. This eliminates duplicate ccache snapshots, frees ~2.2GB of quota, and allows compiler objects to be shared bidirectionally.

## Verification

- First SDK/IB run after this change: expect an SDK-specific miss followed, only then, by a separate full-toolchain fallback restore; a successful compile saves `immwrt-v2-sdk-hostpkg-<target>-<run_id>`.
- Subsequent runs for the same target: expect an SDK-specific prefix hit and no repeated cold host-tool bootstrap for cached paths; if a tool is incompatible with the selected SDK, OpenWrt stamps force the affected tool to rebuild.
- A successful compile saves the updated `immwrt-v2-ccache-<target>-<run_id>` into the shared ccache namespace, retaining only the latest single snapshot.
