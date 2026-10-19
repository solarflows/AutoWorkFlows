#!/usr/bin/env python3
"""AutoWorkflows 工作流验证脚本（可复用，git 追踪）。

定位（2026-10-19 重定位，见 todo H1）: **只做结构/静态检查**。
行为与功能完善性不属本脚本职责——过去第 4 节用 Python 复刻 bash/jq 管道再断言
期望输出，是"运动员兼裁判"的假安心（fixture 编码的是编写者当下的理解，C16/G13/
G15 四轮全是本地语义回归全绿后真实 run 才暴露缺陷）。行为验证的唯一裁判是
真实 run；本脚本只左移平台硬约束与已实证的退化模式。

用法:
    python .github/scripts/validate-workflows.py                 # 全部 7 个活跃 workflow
    python .github/scripts/validate-workflows.py a.yml b.yml     # 指定文件

检查项（全部静态，无行为模拟）:
  1. PyYAML 解析每个 workflow。
  2. 对每个 bash `run:` 块执行 `bash -n`（GitHub 表达式替换为占位值）。
  2b. 单 step `run:` 块长度告警阈值（GitHub 服务端 21000 字符上限, 超限 push/dispatch
      422 而本地 YAML/bash -n 不报错——左移该约束）。
  2c. 同步骤 GITHUB_ENV 自引用（C16 教训的静态形态）。
  3. 已移除机制的残留标识符（防半截子回退: 旧 lock 指纹、cache_strategy 五选项）。
  4. 静态防退化规则（每条对应一个真实 run 事故，grep 级检查，不解释行为）:
     - jq -n 写 .jsonl 必须带 -c（run 36226606223）
     - ls-tree -r 必须带 -t；gh api --jq 禁配 --argjson（run 36519189440 Bug A/B）
     - 追平闸门 diff 前缀含空格（本地拦截过的静默漏检形态）
     - seed 补齐 grep 用容忍模式（run 38112393097）
  5. docs/todo.md 台账 ID 全局唯一（重复即引用歧义，AGENTS.md 翻转规则失效）。
  6. reusable workflow 调用契约：`uses:` 本仓 workflow 的 with/secrets key 必须
      存在于目标 workflow_call 声明（透传拼错在 480 分钟构建后才炸，左移到本地）。

退出码: 0 全部通过; 1 存在失败项（逐项打印, 不吞错误）。
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO / ".github" / "workflows"
TODO_FILE = REPO / "docs" / "todo.md"
DEFAULT_WORKFLOWS = [
    "firmware-build-unified.yml",
    "compile-firmware.yml",
    "compile-packages.yml",
    "custom-feed.yml",
    "upstream-sync.yml",
    "geodata-updater.yml",
    "workflow-lint.yml",
]

# 旧 lock 逐包指纹机制的标识符: 该机制已于 2026-09-26 重构为 tree SHA 真值锁,
# 这些 token 重新出现意味着回退或半截子改造。
RESIDUAL_TOKENS = {
    "firmware-build-unified.yml": [
        "LAST_PKG_MAP", "PKG_COMMITS_JSON", "packages.lock.json 无",
        # 2026-10-02 dispatch 输入裁剪: cache_strategy 5 值收敛为 clean_cache 布尔,
        # no-cache (不持久化) 模式移除。sdk-config 曾被误判为死选项删除,
        # 2026-10-03 恢复并真正接线 (手动强制 SDK+IB), 故不在残留名单。
        "cache_strategy", "CACHE_STRATEGY", "clean-toolchain", "clean-ccache",
        "clean-all", "no-cache",
    ],
    "compile-firmware.yml": [
        "PACKAGE_COMMITS_JSON", "PKG_LOCK_FILE",
        "cache_strategy", "CACHE_STRATEGY", "clean-toolchain", "clean-ccache",
        "clean-all", "no-cache",
    ],
    "compile-packages.yml": [
        "PACKAGE_COMMITS", "package_commits",
        "cache_strategy", "CACHE_STRATEGY", "clean-toolchain", "clean-ccache",
        "clean-all", "no-cache",
    ],
}


def find_bash() -> str:
    """定位 bash: Windows 优先 Git Bash, 其余环境取 PATH。"""
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    if git_bash.exists():
        return str(git_bash)
    found = shutil.which("bash")
    if not found:
        raise RuntimeError("bash 不可用 (Windows 需安装 Git for Windows)")
    return found


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def ok(self, msg: str) -> None:
        print(f"  OK  {msg}")

    def fail(self, msg: str, detail: str = "") -> None:
        self.failures += 1
        print(f"  FAIL {msg}")
        if detail:
            print(indent(detail, "       "))


def indent(text: str, pad: str) -> str:
    return "\n".join(pad + line for line in text.splitlines())


def check_yaml(files: list[Path], rep: Report) -> None:
    print("== 1. YAML 解析 ==")
    for f in files:
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
            if not isinstance(doc, dict):
                raise ValueError(f"顶层不是 mapping: {type(doc).__name__}")
            rep.ok(f.name)
        except Exception as e:
            rep.fail(f"{f.name}: {e}")


def iter_run_blocks(doc: dict):
    """产出 (job, step, run, shell); 只含 bash 块 (Linux runner 默认 shell)。"""
    for jname, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            run = step.get("run")
            if not run:
                continue
            shell = step.get("shell", "bash")
            if shell not in ("bash", "sh"):
                continue
            yield jname, step.get("name") or "<unnamed>", run, shell


def check_bash_n(files: list[Path], bash: str, rep: Report) -> None:
    print("== 2. bash -n (全部 bash run: 块) ==")
    total = 0
    for f in files:
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception:
            rep.fail(f"{f.name}: YAML 解析失败, 跳过 bash -n")
            continue
        for jname, sname, run, shell in iter_run_blocks(doc):
            total += 1
            # GitHub 表达式替换为占位值, 避免多行/嵌套表达式破坏 bash 语法
            sanitized = re.sub(r"\$\{\{[^}]*\}\}", "GHEXPR", run)
            with tempfile.NamedTemporaryFile(
                "w", suffix=".sh", delete=False, encoding="utf-8", newline="\n"
            ) as tf:
                tf.write(sanitized)
                tmp = tf.name
            try:
                r = subprocess.run(
                    [bash, "-n", tmp.replace("\\", "/")],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
            finally:
                Path(tmp).unlink()
            if r.returncode != 0:
                rep.fail(f"{f.name} / {jname} / {sname}", r.stderr.strip())
            else:
                rep.ok(f"{f.name} / {jname} / {sname}")
    print(f"  (共 {total} 个 bash run: 块)")


# GitHub Actions 单 step `run:` 块长度上限约 21000 字符 (含其中 ${{ }} 表达式,
# 服务端按展开前文本校验)。超限时 push/dispatch 被拒: HTTP 422
# "Exceeded max expression length 21000", 报错行列指向 `run: |` 行而非真实语法错误,
# 本地 PyYAML/bash -n 无法覆盖 —— 故在此左移告警 (留 1000 字符余量给表达式膨胀)。
RUN_BLOCK_LIMIT = 21000
RUN_BLOCK_WARN = 20000


def check_run_block_size(files: list[Path], rep: Report) -> None:
    print("== 2b. 单 step run: 块长度 (GitHub 21000 上限) ==")
    oversize = 0
    for f in files:
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception:
            rep.fail(f"{f.name}: YAML 解析失败, 跳过 run 块长度检查")
            continue
        worst = (0, "", "")
        for jname, sname, run, _shell in iter_run_blocks(doc):
            n = len(run)
            if n > worst[0]:
                worst = (n, jname, sname)
            if n > RUN_BLOCK_WARN:
                oversize += 1
                rep.fail(
                    f"{f.name} / {jname} / {sname}: {n} 字符 > 告警线 {RUN_BLOCK_WARN}"
                    + (" (已超 GitHub 21000 上限, push/dispatch 将 422)"
                       if n > RUN_BLOCK_LIMIT else "")
                    + " —— 拆分方案见 docs/openwrt-build-pitfalls.md "
                      "「单 step run: 块超 21000 字符触发 workflow 解析 422」",
                )
        if worst[0] <= RUN_BLOCK_WARN:
            rep.ok(f"{f.name} 最大 run 块 {worst[0]} 字符 ({worst[1]} / {worst[2]})")
    if oversize == 0:
        print(f"  (全部 run 块 ≤ {RUN_BLOCK_WARN} 字符)")


def check_env_self_reference(files: list[Path], rep: Report) -> None:
    """2c. 同一 run: 块内自引用 GITHUB_ENV 变量检测。

    `echo "X=..." >> "$GITHUB_ENV"` 写入的变量要到**本步骤结束后**才对后续
    步骤可见; 同一步骤内的 `${{ env.X }}` 恒为空字符串 (C16 教训: 批量替换
    inputs.version → env.RESOLVED_VERSION 时误伤解析入口赋值行, 显式
    version 被静默丢弃, 外部 caller 传参无效)。
    """
    print("== 2c. 同步骤 GITHUB_ENV 自引用 ==")
    # 写入模式: echo "X=..." >> "$GITHUB_ENV" (容忍引号/空格变体)
    env_write = re.compile(
        r"""echo\s+["']?([A-Za-z_][A-Za-z0-9_]*)=.*?>>\s*["']?\$GITHUB_ENV["']?"""
    )
    found_any = False
    for f in files:
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception:
            continue  # YAML 失败已由检查 1 报告
        for jname, sname, run, _shell in iter_run_blocks(doc):
            defined = set(env_write.findall(run))
            if not defined:
                continue
            # 块内引用了本块定义的 env 变量 → 自引用 bug
            self_refs = sorted(
                v for v in defined if re.search(r"\$\{\{\s*env\." + re.escape(v) + r"\s*\}\}", run)
            )
            if self_refs:
                found_any = True
                rep.fail(
                    f"{f.name} / {jname} / {sname}: 步骤内自引用 GITHUB_ENV 变量 "
                    f"{self_refs} —— 该变量本步骤结束前不存在, 表达式恒为空; "
                    f"入口赋值应读 inputs.* (C16 教训)"
                )
    if not found_any:
        rep.ok("无自引用 (所有 env.* 引用均在定义步骤之后)")


def check_residual(files: list[Path], rep: Report) -> None:
    print("== 3. 旧 lock 指纹残留标识符 ==")
    for f in files:
        tokens = RESIDUAL_TOKENS.get(f.name, [])
        if not tokens:
            continue
        text = f.read_text(encoding="utf-8")
        hits = [t for t in tokens if t in text]
        if hits:
            rep.fail(f"{f.name} 仍含旧机制标识符: {hits}")
        else:
            rep.ok(f"{f.name} 无残留 ({len(tokens)} 项已检查)")


def check_static_rules(files: list[Path], rep: Report) -> None:
    """静态防退化规则: 每条对应一个真实 run 事故, 纯文本/grep 级检查。
    行为语义验证已于 2026-10-19 移除 (fixture 自证 = 运动员兼裁判, 见文件头定位声明)。"""
    print("== 4. 静态防退化规则 ==")

    # 4h. JSONL 落盘必须单行 (run 36226606223: jq 对多行 filter 字面量保留
    # pretty-print 多行输出 → 每 target 22 行碎片 → 下游 while read 读出非法 JSON)。
    # 检查 workflow 中所有写入 *.jsonl 的 jq 命令都带 -c。
    import re as _re
    bad = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        for m in _re.finditer(r"jq -n(?!c)[^\n]*\\\n(?:[^\n]*\\\n)*[^\n]*>>[^\n]*\.jsonl", text):
            bad.append(f"{f.name}: jq -n 无 -c 却写入 .jsonl")
    if bad:
        rep.fail("JSONL 落盘 -c 检查", "\n".join(bad))
    else:
        rep.ok("JSONL 落盘: 所有 jq -n 写 .jsonl 处均带 -c")

    # 4l. 指纹命令防退化 (静态): ① executor 的 ls-tree -r 必须带 -t (缺 -t 则
    # tree 行恒缺 → 指纹恒空); ② gh api 的 --jq 不支持 --argjson (f3d11091
    # 重蹈已记录坑 → CURR_TREES 恒空, 旧基线全包误判删除)
    bad = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        if f.name in ("compile-firmware.yml", "compile-packages.yml"):
            for i, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue  # 注释里的说明文字不算代码
                if _re.search(r"ls-tree -r(?! -t)", line):
                    bad.append(f"{f.name}:{i}: ls-tree -r 缺 -t (tree 行恒缺)")
        if _re.search(r"--jq\s+--argjson", text):
            bad.append(f"{f.name}: gh api --jq 搭配 --argjson (gh 不支持)")
    if bad:
        rep.fail("指纹命令防退化", "\n".join(bad))
    else:
        rep.ok("指纹命令: ls-tree -r -t 齐备 / 无 gh api --jq --argjson 组合")

    # 4m 静态防退化: 两个 executor 的追平 diff 必须 tree 条目过滤且前缀含空格
    # (漏空格 → 永不匹配 → 恒跳过 → 真实包变更静默漏检, 本地测试拦截过)
    bad = []
    for f in files:
        if f.name in ("compile-firmware.yml", "compile-packages.yml"):
            if "grep -E '^[<>] 040000 tree '" not in f.read_text(encoding="utf-8"):
                bad.append(f"{f.name}: 追平闸门缺 tree 条目过滤 (或 diff 前缀漏空格)")
    if bad:
        rep.fail("追平闸门静态检查", "\n".join(bad))
    else:
        rep.ok("追平闸门静态: 两 executor 均含 tree 条目过滤")

    # 4n 静态防退化: compile-firmware 的补齐 grep 必须用容忍模式
    # (回退到 ^OPT=y$ 严格行尾 → 尾注释 seed 误报, run 38112393097)
    fw_text = next((f.read_text(encoding="utf-8") for f in files if f.name == "compile-firmware.yml"), "")
    m = _re.search(_re.escape('grep -qE "^${OPT}=y([[:space:]#]|$)" .config'), fw_text)
    strict = _re.search(_re.escape('grep -q "^${OPT}=y$" .config'), fw_text)
    if m and not strict:
        rep.ok("seed 补齐静态: 容忍模式在位 (无严格行尾回退)")
    else:
        rep.fail("seed 补齐静态: 补齐 grep 缺容忍模式或回退到严格行尾匹配 (run 38112393097 教训)")


def check_todo_ids(rep: Report) -> None:
    """5. 台账 ID 全局唯一（2026-10-19 盘点教训: C7–C10 双编号 → AGENTS.md
    "update matching row" 与进展记录"日期+ID"的引用失去锚点）。"""
    print("== 5. 台账 ID 唯一性 ==")
    if not TODO_FILE.exists():
        rep.fail("docs/todo.md 不存在")
        return
    ids = []
    for line in TODO_FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*([A-Z][A-Z0-9]*\d+)\s*\|", line)
        if m:
            ids.append(m.group(1))
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        rep.fail(f"docs/todo.md 重复 ID: {dup} —— ID 必须全局唯一, 前缀仅历史分组不表章节")
    else:
        rep.ok(f"{len(ids)} 个台账 ID 全局唯一")


def check_caller_contract(files: list[Path], rep: Report) -> None:
    """6. reusable 调用契约: 本仓 job `uses:` 本仓 workflow 时, with/secrets 的每个
    key 必须在目标 workflow_call 声明。透传拼错要到运行期才报 Invalid workflow
    call——本轮 release_type 等三处成对接线的结构性防线。"""
    print("== 6. reusable 调用契约 (with/secrets key 存在性) ==")
    # 收集本仓全部 workflow_call 声明 (YAML 1.1 陷阱: `on:` 被解析为 bool True)
    declared: dict[str, tuple[set[str], set[str]]] = {}
    for f in WORKFLOWS_DIR.glob("*.yml"):
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        on = doc.get("on") or doc.get(True)
        call = on.get("workflow_call") if isinstance(on, dict) else None
        if not isinstance(call, dict):
            continue
        ins = set((call.get("inputs") or {}).keys())
        secs = set((call.get("secrets") or {}).keys())
        declared[f.name.lower()] = (ins, secs)
    checked = 0
    for f in files:
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        for jname, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            uses = job.get("uses") or ""
            m = re.match(r"\./\.github/workflows/([^@]+)$", uses)
            if not m:
                continue
            target = declared.get(m.group(1).lower())
            if target is None:
                rep.fail(f"{f.name} / {jname}: 目标未声明 workflow_call: {uses}")
                continue
            checked += 1
            bad = [f"with.{k}" for k in (job.get("with") or {}) if k not in target[0]]
            bad += [f"secrets.{k}" for k in (job.get("secrets") or {}) if k not in target[1]]
            if bad:
                rep.fail(f"{f.name} / {jname} → {m.group(1)}: 未声明的 key {bad}")
            else:
                rep.ok(f"{f.name} / {jname} → {m.group(1)} (with/secrets 均已声明)")
    if checked == 0:
        rep.ok("(无本仓 reusable 调用)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("workflows", nargs="*", help="workflow 文件名 (默认全部 7 个活跃 workflow)")
    args = ap.parse_args()

    names = args.workflows or DEFAULT_WORKFLOWS
    files = []
    for n in names:
        f = WORKFLOWS_DIR / n if "/" not in n and "\\" not in n else REPO / n
        if not f.exists():
            print(f"FAIL 文件不存在: {f}")
            return 1
        files.append(f)

    try:
        bash = find_bash()
    except RuntimeError as e:
        print(f"FAIL {e}")
        return 1

    rep = Report()
    check_yaml(files, rep)
    check_bash_n(files, bash, rep)
    check_run_block_size(files, rep)
    check_env_self_reference(files, rep)
    check_residual(files, rep)
    check_static_rules(files, rep)
    check_todo_ids(rep)
    check_caller_contract(files, rep)

    print()
    if rep.failures:
        print(f"✗ {rep.failures} 项失败")
        return 1
    print("✓ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
