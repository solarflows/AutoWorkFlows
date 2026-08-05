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

So the fix for v1/v2 is not to stabilise the checkout hash (impossible on rolling branches) but to prevent the purge from deleting the just-saved cache. The `test`-branch hash churn is only an aggravating factor: it makes exact-key misses frequent and the old delete-everything branch fire often. Even a stable hash would still self-delete in v2, because the first miss → save → purge would erase the save before the next run.

### Fix

Implemented in `compile-firmware.yml` (commit: TBD — backfill after push):

- **Reorder: purge before save.** The `Purge stale GitHub Actions caches` step now runs **before** `Save toolchain cache`. At purge time the current run's cache does not yet exist, so it cannot be deleted by construction — the same ordering that made v1's post-action save and ccache's combined `actions/cache@v5` safe. No per-key exclusion is needed.
- Delete **all** toolchain caches only when `cache_strategy ∈ {clean-all, clean-toolchain}` (explicit refresh). In those modes the subsequent save stores the freshly rebuilt toolchain instead of wasting it.
- In `smart` mode, list `immwrt-v2-toolchain-<target>-*` caches, sort by `createdAt` ascending, and delete only the oldest, keeping the most recent 3.
- Apply the same keep-most-recent-3 rule to ccache in `smart` mode (`immwrt-v2-ccache-<target>-*`).
- In `clean-all`/`clean-ccache` modes, purge deletes all ccache entries, and the post-action save (ccache uses combined `actions/cache@v5`) stores the fresh one.

Verification results (Task C): TBD — backfill after a smart-mode run.

### ccache Key Design and Improvement Assessment

ccache is a **cumulative** cache: every compile adds more objects, and its invalidation factors are not enumerable (any package Makefile, CFLAGS, or dependency change can alter compiler output). It therefore uses a per-run `run_id` key with `restore-keys` prefix fallback (v1 comment: "run_id ensures every successful build saves the latest cache; restore-keys falls back to the most recent snapshot").

Why a fixed key is **not** viable for ccache: GitHub Actions caches are immutable, and `actions/cache` skips saving when the exact key already exists (`Cache already exists. Skipping save`). A fixed key would freeze ccache at its first snapshot forever — later accumulated objects would never be persisted, and hit rate would decay silently. The `run_id` design guarantees the freshest snapshot is saved every run.

Why ccache is safe from the self-deletion bug: it still uses the combined `actions/cache@v5`, whose save is a post action **after** the Purge step — the same ordering that protected v1's toolchain. The old purge did delete all ccache entries on every run (exact hit is always false), but the post-save re-created one, keeping it functional.

Assessment after the fix — current state is sound; optional refinements:

- ccache is already bounded and optimised in the build step (inherited from v1): `ccache --max-size 10G`, `compiler_check=content`, `hash_dir=false`, `compression=true` + `compression_level=6`, and `sloppiness=file_stat_matches,include_file_mtime,include_file_ctime,time_macros`. These are the v1 hit-rate optimisations, fully carried over to v2 (`compile-firmware.yml` build step).
- The smart-mode purge now keeps the most recent 3 ccache entries instead of deleting all (old behaviour re-created just one per run).

### Diagnostic Notes

- Tools recompilation is not an architecture bug. First check whether a toolchain cache exists at all.
- Distinguish `Cache restored from key: ...` (hit) from `Cache not found for input keys: ...` (miss).
- If even the restore-keys prefix misses, the cache never survived a run — check the self-deletion pattern.

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