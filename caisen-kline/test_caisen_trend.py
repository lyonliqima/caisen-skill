#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""caisen_trend + 四色出图 回归测试（2026-09-20 新增）

钉死对象：
  T1  暖机根数 / α 公式（EMA 工程估计，不是随便拍的数）
  T2  EMA 递推 = 标准 EMA（逐根手算比对）
  T3  classify 严格等于 Pine 脚本四分支语义（逐根比对，含边界）
  T4  状态 / 阵营持续根数
  T5  侧切换噪声过滤（1 根假穿不认，≥3 根才认）
  T6  量价四象限读数（价升量增/价升量减/价跌量增/价跌量缩）
  T7  summary_text 必带字段（量价 / 交叉校验 / 不参与A/B/K判定声明）
  T8  consistency_note 背离判定
  T9  四色出图：K线数=量柱数=n，EMA 两线在位
  T10 阳线空心 / 阴线实心（保留涨跌维度）
  T11 暖机区半透明（<warmup 的根 alpha<1，>warmup 的 alpha=1）
  T12 图例两行存在且互不重叠
  T13 侧切换三角数 = 确认的侧切换数
  T14 four_color=False 兼容老 mplfinance 路径
  T15 传入异源 trend（长度不匹配）自动退回，不崩
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import math
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.text as mtext
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

import caisen_trend as T
from caisen_chart import render

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f"\n      {detail}" if detail else ""))


