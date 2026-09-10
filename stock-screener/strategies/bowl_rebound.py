"""
碗口反弹策略（右侧·上升趋势中的回踩）

来源：GitHub Dzy-HW-XD/a-share-quant-selector（碗口反弹 / 通达信公式移植），
      2026-08-30 移植进蔡森 skill 体系，并做三处改造：
  ① 由"布尔入选"改为"连续打分"，便于与破底翻等策略做横向加权排序；
  ② 市值门槛改用新浪日K自带的流通股本计算，省掉一次额外请求；
  ③ 补出止损位（多空线下方 1×ATR）与目标位（前高），因为原仓库只管选不管卖。

—— 它和「破底翻」是互补的两种不同位置 ——
  破底翻：左侧。创新低后翻回，赌的是底部反转（弱势股的超跌反弹）。
  碗口反弹：右侧。上升趋势中回踩到支撑，赌的是趋势延续（强势股的回调结束）。
  同一只票若被两个策略同时命中，说明"底部结构已成立 + 趋势已转多"，是强信号。

指标定义：
  知行短期趋势线 = EMA(EMA(CLOSE,10),10)
  知行多空线     = (MA14 + MA28 + MA57 + MA114) / 4

参数取自原仓库 config/strategy_params.yaml 的实际值（N=2, M=30, J_VAL=20），
而非 strategy/bowl_rebound.py 里的类默认参数（N=4, M=15, J_VAL=30）——
后者只在未加载 yaml 时生效，实际运行用的是 yaml 的值。二者差异极大：
按类默认值跑，实测 150 只样本里只有 1 只过得了"放量阳线"那一关。
"""
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .indicators import MA, EMA, KDJ, ATR, zhixing_short_trend, zhixing_bull_bear

DEFAULT_PARAMS = {
    "N": 2,             # 放量倍数：成交量 >= 前一日 × N（yaml 实际值 2，非源码默认 4）
    "M": 30,            # 回溯天数：M 天内出现过关键放量阳线即可（yaml 实际值 30）
    # 原仓库用「总市值 40 亿」做门槛。这里改用「近20日日均成交额 ≥ 1 亿元」：
    # ① 新浪日K不返回股本，取市值需额外请求；
    # ② 成交额比市值更直接地代表"能否从容进出"，才是这个门槛真正想管的事。
    "AMT": 100_000_000,
    "J_VAL": 20,        # KDJ 的 J 值上限（超卖阈值，yaml 实际值 20）
    "duokong_pct": 3,   # 分类用：价格距多空线 ±3%
    "short_pct": 2,     # 分类用：价格距短期趋势线 ±2%
    "M1": 14, "M2": 28, "M3": 57, "M4": 114,   # 多空线四条均线周期
    "min_bars": 150,    # 最少 K 线数量（多空线要 MA114，不够则失真）
}


def _classify(close, short_trend, bull_bear, duokong_pct, short_pct):
    """
    返回 (分类名, 优先级) —— 优先级数字越小越靠前。
    回落碗中：价格夹在多空线与短期趋势线之间（趋势未破、踩到支撑，最强）。
    靠近多空线：价格贴着多空线 ±duokong_pct%。
    靠近短期线：价格贴着短期趋势线 ±short_pct%。
    """
    if bull_bear <= close <= short_trend:
        return "回落碗中", 1
    if abs(close - bull_bear) / bull_bear * 100 <= duokong_pct:
        return "靠近多空线", 2
    if abs(close - short_trend) / short_trend * 100 <= short_pct:
        return "靠近短期趋势线", 3
    return None, 99


