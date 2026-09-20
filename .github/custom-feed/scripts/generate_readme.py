#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_readme.py
根据 packages.yaml 清单和模板，生成结构化、带中文描述与来源链接的 README.md。
支持可选读取 packages.lock.json 展示各插件最新抓取提交（commit SHA 超链接）。
"""

import argparse
from datetime import datetime
import json
import os
import sys
import yaml


def main():
    parser = argparse.ArgumentParser(description="Generate README.md from manifest")
    parser.add_argument("--manifest", required=True, help="Path to packages.yaml")
    parser.add_argument("--template", required=True, help="Path to readme-template.md")
    parser.add_argument("--output", required=True, help="Output README.md path")
    parser.add_argument("--target", default=None, help="Optional target branch name (e.g. main, mt798x, qualcommax, qt6)")
    parser.add_argument("--lockfile", default=None, help="Optional path to packages.lock.json")
    args = parser.parse_args()

    if not os.path.exists(args.manifest):
        print(f"❌ 清单文件不存在: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.template):
        print(f"❌ 模板文件不存在: {args.template}", file=sys.stderr)
        sys.exit(1)

    with open(args.manifest, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    packages = data.get("packages", [])

    # 若指定了 target，则仅筛选属于该 target 的软件包
    if args.target and args.target.lower() != "all":
        packages = [p for p in packages if args.target in p.get("targets", [])]

    # 读取 lockfile 中的 commit SHA 映射
    commit_map = {}
    if args.lockfile and os.path.exists(args.lockfile):
        try:
            with open(args.lockfile, "r", encoding="utf-8") as lf:
                lock_data = json.load(lf)
                targets_dict = lock_data.get("targets", {})
                for t, pkgs in targets_dict.items():
                    for name, meta in pkgs.items():
                        c = meta.get("commit")
                        if c and c != "unknown":
                            commit_map[name] = c
        except Exception as e:
            print(f"⚠️ 读取 lockfile 失败: {e}", file=sys.stderr)

    # 按名称正序排序
    packages.sort(key=lambda x: x.get("name", "").lower())

    rows = []
    rows.append("| 插件名称 | 功能描述 | 上游来源 | 适用分支 |")
    rows.append("|:---|:---|:---|:---|")

    for pkg in packages:
        name = pkg.get("name", "")
        desc = pkg.get("description", "").strip()
        desc = " ".join(desc.split())
        repo = pkg.get("repo", "")
        repo_display = repo.replace("https://github.com/", "")
        
        sha = commit_map.get(name)
        if repo:
            if sha and repo.startswith("https://github.com/"):
                repo_link = f"[{repo_display}]({repo}) ([`{sha[:7]}`]({repo}/commit/{sha}))"
            else:
                repo_link = f"[{repo_display}]({repo})"
        else:
            repo_link = "-"

        targets = pkg.get("targets", [])
        targets_display = ", ".join([f"`{t}`" for t in targets]) if targets else "-"

        rows.append(f"| `{name}` | {desc} | {repo_link} | {targets_display} |")

    table_content = "\n".join(rows)

    with open(args.template, "r", encoding="utf-8") as f:
        template = f.read()

    update_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    target_banner = ""
    if args.target and args.target.lower() != "all":
        target_banner = f"> 📌 **当前分支**: `{args.target}`（本分支共收录 **{len(packages)}** 个插件）\n\n"
    else:
        target_banner = f"> 📌 **全量分支汇总**（共收录 **{len(packages)}** 个插件）\n\n"

    rendered = template.replace("{{BRANCH_INFO}}", target_banner)
    rendered = rendered.replace("{{PLUGIN_TABLE}}", table_content)
    rendered = rendered.replace("{{LAST_UPDATE}}", update_time)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        f.write(rendered)

    target_desc = f" [{args.target}]" if args.target else ""
    print(f"✅ README 生成成功{target_desc}: {args.output} (共包含 {len(packages)} 个插件)")


if __name__ == "__main__":
    main()
