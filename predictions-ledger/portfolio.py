#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
portfolio.py — 组合层风控总账（约定13 · 盲区一修复）
=====================================================
读 predictions-ledger/ledger.jsonl 中 status=open 的预测，按 factor_exposure 归类，
输出组合层全景，而不是单笔对不对：

  1) 每个共享宏观因子的 open 条数、净方向（多空加权置信度）、持仓标的清单
  2) 因子集中度：同因子 open 条数超过阈值(默认 5) → 触发「新开仓降档」硬警告
  3) 全局净敞口：所有 open 预测的方向合计 + 当前已被 --force 放行打破纪律的条数

核心逻辑（LTCM 教训）：单笔证伪位独立，但共享同一个宏观因子的多笔预测会被
同一宏观事件同时击穿。组合层要管的是「这 N 笔加起来长什么样」，不是逐笔。

用法
----
  python3 portfolio.py                 # 打印组合总账 + 降档警告
  python3 portfolio.py --threshold 5   # 自定义同因子阈值（默认 5）
  python3 portfolio.py --json          # JSON 输出（供 agent 程序化读取）
  python3 portfolio.py --quiet         # 只打印警告（无总账表）

依赖：仅标准库。
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger.jsonl")
TODAY = date.today()

# 方向 → 权重符号
_DIR_SIGN = {"多": 1, "中性偏多": 1, "空": -1, "中性偏空": -1, "中性震荡": 0}
# 未填 factor_exposure 的预测归入「未归类」，避免漏算集中度
_UNCLASSIFIED = "（未归类·建议回填 factor_exposure）"


def _load():
    recs = []
    if not os.path.exists(LEDGER):
        return recs
    with open(LEDGER, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception as e:
                sys.stderr.write("⚠️ 第%d行解析失败，跳过: %s\n" % (ln, e))
    return recs


def build_ledger(open_only=True):
    recs = _load()
    if open_only:
        recs = [r for r in recs if str(r.get("status", "open")) == "open"]
    return recs


def analyze(recs, threshold):
    """按因子归类，返回 {factor: {...}, '_global': {...}, '_warnings': [...]}。"""
    factors = defaultdict(lambda: {"count": 0, "net": 0.0, "symbols": [], "ids": []})
    for r in recs:
        tags = r.get("factor_exposure")
        if not isinstance(tags, list) or not tags:
            tags = [_UNCLASSIFIED]
        sign = _DIR_SIGN.get(r.get("direction"), 0)
        conf = r.get("confidence") if isinstance(r.get("confidence"), int) else 0
        for t in tags:
            factors[t]["count"] += 1
            factors[t]["net"] += sign * conf
            factors[t]["symbols"].append(r.get("symbol", "?"))
            factors[t]["ids"].append(r.get("id", "?"))

    warnings = []
    for t, d in factors.items():
        if t == _UNCLASSIFIED:
            continue
        if d["count"] > threshold:
            warnings.append(
                "🔴 因子「%s」当前 open %d 条 > 阈值 %d → 新开仓强制降档一级"
                "（标准仓→轻仓；重仓→标准仓），直至该因子 open 回落阈值内"
                % (t, d["count"], threshold))
    if _UNCLASSIFIED in factors:
        warnings.append(
            "🟡 有 %d 条 open 预测未填 factor_exposure，无法纳入集中度管理，"
            "请回填后再评估组合风险" % factors[_UNCLASSIFIED]["count"])

    # 全局净敞口
    g_net = sum(d["net"] for d in factors.values())
    g_count = len(recs)
    force_cnt = sum(1 for r in recs
                    if isinstance(r.get("discipline_violation"), list)
                    and r["discipline_violation"])

    return {"factors": factors, "global_net": g_net, "global_count": g_count,
            "force_count": force_cnt, "warnings": warnings,
            "_unclassified": _UNCLASSIFIED}


def render(recs, threshold, quiet, as_json):
    a = analyze(recs, threshold)
    if as_json:
        out = {"threshold": threshold, "global_net": a["global_net"],
               "global_count": a["global_count"], "force_count": a["force_count"],
               "factors": {k: {"count": v["count"], "net": round(v["net"], 1),
                               "ids": v["ids"]} for k, v in a["factors"].items()},
               "warnings": a["warnings"]}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if not quiet:
        print("📊 组合层总账（约定13）· %s" % TODAY.isoformat())
        print("   当前 open 预测 %d 条 · 全局净敞口 %+.0f（多正空负，加权置信度）"
              " · --force 放行 %d 条" % (a["global_count"], a["global_net"], a["force_count"]))
        print("\n| 共享因子 | open条数 | 净方向(加权) | 标的 |")
        print("|---|---|---|---|")
        for t, d in sorted(a["factors"].items(), key=lambda kv: -kv[1]["count"]):
            net = d["net"]
            direction = "多▲" if net > 0 else ("空▼" if net < 0 else "中性→")
            print("| %s | %d | %s %+.0f | %s |" % (
                t, d["count"], direction, net,
                "、".join(str(s) for s in d["symbols"][:6])
                + ("…" if len(d["symbols"]) > 6 else "")))

    if a["warnings"]:
        print("\n⚠️ 组合层风控警告：")
        for w in a["warnings"]:
            print("  " + w)
    elif not quiet:
        print("\n✅ 因子集中度在阈值内，无强制降档。")
    if a["force_count"] and not quiet:
        print("\n注：--force 放行记录会削弱多样性纪律，建议关注触发频率。")


def main():
    ap = argparse.ArgumentParser(description="组合层风控总账（约定13）")
    ap.add_argument("--threshold", type=int, default=5,
                    help="同因子 open 条数阈值，超过则新开仓降档（默认 5）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--quiet", action="store_true", help="只打印警告")
    args = ap.parse_args()
    recs = build_ledger(open_only=True)
    render(recs, args.threshold, args.quiet, args.json)


if __name__ == "__main__":
    main()
