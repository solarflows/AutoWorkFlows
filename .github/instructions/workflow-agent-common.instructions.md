---
description: "AutoWorkflows 工作流 Agent 的通用修改、安全和验证规则。"
applyTo: [".github/workflows/**", ".github/upstream-sync/**", ".github/custom-feed/**", ".github/agents/**", ".github/actions/**"]
---

# AutoWorkflows 工作流 Agent 通用规则

- 编辑前先读 `AGENTS.md` 与适用的 file-specific instructions。
- 改动限定在被请求的 workflow、脚本、补丁或文档范围内。
- 不执行 commit、push、rebase、tag、触发远端 workflow、修改 Release 或删除远端数据。
- 绝不读取、打印、复制或暴露 `ACCESS_TOKEN`、`GH_TOKEN`、`GITHUB_TOKEN`、`APK_BUILD_KEY`、`USIGN_KEY` 等 secret。
- 绝不向 OpenWrt 相关进程导出 `TARGET`、`HOST`、`BUILD`（详见 [project-constraints.instructions.md](project-constraints.instructions.md) § 环境变量禁令）。
- `.github/archive/workflows/` 仅作历史参考。
- 保留有意义的失败。不得用宽泛的 `|| true`、丢弃 stderr 或无条件成功兜底来掩盖错误。
- 编辑后先验证最小相关面，优先运行可复用脚本 `.github/scripts/validate-workflows.py`（PyYAML 解析 + 全部 bash `run:` 块 `bash -n` + 指纹管道语义回归），避免重复造轮子；脚本不可用时再手工执行等价检查：
  - 解析 workflow YAML。
  - 对改动的多行 `run:` 块执行 `bash -n`。
  - 有源码 fixture 时对改动的补丁执行 `git apply --check`。
  - 适用时校验生成的名称、校验和、路径与 workflow 输入/输出契约。
- Windows 上临时下载或解压的证据放入 `.diagnostics/`。
- 真实 OpenWrt 构建日志使用 `openwrt-build-diagnostics` skill，不要重复其流程。
- 报告时先列阻断性发现（按严重度排序），再列假设、验证结果、残余风险与简短改动摘要。