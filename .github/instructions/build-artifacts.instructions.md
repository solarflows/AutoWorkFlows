---
description: "修改 SDK、ImageBuilder、固件、Passwall 产物的生成、打包、命名、Release 上传、CI Secret 或归档逻辑时使用。"
applyTo: [".github/workflows/*-release.yml", ".github/workflows/firmware-build.yml"]
---

# Build Artifacts and Repository Operations

- Name SDK archives `sdk-<target>-<version>-<arch>.tar.xz` and ImageBuilder archives `ib-<target>-<version>-<arch>.tar.xz`.
- Derive `<version>` from `VERSION_NUMBER` in `include/version.mk`, but resolve it to a plain string first — the `VERSION_NUMBER:=` line may be a make expression (`$(call qstrip,$(CONFIG_VERSION_NUMBER))`). Resolve in order: `.config`'s `CONFIG_VERSION_NUMBER`, the literal `VERSION_NUMBER:=` value, the `$(if ...)` fallback literal (e.g. `21.02-SNAPSHOT`), then `SNAPSHOT`. Never inject the raw expression into shell steps or `index.json` keys (fails with `command not found`, exit 127). Append the date for SNAPSHOT builds.
- Upstream artifacts are named `<dist>-sdk-*.tar.{xz,zst}` and `<dist>-imagebuilder-*.tar.{xz,zst}`; locate them with `*-sdk-*.tar.*` / `*-imagebuilder-*.tar.*` and rename to the `sdk-`/`ib-` prefixed form.
- Recompute the checksum after renaming into a two-column `.sha256` (`<hash>  <filename>`). Do not reuse the upstream `.sha256sum`: its embedded filename or directory prefix may not match the renamed file, and `sha256sum -c` requires the listed filename to exist.
- Name firmware archives `<target>-release.tar.gz` and include `release/firmware` and `release/passwall`.
- Workflows use `secrets.ACCESS_TOKEN` through `GH_TOKEN` for GitHub API operations.
- Move deprecated workflows to `.github/archive/workflows/` instead of deleting them, preserving the audit trail.