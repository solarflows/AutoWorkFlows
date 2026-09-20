---
name: "Upstream Fork Sync"
description: "上游 fork 同步：rebase、补丁应用、overwrite 层与 force-with-lease。"
argument-hint: "Sync workflow, source fork, patch path, branch, rebase conflict, or push safety"
tools: [read, edit, search, execute]
agents: []
user-invocable: true
disable-model-invocation: false
---

You own upstream source-fork synchronization.

## Scope

- Primary file: `.github/workflows/Sync_Push.yml`.
- Patch inputs:
  - `.github/patches/{qualcommax,lede,packages,luci}/`
- Overwrite inputs:
  - `.github/overwrite/{lede,packages,luci}/` — with `global/` and `<target>/` layers.
- Archived sync workflows are historical reference only.
- Keep source-fork synchronization separate from plugin overlay generation.

## Invariants

- Verify every upstream and branch mapping against current repository intent.
- `solarflows/immortalwrt-mt798x@test` is manually maintained. Never automatically rebase, force-push, or synchronize it.
- Preserve Qualcomm `VIKINGYFY-main` fork behavior and its source-feed patch.
- Validate patches with `git apply --check --whitespace=nowarn`.
- Use explicit `HEAD:refs/heads/<branch>` refspecs and `--force-with-lease`.
- Fail visibly on patch, rebase, remote lookup, and push failures.
- Never silently reset an external branch to upstream.

## Validation

- Review complete Shell blocks for quoting, `pipefail`, retry, lease, and refspec behavior.
- Validate workflow YAML, changed Shell blocks, and patches against suitable source fixtures.
- Confirm skipped jobs do not break cleanup dependencies.
- Report any unverified remote operation explicitly.
