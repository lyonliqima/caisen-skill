#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TACO 前瞻能力的稳健性边界
==========================
1) 分段检验：把 366 个交易日切成两半，信号是否两段都成立。
2) 事件聚集：19 个重大回撤事件的独立簇数 —— 决定「事件预测」是否可信。
3) 基准对照：样本期内各资产的漂移（防止把牛市/熊市背景当成信号）。
4) 随机化检验：把 TACO 序列打乱（保持自相关结构用块置换），
   看「≥8 → 前瞻表现」有多少来自巧合。
"""
import os
import re
import csv
import json
import random
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(os.path.dirname(HERE), "ocmacro-feed", "data", "2026-09-12")
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
MIN_STRENGTH = ("强", "最强", "中强")


def load_taco():
    rows = list(csv.DictReader(open(f"{SNAP}/taco_index_history.csv", encoding="utf-8-sig")))
    return {"dates": [r["date"] for r in rows], "value": [float(r["value"]) for r in rows]}


def load_fred(fn):
    d = {}
    for line in open(os.path.join(HERE, "data", fn), encoding="utf-8-sig"):
        p = line.strip().split(",")
        if len(p) < 2 or not DATE_RE.match(p[0].strip()) or p[1].strip() in (".", "", "NA"):
            continue
        try:
            d[p[0].strip()] = float(p[1])
        except ValueError:
            pass
    return d


def align(dates, s):
    out, last = [], None
    for d in dates:
        if d in s:
            last = s[d]
        out.append(last)
    return out


def rollback_date(period):
    ts = DATE_RE.findall(period or "")
    return max(f"{a}-{b}-{c}" for a, b, c in ts) if ts else None


def snap(t, dates):
    c = [d for d in dates if d <= t]
    return c[-1] if c else None


def event_days(dates):
    ev = json.load(open(f"{SNAP}/taco_events.json", encoding="utf-8"))
    s = set()
    for e in ev:
        if e.get("strength") not in MIN_STRENGTH:
            continue
        d = rollback_date(e.get("period"))
        t = snap(d, dates) if d else None
        if t:
            s.add(t)
    return s


def clusters(idxs, gap=10):
    if not idxs:
        return []
    idxs = sorted(idxs)
    out, cur = [], [idxs[0]]
    for a, b in zip(idxs, idxs[1:]):
        if b - a > gap:
            out.append(cur)
            cur = [b]
        else:
            cur.append(b)
    out.append(cur)
    return out


def main():
    taco = load_taco()
    dates, vals = taco["dates"], taco["value"]
    n = len(dates)
    sp = align(dates, load_fred("fred_SP500.csv"))
    vx = align(dates, load_fred("fred_VIXCLS.csv"))
    hs = align(dates, load_fred("cn_sh000300.csv"))

    print("=" * 96)
    print("1  样本背景：各资产在 TACO 数据窗口内的漂移")
    print("=" * 96)
    print(f"  窗口 {dates[0]} → {dates[-1]}（{n} 个交易日）")
    for lab, v in [("标普500", sp), ("VIX", vx), ("沪深300", hs)]:
        a, b = v[0], v[-1]
        if a and b:
            print(f"    {lab:<10} {a:>9.2f} → {b:>9.2f}   {(b/a-1)*100:+7.2f}%"
                  f"   （年化 ≈ {((b/a)**(252/n)-1)*100:+.1f}%）")
    # 未来20日基准上涨占比
    for lab, v in [("标普500", sp), ("沪深300", hs)]:
        fc = [(v[i + 20] / v[i] - 1) * 100 for i in range(n - 20) if v[i] and v[i + 20]]
        print(f"    未来20日 {lab:<8} 上涨占比 {sum(1 for x in fc if x > 0)/len(fc)*100:.0f}%"
              f"  均值 {st.mean(fc):+.2f}%  → 这是「什么都不看」的基准")
    print()

    print("=" * 96)
    print("2  分段稳健性：信号是否两段都成立")
    print("=" * 96)
    mid = next(i for i, d in enumerate(dates) if d >= "2026-01-01")
    for k, (a, b) in enumerate([(0, mid), (mid, n)], 1):
        dseg, vseg = dates[a:b], vals[a:b]
        seg_n = len(vseg)
        hi = [i for i in range(seg_n) if vseg[i] >= 8]
        eps = clusters(hi, 10)
        print(f"  第{k}段 {dseg[0]} ~ {dseg[-1]}（{seg_n} 日）")
        if not hi:
            print(f"    TACO ≥ 8：0 天 → 该段无法检验\n")
            continue
        f20 = [(sp[a + i + 20] / sp[a + i] - 1) * 100 for i in hi
               if a + i + 20 < n and sp[a + i] and sp[a + i + 20]]
        base = [(sp[a + i + 20] / sp[a + i] - 1) * 100 for i in range(seg_n - 20)
                if a + i + 20 < n and sp[a + i] and sp[a + i + 20]]
        print(f"    TACO ≥ 8：{len(hi)} 天，{len(eps)} 个独立簇")
        if f20:
            print(f"      后20日标普：{st.mean(f20):+.2f}%  胜率 "
                  f"{sum(1 for x in f20 if x > 0)/len(f20)*100:.0f}%"
                  f"   |  该段基准 {st.mean(base):+.2f}%"
                  f"   → 超额 {st.mean(f20)-st.mean(base):+.2f}pp")
        print()
    print()

    print("=" * 96)
    print("3  事件聚集：19 个重大回撤事件分几簇？")
    print("=" * 96)
    evd = event_days(dates)
    idxmap = {d: i for i, d in enumerate(dates)}
    eidx = sorted(idxmap[d] for d in evd if d in idxmap)
    print(f"  事件日（映射到交易日）共 {len(eidx)} 个：")
    print("    " + ", ".join(dates[i] for i in eidx))
    for gap in [10, 20]:
        e = clusters(eidx, gap)
        print(f"  按间隔 >{gap} 交易日分簇 → {len(e)} 簇：")
        for k, c in enumerate(e, 1):
            print(f"    {k:>2}. {dates[c[0]]} ~ {dates[c[-1]]}  {len(c)} 个事件日")
    print()
    print("  ⚠️ 若独立簇数远小于事件数，那么「事件预测率 90%」的分子虽大、分母却是少数几轮政策周期，")
    print("     不具备统计推断所需的独立性。")
    print()

    print("=" * 96)
    print("4  随机化检验：把 TACO 序列做块置换，看 ≥8 的信号有多容易偶然出现")
    print("=" * 96)
    N_SIM = 2000
    random.seed(20260912)
    blk = 20
    f20_all = [None] * n
    for i in range(n - 20):
        if sp[i] and sp[i + 20]:
            f20_all[i] = (sp[i + 20] / sp[i] - 1) * 100
    k_real = sum(1 for i in range(n - 20) if vals[i] >= 8)
    obs = st.mean([f20_all[i] for i in range(n - 20) if vals[i] >= 8 and f20_all[i] is not None])
    obs_hit = sum(1 for i in range(n - 20) if vals[i] >= 8 and f20_all[i] is not None
                  and f20_all[i] > 0) / k_real * 100
    sims = []
    for _ in range(N_SIM):
        # 块置换：把序列切成 20 日块后打乱顺序，保留块内自相关
        blocks = [vals[i:i + blk] for i in range(0, n, blk)]
        random.shuffle(blocks)
        perm = [x for b in blocks for x in b][:n]
        s = [f20_all[i] for i in range(n - 20) if perm[i] >= 8 and f20_all[i] is not None]
        if len(s) >= 5:
            sims.append(st.mean(s))
    sims.sort()
    if sims:
        better = sum(1 for x in sims if x >= obs) / len(sims) * 100
        lo, hi_ = sims[int(len(sims) * 0.05)], sims[int(len(sims) * 0.95)]
        print(f"  实测：TACO ≥ 8 的 {k_real} 天，后20日标普均值 {obs:+.2f}%，胜率 {obs_hit:.0f}%")
        print(f"  块置换模拟 {len(sims)} 次（块长 20 日）：均值分布 {lo:+.2f}% ~ {hi_:+.2f}%，"
              f"中位 {st.median(sims):+.2f}%")
        print(f"  → 置换后有 {better:.1f}% 的随机序列表现不劣于实测")
        print(f"  → 这意味着：在样本期这种单边上涨背景里，"
              f"{'信号很难用巧合解释' if better < 5 else '「高压后上涨」很大程度上可以用随机性+市场漂移解释'}")
    print()


if __name__ == "__main__":
    main()
