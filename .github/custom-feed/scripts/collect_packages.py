#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_packages.py
根据 packages.yaml 清单和目标 target，自动并发克隆并提取指定软件包到当前目录。
支持：
1. ThreadPoolExecutor 多线程并发拉取上游仓库
2. 网络重试与指数退避（抗弱网抖动）
3. 记录 / 导出 packages.lock.json（SHA-lock）
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import yaml


def fetch_repo_with_retry(repo_url, branch, cache_root, max_retries=3):
    """
    带指数退避重试拉取上游仓库到缓存目录，并返回 (cache_dir, commit_sha)。
    """
    os.makedirs(cache_root, exist_ok=True)
    key_src = f"{repo_url}\0{branch or ''}"
    cache_key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
    cache_dir = os.path.join(cache_root, cache_key)

    # 验证已有缓存是否有效
    if os.path.exists(cache_dir):
        if os.path.isdir(os.path.join(cache_dir, ".git")):
            try:
                commit_sha = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=cache_dir, stderr=subprocess.DEVNULL
                ).decode("utf-8").strip()
                return cache_dir, commit_sha
            except Exception:
                shutil.rmtree(cache_dir, ignore_errors=True)
        else:
            shutil.rmtree(cache_dir, ignore_errors=True)

    staging_dir = os.path.join(cache_root, f".clone_{cache_key[:8]}_{os.getpid()}_{int(time.time()*1000)%100000}")
    
    for attempt in range(1, max_retries + 1):
        shutil.rmtree(staging_dir, ignore_errors=True)
        os.makedirs(staging_dir, exist_ok=True)

        clone_cmd = ["git", "clone", "--depth", "1", "--single-branch", "--quiet"]
        if branch:
            clone_cmd.extend(["--branch", str(branch)])
        clone_cmd.extend([repo_url, os.path.join(staging_dir, "repo")])

        print(f"🔄 正在拉取上游 [{attempt}/{max_retries}]: {repo_url} (branch: {branch or 'default'})")
        res = subprocess.run(clone_cmd, capture_output=True, text=True)
        if res.returncode == 0:
            target_repo = os.path.join(staging_dir, "repo")
            try:
                commit_sha = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=target_repo, stderr=subprocess.DEVNULL
                ).decode("utf-8").strip()
            except Exception:
                commit_sha = "unknown"

            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir, ignore_errors=True)
            shutil.move(target_repo, cache_dir)
            shutil.rmtree(staging_dir, ignore_errors=True)
            return cache_dir, commit_sha
        else:
            err_msg = res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "unknown error"
            print(f"⚠️ 拉取失败 (尝试 {attempt}/{max_retries}): {repo_url} -> {err_msg}", file=sys.stderr)
            if attempt < max_retries:
                backoff = 2 ** attempt
                time.sleep(backoff)

    shutil.rmtree(staging_dir, ignore_errors=True)
    print(f"❌ 达到最大重试次数，放弃拉取: {repo_url}", file=sys.stderr)
    return None, None


def get_remote_head_sha(repo_url, branch=None):
    """通过 git ls-remote 获取远程分支最新 commit SHA"""
    cmd = ["git", "ls-remote"]
    if branch:
        cmd.extend([repo_url, f"refs/heads/{branch}"])
    else:
        cmd.extend([repo_url, "HEAD"])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().split()[0]
    except Exception:
        pass
    return None


def prefetch_repositories(unique_repos, cache_root, max_workers=6, skip_repos=None):
    """
    多线程并发预拉取所有上游仓库（可跳过已确认无更新的仓库）
    """
    skip_repos = skip_repos or set()
    repos_to_fetch = [r for r in unique_repos if r not in skip_repos]

    if skip_repos:
        print(f"⚡ 增量模式：{len(skip_repos)} 个仓库无上游更新已跳过，需拉取 {len(repos_to_fetch)} 个仓库")

    if not repos_to_fetch:
        print("✅ 所有上游仓库均为最新，无需额外拉取！")
        return {}

    print(f"🚀 开始并发拉取 {len(repos_to_fetch)} 个上游仓库 (线程数: {max_workers})...")
    repo_cache_map = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_repo = {
            executor.submit(fetch_repo_with_retry, repo, branch, cache_root): (repo, branch)
            for repo, branch in repos_to_fetch
        }
        for future in as_completed(future_to_repo):
            repo, branch = future_to_repo[future]
            try:
                cache_dir, commit_sha = future.result()
                repo_cache_map[(repo, branch)] = (cache_dir, commit_sha)
            except Exception as e:
                print(f"❌ 并发拉取异常: {repo} ({e})", file=sys.stderr)
                repo_cache_map[(repo, branch)] = (None, None)

    return repo_cache_map


