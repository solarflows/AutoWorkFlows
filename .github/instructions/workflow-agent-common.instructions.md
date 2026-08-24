---
description: "AutoWorkflows 工作流 Agent 的通用修改、安全和验证规则。"
applyTo: [".github/workflows/**", ".github/diy/**", ".github/agents/**"]
---

# AutoWorkflows Workflow Agent Rules

- Read `AGENTS.md` and the applicable file-specific instructions before editing.
- Keep edits scoped to the requested workflow, script, patch, or documentation.
- Do not commit, push, rebase, tag, trigger remote workflows, modify Releases, or delete remote data.
- Never read, print, copy, or expose secrets such as `ACCESS_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN`, `APK_BUILD_KEY`, or `USIGN_KEY`.
- Never export `TARGET`, `HOST`, or `BUILD` into OpenWrt-related processes.
- Treat `.github/archive/workflows/` as historical reference only.
- Preserve meaningful failures. Do not hide errors with broad `|| true`, discarded stderr, or unconditional success fallbacks.
- After edits, validate the narrowest relevant surface first:
  - Parse workflow YAML.
  - Run `bash -n` on changed multiline `run:` blocks.
  - Run `git apply --check` for changed patches when a source fixture is available.
  - Verify generated names, checksums, paths, and workflow input/output contracts when applicable.
- Use `.diagnostics/` for temporary downloaded or extracted evidence on Windows.
- For real OpenWrt build logs, use the `openwrt-build-diagnostics` skill instead of duplicating its procedure.
- Report blocking findings first, ordered by severity, followed by assumptions, validation results, residual risks, and a short change summary.