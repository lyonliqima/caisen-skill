"""
scan.py — Mi姐框架每日扫描脚本（可定时跑）
=========================================
对观察池逐票计算最新信号，输出「买入/退出」决策与各模块状态。
用法：
  python scan.py                      # 用内置观察池
  python scan.py --codes sh600519,sz300750   # 指定标的
  python scan.py --csv watchlist.csv  # 第一列 code
  python scan.py --out result.csv     # 导出
依赖本地缓存（data_feed 自动缓存7天），离线也能跑上次数据。
"""
import argparse
import sys
import pandas as pd

from data_feed import fetch_ohlcv
from framework import build_signals, CONFIG

DEFAULT_WATCH = [
    "sh600519", "sh601318", "sh600036", "sh601012", "sh600900",
    "sz000651", "sz000333", "sz000858", "sz002594", "sz300750",
    "sz002415", "sz300059",
]


def scan_one(code: str) -> dict:
    try:
        o = fetch_ohlcv(code)
    except Exception as e:
        return {"code": code, "error": str(e)}
    sig = build_signals(o)
    row = sig.iloc[-1]
    return {
        "code": code,
        "date": str(row["date"].date()),
        "close": round(float(row["close"]), 2),
        "trend": row["trend"], "structure": row["structure"],
        "timing": row["timing"], "capital": row["capital"],
        "emotion": row["emotion"],
        "single_pct": row["single_pct"], "total_pct": row["total_pct"],
        "decision": row["decision"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default="", help="逗号分隔 code 列表")
    ap.add_argument("--csv", default="", help="观察池 CSV（第一列 code）")
    ap.add_argument("--out", default="", help="导出 CSV 路径")
    ap.add_argument("--buyonly", action="store_true", help="只显示买入/退出信号")
    args = ap.parse_args()

    codes = []
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    elif args.csv:
        df = pd.read_csv(args.csv)
        codes = [str(c).strip() for c in df.iloc[:, 0].tolist()]
    else:
        codes = DEFAULT_WATCH

    rows = [scan_one(c) for c in codes]
    out = pd.DataFrame(rows)
    if "error" in out.columns:
        errs = out[out["error"].notna()][["code", "error"]]
        if len(errs):
            print("=== 失败标的 ===")
            print(errs.to_string(index=False))
        out = out[out["error"].isna()].drop(columns=["error"])

    if args.buyonly:
        out = out[out["decision"].isin(["买入", "退出"])]

    cols = ["code", "date", "close", "trend", "structure", "timing",
            "capital", "emotion", "single_pct", "total_pct", "decision"]
    print(out[cols].to_string(index=False))
    n_buy = (out["decision"] == "买入").sum()
    n_exit = (out["decision"] == "退出").sum()
    print(f"\n扫描 {len(out)} 只：买入信号 {n_buy} / 退出信号 {n_exit}")

    if args.out:
        out.to_csv(args.out, index=False, encoding="utf-8-sig")
        print(f"已导出 {args.out}")


if __name__ == "__main__":
    main()
