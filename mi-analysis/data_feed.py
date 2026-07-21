"""
data_feed.py — Mi姐框架行情数据层
=================================
沙箱实测：东方财富被网络层掐断；腾讯K线返回空；新浪 getKLineData 可达。
- 日线: 新浪 scale=240, datalen 可拉到 ~1700 根 (约 2019-07 起)
- 周线: 新浪 scale=1200
- 月线: 由日线 pandas resample('M') 推导（新浪不支持 2400）
注：沙箱对股票API有硬性通过率上限，全市场扫描须在本机运行。
"""
import json
import os
import pickle
import ssl
import time
import urllib.request
from typing import Optional

import pandas as pd

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")


def _cache_path(code: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{code}.pkl")


def _load_cache(code: str, max_age_days: int):
    p = _cache_path(code)
    if os.path.exists(p) and (time.time() - os.path.getmtime(p)) < max_age_days * 86400:
        try:
            with open(p, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None
    return None


def _save_cache(code: str, obj):
    try:
        with open(_cache_path(code), "wb") as f:
            pickle.dump(obj, f)
    except Exception:
        pass

SINA = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"


def _get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout, context=CTX).read().decode("utf-8")


def fetch_daily(code: str, datalen: int = 2000) -> pd.DataFrame:
    """日线 OHLCV。code 形如 sh600519 / sz000001。"""
    url = f"{SINA}?symbol={code}&scale=240&ma=no&datalen={datalen}"
    rows = json.loads(_get(url))
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["day"])
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df = df[["date", "open", "high", "low", "close", "volume"]].sort_values("date").reset_index(drop=True)
    return df


def fetch_weekly(code: str, datalen: int = 400) -> pd.DataFrame:
    url = f"{SINA}?symbol={code}&scale=1200&ma=no&datalen={datalen}"
    rows = json.loads(_get(url))
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["day"])
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df = df[["date", "open", "high", "low", "close", "volume"]].sort_values("date").reset_index(drop=True)
    return df


def fetch_ohlcv(code: str, use_cache: bool = True, max_age_days: int = 7) -> dict:
    """返回 {daily, weekly, monthly} 三个 DataFrame。带本地缓存，支持离线/定时跑。"""
    if use_cache:
        cached = _load_cache(code, max_age_days)
        if cached is not None:
            return cached
    daily = fetch_daily(code)
    weekly = fetch_weekly(code)
    # 月线由日线重采样
    d = daily.set_index("date")
    monthly = d.resample("ME").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna().reset_index()
    out = {"daily": daily, "weekly": weekly, "monthly": monthly}
    if use_cache:
        _save_cache(code, out)
    return out


def fetch_universe(codes: list, sleep: float = 0.2) -> dict:
    """批量拉取，返回 {code: ohlcv_dict}；失败的 code 不计入。"""
    out = {}
    for c in codes:
        try:
            out[c] = fetch_ohlcv(c)
        except Exception as e:
            print(f"  [skip] {c}: {e}")
        time.sleep(sleep)
    return out


if __name__ == "__main__":
    d = fetch_ohlcv("sh600519")
    print("daily", len(d["daily"]), d["daily"]["date"].iloc[0].date(), "->", d["daily"]["date"].iloc[-1].date())
    print("weekly", len(d["weekly"]))
    print("monthly", len(d["monthly"]))
