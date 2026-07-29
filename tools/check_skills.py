#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_skills.py — SKILL.md frontmatter 合规检查（FIX 4）

遍历全仓所有 SKILL.md，逐项检查：
  1) 首行必须是 `---`（YAML frontmatter 起始）
  2) frontmatter 必须含 `name` 和 `description`
  3) `description` 长度 >= 40 字符
  4) `name` 必须与所在目录名一致
  5) 文件不得含 \\r（行尾必须 LF）

任一不通过打印 <文件: 原因> 并以非零码退出。
用法：
  python3 tools/check_skills.py
  python3 tools/check_skills.py --root /path/to/repo   # 指定根目录
"""
import argparse
import os
import sys

MIN_DESC_LEN = 40


def find_skill_md(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过被 gitignore 的归档/缓存目录
        parts = set(dirpath.split(os.sep))
        if parts & {"_archive", "_cache", "__pycache__", ".git"}:
            continue
        for fn in filenames:
            if fn == "SKILL.md":
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def parse_frontmatter(path):
    """返回 (lines, has_fm, fm_dict)。fm_dict 仅取顶层 key（忽略嵌套的 parameters 等）。

    正确处理 YAML 块标量（description: | 或 >）与缩进嵌套字段。
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    has_fm = bool(lines) and lines[0].strip() == "---"
    fm = {}
    in_block = None  # 当前正在累积的块标量字段名
    if has_fm:
        for ln in lines[1:]:
            s = ln
            if in_block is not None:
                if ln[:1] in (" ", "\t") or ln.strip() == "":
                    fm[in_block] = (fm.get(in_block, "") + "\n" + ln.strip()).strip()
                    continue
                else:
                    in_block = None  # 块结束，继续按普通行解析
            if s.strip() == "---":
                break
            # 缩进行 = 嵌套字段（如 parameters 下的 name/description），跳过
            if not s or s[:1] in (" ", "\t") or s.startswith("#"):
                continue
            if ":" in s:
                k, _, v = s.partition(":")
                k, v = k.strip(), v.strip()
                if v in ("|", ">"):
                    in_block = k
                    fm[k] = ""
                else:
                    fm[k] = v
    return lines, has_fm, fm


def check_one(path, root):
    rel = os.path.relpath(path, root)
    problems = []

    with open(path, "rb") as f:
        raw = f.read()
    if b"\r" in raw:
        problems.append("含 \\r 行尾（必须 LF）")

    lines, has_fm, fm = parse_frontmatter(path)
    if not has_fm:
        problems.append("首行不是 ---（缺 YAML frontmatter）")
        return problems  # 后续检查无意义

    if "name" not in fm:
        problems.append("frontmatter 缺 name")
    if "description" not in fm:
        problems.append("frontmatter 缺 description")
    else:
        desc = fm["description"]
        # 去除引号后计算长度
        if len(desc.strip().strip('"').strip("'")) < MIN_DESC_LEN:
            problems.append("description 长度 < %d" % MIN_DESC_LEN)

    if "name" in fm:
        name = fm["name"].strip().strip('"').strip("'")
        # 所在目录名
        dname = os.path.basename(os.path.dirname(os.path.abspath(path)))
        if name != dname:
            problems.append("name(%s) != 目录名(%s)" % (name, dname))

    return problems


def main():
    ap = argparse.ArgumentParser(description="SKILL.md frontmatter 合规检查")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="仓库根目录（默认脚本上级目录）")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    files = find_skill_md(root)
    if not files:
        print("未找到任何 SKILL.md")
        return 0

    all_problems = {}
    for p in files:
        probs = check_one(p, root)
        if probs:
            all_problems[os.path.relpath(p, root)] = probs

    if not all_problems:
        print("✓ 全部 %d 个 SKILL.md 通过 frontmatter 检查" % len(files))
        return 0

    print("✗ %d/%d 个 SKILL.md 存在问题：" % (len(all_problems), len(files)))
    for rel, probs in all_problems.items():
        for pb in probs:
            print("  %s: %s" % (rel, pb))
    return 1


if __name__ == "__main__":
    sys.exit(main())