def detect_bowl_rebound(df: pd.DataFrame,
                        code: str = "",
                        name: str = "",
                        params: Optional[Dict] = None) -> Optional[Dict]:
    """
    输入：日K DataFrame（date/open/high/low/close/volume/amount/outstanding_share/turnover）
    输出：命中则返回信号 dict，否则 None
    """
    p = {**DEFAULT_PARAMS, **(params or {})}
    if df is None or len(df) < p["min_bars"]:
        return None

    d = df.reset_index(drop=True).copy()
    for c in ("open", "high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if d[["open", "high", "low", "close", "volume"]].isna().any().any():
        return None

    close, vol = d["close"], d["volume"]
    n = len(d)

    # ---- 指标 ----
    d["short_trend"] = zhixing_short_trend(close)
    d["bull_bear"] = zhixing_bull_bear(close, p["M1"], p["M2"], p["M3"], p["M4"])
    kdj = KDJ(d)
    d["J"] = kdj["J"]
    d["atr"] = ATR(d)

    c = float(close.iloc[-1])
    st = float(d["short_trend"].iloc[-1])
    bb = float(d["bull_bear"].iloc[-1])
    j = float(d["J"].iloc[-1])
    atr = float(d["atr"].iloc[-1])

    # ---- 硬条件 1：上升趋势（短期线必须在多空线上方）----
    if not st > bb:
        return None

    # ---- 硬条件 2：M 天内出现过「放量阳线」----
    m = int(p["M"])
    seg = d.iloc[-m:] if n >= m else d
    vol_ratio_series = seg["volume"] / seg["volume"].shift(1)
    is_yang = seg["close"] > seg["open"]
    surge = (vol_ratio_series >= float(p["N"])) & is_yang
    if not surge.any():
        return None
    surge_pos = int(np.where(surge.values)[0][-1])          # 最近一次放量阳线在 seg 内的位置
    surge_idx = n - len(seg) + surge_pos
    days_since_surge = n - 1 - surge_idx
    vr_surge = float(vol_ratio_series.iloc[surge_pos])

    # 数据质量门：放量倍数超过 20 倍基本不是"资金进场"，而是复牌、除权、
    # 停牌恢复等技术性跳变。这类票会被误判成最强信号（打分项满分），必须剔除。
    if vr_surge > 20:
        return None

    # ---- 硬条件 3：回顾期内「最大成交量那天如果是阴线」→ 剔除（大资金出逃）----
    max_vol_pos = int(np.argmax(seg["volume"].values))
    if not bool(is_yang.iloc[max_vol_pos]):
        return None

    # ---- 硬条件 4：J 值处于低位（超卖）----
    if not (j <= float(p["J_VAL"])):
        return None

    # ---- 硬条件 5：分类命中其一 ----
    cat, prio = _classify(c, st, bb, p["duokong_pct"], p["short_pct"])
    if cat is None:
        return None

    # ---- 硬条件 6：流动性门槛（近20日日均成交额）----
    amt20 = float((close * vol).iloc[-20:].mean())
    if amt20 < p["AMT"]:
        return None

    # ================= 打分（0-100）=================
    score = 40.0
    # 分类优先级：回落碗中 +12 / 靠近多空线 +7 / 靠近短期线 +4
    score += {1: 12, 2: 7, 3: 4}[prio]

    # J 值越低越超卖：J<=0 满分
    if j <= 0:
        score += 12
    elif j <= 10:
        score += 9
    elif j <= 20:
        score += 5

    # 放量强度：倍数越高越说明资金进场坚决
    if vr_surge >= 6:
        score += 10
    elif vr_surge >= 4:
        score += 7
    elif vr_surge >= 3:
        score += 4

    # 放量阳线距今越近越好（新鲜度）
    if days_since_surge <= 2:
        score += 8
    elif days_since_surge <= 5:
        score += 5
    elif days_since_surge <= 9:
        score += 2

    # 趋势强度：短期线高出多空线的幅度（越大越健康，但过大会透支 → 封顶）
    trend_spread = (st - bb) / bb * 100
    score += min(trend_spread * 1.5, 10)

    # 近 20 日回撤（回踩得越充分、但没跌破多空线，越好）
    hi20 = float(d["high"].iloc[-20:].max())
    drawdown = (1 - c / hi20) * 100 if hi20 > 0 else 0
    if 5 <= drawdown <= 18:
        score += 6
    elif 18 < drawdown <= 28:
        score += 3

    score = round(min(score, 100), 1)

    # ---- 交易参数：止损 / 目标 ----
    stop = round(min(bb * 0.98, c - atr), 2)          # 多空线下方2% 或 1×ATR，取更近者
    hi60 = float(d["high"].iloc[-60:].max())
    target = round(hi60, 2)
    risk = c - stop
    reward = target - c
    rr = round(reward / risk, 2) if risk > 0 else None

    return {
        "代码": code,
        "名称": name,
        "策略": "碗口反弹",
        "分类": cat,
        "最新价": round(c, 2),
        "J值": round(j, 1),
        "短期趋势线": round(st, 2),
        "多空线": round(bb, 2),
        "趋势强度%": round(trend_spread, 2),
        "放量倍数": round(vr_surge, 2),
        "放量距今": days_since_surge,
        "近20日回撤%": round(drawdown, 1),
        "距年高跌幅%": round((1 - c / float(d["high"].max())) * 100, 1),
        "日均成交额亿": round(amt20 / 1e8, 2),
        "止损位": stop,
        "目标位": target,
        "盈亏比": rr,
        "score": score,
    }
