# SDK Hostpkg Cache Sharing Plan

Documents why the SDK incremental path needs its own hostpkg cache, why sharing the full-build toolchain cache does not work, and the final fallback design. Mirrors the decision log in `.github/workflows/compile-packages.yml`.

## Background

The SDK incremental path (`compile-packages.yml`) compiles ~19 passwall-chain packages per target. On qualcommax (SNAPSHOT), each cold run spent ~1h33m bootstrapping a host **rustc 1.96.0** from source (plus golang host toolchain and npm dependency downloads). Full builds with cache finished mt798x in 30-40min and qualcommax in 1h30-2h, because the full-build `immwrt-v2-toolchain-<target>-*` cache restored prebuilt host tools.

## Attempt 1: Share the full-build toolchain cache (rejected)

Added `Restore toolchain cache` in the SDK job, restoring `immwrt-v2-toolchain-<target>-*` into `staging_dir/host*` and `staging_dir/tool*`.

### Verified failure (run 31926183611)

The cache **hit** (`Cache hit for restore-key: immwrt-v2-toolchain-qualcommax-force-1f96307`) but the qualcommax build still exceeded 2h. Root cause: the full-build cache `path` only contains:

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

## Attempt 2: SDK-owned hostpkg cache (current)

Use a dedicated namespace `immwrt-v2-sdk-hostpkg-<target>-<sdk_source_sha>` with `restore` + `save` + `purge` fully managed by the SDK path:

```yaml
key: immwrt-v2-sdk-hostpkg-${{ env.IMMWRT_TARGET }}-${{ steps.resolve.outputs.sdk_source_sha }}
restore-keys: |
  immwrt-v2-sdk-hostpkg-${{ env.IMMWRT_TARGET }}-
  immwrt-v2-toolchain-${{ env.IMMWRT_TARGET }}-
path: |
  openwrt/staging_dir/hostpkg
  openwrt/staging_dir/target-*/host
  openwrt/dl/cargo
  openwrt/dl/rustc
  openwrt/tmp/go-build
```

- `key` binds to `sdk_source_sha` (the SDK tarball source version), so same-version SDK runs hit exactly; SDK has no `.git`, so it cannot compute the full-build `git log tools toolchain` hash.
- `save` runs only on compile success; `purge` keeps the newest 3 snapshots per target (hostpkg is version-distinct, so latest-only deletion would drop rollback candidates).
- The second `restore-keys` entry is the **fallback to the full-build toolchain cache**: when no SDK-owned snapshot exists yet, the run still picks up `immwrt-v2-toolchain-<target>-*` (restoring `host*`/`tool*`). The path/version mismatch warns but extracts normally; rustc still bootstraps on that first run, and the run's own `save` creates the complete SDK-owned snapshot.
- SDK `save`/`purge` only touch `immwrt-v2-sdk-hostpkg-*`; the full-build `immwrt-v2-toolchain-*` / `immwrt-v2-ccache-*` namespaces remain write/purge-managed exclusively by `compile-firmware.yml`.

## Related SDK-path changes (same commit)

- Compile loop output `V=s` → `V=sc`: per-package logs already go to `logs/<pkg>/compile.txt` via `BUILD_LOG=1`; the terminal keeps summaries/commands only (was 56-84MB of redundant CI logs).
- `Purge stale ccache caches` renamed to `Purge stale ccache snapshots` (clears stale cache snapshots, not the ccache data itself).
- Summary note now shows cache hit tables (ccache + SDK hostpkg restore source / save key) and ccache hit-rate (compatible with ccache 5.x `cache hit rate` and 6.x `Hits: x/y`); raw `ccache -s` output stays in the terminal.

## Verification

- First SDK/IB run after this change: expect `Cache hit for restore-key: immwrt-v2-toolchain-<target>-*` (fallback), then a `Cache saved with key: immwrt-v2-sdk-hostpkg-<target>-<sha>` snapshot.
- Subsequent runs with the same SDK version: expect exact hit on `immwrt-v2-sdk-hostpkg-<target>-<sha>` and no 1h+ rustc bootstrap gap in the per-package timestamps.