def sync_path(src, dst):
    if not os.path.exists(src) and not os.path.islink(src):
        return False
    if shutil.which("rsync"):
        if os.path.isdir(src) and not os.path.islink(src):
            os.makedirs(dst, exist_ok=True)
            cmd = [
                "rsync", "-a", "--links",
                "--exclude=.git*", "--exclude=.svn*", "--exclude=.github*",
                f"{src}/", f"{dst}/"
            ]
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            cmd = ["rsync", "-a", "--links", src, dst]
        res = subprocess.run(cmd)
        return res.returncode == 0
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(src) and not os.path.islink(src):
            shutil.copytree(
                src, dst,
                symlinks=True,
                ignore_dangling_symlinks=True,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".git*", ".svn*", ".github*")
            )
        else:
            if os.path.islink(src):
                linkto = os.readlink(src)
                if os.path.lexists(dst):
                    os.remove(dst)
                os.symlink(linkto, dst)
            else:
                shutil.copy2(src, dst)
        return True


MVDIR_USAGE = (
    "用法: hook: mvdir <目录> [--blacklist <spec>[,<spec>...]] "
    "[--overwrite <spec>[,<spec>...]]；spec 为 <名称> 或 <target>/<名称>"
)


def parse_mvdir_hook(hook):
    """解析 mvdir hook，返回 (dirname, blacklist_specs, overwrite_specs)。

    未知参数或缺值直接抛错：静默忽略一个拼错的选项，等于保护机制看起来加了
    其实没生效，正是本次事故最难发现的那一类失效。
    """
    parts = hook.split()
    if len(parts) < 2:
        raise ValueError(f"mvdir hook 缺少目录名。{MVDIR_USAGE}")
    dirname = parts[1]
    specs = {"--blacklist": [], "--overwrite": []}
    idx = 2
    while idx < len(parts):
        flag = parts[idx]
        if flag not in specs:
            raise ValueError(f"mvdir hook 未知参数: {flag}。{MVDIR_USAGE}")
        if idx + 1 >= len(parts):
            raise ValueError(f"mvdir hook 参数 {flag} 缺少取值。{MVDIR_USAGE}")
        specs[flag].extend(s.strip() for s in parts[idx + 1].split(",") if s.strip())
        idx += 2
    return dirname, specs["--blacklist"], specs["--overwrite"]


def build_target_specs(specs, target):
    """把 <名称> / <target>/<名称> 形式的声明展开为仅对当前 target 生效的名称集合"""
    names = set()
    for spec in specs:
        if "/" in spec:
            scope, name = spec.split("/", 1)
            if scope == target and name:
                names.add(name)
        elif spec:
            names.add(spec)
    return names


def entry_root_names(pkg):
    """该条目最终落在工作树根下的目录名集合（与主循环命名规则一致）。

    mvdir 条目的 dirname 本身搬运后即删除，故其归属由子目录决定，这里不登记。
    """
    repo = pkg.get("repo") or ""
    base = os.path.basename(repo.rstrip("/").rstrip(".git"))
    name = pkg.get("name") or base
    paths = pkg.get("paths")
    names = {os.path.basename(p.strip("/")) for p in paths} if paths else {name}
    names.add(name)
    hook = str(pkg.get("hook") or "")
    if hook.startswith("mvdir "):
        names.discard(parse_mvdir_hook(hook)[0])
    return {n for n in names if n}


