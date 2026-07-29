#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
baseline.py — 预测台账的「对照组三基准」计算器
================================================
算三件事（全部基于 asof 之前的历史数据，严禁使用 asof 之后的数据）：

  a) random_dir —— 无条件方向基准
     该标的历史上所有长度为 window 的滚动窗口中，收益方向与本次判断一致的频率。
     注意：不是固定 50%。多数股票/商品有正漂移，用实际频率。
  b) ma_rule    —— 简单规则基准
     规则：收盘价 > MA20 判多，< MA20 判空。统计该规则在历史上同 window 长度的方向命中率。
  c) benchmark  —— 买入持有
     同期该品种滚动 window 窗口的收益率分布（mean / median / n）。

置信区间统一用 Wilson score interval（小样本比正态近似稳）。

数据源优先级：market-data-cache 本地缓存 → akshare → 报错退出（绝不编造）。

防前视偏差：所有统计只用 t 及之前可得的收盘价，窗口定义严格在 asof 之前截断。

用法
----
  python3 tools/baseline.py --symbol 600519 --window 60 --direction 多 \
                            --target-low 0.05 --target-high 0.15 --asof 2026-07-29
  python3 tools/baseline.py --help

退出码：0 = 成功并输出 JSON；1 = 数据不足/取数失败，stdout 仍打印 {"error": "..."}。
"""
import argparse
import json
import math
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE_DIR = os.path.join(ROOT, "market-data-cache")


# ───────────────────────── 数据加载 ─────────────────────────
def _load_prices(symbol, asof):
    """返回 asof 之前、按日期升序的 [(date_str, close), ...]；取不到返回 None。

    优先级：本地缓存 CSV/JSON → akshare。
    绝不编造：任何一步失败都返回 None，由上层报「无法计算」。
    """
    asof_d = datetime.strptime(asof, "%Y-%m-%d")
    rows = []

    # 1) 本地缓存：market-data-cache/<symbol>.csv|json，列 date,close
    for ext in (".csv", ".json"):
        p = os.path.join(CACHE_DIR, symbol + ext)
        if os.path.exists(p):
            try:
                if ext == ".csv":
                    import csv
                    with open(p, encoding="utf-8") as f:
                        for r in csv.DictReader(f):
                            d = str(r.get("date", "")).strip()
                            c = r.get("close")
                            if d and c not in (None, ""):
                                rows.append((d, float(c)))
                else:
                    with open(p, encoding="utf-8") as f:
                        data = json.load(f)
                        for r in data:
                            rows.append((str(r["date"]), float(r["close"])))
            except Exception:
                rows = []
    if rows:
        return _truncate(rows, asof_d)

    # 2) akshare（动态导入，失败即放弃）
    try:
        import akshare as ak  # type: ignore
        # 股票：600519 / 000001；期货/指数尝试不同接口
        for fn in ("stock_zh_a_hist",):
            try:
                df = getattr(ak, fn)(symbol=symbol, period="daily",
                                     start_date="20000101", end_date=asof.replace("-", ""),
                                     adjust="")
                if df is not None and len(df):
                    for _, r in df.iterrows():
                        rows.append((str(r["日期"]), float(r["收盘"])))
                    break
            except Exception:
                continue
    except Exception:
        pass
    if rows:
        return _truncate(rows, asof_d)
    return None


def _truncate(rows, asof_d):
    out = []
    for d, c in rows:
        try:
            dd = datetime.strptime(d[:10], "%Y-%m-%d")
        except Exception:
            continue
        if dd < asof_d:
            out.append((d[:10], c))
    out.sort(key=lambda x: x[0])
    return out


# ───────────────────────── 统计工具 ─────────────────────────
def wilson(p, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = max(0.0, center - margin)
    hi = min(1.0, center + margin)
    return (lo, hi)


def _direction_of(text):
    t = str(text)
    if "多" in t:
        return 1
    if "空" in t:
        return -1
    return 0  # 中性/震荡：无明确方向


# ───────────────────────── 三类基准 ─────────────────────────
def random_dir(prices, window, judge_sign):
    """无条件方向基准：滚动 window 窗口的收益方向与判断一致的频率。"""
    if judge_sign == 0:
        return {"error": "中性/震荡方向无明确方向基准，无法计算 random_dir"}
    rets = [prices[i + window][1] / prices[i][1] - 1
            for i in range(len(prices) - window)]
    if len(rets) < 2:
        return {"error": "历史窗口不足，无法计算 random_dir"}
    hit = sum(1 for r in rets if (1 if r > 0 else -1) == judge_sign)
    n = len(rets)
    p = hit / n
    lo, hi = wilson(p, n)
    return {"hit_rate": round(p, 4), "n": n,
            "ci95": [round(lo, 4), round(hi, 4)], "reliable": n >= 250}


def ma_rule(prices, window, judge_sign):
    """MA20 规则基准：close>MA20 判多，<MA20 判空，持有 window 日的方向命中率。"""
    closes = [c for _, c in prices]
    n = len(closes)
    if n < 20 + window:
        return {"error": "历史不足（需 ≥ %d 根）" % (20 + window)}
    ma20 = []
    for i in range(n):
        if i < 19:
            ma20.append(None)
        else:
            ma20.append(sum(closes[i - 19:i + 1]) / 20.0)
    matches = 0
    total = 0
    for i in range(19, n - window):
        sig = 1 if closes[i] > ma20[i] else -1
        fwd = closes[i + window] / closes[i] - 1
        act = 1 if fwd > 0 else -1
        total += 1
        if sig == act:
            matches += 1
    if total < 2:
        return {"error": "可统计样本不足，无法计算 ma_rule"}
    p = matches / total
    lo, hi = wilson(p, total)
    return {"hit_rate": round(p, 4), "n": total,
            "ci95": [round(lo, 4), round(hi, 4)], "reliable": total >= 250}


def buy_hold(prices, window):
    """买入持有：滚动 window 窗口的收益率分布。"""
    rets = [prices[i + window][1] / prices[i][1] - 1
            for i in range(len(prices) - window)]
    if len(rets) < 2:
        return {"error": "历史窗口不足，无法计算 benchmark"}
    rets_s = sorted(rets)
    mid = len(rets_s) // 2
    median = rets_s[mid] if len(rets_s) % 2 else (rets_s[mid - 1] + rets_s[mid]) / 2
    return {"mean_return": round(sum(rets) / len(rets), 4),
            "median_return": round(median, 4),
            "n": len(rets), "reliable": len(rets) >= 250}


def _selftest():
    """合成数据验证防前视偏差：asof 之后的价格绝不能被纳入任何统计。"""
    asof = "2026-06-01"
    asof_d = datetime.strptime(asof, "%Y-%m-%d")
    # 前 10 个点在 asof 之前，最后 1 个点在 asof 之后（未来极端值）
    rows = [(f"2026-05-{i:02d}", 100.0 + i) for i in range(1, 11)]
    rows.append(("2026-07-01", 999.0))  # 未来极端值
    out = _truncate(rows, asof_d)
    assert all(datetime.strptime(d, "%Y-%m-%d") < asof_d for d, _ in out), \
        "防前视偏差失效：asof 之后数据泄漏进统计"
    assert len(out) == 10, "未来点未被截断：len=%d" % len(out)
    closes = [c for _, c in out]
    assert max(closes) < 200, "未来极端值污染了统计：max=%s" % max(closes)
    # 顺带验证三基准函数只用到截断后的数据（未来点不参与任何收益计算）
    rd = random_dir(out, 1, 1)
    assert isinstance(rd, dict) and "hit_rate" in rd, "random_dir 未返回合法结构"
    print("✓ baseline 防前视偏差自测通过（asof 之后数据被 _truncate 排除，未参与统计）")
    sys.exit(0)


def main():
    # --self-test 须能在不提供 --symbol/--asof 的情况下独立运行（防前视偏差单测）
    if "--self-test" in sys.argv[1:]:
        _selftest()
    ap = argparse.ArgumentParser(
        description="对照组三基准：random_dir / ma_rule / buy&hold",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--symbol", required=True, help="标的代码，如 600519 / I2609")
    ap.add_argument("--window", type=int, default=60, help="滚动窗口长度（交易日）")
    ap.add_argument("--direction", default="多", help="方向判断（多/空/中性震荡…）")
    ap.add_argument("--target-low", type=float, default=None, help="幅度区间下界（小数，如0.05）")
    ap.add_argument("--target-high", type=float, default=None, help="幅度区间上界（小数，如0.15）")
    ap.add_argument("--asof", required=True, help="数据截止日 YYYY-MM-DD（只用此前数据）")
    ap.add_argument("--self-test", action="store_true", help="运行防前视偏差自测（合成数据验证 asof 之后数据被排除）")
    args = ap.parse_args()

    if args.self_test:
        _selftest()

    prices = _load_prices(args.symbol, args.asof)
    if not prices or len(prices) < args.window + 1:
        out = {"error": "历史数据不足或取数失败（symbol=%s, asof=%s, 可用=%d 根）"
               % (args.symbol, args.asof, len(prices) if prices else 0),
               "reliable": False}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)

    judge = _direction_of(args.direction)
    rd = random_dir(prices, args.window, judge)
    mr = ma_rule(prices, args.window, judge)
    bh = buy_hold(prices, args.window)

    result = {
        "symbol": args.symbol, "asof": args.asof, "window": args.window,
        "direction": args.direction,
        "random_dir": rd,
        "ma_rule": mr,
        "benchmark": bh,
    }
    if all(isinstance(v, dict) and "error" in v for v in (rd, mr, bh)):
        # 三项全失败 → 视为取数不可用
        result["error"] = "三项基准均无可用数据"
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
