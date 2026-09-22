---
description: "修改 SDK、ImageBuilder、固件、Passwall 产物的生成、打包、命名、Release 上传、CI Secret 或归档逻辑时使用。"
applyTo: [".github/workflows/compile-firmware.yml", ".github/workflows/compile-packages.yml", ".github/workflows/firmware-build-unified.yml"]
---

# 构建产物与仓库操作

- SDK 归档命名为 `sdk-<target>-<version>-<arch>.tar.xz`，ImageBuilder 归档命名为 `ib-<target>-<version>-<arch>.tar.xz`。
- 每个 target 的 SDK 与 ImageBuilder 归档发布到共享的 `artifacts-<target>` release tag 下。`sdk-index.json` 与 `ib-index.json` 分开维护，两个索引不得互相覆盖。
- `<version>` 取自 `include/version.mk` 的 `VERSION_NUMBER`，但必须先解析为纯字符串——`VERSION_NUMBER:=` 行可能是 make 表达式；完整解析顺序与防御规则见 [version-extraction.instructions.md](version-extraction.instructions.md)。严禁把原始表达式注入 shell 步骤或 `index.json` key（报 `command not found`，exit 127）。SNAPSHOT 构建追加日期。
- 上游产物命名为 `<dist>-sdk-*.tar.{xz,zst}` 与 `<dist>-imagebuilder-*.tar.{xz,zst}`；用 `*-sdk-*.tar.*` / `*-imagebuilder-*.tar.*` 定位，重命名为 `sdk-`/`ib-` 前缀形式。
- 重命名后重新计算校验和，写成两列 `.sha256`（`<hash>  <filename>`）。不要复用上游的 `.sha256sum`：其内嵌文件名或目录前缀可能与重命名后的文件不匹配，而 `sha256sum -c` 要求所列文件名存在。
- 固件归档命名为 `<target>-release.tar.gz`，包含 `release/firmware` 与 `release/passwall`。
- workflow 通过 `GH_TOKEN` 环境变量使用 `secrets.ACCESS_TOKEN` 进行 GitHub API 操作。
- 废弃的 workflow 移到 `.github/archive/workflows/` 而不是删除，保留审计轨迹。