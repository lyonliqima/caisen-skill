#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sanity_check_card.py — 评分卡量纲一致性校验（消除「看对了却被记成错」的假失败）
====================================================================================
核心：期限(period) + 幅度区间(target) + 证伪位(falsification) 必须数学自洽。

  σ_d  = 过去 250 个交易日对数收益的标准差（日波动率）
  σ_p  = σ_d × √(period_days)                      （期间波动率）
  R1   = (target_high − target_low) / σ_p          （幅度宽度比）
  R2   = |current − falsification| / current / σ_p （证伪距离比）

判定：
  R1 < 1.0  → ❌ 幅度区间过窄，几乎必然落空。建议宽度 ≥ __%
  R1 > 3.0  → ⚠️ 幅度区间过宽，判断无信息量。建议收窄至 __%
  R2 < 1.5  → ❌ 证伪位距现价过近（仅 __σ），期间必被噪音打掉。建议 ≥ __%
  R2 > 4.0  → ⚠️ 证伪位过远，形同没有止损

输出 pass / fail + 具体建议数值。fail 时退出码非 0。

用法
----
  python3 tools/sanity_check_card.py --symbol I2609 --period-days 60 \
      --current 780 --target-low 0.05 --target-high 0.15 --falsification 810
  python3 tools/sanity_check_card.py --help
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE_DIR = os.path.join(ROOT, "market-data-cache")


def _load_closes(symbol, asof=None):
    rows = []
    for ext in (".csv", ".json"):
        p = os.path.join(CACHE_DIR, symbol + ext)
        if os.path.exists(p):
            try:
                if ext == ".csv":
                    import csv
                    with open(p, encoding="utf-8") as f:
                        for r in csv.DictReader(f):
                            c = r.get("close")
                            if c not in (None, ""):
                                rows.append(float(c))
                else:
                    with open(p, encoding="utf-8") as f:
                        for r in json.load(f):
                            rows.append(float(r["close"]))
            except Exception:
                rows = []
    if rows:
        return rows
    # akshare 兜底
    try:
        import akshare as ak  # type: ignore
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                start_date="20000101", end_date="20260101", adjust="")
        if df is not None:
            rows = [float(x) for x in df["收盘"]]
    except Exception:
        pass
    return rows


def _log_ret_stdev(closes, lookback=250):
    if len(closes) < lookback + 1:
        sample = closes
    else:
        sample = closes[-(lookback + 1):]
    rets = [math.log(sample[i + 1] / sample[i]) for i in range(len(sample) - 1)]
    if len(rets) < 2:
        return None
    m = sum(rets) / len(rets)
    var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
    return math.sqrt(var)


def check_card(symbol, period_days, current, target_low, target_high, falsification,
               asof=None):
    """返回 (ok_bool, report_dict)。ok=False 表示存在 ❌ 项。"""
    closes = _load_closes(symbol, asof)
    sigma_d = _log_ret_stdev(closes)
    report = {"symbol": symbol, "period_days": period_days,
              "current": current, "target_low": target_low,
              "target_high": target_high, "falsification": falsification}
    if sigma_d is None:
        report["error"] = "历史收盘价不足 250 根，无法估计日波动率"
        report["ok"] = False
        return False, report

    sigma_p = sigma_d * math.sqrt(period_days)
    r1 = (target_high - target_low) / sigma_p
    r2 = abs(current - falsification) / current / sigma_p

    issues = []      # ❌ 阻断项
    warnings = []    # ⚠️ 仅警告
    suggestions = {}

    # 幅度宽度比 R1
    if r1 < 1.0:
        sug = max(target_high - target_low, sigma_p * 1.0)
        issues.append("❌ 幅度区间过窄（R1=%.2f < 1.0），几乎必然落空" % r1)
        suggestions["target_width_min_pct"] = round(sigma_p * 100, 2)
    elif r1 > 3.0:
        warnings.append("⚠️ 幅度区间过宽（R1=%.2f > 3.0），判断无信息量" % r1)
        suggestions["target_width_suggest_pct"] = round(sigma_p * 2.0 * 100, 2)

    # 证伪距离比 R2
    if r2 < 1.5:
        need = current * (1.5 * sigma_p)
        issues.append("❌ 证伪位距现价过近（R2=%.2f < 1.5），%.0f 日内必被噪音打掉"
                      % (r2, period_days))
        suggestions["falsification_min_dist_pct"] = round(1.5 * sigma_p * 100, 2)
    elif r2 > 4.0:
        warnings.append("⚠️ 证伪位过远（R2=%.2f > 4.0），形同没有止损" % r2)

    report.update({
        "sigma_d_pct": round(sigma_d * 100, 3),
        "sigma_p_pct": round(sigma_p * 100, 3),
        "R1": round(r1, 3),
        "R2": round(r2, 3),
        "issues": issues,
        "warnings": warnings,
        "suggestions": suggestions,
        "ok": len(issues) == 0,
    })
    return (len(issues) == 0), report


def main():
    ap = argparse.ArgumentParser(description="评分卡量纲一致性校验")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--period-days", type=int, required=True)
    ap.add_argument("--current", type=float, required=True, help="当前价")
    ap.add_argument("--target-low", type=float, required=True, help="幅度下界（小数，如0.05）")
    ap.add_argument("--target-high", type=float, required=True, help="幅度上界（小数，如0.15）")
    ap.add_argument("--falsification", type=float, required=True, help="证伪价位")
    ap.add_argument("--asof", default=None)
    args = ap.parse_args()

    ok, rep = check_card(args.symbol, args.period_days, args.current,
                         args.target_low, args.target_high, args.falsification, args.asof)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
