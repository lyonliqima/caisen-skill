"""
数据层 —— A股全市场行情获取（纯 urllib 直连 + 本地缓存）

🚨 为什么不用 akshare（2026-08-30 踩坑记录）
============================================
akshare 内部依赖 py_mini_racer（V8 JS 引擎）来跑部分接口的加密参数。
libmini_racer 是**线程不安全**的：一旦多线程并发调用，
进程会直接 FATAL 崩溃，报 `Check failed: !pool->IsInitialized()`，
且无法用 try/except 捕获（是 C++ 层 abort，不是 Python 异常）。
实测在 ThreadPoolExecutor(max_workers=2) 下就已经必崩。

因此本模块的数据获取全部改为 urllib 直连，只留一个 akshare 调用
（交易所官网代码表，主线程、单次、有缓存），并在其失败时给出明确报错。

数据源（均已在沙箱实测可达）
============================
  L1 代码表    akshare.stock_info_a_code_name（交易所官网） 5551 只，约 4 秒
  L2 实时行情  hq.sinajs.cn            批量查询，一次可取数百只，含成交额
  L3 个股日K   money.finance.sina.com.cn/CN_MarketData.getKLineData
               （与 mi-analysis/data_feed.py 同一条已验证通道）

东财全线不可达（ProxyError），已彻底放弃，不要再加回来。

缓存：日K按 symbol 存 cache/kline/<symbol>.csv，同日复用。
"""
import json
import os
import random
import ssl
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

BASE = Path(__file__).resolve().parent
CACHE_DIR = BASE / "cache" / "kline"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
      "Referer": "https://finance.sina.com.cn"}

SINA_KLINE = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
              "CN_MarketData.getKLineData")
SINA_HQ = "http://hq.sinajs.cn/list="

DEFAULT_LOOKBACK_DAYS = 620


def _get(url: str, timeout: int = 20, encoding: str = "utf-8") -> str:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout, context=CTX).read().decode(encoding, "ignore")


