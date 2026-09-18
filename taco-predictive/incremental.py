#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TACO 增量信息检验
==================
问题：TACO 有 50% 权重来自市场价格（其中标普 17.5%），
      那么「TACO 高 → 未来风险资产修复」到底是 TACO 的功劳，
      还是「标普跌了 → 标普反弹」这个众所周知的短期反转效应换了个皮？

做法：找出与 TACO 高压区「同样时点、同样触发频率」的机械基准信号（标普自身回撤），
      逐个事件日对比前瞻表现。若 TACO 版不优于机械版 → 无增量信息。

另做样本聚集检验：TACO ≥8 的日子落在几个独立事件簇里？
      若只有 1~2 簇，所谓「胜率 90%」其实是「某一轮行情」。
"""
import os
import re
import csv
import json
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(os.path.dirname(HERE), "ocmacro-feed", "data", "2026-09-12")
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
FACTORS = ["approval", "dgs10", "move", "sp500", "vix", "bkevenpy02"]
MARKET_FACTORS = ["dgs10", "move", "sp500", "vix"]
NONMARKET_FACTORS = ["approval", "bkevenpy02"]


def load_taco():
    rows = list(csv.DictReader(open(f"{SNAP}/taco_index_history.csv", encoding="utf-8-sig")))
    o = {"dates": [r["date"] for r in rows], "value": [float(r["value"]) for r in rows],
         "contrib": {k: [float(r[f"contributions.{k}"]) for r in rows] for k in FACTORS}}
    n = len(o["dates"])
    o["mkt"] = [sum(o["contrib"][k][i] for k in MARKET_FACTORS) for i in range(n)]
    o["nonmkt"] = [sum(o["contrib"][k][i] for k in NONMARKET_FACTORS) for i in range(n)]
    return o


def load_fred(fn):
    p = os.path.join(HERE, "data", fn)
    d = {}
    for line in open(p, encoding="utf-8-sig"):
        parts = line.strip().split(",")
        if len(parts) < 2:
            continue
        m = DATE_RE.match(parts[0].strip())
        if not m or parts[1].strip() in (".", "", "NA"):
            continue
        try:
            d[parts[0].strip()] = float(parts[1])
        except ValueError:
            pass
    return d


def align(taco_dates, series):
    out, last = [], None
    for d in taco_dates:
        if d in series:
            last = series[d]
        out.append(last)
    return out


def episodes(idxs, dates, gap=10):
    """把索引按间隔 > gap 拆成独立事件簇。"""
    if not idxs:
        return []
    eps, cur = [], [idxs[0]]
    for a, b in zip(idxs, idxs[1:]):
        if b - a > gap:
            eps.append(cur)
            cur = [b]
        else:
            cur.append(b)
    eps.append(cur)
    return eps


def main():
    taco = load_taco()
    dates, vals = taco["dates"], taco["value"]
    n = len(dates)
    sp = align(dates, load_fred("fred_SP500.csv"))
    vx = align(dates, load_fred("fred_VIXCLS.csv"))
    print("=" * 96)
    print("A  样本聚集检验：TACO ≥ 8 的日子落在几个独立事件簇里？")
    print("=" * 96)
    hi = [i for i in range(n) if vals[i] >= 8]
    eps = episodes(hi, dates)
    print(f"  TACO ≥ 8 共 {len(hi)} 个交易日，拆成 {len(eps)} 个独立簇（间隔 >10 个交易日即视为新簇）：\n")
    print(f"    {'簇':>3}  {'起':<12}{'止':<12}{'天数':>5}  {'簇内均值':>9}  "
          f"{'起点后20日标普':>15}{'起点后60日标普':>15}")
    for k, e in enumerate(eps, 1):
        a, b = e[0], e[-1]
        m = st.mean([vals[i] for i in e])
        f20 = (sp[min(a + 20, n - 1)] / sp[a] - 1) * 100 if sp[a] and a + 20 < n else None
        f60 = (sp[min(a + 60, n - 1)] / sp[a] - 1) * 100 if sp[a] and a + 60 < n else None
        print(f"    {k:>3}  {dates[a]:<12}{dates[b]:<12}{len(e):>5}  {m:>+9.2f}  "
              f"{(('%+.2f%%' % f20) if f20 is not None else 'n/a'):>15}"
              f"{(('%+.2f%%' % f60) if f60 is not None else 'n/a'):>15}")
    print()
    # 逐簇前瞻收益的分布
    per_ep = []
    for e in eps:
        a = e[0]
        f = [None if (sp[i] is None or sp[i + 20] is None) else (sp[i + 20] / sp[i] - 1) * 100
             for i in e if i + 20 < n]
        f = [x for x in f if x is not None]
        if f:
            per_ep.append((dates[a], st.mean(f), len(f)))
    if per_ep:
        print("  各簇内部平均「后20日标普收益」：")
        for d, m, c in per_ep:
            print(f"    {d}  {m:+.2f}%   n={c}")
        pos = sum(1 for _, m, _ in per_ep if m > 0)
        print(f"\n  → {pos}/{len(per_ep)} 个簇为正。若因簇数过少而「全正」，"
              f"则该结论等价于「这几轮行情恰好都涨」，样本量不支持统计推断。")
    print()

    print("=" * 96)
    print("B  增量信息检验：TACO ≥ 8  vs  标普自身回撤（机械基准，匹配触发频率）")
    print("=" * 96)
    # 统一可比区间：两边都必须 i>=20（能算出过去20日标普）且 i+60<n（能算出后60日）
    LO, HI = 20, n - 60
    univ = list(range(LO, HI))
    sig_taco = [i for i in univ if vals[i] >= 8]
    sp20 = {i: (sp[i] / sp[i - 20] - 1) * 100 for i in univ if sp[i] and sp[i - 20]}
    target_k = len(sig_taco)
    cand_sorted = sorted([i for i in univ if i in sp20], key=lambda i: sp20[i])
    sig_sp = set(cand_sorted[:target_k])
    print(f"  可比区间：{dates[LO]} ~ {dates[HI-1]}（{len(univ)} 天，两端各留出 20/60 日窗口）")
    print(f"  TACO ≥ 8 触发日：{target_k} 天")
    print(f"  机械基准：标普过去20日跌幅最大的同样 {len(sig_sp)} 天")
    print(f"    机械基准的跌幅门槛：标普20日收益 ≤ {max(sp20[i] for i in sig_sp):+.2f}%"
          f"；TACO 组同日该值为中位 {st.median([sp20[i] for i in sig_taco if i in sp20]):+.2f}%\n")

    def fwd(v, i, h, price=True):
        if i + h >= n or v[i] is None or v[i + h] is None or v[i] == 0:
            return None
        return (v[i + h] / v[i] - 1) * 100 if price else v[i + h] - v[i]

    print(f"    {'信号':<22}{'样本':>6}{'后20日标普':>12}{'胜率':>8}"
          f"{'后20日VIX':>12}{'后60日标普':>12}{'后20日TACO变化':>15}")
    for lab, s in [("TACO ≥ 8", sig_taco), ("标普跌最多（机械）", sorted(sig_sp)),
                   ("全区间基准", univ)]:
        a = [fwd(sp, i, 20) for i in s]; a = [x for x in a if x is not None]
        b = [fwd(vx, i, 20, False) for i in s]; b = [x for x in b if x is not None]
        c = [fwd(sp, i, 60) for i in s]; c = [x for x in c if x is not None]
        d = [vals[i + 20] - vals[i] for i in s]
        print(f"    {lab:<22}{len(s):>6}{st.mean(a):>+11.2f}%"
              f"{sum(1 for x in a if x > 0)/len(a)*100:>7.0f}%"
              f"{st.mean(b):>+12.2f}{st.mean(c):>+11.2f}%{st.mean(d):>+15.2f}")
    print()
    ov = len(set(sig_taco) & sig_sp)
    print(f"  两者重叠 {ov} 天 / 各 {target_k} 天 → 重合度 {ov/max(1,target_k)*100:.0f}%")
    print(f"  （重合度越高，说明 TACO 高压区越接近「标普刚跌过」，增量信息越少）")
    print()
    only_taco = sorted(set(sig_taco) - sig_sp)
    both = sorted(set(sig_taco) & sig_sp)
    print(f"  拆开看：")
    for lab, s in [("TACO≥8 但标普未大跌（独家）", only_taco),
                   ("TACO≥8 且标普大跌（共同）", both)]:
        if len(s) < 3:
            print(f"    {lab:<28} n={len(s)}（样本过少）")
            continue
        a = [fwd(sp, i, 20) for i in s]; a = [x for x in a if x is not None]
        c = [fwd(sp, i, 60) for i in s]; c = [x for x in c if x is not None]
        d = [vals[i + 20] - vals[i] for i in s]
        print(f"    {lab:<28} n={len(s):>3}  后20日标普 {st.mean(a):+.2f}%"
              f"  胜率 {sum(1 for x in a if x > 0)/len(a)*100:.0f}%"
              f"  后60日 {(st.mean(c) if c else float('nan')):+.2f}%"
              f"  后20日TACO变化 {st.mean(d):+.2f}"
              f"  过去20日标普 {st.mean([sp20[i] for i in s if i in sp20]):+.2f}%")
    print()
    # 决定性检验：TACO 是否只是「过去20日标普」的代理？比较两者对未来收益的相关
    print("  决定性检验：谁对未来20日标普更有解释力？")
    pp = [(vals[i], sp20[i], fwd(sp, i, 20)) for i in univ if i in sp20 and fwd(sp, i, 20) is not None]
    import math
    def pr(xs, ys):
        mx, my = st.mean(xs), st.mean(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        dx = sum((x - mx) ** 2 for x in xs) ** 0.5
        dy = sum((y - my) ** 2 for y in ys) ** 0.5
        return num / (dx * dy) if dx and dy else 0
    t_, s20_, f_ = [x[0] for x in pp], [x[1] for x in pp], [x[2] for x in pp]
    print(f"    相关系数 corr(TACO,      未来20日标普) = {pr(t_, f_):+.3f}")
    print(f"    相关系数 corr(过去20日标普, 未来20日标普) = {pr(s20_, f_):+.3f}")
    print(f"    相关系数 corr(TACO, 过去20日标普)         = {pr(t_, s20_):+.3f}")
    # 偏相关：控制「过去20日标普」后，TACO 还剩多少解释力
    rtf, rsf, rts = pr(t_, f_), pr(s20_, f_), pr(t_, s20_)
    den = ((1 - rts ** 2) * (1 - rsf ** 2)) ** 0.5
    pcorr = (rtf - rts * rsf) / den if den else 0
    print(f"    → 控制「过去20日标普」后的偏相关 corr(TACO, 未来20日标普 | 过去20日标普)"
          f" = {pcorr:+.3f}")
    print(f"    → 偏相关绝对值 <0.15 即视为基本无增量信息（TACO 只是标普回撤的代理）")
    print()

    print("=" * 96)
    print("C  非市场部分单独检验（支持率 + 通胀nowcast，权重合计 50%，与市场价格独立）")
    print("=" * 96)
    nm = taco["nonmkt"]
    print(f"  非市场部分的分位阈值与对应前瞻表现（未来20日标普 / VIX）：")
    qs = [50, 70, 80, 90]
    print(f"    {'分位门槛':<10}{'对应值':>9}{'样本':>6}{'后20日标普':>12}{'胜率':>8}"
          f"{'后20日VIX':>12}{'后20日TACO变化':>15}")
    for q in qs:
        sv = sorted(nm)
        th = sv[int(len(sv) * q / 100)]
        s = [i for i in range(n - 60) if nm[i] >= th]
        a = [fwd(sp, i, 20) for i in s]; a = [x for x in a if x is not None]
        b = [fwd(vx, i, 20, False) for i in s]; b = [x for x in b if x is not None]
        d = [vals[i + 20] - vals[i] for i in s]
        print(f"    {q}% 分位{'':<3}{th:>+9.2f}{len(s):>6}{st.mean(a):>+11.2f}%"
              f"{sum(1 for x in a if x > 0)/len(a)*100:>7.0f}%"
              f"{st.mean(b):>+12.2f}{st.mean(d):>+15.2f}")
    print()
    # 非市场部分高位日也做聚集检验
    sv = sorted(nm); th = sv[int(len(sv) * 0.8)]
    hh = [i for i in range(n) if nm[i] >= th]
    e2 = episodes(hh, dates)
    print(f"  非市场部分 ≥ 80 分位（{th:+.2f}）共 {len(hh)} 天，落在 {len(e2)} 个簇里：")
    for k, e in enumerate(e2, 1):
        print(f"    {k}. {dates[e[0]]} ~ {dates[e[-1]]}  {len(e)} 天")
    print()

    print("=" * 96)
    print("D  当前高压区（TACO ≥ 8，共 %d 天）的完整明细" % len(hi))
    print("=" * 96)
    print(f"    {'日期':<12}{'TACO':>7}{'市场部分':>9}{'非市场':>8}"
          f"{'过去20日标普':>13}{'后20日标普':>12}{'后60日标普':>12}")
    for i in hi:
        b20 = (sp[i] / sp[i - 20] - 1) * 100 if i >= 20 and sp[i] and sp[i - 20] else None
        f20 = (sp[i + 20] / sp[i] - 1) * 100 if i + 20 < n and sp[i] and sp[i + 20] else None
        f60 = (sp[i + 60] / sp[i] - 1) * 100 if i + 60 < n and sp[i] and sp[i + 60] else None
        print(f"    {dates[i]:<12}{vals[i]:>+7.2f}{taco['mkt'][i]:>+9.2f}{nm[i]:>+8.2f}"
              f"{(('%+.2f%%' % b20) if b20 is not None else 'n/a'):>13}"
              f"{(('%+.2f%%' % f20) if f20 is not None else 'n/a'):>12}"
              f"{(('%+.2f%%' % f60) if f60 is not None else 'n/a'):>12}")
    print()


if __name__ == "__main__":
    main()
