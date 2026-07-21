"""
framework.py — Mi姐「趋势·筹码·情绪」三维分析框架（可运行版）
=============================================================
把文集里的口语经验 operationalize 成数值阈值。所有阈值集中在 CONFIG，
便于回测后调参。模块：A 趋势 / B 结构 / C 时机 / D 资金筹码 / E 情绪 / F 仓位 / G 宏观(简化)。

约定：价格涨=红、跌=绿（A股习惯）。信号基于日线（小周期60分在实时扫描时用，回测以日线近似）。
"""
from typing import Dict

import numpy as np
import pandas as pd

# ============================================================
#  CONFIG —— 全部数值阈值集中此处（填阈值结果）
# ============================================================
CONFIG = {
    # —— 模块A 趋势（大周期方向）——
    "A": {
        "ma_short": 5, "ma_mid": 10, "ma_long": 20,
        "ma_quarter": 60, "ma_year": 250,        # 年线
        "week_ma": 60,                            # 周线60周线
        "bull_req_weekly": True,                  # 多头需周线>60周线
    },
    # —— 模块B 结构（中周期）——
    "B": {
        "pullback_lo": 0.97,   # 回踩区间下沿 = MA20 * 0.97
        "pullback_hi": 1.02,   # 回踩区间上沿 = MA20 * 1.02
        "pullback_vol": 0.70,  # 缩量阈值：量 < 0.7*MA20量 视为健康缩量
        "break_pct": 0.95,     # 破位：收盘 < MA20*0.95
        "break_vol": 1.20,     # 破位需放量确认：量 > 1.2*MA20量
        "top_away": 2.0,       # 顶部：收盘 > MA250*2.0（远离年线）
        "top_rsi": 80,         # 且 RSI14 > 80
    },
    # —— 模块C 时机（小周期）——
    "C": {
        "buy_touch": 1.005,    # 回踩5日线不破：收盘 <= MA5*1.005
        "buy_vol_hi": 1.5,     # 买点量比上限（避免放量追高/恐慌）
        "stop_ma": 20,         # 破20日线离场
        "stop_loss": 0.06,     # 硬止损 浮亏6%
        "time_stop": 6,        # 持仓>6日不涨撤退
    },
    # —— 模块D 资金/筹码（proxy）——
    "D": {
        "ret_hot": 0.05,       # 单日涨幅>5% 视为异动
        "ret_dump": -0.04,     # 单日跌幅<-4%
        "vol_youzi": 2.5,      # 游资：量比>2.5
        "vol_ship": 1.5,       # 出货：量比>1.5
        "vol_inst_lo": 0.6, "vol_inst_hi": 1.5,  # 机构：量比平稳区间
    },
    # —— 模块E 情绪（个股proxy）——
    "E": {
        "z_hot": 1.0, "z_very": 1.5, "z_quiet": 0.5, "z_ice": 0.3,
        "ret20_up": 0.05, "ret20_strong": 0.10, "ret20_down": -0.03,
        "rsi_high": 80,
    },
    # —— 模块F 仓位/风控 ——
    "F": {
        "bull_single": 0.20, "bull_total": 0.85,
        "bear_single": 0.05, "bear_total": 0.30,
        "osc_single": 0.10, "osc_total": 0.50,
    },
}


# ============================================================
#  指标
# ============================================================
def compute_indicators(daily: pd.DataFrame, cfg: Dict = CONFIG) -> pd.DataFrame:
    df = daily.copy()
    c = cfg["A"]
    for n in [c["ma_short"], c["ma_mid"], c["ma_long"], c["ma_quarter"], c["ma_year"]]:
        df[f"ma{n}"] = df["close"].rolling(n, min_periods=n).mean()
    # RSI14
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
    rs = gain / (loss + 1e-9)
    df["rsi14"] = 100 - 100 / (1 + rs)
    # 量
    df["vol_ma20"] = df["volume"].rolling(20, min_periods=20).mean()
    df["vol_ratio"] = df["volume"] / (df["vol_ma20"] + 1e-9)
    df["ret"] = df["close"].pct_change()
    df["ret20"] = df["close"].pct_change(20)
    # 周线60周线（对齐到日线日期，前向填充）
    return df


