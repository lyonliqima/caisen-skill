"""
蔡森破底翻（左侧·底部反转）

来源：桌面主副本 `蔡森破底翻量化筛选器.py`（v8 · 收盘价口径），
      2026-08-30 原样提炼为可复用模块，判定逻辑一字未改，只把输入从
      list[dict] 换成 DataFrame，并补出交易参数（止损/目标/盈亏比）。

铁律（来自蔡森）：盘中破但收盘站回 = 不算破。全部判定用收盘价口径。

两类入选：
  A 类「破底翻」：收盘价曾有效跌破前低 → 之后收盘翻回前低之上（经典破底翻）
  B 类「守住前低」：收盘全程未有效跌破 → 连续站稳前低 ≥ HOLD_DAYS 天（守而不破）
"""
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .indicators import ATR

DEFAULT_PARAMS = {
    "BOTTOM_PCT": 30,    # 历史分位上限%：只留过去1年收盘价处于底部 30% 的股票
    "BOTTOM_DROP": 40,   # 距年高跌幅下限%：必须距1年高点深跌超 40% 才算底部区域
    "HOLD_DAYS": 3,      # 「守住前低」最少连续站稳天数
    "BT": 0.03,          # 破底/守住容忍度（3%）：收盘跌破 前低×(1-3%) 才算有效破
    "min_bars": 60,
}


