#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MacroMargin（宏观边际 / ocmacro.com）公开数据抓取器
=====================================================
抓取 ocmacro.com 三个公开数据源，落地为本地 JSON/CSV，供蔡森十二专家框架调用。

公开数据源（robots.txt 显式 Allow，无需登录）：
  1. /dashboard/trump            川普压力指数(TACO) + 六因子 + 全历史 + 支持率 + TACO事件复盘
  2. /api/trump/truths           Trump Truth Social 帖文（含中文翻译），CNN truth archive 为源
  3. /dashboard/data-breakdown   中国地产数据拆解：70城房价 253 期 + 广度 + BIS 国际房价周期 + 30城高频销售

用法：
  python3 ocmacro_feed.py digest               # 【框架专用】定向取数证据卡（TACO实时+条件概率+地产快照）
  python3 ocmacro_feed.py digest --json        # 同上，输出机器可读 JSON 并落盘
  python3 ocmacro_feed.py trump                # TACO 指数 + 六因子 + 全历史 + 事件库
  python3 ocmacro_feed.py truths --pages 3     # Truth Social 帖文（每页20条）
  python3 ocmacro_feed.py housing              # 地产核心数据集
  python3 ocmacro_feed.py housing --deep       # 地产全量（含 BIS 950KB / 30城 700KB）
  python3 ocmacro_feed.py snapshot             # 全部抓一遍，落 data/<日期>/
  python3 ocmacro_feed.py brief                # 只打印 TACO 当前读数速览（不落盘）

设计约定
  - 只读，不写远端；仅 GET。
  - 失败重试 3 次，指数退避。
  - 每次请求间隔 >=1.2s，避免触发站点 429 限流（站点限流提示：请求过于频繁，请稍后再试）。
  - TACO/支持率/事件库来自 Next.js RSC 内嵌载荷（self.__next_f.push），无需令牌。
  - 地产数据走带签名令牌的接口，令牌从 data-breakdown 页面 HTML 现取，TTL 约 2 小时。
    请求需带两个自定义头：X-MM-Data-Access: <token>、X-MM-Request-Intent: chart-data
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
BASE = "https://ocmacro.com"
HERE = os.path.dirname(os.path.abspath(__file__))
CST = timezone(timedelta(hours=8))

RETRIES = 3
SLEEP_BETWEEN = 1.2
_last_call = [0.0]


# ----------------------------------------------------------------------------- HTTP
def _throttle():
    dt = time.time() - _last_call[0]
    if dt < SLEEP_BETWEEN:
        time.sleep(SLEEP_BETWEEN - dt)
    _last_call[0] = time.time()


def http_get(url, headers=None, timeout=60):
    """带重试与限速的 GET。返回 bytes。"""
    hd = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    if headers:
        hd.update(headers)
    last = None
    for attempt in range(RETRIES):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=hd)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
        except Exception as e:  # 网络抖动
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {RETRIES} tries: {url} :: {last}")


# ----------------------------------------------------------------------------- RSC
def rsc_payload(html: str) -> str:
    """把 Next.js App Router 的 RSC 流式载荷拼回纯文本。"""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    out = []
    for c in chunks:
        try:
            out.append(json.loads('"' + c + '"'))
        except json.JSONDecodeError:
            continue
    return "".join(out)


def _balanced_json_at(s, i):
    """从 s[i] 处的 '{' 开始，返回配对结束下标。"""
    depth = 0
    instr = False
    esc = False
    for j in range(i, len(s)):
        c = s[j]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
            continue
        if c == '"':
            instr = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
    return None


def find_json_objects(payload: str, anchor: str):
    """在 RSC 载荷里找出包含 anchor 的、最外层 JSON 对象。"""
    out = []
    for m in re.finditer(re.escape(anchor), payload):
        j = payload.rfind("{", 0, m.start())
        if j < 0:
            continue
        end = _balanced_json_at(payload, j)
        if not end:
            continue
        try:
            out.append(json.loads(payload[j:end]))
        except json.JSONDecodeError:
            continue
    return out


# ----------------------------------------------------------------------------- 1. TACO
def fetch_trump_dashboard():
    """抓川普面板：TACO 指数块 + 支持率序列 + TACO 事件复盘。"""
    html = http_get(f"{BASE}/dashboard/trump").decode("utf-8", "ignore")
    payload = rsc_payload(html)

    blocks = find_json_objects(payload, '"methodologyVersion"')
    if not blocks:
        raise RuntimeError("未在 RSC 载荷中找到 TACO 指数块（页面结构可能已改版）")
    taco = max(blocks, key=len)  # 最外层最大那个

    # 支持率序列：标题为「川普支持率跟踪」的对象里带 rows
    approval = {"rows": [], "meta": {}}
    for o in find_json_objects(payload, '"川普支持率跟踪"'):
        rows = _deep_find_key(o, "rows")
        if rows:
            approval = {"rows": rows, "meta": {"title": "川普支持率跟踪"}}
            break

    # TACO 事件复盘：页面是服务端渲染的 HTML 列表，直接从 HTML 解析
    events = parse_taco_events(html)

    return {"taco": taco, "approval": approval, "events": events,
            "fetchedAt": datetime.now(CST).isoformat(timespec="seconds")}


