---
name: openwrt-build-diagnostics
description: "诊断 AutoWorkflows 的 OpenWrt/ImmortalWrt 构建失败、GitHub Actions artifact、error.txt、compile.txt、logs/logs.1、ccache、stamp skip 或 TARGET 环境变量泄漏时使用。严格只读并生成证据化报告。"
argument-hint: "日志目录、GitHub Actions run URL/ID，或粘贴的关键日志"
user-invocable: true
disable-model-invocation: false
---

# OpenWrt Build Diagnostics

Diagnose build failures without changing workflows, configuration, logs, or build state. Produce evidence, confidence, alternatives, and recommended verification steps. Apply fixes only in a separate task after a new plan and user confirmation.

## Input Gate

Use `.diagnostics/openwrt-build/<case-id>/` for downloaded, extracted, or pasted input. Prefer that location even when another source is available.

Treat the input as valid when it contains at least one non-empty `error.txt`, `compile.txt`, Actions job log, or user-provided build log. An existing but empty directory does not satisfy the gate.

If valid input is missing, stop diagnosis and ask the user to choose:

1. Download and extract logs into the displayed case directory, then return when ready.
2. Authorize automatic retrieval of a selected GitHub Actions run or artifact.
3. Paste a bounded relevant log section.
4. Cancel diagnosis.

Recommend option 1. Waiting means ending the current execution at this input gate and resuming after the user's next message. Never poll, sleep, or keep a terminal process waiting for files.

## Automatic Retrieval

1. Use architecture-native GitHub tools when they can list runs and download artifacts.
2. Otherwise use the installed `gh` CLI after checking authentication and repository context.
3. If no run ID or URL was supplied, show a bounded list of likely failed runs and ask the user to select one. Do not assume the latest failure is the target.
4. Download and extract into `.diagnostics/openwrt-build/<case-id>/` without overwriting unrelated case data.
5. Report download, authentication, extraction, and encoding failures explicitly.

## Procedure

1. Confirm the input gate and identify the case directory.
2. Run [the analyzer](./scripts/analyze_build_logs.py):

   ```text
   python <skill-dir>/scripts/analyze_build_logs.py <case-directory>
   ```

3. Read `<case-directory>/report/summary.md` and use `analysis.json` for structured evidence.
4. Inspect only the bounded source excerpts needed to test the primary and alternative hypotheses.
5. Consult [diagnostic signatures](./references/diagnostic-signatures.md) when a known signature appears.
6. Report:
   - Summary
   - Primary hypothesis
   - Evidence with source paths
   - Alternative hypotheses
   - Confidence
   - Missing evidence
   - Recommended fix
   - Verification steps

## Read-Only Boundary

- Do not edit workflows, seeds, package files, or source code.
- Do not delete, clean, rename, or mutate input logs.
- Do not trigger reruns or download artifacts without user authorization.
- Do not present a recommendation as an applied fix.
- Keep complete evidence in files and bound all terminal/tool output.