def entry_static_roots(pkg):
    """清单静态可知的根目录名集合。

    含 glob 路径或 hook 的条目其产物集合必须运行时才知道，返回 None，
    调用方据此不做替换清空与陈旧剪枝（宁可不剪，也不误删他人内容）。
    """
    if pkg.get("hook"):
        return None
    paths = pkg.get("paths")
    if paths:
        if any(ch in p for p in paths for ch in "*?["):
            return None
        return sorted({os.path.basename(p.strip("/")) for p in paths})
    name = pkg.get("name") or os.path.basename((pkg.get("repo") or "").rstrip("/").rstrip(".git"))
    return [name] if name else None


def overlay_root_names(overlay_dir, target):
    """overlay 层会写入的顶层目录（apply-overlay 按需 mkdir），作为未追踪判定的白名单"""
    names = set()
    for scope in ("global", target):
        root = os.path.join(overlay_dir, scope)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
                names.add(rel.split("/")[0])
    return names


def lock_source_matches(locked, repo, branch):
    """lock 记录的来源是否就是清单当前声明的来源。

    只比 commit 会把「换源到同一 commit 的 fork」误判为无更新（fork 镜像极常见），
    增量跳过必须同时要求 repo 与 branch 一致。
    """
    if not locked:
        return False
    return locked.get("repo") == repo and locked.get("branch") == branch


def lock_roots_present(locked, dest_root, fallback_name):
    """上轮该条目产出的根目录是否仍在位。

    有 dirs 账本时逐个校验；没有（旧 lock）时退化为按条目名探测，与历史行为一致。
    """
    roots = (locked or {}).get("dirs")
    if roots:
        return all(os.path.exists(os.path.join(dest_root, r)) for r in roots)
    return os.path.exists(os.path.join(dest_root, fallback_name))


def owned_elsewhere(owners, name, self_name):
    """该根目录是否由清单中其他条目声明（这类目录绝不删除、也不覆盖）"""
    claimants = owners.get(name) or set()
    return bool(claimants) and self_name not in claimants


def stale_roots(old_dirs, produced, owners, self_name):
    """上轮产出、本轮不再产出的目录 = 上游删包/改名或清单 paths 收窄后的残留候选"""
    return sorted(
        d for d in (old_dirs or [])
        if d not in produced and not owned_elsewhere(owners, d, self_name)
    )


def untracked_roots(actual_dirs, tracked, known):
    """工作树里存在、但本轮来源账本覆盖不到的顶层目录（历史残留候选）

    known=False 时由调用方决定不判定，避免 lock 尚无 dirs 账本的第一轮误报刷屏。
    """
    if not known:
        return []
    return sorted(
        d for d in actual_dirs
        if d not in tracked and not d.startswith(".") and d != ".git"
    )