def _deep_find_key(o, key):
    """在嵌套 dict/list 里找第一个非空的 key。"""
    if isinstance(o, dict):
        if o.get(key):
            return o[key]
        for v in o.values():
            r = _deep_find_key(v, key)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _deep_find_key(v, key)
            if r:
                return r
    return None


def parse_taco_events(html: str):
    """解析 TACO 事件复盘 HTML 列表 → 结构化事件。"""
    s = html.find('id="taco-event-log-list"')
    if s < 0:
        return []
    seg = html[s:]
    items = re.findall(r'<li class="[^"]*tacoEventItem[^"]*"[\s\S]*?</li>', seg)
    out = []
    for it in items:
        raw = re.sub(r"<[^>]+>", "|", it)
        raw = raw.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'")
        raw = raw.replace("&lt;", "<").replace("&gt;", ">")
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        parts = [re.sub(r'^__[A-Za-z0-9_]+">?', "", p) for p in parts]
        rec = {"seq": len(out) + 1, "period": None, "strength": None, "topic": None,
               "threat": None, "rollback": None, "analysis": None, "implication": None}
        if parts:
            rec["period"] = parts[0]
        if len(parts) > 1:
            rec["strength"] = parts[1]
        if len(parts) > 2:
            rec["topic"] = parts[2]
        for i, p in enumerate(parts):
            if p == "威胁" and i + 1 < len(parts):
                rec["threat"] = parts[i + 1]
            if p == "回撤" and i + 1 < len(parts):
                rec["rollback"] = parts[i + 1]
            if p == "含义" and i + 1 < len(parts):
                rec["implication"] = parts[i + 1]
        # 分析段 = 夹在 回撤内容 与 「含义」 之间的长句
        if rec["rollback"]:
            try:
                ri = parts.index("回撤")
                if "含义" in parts:
                    hi = parts.index("含义")
                    mids = parts[ri + 2:hi]
                    if mids:
                        rec["analysis"] = mids[0]
            except ValueError:
                pass
        if rec["threat"] or rec["topic"]:
            out.append(rec)
    return out


def taco_csv(taco, path):
    """TACO 全历史 → 宽表 CSV（含六因子贡献）。"""
    hist = taco.get("history") or []
    if not hist:
        return 0
    factor_keys = [f["key"] for f in taco.get("factors", [])]
    cols = ["date", "value"]
    for pre in ("contributions", "changeContributions", "levelContributions",
                "interactionAddOns", "fastStressRestoreContributions"):
        cols += [f"{pre}.{k}" for k in factor_keys]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in hist:
            row = [r.get("date"), r.get("value")]
            for pre in ("contributions", "changeContributions", "levelContributions",
                        "interactionAddOns", "fastStressRestoreContributions"):
                d = r.get(pre) or {}
                row += [d.get(k) for k in factor_keys]
            w.writerow(row)
    return len(hist)


def approval_csv(rows, path):
    if not rows:
        return 0
    cols = ["date", "approve", "disapprove", "net", "netLo", "netHi"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c) for c in cols])
    return len(rows)


# ----------------------------------------------------------------------------- 2. Truths
def fetch_truths(pages=1, page_size=20):
    out = []
    meta = None
    for p in range(pages):
        off = p * page_size
        url = f"{BASE}/api/trump/truths?offset={off}&limit={page_size}"
        raw = http_get(url, headers={"Referer": f"{BASE}/dashboard/trump",
                                     "Accept": "application/json"})
        d = json.loads(raw)
        if meta is None:
            meta = {"account": d.get("account"), "source": d.get("source"),
                    "generatedAt": d.get("generatedAt")}
        truths = d.get("truths") or []
        if not truths:
            break
        out += truths
    return {"meta": meta, "count": len(out), "truths": out,
            "fetchedAt": datetime.now(CST).isoformat(timespec="seconds")}


# ----------------------------------------------------------------------------- 3. Housing
def _housing_token():
    """现取地产数据的签名令牌 + 基础路径。"""
    html = http_get(f"{BASE}/dashboard/data-breakdown").decode("utf-8", "ignore")
    p = rsc_payload(html)
    tok = re.search(r'"dataAccessToken":"([^"]+)"', p)
    base = re.search(r'"dataBasePath":"([^"]+)"', p)
    if not tok or not base:
        raise RuntimeError("未取到地产数据令牌（页面结构可能已改版）")
    return base.group(1), tok.group(1)


