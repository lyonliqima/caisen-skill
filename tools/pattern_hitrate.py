#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pattern_hitrate.py — 破底翻 / 形态 pattern_score 的历史预测力
==============================================================
把蔡森破底翻量化筛选器.py 的 pattern_score 分桶：
    <60 / 60-66 / 67-69 / >=70
与未来 5/20/60 日收益做映射，输出每桶的胜率与平均收益。

直接回答「pattern_score 到底有没有预测力」：
  - 若各桶胜率单调上升 → 有信息量；
  - 若各桶胜率无单调关系 → 明确报出「pattern_score 不携带方向信息」。

数据来源：--data 指向回测导出文件（JSON/CSV，每行含 pattern_score 与
forward_5/forward_20/forward_60 收益%）。无数据文件 → 报错退出，禁止编造。

样本不足：单桶 n < 30 时该桶标「样本不足」，不参与「单调关系」结论。

用法
----
  python3 tools/pattern_hitrate.py --data backtest/breakout_samples.json
  python3 tools/pattern_hitrate.py --help
"""
import argparse
import csv
import json
import os
import sys


BUCKETS = [("<60", lambda s: s < 60),
           ("60-66", lambda s: 60 <= s < 67),
           ("67-69", lambda s: 67 <= s < 70),
           (">=70", lambda s: s >= 70)]


def _load_samples(path):
    if not os.path.exists(path):
        sys.stderr.write("✗ 数据文件不存在：%s\n" % path)
        sys.exit(1)
    rows = []
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
    else:
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(r)
    if not rows:
        sys.stderr.write("✗ 数据文件为空\n")
        sys.exit(1)
    return rows


def _to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description="形态 pattern_score 历史预测力")
    ap.add_argument("--data", required=True,
                    help="回测导出：含 pattern_score 与 forward_5/forward_20/forward_60 收益%%")
    ap.add_argument("--min-bucket", type=int, default=30,
                    help="单桶判定单调关系所需最小样本")
    args = ap.parse_args()

    rows = _load_samples(args.data)
    # 分桶
    table = {name: {"n": 0, "w5": 0, "w20": 0, "w60": 0,
                    "5": [], "20": [], "60": []} for name, _ in BUCKETS}
    for r in rows:
        ps = _to_float(r.get("pattern_score"))
        if ps is None:
            continue
        f5 = _to_float(r.get("forward_5"))
        f20 = _to_float(r.get("forward_20"))
        f60 = _to_float(r.get("forward_60"))
        for name, fn in BUCKETS:
            if fn(ps):
                b = table[name]
                b["n"] += 1
                for key in ("5", "20", "60"):
                    val = {"5": f5, "20": f20, "60": f60}[key]
                    if val is not None:
                        b[key].append(val)
                        if val > 0:
                            b["w" + key] += 1
                break

    result = {"buckets": []}
    rates = []
    for name, _ in BUCKETS:
        b = table[name]
        rec = {"bucket": name, "n": b["n"]}
        for key, lbl in (("5", "5日"), ("20", "20日"), ("60", "60日")):
            arr = b[key]
            n = len(arr)
            win = b["w" + key]
            wr = (win / n) if n else None
            avg = (sum(arr) / n) if n else None
            rec["win_rate_%s" % key] = round(wr * 100, 1) if wr is not None else None
            rec["avg_ret_%s" % key] = round(avg, 3) if avg is not None else None
            if wr is not None:
                rec["n_%s" % key] = n
        result["buckets"].append(rec)
        if b["n"] >= args.min_bucket:
            rates.append((name, rec.get("win_rate_60")))

    # 单调性判定（用 60 日胜率，且桶样本充足）
    monotone = None
    if len(rates) >= 2 and all(r[1] is not None for r in rates):
        seq = [r[1] for r in rates]
        increasing = all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1))
        decreasing = all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1))
        monotone = "上升" if increasing else ("下降" if decreasing else "无单调关系")
        result["monotonic_60d_winrate"] = monotone
        if monotone == "无单调关系":
            result["conclusion"] = ("⚠️ 各桶 60 日胜率无单调关系 → pattern_score 在样本内"
                                    "不携带方向信息，不应单独作为入场依据")
        else:
            result["conclusion"] = "各桶 60 日胜率%s → pattern_score 有方向预测力" % monotone
    else:
        result["conclusion"] = "样本不足（充足桶 < 2），无法判定 pattern_score 是否携带信息"

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
