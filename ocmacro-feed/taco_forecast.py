#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TACO 前瞻卡（taco_forecast）
=============================
回答一个问题：当前这个 TACO 读数，对未来意味着什么？

设计原则（都是被 2026-09-12 的检验打过脸的教训）：
  1. **分四层输出，每层标注可靠度**。TACO 不是一个单一性质的指标：
     它对自己的预测很可靠（指数构造决定），对政策回撤事件中等，
     对市场方向基本不可靠（与「标普跌最深」重合度 80%）。
     把它们混在一起报，就是在制造幻觉。
  2. **任何前瞻结论必须附「独立簇数」**。TACO ≥8 的 33 个交易日其实只落在
     4 个独立事件簇里。不区分「天数」和「独立观测」，会高估可信度一个量级。
  3. **每个条件概率必须同时给基准率**。「TACO≥8 → 20日内回撤」的 91% 看着惊人，
     但基准率就有 63%。只报前者等于骗人。
  4. **市场和事件两层都必须和机械基准对照**。TACO 有 50% 权重来自市场价格，
     不跟「标普自身回撤」比，就无法知道它有没有增量信息。

用法：
  python3 taco_forecast.py                    # 文本前瞻卡（用最新快照）
  python3 taco_forecast.py --json             # 结构化输出，供子智能体切片
  python3 taco_forecast.py --write            # 落盘 data/forecast-<日期>.json
  python3 taco_forecast.py --snapshot <目录>  # 指定快照目录

