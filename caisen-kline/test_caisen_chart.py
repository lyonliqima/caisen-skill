#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""caisen_chart.py S7 回归：把 P2-1/P2-2/P2-3/P2-4 钉死，防未来回退。

覆盖审计里的真实失败场景：
  P2-1：render 不污染入参 levels（不再写 ly 字段）
  P2-2：8 条水平线标签挤在一起 → 不出 ylim 界、两两不重叠（梯形兜底）
  P2-3：idx_of 非交易日（周末）返回最近交易日，不崩溃
  P2-4：pad 自适应，n=250 时右侧留白 ≥ 20%，标签不压 K 线
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.text as mtext
import pandas as pd
from caisen_chart import render, idx_of

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f"\n      {detail}" if detail else ""))


def _mk(n=120, lo=100, hi=200, freq="D"):
    dates = pd.date_range("2026-01-01", periods=n, freq=freq)
    recs = []
    for i in range(n):
        frac = (i % 20) / 19.0          # 锯齿，让 high/low 覆盖 [lo, hi]，ylim 包住标签
        c = lo + (hi - lo) * frac
        recs.append(dict(date=dates[i], open=c, high=c + 2, low=c - 2, close=c, volume=1000))
    return pd.DataFrame(recs).set_index("date").sort_index()


META = dict(title="T", ylabel="价格", vlabel="成交量")


print("=" * 70)
print("P2-1：render 不污染入参 levels")
print("=" * 70)
levels_in = [dict(y=120 + i, c="#c62828", txt=f"L{i} {120+i}") for i in range(8)]
fig = render(_mk(), META, levels_in, events=[], text_left="a", text_right="b",
             out="__tmp1.png", return_fig=True)
plt.close(fig)
check("P2-1 入参 levels 未被写入 ly 字段（无副作用）",
      not any("ly" in d for d in levels_in),
      f"levels_in 含 ly: {any('ly' in d for d in levels_in)}")

print()
print("=" * 70)
print("P2-2：8 条水平线标签不出界、不重叠")
print("=" * 70)
# 8 条价格挤在 100~128（区间 100~200，13%*100=13 间距放不下 8 条 → 触发梯形兜底）
lv = [dict(y=100 + 4 * i, c="#1565c0", txt=f"价{i} {100+4*i}") for i in range(8)]
fig = render(_mk(lo=100, hi=200), META, lv, events=[], text_left="a", text_right="b",
             out="__tmp2.png", return_fig=True)
ax = fig.axes[0]
lo, hi = ax.get_ylim()
anns = [c for c in ax.get_children()
        if isinstance(c, mtext.Annotation) and c.get_text().strip()
        and not getattr(c, "_ev", False)]
# 用渲染后包围盒反算标签数据坐标 y（Annotation 无公开 xytext 属性）
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
ys = []
for a in anns:
    bb = a.get_window_extent(renderer).transformed(ax.transData.inverted())
    ys.append((bb.y0 + bb.y1) / 2.0)
ys.sort()
check("P2-2 标签数=8", len(ys) == 8, f"实际 {len(ys)}")
in_bounds = all((lo + (hi - lo) * 0.005) <= y <= (hi - (hi - lo) * 0.005) for y in ys)
check("P2-2 8 标签全在 ylim 内（不再跑到图外）",
      in_bounds, f"ylim=[{lo:.1f},{hi:.1f}] ys={[round(y,1) for y in ys]}")
gap_thr = (hi - lo) * 0.005   # 视觉重叠阈值（远小于字体高度对应的数据跨度则算重叠）
no_overlap = all((ys[i + 1] - ys[i]) >= gap_thr for i in range(len(ys) - 1))
check("P2-2 8 标签两两不重叠", no_overlap,
      f"相邻间距={[round(ys[i+1]-ys[i],2) for i in range(len(ys)-1)]}")
plt.close(fig)

print()
print("=" * 70)
print("P2-3：idx_of 非交易日兜底（不崩溃）")
print("=" * 70)
df_b = _mk(n=60, freq="B")   # 仅交易日（跳过周末）
try:
    i = idx_of(df_b, "2026-01-03")   # 周六，不在 index
    check("P2-3 周末返回有效索引", isinstance(i, int) and 0 <= i < len(df_b), f"idx={i}")
except Exception as e:
    check("P2-3 周末返回有效索引", False, f"崩溃：{e}")
try:
    i0 = idx_of(df_b, "2000-01-01")   # 远早于首根 → 返回 0
    check("P2-3 早于数据返回 0", i0 == 0, f"idx={i0}")
    i1 = idx_of(df_b, "2100-01-01")   # 远晚于末根 → 返回末位
    check("P2-3 晚于数据返回末位", i1 == len(df_b) - 1, f"idx={i1}")
except Exception as e:
    check("P2-3 边界日期", False, f"崩溃：{e}")

print()
print("=" * 70)
print("P2-4：pad 自适应，n=250 右侧留白 ≥ 20%")
print("=" * 70)
df250 = _mk(n=250, lo=100, hi=200)
fig = render(df250, META, [], events=[], text_left="a", text_right="b",
             out="__tmp3.png", return_fig=True)
ax = fig.axes[0]
xlo, xhi = ax.get_xlim()
right_margin = (xhi - (len(df250) - 1)) / (xhi - xlo)   # 真实占比：右侧空白占整图 x 轴比例
check("P2-4 n=250 真实右侧留白 ≥ 20%", right_margin >= 0.20 - 1e-9, f"right_margin={right_margin:.3f}")
plt.close(fig)

print()
print(f"结果：通过 {len(PASS)} / 失败 {len(FAIL)}")
sys.exit(1 if FAIL else 0)