def _weekly_ma60(weekly: pd.DataFrame, cfg: Dict) -> pd.Series:
    w = weekly.copy()
    w["wma60"] = w["close"].rolling(cfg["A"]["week_ma"], min_periods=cfg["A"]["week_ma"]).mean()
    s = w.set_index("date")["wma60"]
    return s


# ============================================================
#  模块A 趋势
# ============================================================
def module_A(df: pd.DataFrame, weekly: pd.DataFrame, cfg: Dict = CONFIG) -> pd.Series:
    c = cfg["A"]
    close = df["close"]; ma5 = df[f"ma{c['ma_short']}"]; ma10 = df[f"ma{c['ma_mid']}"]
    ma20 = df[f"ma{c['ma_long']}"]; ma60 = df[f"ma{c['ma_quarter']}"]; ma250 = df[f"ma{c['ma_year']}"]
    bull = (close > ma250) & (ma5 > ma10) & (ma10 > ma20) & (ma20 > ma60) & (ma60 > ma250)
    bear = (close < ma250) & (ma5 < ma10) & (ma10 < ma20) & (ma20 < ma60) & (ma60 < ma250)
    out = pd.Series("震荡", index=df.index)
    if cfg["A"]["bull_req_weekly"]:
        wma60 = _weekly_ma60(weekly, cfg).reindex(df["date"]).ffill().reset_index(drop=True)
        bull = bull & (close.values > wma60.values)
    out[bull.fillna(False)] = "多"
    out[bear.fillna(False)] = "空"
    return out


# ============================================================
#  模块B 结构
# ============================================================
def module_B(df: pd.DataFrame, cfg: Dict = CONFIG) -> pd.Series:
    c = cfg["B"]; ma20 = df[f"ma{cfg['A']['ma_long']}"]
    close = df["close"]; vol = df["volume"]; volma = df["vol_ma20"]; rsi = df["rsi14"]; ma250 = df[f"ma{cfg['A']['ma_year']}"]
    near = (close >= ma20 * c["pullback_lo"]) & (close <= ma20 * c["pullback_hi"])
    vol_low = vol < c["pullback_vol"] * volma
    pullback = near & vol_low
    brk = (close < ma20 * c["break_pct"]) & (vol > c["break_vol"] * volma)
    top = (close > ma250 * c["top_away"]) & (rsi > c["top_rsi"])
    out = pd.Series("其他", index=df.index)
    out[pullback.fillna(False)] = "健康回调"
    out[brk.fillna(False)] = "破位"
    out[top.fillna(False)] = "顶部"
    return out


# ============================================================
#  模块C 时机
# ============================================================
def module_C(df: pd.DataFrame, cfg: Dict = CONFIG) -> pd.Series:
    c = cfg["C"]; ma5 = df[f"ma{cfg['A']['ma_short']}"]; ma20 = df[f"ma{cfg['A']['ma_long']}"]
    close = df["close"]; vr = df["vol_ratio"]
    # 缩量回踩5日线买：收盘<=MA5*阈值 且 量比不过高（与模块B缩量健康回调一致）
    buy = (close <= ma5 * c["buy_touch"]) & (vr <= c["buy_vol_hi"])
    sell = close < ma20
    out = pd.Series("持", index=df.index)
    out[buy.fillna(False)] = "买"
    out[sell.fillna(False)] = "卖"
    return out


# ============================================================
#  模块D 资金/筹码（proxy）
# ============================================================
def module_D(df: pd.DataFrame, trend: pd.Series, cfg: Dict = CONFIG) -> pd.Series:
    c = cfg["D"]; vr = df["vol_ratio"]; ret = df["ret"]
    out = pd.Series("量化扰动", index=df.index)
    youzi = (vr > c["vol_youzi"]) & (ret > c["ret_hot"])
    ship = (trend == "空") & (ret > c["ret_hot"]) & (vr > c["vol_ship"])
    wash = (trend == "多") & (ret < c["ret_dump"]) & (vr < 1.0)
    inst = (trend == "多") & (vr >= c["vol_inst_lo"]) & (vr <= c["vol_inst_hi"]) & (ret > 0)
    out[inst.fillna(False)] = "机构趋势"
    out[youzi.fillna(False)] = "游资情绪"
    out[ship.fillna(False)] = "出货预警"
    out[wash.fillna(False)] = "洗盘"
    return out