def _to_sina_symbol(code: str) -> str:
    """000001 -> sz000001 ; 600000 -> sh600000"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "9", "5", "11")):
        return "sh" + code
    if code.startswith(("00", "30", "12", "15", "16")):
        return "sz" + code
    if code.startswith(("4", "8")):
        return "bj" + code
    return "sh" + code


# ============================================================
#  L1 代码表
# ============================================================
def get_stock_list(use_cache_hours: int = 24) -> pd.DataFrame:
    """全市场 A 股代码表（code, name）。走交易所官网，不受东财/代理影响。"""
    cache_file = BASE / "cache" / "stock_list.csv"
    if cache_file.exists():
        age_h = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_h < use_cache_hours:
            try:
                df = pd.read_csv(cache_file, dtype={"code": str})
                if len(df) > 1000:
                    return df
            except Exception:
                pass

    import akshare as ak  # 唯一一处 akshare 调用：主线程、单次、无并发
    df = ak.stock_info_a_code_name()
    df["code"] = df["code"].astype(str).str.zfill(6)
    df = df[df["code"].str.match(r"^\d{6}$")].reset_index(drop=True)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_file, index=False)
    return df


# ============================================================
#  L2 实时行情快照
# ============================================================
def get_spot_snapshot(codes: Optional[List[str]] = None,
                      batch: int = 400,
                      use_cache_minutes: int = 30) -> Optional[pd.DataFrame]:
    """
    全市场实时快照。返回 DataFrame[code, name, 最新价, 昨收, 涨跌幅%, 成交量, 成交额]
    一次请求可查数百只，5551 只约 14 批，几秒完成。
    失败返回 None —— 调用方需降级为"不过滤，全量拉K线"。
    """
    cache_file = BASE / "cache" / "spot.csv"
    if codes is None:
        if cache_file.exists():
            age_min = (time.time() - cache_file.stat().st_mtime) / 60
            if age_min < use_cache_minutes:
                try:
                    df = pd.read_csv(cache_file, dtype={"code": str})
                    if len(df) > 1000:
                        return df
                except Exception:
                    pass
        codes = get_stock_list()["code"].tolist()

    rows = []
    symbols = [_to_sina_symbol(c) for c in codes]
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        try:
            txt = _get(SINA_HQ + ",".join(chunk), encoding="gbk")
        except Exception:
            continue
        for line in txt.strip().split("\n"):
            if '="' not in line:
                continue
            sym = line.split('hq_str_')[1].split('=')[0].strip()
            body = line.split('="')[1].rstrip('";')
            f = body.split(",")
            if len(f) < 10 or not f[0]:
                continue
            try:
                prev = float(f[2])
                last = float(f[3])
                rows.append({
                    "code": sym[2:],
                    "name": f[0],
                    "最新价": last,
                    "昨收": prev,
                    "涨跌幅%": round((last - prev) / prev * 100, 2) if prev > 0 else 0.0,
                    "成交量": float(f[8]),
                    "成交额": float(f[9]),
                })
            except (ValueError, IndexError):
                continue
        time.sleep(0.12)

    if not rows:
        return None
    df = pd.DataFrame(rows)
    df.to_csv(cache_file, index=False)
    return df


# ============================================================
#  L3 个股日K
# ============================================================
def _cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}.csv"


def _cache_fresh(path: Path, max_age_days: float = 1.0) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) / 86400 < max_age_days


def get_kline(code: str,
              datalen: int = DEFAULT_LOOKBACK_DAYS,
              use_cache: bool = True,
              retries: int = 3) -> Optional[pd.DataFrame]:
    """
    单只股票日K。返回 DataFrame[date, open, high, low, close, volume]，日期升序。
    datalen 是"根数"不是天数：620 根 ≈ 2.5 年交易日。
    """
    symbol = _to_sina_symbol(code)
    path = _cache_path(symbol)

    if use_cache and _cache_fresh(path):
        try:
            df = pd.read_csv(path)
            if len(df) > 60:
                return df
        except Exception:
            pass

    url = f"{SINA_KLINE}?symbol={symbol}&scale=240&ma=no&datalen={datalen}"
    for attempt in range(retries):
        try:
            rows = json.loads(_get(url))
            if not rows:
                return None
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["day"]).dt.strftime("%Y-%m-%d")
            for c in ["open", "high", "low", "close", "volume"]:
                df[c] = df[c].astype(float)
            df = (df[["date", "open", "high", "low", "close", "volume"]]
                  .sort_values("date").reset_index(drop=True))
            df.to_csv(path, index=False)
            return df
        except Exception:
            time.sleep(0.25 * (attempt + 1) + random.random() * 0.2)
    return None


def batch_get_kline(codes: List[str],
                    datalen: int = DEFAULT_LOOKBACK_DAYS,
                    workers: int = 12,
                    use_cache: bool = True,
                    progress_every: int = 300) -> Dict[str, pd.DataFrame]:
    """
    并发批量取日K。返回 {code: DataFrame}。
    纯 urllib 无 JS 引擎，线程安全，12 线程实测稳定。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    out: Dict[str, pd.DataFrame] = {}
    todo = list(dict.fromkeys(codes))

    def _one(c):
        return c, get_kline(c, datalen=datalen, use_cache=use_cache)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_one, c) for c in todo]
        done = 0
        for fu in as_completed(futs):
            code, df = fu.result()
            done += 1
            if df is not None and len(df) > 0:
                out[code] = df
            if progress_every and done % progress_every == 0:
                print(f"    ...已取 {done}/{len(todo)}，有效 {len(out)}", flush=True)
    return out


def clear_cache(older_than_days: float = 3.0) -> int:
    n = 0
    for p in CACHE_DIR.glob("*.csv"):
        if (time.time() - p.stat().st_mtime) / 86400 > older_than_days:
            p.unlink()
            n += 1
    return n


if __name__ == "__main__":
    print("== 代码表 ==")
    lst = get_stock_list()
    print(f"{len(lst)} 只")
    print("== 实时行情 ==")
    sp = get_spot_snapshot()
    print("失败" if sp is None else f"{len(sp)} 只，列: {list(sp.columns)}")
    print("== 日K ==")
    k = get_kline("000001")
    print("失败" if k is None else f"{len(k)} 行，最新 {k['date'].iloc[-1]} 收 {k['close'].iloc[-1]}")
