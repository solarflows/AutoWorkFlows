#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_packages.py
根据 packages.yaml 清单和目标 target，自动克隆并提取指定软件包到当前目录。
"""

import argparse
import glob
import hashlib
import os
import shutil
import subprocess
import sys
import yaml


def ensure_source_cache(cache_root, repo_url, branch=None):
    os.makedirs(cache_root, exist_ok=True)
    key_src = f"{repo_url}\0{branch or ''}"
    cache_key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
    cache_dir = os.path.join(cache_root, cache_key)

    if os.path.exists(cache_dir) and not os.path.isdir(os.path.join(cache_dir, ".git")):
        shutil.rmtree(cache_dir, ignore_errors=True)

    if not os.path.exists(os.path.join(cache_dir, ".git")):
        staging_dir = os.path.join(cache_root, f".clone_{cache_key[:8]}")
        shutil.rmtree(staging_dir, ignore_errors=True)
        os.makedirs(staging_dir, exist_ok=True)

        clone_cmd = ["git", "clone", "--depth", "1", "--single-branch", "--quiet"]
        if branch:
            clone_cmd.extend(["--branch", str(branch)])
        clone_cmd.extend([repo_url, os.path.join(staging_dir, "repo")])

        print(f"🔄 正在拉取上游缓存: {repo_url} (branch: {branch or 'default'})")
        res = subprocess.run(clone_cmd)
        if res.returncode != 0:
            shutil.rmtree(staging_dir, ignore_errors=True)
            print(f"❌ 拉取失败: {repo_url}", file=sys.stderr)
            return None

        shutil.move(os.path.join(staging_dir, "repo"), cache_dir)
        shutil.rmtree(staging_dir, ignore_errors=True)

    return cache_dir


def sync_path(src, dst):
    if not os.path.exists(src):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git*", ".svn*", ".github*"))
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
    args = parser.parse_args()

    if not os.path.exists(args.manifest):
        print(f"❌ 清单文件不存在: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    with open(args.manifest, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    packages = data.get("packages", [])
    matched_packages = [p for p in packages if args.target in p.get("targets", [])]

    print(f"📦 目标 [{args.target}] 共匹配到 {len(matched_packages)} 个软件包，开始收集...")

    dest_root = os.path.abspath(args.output_dir)
    success_count = 0

    for pkg in matched_packages:
        name = pkg.get("name")
        repo = pkg.get("repo")
        branch = pkg.get("branch")
        paths = pkg.get("paths")
        hook = pkg.get("hook")

        cache_dir = ensure_source_cache(args.cache_root, repo, branch)
        if not cache_dir:
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
                # 解析 "mv <src> <dst>"
                parts = hook.split()
                if len(parts) >= 3:
                    s_rel = parts[1]
                    d_rel = parts[2]
                    src_full = os.path.join(dest_root, s_rel)
                    dst_full = dest_root if d_rel in [".", "./"] else os.path.join(dest_root, d_rel)
                    if os.path.exists(src_full):
                        try:
                            shutil.move(src_full, dst_full)
                        except Exception as e:
                            print(f"⚠️ 执行 mv 失败: {hook} ({e})")
            else:
                try:
                    subprocess.run(hook, shell=True, cwd=dest_root, check=False)
                except Exception as e:
                    print(f"⚠️ 执行 hook 失败: {hook} ({e})")

        success_count += 1

    print(f"✅ 目标 [{args.target}] 软件包收集完成: 成功 {success_count}/{len(matched_packages)}")


if __name__ == "__main__":
    main()
