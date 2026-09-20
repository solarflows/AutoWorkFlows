#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_readme.py
根据 packages.yaml 清单和模板，生成结构化、带中文描述与来源链接的 README.md。
"""

import argparse
from datetime import datetime
import os
import sys
import yaml


def main():
    parser = argparse.ArgumentParser(description="Generate README.md from manifest")
    parser.add_argument("--manifest", required=True, help="Path to packages.yaml")
    parser.add_argument("--template", required=True, help="Path to readme-template.md")
    parser.add_argument("--output", required=True, help="Output README.md path")
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

    # 按名称正序排序
    packages.sort(key=lambda x: x.get("name", "").lower())

    rows = []
    rows.append("| 插件名称 | 功能描述 | 上游来源 | 适用分支 |")
    rows.append("|:---|:---|:---|:---|")

    for pkg in packages:
        name = pkg.get("name", "")
        desc = pkg.get("description", "").strip()
        # 清理描述中的多余空格或注释前缀
        desc = " ".join(desc.split())
        repo = pkg.get("repo", "")
        repo_display = repo.replace("https://github.com/", "")
        repo_link = f"[{repo_display}]({repo})" if repo else "-"
        targets = pkg.get("targets", [])
        targets_display = ", ".join([f"`{t}`" for t in targets]) if targets else "-"

        rows.append(f"| `{name}` | {desc} | {repo_link} | {targets_display} |")

    table_content = "\n".join(rows)

    with open(args.template, "r", encoding="utf-8") as f:
        template = f.read()

    update_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    rendered = template.replace("{{PLUGIN_TABLE}}", table_content)
    rendered = rendered.replace("{{LAST_UPDATE}}", update_time)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        f.write(rendered)

    print(f"✅ README 生成成功: {args.output} (共包含 {len(packages)} 个插件)")


if __name__ == "__main__":
    main()