HOUSING_SETS = {
    "manifest": "manifest.json",
    "series_second_hand_yoy": "compact/series/second_hand-yoy-all.json",
    "series_second_hand_mom": "compact/series/second_hand-mom-all.json",
    "series_new_house_yoy": "compact/series/new_house-yoy-all.json",
    "series_new_house_mom": "compact/series/new_house-mom-all.json",
    "breadth": "compact/breadth.json",
}
HOUSING_DEEP = {
    "external_zhongyuan": "external/zhongyuan-leading-index.json",
    "external_bis": "external/bis-real-house-price-index.json",
    "external_30city_sales": "external/china-30-city-property-sales.json",
    "series_second_hand_ytd": "compact/series/second_hand-ytd_yoy-all.json",
    "series_new_house_ytd": "compact/series/new_house-ytd_yoy-all.json",
}


def fetch_housing(deep=False):
    base, tok = _housing_token()
    hd = {"Referer": f"{BASE}/dashboard/data-breakdown",
          "Accept": "application/json",
          "X-MM-Request-Intent": "chart-data",
          "X-MM-Data-Access": tok}
    targets = dict(HOUSING_SETS)
    if deep:
        targets.update(HOUSING_DEEP)
    out = {}
    for name, rel in targets.items():
        try:
            raw = http_get(f"{BASE}{base}/{rel}", headers=hd, timeout=120)
            out[name] = json.loads(raw)
        except Exception as e:
            out[name] = {"_error": str(e)}
    return {"base": base, "fetchedAt": datetime.now(CST).isoformat(timespec="seconds"),
            "datasets": out}


# ----------------------------------------------------------------------------- digest（框架专用证据卡）
DATE_RE = re.compile(r"(\d{4})[-/](\d{2})[-/](\d{2})")
MIN_STRENGTH = ("强", "最强", "中强")


def _period_tokens(p):
    return [f"{a}-{b}-{c}" for a, b, c in DATE_RE.findall(p or "")]


def rollback_date(period):
    """事件的回撤日 = period 里最后一个日期（period 格式「威胁日 → 回撤日」）。
    ⚠️ 语义关键：做「给定今日压力 → 未来 N 日是否发生回撤」的条件概率，必须用回撤日；
    用威胁日会把事件日整体前移 1–30 天，严重污染检验结果。"""
    t = _period_tokens(period)
    return max(t) if t else None


def threat_date(period):
    t = _period_tokens(period)
    return min(t) if t else None


def event_rollback_days(events, min_strength=MIN_STRENGTH):
    """重大回撤事件日集合（回撤日口径，去重）。"""
    s = set()
    for e in events:
        if (e.get("strength") or "") not in min_strength:
            continue
        d = rollback_date(e.get("period"))
        if d:
            s.add(d)
    return s


def _pct_rank(vals, v):
    return sum(1 for x in vals if x <= v) / len(vals) * 100 if vals else 0.0


def _snap_to_trading(target_date, dates):
    """把自然日映射到 <= 它的最后一个交易日。"""
    c = [d for d in dates if d <= target_date]
    return c[-1] if c else None


def event_trading_days(events, dates, min_strength=MIN_STRENGTH):
    """重大回撤事件日集合，**已映射到 <= 回撤日的最后一个交易日**。

    ⚠️ 必须做这一步：回撤日常常落在非交易日（周末/节假日），
    直接把自然日塞进集合去和交易日序列比对，会让这些事件静默丢失，
    使条件概率与基准率同时偏低（2026-09-12 实锤：未映射 → 20日基准 58.7%；
    正确映射 → 62.7%，与 make_report.py 一致）。
    """
    out = set()
    for d in event_rollback_days(events, min_strength):
        t = _snap_to_trading(d, dates)
        if t:
            out.add(t)
    return out


def conditional_table(dates, vals, evd, buckets=None,
                      windows=(5, 10, 20)):
    """给定当日 TACO 水平 → 未来 N 个交易日内出现重大回撤的条件概率。"""
    buckets = buckets or [("< +2", -99, 2), ("+2~+5", 2, 5),
                          ("+5~+8", 5, 8), (">= +8", 8, 99)]
    if not dates or not vals:
        return []
    out = []
    for lab, lo, hi in buckets:
        tot = 0
        hits = {w: 0 for w in windows}
        for i in range(len(vals) - max(windows)):
            if not (lo <= vals[i] < hi):
                continue
            tot += 1
            for w in windows:
                if any(d in evd for d in dates[i + 1:i + 1 + w]):
                    hits[w] += 1
        out.append({"label": lab, "n": tot,
                    "p": {str(w): (round(hits[w] / tot * 100, 1) if tot else None)
                          for w in windows}})
    base = {}
    for w in windows:
        tot = len(vals) - w
        base[str(w)] = (round(sum(1 for i in range(tot)
                                  if any(d in evd for d in dates[i + 1:i + 1 + w]))
                              / tot * 100, 1) if tot > 0 else None)
    return {"buckets": out, "base": base,
            "eventDays": len(evd), "tradingDays": len(dates)}


