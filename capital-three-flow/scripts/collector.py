"""
资本三流 —— 数据采集器（2026-07 核实版）
========================================
数据源：akshare 封装的东方财富 / 新浪 / 金十等公开源。函数名已对照 akshare
当前 master 逐一核实（见 references/data_sources.md）。

已确认可用的采集项：
  - M2              macro_china_money_supply        （月）
  - 名义GDP         macro_china_gdp                 （季）
  - 外汇储备        macro_china_foreign_exchange_gold（月，取"国家外汇储备"）
  - 基础货币        macro_china_central_bank_balance （月，取"储备货币"）
  - 融资融券        macro_china_market_margin_sh     （日）
  - 大盘主力资金     stock_market_fund_flow           （日，取"主力净流入-净额"）
  - 人民币汇率      forex_spot_em                  （实时，过滤 USDCNY 取最新价/涨跌幅）
  - 板块资金流      stock_fund_flow_industry        （即时，取各行业"主力净流入-净额"算 HHI）

已确认【不可用】、自动降级：
  - 北向/南向净流量：akshare master 已移除（2024-08-19 交易所停更）
  - 社会融资规模：akshare master 无对应函数
  - 北向持仓：akshare 无聚合函数
  → 跨境流向改用"外汇储备变动"代理（即卢麒元三流中的"外汇储备变动"）。

设计原则：
  1. akshare 为可选依赖，未安装时相关项返回 None。
  2. 每个源独立 try/except，单点失败降级，绝不中断流水线。
  3. 本地缓存（data/cache/*.json）降低重复请求与限流风险。
  4. --demo 加载 scripts/sample_data.json，完全离线可跑。
  5. 缺失项记 None，由 calculator 重新归一化，绝不编造。
"""

import json
import os
import re
import sys
from datetime import date

import pandas as pd

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(SKILL_DIR, "data", "cache")
SAMPLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data.json")
os.makedirs(CACHE_DIR, exist_ok=True)


# ── 缓存 ────────────────────────────────────────────────────
def _cache_path(name):
    return os.path.join(CACHE_DIR, f"{name}.json")