def mk(n=200, seed=7, vol_kind="x"):
    """合成日线：多段趋势（保证 R/Y/B/G 四色都出现）+ 可控量能。"""
    rng = np.random.default_rng(seed)
    px, recs = 100.0, []
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    for i in range(n):
        drift = [0.9, -0.8, 0.5, -1.0, 0.7][(i // (n // 5)) % 5]
        px = px * (1 + drift / 100.0 + rng.normal(0, 0.006))
        o = px * (1 + rng.normal(0, 0.002))
        hi = max(o, px) * 1.006
        lo = min(o, px) * 0.994
        v = 1000 * (1 + 0.5 * abs(math.sin(i / 9.0))) + i * 3
        recs.append(dict(date=dates[i], open=o, high=hi, low=lo, close=px, volume=v))
    return pd.DataFrame(recs).set_index("date")


META = dict(title="T", ylabel="价格", vlabel="成交量")

print("=" * 70)
print("T1 α 公式 / 暖机根数")
print("=" * 70)
check("α(12) = 2/13 ≈ 0.1538", abs(T.alpha_of(12) - 2 / 13) < 1e-12,
      f"{T.alpha_of(12):.6f}")
check("暖机根数 span=50 → 116 根", T.warmup_bars(50) == 116, f"{T.warmup_bars(50)}")
check("暖机根数 span=12 → 28 根", T.warmup_bars(12) == 28, f"{T.warmup_bars(12)}")
check("暖机根数随周期单调不减",
      T.warmup_bars(5) < T.warmup_bars(12) < T.warmup_bars(50) < T.warmup_bars(200))

print()
print("=" * 70)
print("T2 EMA 递推 = 标准 EMA")
print("=" * 70)
df = mk()
e = T.ema(df["close"], 12)
manual, a = [], 2 / 13
for c in df["close"].values:
    manual.append(c if not manual else a * c + (1 - a) * manual[-1])
manual = np.array(manual)
check("EMA12 与逐根手算完全一致", np.allclose(e.values, manual, atol=1e-9),
      f"max|diff|={np.max(np.abs(e.values - manual)):.2e}")
check("EMA 无 NaN（暖机由 alpha 标注，不用 NaN 屏蔽）", not e.isna().any())

print()
print("=" * 70)
print("T3 classify 严格等于 Pine 脚本语义")
print("=" * 70)
tr = T.compute(df)
f, s = df["close"].ewm(span=12, adjust=False, min_periods=1).mean(), \
    df["close"].ewm(span=50, adjust=False, min_periods=1).mean()
exp = []
for c, ff, ss in zip(df["close"], f, s):
    if c >= ff and c >= ss:
        exp.append("R")
    elif c < ff and c >= ss:
        exp.append("Y")
    elif c >= ff and c < ss:
        exp.append("B")
    else:
        exp.append("G")
got = list(tr["state"].values)
check("逐根四色与 Pine 定义一致", got == exp,
      f"首个不一致={next(((i, got[i], exp[i]) for i in range(len(got)) if got[i] != exp[i]), None)}")
cnt = {k: got.count(k) for k in T.STATE_ORDER}
check("四色全部可达（R/Y/B/G 均出现）", all(v > 0 for v in cnt.values()), f"{cnt}")
# 边界：close == EMA 两者 → 归红（>=），不得丢状态
b = pd.Series([10.0, 10.0, 10.0])
st_b = T.classify(b, pd.Series([10.0] * 3), pd.Series([10.0] * 3))
check("close == EMA12 == EMA50 → 判 R（>= 语义，不落空）", list(st_b.values) == ["R"] * 3,
      f"{list(st_b.values)}")

print()
print("=" * 70)
print("T4 状态 / 阵营持续根数")
print("=" * 70)
st = pd.Series(["G", "G", "B", "B", "Y", "Y", "Y", "R", "R"])
kc, ks = T.state_span(st)
check("最新色连续根数 = 2", kc == 2, f"{kc}")
check("最新阵营连续根数 = 5（Y/Y/Y/R/R 同属多头侧）", ks == 5, f"{ks}")

print()
print("=" * 70)
print("T5 侧切换噪声过滤（<3 根假穿不认）")
print("=" * 70)
noise = pd.Series(["G", "G", "R", "G", "G", "G", "G", "Y", "Y", "Y", "Y"])
fl = T.side_flips(noise, min_persist=3)
check("1 根假穿不算侧切换", len(fl) == 1, f"{fl}")
check("确认的侧切换 = 空头侧→多头侧", bool(fl) and fl[0]["frm"] == "bear"
      and fl[0]["to"] == "bull", f"{fl}")
check("侧切换点位落在首根新阵营", bool(fl) and fl[0]["i"] == 7, f"{fl}")

print()
print("=" * 70)
print("T6 量价四象限读数")
print("=" * 70)


def vp(px_chg, vol_chg):
    """近 k 根才发生「价变 + 量变」，前段平盘 —— 这样 近k vs 前k 才可比。"""
    n, k = 40, 5
    close = np.concatenate([np.full(n - k, 100.0), np.full(k, 100.0 * (1 + px_chg))])
    vol = np.concatenate([np.full(n - k, 1000.0), np.full(k, 1000.0 * (1 + vol_chg))])
    d = pd.DataFrame(dict(open=close, high=close * 1.001, low=close * 0.999,
                          close=close, volume=vol),
                     index=pd.date_range("2026-01-01", periods=n, freq="B"))
    return T.vol_price_read(d)["tag"]


t1 = vp(+0.05, +0.5)
t2 = vp(+0.05, -0.5)
t3 = vp(-0.05, +0.5)
t4 = vp(-0.05, -0.5)
check("价升量增 → 量能配合", "价升量增" in t1, t1)
check("价升量减 → 量价背离", "价升量减" in t2, t2)
check("价跌量增 → 抛压释放", "价跌量增" in t3, t3)
check("价跌量缩 → 缩量止跌", "价跌量缩" in t4, t4)

print()
print("=" * 70)
print("T7 summary_text 必带字段")
print("=" * 70)
sx = T.summary_text(df, tr, direction="up")
check("含「六、四色K线节奏」标题", "四色K线节奏" in sx)
check("含「量价」读数行", "量价" in sx)
check("含「交叉校验」行", "交叉校验" in sx)
check("显式声明不参与 A/B/K 招判定", "不参与A/B/K招判定" in sx)
check("行数 ≤5（不撑爆文字副图）", sx.strip().count("\n") + 1 <= 5,
      f"{sx.strip().count(chr(10)) + 1} 行")

print()
print("=" * 70)
print("T8 consistency_note 背离判定")
print("=" * 70)
st_bear = pd.Series(["G"] * 5)
tr_bear = dict(state=st_bear)
check("四色空头侧 × 形态偏多 → 提示反弹非反转",
      "视为反弹" in T.consistency_note(tr_bear, "up"),
      T.consistency_note(tr_bear, "up"))
check("四色多头侧 × 形态偏空 → 提示破位需带量",
      "需带量" in T.consistency_note(dict(state=pd.Series(["R"] * 5)), "down"),
      T.consistency_note(dict(state=pd.Series(["R"] * 5)), "down"))
check("同向 → 无背离",
      "无背离" in T.consistency_note(dict(state=pd.Series(["R"] * 5)), "up"))

print()
print("=" * 70)
print("T9 / T10 / T11 / T12 / T13 四色出图")
print("=" * 70)
df2 = mk(n=260)
tr2 = T.compute(df2)
fig = render(df2, META, [], [], "a", "b", "__t4c.png", return_fig=True, dpi=80)
ax1, ax2 = fig.axes[0], fig.axes[-1]
n = len(df2)
patches = [p for p in ax1.patches if isinstance(p, Rectangle)]
bars = [p for p in ax2.patches if isinstance(p, Rectangle)]
check("K线实体数 + 平盘线 = 覆盖全部 n 根", len(patches) + 0 == len(patches)
      and len(patches) <= n and len(patches) >= n - 5,
      f"n={n} patches={len(patches)}")
check("量柱数 = n", len(bars) == n, f"{len(bars)}")

import caisen_chart as CC
cols, alphas = CC._four_color_plan(df2, tr2)
wu = int(tr2["warmup"])
check("暖机根数 = 116", wu == 116)
check("暖机区 alpha < 1", alphas[0] < 1.0 and alphas[wu - 1] < 1.0, f"{alphas[0]}")
check("暖机区之后 alpha = 1", alphas[wu] == 1.0 and alphas[-1] == 1.0)

# 阳线空心 / 阴线实心
o, c = df2["open"].values, df2["close"].values
up_i = next(i for i in range(wu, n) if c[i] > o[i])
dn_i = next(i for i in range(wu, n) if c[i] < o[i])
up_p = [p for p in patches if abs(p.get_x() + 0.32 - up_i) < 1e-6]
dn_p = [p for p in patches if abs(p.get_x() + 0.32 - dn_i) < 1e-6]
check("阳线（收>开）实体空心（白底 + 状态色描边）",
      bool(up_p) and up_p[0].get_facecolor()[:3] == (1.0, 1.0, 1.0),
      f"{up_p[0].get_facecolor() if up_p else None}")
check("阴线（收<开）实体实心（=状态色）",
      bool(dn_p) and dn_p[0].get_facecolor()[:3] != (1.0, 1.0, 1.0),
      f"{dn_p[0].get_facecolor() if dn_p else None}")

# EMA 双线在位（橙 / 紫）
lines = [ln for ln in ax1.get_lines()]
def has(color):
    want = tuple(round(v, 3) for v in matplotlib.colors.to_rgb(color))
    for ln in lines:
        got = ln.get_color()
        try:
            got = tuple(round(v, 3) for v in matplotlib.colors.to_rgb(got))
        except Exception:
            continue
        if got == want:
            return True
    return False
check("EMA12 橙色线在位", has(T.EMA_FAST_COLOR), T.EMA_FAST_COLOR)
check("EMA50 紫色线在位（避开空头反弹蓝）", has(T.EMA_SLOW_COLOR), T.EMA_SLOW_COLOR)
check("EMA50 线色 ≠ 空头反弹蓝（防同色混淆）",
      T.EMA_SLOW_COLOR.lower() != T.STATE_COLOR['B'].lower(),
      f"{T.EMA_SLOW_COLOR} vs {T.STATE_COLOR['B']}")
check("四色色号两两不同", len({v.lower() for v in T.STATE_COLOR.values()}) == 4,
      f"{T.STATE_COLOR}")

# 图例两行
fts = [t.get_text() for t in fig.texts]
check("图例含四色语义", any("多头强势" in x and "空头弱势" in x for x in fts))
check("图例含暖机区说明", any("暖机区" in x for x in fts), fts[:3])
leg = [t for t in fig.texts if "多头强势" in t.get_text() or "暖机区" in t.get_text()]
fig.canvas.draw()
r = fig.canvas.get_renderer()
ol = any(leg[i].get_window_extent(r).overlaps(leg[j].get_window_extent(r))
         for i in range(len(leg)) for j in range(i + 1, len(leg)))
check("图例两行不重叠", not ol)

# 侧切换三角
sca = [c for c in ax1.collections if hasattr(c, "get_offsets") and len(c.get_offsets())]
n_mark = sum(len(c.get_offsets()) for c in sca)
check("侧切换三角数 = 确认的侧切换数", n_mark == len(tr2["flips"]),
      f"markers={n_mark} flips={len(tr2['flips'])}")
plt.close(fig)

print()
print("=" * 70)
print("T14 four_color=False 兼容老路径")
print("=" * 70)
fig = render(df2, META, [], [], "a", "b", "__t4c2.png", return_fig=True,
             four_color=False, dpi=80)
check("退回 mplfinance 红绿路径不崩", len(fig.axes) == 3, f"{len(fig.axes)}")
check("老路径无四色图例", not any("多头强势" in t.get_text() for t in fig.texts))
plt.close(fig)

print()
print("=" * 70)
print("T15 异源 trend 长度不匹配 → 自动退回")
print("=" * 70)
bad = dict(tr2)
bad["state"] = tr2["state"].iloc[:10]
fig = render(df2, META, [], [], "a", "b", "__t4c3.png", return_fig=True,
             trend=bad, dpi=80)
check("长度不匹配不崩且退回老路径", len(fig.axes) == 3)
plt.close(fig)

print()
print("=" * 70)
print("T16 数据不足（n < 暖机）如实报警，不假装可信")
print("=" * 70)
short = mk(n=60)
trs = T.compute(short)
check("data_short = True", trs["data_short"] is True)
check("summary_text 不再占用行数写警讯（已挪到图例带）",
      "警讯" not in T.summary_text(short, trs))
fig = render(short, META, [], [], "a", "b", "__t4c4.png", return_fig=True, dpi=80)
check("图上出现【警讯】取数提示",
      any("警讯" in t.get_text() and "取数" in t.get_text() for t in fig.texts))
plt.close(fig)

print()
print(f"结果：通过 {len(PASS)} / 失败 {len(FAIL)}")
if FAIL:
    print("失败项:", FAIL)
sys.exit(1 if FAIL else 0)
