#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S8 全链路回归：caisen_pipeline.run / analyze_and_render 钉死。

覆盖：
  S8-1  guard：不支持市场（美股）经 run → 上抛 UnsupportedMarketError，绝不静默出图
  S8-2  茅台 happy path：analyze_and_render → png 生成 + 报告含结构判定 + sig.ok
  S8-3  无形态路径：单调上涨 df → 不崩溃、出图成功、报告含「未识别」类提示
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pandas as pd
from caisen_data import Meta, MARKETS, UnsupportedMarketError
from caisen_pipeline import run, analyze_and_render

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'OK' if cond else 'XX'} {name}" + (f"  -> {detail}" if detail else ""))


def _mt(path):
    df = pd.read_csv(path, parse_dates=['date']).set_index('date')
    df = df.rename(columns={'vol': 'volume'}).astype(float)
    mk = MARKETS["CN_SH"]
    n = len(df)
    meta = Meta(name="贵州茅台", code="600519", setcode=1, market="CN_SH",
                market_label=mk.label, period=4, period_label="日线", tq_flag=1,
                adjust_label="前复权", vol_unit=mk.vol_unit, bars=n,
                start=str(df.index[0].date()), end=str(df.index[-1].date()),
                hq_date="", hq_time="", last_bar_closed=True,
                t_plus=mk.t_plus, price_limit=mk.price_limit, short_mode=mk.short_mode,
                snapshot="2026-08-03", warnings=[])
    return df, meta


print("=" * 64)
print("S8-1：不支持市场（美股）经 run → 上抛异常")
print("=" * 64)
try:
    run({}, "AAPL", "Apple Inc.", market_hint="US")   # 应在此前抛错
    check("S8-1 美股经 run 上抛异常（未静默出图）", False, "竟未抛错")
except UnsupportedMarketError as e:
    check("S8-1 美股经 run 上抛 UnsupportedMarketError", True, str(e)[:40])
except Exception as e:
    check("S8-1 美股经 run 上抛 UnsupportedMarketError", False, f"抛错类型不对：{type(e).__name__}")

print()
print("=" * 64)
print("S8-2：茅台 happy path（analyze_and_render）")
print("=" * 64)
df, meta = _mt("data/600519_daily.csv")
tmp = tempfile.mkdtemp()
res = analyze_and_render(df, meta, out_dir=tmp)
check("S8-2 png 生成", os.path.exists(res["png"]), res["png"])
check("S8-2 sig.ok（识别到形态）", res["sig"].ok, f"reason={getattr(res['sig'],'reason','')}")
check("S8-2 报告非空", bool(res["report"].strip()))
check("S8-2 报告含五块之一：关键价位", "关键价位" in res["report"] or "颈线" in res["report"])
check("S8-2 报告含非投资建议", "不构成任何投资建议" in res["report"])
check("S8-2 报告含 C1 约束", "C1" in res["report"])

print()
print("=" * 64)
print("S8-3：无形态路径（单调上涨 df）不崩溃、出图成功")
print("=" * 64)
n = 120
dates = pd.date_range("2026-01-01", periods=n, freq="B")
mono = pd.DataFrame({"open": range(n), "high": [i + 1 for i in range(n)],
                     "low": [i - 1 for i in range(n)], "close": [i + 0.5 for i in range(n)],
                     "volume": [1000] * n}, index=dates)
mk = MARKETS["CN_SH"]
meta3 = Meta(name="测试单调", code="999999", setcode=1, market="CN_SH",
             market_label=mk.label, period=4, period_label="日线", tq_flag=1,
             adjust_label="前复权", vol_unit=mk.vol_unit, bars=n,
             start=str(dates[0].date()), end=str(dates[-1].date()),
             hq_date="", hq_time="", last_bar_closed=True,
             t_plus=mk.t_plus, price_limit=mk.price_limit, short_mode=mk.short_mode,
             snapshot="2026-08-03", warnings=[])
try:
    res3 = analyze_and_render(mono, meta3, out_dir=tmp)
    check("S8-3 单调 df 不崩溃且出图", os.path.exists(res3["png"]))
except Exception as e:
    check("S8-3 单调 df 不崩溃且出图", False, f"崩溃：{e}")

print()
print(f"结果：通过 {len(PASS)} / 失败 {len(FAIL)}")
sys.exit(1 if FAIL else 0)
