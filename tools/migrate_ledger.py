#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate_ledger.py — 预测台账一次性归一化迁移（P0-③）
======================================================
把 ledger.jsonl 里的历史自由文本字段收敛到 schema 枚举：
  direction     15 种写法 → 多/空/中性偏多/中性偏空/中性震荡
  asset_class   15 种写法 → 12 个标准值（商品期货 等）
  predictability 剥掉括号装饰（"低（60日个股方向）"→"低"）
  market_regime  剥掉括号装饰（"弱势市（…）"→"弱势市"）

映射表直接复用 predictions-ledger/append.py 的 *_ALIASES（单一事实来源）。
写盘前自动备份 ledger.jsonl → ledger.jsonl.bak-<YYYYMMDD-HHMMSS>。

用法：
  python3 tools/migrate_ledger.py --dry-run   # 只看会改什么，不写盘
  python3 tools/migrate_ledger.py             # 备份 + 迁移 + 前后统计
"""
import argparse
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LEDGER = os.path.join(ROOT, "predictions-ledger", "ledger.jsonl")
APPEND_PY = os.path.join(ROOT, "predictions-ledger", "append.py")


def _load_append_module():
    """按路径加载 append.py，复用其归一化映射表与剥装饰函数。"""
    spec = importlib.util.spec_from_file_location("append_mod", APPEND_PY)
    mod = importlib.util.module_from_spec(spec)
    # append.py 顶层只有常量与函数定义，import 安全（main 有 __main__ 保护）
    spec.loader.exec_module(mod)
    return mod


def load_records():
    recs = []
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def main():
    ap = argparse.ArgumentParser(description="ledger.jsonl 字段归一化迁移")
    ap.add_argument("--dry-run", action="store_true", help="只打印变更，不写盘")
    args = ap.parse_args()

    mod = _load_append_module()
    recs = load_records()

    before_dir = Counter(r.get("direction", "?") for r in recs)
    before_asset = Counter(r.get("asset_class", "?") for r in recs)

    changed = 0
    details = []
    for r in recs:
        snap = {k: r.get(k) for k in ("direction", "asset_class",
                                      "predictability", "market_regime")}
        warns = mod.normalize_record(r)
        if warns:
            changed += 1
            details.append((r.get("id"), warns))

    after_dir = Counter(r.get("direction", "?") for r in recs)
    after_asset = Counter(r.get("asset_class", "?") for r in recs)

    print("=== 迁移预览（%d 条记录，%d 条将被修改）===\n" % (len(recs), changed))
    print("direction 前：", dict(before_dir))
    print("direction 后：", dict(after_dir))
    print("")
    print("asset_class 前：", dict(before_asset))
    print("asset_class 后：", dict(after_asset))
    print("")
    if details:
        print("--- 逐条变更 ---")
        for rid, warns in details:
            print("  %s: %s" % (rid, "；".join(warns)))

    # 迁移后完整性自检：枚举全过 + JSON 可序列化
    bad = []
    for r in recs:
        if r.get("direction") not in mod.CANONICAL_DIRECTIONS:
            bad.append((r.get("id"), "direction", r.get("direction")))
        if r.get("asset_class") not in mod.CANONICAL_ASSETS:
            bad.append((r.get("id"), "asset_class", r.get("asset_class")))
    if bad:
        print("\n⚠️ 以下值映射表覆盖不到（需补 ASSET_ALIASES / DIRECTION_ALIASES 后重跑）：")
        for b in bad:
            print("  %s %s=%r" % b)
        if not args.dry_run:
            sys.stderr.write("✗ 存在未归一值，中止写盘（未修改 ledger.jsonl）\n")
            sys.exit(2)

    if args.dry_run:
        print("\n[dry-run] 未写盘。去掉 --dry-run 执行迁移。")
        return

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = LEDGER + ".bak-" + ts
    shutil.copy2(LEDGER, bak)
    with open(LEDGER, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("\n✓ 迁移完成：%d 条记录，%d 条被修改" % (len(recs), changed))
    print("✓ 备份：%s" % bak)


if __name__ == "__main__":
    main()
