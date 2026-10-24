"""`collect_packages.py` 的离线回归测试（不触网、不依赖 CI）。

运行：python .github/custom-feed/scripts/test_mvdir.py
覆盖：mvdir 黑名单 / 跨条目同名保护 / --overwrite 逃生口 / hook 严格解析，
     以及 2026-10-22 mt798x smartdns 被 passwall 附带目录劫持的端到端重放
     （见 docs/openwrt-build-pitfalls.md § custom-feed mvdir 静默同名覆盖）。
需要 GNU patch（Linux/runner 自带，Windows 走 msys）。
"""
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCRIPTS_DIR = os.path.join(REPO, ".github", "custom-feed", "scripts")
sys.path.insert(0, SCRIPTS_DIR)
import collect_packages as cp  # noqa: E402
import yaml  # noqa: E402

WORK = tempfile.mkdtemp(prefix="mvdir-test-")
PATCH = shutil.which("patch") or r"C:\msys64\usr\bin\patch.exe"
P7 = os.path.join(REPO, ".github", "custom-feed", "patches", "mt798x", "0007-fix-smartdns.patch")
# 0009 已退役（2026-10-24 移入 patches-remove，仅作事故重放 fixture）：
# 上游 pymumu/openwrt-smartdns 原生 48.4（commit 21c940ed 锚定），补丁双向失效
P9 = os.path.join(REPO, ".github", "custom-feed", "patches-remove", "mt798x", "0009-smartdns-bump-48.4.patch")

UPSTREAM = """#
# Copyright (c) 2018-2026 Nick Peng (pymumu@gmail.com)
# This is free software, licensed under the GNU General Public License v3.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=smartdns
PKG_VERSION:=1.2026.48.2
PKG_RELEASE:=1

PKG_SOURCE_PROTO:=git
PKG_SOURCE_URL:=https://www.github.com/pymumu/smartdns.git
PKG_MIRROR_HASH:=d8ca4173e7268fc83bd15a05ee4c152bc55a3dfdbe23f9070c97a89a70e3aea4
PKG_SOURCE_VERSION:=2b2b31f1e5acf6cbb975f17c600ccc6bffd03cdf

SMARTDNS_WEBUI_VERSION:=1.0.0
SMARTDNS_WEBUI_SOURCE_PROTO:=git
""" + "\n".join(f"PAD_{i}:={i}" for i in range(38)) + """

define Package/smartdns/conffiles
/etc/config/smartdns
/etc/smartdns/address.conf
/etc/smartdns/blacklist-ip.conf
/etc/smartdns/custom.conf
endef
"""

# passwall 自带 smartdns 的 Makefile 形态：版本块换成 tarball 源，
# conffiles 区块与上游一致（真实 48.4 即如此），因此 0007 能应用、0009 双向皆失败
GIT_SOURCE_BLOCK = """PKG_VERSION:=1.2026.48.2
PKG_RELEASE:=1

PKG_SOURCE_PROTO:=git
PKG_SOURCE_URL:=https://www.github.com/pymumu/smartdns.git
PKG_MIRROR_HASH:=d8ca4173e7268fc83bd15a05ee4c152bc55a3dfdbe23f9070c97a89a70e3aea4
PKG_SOURCE_VERSION:=2b2b31f1e5acf6cbb975f17c600ccc6bffd03cdf
"""

PASSWALL_SOURCE_BLOCK = """PKG_VERSION:=48.4
PKG_RELEASE:=1

PKG_SOURCE_VERSION:=21c940edc65520849ba03544c5cf8d9cf326e680
PKG_SOURCE:=$(PKG_NAME)-$(PKG_SOURCE_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/pymumu/smartdns/tar.gz
PKG_SOURCE_URL_FILE:=$(PKG_SOURCE_VERSION)
"""

PASSWALL = UPSTREAM.replace(GIT_SOURCE_BLOCK, PASSWALL_SOURCE_BLOCK)
if PASSWALL == UPSTREAM:
    raise SystemExit("❌ fixture 版本块替换失败：UPSTREAM 内容与预期不符")

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  [{detail}]"))


def fresh():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)