def _load_cache(name):
    p = _cache_path(name)
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _save_cache(name, payload):
    try:
        with open(_cache_path(name), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


def _safe_float(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (ValueError, TypeError):
        return None


def _col(row, candidates):
    """在 DataFrame 的一行里，按候选关键词匹配列名取数。"""
    for c in row.index:
        for k in candidates:
            if k in str(c):
                return _safe_float(row[c])
    return None


def _date_col(df):
    """定位时间列（不同 akshare 表列名不一）。"""
    for c in ("日期", "统计时间", "月份", "时间"):
        if c in df.columns:
            return c
    return df.columns[0]


def _parse_period(val):
    """把各类时间标签解析为可排序的 Timestamp。
    支持：'2026年第1季度' / '2026年05月份'(中文) / '2026.06' / '2026.5' /
          '2026-07-08' / '2026/5'。"""
    s = str(val).strip()
    m = re.search(r"(\d{4})年第(\d)季度", s)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        return pd.Timestamp(year=y, month=(q - 1) * 3 + 1, day=1)
    m = re.search(r"(\d{4})年(\d{1,2})月", s)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    m = re.match(r"^(\d{4})[.\-/](\d{1,2})", s)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    return pd.NaT


def _sorted_df(df):
    """按时间列升序排序，保证 iloc[-1] 取到最新一期。
    注：akshare 部分表最新在前(money_supply/gdp/central_bank_balance)，
    部分最老在前(forex/margin)，统一排序避免取错行。"""
    dc = _date_col(df)
    try:
        s = df[dc].apply(_parse_period)
        if s.notna().any():
            return df.iloc[s.sort_values(na_position="first").index]
    except Exception:
        pass
    return df


# ── akshare 懒加载 ──────────────────────────────────────────
def _get_ak():
    try:
        import akshare as ak
        return ak
    except Exception:
        return None


# ── 各数据源（函数名已核实） ────────────────────────────────
def fetch_m2(ak, force=False):
    cached = None if force else _load_cache("m2")
    if cached:
        return cached
    if ak is None:
        return None
    try:
        df = ak.macro_china_money_supply()
        sdf = _sorted_df(df)
        last = sdf.iloc[-1]
        out = {
            "date": str(last.get("月份")),
            "m2": _col(last, ["货币和准货币(M2)-数量", "货币和准货币(M2)", "M2"]),
            "m2_yoy": _col(last, ["货币和准货币(M2)-同比增长", "货币和准货币(M2)-同比", "M2-同比", "同比"]),
            "unit": "亿元",
        }
        _save_cache("m2", out)
        return out
    except Exception as e:
        sys.stderr.write(f"[collector] m2 failed: {e}\n")
        return None


def fetch_gdp(ak, force=False):
    cached = None if force else _load_cache("gdp")
    if cached:
        return cached
    if ak is None:
        return None
    try:
        df = ak.macro_china_gdp()
        sdf = _sorted_df(df)
        last = sdf.iloc[-1]
        out = {"date": str(last.get("季度")),
               "value": _col(last, ["国内生产总值-绝对值", "国内生产总值"]),
               "unit": "亿元(季)"}
        _save_cache("gdp", out)
        return out
    except Exception as e:
        sys.stderr.write(f"[collector] gdp failed: {e}\n")
        return None


def fetch_forex(ak, force=False):
    """外汇储备（月）。取"国家外汇储备"，算环比变化。"""
    cached = None if force else _load_cache("forex")
    if cached:
        return cached
    if ak is None:
        return None
    try:
        df = ak.macro_china_foreign_exchange_gold()
        sdf = _sorted_df(df)
        last = sdf.iloc[-1]
        prev = sdf.iloc[-2] if len(sdf) > 1 else None
        val = _col(last, ["国家外汇储备"])
        pval = _col(prev, ["国家外汇储备"]) if prev is not None else None
        out = {
            "date": str(last.get("统计时间")),
            "reserve": val,
            "gold": _col(last, ["黄金储备"]),
            "change": (val - pval) if (val is not None and pval is not None) else None,
            "unit": "亿美元",
        }
        _save_cache("forex", out)
        return out
    except Exception as e:
        sys.stderr.write(f"[collector] forex failed: {e}\n")
        return None


def fetch_base_money(ak, force=False):
    """基础货币（月）。取央行货币当局资产负债表的"储备货币"。"""
    cached = None if force else _load_cache("base_money")
    if cached:
        return cached
    if ak is None:
        return None
    try:
        df = ak.macro_china_central_bank_balance()
        sdf = _sorted_df(df)
        last = sdf.iloc[-1]
        out = {"date": str(last.get("统计时间")),
               "base_money": _col(last, ["储备货币"]), "unit": "亿元"}
        _save_cache("base_money", out)
        return out
    except Exception as e:
        sys.stderr.write(f"[collector] base_money failed: {e}\n")
        return None


def fetch_margin(ak, force=False):
    """融资融券（日）。取 融资余额 / 融券余额 / 融资融券余额 及环比。
    原始单位=元，统一 ÷1e8 转亿元，与主力资金口径一致。"""
    cached = None if force else _load_cache("margin")
    if cached:
        return cached
    if ak is None:
        return None
    try:
        df = ak.macro_china_market_margin_sh()
        sdf = _sorted_df(df)
        last = sdf.iloc[-1]
        prev = sdf.iloc[-2] if len(sdf) > 1 else None
        financing = _col(last, ["融资余额"])
        securities = _col(last, ["融券余额"])
        total = _col(last, ["融资融券余额"])
        total_prev = _col(prev, ["融资融券余额"]) if prev is not None else None
        fin_buy = _col(last, ["融资买入额"])   # 微观杠杆流速代理
        YI = 1e8
        out = {
            "date": str(last.get("日期")),
            "financing": (financing / YI) if financing is not None else None,
            "securities": (securities / YI) if securities is not None else None,
            "total": (total / YI) if total is not None else None,
            "total_prev": (total_prev / YI) if total_prev is not None else None,
            "delta": ((total - total_prev) / YI) if (total is not None and total_prev is not None) else None,
            "fin_buy": (fin_buy / YI) if fin_buy is not None else None,  # 融资买入额(亿元)
            "unit": "亿元",
        }
        _save_cache("margin", out)
        return out
    except Exception as e:
        sys.stderr.write(f"[collector] margin failed: {e}\n")
        return None


def fetch_main_force(ak, force=False):
    """大盘主力资金净流入（日）。取"主力净流入-净额"（全市场，单位元）。"""
    cached = None if force else _load_cache("main_force")
    if cached:
        return cached
    if ak is None:
        return None
    try:
        df = ak.stock_market_fund_flow()
        last = df.iloc[-1]
        net = _col(last, ["主力净流入-净额"])
        # akshare 返回单位为元 → 转亿元
        net_yi = (net / 1e8) if net is not None else None
        out = {"date": str(last.get("日期")), "net_inflow": round(net_yi, 2) if net_yi else None,
               "unit": "亿元"}
        _save_cache("main_force", out)
        return out
    except Exception as e:
        sys.stderr.write(f"[collector] main_force failed: {e}\n")
        return None


def fetch_fx_rate(ak, force=False):
    """人民币汇率 USD/CNY（实时，东方财富外汇）。取"美元人民币"(USDCNY)最新价与涨跌幅。
    人民币贬值(最新价↑、涨跌幅>0)=外部压力↑，作为走资风险 CRI 的代理之一。"""
    cached = None if force else _load_cache("fx_rate")
    if cached:
        return cached
    if ak is None:
        return None
    try:
        df = ak.forex_spot_em()
        target = None
        for sym in ("USDCNY", "USDCNH"):
            row = df[df["代码"] == sym]
            if not row.empty:
                target = row.iloc[0]
                break
        if target is None:  # 退而求其次：按名称匹配"美元人民币"
            nm = df[df["名称"].astype(str).str.contains("美元人民币")]
            if not nm.empty:
                target = nm.iloc[0]
        if target is None:
            sys.stderr.write("[collector] fx_rate: 未找到 USDCNY 行\n")
            return None
        out = {
            "date": str(date.today()),
            "symbol": str(target.get("代码")),
            "name": str(target.get("名称")),
            "rate": _safe_float(target.get("最新价")),
            "change_pct": _safe_float(target.get("涨跌幅")),
            "unit": "USD/CNY",
        }
        _save_cache("fx_rate", out)
        return out
    except Exception as e:
        sys.stderr.write(f"[collector] fx_rate failed: {e}\n")
        return None


def fetch_sector_flow(ak, force=False):
    """板块（行业）资金流（同花顺）。取各行业"主力净流入-净额"，供 HHI 细分层级集中度。
    HHI 为无量纲比值，行业净流入的单位(元/万元/亿)不影响集中度计算。"""
    cached = None if force else _load_cache("sector_flow")
    if cached:
        return cached
    if ak is None:
        return None
    try:
        df = ak.stock_fund_flow_industry(symbol="即时")
        net_col = None
        for c in df.columns:
            s = str(c)
            # 同花顺行业资金流净额列名为「净额」；历史/其它口径可能是「主力净流入-净额」
            if "净额" in s and "占比" not in s:
                net_col = c
                break
        name_col = None
        for c in df.columns:
            if str(c) in ("名称", "行业", "板块"):
                name_col = c
                break
        in_col = next((c for c in df.columns if "流入资金" in str(c)), None)
        out_col = next((c for c in df.columns if "流出资金" in str(c)), None)
        pct_col = next((c for c in df.columns if "涨跌幅" in str(c)), None)
        if net_col is None or name_col is None:
            sys.stderr.write("[collector] sector_flow: 未识别到行业/净额列\n")
            return None
        sectors = []
        gross = 0.0
        for _, r in df.iterrows():
            v = _safe_float(r[net_col])
            if v is None:
                continue
            din = _safe_float(r[in_col]) if in_col else None
            dout = _safe_float(r[out_col]) if out_col else None
            dpct = _safe_float(r[pct_col]) if pct_col else None
            gross += (abs(din or 0) + abs(dout or 0))
            sectors.append({"name": str(r[name_col]), "net": v,
                            "pct": dpct, "inflow": din, "outflow": dout})
        out = {"date": str(date.today()), "sectors": sectors,
               "gross": gross,
               "unit_note": "原始单位不一，HHI 无量纲不依赖单位", "count": len(sectors)}
        _save_cache("sector_flow", out)
        return out
    except Exception as e:
        sys.stderr.write(f"[collector] sector_flow failed: {e}\n")
        return None


# ── 向心坍缩全球风险指标（卢麒元 M3 扩展）────────────────────
# 套息→美元流动性→地缘能源→非美压力→风险情绪 五级早期预警指标。
# 数值项 best-effort 从 akshare 拉取；定性/催化项来自 data/qualitative_state.json。
QUALITATIVE_PATH = os.path.join(SKILL_DIR, "data", "qualitative_state.json")


def _load_qualitative_state() -> dict:
    """加载定性/催化项状态（用户或订阅源维护）。缺失时全部置 False。
    结构：cftc_jpy_unwind(bool) / geopolitical{hormuz,mideast_export_cut,us_iran_conflict} /
          transmission{northbound_4w_outflow,cny_weak_but_pboc,domestic_credit_tightening}"""
    default = {
        "cftc_jpy_unwind": False,
        "geopolitical": {"hormuz": False, "mideast_export_cut": False, "us_iran_conflict": False},
        "transmission": {"northbound_4w_outflow": False, "cny_weak_but_pboc": False,
                         "domestic_credit_tightening": False},
    }
    try:
        if os.path.exists(QUALITATIVE_PATH):
            with open(QUALITATIVE_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            merged = json.loads(json.dumps(default))
            for k, v in (user or {}).items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged
    except Exception:
        pass
    return default


def _get_usdjpy(ak):
    df = ak.forex_spot_em()
    row = df[df["代码"] == "USDJPY"]
    if not row.empty:
        return _safe_float(row.iloc[0].get("最新价"))
    nm = df[df["名称"].astype(str).str.contains("美元日元")]
    if not nm.empty:
        return _safe_float(nm.iloc[0].get("最新价"))
    return None


def _get_us10y(ak):
    df = ak.bond_zh_us_rate()
    last = df.iloc[-1]
    for c in last.index:
        if "美国" in str(c) and ("10年" in str(c) or "10Y" in str(c) or "十年" in str(c)):
            return _safe_float(last[c])
    return None


def _get_jp10y(ak):
    try:
        df = ak.macro_japan_yield_curve()
        last = df.iloc[-1]
        for c in last.index:
            if "10" in str(c):
                return _safe_float(last[c])
    except Exception:
        pass
    return None


def _get_dxy(ak):
    try:
        df = ak.macro_usa_dollar_index()
        last = df.iloc[-1]
        for c in (last.get("美元指数"), last.get("close"), last.get(df.columns[-1])):
            v = _safe_float(c)
            if v is not None:
                return v
    except Exception:
        pass
    return None


def _get_brent(ak):
    try:
        df = ak.macro_oil_brent()
        last = df.iloc[-1]
        v = _safe_float(last.get("value") or last.get(df.columns[-1]))
        return v
    except Exception:
        pass
    return None


def _get_usdkrw(ak):
    df = ak.forex_spot_em()
    row = df[df["代码"] == "USDKRW"]
    if not row.empty:
        return _safe_float(row.iloc[0].get("最新价"))
    nm = df[df["名称"].astype(str).str.contains("美元韩元")]
    if not nm.empty:
        return _safe_float(nm.iloc[0].get("最新价"))
    return None


def _get_vix(ak):
    try:
        df = ak.stock_us_spot_em()
        row = df[df["名称"].astype(str).str.contains("VIX")]
        if not row.empty:
            v = _safe_float(row.iloc[0].get("最新价") or row.iloc[0].get("涨跌幅"))
            return v
    except Exception:
        pass
    return None


def fetch_global_collapse_risk(ak, force=False):
    """向心坍缩全球风险指标（卢麒元 M3 扩展）。
    尝试从 akshare 拉取全球宏观指标，失败/无源项优雅降级（记 None + status），绝不编造。
    定性/催化项来自 qualitative_state.json。
    返回 {"as_of", "indicators":{key:{value,source,status}}, "qualitative":{...}, "akshare":bool}。"""
    cached = None if force else _load_cache("global_collapse_risk")
    if cached:
        return cached
    if ak is None:
        return {"as_of": str(date.today()), "indicators": {}, "qualitative": _load_qualitative_state(),
                "akshare": False}

    indicators = {}
    # 数值型（有免费 akshare 候选源，best-effort）
    attempts = {
        "usdjpy": (_get_usdjpy, "forex_spot_em(USDJPY)"),
        "us10y": (_get_us10y, "bond_zh_us_rate(美10Y)"),
        "jgb10y": (_get_jp10y, "macro_japan_yield_curve(10Y)"),
        "dxy": (_get_dxy, "macro_usa_dollar_index"),
        "brent": (_get_brent, "macro_oil_brent"),
        "usdkrw": (_get_usdkrw, "forex_spot_em(USDKRW)"),
        "vix": (_get_vix, "stock_us_spot_em(VIX)"),
    }
    for key, (fn, src) in attempts.items():
        try:
            val = fn(ak)
            indicators[key] = {"value": val, "source": src, "status": "live" if val is not None else "missing"}
        except Exception as e:
            indicators[key] = {"value": None, "source": src, "status": "missing", "error": str(e)}

    # 美日利差 = 美10Y − 日10Y（需两者均可得）
    try:
        us = indicators.get("us10y", {}).get("value")
        jp = indicators.get("jgb10y", {}).get("value")
        if us is not None and jp is not None:
            indicators["us_jp_spread"] = {"value": round(us - jp, 2), "source": "us10y − jgb10y", "status": "live"}
        else:
            indicators["us_jp_spread"] = {"value": None, "source": "us10y − jgb10y", "status": "missing"}
    except Exception:
        indicators["us_jp_spread"] = {"value": None, "source": "us10y − jgb10y", "status": "missing"}

    # 需专业/订阅源的数值项（FRA-OIS）—— 标记 manual，待人工/订阅源补全
    indicators["fra_ois"] = {"value": None, "source": "需专业源(暂手动)", "status": "manual"}

    out = {"as_of": str(date.today()), "indicators": indicators,
           "qualitative": _load_qualitative_state(), "akshare": True}
    _save_cache("global_collapse_risk", out)
    return out


# ── 汇总 ────────────────────────────────────────────────────
def collect(demo=False, force=False) -> dict:
    if demo:
        if os.path.exists(SAMPLE_PATH):
            with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["as_of"] = str(date.today())
            data["demo"] = True
            return data
        sys.stderr.write("[collector] sample_data.json not found, falling back to live.\n")

    ak = _get_ak()
    if ak is None:
        sys.stderr.write("[collector] akshare 未安装；仅能返回缓存。安装：pip install akshare\n")

    return {
        "as_of": str(date.today()),
        "demo": False,
        "m2": fetch_m2(ak, force),
        "gdp": fetch_gdp(ak, force),
        "forex": fetch_forex(ak, force),
        "base_money": fetch_base_money(ak, force),
        "margin": fetch_margin(ak, force),
        "main_force": fetch_main_force(ak, force),
        "fx_rate": fetch_fx_rate(ak, force),
        "sector_flow": fetch_sector_flow(ak, force),
        # 向心坍缩全球风险早期预警指标（卢麒元 M3 扩展）
        "global_collapse_risk": fetch_global_collapse_risk(ak, force),
        # 明确标注已移除/不可用的项
        "north_flow": None,
        "north_flow_note": "北向净流量自2024-08-19起交易所停更，akshare已移除该接口；跨境流向改用外汇储备变动代理。",
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    print(json.dumps(collect(demo=args.demo, force=args.force), ensure_ascii=False, indent=2, default=str))
