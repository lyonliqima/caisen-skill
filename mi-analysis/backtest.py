"""
backtest.py — Mi姐框架历史回测 + 口诀有效性筛选（2019–2025）
===========================================================
- run_backtest: 事件驱动，次日开盘成交，避免未来函数。
- 策略主框架(full) vs 多个「口诀变体」，对比胜率/盈亏比/最大回撤，
  筛掉「听起来对但实测亏」的条目。
注：沙箱对行情API有通过率上限，全市场扫描须在本机运行（见文件底部说明）。
"""
import numpy as np
import pandas as pd
from data_feed import fetch_universe
from framework import build_signals, CONFIG

# 观察池（跨风格、跨市值，仅作示范样本）
UNIVERSE = [
    "sh600519", "sh601318", "sh600036", "sh601166", "sh600276", "sh600887",
    "sh601012", "sh600030", "sh601888", "sh600900", "sh601398", "sh600028",
    "sh601628", "sh600009",
    "sz000001", "sz000651", "sz000333", "sz000858", "sz002594", "sz300750",
    "sz000725", "sz002415", "sz300059", "sz002475", "sz000002",
]

BACKTEST_END = "2025-12-31"  # 严格限定 2019–2025 样本


def _mask_from_sig(sig, daily):
    """根据 signals + daily 构造各变体的 enter/exit 布尔序列。"""
    cfg = CONFIG
    ma20 = daily[f"ma{cfg['A']['ma_long']}"]
    ma250 = daily[f"ma{cfg['A']['ma_year']}"]
    close = daily["close"]; vol_ratio = daily["vol_ratio"]; ret20 = daily["ret20"]
    trend = sig["trend"]; structure = sig["structure"]; timing = sig["timing"]
    capital = sig["capital"]; emotion = sig["emotion"]

    variants = {}
    # 基线：仅 A多 & B健康 & C买
    base_enter = (trend == "多") & (structure == "健康回调") & (timing == "买")
    base_exit = (timing == "卖") | (trend == "空") | (structure == "破位")
    variants["基线(ABC)"] = (base_enter, base_exit)

    # 全框架：决策矩阵（含资金/情绪门控）
    variants["全框架(ABCDE)"] = (sig["decision"] == "买入", sig["decision"] == "退出")

    # 口诀①：买横买坑不买竖（回避拉升追高）
    k1 = base_enter & (close <= ma20 * 1.15)
    variants["+买横买坑不买竖"] = (k1, base_exit)

    # 口诀②：高位放量滞涨出局（高位量比>1.5且20日动量走平）
    k2_exit = base_exit | ((vol_ratio > 1.5) & (ret20 < 0.02) & (close > ma250 * 1.5))
    variants["+高位放量滞涨出局"] = (base_enter, k2_exit)

    # 口诀③：不抄底/下跌不言底（仅在多头趋势下参与，基线已满足，这里加情绪冰点禁买）
    k3 = base_enter & (~emotion.isin(["冰点期", "高潮期"]))
    variants["+避冰点高潮"] = (k3, base_exit | (emotion.isin(["冰点期", "高潮期"])))

    # 口诀④：连续大阳不买（近3日涨幅均>3%则禁买）
    big_yang = daily["ret"].rolling(3).apply(lambda x: (x > 0.03).all(), raw=True).fillna(False).astype(bool)
    k4 = base_enter & (~big_yang)
    variants["+连续大阳不买"] = (k4, base_exit)

    # 口诀⑤：牛市缓涨急跌=洗盘持有（跌< -4%缩量不止损，仅延长持有）
    # 实现为：在 base_exit 中剔除「洗盘」日的卖出（仅对多头有效）
    wash = (trend == "多") & (daily["ret"] < -0.04) & (vol_ratio < 1.0)
    k5_exit = base_exit & (~wash)
    variants["+急跌洗盘持有"] = (base_enter, k5_exit)

    return variants


def run_backtest(sig, daily, enter_mask, exit_mask, cfg=CONFIG):
    """次日开盘成交的事件驱动回测。返回 (trades_list, equity_curve, metrics)。"""
    n = len(sig)
    opens = daily["open"].values; closes = daily["close"].values
    single = sig["single_pct"].values
    stop_loss = cfg["C"]["stop_loss"]; time_stop = cfg["C"]["time_stop"]
    in_pos = False; entry = 0.0; entry_i = 0; frac = 0.1
    trades = []; equity = [1.0]
    for i in range(n - 1):
        if not in_pos and bool(enter_mask.iloc[i]):
            in_pos = True; entry_i = i + 1; entry = opens[i + 1]; frac = single[i + 1]
        elif in_pos:
            exit_now = bool(exit_mask.iloc[i])
            if closes[i] < entry * (1 - stop_loss):
                exit_now = True
            hold = i - entry_i
            if hold > time_stop and closes[i] <= entry:
                exit_now = True
            if exit_now:
                px = opens[i + 1]; ret = px / entry - 1
                trades.append(ret); equity.append(equity[-1] * (1 + ret * frac))
                in_pos = False
    eq = np.array(equity)
    peak = np.maximum.accumulate(eq); dd = (eq - peak) / peak
    max_dd = dd.min()
    return trades, eq, {"final_equity": eq[-1], "max_drawdown": max_dd}


