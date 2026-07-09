#!/usr/bin/env python3
"""latest.py — 打印最新一份市场数据缓存的路径与摘要。

分析 skill 调用本脚本拿到最新缓存 JSON 路径，读取后作为「通用市场背景」，
只对目标个股实时补拉。用法:

    python3 market-data-cache/latest.py          # 打印路径 + 摘要
    python3 market-data-cache/latest.py --path    # 只打印路径（方便管道）

依赖: Python 3.8+ 标准库。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "cache"


def _latest() -> Path | None:
    files = sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def main() -> None:
    ap = argparse.ArgumentParser(description="打印最新市场缓存")
    ap.add_argument("--path", action="store_true", help="只打印路径")
    args = ap.parse_args()

    path = _latest()
    if not path:
        print("无缓存，请先跑 fetch_daily.py", file=sys.stderr)
        raise SystemExit(1)

    if args.path:
        print(path)
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"缓存: {path}")
    print(f"日期: {data.get('date')}  源: {data.get('sources_used')}")
    print("指数:")
    for name, v in data.get("indices", {}).items():
        pct = v.get("chg_pct")
        pct_s = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else "n/a"
        print(f"  {name}: {pct_s}")
    sec = data.get("sectors") or []
    if sec:
        print("领涨板块: " + "、".join(f"{s['name']}({s['chg_pct']:+.2f}%)" for s in sec[:5]))


if __name__ == "__main__":
    main()
