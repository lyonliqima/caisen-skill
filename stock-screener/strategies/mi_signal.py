"""
Mi姐「趋势·筹码·情绪」三维信号

复用桌面主副本 `mi-analysis/framework.py` 的 build_signals（不重写、不改动阈值），
本文件只负责：把统一的日K DataFrame 转换成 Mi姐框架要求的 ohlcv 结构
（周线由日线 resample 推导，省掉一次额外网络请求），再把决策结果折算成可与
破底翻/碗口反弹横向比较的分数。

Mi姐是「扣扳机」的那一环：趋势(A)+结构(B)+时机(C)+资金(D)+情绪(E) 全部对齐才买入。
所以它对全市场来说命中率很低 —— 这恰恰是它的价值：用极严的条件把假信号筛掉。
"""
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent.parent          # 蔡森 skill/
MI_PATH = BASE / "mi-analysis"
if str(MI_PATH) not in sys.path:
    sys.path.insert(0, str(MI_PATH))

try:
    from framework import build_signals, CONFIG      # type: ignore
    _MI_OK = True
except Exception:
    _MI_OK = False
    build_signals, CONFIG = None, {}

# 决策 → 分数映射（Mi姐只给 买入/退出/无 三态，这里细化成可比分数）
_DECISION_SCORE = {"买入": 100.0, "无": 0.0, "退出": -100.0}

# 模块状态的加分/减分（用于把「差一步就买入」的票也捞出来排序）
_TREND_BONUS = {"多": 10, "震荡": 0, "空": -20}
_STRUCTURE_BONUS = {"健康回调": 12, "整理": 4, "破位": -25, "顶部": -15}
_TIMING_BONUS = {"买": 15, "等": 2, "卖": -20}
_CAPITAL_BONUS = {"机构趋势": 12, "游资情绪": 8, "平稳": 2, "出货预警": -20}
_EMOTION_BONUS = {"启动期": 10, "加速期": 6, "退潮期": -4, "高潮期": -15, "冰点期": -8}


def _to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """日线 resample 成周线（Mi姐只需要周线的 close 来算 60 周线）"""
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    w = (d.set_index("date")
           .resample("W")
           .agg({"open": "first", "high": "max", "low": "min",
                 "close": "last", "volume": "sum"})
           .dropna(subset=["close"])
           .reset_index())
    return w


def detect_mi_signal(df: pd.DataFrame,
                     code: str = "",
                     name: str = "",
                     params: Optional[Dict] = None) -> Optional[Dict]:
    """
    输入统一日K DataFrame，输出 Mi姐模块状态 + 折算分。
    若 Mi姐框架不可用或数据长度不足，返回 None。
    """
    if not _MI_OK or df is None or len(df) < 260:
        return None

    d = df.reset_index(drop=True).copy()
    for c in ("open", "high", "low", "close", "volume"):
        if c not in d.columns:
            return None
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if d[["open", "high", "low", "close", "volume"]].isna().any().any():
        return None

    # ⚠️ 必须把 date 统一成 datetime。
    # module_A 里做的是 _weekly_ma60(weekly).reindex(df["date"])，
    # 若 daily 的 date 是字符串而 weekly 是 Timestamp，reindex 结果全是 NaN，
    # 于是 bull 条件恒 False —— 表现为"全市场一只多头都没有"，且不会报错，极难发现。
    d["date"] = pd.to_datetime(d["date"])

    try:
        ohlcv = {"daily": d, "weekly": _to_weekly(d)}
        sig = build_signals(ohlcv)
    except Exception:
        return None

    if sig is None or len(sig) == 0:
        return None

    r = sig.iloc[-1]
    decision = str(r.get("decision", "无"))
    trend = str(r.get("trend"))
    structure = str(r.get("structure"))

    # —— 命中门槛 ——
    # Mi姐的价值在于"严"：条件全对齐才叫买入。若把 decision=="无" 的票也放进来，
    # 它就会退化成一个噪声源，把综合排名稀释掉。所以只有两种票算命中：
    #   ① decision == "买入"（条件全中）
    #   ② 趋势=多 且 结构=健康回调（差临门一脚，值得进观察名单，但会自然排在后排）
    if decision == "退出":
        return None
    if decision != "买入" and not (trend == "多" and structure == "健康回调"):
        return None

    # 折算分：以决策为主锚，模块状态为辅
    score = _DECISION_SCORE.get(decision, 0.0)
    score += _TREND_BONUS.get(str(r.get("trend")), 0)
    score += _STRUCTURE_BONUS.get(str(r.get("structure")), 0)
    score += _TIMING_BONUS.get(str(r.get("timing")), 0)
    score += _CAPITAL_BONUS.get(str(r.get("capital")), 0)
    score += _EMOTION_BONUS.get(str(r.get("emotion")), 0)

    close = float(d["close"].iloc[-1])
    ma20 = float(pd.Series(d["close"]).rolling(20).mean().iloc[-1])
    ma20_dist = (close - ma20) / ma20 * 100 if ma20 else 0.0

    return {
        "代码": code,
        "名称": name,
        "策略": "Mi姐三维",
        "决策": decision,
        "趋势": trend,
        "结构": structure,
        "时机": str(r.get("timing")),
        "资金": str(r.get("capital")),
        "情绪": str(r.get("emotion")),
        "建议单票仓位%": round(float(r.get("single_pct", 0)) * 100, 1),
        "建议总仓位%": round(float(r.get("total_pct", 0)) * 100, 1),
        "最新价": round(close, 2),
        "MA20": round(ma20, 2),
        "距MA20%": round(ma20_dist, 2),
        # 止损沿用 Mi姐 C 模块的口径：破 20 日线离场，或浮亏 6% 硬止损
        "止损位": round(min(ma20 * 0.99, close * 0.94), 2),
        "score": round(score, 1),
    }
