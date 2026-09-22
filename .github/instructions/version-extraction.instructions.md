---
description: "ImmortalWrt/OpenWrt 版本号提取约束。修改 version.mk、SDK/IB 命名、patch_version、source_version 或 CI 版本解析逻辑时必读。"
applyTo: [".github/workflows/**", "**/version.mk", "openwrt-configs/**"]
---

# 版本号提取陷阱（ImmortalWrt/OpenWrt）

**验证日期**: 2026-08-05
**适用范围**: 修改 SDK/IB 打包、version.mk 补丁、版本解析脚本、`index.json` key 或相关 CI 逻辑前必读。

## 故障现象

`📦 Package SDK & IB tarballs`（或类似）步骤在提取版本后失败，exit 127：

```text
/home/runner/.../cc....sh: line 14: CONFIG_VERSION_NUMBER: command not found
/home/runner/.../cc....sh: line 14: callqstrip,: command not found
```

注入值 `SDK_VERSION="$(callqstrip,$(CONFIG_VERSION_NUMBER))"` 随后被 shell 当作命令替换执行。

## 根因

上游 `include/version.mk`（21.02 与 main 分支均如此）用 make 表达式定义 `VERSION_NUMBER`：

```makefile
VERSION_NUMBER:=$(call qstrip,$(CONFIG_VERSION_NUMBER))
VERSION_NUMBER:=$(if $(VERSION_NUMBER),$(VERSION_NUMBER),21.02-SNAPSHOT)   # qualcommax 回退到 SNAPSHOT
```

如果 "Apply Configuration" 步骤执行：

```bash
grep -m1 '^VERSION_NUMBER:=' include/version.mk | cut -d= -f2 | tr -d '[:space:]'
```

会捕获到 `$(callqstrip,$(CONFIG_VERSION_NUMBER))`（空格被 `tr` 删除）。这个被污染的值写入 `GITHUB_OUTPUT` 后在 shell 脚本中展开，产生 "command not found"。

**注意**: `.config` 通常**不包含** `CONFIG_VERSION_NUMBER=` 赋值（它只出现在 `PKG_CONFIG_DEPENDS` 里），不能依赖它。

## 严格解析顺序（必须按序执行）

1. `.config` 中的 `CONFIG_VERSION_NUMBER="..."` 行（仅当存在且为纯字符串、不含 `$`）。
2. `version.mk` 中第一行字面量 `VERSION_NUMBER:=`（值不得以 `$` 开头或包含 `$(`）。
3. 从 `$(if $(VERSION_NUMBER),$(VERSION_NUMBER),<fallback>)` 行提取的回退字面量。
4. 最终回退 `SNAPSHOT`。

任何包含 `$`、`$(` 或 `call ` 的候选值都必须视为 make 表达式并**跳过**。

## 三个版本变量（严格区分）

| 变量              | 来源                                                | 用途                                                                       | 用于剥离 tarball 前缀？ |
|-------------------|-----------------------------------------------------|----------------------------------------------------------------------------|-------------------------|
| `source_version`  | 原始版本 + 日期后缀（SNAPSHOT 时）                   | `index.json` key、目录名、人类可读标签                                      | 否                      |
| `original_version`| 解析出的补丁前源版本                                 | 仅日志与比较                                                                | 否                      |
| `patched_version` | 对原始版本执行 `s/SNAPSHOT/${VERSION}/g` 的结果      | **本次构建实际嵌入 tarball 的前缀。**剥离 SDK/IB 文件名 `<version>-` 前缀时必须用它。 | **是（强制）**          |

**致命错误示例**: 用仍含 `SNAPSHOT` 的 `original_version` 去匹配以 `21.02-V260805-...` 开头的文件名，会查找失败或产生错误的 `index.json` 条目。

示例：`21.02` + 构建号 `V260805` → `patched_version=21.02-V260805`。

## 推荐做法

- 解析后立即用正则（`\$|\$\(|\bcall\b`）检测结果中的 make 表达式残留；命中则输出 `::error::` 并 `exit 1`。
- 优先读 `.config`；回退到 `sed -n 's/^VERSION_NUMBER:=//p' | head -1` 取第一行字面量，再从第二行取回退值。
- 给 `version.mk` 打补丁时**只**改 `VERSION_NUMBER:=` 行，不要动 URL 或其它 `SNAPSHOT` 出现处。
- SDK/IB 打包步骤必须防御性校验即将注入的版本不含 make 语法。
- 若上游将来提供 `make -f include/version.mk -s -q print-version`，可以使用，但结果仍须校验为纯字符串。
- 始终在日志与输出中同时输出三个变量（`source_version`、`original_version`、`patched_version`）以便诊断。

## 禁止事项

- 直接对 `include/version.mk` 的 `VERSION_NUMBER:=` 行 `grep|cut|tr` 并把结果当作最终版本。
- 不做表达式残留检查就假定解析结果是干净的版本字符串。
- 在产物命名、tarball 匹配或 `index.json` key 中混用 `source_version` 与 `patched_version`。
- 在 workflow 的 `env:` 或 `run:` 步骤中导出通用变量（`TARGET`、`HOST`、`BUILD` 等），避免泄漏进 OpenWrt 构建环境（见 [project-constraints.instructions.md](project-constraints.instructions.md) § 环境变量禁令）。

## 证据与参考

- 完整根因与 shell 展开证据：[docs/openwrt-build-pitfalls.md](../../docs/openwrt-build-pitfalls.md) § Make expression version injection into shell
- 当前实现：[.github/workflows/compile-firmware.yml](https://github.com/solarflows/AutoWorkflows/blob/main/.github/workflows/compile-firmware.yml)（Apply Configuration 步骤）
- 相关消费方：`compile-firmware.yml`、`compile-packages.yml`；已归档的消费方保留在 `.github/archive/workflows/` 供历史参考。

## 改动检查清单（修改相关代码前完成）

- [ ] 确保提取逻辑严格遵循上述 4 级顺序
- [ ] 输出任何版本变量前加入 make 表达式残留检测
- [ ] 剥离 SDK/IB tarball 版本前缀时使用 `patched_version`（绝不用 `original_version` 或 `source_version`）
- [ ] 出现新证据时更新本文件与 `docs/openwrt-build-pitfalls.md`
- [ ] 在 PR 描述中记录版本变量的用法

**修改任何涉及 ImmortalWrt/OpenWrt 版本号、SDK/IB 命名或版本相关 CI 步骤的代码前，先加载本文件。**
