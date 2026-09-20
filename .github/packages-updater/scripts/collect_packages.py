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


def mvdir(dest_root, dirname):
    """将 dirname 下所有直接子目录/文件移动到 dest_root，并删除 dirname"""
    src_dir = os.path.join(dest_root, dirname)
    if not os.path.isdir(src_dir):
        print(f"⚠️ mvdir 目标目录不存在: {src_dir}")
        return
    for item in os.listdir(src_dir):
        s = os.path.join(src_dir, item)
        d = os.path.join(dest_root, item)
        if os.path.exists(d):
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
            else:
                os.remove(d)
        shutil.move(s, d)
    shutil.rmtree(src_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Collect packages from manifest")
    parser.add_argument("--manifest", required=True, help="Path to packages.yaml")
    parser.add_argument("--target", required=True, help="Target branch / platform (e.g. main, mt798x)")
    parser.add_argument("--output-dir", default=".", help="Output working directory")
    parser.add_argument("--cache-root", default=os.environ.get("OPENWRT_PACKAGES_SOURCE_CACHE", "/tmp/openwrt-pkg-cache"))
    parser.add_argument("--threads", type=int, default=6, help="Parallel download threads")
    parser.add_argument("--lockfile", default=None, help="Path to write packages.lock.json")
    parser.add_argument("--force", action="store_true", help="Force refresh all packages regardless of commit lock")
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

            pkg_dest = os.path.join(dest_root, name or os.path.basename(repo.rstrip("/").rstrip(".git")))
            locked_info = existing_target_lock.get(name, {})
            locked_sha = locked_info.get("commit")
            remote_sha = remote_shas.get(repo_tuple)

            if locked_sha and remote_sha and locked_sha == remote_sha and os.path.exists(pkg_dest):
                skipped_packages.add(name)
                lock_records[name] = {
                    "repo": repo,
                    "branch": branch,
                    "commit": locked_sha
                }

        for repo_tuple in unique_repos:
            pkgs_of_repo = [p.get("name") for p in matched_packages if (p.get("repo"), p.get("branch")) == repo_tuple]
            if pkgs_of_repo and all(p in skipped_packages for p in pkgs_of_repo):
                skip_repos.add(repo_tuple)

    # 2. 提取所有唯一的上游仓库并多线程并发下载
    unique_repos = list({(p.get("repo"), p.get("branch")) for p in matched_packages if p.get("repo")})
    repo_cache_map = prefetch_repositories(unique_repos, args.cache_root, max_workers=args.threads, skip_repos=skip_repos)

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
            print(f"❌ 跳过软件包 {name}: 上游缓存缺失 ({repo})", file=sys.stderr)
            continue

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
        else:
            dst_name = name or os.path.basename(repo.rstrip("/").rstrip(".git"))
            dst = os.path.join(dest_root, dst_name)
            sync_path(cache_dir, dst)

        if hook:
            if hook.startswith("mvdir "):
                target_dir = hook.split(maxsplit=1)[1].strip()
                mvdir(dest_root, target_dir)
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
                        except Exception as e:
                            print(f"⚠️ 执行 mv 失败: {hook} ({e})")
            else:
                try:
                    subprocess.run(hook, shell=True, cwd=dest_root, check=False)
                except Exception as e:
                    print(f"⚠️ 执行 hook 失败: {hook} ({e})")

        lock_records[name] = {
            "repo": repo,
            "branch": branch,
            "commit": commit_sha
        }
        success_count += 1

    # 3. 输出 lockfile
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
