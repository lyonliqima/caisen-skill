#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
linkage.py — 板块间联动关系实证分析（状态依赖型虹吸）

一次算出：
  第2步 事件筛选（X 的 4 周滚动收益 ≥ 阈值）
  第3步 二分组（按同期基准是否同步上涨：增量普涨型 / 存量独立型）
  第4步 反证检验（X 跌 ≥ 阈值 时 Y 的表现）
  第5步 相关结构三件套（原始相关 / 剥离 beta 超额相关 / Y1-Y2 超额相关）
  第6步 波动率定标（周 σ 与 1.5σ 证伪位最小距离）

用法:
  python3 linkage.py --data series.json --x 半导体 --bench 沪深300 --y 房地产 养殖

输入 JSON 契约（长表，日期升序）:
  {
    "半导体":  [["2024-01-05", 0.812], ["2024-01-12", 0.845], ...],
    "房地产":  [["2024-01-05", 0.612], ...],
    "养殖":    [["2024-01-05", 0.498], ...],
    "沪深300": [["2024-01-05", 3412.0], ...]
  }
"""

import argparse
import json
import math
import sys
from datetime import datetime


# ---------- 载入 ----------

def load_series(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    series = {}
    for label, rows in raw.items():
        pairs = []
        for row in rows:
            # 容忍 [date, close] / [close] / {"date":..,"close":..} / [ts, o, h, l, c]
            if isinstance(row, dict):
                d = str(row.get("date") or row.get("time") or row.get("day"))
                c = float(row.get("close"))
            elif isinstance(row, (list, tuple)):
                if len(row) == 2:
                    d, c = str(row[0]), float(row[1])
                elif len(row) >= 5:
                    d, c = str(row[0]), float(row[4])
                else:
                    continue
            else:
                continue
            pairs.append((norm_date(d), c))
        pairs.sort(key=lambda t: t[0])
        series[label] = pairs
    return series


def norm_date(s):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt) + 2].strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return s[:10]


def align(series):
    """取所有序列共有的日期，返回 (dates, {label: [close...]})"""
    sets = [set(d for d, _ in v) for v in series.values()]
    common = sorted(set.intersection(*sets)) if sets else []
    out = {}
    for label, pairs in series.items():
        m = dict(pairs)
        out[label] = [m[d] for d in common]
    return common, out


# ---------- 工具 ----------

def roll_ret(closes, w):
    """w 周滚动收益率(%)，长度与 closes 同，前 w 个为 None"""
    r = [None] * len(closes)
    for i in range(w, len(closes)):
        if closes[i - w]:
            r[i] = (closes[i] / closes[i - w] - 1.0) * 100.0
    return r


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return float("nan")
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def winrate(xs):
    xs = [x for x in xs if x is not None]
    return (sum(1 for x in xs if x > 0), len(xs))


def corr(a, b):
    idx = [i for i in range(len(a)) if a[i] is not None and b[i] is not None]
    if len(idx) < 3:
        return float("nan"), 0
    xa = [a[i] for i in idx]
    xb = [b[i] for i in idx]
    ma, mb = mean(xa), mean(xb)
    num = sum((xa[i] - ma) * (xb[i] - mb) for i in range(len(xa)))
    da = math.sqrt(sum((v - ma) ** 2 for v in xa))
    db = math.sqrt(sum((v - mb) ** 2 for v in xb))
    if da == 0 or db == 0:
        return float("nan"), len(idx)
    return num / (da * db), len(idx)


def stdev(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((v - m) ** 2 for v in xs) / (len(xs) - 1))


def fmt(v, nd=2):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "  n/a"
    return f"{v:+.{nd}f}"


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="规范化 JSON 路径")
    ap.add_argument("--x", required=True, help="发起板块标签")
    ap.add_argument("--bench", required=True, help="基准标签（必须）")
    ap.add_argument("--y", nargs="+", required=True, help="目标板块标签，1~3 个")
    ap.add_argument("--window", type=int, default=4, help="滚动窗口（周），默认 4")
    ap.add_argument("--threshold", type=float, default=12.0, help="X 事件阈值(%%)，默认 12")
    ap.add_argument("--bench-threshold", type=float, default=3.0,
                    help="判定增量态的基准阈值(%%)，默认 3")
    ap.add_argument("--sigma-years", type=float, default=2.0,
                    help="波动率统计回看的年数，默认 2")
    ap.add_argument("--horizon", type=int, default=12, help="证伪位持有周数，默认 12")
    args = ap.parse_args()

    series = load_series(args.data)
    need = [args.x, args.bench] + args.y
    missing = [k for k in need if k not in series]
    if missing:
        print(f"[错误] JSON 缺少标签: {missing}\n现有: {list(series.keys())}")
        sys.exit(1)

    dates, px = align(series)
    n = len(dates)
    if n < args.window * 3:
        print(f"[错误] 共同交易日仅 {n} 个，样本不足（需 ≥{args.window*3}）")
        sys.exit(1)

    W = args.window
    ret = {k: roll_ret(px[k], W) for k in need}

    print("=" * 66)
    print(f"板块间联动实证分析  |  窗口 {W} 周  |  样本 {n} 个交易日")
    print(f"区间 {dates[0]} → {dates[-1]}")
    print(f"X={args.x}  基准={args.bench}  Y={args.y}")
    print("=" * 66)

    xr = ret[args.x]
    br = ret[args.bench]

    # ---- 第2步 事件筛选 + 第3步 二分组 ----
    up_all, inc, sto = [], [], []
    for i in range(n):
        if xr[i] is None or br[i] is None:
            continue
        if xr[i] >= args.threshold:
            up_all.append(i)
            (inc if br[i] > args.bench_threshold else sto).append(i)

    print(f"\n【第2步】X 的 {W} 周涨幅 ≥ {args.threshold:g}% 的事件共 {len(up_all)} 个")
    print(f"【第3步】二分组：增量普涨型 {len(inc)} 个 | 存量独立型 {len(sto)} 个")

    header = "  " + "组别".ljust(12) + f"{'n':>3}  " + "".join(
        k.ljust(16) for k in need)
    for grp_name, grp in (("增量普涨型", inc), ("存量独立型", sto)):
        if not grp:
            continue
        print(f"\n  ── {grp_name}（n={len(grp)}）──")
        print("  " + "标的".ljust(14) + f"{'均值':>9}{'中位':>9}{'胜率':>9}")
        for k in need:
            vals = [ret[k][i] for i in grp]
            w, t = winrate(vals)
            print(f"  {k.ljust(14)}{fmt(mean(vals)):>9}{fmt(median(vals)):>9}"
                  f"{f'{w}/{t}':>9}")

    if len(inc) >= 2 and len(sto) >= 2:
        print("\n  ── 状态差（增量 − 存量）──")
        for k in need:
            d = mean([ret[k][i] for i in inc]) - mean([ret[k][i] for i in sto])
            print(f"  {k.ljust(14)}{fmt(d):>9}  pct")

    # ---- 第4步 反证检验 ----
    dn = [i for i in range(n) if xr[i] is not None and xr[i] <= -args.threshold]
    print(f"\n【第4步】反证检验：X 的 {W} 周跌幅 ≤ -{args.threshold:g}% 事件共 {len(dn)} 个")
    if dn:
        print("  " + "标的".ljust(14) + f"{'均值':>9}{'中位':>9}{'胜率':>9}")
        for k in need:
            vals = [ret[k][i] for i in dn]
            w, t = winrate(vals)
            print(f"  {k.ljust(14)}{fmt(mean(vals)):>9}{fmt(median(vals)):>9}"
                  f"{f'{w}/{t}':>9}")
        print("  判读：Y 同向下跌 → 双向跷跷板否证（单向虹吸）；Y 反向上涨 → 跷跷板成立")
    else:
        print("  无样本，跷跷板无法证伪（结论必须标注此限制）")

    # ---- 第5步 相关结构 ----
    print("\n【第5步】相关结构（全样本滚动序列）")
    kx = args.x
    excess = {}
    for k in need:
        e = [None] * n
        for i in range(n):
            if ret[k][i] is not None and br[i] is not None:
                e[i] = ret[k][i] - br[i]
        excess[k] = e

    print(f"  {'配对':<24}{'原始相关':>10}{'超额相关':>10}{'n':>7}{'符号':>8}")
    pairs = []
    for j, k in enumerate(args.y):
        pairs.append((kx, k))
    for i in range(len(args.y)):
        for j in range(i + 1, len(args.y)):
            pairs.append((args.y[i], args.y[j]))
    for a, b in pairs:
        c0, n0 = corr(ret[a], ret[b])
        c1, n1 = corr(excess[a], excess[b])
        flip = "反转" if (not math.isnan(c0) and not math.isnan(c1)
                          and (c0 > 0) != (c1 > 0)) else "-"
        print(f"  {a+'−'+b:<24}{fmt(c0,3):>10}{fmt(c1,3):>10}{n0:>7}{flip:>8}")

    print("  判读：原始相关全正 + 超额相关为负 = 符号反转 = 因子重叠（须合并仓位）")
    print("        同组内 Y−Y 超额相关显著为正 = 同一因子（合并计算仓位上限）")

    # ---- 第6步 波动率定标 ----
    # 口径铁律：σ 必须用【单周收益率】σ_1w，再按 √horizon 缩放到持有期。
    # 若用 W 周滚动收益的 σ 再乘 √horizon，会重复放大（σ_W 已含 √W）。
    print("\n【第6步】波动率定标")
    ret1 = {k: roll_ret(px[k], 1) for k in need}
    lookback = int(args.sigma_years * 52)
    start = max(1, n - lookback)
    scale = math.sqrt(args.horizon)
    print(f"  {'标的':<14}{'σ_1w':>8}{'σ_W':>8}{'目标区间±kσ_H':>16}"
          f"{f'1.5σ_H证伪距离':>18}")
    for k in need:
        s1 = stdev([ret1[k][i] for i in range(start, n)])
        sW = stdev([ret[k][i] for i in range(start, n)])
        sH = s1 * scale                      # 持有期 σ
        print(f"  {k.ljust(14)}{s1:>7.2f}%{sW:>7.2f}%{sH:>15.2f}%{1.5*sH:>17.1f}pct")
    print(f"  说明：回看 {args.sigma_years:g} 年（{n-start} 周）；"
          f"持有期 σ_H = σ_1w × √{args.horizon}")
    print(f"        目标区间宽度取 1σ_H（k=1）；证伪位距离 = 1.5×σ_H "
          f"（小于此值 = 会被噪声打掉 = 无效研判）")

    # ---- 当前状态 ----
    print("\n【当前状态】最新滚动收益")
    for k in need:
        v = ret[k][-1]
        print(f"  {k.ljust(14)}{fmt(v):>9}%  ({dates[-1]})")
    print("\n" + "=" * 66)


if __name__ == "__main__":
    main()