零依赖（纯标准库）。市场数据可选：若存在 ../taco-predictive/data/fred_*.csv
则额外输出市场前瞻分布；缺失则自动跳过该层（不影响前两层）。
"""
import os
import re
import csv
import json
import argparse
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
DATE_RE = re.compile(r"(\d{4})[-/](\d{2})[-/](\d{2})")
MIN_STRENGTH = ("强", "最强", "中强")
MARKET_FACTORS = ("dgs10", "move", "sp500", "vix")
NONMARKET_FACTORS = ("approval", "bkevenpy02")
CLUSTER_GAP = 10          # 间隔 >10 个交易日即视为新的独立簇


# --------------------------------------------------------------------------- 基础
def latest_snapshot(outdir):
    if not os.path.isdir(outdir):
        return None
    days = sorted(d for d in os.listdir(outdir)
                  if re.match(r"^\d{4}-\d{2}-\d{2}$", d)
                  and os.path.exists(os.path.join(outdir, d, "taco_index_history.csv")))
    return os.path.join(outdir, days[-1]) if days else None


def load_snapshot(snap):
    rows = list(csv.DictReader(open(os.path.join(snap, "taco_index_history.csv"),
                                    encoding="utf-8-sig")))
    dates = [r["date"] for r in rows]
    vals = [float(r["value"]) for r in rows]
    contrib = {}
    for k in list(MARKET_FACTORS) + list(NONMARKET_FACTORS):
        col = f"contributions.{k}"
        contrib[k] = [float(r[col]) if r.get(col) not in (None, "") else 0.0 for r in rows]
    epath = os.path.join(snap, "taco_events.json")
    events = json.load(open(epath, encoding="utf-8")) if os.path.exists(epath) else []
    fpath = os.path.join(snap, "trump_dashboard.json")
    fac_meta = {}
    cur_idx = {}
    if os.path.exists(fpath):
        t = json.load(open(fpath, encoding="utf-8"))["taco"]
        for f in t.get("factors", []):
            fac_meta[f["key"]] = {"label": f.get("shortLabel") or f.get("label"),
                                  "weight": f.get("weight"),
                                  "valueLabel": f.get("valueLabel")}
        cur_idx = t.get("index") or {}
    return {"dates": dates, "vals": vals, "contrib": contrib,
            "events": events, "facMeta": fac_meta, "index": cur_idx,
            "change": None}


def load_change_contrib(snap):
    rows = list(csv.DictReader(open(os.path.join(snap, "taco_index_history.csv"),
                                    encoding="utf-8-sig")))
    out = {}
    for k in list(MARKET_FACTORS) + list(NONMARKET_FACTORS):
        col = f"changeContributions.{k}"
        out[k] = [float(r[col]) if r.get(col) not in (None, "") else 0.0 for r in rows]
    return out


# --------------------------------------------------------------------------- 事件
def _tokens(p):
    return [f"{a}-{b}-{c}" for a, b, c in DATE_RE.findall(p or "")]


def rollback_date(period):
    t = _tokens(period)
    return max(t) if t else None


def snap_to_trading(target, dates):
    c = [d for d in dates if d <= target]
    return c[-1] if c else None


def event_days(events, dates):
    s = set()
    for e in events:
        if (e.get("strength") or "") not in MIN_STRENGTH:
            continue
        d = rollback_date(e.get("period"))
        t = snap_to_trading(d, dates) if d else None
        if t:
            s.add(t)
    return s


# --------------------------------------------------------------------------- 工具
def clusters(idxs, gap=CLUSTER_GAP):
    """把索引切成独立簇 —— 这是判断「样本量」的唯一正确方式。"""
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


def corr(a, b):
    if len(a) != len(b):
        n = min(len(a), len(b))
        a, b = a[:n], b[:n]
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    dx = sum((x - ma) ** 2 for x in a) ** 0.5
    dy = sum((y - mb) ** 2 for y in b) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def fred_series(name, root):
    """读取可选的 FRED 缓存；缺失返回 None。"""
    p = os.path.join(root, "data", f"fred_{name}.csv")
    if not os.path.exists(p):
        return None
    d = {}
    for line in open(p, encoding="utf-8-sig"):
        parts = line.strip().split(",")
        if len(parts) < 2 or not DATE_RE.match(parts[0].strip()):
            continue
        if parts[1].strip() in (".", "", "NA"):
            continue
        try:
            d[parts[0].strip()] = float(parts[1])
        except ValueError:
            pass
    return d or None


def align(dates, series):
    out, last = [], None
    for d in dates:
        if d in series:
            last = series[d]
        out.append(last)
    return out


def pct_rank(vals, v):
    return sum(1 for x in vals if x <= v) / len(vals) * 100 if vals else 0.0


# --------------------------------------------------------------------------- 四层分析
def layer1_self(dates, vals):
    """层一：TACO 自身的未来路径。可靠度最高 —— 由指数构造（成分均值回归）决定。"""
    n = len(vals)
    cur = vals[-1]
    out = {"reliability": "高", "asOf": dates[-1], "value": cur,
           "percentile": round(pct_rank(vals, cur), 0)}
    # 自相关 / 半衰期
    ac = {}
    for h in (1, 5, 10, 20, 60):
        if n > h + 20:
            ac[h] = round(corr(vals[:-h], vals[h:]), 3)
    out["autocorr"] = ac
    a1 = ac.get(1)
    if a1 and 0 < a1 < 1:
        import math
        out["halfLifeDays"] = round(math.log(0.5) / math.log(a1), 1)
    # 历史同类状态
    for lab, w in (("pm1", 1.0), ("pm3", 3.0)):
        idxs = [i for i in range(n) if cur - w <= vals[i] <= cur + w]
        if len(idxs) < 8:
            out[lab] = {"n": len(idxs), "insufficient": True}
            continue
        rec = {"n": len(idxs), "from": dates[idxs[0]], "to": dates[idxs[-1]],
               "clusters": len(clusters(idxs)), "forward": {}}
        for h in (5, 20, 60):
            fv = [vals[i + h] for i in idxs if i + h < n]
            ch = [vals[i + h] - vals[i] for i in idxs if i + h < n]
            if len(fv) < 5:
                continue
            rec["forward"][h] = {
                "mean": round(st.mean(fv), 2), "median": round(st.median(fv), 2),
                "changeMean": round(st.mean(ch), 2),
                "min": round(min(fv), 2), "max": round(max(fv), 2),
                "upProb": round(sum(1 for x in ch if x > 0) / len(ch) * 100, 0)}
        out[lab] = rec
    return out


def layer2_event(dates, vals, evd):
    """层二：政策回撤窗口。可靠度中 —— 机制清楚但独立簇少。"""
    n = len(vals)
    cur = vals[-1]
    out = {"reliability": "中", "eventDays": len(evd)}
    windows = (5, 10, 20, 60)
    # 当前档位所在区间
    bucket = None
    for lab, lo, hi in [("< 0", -99, 0), ("0 ~ 4", 0, 4), ("4 ~ 8", 4, 8),
                        ("8 ~ 12", 8, 12), ("≥ 12", 12, 99)]:
        if lo <= cur < hi:
            bucket = lab
    out["currentBucket"] = bucket
    # 条件概率（当前档位）
    lo, hi = next(((a, b) for l, a, b in [("< 0", -99, 0), ("0 ~ 4", 0, 4),
                                          ("4 ~ 8", 4, 8), ("8 ~ 12", 8, 12),
                                          ("≥ 12", 12, 99)] if l == bucket), (-99, 99))
    idxs = [i for i in range(n - max(windows)) if lo <= vals[i] < hi]
    out["bucketCond"] = {"label": bucket, "n": len(idxs),
                         "clusters": len(clusters(idxs)), "p": {}}
    for w in windows:
        if not idxs:
            continue
        out["bucketCond"]["p"][w] = round(
            sum(1 for i in idxs if any(d in evd for d in dates[i + 1:i + 1 + w]))
            / len(idxs) * 100, 1)
    # 基准率
    out["base"] = {}
    for w in windows:
        tot = n - w
        out["base"][w] = round(sum(1 for i in range(tot)
                                   if any(d in evd for d in dates[i + 1:i + 1 + w]))
                               / tot * 100, 1) if tot > 0 else None
    # 阈值结构：哪个门槛真正有区分度
    out["thresholds"] = []
    for th in (2, 4, 6, 8, 10, 12):
        cross = [i for i in range(1, n) if vals[i] >= th > vals[i - 1]]
        if not cross:
            continue
        p20 = round(sum(1 for i in cross
                        if any(d in evd for d in dates[i + 1:i + 21])) / len(cross) * 100, 1)
        out["thresholds"].append({"threshold": th, "crossings": len(cross),
                                  "crossClusters": len(clusters(cross)),
                                  "p20": p20, "base20": out["base"][20]})
    # 前瞻等待时间
    idxmap = {d: i for i, d in enumerate(dates)}
    eidx = sorted(idxmap[d] for d in evd if d in idxmap)
    waits = []
    for i in range(n):
        nx = next((j for j in eidx if j > i), None)
        if nx is not None:
            waits.append(nx - i)
    out["waitingMedian"] = round(st.median(waits), 0) if waits else None
    if idxs:
        w2 = []
        for i in idxs:
            nx = next((j for j in eidx if j > i), None)
            if nx is not None:
                w2.append(nx - i)
        out["bucketWaitMedian"] = round(st.median(w2), 0) if w2 else None
    return out


def layer3_market(dates, vals, root):
    """层三：市场前瞻。可靠度低 —— 必须与机械基准对照才能判断有无增量信息。"""
    out = {"reliability": "低",
           "note": "TACO 有 50% 权重来自市场价格（标普 17.5% + 10Y 17.5% + MOVE 7.5% + VIX 7.5%），"
                   "不跟机械基准对照就无法判断增量信息。"}
    FILEMAP = {"sp500": ("fred_SP500.csv", True), "vix": ("fred_VIXCLS.csv", False),
               "dgs10": ("fred_DGS10.csv", False), "dxy": ("fred_DTWEXBGS.csv", True),
               "oil": ("fred_DCOILWTICO.csv", True), "hy": ("fred_BAMLH0A0HYM2.csv", False),
               "hs300": ("cn_sh000300.csv", True)}
    series = {}
    for nm, (fn, _p) in FILEMAP.items():
        p = os.path.join(root, "data", fn)
        if not os.path.exists(p):
            continue
        d = {}
        for line in open(p, encoding="utf-8-sig"):
            parts = line.strip().split(",")
            if len(parts) < 2 or not DATE_RE.match(parts[0].strip()):
                continue
            if parts[1].strip() in (".", "", "NA"):
                continue
            try:
                d[parts[0].strip()] = float(parts[1])
            except ValueError:
                pass
        if d:
            series[nm] = align(dates, d)
    if not series:
        out["available"] = False
        out["hint"] = f"未找到市场数据缓存（{os.path.join(root, 'data')}）。"
        return out
    out["available"] = True
    n = len(vals)
    cur = vals[-1]

    def fwd(v, i, h, price=True):
        if i + h >= n or v[i] is None or v[i + h] is None or v[i] == 0:
            return None
        return (v[i + h] / v[i] - 1) * 100 if price else v[i + h] - v[i]

    LAST = {k: v for k, (_f, v) in FILEMAP.items()}
    # 当前档位的前瞻分布
    hi_i = [i for i in range(n) if vals[i] >= 8]
    lo_i = [i for i in range(n) if vals[i] < 8]
    out["heavyVsRest"] = {}
    for nm, v in series.items():
        rec = {}
        for lab, idxs in (("TACO≥8", hi_i), ("TACO<8", lo_i)):
            f = [fwd(v, i, 20, LAST[nm]) for i in idxs]
            f = [x for x in f if x is not None]
            if len(f) >= 5:
                rec[lab] = {"n": len(f), "mean": round(st.mean(f), 2),
                            "upProb": round(sum(1 for x in f if x > 0) / len(f) * 100, 0)}
        if rec:
            out["heavyVsRest"][nm] = rec
    # 机械基准对照：标普自身回撤
    sp = series.get("sp500")
    if sp:
        LO, HI = 20, n - 60
        univ = [i for i in range(LO, HI) if sp[i] and sp[i - 20]]
        sig_taco = [i for i in univ if vals[i] >= 8]
        sp20 = {i: (sp[i] / sp[i - 20] - 1) * 100 for i in univ}
        cand = sorted(univ, key=lambda i: sp20[i])[:len(sig_taco)]
        sig_sp = set(cand)
        a = [fwd(sp, i, 20) for i in sig_taco]
        a = [x for x in a if x is not None]
        b = [fwd(sp, i, 20) for i in sig_sp]
        b = [x for x in b if x is not None]
        ov = len(set(sig_taco) & sig_sp)
        out["vsMechanical"] = {
            "window": f"{dates[LO]} ~ {dates[HI-1]}", "n": len(sig_taco),
            "tacoMean": round(st.mean(a), 2) if a else None,
            "tacoHit": round(sum(1 for x in a if x > 0) / len(a) * 100, 0) if a else None,
            "mechMean": round(st.mean(b), 2) if b else None,
            "mechHit": round(sum(1 for x in b if x > 0) / len(b) * 100, 0) if b else None,
            "overlapPct": round(ov / max(1, len(sig_taco)) * 100, 0),
            "episodes": len(clusters(sig_taco)),
        }
        # 偏相关：控制过去20日标普后 TACO 还剩多少解释力
        rows = [(vals[i], sp20[i], fwd(sp, i, 20)) for i in univ]
        rows = [r for r in rows if r[2] is not None]
        if len(rows) > 50:
            t_, s_, f_ = [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]
            rtf, rsf, rts = corr(t_, f_), corr(s_, f_), corr(t_, s_)
            den = ((1 - rts ** 2) * (1 - rsf ** 2)) ** 0.5
            out["vsMechanical"]["partialCorr"] = round((rtf - rts * rsf) / den, 3) if den else None
            out["vsMechanical"]["rawCorrTacoFwd"] = round(rtf, 3)
            out["vsMechanical"]["rawCorrPastFwd"] = round(rsf, 3)
    # 簇级检验
    if sp:
        eps = clusters([i for i in range(n) if vals[i] >= 8 and i + 20 < n])
        rets = []
        for e in eps:
            f = [fwd(sp, i, 20) for i in e]
            f = [x for x in f if x is not None]
            if f:
                rets.append(st.mean(f))
        base = [fwd(sp, i, 20) for i in range(n - 20)]
        base = [x for x in base if x is not None]
        if len(rets) >= 2 and base:
            se = st.pstdev(rets) / len(rets) ** 0.5
            t = (st.mean(rets) - st.mean(base)) / se if se else 0
            out["clusterTest"] = {"nClusters": len(rets),
                                  "clusterMean": round(st.mean(rets), 2),
                                  "baseMean": round(st.mean(base), 2),
                                  "t": round(t, 2),
                                  "significant": abs(t) > 2.78,
                                  "perCluster": [round(x, 2) for x in rets]}
    return out


# --------------------------------------------------------------------------- 输出
def build(outdir):
    snap = latest_snapshot(outdir)
    if not snap:
        return {"error": f"未找到快照，请先跑 snapshot。查找目录：{outdir}"}
    d = load_snapshot(snap)
    dates, vals = d["dates"], d["vals"]
    evd = event_days(d["events"], dates)
    change = load_change_contrib(snap)
    contrib = d["contrib"]
    n = len(vals)
    # 构成拆解
    mkt = [sum(contrib[k][i] for k in MARKET_FACTORS) for i in range(n)]
    nmk = [sum(contrib[k][i] for k in NONMARKET_FACTORS) for i in range(n)]
    ch_last = {k: change[k][-1] for k in change if change.get(k)}
    pos = {k: v for k, v in ch_last.items() if v > 0}
    tot_pos = sum(pos.values()) or 1.0
    dom = max(pos, key=pos.get) if pos else None
    # 市场数据缓存固定在桌面主副本根（镜像副本经绝对路径共享，不做本地拷贝）
    root = os.environ.get("CAISEN_ROOT") or "/Users/weihaoli/Desktop/蔡森 skill"
    pred = os.path.join(root, "taco-predictive")
    return {
        "asOf": dates[-1],
        "snapshot": os.path.basename(snap),
        "value": vals[-1],
        "percentile": round(pct_rank(vals, vals[-1]), 0),
        "change20d": round(vals[-1] - vals[-21], 2) if n > 20 else None,
        "window": {"from": dates[0], "to": dates[-1], "sessions": n},
        "composition": {
            "market": round(mkt[-1], 2), "marketShare": round(mkt[-1] / vals[-1] * 100, 0) if vals[-1] else None,
            "nonMarket": round(nmk[-1], 2),
            "dominantDriver": dom,
            "dominantDriverLabel": (d["facMeta"].get(dom) or {}).get("label", dom),
            "dominantSharePct": round(pos.get(dom, 0) / tot_pos * 100, 0) if dom else None,
            "changeContrib": {k: round(v, 2) for k, v in ch_last.items()},
        },
        "layer1_self": layer1_self(dates, vals),
        "layer2_event": layer2_event(dates, vals, evd),
        "layer3_market": layer3_market(dates, vals, pred),
    }


def render(f):
    if "error" in f:
        return "❌ " + f["error"]
    L = []
    A = L.append
    A("=" * 74)
    A(f"TACO 前瞻卡    数据截至 {f['asOf']}    快照 {f['snapshot']}")
    A("=" * 74)
    A(f"当前读数  {f['value']:+.2f}   分位 {f['percentile']:.0f}   "
      f"20日变化 {f['change20d']:+.2f}")
    c = f["composition"]
    A(f"构成拆解  市场因子部分 {c['market']:+.2f}   非市场部分 {c['nonMarket']:+.2f}")
    if c["dominantDriver"]:
        A(f"          主导变化因子：{c['dominantDriverLabel']}  "
          f"{c['changeContrib'].get(c['dominantDriver'], 0):+.2f}"
          f"（占正向变化 {c['dominantSharePct']:.0f}%）")
    A("")
    l1 = f["layer1_self"]
    A(f"[一] 它自己的未来       可靠度：{l1['reliability']}")
    A(f"     AR(1)={l1['autocorr'].get(1)}  半衰期 {l1.get('halfLifeDays','n/a')} 个交易日  "
      f"20日自相关 {l1['autocorr'].get(20)}")
    A("     → 高压读数约 3 周内自然回落，这是指数构造决定的（成分均值回归），不是判断。")
    for lab, name in (("pm1", "±1"), ("pm3", "±3")):
        r = l1.get(lab) or {}
        if r.get("insufficient"):
            A(f"     同类区间{name}：仅 {r['n']} 天，样本不足")
            continue
        A(f"     同类区间{name}（{r['n']} 天，{r['clusters']} 簇）：", )
        for h, v in sorted(r["forward"].items(), key=lambda x: int(x[0])):
            A(f"        未来{h:>3}日 TACO 均值 {v['mean']:+6.2f}（变化 {v['changeMean']:+5.2f}）"
              f"  中位 {v['median']:+6.2f}  上行概率 {v['upProb']:>3.0f}%")
    A("")
    l2 = f["layer2_event"]
    A(f"[二] 政策回撤窗口       可靠度：{l2['reliability']}")
    bc = l2["bucketCond"]
    A(f"     当前档位 {bc['label']}：样本 {bc['n']} 天，但只落在 {bc['clusters']} 个独立簇里")
    A(f"     {'窗口':<10}{'本档':>9}{'基准率':>9}{'倍数':>8}")
    for w in (5, 10, 20, 60):
        p = bc["p"].get(w)
        b = l2["base"].get(w)
        if p is None or b is None:
            continue
        A(f"     未来{w:>3}日 {p:>8.1f}%{b:>8.1f}%{(p/b if b else 0):>7.1f}x")
    A(f"     前瞻等待中位 {l2['bucketWaitMedian']} 个交易日 "
      f"（全样本 {l2['waitingMedian']}）")
    A("     阈值结构（看哪一档真正有区分度）：")
    A(f"       {'门槛':<8}{'穿越':>6}{'独立簇':>7}{'后20日发生':>11}{'基准':>8}")
    for t in l2["thresholds"]:
        flag = "  ← 有区分度" if t["p20"] >= t["base20"] + 20 else ("  ← 无区分度" if t["p20"] < t["base20"] + 8 else "")
        A(f"       +{t['threshold']:<7}{t['crossings']:>6}{t['crossClusters']:>7}"
          f"{t['p20']:>10.1f}%{t['base20']:>7.1f}%{flag}")
    A("")
    l3 = f["layer3_market"]
    A(f"[三] 市场前瞻           可靠度：{l3['reliability']}")
    if not l3.get("available"):
        A(f"     {l3.get('hint','无市场数据')}")
    else:
        vm = l3.get("vsMechanical") or {}
        A(f"     与机械基准对照（{vm.get('window','')}，n={vm.get('n')}）：")
        A(f"       TACO≥8          后20日标普 {vm.get('tacoMean')}%  胜率 {vm.get('tacoHit')}%")
        A(f"       标普跌最深（机械） 后20日标普 {vm.get('mechMean')}%  胜率 {vm.get('mechHit')}%")
        A(f"       重合度 {vm.get('overlapPct')}%   → 增量 ≈ "
          f"{(vm.get('tacoMean') or 0) - (vm.get('mechMean') or 0):+.2f}pp")
        if vm.get("partialCorr") is not None:
            A(f"     控制「过去20日标普」后的偏相关 {vm['partialCorr']:+.3f}"
              f"（|·|<0.15 视为无增量信息）")
        ct = l3.get("clusterTest")
        if ct:
            A(f"     簇级检验：{ct['nClusters']} 个独立簇，簇均 {ct['clusterMean']}% "
              f"vs 基准 {ct['baseMean']}%，t={ct['t']}"
              f" → {'统计显著' if ct['significant'] else '样本不足，统计上不成立'}")
            A(f"       各簇：{ct['perCluster']}")
    A("")
    A("-" * 74)
    A("用法提醒：把三层分开用。第一层可当事实，第二层当参考（注意独立簇数），")
    A("          第三层不要单独用来做方向判断 —— 它对市场没有独立信息。")
    A("-" * 74)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="TACO 前瞻卡")
    ap.add_argument("--out", default=os.path.join(HERE, "data"), help="快照目录")
    ap.add_argument("--snapshot", help="直接指定快照目录")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON")
    ap.add_argument("--write", action="store_true", help="落盘 data/forecast-<日期>.json")
    a = ap.parse_args()
    if a.snapshot:
        global latest_snapshot
        latest_snapshot = lambda _o: a.snapshot
    f = build(a.out)
    if a.write and "error" not in f:
        p = os.path.join(a.out, f"forecast-{f['asOf']}.json")
        json.dump(f, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if not a.json:
            print(f"（已落盘 {p}）")
    if a.json:
        print(json.dumps(f, ensure_ascii=False, indent=1))
    else:
        print(render(f))


if __name__ == "__main__":
    main()