def compute_metrics(trades_list, frac=0.10):
    """从全样本 trade 收益率列表构建统一权益曲线与指标。"""
    eq = [1.0]
    for r in trades_list:
        eq.append(eq[-1] * (1 + r * frac))
    eq = np.array(eq)
    peak = np.maximum.accumulate(eq); dd = (eq - peak) / peak
    tr = np.array(trades_list)
    if len(tr) == 0:
        return {"trades": 0, "win_rate": 0.0, "avg_ret": 0.0,
                "profit_factor": 0.0, "max_drawdown": 0.0, "final_equity": 1.0}
    wins = tr[tr > 0]; losses = tr[tr <= 0]
    pf = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else (np.inf if len(wins) else 0.0)
    return {
        "trades": len(tr), "win_rate": len(wins) / len(tr),
        "avg_ret": tr.mean(), "profit_factor": pf,
        "max_drawdown": dd.min(), "final_equity": eq[-1],
    }


def main():
    print("拉取行情（沙箱受限，仅部分标的成功）...")
    data = fetch_universe(UNIVERSE, sleep=0.15)
    print(f"成功标的: {len(data)} / {len(UNIVERSE)}")
    if not data:
        print("无可用数据，无法回测。请在用户本机运行（取消沙箱网络限制）。")
        return

    variant_names = None
    all_trades = {}      # name -> [trade returns across all stocks]
    bench_rets = []
    first_last = []

    for code, ohlcv in data.items():
        daily = ohlcv["daily"].copy()
        daily = daily[daily["date"] <= BACKTEST_END]
        if len(daily) < 300:
            continue
        from framework import compute_indicators
        daily = compute_indicators(daily)
        ohlcv_t = dict(ohlcv); ohlcv_t["daily"] = daily
        sig = build_signals(ohlcv_t)
        variants = _mask_from_sig(sig, daily)
        if variant_names is None:
            variant_names = list(variants.keys())
            all_trades = {k: [] for k in variant_names}
        for name, (em, xm) in variants.items():
            trades, _, _ = run_backtest(sig, daily, em, xm)
            all_trades[name].extend(trades)
        # 买入持有基准（等权）
        c = daily["close"].values
        bench_rets.append(c[-1] / c[0] - 1)
        first_last.append((daily["date"].iloc[0].date(), daily["date"].iloc[-1].date()))

    # 基准
    bh = np.mean(bench_rets)
    print(f"\n基准 买入持有(等权 {len(bench_rets)} 只): 区间收益 {bh*100:.1f}%  "
          f"({first_last[0][0]} ~ {first_last[0][1]})")

    print("\n================== 回测汇总（2019–2025） ==================")
    print(f"{'变体':<22}{'笔数':>6}{'胜率':>8}{'均收益':>9}{'盈亏比':>8}{'最大回撤':>10}{'净值':>10}")
    results = {}
    for name in variant_names:
        m = compute_metrics(all_trades[name])
        pf = m["profit_factor"]
        pf_s = f"{pf:.2f}" if np.isfinite(pf) else "inf"
        print(f"{name:<20}{m['trades']:>6}{m['win_rate']*100:>7.1f}%"
              f"{m['avg_ret']*100:>8.2f}%{pf_s:>8}{m['max_drawdown']*100:>9.1f}%"
              f"{m['final_equity']:>9.2f}x")
        results[name] = m

    print("\n================== 口诀有效性结论 ==================")
    base = results.get("基线(ABC)")
    if base:
        print(f"基线(ABC) 净值 {base['final_equity']:.2f}x，胜率 {base['win_rate']*100:.1f}%，"
              f"盈亏比 {base['profit_factor']:.2f}，回撤 {base['max_drawdown']*100:.1f}%")
    print("判定：相对基线净值↑且回撤不恶化 => 该口诀有效；净值↓ => 实测亏，剔除。")
    print("观察：")
    for name in variant_names:
        if name == "基线(ABC)":
            continue
        m = results[name]
        delta = m["final_equity"] - base["final_equity"]
        if delta > 0.01:
            tag = "有效↑"
        elif delta < -0.01:
            tag = "实测亏↓(剔除)"
        else:
            tag = "冗余/中性(已内含)"
        print(f"  {name:<18} 净值 {m['final_equity']:.2f}x ({delta:+.2f})  胜率 {m['win_rate']*100:.1f}%  -> {tag}")
    print("\n(完整无偏结论需在本机跑全市场后得出；蓝筹样本本身偏保守，题材/周期股结论可能相反。)")


if __name__ == "__main__":
    main()
