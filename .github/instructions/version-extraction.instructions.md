---
description: "ImmortalWrt/OpenWrt 版本号提取约束。修改 version.mk、SDK/IB 命名、patch_version、source_version 或 CI 版本解析逻辑时必读。"
applyTo: ["**/*.yml", "**/version.mk", "**/include/version.mk", "openwrt-configs/**"]
---

# Version Extraction Pitfalls (ImmortalWrt/OpenWrt)

**Verified**: 2026-08-05
**Scope**: Must read when modifying SDK/IB packaging, version.mk patches, version parsing scripts, `index.json` keys, or related CI logic.

## Problem Symptoms

The `📦 Package SDK & IB tarballs` (or similar) step fails after extracting the version, with exit 127:

```text
/home/runner/.../cc....sh: line 14: CONFIG_VERSION_NUMBER: command not found
/home/runner/.../cc....sh: line 14: callqstrip,: command not found
```

The injected value `SDK_VERSION="$(callqstrip,$(CONFIG_VERSION_NUMBER))"` is then executed by the shell as a command substitution.

## Root Cause

Upstream `include/version.mk` (both 21.02 and main branches) defines `VERSION_NUMBER` using make expressions:

```makefile
VERSION_NUMBER:=$(call qstrip,$(CONFIG_VERSION_NUMBER))
VERSION_NUMBER:=$(if $(VERSION_NUMBER),$(VERSION_NUMBER),21.02-SNAPSHOT)   # qualcommax falls back to SNAPSHOT
```

If the "Apply Configuration" step runs:

```bash
grep -m1 '^VERSION_NUMBER:=' include/version.mk | cut -d= -f2 | tr -d '[:space:]'
```

it captures `$(callqstrip,$(CONFIG_VERSION_NUMBER))` (spaces removed by tr). This polluted value is written to `GITHUB_OUTPUT` and later expanded inside shell scripts, producing "command not found".

**Important**: `.config` usually does **not** contain a `CONFIG_VERSION_NUMBER=` assignment (it only appears inside `PKG_CONFIG_DEPENDS`), so it cannot be relied upon.

## Strict Parse Order (must follow exactly)

1. `.config` line `CONFIG_VERSION_NUMBER="..."` (only if present and a plain string, no `$`).
2. First literal `VERSION_NUMBER:=` line from `version.mk` (the value must not start with `$` or contain `$(`).
3. Fallback literal extracted from the `$(if $(VERSION_NUMBER),$(VERSION_NUMBER),<fallback>)` line.
4. Final fallback `SNAPSHOT`.

Any candidate containing `$`, `$(`, or `call ` must be treated as a make expression and **skipped**.

## The Three Version Variables (strict distinction)

| Variable          | Source                                              | Intended Use                                                             | Use to strip tarball prefix? |
|-------------------|-----------------------------------------------------|--------------------------------------------------------------------------|------------------------------|
| `source_version`  | Original version + date suffix (for snapshots)      | `index.json` keys, directory names, human-readable labels                | No                           |
| `original_version`| Parsed pre-patch source version                     | Logging and comparison only                                              | No                           |
| `patched_version` | Result of `s/SNAPSHOT/${VERSION}/g` on original     | **The prefix actually embedded in tarballs produced by this build.** Must be used to strip the `<version>-` prefix from SDK/IB filenames. | **Yes (mandatory)**          |

**Fatal mistake example**: Using `original_version` (still containing `SNAPSHOT`) to match a filename starting with `21.02-V260805-...` will fail lookup or produce wrong `index.json` entries.

Example: `21.02` + build id `V260805` → `patched_version=21.02-V260805`.

## Recommended Practices

- Immediately after parsing, test the result with a regex for make expression remnants (`\$|\$\(|\bcall\b`). If matched, emit `::error::` and `exit 1`.
- Prefer reading from `.config`; fall back to `sed -n 's/^VERSION_NUMBER:=//p' | head -1` for the first literal, then the second line for the fallback value.
- When patching `version.mk`, modify **only** the `VERSION_NUMBER:=` line(s). Do not touch URLs or other `SNAPSHOT` occurrences.
- SDK/IB packaging steps must defensively validate that the version about to be injected does not contain make syntax.
- If upstream ever exposes `make -f include/version.mk -s -q print-version`, it may be used, but the result must still be validated as a plain string.
- Always emit all three variables (`source_version`, `original_version`, `patched_version`) in logs and outputs for diagnostics.

## Prohibited Actions

- Directly `grep|cut|tr` the `VERSION_NUMBER:=` line from `include/version.mk` and treat the result as the final version.
- Assume any parsed result is a clean version string without checking for expression remnants.
- Mix `source_version` and `patched_version` when naming artifacts, matching tarballs, or forming `index.json` keys.
- Export generic variables (`TARGET`, `HOST`, `BUILD`, etc.) in workflow `env:` or `run:` steps that can leak into the OpenWrt build environment (see also `project-constraints.instructions.md`).

## Evidence & References

- Complete root cause and shell expansion evidence: [docs/openwrt-build-pitfalls.md](../docs/openwrt-build-pitfalls.md) § Make expression version injection into shell
- Current implementation: [.github/workflows/compile-firmware.yml](https://github.com/solarflows/AutoWorkflows/blob/main/.github/workflows/compile-firmware.yml) (Apply Configuration step)
- Related consumers: `compile-firmware.yml`, `compile-packages.yml`; archived consumers remain under `.github/archive/workflows/` for historical reference.

## Change Checklist (complete before modifying related code)

- [ ] Ensure extraction logic follows the exact 4-level order above
- [ ] Add make-expression remnant detection before emitting any version variable
- [ ] Use `patched_version` (never `original_version` or `source_version`) when stripping the version prefix from SDK/IB tarballs
- [ ] Update this file and `docs/openwrt-build-pitfalls.md` if new evidence appears
- [ ] Document the version variable usage in the PR description

**Load this file before editing any code that touches ImmortalWrt/OpenWrt version numbers, SDK/IB naming, or version-related CI steps.**
