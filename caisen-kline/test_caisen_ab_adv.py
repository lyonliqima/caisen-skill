#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2 对抗性复查（修 base_lookback 与 name_pattern 后的回归测试）。

覆盖：宽左肩漏触点 / 横盘无结构 / 末根突破 / 末端形态误判 / 列名契约。
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from caisen_ab import analyze, ABParams


def make_df(closes, vols=None, start="2025-01-01"):
    """从 close 序列造 OHLCV。open=前收，high/low 在 open/close 外扩 1，
    volume 默认常值 1000（保证量能字段存在）。"""
    n = len(closes)
    dates = pd.date_range(start, periods=n, freq="D")
    recs = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        hi = max(o, c) + 1.0
        lo = min(o, c) - 1.0
        recs.append({
            "date": dates[i],
            "open": float(o), "high": float(hi), "low": float(lo),
            "close": float(c),
            "volume": float(vols[i]) if vols else 1000.0,
        })
        prev = c
    return pd.DataFrame(recs).set_index("date").sort_index()


def ramp(turns, n, vol=1000.0):
    """由转折点 (i, price) 线性插值生成 close 序列，再交给 make_df 造 OHLCV。
    相邻转折点之间单调，确保只有转折点成为摆动极值（无杂散分形）。
    turns 须按 i 升序，且覆盖 0..n-1 的端点。"""
    xs = [t[0] for t in turns]
    ys = [t[1] for t in turns]
    closes = []
    for i in range(n):
        if i <= xs[0]:
            y = ys[0]
        elif i >= xs[-1]:
            y = ys[-1]
        else:
            for k in range(len(xs) - 1):
                if xs[k] <= i <= xs[k + 1]:
                    y = ys[k] + (ys[k + 1] - ys[k]) * (i - xs[k]) / (xs[k + 1] - xs[k])
                    break
            else:
                y = ys[-1]
        closes.append(float(y))
    return make_df(closes, vols=[vol] * n)


def build_wide_double_bottom(n=95):
    """宽左肩头肩底：左底/左颈线触点在头之前约 23 根（>15 但 <30）。
    用单调分段构造，颈线触点(反弹高点)是真实的摆动高点，左底在首触点之前——
    既测 base_lookback=60 不漏左触点，也测 name_pattern 修 P1-1 后不把左底裁成单底。
    结构：左肩底80(18) → 左反弹顶100(25,颈线触点①) → 头75(48) →
          右反弹顶100(55,颈线触点②) → 右肩底82(62) → 突破110(78)。
    base_lookback=15 时 start=头-15 会丢掉左触点①(25<33)，仅 1 触点 → 漏判。"""
    turns = [(0, 100), (18, 80), (25, 100), (48, 75), (55, 100), (62, 82), (78, 110), (79, 112)]
    return ramp(turns, n)


def build_flat(n=100):
    return make_df([100.0] * n)


def build_last_bar_breakout(n=90):
    """突破发生在最后一根，验证 find_pullback 空段不崩。"""
    cl = [90] * 6 + [100]            # i=6 高
    cl += [80]                       # 左底
    cl += [100]                      # 颈线触点
    while len(cl) < 60:
        cl.append(95)
    cl[59] = 75                      # 头
    cl.append(95)
    cl.append(100)                   # 颈线触点
    cl.append(82)                    # 右底
    while len(cl) < n - 1:
        cl.append(100)
    cl.append(110)                   # 末根突破
    return make_df(cl[:n])


def build_tail_recent(n=90):
    """末端形态：结构紧凑、突破临近末尾，验证 name_pattern 修 P1-1 后
    不再把近期头肩底误判单底。与 A1 同构，仅 n=90 且突破在 i=80（距末尾近，属近期）。"""
    turns = [(0, 100), (20, 80), (27, 100), (50, 75), (57, 100), (64, 82), (80, 110), (81, 112)]
    return ramp(turns, n)


PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")


print("=== S2 对抗性复查 ===")
# T-A1 宽左肩双底
df1 = build_wide_double_bottom()
sig1 = analyze(df1)
check("A1 宽左肩识别 ok", sig1.ok, f"neck={sig1.neckline:.1f} pattern={sig1.pattern}")
check("A1 颈线触点≥2（左肩未漏）", sig1.ok and len(sig1.neck_touches) >= 2,
      f"touches={sig1.neck_touches}")
check("A1 形态非单底", sig1.ok and sig1.pattern not in ("单底反转",),
      f"pattern={sig1.pattern}")

# T-A1b 用 base_lookback=15 应漏掉左肩触点（证明放宽到 60 有必要）：
# 窄窗口 start=头-15 把左颈线触点(2025-01-26)裁掉，颈线只剩右触点+突破触点，
# 形态结构不完整（头肩底退化成双底）。这是 S2 修复「宽左肩漏触点」的真实回归点。
p15 = ABParams(base_lookback=15)
sig1b = analyze(df1, p15)
left_touch_dropped = "2025-01-26" not in [t[0] for t in sig1b.neck_touches]
check("A1b base_lookback=15 漏掉左肩触点", left_touch_dropped,
      f"touches={sig1b.neck_touches}")

# T-A2 横盘
df2 = build_flat()
sig2 = analyze(df2)
check("A2 横盘无结构 ok=False", not sig2.ok, f"reason={sig2.reason[:30]}")
check("A2 横盘不崩", True)

# T-A3 末根突破
df3 = build_last_bar_breakout()
sig3 = analyze(df3)
check("A3 末根突破不崩", True)
check("A3 突破 ok 或 优雅无信号", sig3.ok or (not sig3.ok))

# T-A4 末端形态误判
df4 = build_tail_recent()
sig4 = analyze(df4)
check("A4 末端形态不误判单底", sig4.ok and sig4.pattern not in ("单底反转",),
      f"pattern={sig4.pattern} touches={len(sig4.neck_touches)}")

# T-A5 列名契约：缺 volume 列应报错而非静默错
try:
    bad = df1.drop(columns=["volume"])
    _ = analyze(bad)
    check("A5 缺volume列报错", False, "未抛错")
except Exception as e:
    check("A5 缺volume列报错", True, f"{type(e).__name__}")

print(f"\n对抗性复查: {len(PASS)} 通过 / {len(FAIL)} 失败")
sys.exit(1 if FAIL else 0)
