#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
expert_weights.py — 专家动态权重（收缩加权，样本不足回退先验）
=============================================================
当某专家在某资产类别上的台账样本 ≥10 条后，权重按收缩公式调整：
    λ        = n / (n + 20)
    权重      = 先验权重 × (1 − λ) + 表现权重 × λ
    表现权重  = 该专家在该资产类别上的超额命中率归一化（softmax）

样本不足（n < 10）→ λ 强制为 0，完全用先验权重（不硬拟合）。

数据来源：ledger.jsonl 的 expert_views 字段（每条记录记录各专家分项判断）。
无 expert_views → 全部 n=0 → 回退先验。

用法
----
  python3 tools/expert_weights.py
  python3 tools/expert_weights.py --ledger predictions-ledger/ledger.jsonl
  python3 tools/expert_weights.py --help
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_LEDGER = os.path.join(ROOT, "predictions-ledger", "ledger.jsonl")

# 先验权重（与 caisen-10 SKILL.md 权重体系精神一致；核心框架高、辅助低）
PRIOR = {
    "杨世光": 1.00, "卢麒元": 1.00, "蔡森": 1.00, "笨鸟": 1.00,
    "serenity": 0.90, "Mi姐": 1.00, "妙想量化": 0.80, "实证因果": 0.80,
    "risk-control": 0.70, "腾讯圆桌": 0.70, "期货团": 0.90, "路口大爷": 0.90,
}
DIR_SIGN = {"多": 1, "空": -1, "中性": 0}


def _load(ledger_path):
    recs = []
    if not os.path.exists(ledger_path):
        return recs
    with open(ledger_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except Exception:
                    pass
    return recs


def _direction_of(t):
    t = str(t)
    if "多" in t:
        return 1
    if "空" in t:
        return -1
    return 0


def collect_cells(recs):
    """返回 {(expert, asset_class): [outcome_1/0, ...]}。"""
    cells = {}
    for r in recs:
        views = r.get("expert_views")
        if not isinstance(views, list):
            continue
        ret = r.get("actual_return")
        if not isinstance(ret, (int, float)):
            continue
        actual = 1 if ret > 0 else (-1 if ret < 0 else 0)
        if actual == 0:
            continue
        ac = r.get("asset_class", "?")
        for v in views:
            if not isinstance(v, dict):
                continue
            ex = v.get("expert")
            d = _direction_of(v.get("direction"))
            if not ex or d == 0:
                continue
            hit = 1 if d == actual else 0
            cells.setdefault((ex, ac), []).append(hit)
    return cells


def compute_weights(recs):
    cells = collect_cells(recs)
    total_n = sum(len(v) for v in cells.values())
    result = {"total_expert_views": total_n, "weights": [], "cells": {}}
    if total_n == 0:
        result["note"] = "暂无 expert_views 数据 → 全部回退先验权重（λ=0）"
        for ex, w in PRIOR.items():
            result["weights"].append({"expert": ex, "prior": w,
                                      "effective": w, "lambda": 0.0, "n": 0})
        return result

    # 逐单元：命中率 + 先验下的 λ
    for (ex, ac), outcomes in cells.items():
        n = len(outcomes)
        hr = sum(outcomes) / n
        lam = n / (n + 20)
        cap_lam = 0.0 if n < 10 else lam
        result["cells"]["%s|%s" % (ex, ac)] = {
            "n": n, "hit_rate": round(hr, 4),
            "lambda": round(cap_lam, 4),
            "sample_sufficient": n >= 10,
        }

    # 按资产类别做 softmax 归一化超额命中率 → 表现权重
    by_ac = {}
    for (ex, ac), outcomes in cells.items():
        by_ac.setdefault(ac, []).append((ex, sum(outcomes) / len(outcomes)))
    perf = {}
    for ac, lst in by_ac.items():
        if any(n >= 10 for (_, _) in []):  # 占位，真正判断在下方
            pass
        rates = {ex: hr for ex, hr in lst}
        # 以 0.5 为基准的超额；softmax 温度缩放
        excess = {ex: max(0.0, hr - 0.5) for ex, hr in rates.items()}
        # 仅对 n>=10 的单元参与表现权重；否则用先验
        sufficient = {ex: (n >= 10) for (ex, ac2), outcomes in cells.items() if ac2 == ac}
        vals = {ex: (excess[ex] if sufficient.get(ex) else 0.0) for ex in rates}
        denom = sum(math.exp(vals[e] * 5) for e in vals) or 1.0
        for ex in vals:
            perf[(ex, ac)] = math.exp(vals[ex] * 5) / denom

    # 合成有效权重
    seen = set()
    for (ex, ac), outcomes in cells.items():
        if ex in seen:
            continue
        seen.add(ex)
        n = len(outcomes)
        lam = 0.0 if n < 10 else n / (n + 20)
        prior = PRIOR.get(ex, 0.80)
        pw = perf.get((ex, ac), 1.0 / max(1, len([e for e in perf if e[1] == ac])))
        eff = prior * (1 - lam) + pw * lam
        result["weights"].append({
            "expert": ex, "prior": round(prior, 3),
            "effective": round(eff, 3), "lambda": round(lam, 4), "n": n,
        })
    result["weights"].sort(key=lambda x: x["effective"], reverse=True)
    if total_n < 30:
        result["note"] = "样本不足（总 n=%d < 30），λ 受 n<10 强约束，基本回退先验" % total_n
    return result


def main():
    ap = argparse.ArgumentParser(description="专家动态权重（收缩加权）")
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    args = ap.parse_args()
    out = compute_weights(_load(args.ledger))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