def detect_podifan(df: pd.DataFrame,
                   code: str = "",
                   name: str = "",
                   change_pct: float = 0.0,
                   params: Optional[Dict] = None) -> Optional[Dict]:
    p = {**DEFAULT_PARAMS, **(params or {})}
    if df is None or len(df) < max(40, p["min_bars"]):
        return None

    d = df.reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume"):
        if c not in d.columns:
            return None
    close = pd.to_numeric(d["close"], errors="coerce").to_numpy(dtype=float)
    high = pd.to_numeric(d["high"], errors="coerce").to_numpy(dtype=float)
    low = pd.to_numeric(d["low"], errors="coerce").to_numpy(dtype=float)
    volume = pd.to_numeric(d["volume"], errors="coerce").to_numpy(dtype=float)
    if np.isnan(close).any() or np.isnan(low).any():
        return None

    n = len(close)
    tc = close[-1]
    bt = p["BT"]

    # === 60日窗口：必须在 60 日高位之下（不能在山顶谈破底翻）===
    window = min(60, n)
    start = n - window
    ph60 = np.max(high[start:])
    pr60 = tc / ph60 if ph60 > 0 else 1
    if pr60 > 0.85:
        return None

    # === 长期历史低位过滤：破底翻只有在底部区域才有意义 ===
    long_high = np.max(high)
    drop_from_year_high = (1 - tc / long_high) * 100 if long_high > 0 else 0
    close_sorted = np.sort(close)
    percentile = np.searchsorted(close_sorted, tc) / n * 100
    if percentile > p["BOTTOM_PCT"]:
        return None
    if drop_from_year_high < p["BOTTOM_DROP"]:
        return None

    # === 局部极值找前低支撑 ===
    # 前低必须是「破底发生之前」的局部最低价，不能把破底新低误当支撑。
    # 判定：左侧 lk 根都更高 + 紧邻右侧 1 根更高（右侧不必全更高，
    # 否则破底K线会把前低挤出局部极小值集合）。
    lk = 5
    local_lows = []
    for i in range(start + lk, n):
        if not all(low[i] <= low[i - j] for j in range(1, lk + 1)):
            continue
        if i + 1 < n and low[i] > low[i + 1]:
            continue
        local_lows.append((i, low[i]))
    if not local_lows:
        return None

    cands = [(i, v) for i, v in local_lows if i < n - 2]   # 给「站稳」判断留空间
    if not cands:
        return None

    thr = 1 - bt
    best, best_conf = None, 0.0

    for sidx, sprice in cands:
        if (n - 1) <= sidx:
            continue
        seg_close = close[sidx + 1:]
        seg_low = low[sidx + 1:]
        min_close_after = float(np.min(seg_close))
        min_low_after = float(np.min(seg_low))

        # 必须曾触及/接近前低，否则「没破」是平凡(trivial)的
        if min_low_after > sprice * (1 + bt):
            continue

        # —— 收盘价口径（蔡森铁律）——
        broke = min_close_after < sprice * thr        # 收盘曾有效跌破前低
        close_held = min_close_after >= sprice * thr  # 收盘从未有效跌破
        recovered = tc >= sprice * thr                # 当前已站回前低之上
        if not recovered:
            continue

        hold_days = 0
        for i in range(n - 1, sidx, -1):
            if close[i] >= sprice * thr:
                hold_days += 1
            else:
                break

        if broke:
            # —— A 类：经典破底翻 ——
            bl = min_close_after
            bd = (sprice - bl) / sprice * 100
            bi = sidx + 1 + int(np.argmin(seg_close))
            # 破底之后不能再创更低的收盘（止损锚定前低，不锚定破底最低点）
            if bi < n - 1:
                if np.min(close[bi + 1:]) < bl * 0.98:
                    continue
            is_podi = True
        else:
            # —— B 类：守住前低 ——
            if not (close_held and hold_days >= p["HOLD_DAYS"]):
                continue
            bl, bd = sprice, 0.0
            is_podi = False

        # —— 评分 ——
        rc = (tc - sprice) / sprice * 100       # 站上前低的幅度
        dh = (1 - pr60) * 100                   # 距 60 日高跌幅
        vt = volume[-1]
        va5 = float(np.mean(volume[-6:-1])) if n >= 6 else float(np.mean(volume))
        vr = vt / va5 if va5 > 0 else 0
        ma5 = float(np.mean(close[-5:]))
        ma10 = float(np.mean(close[-10:]))
        ma20 = float(np.mean(close[-20:])) if n >= 20 else float(np.mean(close))

        if is_podi:
            conf = 60
            if vr > 1.5: conf += 4
            if vr > 2.0: conf += 2
            if bd > 5: conf += 3
            if rc > 3: conf += 3
            if pr60 < 0.60: conf += 3
            if percentile < 10: conf += 3
            elif percentile < 20: conf += 1
            if tc > ma5 > ma10: conf += 2
            if hold_days >= 3: conf += 3
            if hold_days >= 5: conf += 2
            typ = "破底翻"
        else:
            conf = 50 + min(hold_days, 8) * 2
            if vr > 1.5: conf += 3
            if percentile < 10: conf += 3
            elif percentile < 20: conf += 1
            if tc > ma5 > ma10: conf += 2
            if pr60 < 0.60: conf += 2
            typ = "守住前低"

        conf = min(conf, 80)

        if conf > best_conf:
            best_conf = conf
            # 交易参数：A类止损锚定前低（跌回前低下方即证伪）；B类同理
            atr_series = ATR(d)
            atr = float(atr_series.iloc[-1]) if len(atr_series) else (tc * 0.02)
            stop = round(min(sprice * (1 - bt), tc - atr), 2)
            hi60 = float(np.max(high[start:]))
            target = round(hi60, 2)
            risk = tc - stop
            rr = round((target - tc) / risk, 2) if risk > 0 else None

            best = {
                "代码": code,
                "名称": name,
                "策略": "破底翻",
                "类型": typ,
                "最新价": round(tc, 2),
                "今日涨幅%": round(change_pct, 2),
                "前低支撑": round(sprice, 2),
                "破底最低": round(bl, 2) if is_podi else None,
                "破底深度%": round(bd, 1) if is_podi else None,
                "收回幅度%": round(rc, 1),
                "站稳天数": hold_days,
                "距60日高跌幅%": round(dh, 1),
                "距年高跌幅%": round(drop_from_year_high, 1),
                "历史分位%": round(percentile, 1),
                "量比vs5日均": round(vr, 2),
                "MA5": round(ma5, 2),
                "MA20": round(ma20, 2),
                "止损位": stop,
                "目标位": target,
                "盈亏比": rr,
                "score": float(conf),
            }
    return best
