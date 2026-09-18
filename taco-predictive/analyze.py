#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TACO 指数前瞻能力正面检验
==========================
回答一个问题：TACO 到底能预测什么、能预测多远、预测力从哪来。

数据源：
  - TACO 序列 + 30 条政策回撤事件：ocmacro-feed/data/<日期>/（本地快照）
  - 美国市场：FRED 免费 CSV 出口（fredgraph.csv，无密钥）
  - 10Y 收益率的官方原始口径：U.S. Treasury daily yield curve CSV
  - 中国资产：腾讯自选股 westock（已落 data/cn_*.csv）

方法学要点：
  1. 严格用 t 时点可知信息，前瞻窗口不越界。
  2. TACO 的六个因子中 dgs10/sp500/move/vix 本身就是市场价格（权重合计 50%），
     所以必须把它拆成「市场因子部分」与「非市场部分（支持率 + 通胀nowcast）」
     分别检验 —— 否则会把市场自身的均值回归误读成 TACO 的预测力。
  3. 事件日一律用「回撤日」（period 的最后一个日期）并映射到交易日。
"""
import csv
import json
import os
import re
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SNAP = os.path.join(os.path.dirname(HERE), "ocmacro-feed", "data", "2026-09-12")

MIN_STRENGTH = ("强", "最强", "中强")
DATE_RE = re.compile(r"(\d{4})[-/](\d{2})[-/](\d{2})")

FACTORS = ["approval", "dgs10", "move", "sp500", "vix", "bkevenpy02"]
MARKET_FACTORS = ["dgs10", "move", "sp500", "vix"]      # 就是市场价格，权重合计 50%
NONMARKET_FACTORS = ["approval", "bkevenpy02"]          # 支持率 + 通胀nowcast，权重合计 50%


# --------------------------------------------------------------------------- 载入
def load_taco():
    rows = list(csv.DictReader(open(f"{SNAP}/taco_index_history.csv", encoding="utf-8-sig")))
    out = {"dates": [], "value": [], "contrib": {k: [] for k in FACTORS}}
    for r in rows:
        out["dates"].append(r["date"])
        out["value"].append(float(r["value"]))
        for k in FACTORS:
            out["contrib"][k].append(float(r[f"contributions.{k}"]))
    # 市场部分 / 非市场部分（按 2026-09-11 的 targetScaleWeights 还原权重）
    w = json.load(open(f"{SNAP}/trump_dashboard.json", encoding="utf-8"))["taco"]["normalization"]["targetScaleWeights"]
    n = len(out["dates"])
    out["mkt"] = [sum(out["contrib"][k][i] for k in MARKET_FACTORS) for i in range(n)]
    out["nonmkt"] = [sum(out["contrib"][k][i] for k in NONMARKET_FACTORS) for i in range(n)]
    out["weights"] = w
    return out


def _fred(path, scale=1.0):
    """FRED/treasury CSV → {date: value}，自动跳过 '.' 缺失值。"""
    if not os.path.exists(path):
        return {}
    d = {}
    for line in open(path, encoding="utf-8-sig"):
        parts = line.strip().split(",")
        if len(parts) < 2:
            continue
        k, v = parts[0].strip(), parts[1].strip()
        m = DATE_RE.match(k)
        if not m:
            continue
        if m.group(1) and len(m.group(1)) == 4:
            iso = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        else:  # 美国格式 MM/DD/YYYY
            iso = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
        if v in (".", "", "NA"):
            continue
        try:
            d[iso] = float(v) * scale
        except ValueError:
            continue
    return d


def load_market():
    mk = {}
    for name, fn, sc in [
        ("sp500", "fred_SP500.csv", 1.0),
        ("vix", "fred_VIXCLS.csv", 1.0),
        ("dgs10", "fred_DGS10.csv", 1.0),
        ("dgs2", "fred_DGS2.csv", 1.0),
        ("real10", "fred_DFII10.csv", 1.0),
        ("breakeven", "fred_T10YIE.csv", 1.0),
        ("dxy", "fred_DTWEXBGS.csv", 1.0),
        ("oil", "fred_DCOILWTICO.csv", 1.0),
        ("hy", "fred_BAMLH0A0HYM2.csv", 1.0),
        ("nfci", "fred_NFCI.csv", 1.0),
        ("hs300", "cn_sh000300.csv", 1.0),
        ("sse", "cn_sh000001.csv", 1.0),
        ("chinext", "cn_sz399006.csv", 1.0),
    ]:
        mk[name] = _fred(os.path.join(DATA, fn))
    return mk


def align(taco_dates, series):
    """把某个市场序列对齐到 TACO 交易日：缺失取上一个已知值（前向填充，无未来信息）。"""
    out, last = [], None
    for d in taco_dates:
        if d in series:
            last = series[d]
        out.append(last)
    return out


def fwd_change(vals, h):
    """t → t+h 的变化（价格序列用百分比，利率/利差用绝对 bp/百分数单位由调用方决定）。"""
    n = len(vals)
    out = [None] * n
    for i in range(n - h):
        if vals[i] is not None and vals[i + h] is not None:
            out[i] = vals[i + h] - vals[i]
    return out


# --------------------------------------------------------------------------- 事件
def rollback_date(period):
    ts = DATE_RE.findall(period or "")
    if not ts:
        return None
    return max(f"{a}-{b}-{c}" for a, b, c in ts)


def snap_to_trading(target, dates):
    c = [d for d in dates if d <= target]
    return c[-1] if c else None


def event_days(dates):
    ev = json.load(open(f"{SNAP}/taco_events.json", encoding="utf-8"))
    s = {}
    for e in ev:
        if e.get("strength") not in MIN_STRENGTH:
            continue
        d = rollback_date(e.get("period"))
        if not d:
            continue
        t = snap_to_trading(d, dates)
        if t:
            s.setdefault(t, []).append(e.get("topic"))
    return s


# --------------------------------------------------------------------------- 统计工具
def pct_rank(vals, x):
    v = [y for y in vals if y is not None]
    if not v:
        return None
    return sum(1 for y in v if y <= x) / len(v) * 100


def corr(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 20:
        return None
    xs, ys = zip(*pairs)
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else None


def rank_ic(sig, fwd):
    """Spearman 秩相关，抗异常值。"""
    pairs = [(i, sig[i], fwd[i]) for i in range(len(sig))
             if sig[i] is not None and fwd[i] is not None]
    if len(pairs) < 20:
        return None
    def rk(vs):
        order = sorted(range(len(vs)), key=lambda k: vs[k])
        r = [0.0] * len(vs)
        for pos, k in enumerate(order):
            r[k] = pos + 1
        return r
    a = rk([p[1] for p in pairs])
    b = rk([p[2] for p in pairs])
    return corr(a, b)


def mean_of(xs):
    v = [x for x in xs if x is not None]
    return st.mean(v) if v else None


# --------------------------------------------------------------------------- T1 领先性
def t1_leadership(taco, evd):
    dates, vals = taco["dates"], taco["value"]
    n = len(dates)
    idx = {d: i for i, d in enumerate(dates)}
    print("=" * 92)
    print("T1  领先性检验：政策回撤事件前后的 TACO 路径（事件日 = 回撤日）")
    print("=" * 92)
    lags = list(range(-40, 21, 5))
    print(f"{'相对事件日':>10}", end="")
    for L in lags:
        print(f"{L:>8}", end="")
    print("   n")
    rows = {}
    for strn, sel in [("最强+强", ("最强", "强")), ("中强", ("中强",))]:
        ev = json.load(open(f"{SNAP}/taco_events.json", encoding="utf-8"))
        ds = []
        for e in ev:
            if e.get("strength") not in sel:
                continue
            d = rollback_date(e.get("period"))
            t = snap_to_trading(d, dates) if d else None
            if t and t in idx:
                ds.append(idx[t])
        if not ds:
            continue
        print(f"{strn:>10}", end="")
        for L in lags:
            sub = [pct_rank(vals, vals[i + L]) for i in ds if 0 <= i + L < n]
            print(f"{st.mean(sub):>7.0f}%", end="")
        print(f"   {len(ds)}")
        rows[strn] = ds
    # 全样本对照
    print(f"{'全样本':>10}", end="")
    print(f"{'—':>8}" * len(lags), end="")
    print(f"   {n}")
    print()
    print("读法：百分位越高＝当日 TACO 在 366 日样本中越靠前。")
    print("若事件日前路径持续抬升 → 领先指标；若平走而事件日／之后才抬高 → 同步或滞后。")
    print()
    # 事件前后均值差
    ev = json.load(open(f"{SNAP}/taco_events.json", encoding="utf-8"))
    allidx = []
    for e in ev:
        if e.get("strength") not in MIN_STRENGTH:
            continue
        d = rollback_date(e.get("period"))
        t = snap_to_trading(d, dates) if d else None
        if t and t in idx:
            allidx.append(idx[t])
    def _seg(rng):
        out = []
        for i in allidx:
            w = [vals[i + L] for L in rng if 0 <= i + L < n]
            if w:
                out.append(st.mean(w))
        return out
    pre60, pre, day, post = _seg(range(-60, -20)), _seg(range(-20, 0)), [vals[i] for i in allidx], _seg(range(1, 21))
    post40 = _seg(range(21, 41))
    for lab, seg in [("事件前 60~21 日", pre60), ("事件前 20~1 日", pre),
                     ("事件日", day), ("事件后 1~20 日", post), ("事件后 21~40 日", post40)]:
        if not seg:
            continue
        m = st.mean(seg)
        print(f"  {lab:<16} TACO 均值 {m:+6.2f}（分位 {pct_rank(vals, m):>3.0f}）"
              f"  逐事件中位 {st.median(seg):+5.2f}  n={len(seg)}")
    # 显著性：事件前 20 日均值 vs 全样本分布 —— 有多少比例的随机 20 日窗口低于它
    if pre:
        mpre = st.mean(pre)
        windows = [st.mean(vals[i:i + 20]) for i in range(0, n - 20)]
        hits = sum(1 for wv in windows if wv <= mpre) / len(windows) * 100
        print(f"\n  随机抽 20 个连续交易日，其均值低于「事件前 20 日均值 {mpre:+.2f}」的比例：{hits:.0f}%")
        print(f"  → 若接近 50%，说明事件前 TACO 并不异常，领先性不成立。")
    print()
    # 事件日 TACO 分档分布
    print("  事件日 TACO 值分布：", end="")
    buckets = {"<0": 0, "0~4": 0, "4~8": 0, "8~12": 0, "≥12": 0}
    for v in day:
        if v < 0: buckets["<0"] += 1
        elif v < 4: buckets["0~4"] += 1
        elif v < 8: buckets["4~8"] += 1
        elif v < 12: buckets["8~12"] += 1
        else: buckets["≥12"] += 1
    print("  ".join(f"{k}:{v}" for k, v in buckets.items()))
    print()
    return allidx


# --------------------------------------------------------------------------- T2 前瞻预测
def t2_forward(taco, mk):
    dates = taco["dates"]
    n = len(dates)
    print("=" * 92)
    print("T2  TACO 对未来的预测力（秩相关 IC，正=同向，负=反向）")
    print("=" * 92)
    aligned = {}
    for k, s in mk.items():
        aligned[k] = align(dates, s)
    horis = [5, 10, 20, 60]
    sigs = {"TACO 水平": taco["value"],
            "TACO 20日变化": [taco["value"][i] - taco["value"][i - 20] if i >= 20 else None for i in range(n)],
            "市场因子部分": taco["mkt"],
            "非市场部分": taco["nonmkt"]}
    targets = [("sp500", "标普500", True), ("vix", "VIX", False), ("dgs10", "10Y收益率", False),
               ("dxy", "美元指数", True), ("oil", "WTI原油", True), ("hy", "高收益利差", False),
               ("hs300", "沪深300", True)]
    for tname, tlab, is_price in targets:
        v = aligned[tname]
        if not any(v):
            print(f"\n  [{tlab}] 无数据，跳过")
            continue
        print(f"\n  [{tlab}]" + ("（价格：算百分比收益）" if is_price else "（算绝对变化）"))
        print(f"    {'信号':<14}", end="")
        for h in horis:
            print(f"{'未来'+str(h)+'日':>13}", end="")
        print()
        for sname, sig in sigs.items():
            print(f"    {sname:<14}", end="")
            for h in horis:
                if is_price:
                    fc = [None if (v[i] is None or v[i + h] is None) else (v[i + h] / v[i] - 1) * 100
                          for i in range(n - h)] + [None] * h
                else:
                    fc = [None if (v[i] is None or v[i + h] is None) else (v[i + h] - v[i])
                          for i in range(n - h)] + [None] * h
                ic = rank_ic(sig, fc)
                print(f"{(('%+.3f' % ic) if ic is not None else '  n/a'):>13}", end="")
            print()
    print()


# --------------------------------------------------------------------------- T3 拆解
def t3_decompose(taco, mk):
    dates = taco["dates"]
    n = len(dates)
    print("=" * 92)
    print("T3  预测力从哪来：市场因子部分 vs 非市场部分")
    print("=" * 92)
    print(f"  TACO 分项权重（targetScaleWeights）：")
    w = taco["weights"]
    for k in FACTORS:
        tag = "  ← 本身就是市场价格" if k in MARKET_FACTORS else "  ← 非市场价格"
        print(f"    {k:<12} {w.get(k, 0):.3f}{tag}")
    print(f"    市场因子部分合计 {sum(w.get(k,0) for k in MARKET_FACTORS):.3f}"
          f"   非市场部分合计 {sum(w.get(k,0) for k in NONMARKET_FACTORS):.3f}")
    print()
    print(f"  序列统计：")
    for nm, k in [("TACO 总指数", "value"), ("市场因子部分", "mkt"), ("非市场部分", "nonmkt")]:
        v = taco[k]
        print(f"    {nm:<12} 均值 {st.mean(v):+6.2f}  标准差 {st.pstdev(v):5.2f}  "
              f"区间 {min(v):+6.2f} ~ {max(v):+6.2f}  最新 {v[-1]:+6.2f}")
    print()
    # 相关性
    print(f"  市场因子部分 与 非市场部分 的相关：", end="")
    c = corr(taco["mkt"], taco["nonmkt"])
    print(f"{c:+.3f}" if c is not None else "n/a")
    c2 = corr(taco["value"], taco["mkt"])
    c3 = corr(taco["value"], taco["nonmkt"])
    print(f"  TACO 与市场部分 {c2:+.3f} ; TACO 与非市场部分 {c3:+.3f}")
    print()
    # 市场序列的自相关导致的伪预测：用「市场部分」预测市场收益 —— 这是同期性，不是预测
    print("  市场因子部分 vs 非市场部分：对未来市场的 IC（20日）")
    print(f"    {'目标':<10}{'市场部分':>12}{'非市场部分':>14}")
    for tname, tlab, is_price in [("sp500", "标普500", True), ("vix", "VIX", False),
                                  ("dgs10", "10Y", False), ("hy", "高收益利差", False),
                                  ("hs300", "沪深300", True)]:
        v = align(dates, mk[tname])
        if not any(v):
            continue
        h = 20
        if is_price:
            fc = [None if (v[i] is None or v[i + h] is None) else (v[i + h] / v[i] - 1) * 100
                  for i in range(n - h)] + [None] * h
        else:
            fc = [None if (v[i] is None or v[i + h] is None) else (v[i + h] - v[i])
                  for i in range(n - h)] + [None] * h
        a = rank_ic(taco["mkt"], fc)
        b = rank_ic(taco["nonmkt"], fc)
        print(f"    {tlab:<10}{(('%+.3f' % a) if a is not None else 'n/a'):>12}"
              f"{(('%+.3f' % b) if b is not None else 'n/a'):>14}")
    print()


# --------------------------------------------------------------------------- T4 阈值穿越
def t4_threshold(taco, mk, evd):
    dates, vals = taco["dates"], taco["value"]
    n = len(dates)
    print("=" * 92)
    print("T4  阈值穿越事件研究：TACO 从下方上穿某阈值之后会发生什么")
    print("=" * 92)
    print(f"  {'阈值':>6}{'穿越次数':>9}{'后20日回撤事件率':>18}{'基准率':>9}"
          f"{'后20日SPX':>12}{'后20日VIX':>11}{'后20日10Y(bp)':>14}{'后20日沪深300':>14}")
    sp = align(dates, mk["sp500"]); vx = align(dates, mk["vix"])
    t10 = align(dates, mk["dgs10"]); hs = align(dates, mk["hs300"])

    def fwd(v, i, h, price, mult=1.0):
        if i + h >= n or v[i] is None or v[i + h] is None or v[i] == 0:
            return None
        return (v[i + h] / v[i] - 1) * 100 if price else (v[i + h] - v[i]) * mult

    base_ev = sum(1 for i in range(n - 20) if any(d in evd for d in dates[i + 1:i + 21])) / (n - 20) * 100
    for th in [0, 2, 4, 6, 8, 10, 12]:
        crossings = []
        for i in range(1, n):
            if vals[i] >= th > vals[i - 1]:
                crossings.append(i)
        if not crossings:
            print(f"  {th:>6}{0:>9}")
            continue
        evr = mean_of([100.0 if any(d in evd for d in dates[i + 1:i + 21]) else 0.0 for i in crossings])
        a = mean_of([fwd(sp, i, 20, True) for i in crossings])
        b = mean_of([fwd(vx, i, 20, False) for i in crossings])
        c = mean_of([fwd(t10, i, 20, False, 100) for i in crossings])
        e = mean_of([fwd(hs, i, 20, True) for i in crossings])
        print(f"  {th:>6}{len(crossings):>9}{evr:>17.1f}%{base_ev:>8.1f}%"
              f"{(('%+.2f%%' % a) if a is not None else 'n/a'):>12}"
              f"{(('%+.2f' % b) if b is not None else 'n/a'):>11}"
              f"{(('%+.1f' % c) if c is not None else 'n/a'):>14}"
              f"{(('%+.2f%%' % e) if e is not None else 'n/a'):>14}")
        if len(crossings) >= 5:
            d5 = mean_of([fwd(sp, i, 5, True) for i in crossings])
            d60 = mean_of([fwd(sp, i, 60, True) for i in crossings])
            print(f"        └ 标普500 后5日 {(('%+.2f%%' % d5) if d5 is not None else 'n/a')}"
                  f"   后60日 {(('%+.2f%%' % d60) if d60 is not None else 'n/a')}"
                  f"   （穿越日：{', '.join(dates[i] for i in crossings[:6])}"
                  f"{' …' if len(crossings) > 6 else ''}）")
    print()
    print("  注：4~8 档穿越后 20 日 '回撤事件率' 才是关键对比项 —— 若与基准率无差，则该档无预测价值。")
    print()


# --------------------------------------------------------------------------- T5 当前状态前瞻
def t5_analogue(taco, mk, evd):
    dates, vals = taco["dates"], taco["value"]
    n = len(dates)
    cur = vals[-1]
    print("=" * 92)
    print(f"T5  当前状态的前瞻分布（TACO 最新 = {cur:+.1f}，取历史同类状态做类比）")
    print("=" * 92)
    for lo, hi, lab in [(cur - 1, cur + 1, f"{cur-1:.1f}~{cur+1:.1f}（±1）"),
                        (cur - 3, cur + 3, f"{cur-3:.1f}~{cur+3:.1f}（±3）")]:
        idxs = [i for i in range(n) if lo <= vals[i] <= hi]
        if len(idxs) < 10:
            print(f"  类比区间 {lab}：样本仅 {len(idxs)} 天，不足以统计")
            continue
        print(f"\n  类比区间 {lab}：{len(idxs)} 个交易日，{dates[idxs[0]]} ~ {dates[idxs[-1]]}")
        # 前瞻：TACO 自身
        for h in [5, 20, 60]:
            fv = [vals[i + h] for i in idxs if i + h < n]
            if len(fv) < 5:
                continue
            d = [vals[i] - vals[i] for i in idxs]
            ch = [vals[i + h] - vals[i] for i in idxs if i + h < n]
            print(f"    TACO 未来{h:>3}日：均值 {st.mean(fv):+6.2f}（变化 {st.mean(ch):+5.2f}）"
                  f"  中位 {st.median(fv):+6.2f}  区间 {min(fv):+5.2f}~{max(fv):+5.2f}"
                  f"  上行概率 {sum(1 for x in ch if x > 0)/len(ch)*100:.0f}%")
        # 前瞻：事件
        for h in [20, 60]:
            r = [any(d in evd for d in dates[i + 1:i + 1 + h]) for i in idxs if i + h < n]
            if r:
                print(f"    未来{h}日内出现重大回撤：{sum(r)}/{len(r)} = {sum(r)/len(r)*100:.0f}%")
        # 前瞻：市场
        for nm, lab, is_price in [("sp500", "标普500", True), ("vix", "VIX", False), ("hs300", "沪深300", True)]:
            v = align(dates, mk[nm])
            for h in [20]:
                fv = [None if (v[i] is None or v[i + h] is None) else
                      ((v[i + h] / v[i] - 1) * 100 if is_price else v[i + h] - v[i])
                      for i in idxs if i + h < n]
                fv = [x for x in fv if x is not None]
                if fv:
                    print(f"    未来{h}日 {lab:<8}：均值 {st.mean(fv):+6.2f}  中位 {st.median(fv):+6.2f}"
                          f"  上涨占比 {sum(1 for x in fv if x > 0)/len(fv)*100:>3.0f}%")
    print()
    # 全样本对照
    print("  全样本对照（任意一天）：")
    for nm, lab, is_price in [("sp500", "标普500", True), ("vix", "VIX", False), ("hs300", "沪深300", True)]:
        v = align(dates, mk[nm])
        h = 20
        fv = [None if (v[i] is None or v[i + h] is None) else
              ((v[i + h] / v[i] - 1) * 100 if is_price else v[i + h] - v[i]) for i in range(n - h)]
        fv = [x for x in fv if x is not None]
        print(f"    未来20日 {lab:<8}：均值 {st.mean(fv):+6.2f}  中位 {st.median(fv):+6.2f}"
              f"  上涨占比 {sum(1 for x in fv if x > 0)/len(fv)*100:>3.0f}%")
    r = [any(d in evd for d in dates[i + 1:i + 21]) for i in range(n - 20)]
    print(f"    未来20日内出现重大回撤：{sum(r)}/{len(r)} = {sum(r)/len(r)*100:.0f}%")
    print()


# --------------------------------------------------------------------------- T6 自相关
def t6_persistence(taco):
    vals = taco["value"]
    n = len(vals)
    print("=" * 92)
    print("T6  TACO 自身的持续性（决定信号能挂多久）")
    print("=" * 92)
    for h in [1, 5, 10, 20, 60]:
        c = corr(vals[:-h], vals[h:])
        ch = [vals[i + h] - vals[i] for i in range(n - h)]
        print(f"  与 {h:>3} 交易日后：自相关 {c:+.3f}   平均变化 {st.mean(ch):+5.2f}"
              f"   上行比例 {sum(1 for x in ch if x > 0)/(n-h)*100:>3.0f}%")
    print()
    # 半衰期
    a = corr(vals[:-1], vals[1:])
    print(f"  AR(1) = {a:+.4f}")
    if 0 < a < 1:
        import math
        print(f"  均值回归半衰期 ≈ {math.log(0.5)/math.log(a):.1f} 个交易日")
    print()
    # 高位停留时长
    print("  高位停留时长（历史上 TACO ≥ 阈值后连续保持的交易日数）：")
    for th in [4, 6, 8, 10]:
        runs, cur = [], 0
        for v in vals:
            if v >= th:
                cur += 1
            else:
                if cur:
                    runs.append(cur)
                cur = 0
        if cur:
            runs.append(cur)
        if runs:
            print(f"    ≥{th:>2}：{len(runs)} 段，中位 {st.median(runs):.0f} 日，"
                  f"最长 {max(runs)} 日，当前段已持续 "
                  f"{sum(1 for v in list(reversed(vals)) if v >= th and (runs and True)) if False else ''}"
                  f"{next((i for i, v in enumerate(reversed(vals)) if v < th), len(vals))} 日")
    print()


# --------------------------------------------------------------------------- T7 稳健性
def t7_robust(taco, mk):
    """剥离样本期趋势后的条件表现 —— 防止把「样本期内资产单边趋势」误读成信号。"""
    dates = taco["dates"]
    n = len(dates)
    print("=" * 92)
    print("T7  稳健性：剥离样本期趋势后的条件表现（防伪相关）")
    print("=" * 92)
    print("  做法：对每个前瞻窗口算出全样本平均收益作为基准，再看各 TACO 档位的超额与胜率。")
    print("       胜率 = 该档前瞻收益高于全样本中位数的比例；50% = 无信息。")
    print()
    for tname, tlab, is_price in [("sp500", "标普500", True), ("vix", "VIX", False),
                                  ("dxy", "美元指数", True), ("hy", "高收益利差", False),
                                  ("oil", "WTI原油", True), ("hs300", "沪深300", True)]:
        v = align(dates, mk[tname])
        if not any(v):
            continue
        h = 20
        if is_price:
            fc = [None if (v[i] is None or v[i + h] is None) else (v[i + h] / v[i] - 1) * 100
                  for i in range(n - h)] + [None] * h
        else:
            fc = [None if (v[i] is None or v[i + h] is None) else (v[i + h] - v[i])
                  for i in range(n - h)] + [None] * h
        valid = [x for x in fc if x is not None]
        if len(valid) < 50:
            continue
        base_m, base_med = st.mean(valid), st.median(valid)
        print(f"  [{tlab}] 未来20日  全样本均值 {base_m:+.2f}  中位 {base_med:+.2f}")
        print(f"    {'TACO档位':<14}{'样本':>6}{'均值':>10}{'超额':>10}{'高于中位比例':>14}")
        for lab, lo, hi in [("< 0", -99, 0), ("0 ~ 4", 0, 4), ("4 ~ 8", 4, 8),
                            ("8 ~ 12", 8, 12), ("≥ 12", 12, 99)]:
            sub = [fc[i] for i in range(n) if fc[i] is not None and lo <= taco["value"][i] < hi]
            if len(sub) < 8:
                print(f"    {lab:<14}{len(sub):>6}   样本不足")
                continue
            print(f"    {lab:<14}{len(sub):>6}{st.mean(sub):>+10.2f}{st.mean(sub)-base_m:>+10.2f}"
                  f"{sum(1 for x in sub if x > base_med)/len(sub)*100:>13.0f}%")
        print()


# --------------------------------------------------------------------------- T8 等待时间
def t8_waiting(taco, evd):
    """从任意一天出发，距下一次重大政策回撤还有多久 —— 直接回答「能预测多远」。"""
    dates, vals = taco["dates"], taco["value"]
    n = len(dates)
    idxmap = {d: i for i, d in enumerate(dates)}
    evidx = sorted(idxmap[d] for d in evd if d in idxmap)
    print("=" * 92)
    print("T8  前瞻等待时间：从当前 TACO 水平出发，距下一次重大政策回撤还有多久")
    print("=" * 92)
    print(f"  {'TACO 档位':<14}{'样本日':>7}{'等待天数中位':>13}{'平均':>8}"
          f"{'≤20日内发生':>12}{'≤60日内发生':>12}")
    for lab, lo, hi in [("< 0", -99, 0), ("0 ~ 4", 0, 4), ("4 ~ 8", 4, 8),
                        ("8 ~ 12", 8, 12), ("≥ 12", 12, 99)]:
        waits, i20, i60 = [], 0, 0
        tot = 0
        for i in range(n):
            if not (lo <= vals[i] < hi):
                continue
            tot += 1
            nxt = next((j for j in evidx if j > i), None)
            if nxt is None:
                continue
            waits.append(nxt - i)
            if nxt - i <= 20:
                i20 += 1
            if nxt - i <= 60:
                i60 += 1
        if tot < 5:
            print(f"  {lab:<14}{tot:>7}   样本不足")
            continue
        print(f"  {lab:<14}{tot:>7}{st.median(waits):>13.0f}{st.mean(waits):>8.0f}"
              f"{i20/tot*100:>11.0f}%{i60/tot*100:>11.0f}%")
    # 全样本
    waits = []
    for i in range(n):
        nxt = next((j for j in evidx if j > i), None)
        if nxt is not None:
            waits.append(nxt - i)
    print(f"  {'全样本':<14}{len(waits):>7}{st.median(waits):>13.0f}{st.mean(waits):>8.0f}")
    print()
    print("  读法：等待天数中位数若各档接近，说明 TACO 水平对「还有多久出事」没有区分力；")
    print("       若低档等待明显更长、高档明显更短，则它确实携带前瞻的时间信息。")
    print()


# --------------------------------------------------------------------------- main
def main():
    taco = load_taco()
    mk = load_market()
    dates = taco["dates"]
    print()
    print("=" * 92)
    print(f"数据窗口：{dates[0]} → {dates[-1]}（{len(dates)} 个交易日）")
    print(f"TACO 最新：{taco['value'][-1]:+.1f}  |  市场因子部分 {taco['mkt'][-1]:+.2f}"
          f"  |  非市场部分 {taco['nonmkt'][-1]:+.2f}")
    print("=" * 92)
    print()
    evd = event_days(dates)
    print(f"重大回撤事件日（强/最强/中强，按回撤日映射到交易日）：{len(evd)} 个")
    print()
    t1_leadership(taco, evd)
    t2_forward(taco, mk)
    t3_decompose(taco, mk)
    t7_robust(taco, mk)
    t4_threshold(taco, mk, evd)
    t8_waiting(taco, evd)
    t5_analogue(taco, mk, evd)
    t6_persistence(taco)


if __name__ == "__main__":
    main()