# ============================================================
#  模块E 情绪（个股proxy，六阶段）
# ============================================================
def module_E(df: pd.DataFrame, trend: pd.Series, cfg: Dict = CONFIG) -> pd.Series:
    c = cfg["E"]; ma60 = df[f"ma{cfg['A']['ma_quarter']}"]
    vol = df["volume"]; vz = (vol - vol.rolling(20).mean()) / (vol.rolling(20).std() + 1e-9)
    vz = vz.fillna(0); rsi = df["rsi14"]; ret20 = df["ret20"]; close = df["close"]
    out = pd.Series("潜伏期", index=df.index)
    # 优先级：高潮 > 冰点 > 分化 > 加速 > 启动 > 潜伏
    start = (vz > c["z_hot"]) & (close > df[f"ma{cfg['A']['ma_long']}"]) & (ret20 > c["ret20_up"]) & (rsi < c["rsi_high"])
    acc = (vz > c["z_hot"]) & (ret20 > c["ret20_strong"]) & (close > ma60)
    div = (vz > c["z_hot"]) & (ret20 < c["ret20_down"])
    climax = (vz > c["z_very"]) & (rsi > c["rsi_high"])
    ice = (vz < c["z_ice"]) & (close < ma60) & (ret20 < 0)
    out[start.fillna(False)] = "启动期"
    out[acc.fillna(False)] = "加速期"
    out[div.fillna(False)] = "分化期"
    out[climax.fillna(False)] = "高潮期"
    out[ice.fillna(False)] = "冰点期"
    return out


# ============================================================
#  模块F 仓位
# ============================================================
def module_F(trend: pd.Series, cfg: Dict = CONFIG) -> pd.DataFrame:
    c = cfg["F"]
    single = trend.map({"多": c["bull_single"], "空": c["bear_single"], "震荡": c["osc_single"]})
    total = trend.map({"多": c["bull_total"], "空": c["bear_total"], "震荡": c["osc_total"]})
    return pd.DataFrame({"single_pct": single, "total_pct": total}, index=trend.index)


# ============================================================
#  决策矩阵
# ============================================================
def decision_matrix(trend, structure, timing, capital, emotion, cfg: Dict = CONFIG) -> pd.Series:
    enter = (
        (trend == "多")
        & (structure == "健康回调")
        & (timing == "买")
        & (capital.isin(["机构趋势", "游资情绪"]))
        & ((emotion.isin(["启动期", "加速期"])) | (capital == "机构趋势"))
    )
    exit_sig = (
        (trend == "空")
        | (structure == "破位")
        | (timing == "卖")
        | (capital == "出货预警")
        | (emotion.isin(["高潮期", "冰点期"]))
    )
    out = pd.Series("无", index=trend.index)
    out[enter.fillna(False)] = "买入"
    out[exit_sig.fillna(False)] = "退出"
    return out


# ============================================================
#  总装：返回带全部信号的 DataFrame
# ============================================================
def build_signals(ohlcv: Dict, cfg: Dict = CONFIG) -> pd.DataFrame:
    daily = compute_indicators(ohlcv["daily"], cfg)
    trend = module_A(daily, ohlcv["weekly"], cfg)
    structure = module_B(daily, cfg)
    timing = module_C(daily, cfg)
    capital = module_D(daily, trend, cfg)
    emotion = module_E(daily, trend, cfg)
    position = module_F(trend, cfg)
    decision = decision_matrix(trend, structure, timing, capital, emotion, cfg)
    sig = pd.DataFrame({
        "date": daily["date"], "close": daily["close"],
        "trend": trend, "structure": structure, "timing": timing,
        "capital": capital, "emotion": emotion,
        "single_pct": position["single_pct"], "total_pct": position["total_pct"],
        "decision": decision,
    })
    return sig


if __name__ == "__main__":
    from data_feed import fetch_ohlcv
    o = fetch_ohlcv("sh600519")
    s = build_signals(o)
    print(s.tail(8).to_string(index=False))
