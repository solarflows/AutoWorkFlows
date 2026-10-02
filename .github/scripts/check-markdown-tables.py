#!/usr/bin/env python3
"""GFM markdown 表格格式检查器 (可选 --fix 自动修复 T1)。

检查项:
  T1 分隔行列数 != 表头列数 —— 整个表格退化为普通段落 (最常见根因)
  T2 数据行列数 != 表头列数 —— 单行溢出/缺列
  T3 表格块前一行非空且非标题/分隔线 —— 表格无法中断段落, 不渲染
  T4 分隔行单元格非法 (须为 - / :-- / --: / :--: 形式, 至少一个连字符)
  T5 表格行内反引号未闭合
  T6 表格块无分隔行 (仅 1 行, 可能是正文误用 | 开头或表格被空行截断)

列数按 GFM 语义计算: 反引号内与转义 \\| 的管道不计入分隔符。

用法:
  python check-markdown-tables.py                     # 扫描 git tracked *.md
  python check-markdown-tables.py a.md b.md           # 指定文件
  python check-markdown-tables.py --fix docs/todo.md  # 重写纯 --- 分隔行使其匹配表头列数
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")
HEADING_RE = re.compile(r"^#{1,6}\s")
HR_RE = re.compile(r"^\s{0,3}((-\s*){3,}|(\*\s*){3,}|(_\s*){3,})$")
SEP_CELL_RE = re.compile(r"^\s*:?-+:?\s*$")


def scan_pipes(line: str):
    """返回 (有效管道数, 反引号是否未闭合)。反引号 span 内与转义 \\| 不计。"""
    n = 0
    i = 0
    length = len(line)
    while i < length:
        ch = line[i]
        if ch == "`":
            j = line.find("`", i + 1)
            if j == -1:
                return n, True
            i = j + 1
            continue
        if ch == "\\" and i + 1 < length and line[i + 1] == "|":
            i += 2
            continue
        if ch == "|":
            n += 1
        i += 1
    return n, False


def cell_count(line: str):
    """表格行单元格数; 反引号未闭合返回 None。"""
    n, unclosed = scan_pipes(line)
    if unclosed:
        return None
    s = line.strip()
    lead = s.startswith("|")
    trail = s.endswith("|") and not s.endswith("\\|")
    return n + 1 - (1 if lead else 0) - (1 if trail else 0)


def split_row(line: str):
    """拆出单元格文本列表 (去掉首尾管道外侧的空段)。"""
    s = line.strip()
    parts = s.split("|")
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return parts


def is_plain_sep(line: str):
    """分隔行是否为纯 --- 单元格 (无对齐冒号) —— 可安全自动重写。"""
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r"-+", c.strip()) for c in cells)


def iter_blocks(lines):
    """产出 (块起始行号 0 基, 块行列表); 跳过 fenced code block 内的行。"""
    in_fence = False
    fence_char = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(1)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
            elif line.strip() and set(line.strip()) == {fence_char}:
                in_fence = False
            i += 1
            continue
        if in_fence:
            i += 1
            continue
        if not line.strip().startswith("|"):
            i += 1
            continue
        start = i
        while i < len(lines) and lines[i].strip().startswith("|"):
            i += 1
        yield start, lines[start:i]


def check_file(path: Path):
    issues = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        return [(1, "E0", f"非 UTF-8 编码: {e}")]
    lines = text.splitlines()

    for start, block in iter_blocks(lines):
        header = block[0]
        hcols = cell_count(header)
        if hcols is None:
            issues.append((start + 1, "T5", "表头行反引号未闭合"))
        if len(block) < 2:
            issues.append((start + 1, "T6", f"表格块仅 {len(block)} 行 (无分隔行)"))
        else:
            sep = block[1]
            scols = cell_count(sep)
            if scols is None:
                issues.append((start + 2, "T5", "分隔行反引号未闭合"))
            else:
                bad = [c for c in split_row(sep) if not SEP_CELL_RE.match(c)]
                if bad:
                    issues.append((start + 2, "T4", f"分隔行含非法单元格: {bad}"))
                if hcols is not None and scols != hcols:
                    issues.append(
                        (start + 2, "T1",
                         f"分隔行 {scols} 列 != 表头 {hcols} 列 (整表不渲染)"))
            for k in range(2, len(block)):
                dcols = cell_count(block[k])
                if dcols is None:
                    issues.append((start + k + 1, "T5", "数据行反引号未闭合"))
                elif hcols is not None and dcols != hcols:
                    issues.append((start + k + 1, "T2",
                                   f"数据行 {dcols} 列 != 表头 {hcols} 列"))
        if start > 0:
            prev = lines[start - 1]
            if prev.strip() and not HEADING_RE.match(prev) and not HR_RE.match(prev):
                issues.append((start + 1, "T3",
                               f"表格前一行非空非标题: \"{prev.strip()[:48]}\""))
    return issues


def fix_file(path: Path):
    """重写纯 --- 分隔行, 使列数匹配表头。返回修复数。"""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)
    bare = [l.rstrip("\r\n") for l in lines]
    changed = 0
    for start, block in iter_blocks(bare):
        if len(block) < 2:
            continue
        hcols = cell_count(block[0])
        scols = cell_count(block[1])
        if (hcols and scols is not None and scols != hcols
                and is_plain_sep(block[1])):
            eol = lines[start + 1][len(bare[start + 1]):]
            lines[start + 1] = "|" + "---|" * hcols + eol
            changed += 1
    if changed:
        path.write_bytes("".join(lines).encode("utf-8"))
    return changed


def main():
    args = [a for a in sys.argv[1:] if a != "--fix"]
    do_fix = "--fix" in sys.argv[1:]
    if args:
        files = [Path(a) for a in args]
    else:
        r = subprocess.run(["git", "ls-files", "*.md"],
                           capture_output=True, text=True, encoding="utf-8")
        files = [Path(p) for p in r.stdout.splitlines() if p]

    if do_fix:
        for f in files:
            n = fix_file(f)
            print(f"{'FIX' if n else 'SKIP'} {f}: 重写 {n} 个分隔行")
        return 0

    total = 0
    for f in files:
        if not f.exists():
            print(f"SKIP  {f} (不存在)")
            continue
        issues = check_file(f)
        if issues:
            total += len(issues)
            print(f"\n== {f} ==")
            for ln, code, msg in issues:
                print(f"  L{ln:<5} {code}  {msg}")
        else:
            print(f"OK    {f}")
    print(f"\n{'✓ 无问题' if total == 0 else f'✗ 共 {total} 个问题'}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