def analyze_taco(taco, events):
    """把 TACO 原始块压成框架可用的结构化摘要。"""
    idx = taco["index"]
    hist = taco.get("history") or []
    dates = [h["date"] for h in hist]
    vals = [h["value"] for h in hist]
    cur = idx["value"]
    factors = []
    for f in taco.get("factors", []):
        factors.append({
            "key": f["key"], "label": f.get("shortLabel") or f.get("label"),
            "weightLabel": f.get("weightLabel"),
            "valueLabel": f.get("valueLabel"),
            "currentValueLabel": f.get("currentValueLabel"),
            "pressureLabel": f.get("pressureLabel"),
        })
    last = hist[-1] if hist else {}
    contrib = last.get("contributions") or {}
    chang = last.get("changeContributions") or {}
    # 主导因子 = 20 日变化的贡献最大者
    pos = {k: v for k, v in chang.items() if isinstance(v, (int, float)) and v > 0}
    tot_pos = sum(pos.values()) or 1.0
    dom_key = max(pos, key=pos.get) if pos else None
    lab = {f["key"]: f["label"] for f in factors}
    # 极值
    peak_i = max(range(len(vals)), key=lambda i: vals[i]) if vals else None
    trough_i = min(range(len(vals)), key=lambda i: vals[i]) if vals else None
    tbl = conditional_table(dates, vals, event_trading_days(events, dates))
    # 事件日聚合
    ev = []
    for e in events:
        rd = rollback_date(e.get("period"))
        if not rd:
            continue
        ev.append({"rollbackDate": rd, "threatDate": threat_date(e.get("period")),
                   "strength": e.get("strength"), "topic": e.get("topic"),
                   "rollback": (e.get("rollback") or "")[:120],
                   "implication": (e.get("implication") or "")[:120]})
    ev.sort(key=lambda x: x["rollbackDate"], reverse=True)
    return {
        "asOfDate": idx["asOfDate"], "value": cur, "valueLabel": idx["valueLabel"],
        "status": idx["status"], "change20d": idx.get("change20d"),
        "change20dLabel": idx.get("change20dLabel"),
        "percentile": round(_pct_rank(vals, cur), 1),
        "range": [min(vals), max(vals)] if vals else None,
        "peak": {"value": vals[peak_i], "date": dates[peak_i]} if vals else None,
        "trough": {"value": vals[trough_i], "date": dates[trough_i]} if vals else None,
        "sampleDays": len(vals), "windowStart": dates[0] if dates else None,
        "factors": factors,
        "contributions": contrib, "changeContributions": chang,
        "dominantDriver": dom_key, "dominantDriverLabel": lab.get(dom_key),
        "dominantShare": round(pos.get(dom_key, 0) / tot_pos * 100, 1) if dom_key else None,
        "conditional": tbl,
        "events": ev,
    }