def mvdir(dest_root, dirname, target=None, blacklist=(), overwrite=(), owners=None, self_name=None):
    """将 dirname 下所有直接子目录/文件移动到 dest_root，并删除 dirname。

    同名处理（旧实现是不加提示地 rmtree 覆盖，曾让 passwall 自带的 smartdns
    覆盖 packages.yaml 声明、靠 0007/0009 补丁维护的 smartdns，导致 mt798x
    feed 连续失败；详见 docs/openwrt-build-pitfalls.md）：
      - 命中黑名单：跳过搬运，保留现有目录（源副本随 dirname 一起丢弃）；
      - 该名称由清单中其他条目声明：默认保护，跳过并出 ::warning::；
      - 命中 --overwrite 或无归属声明：照常覆盖，但逐项显式打印，不再静默。
    """
    stats = {"moved": 0, "overwritten": 0, "blacklisted": 0, "protected": 0, "produced": []}
    src_dir = os.path.join(dest_root, dirname)
    if not os.path.isdir(src_dir):
        print(f"::warning::mvdir 源目录不存在，未搬运任何内容: {src_dir}")
        return stats

    blacklist_names = build_target_specs(blacklist, target)
    overwrite_names = build_target_specs(overwrite, target)
    owners = owners or {}
    seen = set()

    for item in sorted(os.listdir(src_dir)):
        s = os.path.join(src_dir, item)
        d = os.path.join(dest_root, item)

        # 绝不把子项搬向暂存目录自身：当仓库顶层目录与克隆目录同名（条目 name ==
        # 子项名）时，旧实现会先 rmtree 掉暂存目录本身再复制，等于当场丢包。
        if os.path.abspath(d) == os.path.abspath(src_dir):
            raise RuntimeError(
                f"mvdir 冲突：仓库子目录 '{item}' 与克隆目录同名，会把暂存目录自我覆盖；"
                f"请让条目 name 与 hook 中的目录名不同（当前均为 {dirname}）"
            )
        seen.add(item)

        if item in blacklist_names:
            print(f"🚫 [黑名单] mvdir 保留现有内容，跳过: {item}（{dirname}/{item} 未采用）")
            stats["blacklisted"] += 1
            continue

        if os.path.lexists(d):
            claimants = owners.get(item) or set()
            if claimants and self_name not in claimants and item not in overwrite_names:
                print(
                    "::warning::mvdir 同名目录由清单其他条目声明，已跳过覆盖: "
                    f"{item}（声明条目: {', '.join(sorted(claimants))}；搬运方: {self_name or dirname}）"
                )
                print(f"   如确需改用 {dirname}/{item}，在 hook 追加 --overwrite {item}")
                stats["protected"] += 1
                continue
            kind = "目录" if (os.path.isdir(d) and not os.path.islink(d)) else "文件"
            tag = "♻️ [强制覆盖]" if item in overwrite_names else "♻️"
            print(f"{tag} mvdir 覆盖同名{kind}: {item}")
            if os.path.islink(d):
                os.remove(d)
            elif os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
            else:
                os.remove(d)
            stats["overwritten"] += 1

        shutil.move(s, d)
        stats["moved"] += 1
        stats["produced"].append(item)

    for name in sorted(blacklist_names - seen):
        print(f"ℹ️ mvdir 黑名单项未出现在源目录（上游可能已移除，可考虑撤销该声明）: {name}")

    shutil.rmtree(src_dir, ignore_errors=True)
    print(
        f"📦 mvdir {dirname}: 搬运 {stats['moved']} 项（覆盖 {stats['overwritten']}），"
        f"黑名单跳过 {stats['blacklisted']}，跨条目保护 {stats['protected']}"
    )
    return stats


