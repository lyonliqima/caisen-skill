#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S2 (A+B 自动识别) 自检
======================
锁定 caisen_ab.analyze 的行为，防止回归。

覆盖：
  T1 茅台集成：算法零人工填参复现 颈线≈1265 / 底1151 / 突破07-20 的当前形态
  T2 合成 W 底（多头）：通用性，不依赖茅台
  T3 合成 M 头（空头）：方向识别与等幅计算
  T4 单边无形态：应返回 ok=False 而非崩溃
  T5 窗口太短：<40 根应拒绝
"""
import math
from pathlib import Path
import pandas as pd
import numpy as np

from caisen_ab import analyze, ABParams, find_swings, cluster_swings, atr, _candidates_for


def _load_maotai():
    # 路径固定到本文件所在目录，避免从项目根目录运行时解析到错误位置
    here = Path(__file__).resolve().parent
    df = pd.read_csv(here / "data" / "600519_daily.csv", parse_dates=["date"]).set_index("date").sort_index()
    return df.rename(columns={"vol": "volume"})


def _synth(n: int, gen) -> pd.DataFrame:
    """gen(i) -> (open, high, low, close, vol)"""
    rows = []
    for i in range(n):
        o, h, l, c, v = gen(i)
        d = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)
        rows.append({"date": d, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return pd.DataFrame(rows).set_index("date").sort_index()


# ----------------------------------------------------------------------
# T1 茅台集成
# ----------------------------------------------------------------------
def test_maotai_current_formation():
    df = _load_maotai()
    sig = analyze(df, ABParams())
    assert sig.ok, f"茅台应识别到形态，但: {sig.reason}"
    assert sig.direction == "up", f"方向应为 up，实得 {sig.direction}"
    # 颈线应是 1265 附近的阻力带（算法簇代表价 1268 合理）
    assert 1255 <= sig.neckline <= 1275, f"颈线应≈1265，实得 {sig.neckline}"
    # 底必须是 1151（06-29），这是用户人工标注的精确位置
    assert abs(sig.extreme["price"] - 1151.01) < 1.0, f"底应≈1151，实得 {sig.extreme['price']}"
    assert sig.extreme["date"] == "2026-06-29", f"底日期应 2026-06-29，实得 {sig.extreme['date']}"
    # 突破必须是 07-20 附近
    assert sig.breakout["date"] == "2026-07-20", f"突破应 2026-07-20，实得 {sig.breakout['date']}"
    # 等幅目标① = 颈线 + (颈线-底) ≈ 1268 + 117 ≈ 1385
    assert 1375 <= sig.target1 <= 1395, f"目标①应≈1385，实得 {sig.target1}"
    # 形态名必须是「头肩底」（数据实为三低点：左肩1177/头1151/右肩1170），
    # 不可退化成「单底反转 / 破底翻」（修 P1-1：name_pattern 此前会裁掉左肩）
    assert sig.pattern == "头肩底", f"形态应为头肩底，实得 {sig.pattern}"
    # 突破量能应确认（07-20 放量）
    assert sig.breakout["vol_confirm"], "07-20 突破应有量能确认"
    # 置信度不应低于「中」
    assert sig.confidence in ("中", "高"), f"置信度应中/高，实得 {sig.confidence}"
    print(f"  [T1] 茅台: 颈线={sig.neckline:.2f} 底={sig.extreme['price']:.2f} "
          f"突破={sig.breakout['date']} 目标①={sig.target1:.2f} 形态={sig.pattern} 置信={sig.confidence}")
    return True


# ----------------------------------------------------------------------
# T2 合成 W 底（多头）
# ----------------------------------------------------------------------
def _w_bottom_gen(i):
    # 80 根：100 -> 左底80(20) -> 颈线95(30) -> 右底78(40) -> 突破95(50) -> 上行
    if i < 20:
        c = 100 - i * 1.0
    elif i < 30:
        c = 80 + (i - 20) * 1.5
    elif i < 40:
        c = 95 - (i - 30) * 1.7
    elif i < 50:
        c = 78 + (i - 40) * 1.7
    else:
        c = 95 + (i - 50) * 1.2
    o = c - 0.5
    h = max(o, c) + 1.0
    l = min(o, c) - 1.0
    # 突破日(50)附近加量
    v = 1000.0 if i != 50 else 3000.0
    return o, h, l, c, v


def test_synth_w_bottom():
    df = _synth(80, _w_bottom_gen)
    sig = analyze(df, ABParams())
    assert sig.ok, f"合成W底应识别，但: {sig.reason}"
    assert sig.direction == "up"
    # 颈线应≈95（左右反弹高点连线）
    assert 90 <= sig.neckline <= 100, f"颈线应≈95，实得 {sig.neckline}"
    # 底应≈78（右底，略低于左底80）
    assert 75 <= sig.extreme["price"] <= 82, f"底应≈78，实得 {sig.extreme['price']}"
    # 目标① = 颈线 + (颈线-底) ≈ 95 + 17 ≈ 112
    assert 105 <= sig.target1 <= 120, f"目标①应≈112，实得 {sig.target1}"
    print(f"  [T2] 合成W底: 颈线={sig.neckline:.2f} 底={sig.extreme['price']:.2f} "
          f"突破={sig.breakout['date']} 目标①={sig.target1:.2f} 形态={sig.pattern}")
    return True


# ----------------------------------------------------------------------
# T3 合成 M 头（空头）
# ----------------------------------------------------------------------
def _m_top_gen(i):
    # 80 根：100 -> 左顶130(20) -> 颈线115(30) -> 右顶132(40) -> 跌破115(50) -> 下行
    if i < 20:
        c = 100 + i * 1.5
    elif i < 30:
        c = 130 - (i - 20) * 1.5
    elif i < 40:
        c = 115 + (i - 30) * 1.7
    elif i < 50:
        c = 132 - (i - 40) * 1.7
    else:
        c = 115 - (i - 50) * 1.2
    o = c - 0.5
    h = max(o, c) + 1.0
    l = min(o, c) - 1.0
    v = 1000.0 if i != 50 else 3000.0
    return o, h, l, c, v


def test_synth_m_top():
    df = _synth(80, _m_top_gen)
    sig = analyze(df, ABParams())
    assert sig.ok, f"合成M头应识别，但: {sig.reason}"
    assert sig.direction == "down", f"方向应为 down，实得 {sig.direction}"
    # 颈线应≈115（两顶之间低点连线）
    assert 110 <= sig.neckline <= 120, f"颈线应≈115，实得 {sig.neckline}"
    # 顶应≈132（右顶）
    assert 128 <= sig.extreme["price"] <= 135, f"顶应≈132，实得 {sig.extreme['price']}"
    # 目标① = 颈线 - (顶-颈线) ≈ 115 - 17 ≈ 98
    assert 92 <= sig.target1 <= 104, f"目标①应≈98，实得 {sig.target1}"
    print(f"  [T3] 合成M头: 颈线={sig.neckline:.2f} 顶={sig.extreme['price']:.2f} "
          f"突破={sig.breakout['date']} 目标①={sig.target1:.2f} 形态={sig.pattern}")
    return True


# ----------------------------------------------------------------------
# T4 单边无形态
# ----------------------------------------------------------------------
def test_monotone_no_pattern():
    df = _synth(80, lambda i: (100 + i, 101 + i, 99 + i, 100 + i, 1000.0))
    sig = analyze(df, ABParams())
    assert not sig.ok, "单边上涨无整理区，应返回 ok=False"
    assert "无信号" in sig.reason or "颈线" in sig.reason, f"应给出无信号理由，实得 {sig.reason}"
    print(f"  [T4] 单边无形态: ok={sig.ok} reason={sig.reason[:30]}...")
    return True


# ----------------------------------------------------------------------
# T5 窗口太短
# ----------------------------------------------------------------------
def test_too_short():
    df = _synth(30, _w_bottom_gen)
    sig = analyze(df, ABParams())
    assert not sig.ok, "不足 40 根应拒绝"
    print(f"  [T5] 窗口太短: ok={sig.ok} reason={sig.reason[:30]}...")
    return True


# ----------------------------------------------------------------------
if __name__ == "__main__":
    tests = [test_maotai_current_formation, test_synth_w_bottom, test_synth_m_top,
             test_monotone_no_pattern, test_too_short]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
        except Exception as e:
            print(f"  [ERROR] {t.__name__}: {repr(e)}")
    print(f"\nS2 自检: {passed}/{len(tests)} 通过")
    if passed != len(tests):
        raise SystemExit(1)
