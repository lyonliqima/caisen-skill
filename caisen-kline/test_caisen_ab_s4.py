#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S4 专项核查测试：颈线起点(x0) + 动态停损(2~7% ATR自适应) + 形态命名算法化。

钉死 S4 三个核心产物，避免未来改动悄悄破坏（此前靠看图侥幸，无回归守护）：
  (1) neck_start_i 必须 = 颈线首触点 index（图上线只从该点画起，P1-2）
  (2) stop_pct 必须落在 2%~7% 区间（ATR 自适应夹紧，P1-4）
  (3) pattern 必须算法化判定（头肩底/W底/M头/双底…，P1-1）
"""
import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, ".")
from caisen_ab import analyze, ABParams

HERE = Path(__file__).resolve().parent
PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra and not cond else ""))


# ----------------------------------------------------------------------
# 构造器（复用 T2/T3 已验证可识别的 W底/M头；头肩底用 ramp 单调段）
# ----------------------------------------------------------------------
def _synth(n, gen):
    rows = []
    for i in range(n):
        o, h, l, c, v = gen(i)
        d = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)
        rows.append({"date": d, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return pd.DataFrame(rows).set_index("date").sort_index()


def _w_bottom_gen(i):
    if i < 20:   c = 100 - i * 1.0
    elif i < 30: c = 80 + (i - 20) * 1.5
    elif i < 40: c = 95 - (i - 30) * 1.7
    elif i < 50: c = 78 + (i - 40) * 1.7
    else:        c = 95 + (i - 50) * 1.2
    o = c - 0.5; h = max(o, c) + 1.0; l = min(o, c) - 1.0
    v = 1000.0 if i != 50 else 3000.0
    return o, h, l, c, v


def _m_top_gen(i):
    if i < 20:   c = 100 + i * 1.5
    elif i < 30: c = 130 - (i - 20) * 1.5
    elif i < 40: c = 115 + (i - 30) * 1.7
    elif i < 50: c = 132 - (i - 40) * 1.7
    else:        c = 115 - (i - 50) * 1.2
    o = c - 0.5; h = max(o, c) + 1.0; l = min(o, c) - 1.0
    v = 1000.0 if i != 50 else 3000.0
    return o, h, l, c, v


def _ramp(turns, n, vol=1000.0):
    xs = [t[0] for t in turns]; ys = [t[1] for t in turns]
    closes = []
    for i in range(n):
        if i <= xs[0]: y = ys[0]
        elif i >= xs[-1]: y = ys[-1]
        else:
            for k in range(len(xs) - 1):
                if xs[k] <= i <= xs[k + 1]:
                    y = ys[k] + (ys[k + 1] - ys[k]) * (i - xs[k]) / (xs[k + 1] - xs[k]); break
            else: y = ys[-1]
        closes.append(float(y))
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    recs = []
    prev = closes[0]
    for i, c in enumerate(closes):
        recs.append({"date": dates[i], "open": float(prev), "high": max(prev, c) + 1.0,
                     "low": min(prev, c) - 1.0, "close": float(c), "volume": float(vol)})
        prev = c
    return pd.DataFrame(recs).set_index("date").sort_index()


# ----------------------------------------------------------------------
# S4-1 茅台：颈线起点 / 停损区间 / 形态
# ----------------------------------------------------------------------
def test_maotai_s4():
    df = pd.read_csv(HERE / "data" / "600519_daily.csv", parse_dates=["date"]).set_index("date")
    df = df.rename(columns={"vol": "volume"}).astype(float)
    sig = analyze(df, ABParams())
    assert sig.ok
    check("S4-1 茅台 颈线起点存在且>0", sig.neck_start_i > 0, f"neck_start_i={sig.neck_start_i}")
    check("S4-1 茅台 颈线起点=首触点(日期一致)",
          pd.Timestamp(df.index[sig.neck_start_i]).date() == pd.Timestamp(sig.neck_start).date(),
          f"i={sig.neck_start_i} date={df.index[sig.neck_start_i].date()} neck_start={sig.neck_start}")
    check("S4-1 茅台 首触点确实在颈线触点列表",
          str(df.index[sig.neck_start_i].date()) in [str(d) for d, _ in sig.neck_touches],
          f"touches={sig.neck_touches}")
    pct = sig.stop_pct * 100
    check("S4-1 茅台 停损幅度在 2%~7%", 2.0 <= pct <= 7.0, f"stop_pct={pct:.2f}%")
    check("S4-1 茅台 停损被夹紧(不小于颈线93%)",
          sig.stop >= sig.neckline * 0.93 - 1e-6 and sig.stop <= sig.neckline * 0.98 + 1e-6,
          f"stop={sig.stop} neck={sig.neckline}")
    check("S4-1 茅台 形态=头肩底", sig.pattern == "头肩底", f"pattern={sig.pattern}")
    check("S4-1 茅台 进场价=突破根收盘(非颈线价)",
          abs(sig.entry - sig.breakout["close"]) < 1e-6 and abs(sig.entry - sig.neckline) > 1e-6,
          f"entry={sig.entry} bo_close={sig.breakout['close']} neck={sig.neckline}")


# ----------------------------------------------------------------------
# S4-2 合成头肩底：首触点 i 精确 + 形态 + 停损
# ----------------------------------------------------------------------
def test_synth_head_shoulders():
    df = _ramp([(0,100),(12,80),(18,100),(48,60),(55,100),(62,80),(78,110),(94,112)], 95)
    sig = analyze(df, ABParams())
    assert sig.ok, sig.reason
    check("S4-2 头肩底 形态命名正确", sig.pattern == "头肩底", f"pattern={sig.pattern}")
    # 首颈线触点 i=18（左肩顶），颈线起点必须与之对应
    check("S4-2 头肩底 颈线起点=首触点i(18)",
          sig.neck_start_i == 18, f"neck_start_i={sig.neck_start_i}")
    pct = sig.stop_pct * 100
    check("S4-2 头肩底 停损在 2%~7%", 2.0 <= pct <= 7.0, f"stop_pct={pct:.2f}%")


# ----------------------------------------------------------------------
# S4-3 合成 W 底：形态命名 + 颈线起点存在 + 停损
# ----------------------------------------------------------------------
def test_synth_w_bottom():
    df = _synth(80, _w_bottom_gen)
    sig = analyze(df, ABParams())
    assert sig.ok, sig.reason
    check("S4-3 W底 形态含W底/双底", "W 底" in sig.pattern or "双底" in sig.pattern, f"pattern={sig.pattern}")
    check("S4-3 W底 颈线起点存在且<突破", sig.neck_start_i > 0 and sig.neck_start_i < sig.breakout["i"],
          f"neck_start_i={sig.neck_start_i} bo_i={sig.breakout['i']}")
    pct = sig.stop_pct * 100
    check("S4-3 W底 停损在 2%~7%", 2.0 <= pct <= 7.0, f"stop_pct={pct:.2f}%")


# ----------------------------------------------------------------------
# S4-4 合成 M 头（空头）：形态 + 方向 + 颈线起点 + 停损
# ----------------------------------------------------------------------
def test_synth_m_top():
    df = _synth(80, _m_top_gen)
    sig = analyze(df, ABParams())
    assert sig.ok, sig.reason
    check("S4-4 M头 方向=down", sig.direction == "down", f"dir={sig.direction}")
    check("S4-4 M头 形态含M头/双顶", "M 头" in sig.pattern or "双顶" in sig.pattern, f"pattern={sig.pattern}")
    check("S4-4 M头 颈线起点<跌破点",
          sig.neck_start_i > 0 and sig.neck_start_i < sig.breakout["i"],
          f"neck_start_i={sig.neck_start_i} bo_i={sig.breakout['i']}")
    pct = sig.stop_pct * 100
    check("S4-4 M头 停损在 2%~7%", 2.0 <= pct <= 7.0, f"stop_pct={pct:.2f}%")


# ----------------------------------------------------------------------
# S4-5 停损 clamp 边界：用茅台验证 1×ATR 被夹进 [93%,98%] 区间
# ----------------------------------------------------------------------
def test_stop_clamp():
    df = pd.read_csv(HERE / "data" / "600519_daily.csv", parse_dates=["date"]).set_index("date")
    df = df.rename(columns={"vol": "volume"}).astype(float)
    sig = analyze(df, ABParams())
    raw = sig.neckline - sig.atr  # 理论停损（未夹）
    clamped = sig.stop
    # 实际停损应取 raw 与 [93%,98%] 的交集
    lo, hi = sig.neckline * 0.93, sig.neckline * 0.98
    expect = max(min(raw, hi), lo)
    check("S4-5 停损=clamp(颈线-ATR, 93%, 98%)", abs(clamped - expect) < 0.01,
          f"raw={raw:.2f} expect={expect:.2f} got={clamped:.2f}")


if __name__ == "__main__":
    for fn in [test_maotai_s4, test_synth_head_shoulders, test_synth_w_bottom,
              test_synth_m_top, test_stop_clamp]:
        print(f"\n=== {fn.__name__} ===")
        fn()
    print(f"\nS4 专项自检: {len(PASS)} 通过 / {len(FAIL)} 失败")
    sys.exit(1 if FAIL else 0)