def main():
    parser = argparse.ArgumentParser(description="Collect packages from manifest")
    parser.add_argument("--manifest", required=True, help="Path to packages.yaml")
    parser.add_argument("--target", required=True, help="Target branch / platform (e.g. main, mt798x)")
    parser.add_argument("--output-dir", default=".", help="Output working directory")
    parser.add_argument("--cache-root", default=os.environ.get("OPENWRT_PACKAGES_SOURCE_CACHE", "/tmp/openwrt-pkg-cache"))
    parser.add_argument("--threads", type=int, default=6, help="Parallel download threads")
    parser.add_argument("--lockfile", default=None, help="Path to write packages.lock.json")
    parser.add_argument("--force", action="store_true", help="Force refresh all packages regardless of commit lock")
    parser.add_argument("--prune-untracked", action="store_true",
                        help="删除工作树中来源账本覆盖不到的顶层目录（默认只报告 ::warning::）")
    parser.add_argument("--overlay-dir", default=None,
                        help="overlay 根目录（默认取 manifest 同级的 overlay/），用于未追踪目录判定的白名单")
    args = parser.parse_args()

    if not os.path.exists(args.manifest):
        print(f"❌ 清单文件不存在: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    with open(args.manifest, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    packages = data.get("packages", [])
    matched_packages = [p for p in packages if args.target in p.get("targets", [])]

    print(f"📦 目标 [{args.target}] 共匹配到 {len(matched_packages)} 个软件包，开始准备拉取...")

    dest_root = os.path.abspath(args.output_dir)
    success_count = 0
    lock_records = {}
    collect_failures = []

    # 读取已有 lockfile（用于增量模式比对）
    existing_target_lock = {}
    if not args.force and args.lockfile:
        lock_path = os.path.abspath(args.lockfile)
        if os.path.exists(lock_path):
            try:
                with open(lock_path, "r", encoding="utf-8") as lf:
                    lock_data = json.load(lf)
                    existing_target_lock = lock_data.get("targets", {}).get(args.target, {})
            except Exception:
                existing_target_lock = {}

    # 1. 检查哪些仓库在增量模式下可以跳过
    skip_repos = set()
    skipped_packages = set()

    if existing_target_lock and not args.force:
        unique_repos = list({(p.get("repo"), p.get("branch")) for p in matched_packages if p.get("repo")})
        print(f"🔍 增量检测中：正在并行检查 {len(unique_repos)} 个上游仓库的最新提交...")
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            future_to_repo = {
                executor.submit(get_remote_head_sha, repo, branch): (repo, branch)
                for repo, branch in unique_repos
            }
            remote_shas = {}
            for future in as_completed(future_to_repo):
                repo_tuple = future_to_repo[future]
                remote_shas[repo_tuple] = future.result()

        for pkg in matched_packages:
            name = pkg.get("name")
            repo = pkg.get("repo")
            branch = pkg.get("branch")
            repo_tuple = (repo, branch)

            fallback_root = name or os.path.basename(repo.rstrip("/").rstrip(".git"))
            locked_info = existing_target_lock.get(name, {})
            locked_sha = locked_info.get("commit")
            remote_sha = remote_shas.get(repo_tuple)

            # 增量跳过必须来源(repo/branch)与 commit 同时一致，且上轮产出的根目录仍在位
            if (locked_sha and remote_sha and locked_sha == remote_sha
                    and lock_source_matches(locked_info, repo, branch)
                    and lock_roots_present(locked_info, dest_root, fallback_root)):
                skipped_packages.add(name)
                lock_records[name] = {
                    "repo": repo,
                    "branch": branch,
                    "commit": locked_sha
                }
                if locked_info.get("dirs"):
                    lock_records[name]["dirs"] = sorted(locked_info["dirs"])

        for repo_tuple in unique_repos:
            pkgs_of_repo = [p.get("name") for p in matched_packages if (p.get("repo"), p.get("branch")) == repo_tuple]
            if pkgs_of_repo and all(p in skipped_packages for p in pkgs_of_repo):
                skip_repos.add(repo_tuple)

    # 2. 提取所有唯一的上游仓库并多线程并发下载
    unique_repos = list({(p.get("repo"), p.get("branch")) for p in matched_packages if p.get("repo")})
    repo_cache_map = prefetch_repositories(unique_repos, args.cache_root, max_workers=args.threads, skip_repos=skip_repos)

    # 2.5 先校验全部 mvdir hook 书写，再建立根目录归属表：
    #     mvdir 搬运时据归属表判定同名目录是否属于清单中其他条目声明的来源
    #     （清单声明的来源优先于仓库附带目录）
    for pkg in matched_packages:
        pkg_hook = str(pkg.get("hook") or "")
        if pkg_hook.startswith("mvdir "):
            try:
                parse_mvdir_hook(pkg_hook)
            except ValueError as exc:
                print(f"❌ 清单 hook 书写错误（条目 {pkg.get('name')}）: {exc}", file=sys.stderr)
                sys.exit(1)

    dir_owners = {}
    for pkg in matched_packages:
        for root_name in entry_root_names(pkg):
            dir_owners.setdefault(root_name, set()).add(pkg.get("name") or root_name)

    # 3. 依序提取文件与执行 hook
    for pkg in matched_packages:
        name = pkg.get("name")
        if name in skipped_packages:
            print(f"⚡ [增量跳过] {name}: 上游无新提交 ({lock_records[name]['commit'][:7]})")
            success_count += 1
            continue

        repo = pkg.get("repo")
        branch = pkg.get("branch")
        paths = pkg.get("paths")
        hook = pkg.get("hook")

        cache_dir, commit_sha = repo_cache_map.get((repo, branch), (None, None))
        if not cache_dir:
            print(f"❌ 软件包未取得上游内容: {name} ({repo})", file=sys.stderr)
            collect_failures.append(name)
            continue

        locked_info = existing_target_lock.get(name, {})
        old_dirs = locked_info.get("dirs") or []
        resourced = bool(old_dirs) and not lock_source_matches(locked_info, repo, branch)
        static_roots = entry_static_roots(pkg)

        # 替换写入：重拉时先清空该条目自己的旧根目录，避免"新 Makefile + 旧
        # patches/src"的混合树（换源、以及上游删文件都会踩到）。他人声明的目录
        # 绝不动；glob/hook 条目产物集合静态不可知，不做此步。
        if static_roots is not None:
            cleared = []
            for root in static_roots:
                rpath = os.path.join(dest_root, root)
                if not os.path.lexists(rpath) or owned_elsewhere(dir_owners, root, name):
                    continue
                if os.path.islink(rpath) or not os.path.isdir(rpath):
                    os.remove(rpath)
                else:
                    shutil.rmtree(rpath, ignore_errors=True)
                cleared.append(root)
            if cleared:
                tag = "🔁 [换源]" if resourced else "♻️ [替换]"
                print(f"{tag} {name}: 先清空旧内容 {len(cleared)} 项 ({', '.join(cleared)})")

        produced = []
        if paths:
            for p in paths:
                pattern = os.path.join(cache_dir, p.strip("/"))
                matched = glob.glob(pattern)
                if not matched and os.path.exists(pattern):
                    matched = [pattern]
                for src in matched:
                    dst_name = os.path.basename(src.rstrip("/"))
                    dst = os.path.join(dest_root, dst_name)
                    sync_path(src, dst)
                    produced.append(dst_name)
        else:
            dst_name = name or os.path.basename(repo.rstrip("/").rstrip(".git"))
            dst = os.path.join(dest_root, dst_name)
            sync_path(cache_dir, dst)
            produced.append(dst_name)

        if hook:
            if hook.startswith("mvdir "):
                mvdir_target, mvdir_blacklist, mvdir_overwrite = parse_mvdir_hook(hook)
                try:
                    moved = mvdir(
                        dest_root,
                        mvdir_target,
                        target=args.target,
                        blacklist=mvdir_blacklist,
                        overwrite=mvdir_overwrite,
                        owners=dir_owners,
                        self_name=name,
                    )
                except RuntimeError as exc:
                    print(f"❌ 条目 {name}: {exc}", file=sys.stderr)
                    sys.exit(1)
                produced.extend(moved["produced"])
            elif hook.startswith("mv "):
                parts = hook.split()
                if len(parts) >= 3:
                    s_rel = parts[1]
                    d_rel = parts[2]
                    src_full = os.path.join(dest_root, s_rel)
                    dst_full = dest_root if d_rel in [".", "./"] else os.path.join(dest_root, d_rel)
                    if os.path.exists(src_full):
                        target_name = os.path.basename(s_rel) if d_rel in [".", "./"] else ""
                        final_dest = os.path.join(dst_full, target_name) if target_name else dst_full
                        if os.path.exists(final_dest):
                            if os.path.isdir(final_dest):
                                shutil.rmtree(final_dest, ignore_errors=True)
                            else:
                                os.remove(final_dest)
                        try:
                            shutil.move(src_full, dst_full)
                            produced.append(os.path.basename(final_dest.rstrip("/")))
                        except Exception as e:
                            print(f"⚠️ 执行 mv 失败: {hook} ({e})")
            else:
                try:
                    subprocess.run(hook, shell=True, cwd=dest_root, check=False)
                except Exception as e:
                    print(f"⚠️ 执行 hook 失败: {hook} ({e})")

        # 陈旧根目录剪枝：上轮由本条目产出、本轮不再产出的目录（上游删包/改名、
        # paths 收窄）。shell 自定义 hook 的产物未知，故不剪枝，交由未追踪目录报告。
        if hook and not (hook.startswith("mvdir ") or hook.startswith("mv ")):
            prune_plan = []
        else:
            prune_plan = stale_roots(old_dirs, set(produced), dir_owners, name)
        for root in prune_plan:
            rpath = os.path.join(dest_root, root)
            if os.path.lexists(rpath):
                if os.path.isdir(rpath) and not os.path.islink(rpath):
                    shutil.rmtree(rpath, ignore_errors=True)
                else:
                    os.remove(rpath)
                print(f"🧹 [剪枝] {name}: 移除本轮不再产出的目录 {root}")

        # 只登记"条目执行完毕后确实存在"的根目录：mvdir 的暂存目录会被删除、
        # mv 的源目录可能已被搬空，把它们写进账本会让下轮的在位判定永远失败。
        produced = [r for r in dict.fromkeys(produced) if os.path.lexists(os.path.join(dest_root, r))]

        record = {
            "repo": repo,
            "branch": branch,
            "commit": commit_sha
        }
        if produced:
            record["dirs"] = sorted(set(produced))
        lock_records[name] = record
        success_count += 1

    # 4. 目录来源账本闭合性检查：工作树顶层目录必须能追溯到清单条目或 overlay。
    #    默认只报告不删除（加 --prune-untracked 才动手）；lock 尚无 dirs 账本时不判定，
    #    避免首轮把上百个合法目录误报成残留。
    overlay_dir = args.overlay_dir or os.path.join(
        os.path.dirname(os.path.abspath(args.manifest)), "overlay")
    tracked_dirs = set(overlay_root_names(overlay_dir, args.target))
    for rec in lock_records.values():
        tracked_dirs |= set(rec.get("dirs") or [])
    uncovered = [p.get("name") for p in matched_packages
                 if not (lock_records.get(p.get("name")) or {}).get("dirs")]
    if uncovered:
        print(f"ℹ️ 来源账本未覆盖 {len(uncovered)}/{len(matched_packages)} 个条目，"
              f"本轮不做未追踪目录判定（下轮起自动生效）: {', '.join(sorted(uncovered)[:5])}"
              + (" …" if len(uncovered) > 5 else ""))
    else:
        actual_dirs = {d for d in os.listdir(dest_root)
                       if os.path.isdir(os.path.join(dest_root, d))
                       or os.path.islink(os.path.join(dest_root, d))}
        ghosts = untracked_roots(actual_dirs, tracked_dirs, True)
        removed = 0
        if ghosts and args.prune_untracked:
            for ghost in ghosts:
                gpath = os.path.join(dest_root, ghost)
                if os.path.isdir(gpath) and not os.path.islink(gpath):
                    shutil.rmtree(gpath, ignore_errors=True)
                else:
                    os.remove(gpath)
                removed += 1
            print(f"🧹 [剪枝] 移除未追踪目录 {removed} 个: {', '.join(ghosts)}")
        elif ghosts:
            print(f"::warning::custom-feed[{args.target}] 未追踪目录（清单与 overlay 均不产出，疑似历史残留，"
                  f"本轮未删除；确认后可加 --prune-untracked）: {', '.join(ghosts)}")
        if not ghosts or removed == len(ghosts):
            print(f"✅ 来源账本闭合：工作树顶层 {len(actual_dirs) - removed} 个目录全部可追溯到清单条目或 overlay")

    # 5. 收集不完整必须硬失败：否则上游改名/删除时 feed 静默少包而 CI 全绿
    if collect_failures:
        print(f"❌ 目标 [{args.target}] 收集不完整: {len(collect_failures)}/{len(matched_packages)} "
              f"个软件包未取得上游内容", file=sys.stderr)
        for failed_name in collect_failures:
            print(f"   - {failed_name}", file=sys.stderr)
        print("   不落盘 SHA-lock，避免把不完整状态记为已同步；"
              "上游改名或删除需修清单，临时抖动可重跑或 force_refresh", file=sys.stderr)
        sys.exit(1)

    # 6. 输出 lockfile（放在硬失败之后，避免把不完整状态记为已同步）
    if args.lockfile:
        lock_path = os.path.abspath(args.lockfile)
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        existing_lock = {}
        if os.path.exists(lock_path):
            try:
                with open(lock_path, "r", encoding="utf-8") as lf:
                    existing_lock = json.load(lf)
            except Exception:
                pass
        existing_lock.setdefault("targets", {})[args.target] = lock_records
        with open(lock_path, "w", encoding="utf-8") as lf:
            json.dump(existing_lock, lf, indent=2, ensure_ascii=False)
        print(f"🔒 SHA-lock 已保存至: {lock_path}")

    print(f"✅ 目标 [{args.target}] 软件包收集完成: 成功 {success_count}/{len(matched_packages)}")


if __name__ == "__main__":
    main()
