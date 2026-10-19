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
- Release 发布类型由运行级 `release_type`（`release` / `prerelease` / `draft`，默认 `release`）控制，必须同时作用于本次构建创建或更新的**全部** Release（固件、Passwall 软件包、SDK/IB `artifacts-<target>`），不得只改固件一处。`release` 在编辑已有 Release 时必须显式传 `--draft=false --prerelease=false`，以清除历史非正式状态。
- per-build 固件 Release 的 `--target` 统一钉构建源码 commit（全量 = `sha_full`，IB 增量 = `sdk_source_sha`，二者同源）；共享常驻 tag（`packages-*` / `artifacts-*`）刻意不传 `--target` 且 `--latest=false`——它们是滚动容器，版本指针由 index.json 承担。改动发布步骤时保持这一区分。
- `release_type != release` 的 run 不得把已转正（非 draft 非 prerelease）的同 tag **固件 Release** 降级改写：edit 前必须先查 `.draft`/`.prerelease`，已正式则硬失败。共享常驻 tag（packages/artifacts）刻意不加此守卫——其正式态是常态、tag 不含可复用的 version，`release_type` 直接生效即操作者意图。`--clobber` 资产覆盖是刻意设计（CI 重跑幂等），不是缺陷。
- `require_signing=true` 时签名密钥缺失/无效必须硬失败（`Setup Signing Key` 的 `random_fallback`），不得降级 random 后继续发布；默认 false 的"告警 + 构建继续"是刻意设计，保留。
- 同包版本收敛保留数（`matrix_artifacts_keep_versions` / `passwall_keep_versions`）下限为 1：有界保留是收敛的立项前提（G14），刻意不提供 0/禁用档。
- workflow 通过 `GH_TOKEN` 环境变量使用 `secrets.ACCESS_TOKEN` 进行 GitHub API 操作。
- 发布/签名行为实现在 `.github/scripts/release-lib.sh` 与 `signing-lib.sh`（R12 单一事实来源，两 executor source 引用）：新增发布开关/安全行为只改库，不在 executor 里重新内联拷贝；`--clobber` 覆盖、常驻 tag 不传 `--target`、keep 下限 1 均为刻意设计（见库头注释）。
- 废弃的 workflow 移到 `.github/archive/workflows/` 而不是删除，保留审计轨迹。