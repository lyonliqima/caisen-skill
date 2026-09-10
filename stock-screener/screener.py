"""
统一选股引擎 —— 破底翻 × 碗口反弹 × Mi姐三维，交叉验证后排名次

设计要点
========
1) 三层漏斗，而不是一步到位
   第1层 前置过滤：用一次请求拿到的全市场快照，剔掉 ST/退市/停牌/低价/无流动性
   第2层 量化粗筛：对存活股票逐票拉日K，并行跑 3 套策略，各自独立打分（互不干扰）
   第3层 交叉验证：被多套策略同时命中的票加权加成 —— 这是本引擎的核心 alpha 来源
                   破底翻（底部反转）+ 碗口反弹（趋势转多）同时命中 = 结构已成立

2) 为什么不能只用一套策略
   破底翻是左侧抄底，在单边下跌市会连续产生假信号；
   碗口反弹是右侧回踩，在底部区域几乎筛不出票（因为要求短期线>多空线）；
   两者互补。Mi姐三维条件最严，命中率低但假信号最少，用作"确认票"。

3) 输出即决策：每只票都带 止损位 / 目标位 / 盈亏比，
   盈亏比 < 2 的直接降权，不出现在推荐名单里。
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from data_source import get_stock_list, get_spot_snapshot, batch_get_kline  # noqa: E402
from strategies.podifan import detect_podifan                              # noqa: E402
from strategies.bowl_rebound import detect_bowl_rebound                    # noqa: E402
from strategies.mi_signal import detect_mi_signal                          # noqa: E402

OUT_DIR = BASE.parent / "stock-screener-output"
OUT_DIR.mkdir(exist_ok=True)

# 交叉命中加成：每多命中一套策略，在最强策略分数上叠加的分值
CROSS_BONUS = 12
# 盈亏比门槛：低于此值不进推荐名单
MIN_RR = 2.0


def build_universe(min_price: float = 2.0,
                   min_amount: float = 30_000_000,
                   limit: int = 0,
                   verbose: bool = True) -> pd.DataFrame:
    """
    第1层：构造待扫描股票池（code, name, 最新价, 涨跌幅%, 成交额）
    min_amount 默认 3000 万：当日成交额低于此值的票，进出都会有滑点，直接剔掉。
    """
    lst = get_stock_list()
    if verbose:
        print(f"[1/4] 全市场代码表 {len(lst)} 只")

    spot = get_spot_snapshot(codes=lst["code"].tolist())
    if spot is not None and len(spot) > 1000:
        spot["code"] = spot["code"].astype(str).str.zfill(6)
        uni = lst.merge(spot, on="code", how="left", suffixes=("", "_s"))
        uni["name"] = uni["name_s"].fillna(uni["name"])
        uni = uni.drop(columns=[c for c in uni.columns if c.endswith("_s")])
        if verbose:
            print(f"      合并实时快照成功（{len(uni)} 只）")
    else:
        uni = lst.copy()
        if verbose:
            print("      ⚠ 快照获取失败，降级为全量拉K线（会慢一些）")

    # ---- 过滤 ----
    before = len(uni)
    nm = uni["name"].astype(str)
    uni = uni[~nm.str.contains("ST|退", na=False, regex=True)]            # ST/退市
    if "最新价" in uni.columns:
        # 停牌票最新价为 0，保留（后面拉K线时用得上历史）；但剔掉真实低价股
        uni = uni[(uni["最新价"].isna()) | (uni["最新价"] == 0) | (uni["最新价"] >= min_price)]
    if "成交额" in uni.columns:
        uni = uni[(uni["成交额"].isna()) | (uni["成交额"] >= min_amount)]
    uni = uni[~uni["code"].astype(str).str.startswith(("4", "8"))]        # 剔北交所
    uni = uni.reset_index(drop=True)
    if verbose:
        print(f"      过滤 ST/退市/低价(<{min_price}元)/低成交额(<{min_amount/1e4:.0f}万)/北交所："
              f"{before} → {len(uni)} 只")

    if limit and limit > 0:
        uni = uni.head(limit).reset_index(drop=True)
        if verbose:
            print(f"      ⚠ 测试模式：只取前 {len(uni)} 只")
    return uni


def run_screen(min_price: float = 2.0,
               min_amount: float = 30_000_000,
               limit: int = 0,
               workers: int = 12,
               datalen: int = 620,
               use_cache: bool = True,
               enable_mi: bool = True,
               verbose: bool = True) -> Dict[str, pd.DataFrame]:
    """
    跑完整流程，返回 {"破底翻": df, "碗口反弹": df, "Mi姐三维": df, "综合": df}
    """
    t0 = time.time()
    uni = build_universe(min_price=min_price, min_amount=min_amount,
                         limit=limit, verbose=verbose)

    if verbose:
        print(f"\n[2/4] 批量拉取日K（{len(uni)} 只，{workers} 线程，缓存={'开' if use_cache else '关'}）")
        print("      首次全量约需 3-6 分钟，之后走缓存会快很多")
    klines = batch_get_kline(uni["code"].tolist(),
                             datalen=datalen,
                             workers=workers,
                             use_cache=use_cache)
    if verbose:
        print(f"      日K 获取成功 {len(klines)}/{len(uni)} 只，用时 {time.time()-t0:.0f}s")

    name_map = dict(zip(uni["code"].astype(str), uni["name"].astype(str)))
    chg_map = ({}
               if "涨跌幅%" not in uni.columns
               else dict(zip(uni["code"].astype(str),
                             pd.to_numeric(uni["涨跌幅%"], errors="coerce").fillna(0))))

    scanned_n = len(uni)
    rows_podi, rows_bowl, rows_mi = [], [], []
    done = 0
    total = len(klines)
    if verbose:
        print(f"\n[3/4] 逐票跑策略")

    for code, df in klines.items():
        done += 1
        if verbose and done % 500 == 0:
            print(f"      ...已算 {done}/{total}，破底翻{len(rows_podi)} 碗口{len(rows_bowl)} "
                  f"Mi姐{len(rows_mi)}", flush=True)
        nm = name_map.get(code, "")
        try:
            r = detect_podifan(df, code, nm, chg_map.get(code, 0.0))
            if r:
                rows_podi.append(r)
            r = detect_bowl_rebound(df, code, nm)
            if r:
                rows_bowl.append(r)
            if enable_mi:
                r = detect_mi_signal(df, code, nm)
                if r and r.get("score", 0) > 0:
                    rows_mi.append(r)
        except Exception:
            continue

    res = {}
    for key, rows in (("破底翻", rows_podi), ("碗口反弹", rows_bowl), ("Mi姐三维", rows_mi)):
        if rows:
            res[key] = (pd.DataFrame(rows)
                        .sort_values("score", ascending=False)
                        .reset_index(drop=True))
        else:
            res[key] = pd.DataFrame()

    if verbose:
        print(f"      破底翻 {len(res['破底翻'])} 只 | "
              f"碗口反弹 {len(res['碗口反弹'])} 只 | "
              f"Mi姐三维 {len(res['Mi姐三维'])} 只")

    res["综合"] = _cross_rank(res, verbose=verbose,
                              scanned=scanned_n, got_kline=len(klines))
    if verbose:
        print(f"\n[4/4] 完成，总耗时 {time.time()-t0:.0f}s")
    return res


def _cross_rank(res: Dict[str, pd.DataFrame], verbose: bool = False,
                scanned: int = 0, got_kline: int = 0) -> pd.DataFrame:
    """
    第3层：交叉验证排序。
    final = 最强策略分 + (命中策略数 - 1) × CROSS_BONUS
    """
    buckets: Dict[str, Dict[str, float]] = {}
    meta: Dict[str, dict] = {}

    def _absorb(df: pd.DataFrame, tag: str):
        if df is None or len(df) == 0:
            return
        for _, r in df.iterrows():
            code = str(r["代码"])
            buckets.setdefault(code, {})[tag] = float(r["score"])
            if code not in meta:
                meta[code] = {k: v for k, v in r.items()}
            else:
                # 保留信息更全的那条快照，并合并关键字段
                for k, v in r.items():
                    if k not in meta[code] or meta[code][k] is None or (
                            isinstance(v, (int, float)) and v and not meta[code][k]):
                        meta[code][k] = v

    _absorb(res.get("破底翻"), "破底翻")
    _absorb(res.get("碗口反弹"), "碗口反弹")
    _absorb(res.get("Mi姐三维"), "Mi姐三维")

    rows = []
    for code, sc in buckets.items():
        best = max(sc.values())
        n = len(sc)
        final = round(min(best + (n - 1) * CROSS_BONUS, 100), 1)
        m = dict(meta.get(code, {}))
        m["命中策略"] = "/".join(sc.keys())
        m["命中数"] = n
        m["最强分"] = round(best, 1)
        m["score"] = final
        m["扫描总数"] = scanned          # 供 report.py 画漏斗
        m["有效K线数"] = got_kline
        # 盈亏比门槛：达不到 2:1 的降权（仍保留在表里，但排到后面）
        # 没算出盈亏比的（如 Mi姐单命中、无目标位）不降权也不奖励，保持原分
        rr = m.get("盈亏比")
        if rr is None or pd.isna(rr):
            m["盈亏比不足"] = False
        else:
            m["盈亏比不足"] = bool(rr < MIN_RR)
            if rr < MIN_RR:
                m["score"] = round(final * 0.8, 1)
        rows.append(m)

    out = pd.DataFrame(rows)
    if len(out) == 0:
        return out
    out = out.sort_values("score", ascending=False).reset_index(drop=True)
    out.insert(0, "排名", range(1, len(out) + 1))
    return out


def main():
    ap = argparse.ArgumentParser(description="蔡森统一选股引擎：破底翻 × 碗口反弹 × Mi姐三维")
    ap.add_argument("--limit", type=int, default=0, help="只扫前 N 只（测试用）")
    ap.add_argument("--workers", type=int, default=12, help="并发线程数（12 为宜，过高会被限流）")
    ap.add_argument("--min-price", type=float, default=2.0, help="最低价过滤")
    ap.add_argument("--min-amount", type=float, default=30_000_000, help="当日最低成交额过滤")
    ap.add_argument("--datalen", type=int, default=620, help="日K根数（620根≈2.5年）")
    ap.add_argument("--no-cache", action="store_true", help="忽略本地缓存，强制重拉")
    ap.add_argument("--no-mi", action="store_true", help="跳过 Mi姐三维（省一半时间）")
    ap.add_argument("--top", type=int, default=20, help="控制台显示前 N 名")
    args = ap.parse_args()

    res = run_screen(min_price=args.min_price,
                     min_amount=args.min_amount,
                     limit=args.limit,
                     workers=args.workers,
                     datalen=args.datalen,
                     use_cache=not args.no_cache,
                     enable_mi=not args.no_mi)

    ts = datetime.now().strftime("%Y%m%d")
    for key, df in res.items():
        fp = OUT_DIR / f"{key}_{ts}.csv"
        if len(df):
            df.to_csv(fp, index=False, encoding="utf-8-sig")
            print(f"  💾 {key}: {len(df)} 只 → {fp.name}")
        else:
            # ⚠️ 空结果也必须写文件（只写表头），把上一次运行的旧结果覆盖掉。
            # 否则 report.py 会读到陈旧的中签名单，把"本次 0 命中"误报成"命中 N 只"。
            pd.DataFrame(columns=["代码", "名称", "score"]).to_csv(
                fp, index=False, encoding="utf-8-sig")
            print(f"  💾 {key}: 0 只（已覆盖旧结果）→ {fp.name}")

    combo = res.get("综合", pd.DataFrame())
    if len(combo) == 0:
        print("\n本次未筛出任何标的。")
        return
    cols = [c for c in ["排名", "代码", "名称", "命中策略", "命中数", "最强分", "score",
                        "最新价", "止损位", "目标位", "盈亏比", "J值", "历史分位%",
                        "分类", "类型", "决策"] if c in combo.columns]
    print(f"\n{'='*96}\n综合排名 Top {min(args.top, len(combo))}\n{'='*96}")
    print(combo[cols].head(args.top).to_string(index=False))


if __name__ == "__main__":
    main()
