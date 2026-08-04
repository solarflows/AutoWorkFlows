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

## SDK and ImageBuilder Retention

SDK and ImageBuilder archives are stored under `sdk-<target>` and `ib-<target>` release tags with an `index.json`. Replace files for the same version with `--clobber`. For different versions, retain the configured number of version groups. Sorting must compare numeric fields numerically, map SNAPSHOT to a stable sentinel, and parse `V<n>` as a number.