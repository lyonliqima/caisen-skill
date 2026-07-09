#!/usr/bin/env python3
"""fetch_daily.py — 每日市场数据预取（多源容错链：东财 → 新浪 → 腾讯）

把大盘指数 / 行业板块 / 资金流向等「通用市场背景数据」每天跑一次落盘成 JSON，
分析时直接读缓存，只对目标个股实时补拉，避免每次分析都走完整的降级重试链（主要 I/O 延迟来源）。

⚠️ 必须在「能直连东财/新浪/腾讯」的机器上跑（WorkBuddy 沙箱对行情 API 有硬性限流，约 4% 通过率）。
   推荐：你本机用 crontab / 任务计划程序 每天盘后跑一次，或手动跑。

用法:
    python3 fetch_daily.py                 # 拉今天，写到 cache/<今天>.json
    python3 fetch_daily.py --date 2026-07-09
    python3 fetch_daily.py --out /tmp/m.json --force

输出 JSON 结构:
{
  "date": "2026-07-09",
  "generated_at": "2026-07-09T16:30:00",
  "sources_used": ["eastmoney"],
  "indices": {"上证指数": {"price":3210.5,"chg_pct":0.85,"amount":2.8e11}, ...},
  "sectors": [{"name":"半导体","chg_pct":2.3,"rank":1}, ...],
  "flows": {"northbound": {...}, "southbound": {...}}
}

依赖: Python 3.8+ 标准库（urllib / json）。无第三方依赖。
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "cache"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
TIMEOUT = 8

# 指数映射: 名称 -> (东财 secid, 新浪代码, 腾讯代码)
INDEX_MAP = {
    "上证指数": ("1.000001", "sh000001", "sh000001"),
    "深证成指": ("0.399001", "sz399001", "sz399001"),
    "创业板指": ("0.399006", "sz399006", "sz399006"),
    "沪深300": ("1.000300", "sh000300", "sh000300"),
    "科创50": ("1.000688", "sh000688", "sh000688"),
    "恒生指数": ("100.HSI", "r_hkHSI", "r_hkHSI"),
    "纳斯达克": ("100.NDX", "gb_ixic", "usIXIC"),
    "标普500": ("100.SPX", "gb_inx", "usSPX"),
}


def _get(url: str, referer: str | None = None, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if referer:
        req.add_header("Referer", referer)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", errors="ignore")


def _eastmoney_indices() -> dict[str, dict]:
    secids = ",".join(v[0] for v in INDEX_MAP.values())
    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get"
        f"?fltt=2&invt=2&fields=f12,f14,f2,f3,f4,f6&secids={secids}"
    )
    txt = _get(url)
    obj = json.loads(txt)
    out = {}
    for d in obj.get("data", {}).get("diff", []):
        name = d.get("f14")
        if not name:
            continue
        out[name] = {
            "price": _num(d.get("f2")),
            "chg_pct": _num(d.get("f3")),
            "chg": _num(d.get("f4")),
            "amount": _num(d.get("f6")),
        }
    return out


def _sina_indices() -> dict[str, dict]:
    codes = ",".join(v[1] for v in INDEX_MAP.values())
    url = f"https://hq.sinajs.cn/list={codes}"
    txt = _get(url, referer="https://finance.sina.com.cn")
    out = {}
    for line in txt.split(";"):
        line = line.strip()
        if "=" not in line or "hq_str" not in line:
            continue
        code = line.split("hq_str_")[1].split("=")[0]
        payload = line.split('"')[1] if '"' in line else ""
        parts = payload.split(",")
        if len(parts) < 4:
            continue
        name = parts[0]
        price = _num(parts[3])
        prev = _num(parts[2])
        chg_pct = round((price - prev) / prev * 100, 2) if prev else None
        out[name] = {"price": price, "chg_pct": chg_pct}
    return out


def _tencent_indices() -> dict[str, dict]:
    codes = ",".join(v[2] for v in INDEX_MAP.values())
    url = f"https://qt.gtimg.cn/q={codes}"
    txt = _get(url)
    out = {}
    for line in txt.split(";"):
        line = line.strip()
        if "=" not in line or "v_" not in line:
            continue
        code = line.split("v_")[1].split("=")[0]
        payload = line.split('"')[1] if '"' in line else ""
        parts = payload.split("~")
        if len(parts) < 5:
            continue
        name = parts[1]
        price = _num(parts[3])
        prev = _num(parts[4])
        chg_pct = round((price - prev) / prev * 100, 2) if prev else None
        out[name] = {"price": price, "chg_pct": chg_pct}
    return out


def get_indices() -> tuple[dict, str]:
    """多源容错链，返回 (数据, 用到的源)。"""
    for fn, src in (
        (_eastmoney_indices, "eastmoney"),
        (_sina_indices, "sina"),
        (_tencent_indices, "tencent"),
    ):
        try:
            data = fn()
            if data:
                return data, src
        except Exception as e:  # noqa: BLE001
            print(f"[fetch] {src} 失败: {e}", file=sys.stderr)
    return {}, "none"


def get_sectors() -> list[dict]:
    """行业板块涨幅榜（东财，失败返回空）。"""
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=30&fs=m:90+t:2&fields=f12,f14,f3,f62&_=" + str(int(__import__("time").time()))
    )
    try:
        obj = json.loads(_get(url))
        out = []
        for i, d in enumerate(obj.get("data", {}).get("diff", []), 1):
            out.append({"name": d.get("f14"), "chg_pct": _num(d.get("f3")), "rank": i})
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[fetch] sectors 失败: {e}", file=sys.stderr)
        return []


def get_flows() -> dict:
    """资金流向（东财 best-effort，北向已停更则标 unavailable）。"""
    out = {"northbound": "unavailable", "southbound": "unavailable"}
    try:
        url = (
            "https://push2.eastmoney.com/api/qt/kamt/get"
            "?fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54,f55,f56"
        )
        obj = json.loads(_get(url))
        if obj.get("data") and obj["data"].get("hk1"):
            out["southbound"] = obj["data"]["hk1"]
    except Exception as e:  # noqa: BLE001
        print(f"[fetch] flows 失败: {e}", file=sys.stderr)
    return out


def _num(x):
    try:
        if x in (None, "", "-", "--"):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="每日市场数据预取（多源容错）")
    ap.add_argument("--date", default=datetime.date.today().isoformat(), help="数据日期 YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="输出 JSON 路径（默认 cache/<date>.json）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的缓存")
    args = ap.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else CACHE_DIR / f"{args.date}.json"
    if out_path.exists() and not args.force:
        print(f"[fetch] 缓存已存在，跳过（--force 覆盖）: {out_path}")
        return

    indices, src = get_indices()
    payload = {
        "date": args.date,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "sources_used": [src] if src != "none" else [],
        "indices": indices,
        "sectors": get_sectors(),
        "flows": get_flows(),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch] 已落盘 → {out_path}（源: {src or '无'}；指数 {len(indices)} 个）")


if __name__ == "__main__":
    main()
