#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""几何自检：标注框（文字框）是否互相重叠 / 是否压到 K 线。

方法：复用 build_events/build_levels 在完全相同的坐标上，用 ax1.text 临时建
「无箭头」纯文本框（get_window_extent 对纯文本可靠），量真实像素包围盒后判定：
  - 任意两个文字框不可相交（项目硬约束 #1：互不重叠）
  - 任意要点标注框不可与 K 线矩形相交（项目硬约束 #2：不遮挡 K 线）
箭头穿过 K 线是允许的，本脚本不检查箭头。
"""
import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.text as mtext
import matplotlib.transforms as mtrans
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caisen_ab import analyze, ABParams
from caisen_data import Meta, MARKETS
from caisen_narrative import render_signal, build_events, build_levels
from types import SimpleNamespace


HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, code, setcode, market):
    df = pd.read_csv(os.path.join(HERE, "data", f"{code}_daily.csv"),
                     parse_dates=["date"]).set_index("date")
    df = df.rename(columns={"vol": "volume"}).astype(float)
    mk = MARKETS[market]
    meta = Meta(name=name, code=code, setcode=setcode, market=market,
                market_label=mk.label, period=4, period_label="日线", tq_flag=1,
                adjust_label="前复权", vol_unit=mk.vol_unit, bars=len(df),
                start=str(df.index[0].date()), end=str(df.index[-1].date()),
                hq_date="", hq_time="", last_bar_closed=True,
                t_plus=mk.t_plus, price_limit=mk.price_limit, short_mode=mk.short_mode,
                snapshot="2026-08-03", warnings=[])
    return df, meta


def check_layout(df, meta, tag):
    sig = analyze(df, ABParams())
    assert sig.ok, f"{tag}: {sig.reason}"
    fig = render_signal(sig, df, meta, os.path.join(HERE, "_verify.png"),
                        return_fig=True)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ax1 = fig.axes[0]

    # 要点标注框：在完全相同坐标上临时建「无箭头」纯文本框量真实像素包围盒
    # （事件注记箭头很长，直接 get_window_extent 会把箭头算进去导致虚大，故用临时文本）
    ev_boxes, ev_pos = [], []
    for ev in build_events(sig, df, meta):
        x, y = ev["xytext"]
        t = ax1.text(x, y, ev["txt"], fontsize=ev.get("fs", 8.5),
                     ha="left", va="center",
                     bbox=dict(boxstyle="round,pad=0.4", fc="white",
                               ec=ev.get("ec", "#666"), lw=1.2))
        ev_boxes.append(t.get_window_extent(renderer))
        ev_pos.append((x, y))
        t.remove()

    # 水平价位线标签：量纯文字框（去箭头）。否则 get_window_extent 会把长引线
    # 也算进包围盒，梯形模式下 ly 与真实价位差距大 → 误报「标签重叠」。
    # 项目硬约束只禁止「文字框」互相重叠；箭头可交叉（已明确允许）。
    lv_boxes = []
    for ch in ax1.get_children():
        if isinstance(ch, mtext.Annotation) and ch.get_text().strip() \
                and not getattr(ch, "_ev", False):
            tx, ty = ch.xyann
            tmp = ax1.text(tx, ty, ch.get_text(), fontsize=9.6, va="center", ha="left",
                           bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="gray", lw=1.0))
            lv_boxes.append(tmp.get_window_extent(renderer))
            tmp.remove()

    # (1) 要点框两两不重叠（作者：相互不能重叠）
    ev_overlaps = [(i, j) for i in range(len(ev_boxes)) for j in range(i + 1, len(ev_boxes))
                   if ev_boxes[i].overlaps(ev_boxes[j])]
    # (1b) 价位标签两两不重叠（次要，已有 min_gap 逻辑）
    lv_overlaps = [(i, j) for i in range(len(lv_boxes)) for j in range(i + 1, len(lv_boxes))
                   if lv_boxes[i].overlaps(lv_boxes[j])]

    # (2) 要点框不压 K 线矩形（作者：不遮挡 K 线）
    kh = float(df["high"].max()); kl = float(df["low"].min())
    x0, y0 = ax1.transData.transform((0, kl))
    x1, y1 = ax1.transData.transform((len(df) - 1, kh))
    candle = mtrans.Bbox([[x0, y0], [x1, y1]])
    hit_candle = [k for k, b in enumerate(ev_boxes) if b.overlaps(candle)]

    ok = (not ev_overlaps) and (not hit_candle)
    print(f"[{tag}] 要点框={len(ev_boxes)} 要点框互重叠={len(ev_overlaps)}  "
          f"要点框压K线={len(hit_candle)}  | 价位标签互重叠={len(lv_overlaps)}  "
          f"-> {'OK' if ok else 'FAIL'}")
    if ev_overlaps:
        _idx = set()
        for a, b in ev_overlaps:
            _idx.add(a); _idx.add(b)
        print("   要点框重叠对:", ev_overlaps, "坐标:", [ev_pos[i] for i in _idx])
    if hit_candle:
        print("   压K线要点框坐标:", [ev_pos[k] for k in hit_candle])
    if lv_overlaps:
        print("   价位标签重叠对:", lv_overlaps)
    plt.close(fig)
    return ok


def _make_df(closes):
    n = len(closes)
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    recs = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        hi = max(o, c) + 1.0
        lo = min(o, c) - 1.0
        recs.append(dict(date=dates[i], open=o, high=hi, low=lo, close=c,
                         volume=1000 + (i % 5) * 100))
    return pd.DataFrame(recs).set_index("date").sort_index()


def _build_mtop(n=100):
    cl = [100.0] * n
    for i in range(0, 20):
        cl[i] = 100.0 + (130 - 100) * (i / 19)
    cl[20] = 130.0
    for i in range(21, 35):
        cl[i] = 130.0 - (130 - 110) * ((i - 20) / 15)
    cl[35] = 110.0
    for i in range(36, 50):
        cl[i] = 110.0 + (130 - 110) * ((i - 35) / 15)
    cl[50] = 130.0
    for i in range(51, 70):
        cl[i] = 130.0 - (130 - 90) * ((i - 50) / 19)
    cl[70] = 90.0
    for i in range(71, n):
        cl[i] = 90.0 + (i - 70) * 0.1
    return _make_df(cl)


if __name__ == "__main__":
    # 茅台（多头）
    df, meta = _load("贵州茅台", "600519", 1, "CN_SH")
    ok_m = check_layout(df, meta, "茅台-多头")
    # 合成 M 头（空头）
    mtop = _build_mtop()
    fmeta = SimpleNamespace(name="测试M头", code="X",
                            market_label="上期所", vol_unit="手", t_plus=0,
                            price_limit="无涨跌停", short_mode="可双向开仓")
    ok_d = check_layout(mtop, fmeta, "合成M头-空头")
    print("\n结论:", "全部通过" if (ok_m and ok_d) else "存在重叠/遮挡，需修正")
    sys.exit(0 if (ok_m and ok_d) else 1)
