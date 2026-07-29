"""
资本三流 —— 代理变量有效性检验（一次性脚本）
============================================
检验「北向净流入 → Δ外汇储备」在重合期（2018-01 ~ 2024-08）月频相关性，
输出 Pearson / Spearman，并把结果回填 data_sources.md 第八节的相关系数表。

原则（与第八节一致）：
- 拉不到数据 → 明确打印「无法验证」并以**非 0 退出码**结束，**绝不编造相关系数**。
- 仅当两侧数据都拿到且样本数 ≥ 6 个月时才计算并回填。

用法：
    python validate_proxy.py
依赖：akshare / pandas（在 capital-three-flow 的 venv 中运行；沙箱无网络会自然失败）。
"""
import os
import sys
import re

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_SOURCES = os.path.join(SKILL_DIR, "references", "data_sources.md")


def _die(msg):
    print(f"[validate_proxy] 无法验证：{msg}")
    sys.exit(2)


def get_forex_reserve_delta_monthly():
    """拉取外汇储备月度值，按月份排序后取一阶差分 → Δ外储（亿美元）。"""
    try:
        import akshare as ak
    except Exception as e:
        _die(f"无法导入 akshare：{e}")
    try:
        df = ak.macro_china_foreign_exchange_gold()
    except Exception as e:
        _die(f"外汇储备数据拉取失败：{e}")
    if df is None or df.empty:
        _die("外汇储备返回空")
    # 列：统计时间、国家外汇储备、黄金储备
    df = df.sort_values("统计时间").reset_index(drop=True)
    df["dt"] = df["统计时间"].astype(str).str.replace(".", "-", regex=False).str[:7]
    df["reserve"] = df["国家外汇储备"].astype(float)
    df["delta"] = df["reserve"].diff()
    out = df[["dt", "delta"]].dropna()
    out = out[out["dt"] >= "2018-01"]
    return {row["dt"]: float(row["delta"]) for _, row in out.iterrows()}


def get_northbound_monthly():
    """拉取北向净流入月度汇总。优先尝试 akshare 历史月度聚合函数，
    拿不到则明确失败（不编造）。"""
    try:
        import akshare as ak
    except Exception as e:
        _die(f"无法导入 akshare：{e}")
    # 候选函数（历史可用，部分已在 master 移除）——逐一试，全部失败即报错
    candidates = [
        ("stock_hsgt_north_net_flow_in_em", {}),
        ("stock_hsgt_north_cash_em", {}),
        ("stock_hsgt_north_net_flow_em", {}),
    ]
    df = None
    used = None
    for fn, kw in candidates:
        try:
            f = getattr(ak, fn, None)
            if f is None:
                continue
            df = f(**kw)
            if df is not None and not df.empty:
                used = fn
                break
        except Exception:
            continue
    if df is None or df.empty:
        _die("北向净流入历史月度数据在当前 akshare 不可用（接口已移除/无数据），无法验证")
    # 归一化为 {YYYY-MM: 净流入}
    # 兼容多种列名：日期列含"日期/时间/date"，值列含"净买/净流入/net"
    date_col = next((c for c in df.columns if "日期" in c or "时间" in c or c.lower() == "date"), None)
    val_col = next((c for c in df.columns if "净买" in c or "净流入" in c or "net" in c.lower()), None)
    if date_col is None or val_col is None:
        _die(f"北向数据列结构不可识别（列为 {list(df.columns)}），无法验证")
    sub = df.copy()
    sub[date_col] = sub[date_col].astype(str).str.replace(".", "-", regex=False).str[:7]
    sub[val_col] = sub[val_col].astype(float)
    sub = sub.groupby(date_col)[val_col].sum().reset_index()
    sub = sub[sub[date_col] >= "2018-01"]
    sub = sub[sub[date_col] <= "2024-08"]
    return {row[date_col]: float(row[val_col]) for _, row in sub.iterrows()}, used


def compute_corr(north: dict, fx: dict):
    import pandas as pd
    months = sorted(set(north) & set(fx))
    if len(months) < 6:
        _die(f"共同月份仅 {len(months)} 个（<6），样本不足无法验证")
    xs = [north[m] for m in months]
    ys = [fx[m] for m in months]
    s = pd.Series(xs)
    t = pd.Series(ys)
    pearson = s.corr(t, method="pearson")
    try:
        spearman = s.corr(t, method="spearman")
    except Exception:
        spearman = None
    return pearson, spearman, len(months), months[0], months[-1]


def backfill(pearson, spearman, n, start, end):
    """把结果写回 data_sources.md 第八节的北向→Δ外储行。"""
    if not os.path.exists(DATA_SOURCES):
        print(f"[validate_proxy] 未找到 {DATA_SOURCES}，跳过回填（仅打印结果）")
        return
    text = open(DATA_SOURCES, encoding="utf-8").read()
    sp = f"{spearman:.3f}" if spearman is not None else "N/A"
    # 匹配北向行：| 北向净流入 → Δ外汇储备 | _待跑_ | _待填_ | 2018-01 ~ 2024-08 | _待填_ |
    pat = re.compile(
        r"(\|\s*北向净流入 → Δ外汇储备\s*\|\s*)_待跑_(\s*\|\s*)_待填_"
        r"(\s*\|\s*2018-01 ~ 2024-08\s*\|\s*)_待填_(\s*\|)"
    )
    new_line = f"\\1{pearson:.3f}\\2{sp}\\3相关(n={n}, {start}~{end})\\4"
    new_text, cnt = pat.subn(new_line, text)
    if cnt == 0:
        print("[validate_proxy] 未匹配到待填行，请手动回填（结果见上）。")
        return
    open(DATA_SOURCES, "w", encoding="utf-8").write(new_text)
    print(f"[validate_proxy] 已回填 data_sources.md 第八节（n={n}）。")


def main():
    print("[validate_proxy] 开始代理变量有效性检验：北向净流入 → Δ外汇储备")
    fx = get_forex_reserve_delta_monthly()
    if not fx:
        _die("外汇储备差分后无样本")
    north = get_northbound_monthly()
    north_dict = north[0] if isinstance(north, tuple) else north
    pearson, spearman, n, start, end = compute_corr(north_dict, fx)
    print(f"  重合期：{start} ~ {end}，共同月份 n={n}")
    print(f"  Pearson  = {pearson:.3f}")
    if spearman is not None:
        print(f"  Spearman = {spearman:.3f}")
    else:
        print("  Spearman = N/A")
    verdict = "≥0.5：可作方向性参考，可进 CFCI/CRI" if pearson >= 0.5 else "<0.5：仅方向性参考，不得进 CFCI/CRI 计算"
    print(f"  判定：{verdict}")
    backfill(pearson, spearman, n, start, end)
    # 退出码：相关性过低也视为「已验证但不可用」，正常 0；只有拿不到数据才非 0
    sys.exit(0)


if __name__ == "__main__":
    main()
