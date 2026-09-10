"""
技术指标库 —— 通达信口径的纯 pandas 实现

所有函数输入/output 均为 pandas Series，按日期升序排列（与 data_source 一致）。
刻意不依赖 TA-Lib（沙箱安装困难），全部手写，行为与通达信公式对齐。
"""
import numpy as np
import pandas as pd


def MA(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=1).mean()


def EMA(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def SMA(s: pd.Series, n: int, m: int) -> pd.Series:
    """通达信 SMA(X,N,M) = (M*X + (N-M)*Y') / N，Y'为上一期值"""
    return s.ewm(alpha=m / n, adjust=False).mean()


def REF(s: pd.Series, n: int) -> pd.Series:
    return s.shift(n)


def LLV(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=1).min()


def HHV(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=1).max()


def KDJ(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """
    KDJ(9,3,3)。RSV = (C - LLV(L,n)) / (HHV(H,n) - LLV(L,n)) * 100
    K = SMA(RSV, m1, 1)；D = SMA(K, m2, 1)；J = 3K - 2D
    """
    low_n = LLV(df["low"], n)
    high_n = HHV(df["high"], n)
    rng = (high_n - low_n).replace(0, np.nan)
    rsv = ((df["close"] - low_n) / rng * 100).fillna(50)
    k = SMA(rsv, m1, 1)
    d = SMA(k, m2, 1)
    return pd.DataFrame({"K": k, "D": d, "J": 3 * k - 2 * d})


def zhixing_short_trend(close: pd.Series) -> pd.Series:
    """知行短期趋势线 = EMA(EMA(CLOSE,10),10)"""
    return EMA(EMA(close, 10), 10)


def zhixing_bull_bear(close: pd.Series, m1: int = 14, m2: int = 28,
                      m3: int = 57, m4: int = 114) -> pd.Series:
    """
    知行多空线 = (MA(m1) + MA(m2) + MA(m3) + MA(m4)) / 4

    ⚠️ 口径以源码实现为准，不要信源码顶部的文档注释：
       原仓库 bowl_rebound.py 的 docstring 写的是 MA5/10/20/30，
       但 calculate_zhixing_trend() 的实现与 config/strategy_params.yaml
       用的都是 14/28/57/114。实测也证明 14/28/57/114 才是真实运行口径。
       四条长均线意味着多空线反应很慢——它是"牛熊分界"，不是短期支撑。
    """
    return (MA(close, m1) + MA(close, m2) + MA(close, m3) + MA(close, m4)) / 4


def MACD(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    dif = EMA(close, fast) - EMA(close, slow)
    dea = EMA(dif, signal)
    return dif, dea, (dif - dea) * 2


def RSI(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    dn = (-delta).clip(lower=0)
    ru = up.ewm(alpha=1 / n, adjust=False).mean()
    rd = dn.ewm(alpha=1 / n, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def ATR(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """真实波幅，用于止损位测算"""
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (c.shift() - l).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()