def housing_summary(path):
    """把地产快照压成框架可用的结构化摘要（本地读，不联网）。"""
    with open(path, encoding="utf-8") as f:
        ds = json.load(f).get("datasets", {})

    def norm(d):
        sc = d.get("scale", 1) or 1
        out = []
        for row in d.get("series", []):
            if isinstance(row, list):
                k, e, t, r, v = (row + [None] * 5)[:5]
                out.append({"entity": e, "entityType": t,
                            "values": [None if x is None else x / sc for x in (v or [])]})
            else:
                out.append(row)
        return d.get("periods") or [], out

    def latest_map(key):
        if key not in ds or "_error" in ds[key]:
            return {}, []
        P, S = norm(ds[key])
        m = {}
        for s in S:
            if s.get("entity") in ("全国", "一线城市", "二线城市", "三线城市"):
                m[s["entity"]] = s["values"][0] if s.get("values") else None
        return m, P

    sh_yoy, P1 = latest_map("series_second_hand_yoy")
    nh_yoy, _ = latest_map("series_new_house_yoy")
    sh_mom, Pm = latest_map("series_second_hand_mom")
    nh_mom, _ = latest_map("series_new_house_mom")
    # 上涨城市数
    up = down = 0
    if "series_second_hand_yoy" in ds:
        _, S = norm(ds["series_second_hand_yoy"])
        cities = [s for s in S if s.get("entityType") == "city"]
        for s in cities:
            v = s["values"][0] if s.get("values") else None
            if v is None:
                continue
            up += 1 if v > 0 else 0
            down += 1 if v <= 0 else 0
    # 一线环比连续为正月数
    tier_streak = {}
    if "series_second_hand_mom" in ds:
        _, S = norm(ds["series_second_hand_mom"])
        for s in S:
            if s.get("entityType") not in ("all", "tier"):
                continue
            vs = [x for x in (s.get("values") or []) if x is not None]
            n = 0
            for x in vs:
                if x > 0:
                    n += 1
                else:
                    break
            tier_streak[s.get("entity")] = n
    # BIS
    bis = {}
    if "external_bis" in ds and "_error" not in ds["external_bis"]:
        b = ds["external_bis"]
        cur = [c for c in b.get("current", []) if c.get("entity") == "中国"]
        if cur:
            c = cur[0]
            cls = c.get("class")
            peers = [x for x in b.get("cycles", []) if x.get("class") == cls]
            dd = sorted(x["drawdownPct"] for x in peers)
            dq = sorted(x["downQuarters"] for x in peers)
            rec = [x["recoveryQuarters"] for x in peers
                   if x.get("recovered") and x.get("recoveryQuarters")]
            med = lambda a: (a[len(a) // 2] if len(a) % 2 else
                             (a[len(a) // 2 - 1] + a[len(a) // 2]) / 2) if a else None
            bis = {"entity": c["entity"], "latestPeriod": c.get("latestPeriod"),
                   "peakPeriod": c.get("peakPeriod"), "drawdownPct": c.get("drawdownPct"),
                   "quartersFromPeak": c.get("quartersFromPeak"), "class": cls,
                   "oneYearPct": c.get("oneYearPct"),
                   "peerN": len(peers),
                   "peerDrawdownMedian": med(dd), "peerDownQuartersMedian": med(dq),
                   "peerRecoveryQuartersMedian": med(rec)}
    # 30 城高频（4 周均 vs 去年同点 4 周均，消除单周噪声）
    hf = []
    if "external_30city_sales" in ds and "_error" not in ds["external_30city_sales"]:
        from datetime import date as _d, timedelta
        agg = {"30城", "一线城市", "二线城市", "三线城市"}
        for r in ds["external_30city_sales"].get("series", []):
            # ⚠️ 只取商品房口径的四个汇总序列；城市级序列同 scopeLabel 会重复（商品房/二手房），
            #    混入会造成口径污染（2026-09-12 实锤：曾因此把 +7.8% 误算成 -22.7%）
            if r.get("metric") != "area" or r.get("market") != "commodity":
                continue
            if r.get("scopeLabel") not in agg:
                continue
            pts = [p for p in r.get("points", []) if p.get("value") is not None]
            if len(pts) < 60:
                continue
            cur = pts[-1]
            try:
                cd = _d.fromisoformat(cur["date"])
            except Exception:
                continue
            # 去年同期 = 距最新点 52 周（364 天）「最接近」的那一点（周度序列必须周日对齐，
            # 用 <= 截断会错位 1 周 —— 2026-09-12 实锤：错位使 30 城同比从 -6.9% 漂到 +7.8%）
            tgt = cd - timedelta(days=364)
            pi, best = None, 11
            for i in range(len(pts) - 1):
                try:
                    diff = abs((_d.fromisoformat(pts[i]["date"]) - tgt).days)
                except Exception:
                    continue
                if diff < best:
                    pi, best = i, diff
            a4 = sum(p["value"] for p in pts[-4:]) / 4
            yoy = None
            if pi is not None and pi >= 3:
                p4 = sum(p["value"] for p in pts[pi - 3:pi + 1]) / 4
                if p4:
                    yoy = (a4 / p4 - 1) * 100
            hf.append({"scope": r.get("scopeLabel"), "latestDate": cur["date"],
                       "latest": cur["value"], "avg4w": round(a4, 1),
                       "yoyPct": round(yoy, 1) if yoy is not None else None,
                       "baseDate": pts[pi]["date"] if pi is not None else None,
                       "baseLagDays": best if pi is not None else None})
    return {"period": (P1 or [None])[0], "momPeriod": (Pm or [None])[0],
            "secondHandYoy": sh_yoy, "newHouseYoy": nh_yoy,
            "secondHandMom": sh_mom, "newHouseMom": nh_mom,
            "citiesUp": up, "citiesDown": down,
            "momPositiveStreak": tier_streak,
            "bisChina": bis, "highFreq": hf}


def find_latest_snapshot(outdir):
    """返回最新的 housing.json 路径（无则 None）。"""
    if not os.path.isdir(outdir):
        return None
    days = sorted(d for d in os.listdir(outdir)
                  if re.match(r"^\d{4}-\d{2}-\d{2}$", d))
    for d in reversed(days):
        p = os.path.join(outdir, d, "housing.json")
        if os.path.exists(p):
            return p
    return None


def cmd_digest(outdir, as_json=False, write=False, pages=0):
    """框架专用证据卡：TACO 实时 + 条件概率现场复算 + 本地地产快照摘要。"""
    html = http_get(f"{BASE}/dashboard/trump").decode("utf-8", "ignore")
    payload = rsc_payload(html)
    blocks = find_json_objects(payload, '"methodologyVersion"')
    if not blocks:
        raise RuntimeError("未取到 TACO 数据")
    taco = max(blocks, key=len)
    events = parse_taco_events(html)
    approval_rows = []
    for o in find_json_objects(payload, '"川普支持率跟踪"'):
        rows = _deep_find_key(o, "rows")
        if rows:
            approval_rows = rows
            break
    a = analyze_taco(taco, events)
    ap = {}
    if approval_rows:
        r0 = approval_rows[-1]
        nets = [r.get("net") for r in approval_rows if r.get("net") is not None]
        ap = {"date": r0.get("date"), "net": r0.get("net"),
              "netLo": r0.get("netLo"), "netHi": r0.get("netHi"),
              "termMin": min(nets) if nets else None,
              "termMax": max(nets) if nets else None,
              "n": len(approval_rows), "atTermLow": bool(nets and r0.get("net") == min(nets))}
    snap = find_latest_snapshot(outdir)
    hou = None
    if snap:
        try:
            hou = housing_summary(snap)
            hou["_snapshot"] = os.path.relpath(snap, outdir)
        except Exception as e:
            hou = {"_error": str(e)}
    out = {"fetchedAt": datetime.now(CST).isoformat(timespec="seconds"),
           "source": BASE, "taco": a, "approval": ap,
           "housing": hou, "housingSnapshot": snap}

    if write or as_json:
        os.makedirs(outdir, exist_ok=True)
        day = datetime.now(CST).strftime("%Y-%m-%d")
        p = os.path.join(outdir, f"digest-{day}.json")
        _dump(out, p)
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return out

    # ---------------- 人读版
    W = 78
    print("═" * W)
    print(f"ocmacro 定向取数证据卡 · 抓取于 {out['fetchedAt']}")
    print("═" * W)
    print(f"\n[1] TACO 川普压力指数（政策回撤压力存量）  源 {BASE}/dashboard/trump")
    print(f"    截至 {a['asOfDate']}  {a['valueLabel']}  状态「{a['status']['label']}」"
          f"    分位 {a['percentile']}")
    print(f"    {a['change20dLabel']} | 区间 {a['range'][0]} ~ {a['range'][1]}"
          f" | 峰值 {a['peak']['value']} @ {a['peak']['date']} | 样本 {a['sampleDays']} 交易日")
    print(f"    因子贡献拆解（水平贡献 / 20日变化贡献）：")
    for f in a["factors"]:
        k = f["key"]
        c = a["contributions"].get(k, 0) or 0
        ch = a["changeContributions"].get(k, 0) or 0
        mark = "  ← 本轮主导" if k == a["dominantDriver"] else ""
        print(f"      {f['label']:<12} {f['weightLabel']:>5}  "
              f"读数 {str(f['valueLabel']):>9}  压力 {str(f['pressureLabel']):>7}"
              f"  贡献 {c:>6.2f}  变化 {ch:>+6.2f}{mark}")
    if a["dominantDriver"]:
        print(f"    ▸ 本轮变化由「{a['dominantDriverLabel']}」主导，"
              f"占全部正向变化贡献 {a['dominantShare']}%")

    ct = a["conditional"]
    print(f"\n[2] 条件概率规则（现场复算 · 回撤日口径 · {ct['eventDays']} 个重大回撤事件日"
          f" / {ct['tradingDays']} 交易日）")
    print(f"    {'当日TACO':>10}{'5日':>8}{'10日':>8}{'20日':>8}{'样本日':>8}")
    for b in ct["buckets"]:
        p = b["p"]
        print(f"    {b['label']:>10}{str(p.get('5')) + '%':>8}"
              f"{str(p.get('10')) + '%':>8}{str(p.get('20')) + '%':>8}{b['n']:>8}")
    bs = ct["base"]
    print(f"    {'无条件基准':>10}{str(bs.get('5')) + '%':>8}"
          f"{str(bs.get('10')) + '%':>8}{str(bs.get('20')) + '%':>8}")
    print("    ▸ 用法：≥+5 起出现区分度，≥+8 时 20 日内几乎必然出现重大回撤；")
    print("      ≤+5 区间与基准无显著差异，**不得**据此判断「压力不大所以安全」。")
    print("    ▸ 它不是领先指标：重大事件发生时指数常处中位区间（压力是「施压进行时」的存量，")
    print("      回撤落地后存量被消耗 → 指数见顶回落 ≠ 风险解除）。")
    print("    ⚠️ 事件高度时间聚集，有效独立样本远小于朴素计数，仅供参照不作铁律。")

    if ap:
        gap = None
        if ap.get("net") is not None and ap.get("termMin") is not None:
            gap = round(ap["net"] - ap["termMin"], 2)
        print(f"\n[3] 净支持率  {ap['date']}  {ap['net']}% "
              f"({'⚠️ 任期最低' if ap['atTermLow'] else f'距任期最低 {gap}pp'}）"
              f"   任期区间 {ap['termMin']}% ~ {ap['termMax']}%  样本 {ap['n']}")
        print("    ▸ 40% 权重走「相对旧基数的反向变化」、60% 走「任期反向历史分位」——"
              "跌到低位区后边际增量衰减，支持率不再是 TACO 的主要驱动")

    print(f"\n[4] 最近重大回撤事件（回撤日口径，共 {len(a['events'])} 条）")
    for e in a["events"][:5]:
        print(f"    {e['rollbackDate']}  [{e['strength']}]  {e['topic']}")
        if e.get("implication"):
            print(f"        含义：{e['implication']}")

    if hou and "_error" not in hou:
        print(f"\n[5] 中国地产（本地快照 {hou['_snapshot']} · 数据期 {hou['period']}）")
        print(f"    70城二手房同比 {hou['secondHandYoy'].get('全国')}% / 新房同比 "
              f"{hou['newHouseYoy'].get('全国')}%")
        print(f"    二手房环比  全国 {hou['secondHandMom'].get('全国')}% | "
              f"一线 {hou['secondHandMom'].get('一线城市')}% | "
              f"二线 {hou['secondHandMom'].get('二线城市')}% | "
              f"三线 {hou['secondHandMom'].get('三线城市')}%")
        print(f"    同比上涨城市 {hou['citiesUp']}/{hou['citiesUp'] + hou['citiesDown']}"
              f"（下跌 {hou['citiesDown']}）")
        st = hou.get("momPositiveStreak") or {}
        if st:
            print(f"    环比连续为正月数：" +
                  " | ".join(f"{k} {v}月" for k, v in st.items()))
        bu = hou.get("bisChina") or {}
        if bu:
            print(f"    BIS 实际房价：{bu['entity']} 回撤 {bu['drawdownPct']}% "
                  f"距峰 {bu['quartersFromPeak']} 季（{bu['latestPeriod']}，"
                  f"归「{bu['class']}」）")
            print(f"      同类历史周期 n={bu['peerN']}：跌幅中位 {bu['peerDrawdownMedian']}%、"
                  f"下跌季数中位 {bu['peerDownQuartersMedian']}、"
                  f"收复用时中位 {bu['peerRecoveryQuartersMedian']} 季")
        for h in hou.get("highFreq", []):
            y = f"同比 {h['yoyPct']:+.1f}%" if h["yoyPct"] is not None else "同比 n/a"
            print(f"    30城高频成交 {h['scope']:<5} {h['latestDate']} "
                  f"4周均 {h['avg4w']:>6} 万㎡  {y}（基准 {h['baseDate']}）")
    else:
        print("\n[5] 中国地产：本地无快照 → 跑 `python3 ocmacro_feed.py snapshot` 获取")

    print(f"\n[6] 时效与限制")
    print(f"    TACO 数据截至 {a['asOfDate']}；地产为本地快照（非实时，见上）；"
          f"令牌型接口 TTL≈2h")
    print(f"    用途边界：本卡只提供「压力水平 + 条件概率 + 地产周期定位」三类事实，"
          f"不含方向性结论")
    print("═" * W)
    return out


# ----------------------------------------------------------------------------- 输出
def _dump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return os.path.getsize(path)


def cmd_trump(outdir):
    d = fetch_trump_dashboard()
    t = d["taco"]
    _dump(d, os.path.join(outdir, "trump_dashboard.json"))
    n = taco_csv(t, os.path.join(outdir, "taco_index_history.csv"))
    m = approval_csv(d["approval"]["rows"], os.path.join(outdir, "trump_approval.csv"))
    _dump(d["events"], os.path.join(outdir, "taco_events.json"))
    idx = t["index"]
    print(f"[TACO] {idx['asOfDate']} 指数 {idx['valueLabel']}  状态 {idx['status']['label']}"
          f"  ({idx['change20dLabel']})  方法版本 {t['methodologyVersion']}")
    print(f"       历史 {n} 点 (起 {t['history'][0]['date']}) · 支持率 {m} 点 · 事件 {len(d['events'])} 条")
    for f in t["factors"]:
        print(f"       - {f['shortLabel']:<10} 权重{f['weightLabel']:>5}  "
              f"读数 {f['valueLabel']:>10}  压力贡献 {f['pressureLabel']:>8}")
    print(f"       落地 {outdir}")


def cmd_truths(outdir, pages):
    d = fetch_truths(pages=pages)
    _dump(d, os.path.join(outdir, "truths.json"))
    src = (d["meta"] or {}).get("source") or {}
    print(f"[Truths] 取到 {d['count']} 条 · 源 {src.get('url')} · 最新 {src.get('latestDateLabel')}")
    for t in d["truths"][:8]:
        print(f"   {t.get('createdAtLabel')}  {t.get('headline')}")
    print(f"       落地 {outdir}")


def cmd_housing(outdir, deep):
    d = fetch_housing(deep=deep)
    _dump(d, os.path.join(outdir, "housing.json"))
    print(f"[地产] 令牌路径 {d['base']}")
    for k, v in d["datasets"].items():
        if "_error" in v:
            print(f"   {k:<26} ERROR {v['_error']}")
            continue
        extra = ""
        if "periods" in v:
            extra = f" {len(v['periods'])}期 {v['periods'][0]}→{v['periods'][-1]}"
        if "series" in v:
            extra += f" {len(v['series'])}序列"
        if "latestPeriod" in v:
            extra += f" 最新{v['latestPeriod']}"
        if "latestDate" in v:
            extra += f" 最新{v['latestDate']}"
        print(f"   {k:<26} OK{extra}")
    print(f"       落地 {outdir}")


def cmd_snapshot(outdir, pages):
    day = datetime.now(CST).strftime("%Y-%m-%d")
    dst = os.path.join(outdir, day)
    os.makedirs(dst, exist_ok=True)
    print(f"→ 快照目录 {dst}")
    cmd_trump(dst)
    cmd_truths(dst, pages)
    cmd_housing(dst, deep=True)


def cmd_brief():
    """只看 TACO 当前读数，不落盘。"""
    html = http_get(f"{BASE}/dashboard/trump").decode("utf-8", "ignore")
    payload = rsc_payload(html)
    blocks = find_json_objects(payload, '"methodologyVersion"')
    if not blocks:
        print("未取到数据")
        return
    t = max(blocks, key=len)
    idx, factors, hist = t["index"], t["factors"], t["history"]
    print(f"川普压力指数（TACO）  {idx['asOfDateLabel']}  {idx['valueLabel']}  {idx['status']['label']}")
    print(f"  {idx['change20dLabel']} · {idx['status']['description']}")
    print(f"  {'分项':<12}{'权重':>6}{'读数':>12}{'压力贡献':>10}")
    for f in factors:
        print(f"  {f['shortLabel']:<12}{f['weightLabel']:>6}{f['valueLabel']:>12}{f['pressureLabel']:>10}")
    vals = [h["value"] for h in hist]
    cur = vals[-1]
    rank = sum(1 for v in vals if v <= cur) / len(vals) * 100
    print(f"  当前 {cur} 在 {len(vals)} 个交易日中位于 {rank:.0f} 分位；"
          f"区间 {min(vals)} ~ {max(vals)}")
    peak = max(hist, key=lambda h: h["value"])
    print(f"  历史峰值 {peak['value']} 出现在 {peak['date']}")


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="MacroMargin ocmacro.com 公开数据抓取器")
    ap.add_argument("cmd", choices=["trump", "truths", "housing", "snapshot",
                                    "brief", "digest"])
    ap.add_argument("--out", default=os.path.join(HERE, "data"), help="输出目录")
    ap.add_argument("--pages", type=int, default=3, help="Truths 抓取页数（每页20条）")
    ap.add_argument("--deep", action="store_true", help="地产数据全量下载")
    ap.add_argument("--json", action="store_true",
                    help="digest：输出机器可读 JSON（并落盘 digest-<日期>.json）")
    ap.add_argument("--write", action="store_true",
                    help="digest：仅落盘 JSON，仍打印人读版")
    a = ap.parse_args()

    if a.cmd == "brief":
        cmd_brief()
        return
    if a.cmd == "digest":
        os.makedirs(a.out, exist_ok=True)
        cmd_digest(a.out, as_json=a.json, write=a.write)
        return
    os.makedirs(a.out, exist_ok=True)
    if a.cmd == "trump":
        cmd_trump(a.out)
    elif a.cmd == "truths":
        cmd_truths(a.out, a.pages)
    elif a.cmd == "housing":
        cmd_housing(a.out, a.deep)
    elif a.cmd == "snapshot":
        cmd_snapshot(a.out, a.pages)


if __name__ == "__main__":
    sys.exit(main())
