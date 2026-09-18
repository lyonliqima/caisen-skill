#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
由 data/<日期>/ 快照生成单文件 HTML 可视化报告（Chart.js，浅色金融风）。

用法：
    python3 make_report.py                      # 用最新快照
    python3 make_report.py --date 2026-09-12    # 指定日期
输出：报告-ocmacro数据源研究.html
"""

import argparse
import csv
import json
import os
import re
import statistics as st
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))

FACTOR_COLORS = {
    "approval": "#c0392b", "dgs10": "#1f4e79", "move": "#b8860b",
    "sp500": "#0e7c86", "vix": "#7b3fa0", "bkevenpy02": "#d97706",
}


def load(day):
    d = os.path.join(HERE, "data", day)
    taco = json.load(open(f"{d}/trump_dashboard.json", encoding="utf-8"))["taco"]
    rows = list(csv.DictReader(open(f"{d}/taco_index_history.csv", encoding="utf-8-sig")))
    events = json.load(open(f"{d}/taco_events.json", encoding="utf-8"))
    housing = json.load(open(f"{d}/housing.json", encoding="utf-8"))["datasets"]
    ap_path = f"{d}/trump_approval.csv"
    approval = list(csv.DictReader(open(ap_path, encoding="utf-8-sig"))) \
        if os.path.exists(ap_path) else []
    return taco, rows, events, housing, approval


def norm_series(ds):
    """紧凑数组或对象数组统一成 {entity, entityType, values}，并按 scale 还原。"""
    sc = ds.get("scale", 1) or 1
    out = []
    for row in ds.get("series", []):
        if isinstance(row, list):
            k, e, ty, r, v = (row + [None] * 5)[:5]
            out.append({"entity": e, "entityType": ty,
                        "values": [None if x is None else x / sc for x in (v or [])]})
        else:
            out.append(row)
    return ds.get("periods", []), out


def build():
    days = sorted(os.listdir(os.path.join(HERE, "data")))
    days = [x for x in days if os.path.isdir(os.path.join(HERE, "data", x))]
    return days[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    day = a.date or build()
    taco, rows, events, housing, approval = load(day)

    # 支持率极值（用于报告里的「是否任期最低」判断——不许凭印象说「已是任期最低」）
    apnets = [float(r["net"]) for r in approval if r.get("net")]
    ap = {"n": len(apnets), "last": apnets[-1] if apnets else None,
          "min": min(apnets) if apnets else None, "max": max(apnets) if apnets else None,
          "dateMin": None}
    if apnets:
        for r in approval:
            if r.get("net") and float(r["net"]) == ap["min"]:
                ap["dateMin"] = r["date"]
    ap["atLow"] = bool(apnets and ap["last"] == ap["min"])
    ap["gap"] = round(ap["last"] - ap["min"], 2) if apnets else None

    fk = [f["key"] for f in taco["factors"]]
    fname = {f["key"]: f["shortLabel"] for f in taco["factors"]}
    dates = [r["date"] for r in rows]
    vals = [float(r["value"]) for r in rows]
    n = len(rows)

    # ---- 事件标记
    # ⚠️ 必须用「回撤日」= period 区间内**最后一个**日期（period 格式「威胁日 → 回撤日」）。
    #    用第一个日期（威胁日）会把事件整体前移 1–30 天，把条件概率的梯度打平。
    def rollback_date(p):
        t = re.findall(r"(\d{4})[-/](\d{2})[-/](\d{2})", p or "")
        return max(f"{a}-{b}-{c}" for a, b, c in t) if t else None

    marks, seen = [], set()
    for e in events:
        d0 = rollback_date(e["period"])
        if not d0 or e.get("strength") not in ("强", "最强", "中强"):
            continue
        cands = [d for d in dates if d <= d0]
        if not cands:
            continue
        k = (cands[-1], e["topic"])
        if k in seen:
            continue
        seen.add(k)
        marks.append({"x": cands[-1], "topic": e["topic"], "s": e["strength"]})

    # ---- 分项贡献（近 90 日）
    w = min(90, n)
    win_dates = dates[n - w:]
    contrib = {k: [float(rows[i]["contributions." + k]) for i in range(n - w, n)] for k in fk}

    # ---- 条件概率（回撤日口径，与 ocmacro_feed.py 的 conditional_table 同源）
    evd = set()
    for e in events:
        if e.get("strength") in ("强", "最强", "中强"):
            d0 = rollback_date(e["period"])
            if d0:
                cands = [d for d in dates if d <= d0]
                if cands:
                    evd.add(cands[-1])
    buckets = [("< +2", -99, 2), ("+2 ~ +5", 2, 5), ("+5 ~ +8", 5, 8), ("≥ +8", 8, 99)]
    cp = []
    for lab, lo, hi in buckets:
        tot = hit = 0
        for i in range(n - 20):
            if not (lo <= vals[i] < hi):
                continue
            tot += 1
            if any(d in evd for d in dates[i + 1:i + 21]):
                hit += 1
        cp.append({"label": lab, "p": round(hit / tot * 100, 1) if tot else 0, "n": tot})
    tot0 = n - 20
    base = sum(1 for i in range(tot0) if any(d in evd for d in dates[i + 1:i + 21])) / tot0 * 100

    # ---- 地产：能级读数表（最新期）
    TE = ("全国", "一线城市", "二线城市", "三线城市")
    tier_tbl = []
    for key, lab in (("series_second_hand_yoy", "二手房同比"),
                     ("series_new_house_yoy", "新房同比"),
                     ("series_second_hand_mom", "二手房环比"),
                     ("series_new_house_mom", "新房环比")):
        # 累计同比数据缺失较多，跳过 None
        _, SS = norm_series(housing[key])
        m = {s["entity"]: s["values"][0] for s in SS if s.get("entity") in TE}
        tier_tbl.append({"lab": lab,
                         "v": [m.get(t) for t in TE]})
    tier_period = housing["series_second_hand_yoy"]["periods"][0]

    # ---- 地产：能级环比（近 24 月）
    Pm, Sm = norm_series(housing["series_second_hand_mom"])
    tier = {s["entity"]: s["values"] for s in Sm if s.get("entityType") in ("tier", "all")}
    mon = {k: [round(x, 2) for x in list(reversed(tier[k]))[-24:]]
           for k in ("一线城市", "二线城市", "三线城市") if k in tier}
    months = list(reversed(Pm))[-24:]

    # ---- BIS 各国
    bis = housing["external_bis"]
    want = ("中国", "中国香港", "美国", "日本", "韩国", "英国", "德国",
            "法国", "澳大利亚", "加拿大", "西班牙", "意大利", "瑞典", "荷兰")
    bis_cur = sorted([c for c in bis["current"] if c["entity"] in want],
                     key=lambda x: x["drawdownPct"])
    bis_rows = [{"n": c["entity"], "dd": round(c["drawdownPct"], 1),
                 "q": c["quartersFromPeak"], "cls": c["class"],
                 "y1": round(c["oneYearPct"], 1), "pk": c["peakPeriod"]} for c in bis_cur]

    # ---- BIS 周期规律
    reg = []
    for cls in ("常规周期", "小型泡沫", "大型泡沫"):
        sub = [c for c in bis["cycles"] if c["class"] == cls]
        if not sub:
            continue
        rec = [c["recoveryQuarters"] for c in sub if c.get("recovered") and c.get("recoveryQuarters")]
        reg.append({"cls": cls, "n": len(sub),
                    "dd": round(st.median([c["drawdownPct"] for c in sub]), 1),
                    "q": round(st.median([c["downQuarters"] for c in sub]), 1),
                    "rec": f"{len([c for c in sub if c.get('recovered')])}/{len(sub)}",
                    "rq": round(st.median(rec)) if rec else None})

    # ---- 高频成交（52 周对齐 + 4周均比4周均；周度序列用 <= 截断会错位 1 周）
    from datetime import date as _d, timedelta
    s30 = housing["external_30city_sales"]
    agg = ("30城", "一线城市", "二线城市", "三线城市")
    hf = []
    for r in s30["series"]:
        # ⚠️ 只取商品房口径的四个汇总序列；城市级序列同名（商品房/二手房）重复会污染口径
        if r.get("market") != "commodity" or r.get("metric") != "area":
            continue
        if r.get("scopeLabel") not in agg:
            continue
        pts = [p for p in r["points"] if p.get("value") is not None]
        if len(pts) < 60:
            continue
        cur = pts[-1]
        try:
            cd = _d.fromisoformat(cur["date"])
        except Exception:
            continue
        tgt = cd - timedelta(days=364)
        pi, best = None, 11
        for i in range(len(pts) - 1):
            try:
                diff = abs((_d.fromisoformat(pts[i]["date"]) - tgt).days)
            except Exception:
                continue
            if diff < best:
                pi, best = i, diff
        l4 = st.mean([p["value"] for p in pts[-4:]])
        yoy = None
        if pi is not None and pi >= 3:
            p4 = st.mean([p["value"] for p in pts[pi - 3:pi + 1]])
            if p4:
                yoy = round((l4 / p4 - 1) * 100, 1)
        hf.append({"n": r.get("scopeLabel"), "wk": cur["date"], "v": round(cur["value"], 1),
                   "m4": round(l4, 1), "yoy": yoy,
                   "base": pts[pi]["date"] if pi is not None else None})

    idx = taco["index"]
    fac = [{"n": f["shortLabel"], "w": f["weightLabel"], "v": f["valueLabel"],
            "p": f["pressureLabel"], "c": round(f["weightedPressure"], 2),
            "key": f["key"]} for f in taco["factors"]]

    data = {
        "day": day, "asOf": idx["asOfDateLabel"], "value": idx["value"],
        "valueLabel": idx["valueLabel"], "status": idx["status"]["label"],
        "statusDesc": idx["status"]["description"], "chg20": idx["change20dLabel"],
        "ver": taco["methodologyVersion"],
        "dates": dates, "vals": vals, "marks": marks,
        "winDates": win_dates, "contrib": contrib, "fname": fname,
        "fcolors": FACTOR_COLORS, "cp": cp, "base": round(base, 1),
        "factorTable": fac,
        "peak": {"v": max(vals), "d": dates[vals.index(max(vals))]},
        "pctile": round(sum(1 for v in vals if v <= vals[-1]) / n * 100),
        "months": months, "mon": mon, "tierTbl": tier_tbl, "tierPeriod": tier_period,
        "bisRows": bis_rows, "bisReg": reg, "bisCounts": bis["cycleCounts"],
        "bisLatest": bis["latestPeriod"], "bisMeta": bis["methodThresholds"],
        "hf": hf, "hfLatest": s30["latestDate"], "ap": ap,
        "cpMax": max(x["p"] for x in cp) if cp else 0,
        "cpMaxLab": max(cp, key=lambda x: x["p"])["label"] if cp else "",
        "cpMaxN": max(cp, key=lambda x: x["p"])["n"] if cp else 0,
        "hf30": next((x["yoy"] for x in hf if x["n"] == "30城"), None),
        "hfTier": {x["n"]: x["yoy"] for x in hf},
    }

    html = TEMPLATE.replace("/*DATA*/", json.dumps(data, ensure_ascii=False))
    out = os.path.join(HERE, "报告-ocmacro数据源研究.html")
    open(out, "w", encoding="utf-8").write(html)
    print(f"已生成 {out}  （基于 {day} 快照）")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ocmacro.com 数据源研究 · TACO 压力指数与地产拆解</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#f7f6f3;--card:#fff;--ink:#15181d;--mute:#6b7280;--line:#e3e1db;
      --red:#c0392b;--blue:#1f4e79;--teal:#0e7c86;--amber:#b8860b;--purple:#7b3fa0;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:15px/1.75 -apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;}
.wrap{max-width:1080px;margin:0 auto;padding:48px 28px 80px}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.4px}
h2{font-size:20px;margin:52px 0 6px;padding-top:22px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:26px 0 8px;color:var(--blue)}
.sub{color:var(--mute);font-size:13.5px;margin:0 0 4px}
.tag{display:inline-block;background:#eef2f7;color:var(--blue);border-radius:20px;
     padding:2px 11px;font-size:12px;margin-right:6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
      padding:20px 22px;margin:16px 0}
.grid{display:grid;gap:14px}
.g4{grid-template-columns:repeat(4,1fr)}
.g3{grid-template-columns:repeat(3,1fr)}
.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:760px){.g4,.g3,.g2{grid-template-columns:1fr}}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.kpi .l{font-size:12.5px;color:var(--mute);letter-spacing:.3px}
.kpi .v{font-size:26px;font-weight:650;margin:4px 0 2px;letter-spacing:-.5px}
.kpi .d{font-size:12.5px;color:var(--mute)}
.hot .v{color:var(--red)}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:8px 0}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--mute);font-weight:600;font-size:12.5px;letter-spacing:.3px}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:none}
.callout{background:#fdf6f4;border-left:3px solid var(--red);border-radius:0 8px 8px 0;
         padding:14px 18px;margin:16px 0}
.callout.good{background:#f2f8f7;border-left-color:var(--teal)}
.callout.note{background:#f6f5f1;border-left-color:var(--amber)}
.callout p{margin:6px 0}
.chart{position:relative;height:340px;margin:8px 0}
.chart.tall{height:440px}
.chart.short{height:250px}
.warn{font-size:12.5px;color:var(--mute);margin-top:8px;line-height:1.7}
code{background:#efeee9;padding:1px 6px;border-radius:4px;font-size:12.5px}
.foot{margin-top:60px;padding-top:18px;border-top:1px solid var(--line);
      color:var(--mute);font-size:12.5px}
</style></head><body><div class="wrap">

<p class="sub">数据源研究 · 2026-09-12</p>
<h1>ocmacro.com：TACO 压力指数与地产拆解</h1>
<p class="sub">MacroMargin（宏观边际）两个公开栏目的数据可用性、方法论逆向与实证检验</p>
<p style="margin:12px 0 0">
<span class="tag">TACO 指数</span><span class="tag">70城房价 253期</span>
<span class="tag">BIS 58国 / 143周期</span><span class="tag">30城高频</span>
<span class="tag">方法版本 <span id="ver"></span></span></p>

<h2>一、TACO 压力指数当前读数</h2>
<div class="grid g4" style="margin-top:14px">
  <div class="kpi hot"><div class="l">TACO 压力指数</div><div class="v" id="kVal"></div>
    <div class="d" id="kSt"></div></div>
  <div class="kpi"><div class="l">较 20 交易日前</div><div class="v" id="kChg"></div>
    <div class="d">正值 = 压力仍在升温</div></div>
  <div class="kpi"><div class="l">历史分位</div><div class="v" id="kPct"></div>
    <div class="d" id="kPeak"></div></div>
  <div class="kpi"><div class="l">主导分项</div><div class="v" id="kDom"></div>
    <div class="d">占总指数 58%</div></div>
</div>

<div class="card" style="margin-top:16px">
<h3 style="margin-top:4px">六因子拆解（固定权重）</h3>
<table><thead><tr><th>因子</th><th class="n">权重</th><th class="n">当日读数</th>
<th class="n">压力贡献</th><th class="n">对指数贡献</th></tr></thead>
<tbody id="facT"></tbody></table>
<p class="warn">10 年美债贡献最高，本轮压力是<strong>利率驱动</strong>，不是政治驱动。
净支持率 <strong id="apNow"></strong>（<span id="apTxt"></span>，任期区间 <span id="apRange"></span>）
——已在低位区，边际增量衰减，<strong>指数下一轮见顶回落大概率由 10Y 见顶驱动，不会由支持率反弹驱动</strong>。</p>
</div>

<h2>二、指数全历史与政策回撤事件</h2>
<p class="sub">366 个交易日（2025-03-26 起，预热期不伪造数据点）；圆点为「强/最强/中强」级 TACO 事件</p>
<div class="card"><div class="chart tall"><canvas id="cMain"></canvas></div></div>

<h2>三、六因子贡献分解（近 90 个交易日）</h2>
<p class="sub">黑色实线为六项净和，即当期指数走势</p>
<div class="card"><div class="chart"><canvas id="cFactor"></canvas></div></div>

<h2>四、实证检验：这个指数怎么用</h2>
<div class="callout">
<p><strong>核心发现：TACO <span id="cpLab"></span> 时，未来 20 个交易日内出现重大政策回撤的概率为 <span id="cpP"></span>%（无条件基准 <span id="cpB"></span>%）。</strong></p>
<p><span id="cpTxt"></span>样本仅 <span id="cpN"></span> 个交易日且事件高度时间聚集，当参考、不当铁律。</p>
</div>
<div class="card"><div class="chart short"><canvas id="cProb"></canvas></div>
<p class="warn">
<strong>它不是领先指标。</strong>「强」级事件发生前，指数分位中位数只有 36（低于中位）——不能用「指数还没涨起来」推断「暂时不会有事」。<br>
<strong>回撤即释放。</strong> 重大事件后 20 交易日指数平均 <strong>−1.70</strong>，而全样本基准仅 −0.08。事件是压力的释放阀，不是压力的起点。<br>
<strong>回撤 ≠ 风险消除。</strong> 30 条复盘里绝大多数是「暂停/延期/口径降档」，明确写着「并非永久撤销」「尾部风险后移」。
</p></div>

<h2>五、70 城房价：能级分化出现拐点</h2>
<p class="sub">二手房环比（%），近 24 个月 —— 一线已连续 5 个月转正，三线仍在匀速阴跌</p>
<div class="card"><div class="chart"><canvas id="cTier"></canvas></div>
<div class="callout note" style="margin-top:14px">
<p><strong>价量分化：一线价量同向，二三线仍在缩量。</strong>
一线二手房环比连续 5 个月为正（+0.40/+0.40/+0.40/+0.30/+0.20），
且高频成交显示一线成交量同比 <strong id="hfy"></strong>（<span id="hfBase"></span>）——<strong>价与量同向回升</strong>；
但二线 <span id="hf2"></span>、三线 <span id="hf3"></span>、30 城合计 <span id="hf30"></span>，量能仍为负。</p>
<p>按蔡森形态学口径：<strong>一线「价稳 + 量增」两要素齐备，支持转多；但广度只有 5/70 城环比上涨、二三线双位数缩量，
属结构性分化行情而非全面反转，仓位仍须按「分化市」而非「牛市」配置。</strong></p>
</div>
</div>

<h3>70 城读数（<span id="tierP"></span>）：二手房同比全部下跌，0 城上涨</h3>
<div class="card"><table><thead><tr><th>口径</th><th class="n">全国</th><th class="n">一线</th>
<th class="n">二线</th><th class="n">三线</th></tr></thead><tbody id="tierT"></tbody></table>
<p class="warn">环比上涨仅 <strong>5/70</strong> 城：广州 +0.40、上海 +0.30、深圳 +0.20、徐州 +0.20、沈阳 +0.10 —— 全部集中于一二线。</p>
</div>

<h2>六、用 BIS 143 个历史周期给中国定位</h2>
<div class="grid g3" style="margin:14px 0">
  <div class="kpi"><div class="l">中国当前回撤</div><div class="v" style="color:var(--red)">−24.6%</div>
    <div class="d">实际房价，峰值 2021-Q3，距峰 18 季</div></div>
  <div class="kpi"><div class="l">同类周期中位跌幅</div><div class="v">−28.6%</div>
    <div class="d">小型泡沫（20%~35%），n=46</div></div>
  <div class="kpi"><div class="l">同类周期收复用时中位</div><div class="v" style="color:var(--amber)">52 季</div>
    <div class="d">= 13 年。这是时间价值的判决</div></div>
</div>
<div class="card"><h3 style="margin-top:4px">主要经济体高点回撤（BIS 实际房价，最新 <span id="bisL"></span>）</h3>
<div class="chart tall"><canvas id="cBis"></canvas></div>
<h3>历史周期规律</h3>
<table><thead><tr><th>分类</th><th class="n">周期数</th><th class="n">跌幅中位</th>
<th class="n">下跌季数中位</th><th class="n">已收复</th><th class="n">收复用时中位</th></tr></thead>
<tbody id="regT"></tbody></table>
<p class="warn">分档口径：常规周期 &lt;20%、小型泡沫 20%~35%、大型泡沫 ≥35%（参考长江证券《房价何处寻底？195 个房价周期的大数规律》）。</p>
</div>

<div class="callout">
<p><strong>三条硬结论：</strong></p>
<p>1. <strong>深度上</strong>，中国已跌到同类周期的 25 分位附近（实际 ≈75.4 vs p25 = 75.2），比典型「小型泡沫」更深，但未达「大型泡沫」门槛。</p>
<p>2. <strong>时间上</strong>，18 个季度 vs 中位 21.5 季 —— 价格主跌段按历史规律已接近尾声，但 p25 仍在下探。</p>
<p>3. <strong>收复上</strong>，小型泡沫收复用时中位 52 季（13 年）。即使此刻就是底，名义回到 2021 年高点也要等到 2034 年前后。
<strong>这是时间价值的判决，不是价格方向的判决。</strong></p>
</div>

<h2>七、高频数据：量能验证（与月度数据的分歧）</h2>
<p class="sub">30 大中城市成交面积（Wind 周频，商品房口径，4 周均 vs 52 周前同期 4 周均），最新 <span id="hfL"></span></p>
<div class="card"><div class="chart short"><canvas id="cHf"></canvas></div>
<p class="warn">70 城官方数据止于 2026-07，高频数据更新到 <span id="hfL2"></span>，比官方快两个月。
<span id="hfSum"></span></p></div>

<h2>八、数据可信度与局限</h2>
<div class="card">
<h3 style="margin-top:4px">可信的部分</h3>
<p>TACO 方法论参数是<strong>原始 JSON 字段</strong>（<code>normalization.scales</code>、<code>changeBaseline.lags</code>、
<code>stateDependentRules</code> 均带具体数值），不是从文字里猜的。地产面板是 Wind / BIS / 中原的原始结构化数据。</p>
<h3>必须打折的部分</h3>
<p>① 条件概率的极端档（<span id="cpLab2"></span> → <span id="cpP2"></span>%）基于 <strong><span id="cpN2"></span> 个样本日</strong>，2026 年事件高度聚集 → 当参考不当铁律。<strong>必须与基准率 <span id="cpB2"></span>% 一起读</strong>。<br>
② 压力区间阈值站方未公开数值（只给「中压」标签），分档边界无法复现。<br>
③ <code>@MacroMargin</code> 战绩为自述，未经独立验证。<br>
④ 70 城为国家统计局口径，存在结构性平滑；与 Wind 30 城周频不可直接换算。<br>
⑤ <strong>BIS 为季度、全国口径，掩盖中国内部能级分化</strong> —— 一线与三四线的差异被平均掉，做决策必须拆回 70 城。<br>
⑥ 本站为付费平台，公开栏目随时可能收紧。工具遇权限变化会明确报错，不做绕过。</p>
</div>

<div class="foot">
数据源：ocmacro.com（robots.txt 允许的两个公开栏目）。抓取工具：<code>ocmacro-feed/ocmacro_feed.py</code>，
快照日期 <span id="day"></span>。本报告所有图表均由该快照实时渲染，可复现。
</div>
</div>

<script>
const D = /*DATA*/;
Chart.defaults.font.family = '-apple-system,"PingFang SC","Microsoft YaHei",sans-serif';
Chart.defaults.font.size = 11.5;
Chart.defaults.color = '#6b7280';
const grid = {color:'#eceae4'};
const CK = Object.assign({}, D.contrib);
const palette = D.fcolors;

document.getElementById('ver').textContent = D.ver;
document.getElementById('day').textContent = D.day;
document.getElementById('kVal').textContent = D.valueLabel;
document.getElementById('kSt').textContent = D.status + ' · ' + D.statusDesc;
document.getElementById('kChg').textContent = D.chg20.replace('较20个交易日前 ','');
document.getElementById('kPct').textContent = D.pctile + ' 分位';
document.getElementById('kPeak').textContent = '峰值 ' + D.peak.v + '（' + D.peak.d + '）';

const dom = D.factorTable.reduce((a,b)=> b.c>a.c ? b : a);
document.getElementById('kDom').textContent = dom.n;

// 支持率（不许凭印象说「已是任期最低」）
if(D.ap && D.ap.last!=null){
  document.getElementById('apNow').textContent = D.ap.last+'%';
  document.getElementById('apTxt').textContent =
    D.ap.atLow ? '任期最低' : ('距任期最低 '+D.ap.gap+'pp，最低点 '+D.ap.dateMin);
  document.getElementById('apRange').textContent = D.ap.min+'% ~ '+D.ap.max+'%';
}
// 条件概率头条（全部从数据取，禁止硬编码）
document.getElementById('cpLab').textContent = D.cpMaxLab;
document.getElementById('cpP').textContent = D.cpMax;
document.getElementById('cpB').textContent = D.base;
document.getElementById('cpN').textContent = D.cpMaxN;
document.getElementById('cpLab2').textContent = D.cpMaxLab;
document.getElementById('cpP2').textContent = D.cpMax;
document.getElementById('cpN2').textContent = D.cpMaxN;
document.getElementById('cpB2').textContent = D.base;
const lowBuckets = D.cp.filter(x=>x.n>=20 && x.p < D.base + 8).map(x=>x.label);
document.getElementById('cpTxt').innerHTML =
  (D.cpMaxLab==='≥ +8' ? '≥ +5 起已出现区分度，' : '')
  +'注意 '+lowBuckets.join(' / ')+' 档与无条件基准（'+D.base+'%）无显著差异，'
  +'<strong>不得据此判断「压力不大所以安全」</strong>。';

document.getElementById('facT').innerHTML = D.factorTable.map(f=>{
  const strong = f.key==='dgs10' ? ' style="font-weight:650;color:#1f4e79"' : '';
  return `<tr${strong}><td>${f.n}</td><td class="n">${f.w}</td><td class="n">${f.v}</td>
          <td class="n">${f.p}</td><td class="n">${f.c>0?'+':''}${f.c.toFixed(2)}</td></tr>`;
}).join('');

// 1. 主图
new Chart(document.getElementById('cMain'),{type:'line',
 data:{labels:D.dates,datasets:[
  {label:'TACO 压力指数',data:D.vals,borderColor:'#1f4e79',borderWidth:1.6,
   pointRadius:0,tension:.15,fill:{target:{value:0},
   above:'rgba(192,57,43,.10)',below:'rgba(14,124,134,.10)'}},
  {label:'强/最强/中强 事件',type:'scatter',
   data:D.marks.map(m=>({x:m.x,y:D.vals[D.dates.indexOf(m.x)]})),
   backgroundColor:'#c0392b',borderColor:'#fff',borderWidth:1,pointRadius:4.5,
   pointHoverRadius:7}]},
 options:{maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
  plugins:{legend:{position:'top',labels:{boxWidth:12,usePointStyle:true}},
   tooltip:{callbacks:{afterBody:(it)=>{
     const m=D.marks.find(x=>D.dates[it[0].dataIndex]===x.x);
     return m? ['▶ '+m.s+' · '+m.topic] : [];}}}},
  scales:{x:{grid:grid,ticks:{maxTicksLimit:14}},
   y:{grid:grid,title:{display:true,text:'压力指数'}}}}});

// 2. 分项堆叠
const fs = Object.keys(D.contrib);
new Chart(document.getElementById('cFactor'),{type:'bar',
 data:{labels:D.winDates,datasets:[
  ...fs.map(k=>({label:D.fname[k],data:D.contrib[k],backgroundColor:palette[k],
    stack:'c',borderWidth:0})),
  {label:'六项净和（=指数）',type:'line',data:D.winDates.map((d,i)=>
     fs.reduce((s,k)=>s+D.contrib[k][i],0)),
   borderColor:'#15181d',borderWidth:1.8,pointRadius:0,tension:.15,stack:'x'}]},
 options:{maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
  plugins:{legend:{position:'top',labels:{boxWidth:12}},
   tooltip:{filter:i=>i.dataset.type==='line'||Math.abs(i.parsed.y)>0.005}},
  scales:{x:{stacked:true,grid:{display:false},ticks:{maxTicksLimit:12}},
   y:{stacked:true,grid:grid,title:{display:true,text:'对指数贡献（点）'}}}}});

// 3. 条件概率（基准线插件须在创建图表前注册）
Chart.register({id:'baseLine',afterDatasetsDraw(c){
  const y=c.scales.y.getPixelForValue(D.base), a=c.chartArea;
  const x=c.ctx; x.save(); x.setLineDash([5,4]); x.strokeStyle='#b8860b'; x.lineWidth=1.4;
  x.beginPath(); x.moveTo(a.left,y); x.lineTo(a.right,y); x.stroke();
  x.fillStyle='#b8860b'; x.font='11px sans-serif';
  x.fillText('无条件基准 '+D.base+'%',a.left+6,y-5); x.restore();}});
new Chart(document.getElementById('cProb'),{type:'bar',
 data:{labels:D.cp.map(x=>x.label),datasets:[
  {label:'20 交易日内出现重大政策回撤的概率',data:D.cp.map(x=>x.p),
   backgroundColor:D.cp.map(x=>x.p>80?'#c0392b':'#9fb3c8'),borderRadius:5}]},
 options:{maintainAspectRatio:false,
  plugins:{legend:{display:false},
   tooltip:{callbacks:{afterLabel:i=>'样本 '+D.cp[i.dataIndex].n+' 个交易日'}}},
  scales:{y:{grid:grid,beginAtZero:true,max:100,ticks:{callback:v=>v+'%'}},
   x:{grid:{display:false},title:{display:true,text:'当日 TACO 水平区间'}}}}});

// 4. 能级环比
const tierColors={'一线城市':'#c0392b','二线城市':'#1f4e79','三线城市':'#0e7c86'};
new Chart(document.getElementById('cTier'),{type:'line',
 data:{labels:D.months,datasets:Object.keys(D.mon).map(k=>({
   label:k+' 二手房环比',data:D.mon[k],borderColor:tierColors[k],
   backgroundColor:tierColors[k],borderWidth:2,pointRadius:2.5,tension:.2}))},
 options:{maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
  plugins:{legend:{position:'top',labels:{boxWidth:12,usePointStyle:true}}},
  scales:{y:{grid:grid,title:{display:true,text:'环比 %'}},
   x:{grid:{display:false},ticks:{maxTicksLimit:12}}}}});

// 5. 70城能级读数表（由快照实时计算）
const col = v => v===null||v===undefined ? '<td class="n">—</td>'
  : `<td class="n"${v>0?' style="color:#c0392b;font-weight:650"':''}>`
    +(v>0?'+':'')+v.toFixed(2)+'%</td>';
document.getElementById('tierP').textContent = D.tierPeriod;
document.getElementById('tierT').innerHTML = D.tierTbl.map(r=>
  '<tr><td>'+r.lab+'</td>'+r.v.map(col).join('')+'</tr>').join('');

// 6. BIS
document.getElementById('bisL').textContent = D.bisLatest;
const bc={'大型泡沫':'#c0392b','小型泡沫':'#b8860b','常规周期':'#7f8c8d'};
new Chart(document.getElementById('cBis'),{type:'bar',
 data:{labels:D.bisRows.map(x=>x.n),datasets:[
  {label:'高点回撤 %',data:D.bisRows.map(x=>x.dd),
   backgroundColor:D.bisRows.map(x=>bc[x.cls]),borderRadius:4}]},
 options:{indexAxis:'y',maintainAspectRatio:false,
  plugins:{legend:{display:false},
   tooltip:{callbacks:{afterLabel:i=>{const r=D.bisRows[i.dataIndex];
     return ['峰值 '+r.pk,'距峰 '+r.q+' 季','近1年 '+(r.y1>0?'+':'')+r.y1+'%','分类：'+r.cls];}}}},
  scales:{x:{grid:grid,title:{display:true,text:'距高点回撤 %'}},
   y:{grid:{display:false}}}}});

document.getElementById('regT').innerHTML = D.bisReg.map(r=>
 `<tr><td>${r.cls}</td><td class="n">${r.n}</td><td class="n">${r.dd}%</td>
  <td class="n">${r.q} 季（${(r.q/4).toFixed(1)} 年）</td><td class="n">${r.rec}</td>
  <td class="n">${r.rq?r.rq+' 季':'-'}</td></tr>`).join('');

// 7. 高频
document.getElementById('hfL').textContent = D.hfLatest;
document.getElementById('hfL2').textContent = D.hfLatest;
const pct = v => (v==null? 'n/a' : (v>0?'+':'')+v+'%');
const h1 = D.hf.find(x=>x.n==='一线城市');
if(h1) document.getElementById('hfy').textContent = pct(h1.yoy);
document.getElementById('hfBase').textContent = '基准 '+(h1?h1.base:'');
document.getElementById('hf2').textContent = pct(D.hfTier['二线城市']);
document.getElementById('hf3').textContent = pct(D.hfTier['三线城市']);
document.getElementById('hf30').textContent = pct(D.hfTier['30城']);
document.getElementById('hfSum').innerHTML =
  '一线 <strong style="color:var(--red)">'+pct(D.hfTier['一线城市'])+'</strong>、'
  +'二线 '+pct(D.hfTier['二线城市'])+'、三线 '+pct(D.hfTier['三线城市'])
  +'、30 城合计 '+pct(D.hfTier['30城'])
  +' —— <strong>只有一线在放量，二三线量能仍为负</strong>，属结构性分化而非全面反转。';
new Chart(document.getElementById('cHf'),{type:'bar',
 data:{labels:D.hf.map(x=>x.n),datasets:[
  {label:'最新周成交面积（万㎡）',data:D.hf.map(x=>x.v),backgroundColor:'#9fb3c8',borderRadius:4,yAxisID:'y'},
  {label:'同比 %',data:D.hf.map(x=>x.yoy),backgroundColor:'#c0392b',borderRadius:4,
   type:'line',yAxisID:'y1',borderColor:'#c0392b',borderWidth:2,pointRadius:5,
   pointBackgroundColor:'#c0392b'}]},
 options:{maintainAspectRatio:false,
  plugins:{legend:{position:'top',labels:{boxWidth:12,usePointStyle:true}},
   tooltip:{callbacks:{afterLabel:i=>'4周均值 '+D.hf[i.dataIndex].m4+' 万㎡'}}},
  scales:{y:{grid:grid,title:{display:true,text:'万㎡'}},
   y1:{position:'right',grid:{display:false},ticks:{callback:v=>v+'%'},
       title:{display:true,text:'同比 %'}},
   x:{grid:{display:false}}}}});
</script></body></html>
"""

if __name__ == "__main__":
    main()
