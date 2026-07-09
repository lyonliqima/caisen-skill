#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
examples-retire.py — 示例退役机制
====================================
每个 *-analysis 技能目录下若堆积了过多 dated 示例（examples-YYMMDD*.md），
只保留最新的 N 期（默认 3），其余移到 `<skill>/_archive/` 归档。

为什么：示例是「学步骤不抄结论」的素材，但过期示例会诱使模型复述旧方向性判断。
保留最新 2-3 期即可，旧的归档不删（可逆）。

用法
----
  python3 examples-retire.py                 # 全仓库所有 *-analysis 技能，默认保留 3 期
  python3 examples-retire.py --keep 2       # 只保留最新 2 期
  python3 examples-retire.py --dry-run      # 只打印将归档哪些，不移动
  python3 examples-retire.py --skill yang-shiguang-analysis   # 只处理某个技能

说明
----
- 仅匹配 `examples-<6位日期>*.md`（如 examples-0624.md / examples-0630-strong-dollar.md）。
- 不含 `examples.md`（通用步骤说明，永远保留）。
- 按文件名内嵌日期降序，保留前 N，其余移入 `_archive/`。
"""
import argparse, os, re, shutil, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DATE = re.compile(r"examples-(\d{6})")
SKILLS = [d for d in os.listdir(ROOT)
           if d.endswith("-analysis") and os.path.isdir(os.path.join(ROOT, d))]


def dated_examples(skill_dir):
    out = []
    for fn in os.listdir(skill_dir):
        m = DATE.match(fn)
        if m and fn.endswith(".md"):
            out.append((m.group(1), fn))
    out.sort(key=lambda x: x[0], reverse=True)  # 新→旧
    return out


def main():
    ap = argparse.ArgumentParser(description="示例退役：保留最新 N 期，其余归档")
    ap.add_argument("--keep", type=int, default=3, help="保留最新几期（默认 3）")
    ap.add_argument("--dry-run", action="store_true", help="只打印不移动")
    ap.add_argument("--skill", help="只处理指定技能目录名")
    args = ap.parse_args()

    skills = [args.skill] if args.skill else SKILLS
    total_moved = 0
    for sk in skills:
        sdir = os.path.join(ROOT, sk)
        if not os.path.isdir(sdir):
            sys.stderr.write("✗ 找不到技能目录: %s\n" % sk)
            continue
        dated = dated_examples(sdir)
        if not dated:
            continue
        keep = dated[:args.keep]
        retire = dated[args.keep:]
        print("\n📂 %s：共 %d 期 dated 示例，保留 %d，归档 %d"
              % (sk, len(dated), len(keep), len(retire)))
        for _, fn in keep:
            print("   ✓ 保留  %s" % fn)
        if not retire:
            print("   （无需归档）")
            continue
        arch = os.path.join(sdir, "_archive")
        if not args.dry_run:
            os.makedirs(arch, exist_ok=True)
        for _, fn in retire:
            src = os.path.join(sdir, fn)
            if args.dry_run:
                print("   🗄 将归档  %s" % fn)
            else:
                shutil.move(src, os.path.join(arch, fn))
                print("   🗄 已归档  %s → _archive/" % fn)
                total_moved += 1
    print("\n✓ 完成（共移动 %d 个文件）" % total_moved)


if __name__ == "__main__":
    main()