def bundle(rel_path, text):
    """mvdir 的 dirname 必须位于 dest_root 内：写到 <dest_root>/bundle/..."""
    write(os.path.join(WORK, "root", "bundle", rel_path), text)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def run_mvdir(**kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        stats = cp.mvdir(**kw)
    return stats, buf.getvalue()


check("parse: 纯目录名",
      cp.parse_mvdir_hook("mvdir openwrt-passwall-packages") == ("openwrt-passwall-packages", [], []))
d, bl, ow = cp.parse_mvdir_hook("mvdir x --blacklist mt798x/smartdns --overwrite a,b")
check("parse: 黑名单与覆盖取值", d == "x" and bl == ["mt798x/smartdns"] and ow == ["a", "b"])
try:
    cp.parse_mvdir_hook("mvdir x --blacklist a --skipme b")
    check("parse: 未知参数抛错", False)
except ValueError as e:
    check("parse: 未知参数抛错", "未知参数" in str(e))
try:
    cp.parse_mvdir_hook("mvdir x --blacklist")
    check("parse: 缺值抛错", False)
except ValueError:
    check("parse: 缺值抛错", True)
check("spec: 全局项", cp.build_target_specs(["smartdns"], "mt798x") == {"smartdns"})
check("spec: 限定项命中", cp.build_target_specs(["mt798x/smartdns"], "mt798x") == {"smartdns"})
check("spec: 限定项不命中", cp.build_target_specs(["mt798x/smartdns"], "qualcommax") == set())

if not os.path.exists(PATCH):
    print(f"❌ 未找到 GNU patch ({PATCH})，无法重放补丁探测")
    sys.exit(2)

OWNERS = {"smartdns": {"smartdns"}, "shared-lib": set(), "self-own": {"bundle"}}

fresh()
write(os.path.join(WORK, "root", "smartdns", "Makefile"), "OURS\n")
bundle(os.path.join("smartdns", "Makefile"), "PASSWALL\n")
bundle(os.path.join("xray-core", "Makefile"), "X\n")
st, out = run_mvdir(dest_root=os.path.join(WORK, "root"), dirname="bundle", target="mt798x",
                    blacklist=["smartdns"], owners=OWNERS, self_name="bundle")
check("mvdir: 黑名单保留现有目录", read(os.path.join(WORK, "root", "smartdns", "Makefile")) == "OURS\n")
check("mvdir: 黑名单计数", st["blacklisted"] == 1 and st["moved"] == 1, str(st))
check("mvdir: 黑名单可见提示", "[黑名单]" in out, out)
check("mvdir: 源目录已清理", not os.path.exists(os.path.join(WORK, "root", "bundle")))

fresh()
write(os.path.join(WORK, "root", "smartdns", "Makefile"), "OURS\n")
bundle(os.path.join("smartdns", "Makefile"), "PASSWALL\n")
st, out = run_mvdir(dest_root=os.path.join(WORK, "root"), dirname="bundle", target="mt798x",
                    owners=OWNERS, self_name="bundle")
check("mvdir: 跨条目默认保护", read(os.path.join(WORK, "root", "smartdns", "Makefile")) == "OURS\n")
check("mvdir: 保护出 ::warning::", "::warning::" in out and st["protected"] == 1, out)
check("mvdir: 保护给出逃生口", "--overwrite smartdns" in out, out)

fresh()
write(os.path.join(WORK, "root", "smartdns", "Makefile"), "OURS\n")
bundle(os.path.join("smartdns", "Makefile"), "PASSWALL\n")
st, out = run_mvdir(dest_root=os.path.join(WORK, "root"), dirname="bundle", target="mt798x",
                    overwrite=["mt798x/smartdns"], owners=OWNERS, self_name="bundle")
check("mvdir: --overwrite 强制覆盖", read(os.path.join(WORK, "root", "smartdns", "Makefile")) == "PASSWALL\n")
check("mvdir: 强制覆盖有标注", "强制覆盖" in out, out)

fresh()
write(os.path.join(WORK, "root", "shared-lib", "Makefile"), "OLD\n")
bundle(os.path.join("shared-lib", "Makefile"), "NEW\n")
st, out = run_mvdir(dest_root=os.path.join(WORK, "root"), dirname="bundle", target="mt798x",
                    owners=OWNERS, self_name="bundle")
check("mvdir: 无归属同名照常覆盖", read(os.path.join(WORK, "root", "shared-lib", "Makefile")) == "NEW\n")
check("mvdir: 覆盖不再静默", "♻️" in out, out)

fresh()
write(os.path.join(WORK, "root", "self-own", "Makefile"), "V1\n")
bundle(os.path.join("self-own", "Makefile"), "V2\n")
st, out = run_mvdir(dest_root=os.path.join(WORK, "root"), dirname="bundle", target="mt798x",
                    owners=OWNERS, self_name="bundle")
check("mvdir: 自有条目刷新可覆盖", read(os.path.join(WORK, "root", "self-own", "Makefile")) == "V2\n")

fresh()
bundle(os.path.join("only", "f"), "1\n")
st, out = run_mvdir(dest_root=os.path.join(WORK, "root"), dirname="bundle", target="mt798x",
                    blacklist=["ghost"], owners={}, self_name="bundle")
check("mvdir: 黑名单项缺失提示可撤销", "未出现在源目录" in out, out)
check("mvdir: 源目录不存在仅告警",
      run_mvdir(dest_root=os.path.join(WORK, "root"), dirname="nope", target="mt798x")[1]
      .startswith("::warning::"))

fresh()
bundle(os.path.join("bundle", "inner", "Makefile"), "x\n")
try:
    run_mvdir(dest_root=os.path.join(WORK, "root"), dirname="bundle", target="mt798x",
              owners={}, self_name="bundle")
    check("mvdir: 顶层与克隆目录同名时拒绝自我覆盖", False, "未抛错")
except RuntimeError as exc:
    check("mvdir: 顶层与克隆目录同名时拒绝自我覆盖", "自我覆盖" in str(exc), str(exc))

data = yaml.safe_load(open(os.path.join(REPO, ".github", "custom-feed", "packages.yaml"), encoding="utf-8"))
by_name = {p.get("name"): p for p in data["packages"]}
pw_hook = str(by_name["openwrt-passwall-packages"]["hook"])
check("manifest: 真实 hook 可解析", pw_hook.startswith("mvdir openwrt-passwall-packages --blacklist"))
check("manifest: pymumu smartdns 登记归属", "smartdns" in cp.entry_root_names(by_name["smartdns"]),
      str(cp.entry_root_names(by_name["smartdns"])))
check("manifest: mvdir 条目不登记 dirname",
      "openwrt-passwall-packages" not in cp.entry_root_names(by_name["openwrt-passwall-packages"]))


def probe(tree):
    out = {}
    for tag, pfile in (("0007", P7), ("0009", P9)):
        fwd = subprocess.run([PATCH, "-d", tree, "-p1", "-E", "--forward", "--batch",
                              "--no-backup-if-mismatch", "-i", pfile],
                             capture_output=True, text=True, encoding="utf-8")
        if fwd.returncode == 0:
            out[tag] = "APPLIED"
            continue
        rev = subprocess.run([PATCH, "-R", "-d", tree, "-p1", "-E", "--batch",
                              "--no-backup-if-mismatch", "--dry-run", "-i", pfile],
                             capture_output=True, text=True, encoding="utf-8")
        out[tag] = "SKIPPED" if rev.returncode == 0 else "CONFLICT"
    return out


def make_branch_tree(root):
    write(os.path.join(root, "smartdns", "Makefile"), UPSTREAM)
    for p in (P7, P9):
        subprocess.run([PATCH, "-d", root, "-p1", "-E", "--forward", "--batch",
                        "--no-backup-if-mismatch", "-i", p],
                       capture_output=True, text=True, encoding="utf-8", check=True)
    return read(os.path.join(root, "smartdns", "Makefile"))


fresh()
make_branch_tree(os.path.join(WORK, "old", "root"))
write(os.path.join(WORK, "old", "root", "bundle", "smartdns", "Makefile"), PASSWALL)
run_mvdir(dest_root=os.path.join(WORK, "old", "root"), dirname="bundle", target="mt798x",
          owners={}, self_name="bundle")
# 先取内容再探测：probe 的正向应用会改写文件
hijacked = read(os.path.join(WORK, "old", "root", "smartdns", "Makefile"))
old_probe = probe(os.path.join(WORK, "old", "root"))
check("事故重放(旧行为): smartdns 被劫持", hijacked == PASSWALL)
check("事故重放(旧行为): 0009 冲突", old_probe["0009"] == "CONFLICT", str(old_probe))

fresh()
ours = make_branch_tree(os.path.join(WORK, "new", "root"))
write(os.path.join(WORK, "new", "root", "bundle", "smartdns", "Makefile"), PASSWALL)
write(os.path.join(WORK, "new", "root", "bundle", "xray-core", "Makefile"), "X\n")
st, out = run_mvdir(dest_root=os.path.join(WORK, "new", "root"), dirname="bundle", target="mt798x",
                    blacklist=cp.parse_mvdir_hook(pw_hook)[1],
                    owners={"smartdns": {"smartdns"}}, self_name="openwrt-passwall-packages")
check("事故重放(新行为): 保住我们的 smartdns",
      read(os.path.join(WORK, "new", "root", "smartdns", "Makefile")) == ours)
check("事故重放(新行为): 补丁走增量跳过",
      probe(os.path.join(WORK, "new", "root")) == {"0007": "SKIPPED", "0009": "SKIPPED"})
check("事故重放(新行为): 其他包照常搬运", os.path.isdir(os.path.join(WORK, "new", "root", "xray-core")))

fresh()
write(os.path.join(WORK, "q", "bundle", "smartdns", "Makefile"), PASSWALL)
st, out = run_mvdir(dest_root=os.path.join(WORK, "q"), dirname="bundle", target="qualcommax",
                    blacklist=cp.parse_mvdir_hook(pw_hook)[1], owners={},
                    self_name="openwrt-passwall-packages")
check("qualcommax: 自带 smartdns 照常搬入", read(os.path.join(WORK, "q", "smartdns", "Makefile")) == PASSWALL
      and st["blacklisted"] == 0)

# ---------- 5. 直接执行 workflow 中真实的「应用补丁」脚本 ----------
BASH = next((p for p in (r"C:\msys64\usr\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe")
             if os.path.exists(p)), None) or shutil.which("bash")
STEP_BODY = None


def to_posix(path):
    p = path.replace("\\", "/")
    if len(p) > 2 and p[1] == ":":
        p = "/" + p[0].lower() + p[2:]
    return p


def feed_patch_step_body():
    """从 custom-feed.yml 原样取出「应用补丁」步骤的 run 脚本（测真代码，不抄副本）"""
    global STEP_BODY
    if STEP_BODY is not None:
        return STEP_BODY
    yml = yaml.safe_load(open(os.path.join(REPO, ".github", "workflows", "custom-feed.yml"), encoding="utf-8"))
    for job in yml["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == "应用补丁" and "run" in step:
                STEP_BODY = step["run"]
    if STEP_BODY is None:
        raise SystemExit("❌ 未在 custom-feed.yml 找到「应用补丁」步骤")
    return STEP_BODY


def run_feed_step(case_name, build_tree):
    """在临时工作区跑真实的「应用补丁」步骤；build_tree(tree_dir) 铺 fixture。返回 (rc, 合并输出)"""
    if not BASH:
        print(f"SKIP {case_name}：未找到 bash")
        return None
    ws = os.path.join(WORK, "step_" + case_name)
    tree = os.path.join(ws, "mt798x")
    pdir = os.path.join(ws, ".github", "custom-feed", "patches", "mt798x")
    os.makedirs(tree, exist_ok=True)
    os.makedirs(pdir, exist_ok=True)
    build_tree(tree)
    shutil.copy(P7, pdir)
    shutil.copy(P9, pdir)
    script = re.sub(r"\$\{\{\s*matrix\.target\s*\}\}", "mt798x", feed_patch_step_body())
    step_sh = os.path.join(ws, "step.sh")
    write(step_sh, script)
    env = dict(os.environ, GITHUB_WORKSPACE=to_posix(ws))
    # Windows 的 System32\find.exe 会抢在 msys find 之前；把 bash 自带 bin 目录置于 PATH 首位
    env["PATH"] = os.path.dirname(BASH) + os.pathsep + env.get("PATH", "")
    res = subprocess.run([BASH, "-e", to_posix(step_sh)], capture_output=True, text=True,
                         encoding="utf-8", env=env)
    return res.returncode, (res.stdout or "") + (res.stderr or "")


if BASH:
    rc, out = run_feed_step("ours", make_branch_tree)
    check("workflow 步骤: 我们的 smartdns 走增量跳过",
          rc == 0 and "增量跳过] 补丁已处于应用状态: 0009-smartdns-bump-48.4.patch" in out
          and "增量跳过] 补丁已处于应用状态: 0007-fix-smartdns.patch" in out,
          f"rc={rc}\n{out}")

    rc, out = run_feed_step("hijacked",
                            lambda t: write(os.path.join(t, "smartdns", "Makefile"), PASSWALL))
    check("workflow 步骤: 被劫持时硬失败",
          rc != 0 and "::error::补丁冲突或目标文件校验失败: 0009-smartdns-bump-48.4.patch" in out,
          f"rc={rc}\n{out}")
    check("workflow 步骤: 冲突保留 patch 原始输出（本次事故的可归因性）",
          "FAILED" in out or "hunk" in out, out[-400:])

    shifted = UPSTREAM.replace("SMARTDNS_WEBUI_SOURCE_PROTO:=git\n",
                               "SMARTDNS_WEBUI_SOURCE_PROTO:=git\n" + "\n".join(
                                   f"SHIFT_{i}" for i in range(5)) + "\n")
    rc, out = run_feed_step("offset",
                            lambda t: write(os.path.join(t, "smartdns", "Makefile"), shifted))
    check("workflow 步骤: 偏移应用暴露为 ::warning::",
          "::warning::补丁带偏移或 fuzz 应用" in out and rc == 0, f"rc={rc}\n{out[-600:]}")
else:
    print("SKIP workflow 步骤用例：未找到 bash")

# ---------- 6. 增量跳过 / 换源 / 来源账本闭合 ----------
check("lock: 同源同分支匹配",
      cp.lock_source_matches({"repo": "A", "branch": None, "commit": "x"}, "A", None))
check("lock: 换源不再被误判为无更新",
      not cp.lock_source_matches({"repo": "A", "branch": None}, "B", None))
check("lock: 换分支同样失效",
      not cp.lock_source_matches({"repo": "A", "branch": "main"}, "A", "qt6"))
check("lock: 空记录不匹配", not cp.lock_source_matches({}, "A", None))

fresh()
LED = os.path.join(WORK, "ledger")
write(os.path.join(LED, "smartdns", "Makefile"), "1\n")
write(os.path.join(LED, "xray-core", "Makefile"), "1\n")
check("lock: dirs 账本齐全判定在位",
      cp.lock_roots_present({"dirs": ["smartdns", "xray-core"]}, LED, "smartdns"))
check("lock: dirs 有缺失判定不在位",
      not cp.lock_roots_present({"dirs": ["smartdns", "gone"]}, LED, "smartdns"))
check("lock: 旧 lock 无 dirs 时按条目名退化探测", cp.lock_roots_present({}, LED, "smartdns"))
check("lock: 旧 lock 条目名也不存在则不在位", not cp.lock_roots_present({}, LED, "ghost"))

CLAIM = {"smartdns": {"smartdns"}, "koolproxy": {"bundle"}}
check("stale: 本轮不再产出即剪枝候选", cp.stale_roots(["a", "b"], {"a"}, {}, "e") == ["b"])
check("stale: 他人声明的目录绝不剪", cp.stale_roots(["smartdns"], set(), CLAIM, "bundle") == [])
check("stale: 自己声明的可剪", cp.stale_roots(["koolproxy"], set(), CLAIM, "bundle") == ["koolproxy"])
check("drift: 账本未覆盖时不判定", cp.untracked_roots(["x"], set(), False) == [])
check("drift: 隐藏目录不算残留", cp.untracked_roots([".git", ".github", "x"], set(), True) == ["x"])
check("drift: 已追踪目录不算残留", cp.untracked_roots({"smartdns", "ghost"}, {"smartdns"}, True) == ["ghost"])

check("static: 整仓条目可静态判定", cp.entry_static_roots({"name": "smartdns"}) == ["smartdns"])
check("static: paths 条目取 basename",
      cp.entry_static_roots({"name": "x", "paths": ["net/a", "luci/b"]}) == ["a", "b"])
check("static: glob 条目返回 None", cp.entry_static_roots({"name": "x", "paths": ["luci/*"]}) is None)
check("static: hook 条目返回 None", cp.entry_static_roots({"name": "x", "hook": "mvdir x"}) is None)

ov_dirs = cp.overlay_root_names(os.path.join(REPO, ".github", "custom-feed", "overlay"), "mt798x")
check("overlay 白名单覆盖 global 与 target 顶层",
      {"v2ray-geodata", "smartdns", "shadowsocks-rust"} <= ov_dirs, str(sorted(ov_dirs)))

fresh()
write(os.path.join(WORK, "root", "smartdns", "Makefile"), "OURS\n")
bundle(os.path.join("smartdns", "Makefile"), "PASSWALL\n")
bundle(os.path.join("xray-core", "Makefile"), "X\n")
st, out = run_mvdir(dest_root=os.path.join(WORK, "root"), dirname="bundle", target="mt798x",
                    blacklist=["smartdns"], owners=OWNERS, self_name="bundle")
check("mvdir: produced 只登记实际搬入项", st["produced"] == ["xray-core"], str(st))

shutil.rmtree(WORK, ignore_errors=True)

print("\n---- 汇总 ----")
bad = [r for r in results if not r[1]]
print(f"{len(results) - len(bad)}/{len(results)} 通过")
sys.exit(1 if bad else 0)
