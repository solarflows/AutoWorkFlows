"""collect_packages.py 的增量与巨变语义端到端测试（离线，使用本地 git 仓库）。

运行：python .github/custom-feed/scripts/test_collect_incremental.py

覆盖四类边界：换源、上游删包、上游仓库消失、历史残留目录检出。
每轮使用独立 cache-root，与 CI 每次 run 的全新 /tmp 缓存一致。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
COLLECT = os.path.join(REPO, ".github", "custom-feed", "scripts", "collect_packages.py")
WORK = tempfile.mkdtemp(prefix="collect-test-")
FEED = os.path.join(WORK, "feed")
MANIFEST = os.path.join(WORK, "manifest.yaml")
LOCK = os.path.join(FEED, "packages.lock.json")
OVERLAY = os.path.join(WORK, "overlay_empty")

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"\n      {detail}"))


def git(cwd, *args):
    cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@e", *args]
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                         encoding="utf-8")
    assert res.returncode == 0, res.stdout + res.stderr
    return res.stdout.strip()


def posix(path):
    return path.replace("\\", "/")


def mkrepo(rel, files):
    """建立带初始提交的上游仓库，返回本地 URL"""
    path = os.path.join(WORK, rel)
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path)
    git(path, "init", "-q", "-b", "main")
    write_files(path, files)
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    return posix(path)


def commit_change(repo_url, add=None, remove=None):
    path = repo_url if os.path.isabs(repo_url) else os.path.join(WORK, repo_url)
    if remove:
        for r in remove:
            target = os.path.join(path, r)
            if os.path.isdir(target):
                shutil.rmtree(target)
            elif os.path.exists(target):
                os.remove(target)
    if add:
        write_files(path, add)
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "change")


def write_files(root, files):
    for rel, content in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)


def write_manifest(entries):
    write_files(WORK, {"manifest.yaml": yaml.safe_dump({"packages": entries}, sort_keys=False,
                                                       allow_unicode=True)})


def run_collect(extra=None):
    cache = os.path.join(WORK, "cache_%d" % len(results))
    cmd = [sys.executable, COLLECT, "--manifest", MANIFEST, "--target", "t1",
           "--output-dir", FEED, "--cache-root", cache, "--threads", "2",
           "--lockfile", LOCK, "--overlay-dir", OVERLAY]
    cmd += extra or []
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    return res.returncode, (res.stdout or "") + (res.stderr or "")


def lock_records():
    with open(LOCK, encoding="utf-8") as f:
        return json.load(f)["targets"]["t1"]


def feed_dir():
    return {d for d in os.listdir(FEED) if os.path.isdir(os.path.join(FEED, d))}


os.makedirs(FEED, exist_ok=True)
os.makedirs(OVERLAY, exist_ok=True)

ALPHA = mkrepo("up_alpha", {"Makefile": "A\n", "ONLY_ALPHA": "1\n"})
BETA = mkrepo("up_beta", {"Makefile": "B\n"})
# bundle 仓库顶层直接是包目录（与线上 openwrt-passwall-packages 的结构一致）
BUNDLE = mkrepo("up_bundle", {"child1/Makefile": "c1\n", "child2/Makefile": "c2\n"})
write_manifest([
    {"name": "pkg-a", "repo": ALPHA, "targets": ["t1"]},
    {"name": "bundle_pkg", "repo": BUNDLE, "hook": "mvdir bundle_pkg", "targets": ["t1"]},
])

# 轮次 1：全新工作树
rc, out = run_collect()
check("R1 首轮成功并建立来源账本", rc == 0, out)
check("R1 记录 dirs 账本",
      lock_records().get("pkg-a", {}).get("dirs") == ["pkg-a"]
      and lock_records().get("bundle_pkg", {}).get("dirs") == ["child1", "child2"],
      json.dumps(lock_records(), ensure_ascii=False))
check("R1 账本闭合（无残留）", "来源账本闭合" in out, out[-600:])

# 轮次 2：上游无变化，含 mvdir 条目在内全部增量跳过
rc, out = run_collect()
check("R2 上游未变时全部跳过", rc == 0 and "所有上游仓库均为最新" in out, out)
check("R2 mvdir 条目不再每轮重拉（D 项）",
      out.count("[增量跳过]") == 2, out)

# 轮次 3：换源 alpha -> beta，必须替换而非合并
write_manifest([
    {"name": "pkg-a", "repo": BETA, "targets": ["t1"]},
    {"name": "bundle_pkg", "repo": BUNDLE, "hook": "mvdir bundle_pkg", "targets": ["t1"]},
])
rc, out = run_collect()
mk_path = os.path.join(FEED, "pkg-a", "Makefile")
mk = open(mk_path, encoding="utf-8").read().strip() if os.path.exists(mk_path) else "<缺失>"
check("R3 换源被识别", "🔁 [换源]" in out, out)
check("R3 换源后取到新内容", rc == 0 and mk == "B", f"mk={mk}\n{out}")
check("R3 旧源独有文件不残留",
      not os.path.exists(os.path.join(FEED, "pkg-a", "ONLY_ALPHA")), str(feed_dir()))

# 轮次 4：上游 bundle 删掉 child2 -> 陈旧目录剪枝
commit_change(BUNDLE, remove=["child2"])
rc, out = run_collect()
check("R4 上游删包触发剪枝", "🧹 [剪枝]" in out and "child2" in out, out)
check("R4 child2 已从工作树移除", not os.path.exists(os.path.join(FEED, "child2")), str(feed_dir()))
check("R4 child1 仍在", os.path.isdir(os.path.join(FEED, "child1")))
check("R4 账本同步收窄", lock_records()["bundle_pkg"]["dirs"] == ["child1"],
      json.dumps(lock_records()["bundle_pkg"], ensure_ascii=False))

# 轮次 5：上游仓库消失 -> 必须硬失败且不落盘 lock
before = open(LOCK, encoding="utf-8").read()
write_manifest([
    {"name": "pkg-a", "repo": BETA, "targets": ["t1"]},
    {"name": "bundle_pkg", "repo": BUNDLE, "hook": "mvdir bundle_pkg", "targets": ["t1"]},
    {"name": "gone", "repo": os.path.join(WORK, "up_missing"), "targets": ["t1"]},
])
rc, out = run_collect()
check("R5 收集不完整时硬失败", rc != 0, out[-400:])
check("R5 失败原因点名条目", "收集不完整" in out and "gone" in out, out)
check("R5 不落盘 lock（避免记成已同步）", open(LOCK, encoding="utf-8").read() == before)

# 轮次 6：移除坏条目，检出人工塞入的历史残留（只报告）
write_manifest([
    {"name": "pkg-a", "repo": BETA, "targets": ["t1"]},
    {"name": "bundle_pkg", "repo": BUNDLE, "hook": "mvdir bundle_pkg", "targets": ["t1"]},
])
write_files(FEED, {"zombie-pkg/Makefile": "old\n"})
rc, out = run_collect()
check("R6 残留目录被检出并告警", "::warning::" in out and "zombie-pkg" in out, out)
check("R6 默认不删除残留", os.path.isdir(os.path.join(FEED, "zombie-pkg")) and rc == 0)

# 轮次 7：显式开启剪枝才删除
rc, out = run_collect(["--prune-untracked"])
check("R7 显式剪枝删除残留", "zombie-pkg" in out and not os.path.exists(os.path.join(FEED, "zombie-pkg")), out[-400:])
check("R7 剪枝后账本闭合", "来源账本闭合" in out and rc == 0, out[-400:])

shutil.rmtree(WORK, ignore_errors=True)
print("\n---- 汇总 ----")
bad = [r for r in results if not r[1]]
print(f"{len(results) - len(bad)}/{len(results)} 通过")
sys.exit(1 if bad else 0)
