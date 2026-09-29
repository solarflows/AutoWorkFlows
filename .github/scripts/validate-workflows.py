#!/usr/bin/env python3
"""AutoWorkflows 工作流验证脚本（可复用，git 追踪）。

用法:
    python .github/scripts/validate-workflows.py                 # 全部 6 个活跃 workflow
    python .github/scripts/validate-workflows.py a.yml b.yml     # 指定文件
    python .github/scripts/validate-workflows.py --no-semantics  # 跳过指纹语义回归

检查项:
  1. PyYAML 解析每个 workflow。
  2. 对每个 bash `run:` 块执行 `bash -n`（GitHub 表达式替换为占位值）。
  2b. 单 step `run:` 块长度告警阈值（GitHub 服务端 21000 字符上限, 超限 push/dispatch
      422 而本地 YAML/bash -n 不报错——左移该约束）。
  3. 指纹管道语义回归（tree SHA 真值锁, 2026-09-26 重构）:
     - feeds.conf.default 解析（sed 双模式: 有锁/无锁分支、注释、src-link、packages 排除）
     - compare diff 包名提取（awk: 分类/包 与 包/... 两类 feed 布局, 根文件跳过）
     - git ls-tree -> {pkg: tree_sha}（jq -Rrs 管道的 Python 等价, 本机无 jq）
     - feeds map {feed: sha} 构建
     - persist-state 合并语义（feed_trees/feeds_sha 写入, 旧 .packages 清除）
     - heredoc 插值展开后为合法 JSON
     - 旧 lock 指纹机制残留标识符检查（防回归）

退出码: 0 全部通过; 1 存在失败项（逐项打印, 不吞错误）。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO / ".github" / "workflows"
DEFAULT_WORKFLOWS = [
    "firmware-build-unified.yml",
    "compile-firmware.yml",
    "compile-packages.yml",
    "custom-feed.yml",
    "upstream-sync.yml",
    "geodata-updater.yml",
]

# 旧 lock 逐包指纹机制的标识符: 该机制已于 2026-09-26 重构为 tree SHA 真值锁,
# 这些 token 重新出现意味着回退或半截子改造。
RESIDUAL_TOKENS = {
    "firmware-build-unified.yml": ["LAST_PKG_MAP", "PKG_COMMITS_JSON", "packages.lock.json 无"],
    "compile-firmware.yml": ["PACKAGE_COMMITS_JSON", "PKG_LOCK_FILE"],
    "compile-packages.yml": ["PACKAGE_COMMITS", "package_commits"],
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


def run_bash(bash: str, script: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    """执行 bash 片段, 显式 UTF-8 解码 (error-visibility: 不吞 stderr)。"""
    return subprocess.run(
        [bash, "-c", script],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


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


def check_semantics(bash: str, files: list[Path], rep: Report) -> None:
    """指纹管道语义回归: 与 workflow 内实际管道逐段等价验证。"""
    print("== 4. 指纹管道语义回归 ==")

    # 4a. feeds.conf.default 解析 (plan 侧 sed 双模式)
    conf = (
        "src-git packages https://github.com/solarflows/packages.git;hanwckf\n"
        "src-git luci https://github.com/immortalwrt/luci.git\n"
        "src-git routing https://github.com/openwrt/routing.git;openwrt-21.02\n"
        "#src-git targets https://github.com/openwrt/targets.git\n"
        "src-link custom /usr/src/openwrt/custom-feed\n"
    )
    sed_script = (
        r"""sed -nE -e 's|^src-git[[:space:]]+([^[:space:]]+)[[:space:]]+([^[:space:]]+);([^[:space:]]+)$|\1 \2 \3|p' """
        r"""-e 's|^src-git[[:space:]]+([^[:space:]]+)[[:space:]]+([^[:space:];]+)$|\1 \2|p' """
        """| awk '$1 != \"packages\"'"""
    )
    r = run_bash(bash, sed_script, stdin=conf)
    if r.returncode != 0:
        rep.fail("feeds.conf sed 解析", r.stderr.strip())
    else:
        got = [l.split() for l in r.stdout.strip().split("\n") if l]
        want = [
            ["luci", "https://github.com/immortalwrt/luci.git"],
            ["routing", "https://github.com/openwrt/routing.git", "openwrt-21.02"],
        ]
        if got == want:
            rep.ok("feeds.conf 解析: 有锁/无锁分支、注释、src-link、packages 排除")
        else:
            rep.fail(f"feeds.conf 解析: got {got}")

    # 4b. compare diff 包名提取 (plan 侧 awk NF 规则)
    cases = {
        "net/tailscale/Makefile": "tailscale",        # 2 级分类布局 (openwrt/packages)
        "modules/luci-base/Makefile": "luci-base",   # luci 布局
        "batman-adv/Makefile": "batman-adv",         # 1 级布局 (routing/telephony)
        "README.md": "",                             # 根文件 -> 空 (调用方 continue)
    }
    bad = []
    for path, want in cases.items():
        r = run_bash(
            bash,
            "echo '" + path + "' | awk -F/ 'NF >= 3 {print $2; next} NF == 2 {print $1}'",
        )
        if r.returncode != 0 or r.stdout.strip() != want:
            bad.append(f"{path} -> {r.stdout.strip()!r} (want {want!r})")
    if bad:
        rep.fail("包名提取 awk 规则", "\n".join(bad))
    else:
        rep.ok("包名提取: 两类 feed 布局 + 根文件跳过")

    # 4c. ls-tree -> {pkg: tree_sha} (executor 侧 INPUT_TREES jq -Rrs 管道, Python 等价)
    # 深度 ≤2 与 plan 侧 fetch_pkg_trees 同规则 (键集不对齐 → 每轮幽灵子目录键
    # 误判新增); 输入为 ls-tree -r -t 形态 (含深度 3 子目录与 blob 行)
    ls_tree_out = (
        "040000 tree aaaa111111111111111111111111111111111111\tnet\n"
        "040000 tree bbbb222222222222222222222222222222222222\tnet/curl\n"
        "100644 blob cccc333333333333333333333333333333333333\tnet/curl/Makefile\n"
        "040000 tree dddd444444444444444444444444444444444444\tnet/curl/src\n"
        "100644 blob eeee555555555555555555555555555555555555\tpackages.lock.json\n"
    )

    def jq_lstree(raw: str) -> dict:
        lines = [l for l in raw.split("\n") if l]                    # select(length>0)
        pairs = [l.split("\t") for l in lines]                       # split("\t")
        out: dict[str, str] = {}
        for p in pairs:
            if len(p) != 2 or not p[0].startswith("040000 tree "):   # select(test)
                continue
            parts = p[1].split("/")
            if len(parts) > 2:                                       # select(depth <= 2)
                continue
            out[parts[-1]] = p[0].split(" ")[2][0:7]                 # last + sha[0:7]
        return out

    got = jq_lstree(ls_tree_out)
    want = {"net": "aaaa111", "curl": "bbbb222"}
    if got == want:
        rep.ok("ls-tree 树表: -t tree 行 + 深度≤2 + SHA 提取 (blob/深目录排除)")
    else:
        rep.fail(f"ls-tree 树表: got {got}")

    # 4d. feeds map {feed: sha} (executor 侧 jq -Rrs 管道, Python 等价)
    def jq_feedsmap(raw: str) -> dict:
        lines = [l for l in raw.split("\n") if l]
        out: dict[str, str] = {}
        for l in lines:
            parts = l.split(" ")
            out[parts[0]] = parts[1]
        return out or {}

    got = jq_feedsmap("packages " + "1" * 40 + "\nluci " + "2" * 40 + "\n")
    if got == {"packages": "1" * 40, "luci": "2" * 40}:
        rep.ok("feeds map: {feed: sha} 构建")
    else:
        rep.fail(f"feeds map: got {got}")

    # 4e. persist-state 合并语义 (input_trees/std/upstream/deferred 写入, 旧 .packages/feed_trees 清除)
    state_pkg = {"source_sha": "s1", "packages": {"old": "aaa"}, "feed_trees": {"old": "t1"}, "last_build": "old"}
    info = {
        "input_trees": {"tailscale": "bbbb222"},
        "std_input_trees": {"curl": "cccc333"},
        "upstream_input_trees": {"luci": {"luci-base": "dddd444"}},
        "feeds_sha": {"luci": "2" * 40},
        "deferred_pkgs": ["v2ray-geodata"],
    }
    merged = dict(state_pkg)
    merged.update({**info, "last_build": "new", "last_mode": "firmware"})
    merged.pop("packages", None)   # jq: del(.packages)
    merged.pop("feed_trees", None)  # jq: del(.feed_trees)
    if "packages" in merged or "feed_trees" in merged:
        rep.fail("persist 合并: 旧字段未被清除")
    elif (merged["input_trees"]["tailscale"] != "bbbb222"
          or merged["deferred_pkgs"] != ["v2ray-geodata"]
          or merged["std_input_trees"]["curl"] != "cccc333"
          or merged["upstream_input_trees"]["luci"]["luci-base"] != "dddd444"):
        rep.fail("persist 合并: 新指纹字段未正确写入")
    else:
        rep.ok("persist 合并: input_trees/std/upstream/deferred 写入 + 旧字段清除")

    # 4f. heredoc 插值合法性 (build-info.json 内 ${...} 展开后)
    doc = json.loads(
        '{"input_trees": ' + json.dumps(info["input_trees"])
        + ', "feeds_sha": ' + json.dumps(info["feeds_sha"])
        + ', "deferred_pkgs": ' + json.dumps(info["deferred_pkgs"]) + "}"
    )
    if doc["input_trees"]["tailscale"] == "bbbb222" and doc["feeds_sha"]["luci"] == "2" * 40:
        rep.ok("heredoc 插值: 展开后为合法 JSON")
    else:
        rep.fail("heredoc 插值: 展开后 JSON 异常")

    # 4i. 短哈希截断语义 (plan 侧 .sha[0:$short] 与 executor 侧 [0:$short] 同规则)
    SHORT = 7
    full = "bbbb222222222222222222222222222222222222"
    if full[0:SHORT] == "bbbb222" and len(full[0:SHORT]) == SHORT:
        rep.ok(f"短哈希: {SHORT} 位截断两侧同规则")
    else:
        rep.fail("短哈希: 截断语义错误")

    # 4j. deferred 分流语义: outside-sdk 变更不再升级全量, 而是搁置累计
    # (run 36363278098: v2ray-geodata 触发 3 目标全量 → 现在应只记 deferred)
    sdk_config = {"sing-box", "luci-app-passwall"}
    changed = {"sing-box", "v2ray-geodata", "tailscale"}
    if (changed & sdk_config == {"sing-box"}
            and changed - sdk_config == {"v2ray-geodata", "tailscale"}):
        rep.ok("deferred 分流: ∩ sdk.config 增量 / outside-sdk 搁置")
    else:
        rep.fail("deferred 分流: 语义错误")

    # 4g. 基线闸门 (plan 侧 jq -e '.feeds_sha | type == "object"' 的语义)
    # 无基线 → 闸门触发 (强制全量建基线); 有基线 → 放行正常检测。
    def gate_triggers(state_pkg: dict) -> bool:
        return not isinstance(state_pkg.get("feeds_sha"), dict)

    if gate_triggers({"source_sha": "s1"}) and not gate_triggers({"feeds_sha": {"luci": "2" * 40}}):
        rep.ok("基线闸门: 无 feeds_sha 触发全量 / 有基线放行 (防 skip 死锁)")
    else:
        rep.fail("基线闸门: 语义错误")

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

    # 4k. FTREES 深度管道语义 (executor 侧 ls-tree -r -t 输出, Python 等价)
    # run 36519189440: ls-tree -r 无 -t 只出 blob 行 → tree 过滤恒空;
    # 旧 jq map(. + {depth:...}) 数组加 object 亦是语法错误 (被空输入掩盖)。
    ftrees_raw = (
        "040000 tree aaaa111111111111111111111111111111111111\tnet\n"
        "040000 tree bbbb222222222222222222222222222222222222\tnet/curl\n"
        "100644 blob cccc333333333333333333333333333333333333\tnet/curl/Makefile\n"
        "040000 tree dddd444444444444444444444444444444444444\tnet/curl/src\n"
        "040000 tree eeee555555555555555555555555555555555555\tlibs\n"
        "040000 tree ffff666666666666666666666666666666666666\tlibs/libxml2\n"
        "100644 blob gggg777777777777777777777777777777777777\tlibs/libxml2/Makefile\n"
        "100644 blob hhhh888888888888888888888888888888888888\tpackages.lock.json\n"
    )

    def jq_ftrees(raw: str, seed: list[str]) -> dict:
        lines = [l for l in raw.split("\n") if l]                     # select(length>0)
        pairs = [l.split("\t") for l in lines]                        # split("\t")
        trees = [p for p in pairs
                 if len(p) == 2 and p[0].startswith("040000 tree ")]  # select(test)
        out: dict[str, str] = {}
        for p in trees:
            parts = p[1].split("/")
            if len(parts) > 2:                                        # select(depth <= 2)
                continue
            key = parts[-1]                                           # last
            if key in seed:                                           # with_entries(seed 过滤)
                out[key] = p[0].split(" ")[2][0:SHORT]                # [0:$short]
        return out

    got = jq_ftrees(ftrees_raw, ["curl", "libxml2"])
    want = {"curl": "bbbb222", "libxml2": "ffff666"}
    if got == want:
        rep.ok("FTREES 深度管道: -t tree 行 + 深度≤2 + seed 过滤 + 7 位截断")
    else:
        rep.fail(f"FTREES 深度管道: got {got}")

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

    # 4m. 追平闸门语义 (executor 侧 BEFORE/AFTER 顶层 tree 表 diff, Python 等价)
    # run 36557139597: custom-feed README 时间戳每次必提交 → SHA 闸门必开 → 每次
    # 构建后空转一轮 make (diff 仅 README+lock, 313 个 stamp 检查 0 真实编译)。
    # 闸门 = 顶层 tree 条目 (包目录) 变化非空才重编; blob 根文件不算; 双向计入
    # (< 删除 / > 新增或变更)。diff 行前缀是 "< "/" > " (含空格)。
    catchup_before = (
        "040000 tree aaaa111111111111111111111111111111111111\tsing-box\n"
        "040000 tree bbbb222222222222222222222222222222222222\tmosdns\n"
        "100644 blob cccc333333333333333333333333333333333333\tREADME.md\n"
        "100644 blob dddd444444444444444444444444444444444444\tpackages.lock.json\n"
    )

    def gate_changed(before: str, after: str) -> set[str]:
        def entries(raw: str) -> dict[str, str]:
            out: dict[str, str] = {}
            for l in raw.split("\n"):
                if not l.startswith("040000 tree "):
                    continue
                sha, path = l.split("\t", 1)
                out[path] = sha
            return out
        b, a = entries(before), entries(after)
        return {p for p in set(b) | set(a) if b.get(p) != a.get(p)}

    g_meta = gate_changed(catchup_before, catchup_before.replace("cccc333", "dddd444"))
    g_pkg = gate_changed(catchup_before, catchup_before.replace("aaaa111", "ffff555"))
    g_del = gate_changed(catchup_before, catchup_before.replace(
        "040000 tree bbbb222222222222222222222222222222222222\tmosdns\n", ""))
    if g_meta == set() and g_pkg == {"sing-box"} and g_del == {"mosdns"}:
        rep.ok("追平闸门: 元数据跳过 / 包变更触发 / 删除检出")
    else:
        rep.fail(f"追平闸门: got meta={g_meta} pkg={g_pkg} del={g_del}")

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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("workflows", nargs="*", help="workflow 文件名 (默认全部 6 个活跃 workflow)")
    ap.add_argument("--no-semantics", action="store_true", help="跳过指纹语义回归段")
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
    check_residual(files, rep)
    if not args.no_semantics:
        check_semantics(bash, files, rep)

    print()
    if rep.failures:
        print(f"✗ {rep.failures} 项失败")
        return 1
    print("✓ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
