#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sanity_check_card.py — 评分卡量纲一致性校验（消除「看对了却被记成错」的假失败）
====================================================================================
核心：期限(period) + 幅度区间(target) + 证伪位(falsification) 必须数学自洽。

  σ_d  = 日波动率（对数收益标准差，**期限匹配窗口**，见下）
  σ_p  = σ_d × √(period_days)                      （期间波动率）
  R1   = (target_high − target_low) / σ_p          （幅度宽度比）
  R2   = |current − falsification| / current / σ_p （证伪距离比）

判定：
  R1 < 1.0  → ❌ 幅度区间过窄，几乎必然落空。建议宽度 ≥ __%
  R1 > 3.0  → ⚠️ 幅度区间过宽，判断无信息量。建议收窄至 __%
  R2 < 1.5  → ❌ 证伪位距现价过近（仅 __σ），期间必被噪音打掉。建议 ≥ __%
  R2 > 4.0  → ⚠️ 证伪位过远，形同没有止损

输出 pass / fail + 具体建议数值。fail 时退出码非 0。

═══════════════════════════════════════════════════════════════════════════════
⚠️ σ 估计窗口纪律（2026-09-17 修正 · 本条是历史误判的根因）
═══════════════════════════════════════════════════════════════════════════════
**旧版固定用过去 250 个交易日算 σ_d**，这是错的。当品种刚经历一段高波动（暴涨/暴跌）
然后进入低波动横盘时，250 日窗口会把**已经过去的旧波动制度**残留进 σ，导致 σ_p 被高估
数倍，进而把「幅度区间»判成过窄»、把「证伪位»判成过近»——**假失败**，污染校准曲线。

  2026-09-17 涪陵电力（600452）实锤：
    近 20 日窗口  日σ=0.933% → σ₂₀ = 4.17%
    近 60 日窗口  日σ=2.174% → σ₂₀ = 9.72%
    近 250 日窗口 日σ=2.764% → σ₂₀ = 12.36%   ← 旧版默认，掺入 3–6 月 16元→8.6元 崩跌段
    EWMA(λ=0.94) 日σ=1.439% → σ₂₀ = 6.43%
  同一张评分卡在三种口径下，R2 分别为 1.50 / 0.64 / 0.51 —— **「通过 / 不通过」的结论直接翻转**。
  旧版 250 日口径要求的证伪位距离是 ±18.5%，对一个当前日波动不足 1% 的标的是荒谬的。

**修正后的默认口径（--sigma-mode match，默认）**：
    σ_d 用**与预测期限匹配的窗口**：lookback = clamp(period_days, 20, 250)
    （给 20 日预测就用近 20 个日收益；给 60 日预测就用近 60 个）
**同时输出四个估计量**（窗口=期限 / EWMA λ=0.94 / 窗口=60 / 窗口=250）作为诊断，
**且当「期限匹配 σ」与「250 日 σ」之比超出 [0.67, 1.50] 时打 ⚠️ 制度切换警告**——
提醒分析者：本卡的量纲判定对 σ 口径敏感，必须在报告里**显式声明用的是哪个 σ**。

可用模式：
  --sigma-mode match   （默认）lookback = clamp(period_days,20,250)
  --sigma-mode ewma     EWMA λ=0.94（对制度切换反应最快，约 11 日半衰期）
  --sigma-mode window   固定窗口，用 --sigma-lookback 指定（旧版默认 250 → --sigma-window-legacy）
  --sigma-mode conservative  σ_d = max(match, ewma, 250)：最宽口径，宁可要求更远止损
  --sigma-mode legacy    完全复现 2026-09-17 之前的行为（固定 250 日），仅供历史卡重算

用法
----
  python3 tools/sanity_check_card.py --symbol 600452 --period-days 20 \
      --current 9.12 --target-low -0.0406 --target-high 0.0307 --falsification 9.69
  python3 tools/sanity_check_card.py --help
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE_DIR = os.path.join(ROOT, "market-data-cache")

# 价格四舍五入容差：证伪位/目标位按 2 位小数报价，1.5σ 边界上 ±0.05% 属四舍五入伪影，不判失败
R2_EPS = 0.005
R1_EPS = 0.005

LEGACY_LOOKBACK = 250
EWMA_LAMBDA = 0.94
EWMA_SEED = 60
REGIME_LO, REGIME_HI = 0.67, 1.50


def _load_closes(symbol, asof=None):
    rows = []
    for ext in (".csv", ".json", ".txt"):
        p = os.path.join(CACHE_DIR, symbol + ext)
        if os.path.exists(p):
            try:
                if ext == ".csv":
                    import csv
                    with open(p, encoding="utf-8") as f:
                        for r in csv.DictReader(f):
                            c = r.get("close")
                            if c not in (None, ""):
                                rows.append(float(c))
                elif ext == ".txt":
                    # 新浪期货日K（2026-09-18 新增）：整文件是一个 JSON 数组，
                    # 键为 d/o/h/l/c/v/p/s —— 不解析它，国内商品期货的 σ 恒算不出，
                    # 量纲闸门（R1≥1σ / R2≥1.5σ）对期货整类品种静默失效。
                    raw = open(p, encoding="utf-8").read()
                    i, j = raw.find("["), raw.rfind("]")
                    if i >= 0 and j > i:
                        for r in json.loads(raw[i:j + 1]):
                            c = r.get("c")
                            if c not in (None, ""):
                                rows.append(float(c))
                else:
                    with open(p, encoding="utf-8") as f:
                        for r in json.load(f):
                            rows.append(float(r["close"]))
            except Exception:
                rows = []
    if rows:
        return rows
    # akshare 兜底
    try:
        import akshare as ak  # type: ignore
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                start_date="20000101", end_date="20260101", adjust="")
        if df is not None:
            rows = [float(x) for x in df["收盘"]]
    except Exception:
        pass
    return rows


def _log_rets(closes):
    return [math.log(closes[i + 1] / closes[i]) for i in range(len(closes) - 1)]


def _stdev(xs):
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _log_ret_stdev(closes, lookback=LEGACY_LOOKBACK):
    """保留旧签名（append.py / 外部脚本可能引用）。窗口不足时用全部样本。"""
    if len(closes) < lookback + 1:
        sample = closes
    else:
        sample = closes[-(lookback + 1):]
    return _stdev(_log_rets(sample))


def _ewma_stdev(rets, lam=EWMA_LAMBDA, seed=EWMA_SEED):
    """RiskMetrics: σ²_t = λσ²_{t−1} + (1−λ)r²_{t−1}；用前 seed 个收益率的等权方差做初值。"""
    if len(rets) < 2:
        return None
    s = min(seed, len(rets))
    var = sum(x * x for x in rets[:s]) / s
    for x in rets[s:]:
        var = lam * var + (1 - lam) * x * x
    return math.sqrt(var)


def _pick_sigma(closes, period_days, mode="match", lookback=None):
    """返回 (sigma_d, basis_str, diagnostics_dict)。"""
    rets = _log_rets(closes)
    if len(rets) < 2:
        return None, "", {}

    n = len(closes)
    lb_match = max(20, min(int(period_days), 250))
    sig_match = _stdev(rets[-lb_match:]) if len(rets) >= lb_match else _stdev(rets)
    sig_ewma = _ewma_stdev(rets)
    sig_60 = _stdev(rets[-60:]) if len(rets) >= 60 else _stdev(rets)
    sig_250 = _stdev(rets[-250:]) if len(rets) >= 250 else _stdev(rets)

    diag = {
        "bars": n,
        "sigma_d_match_pct": round(sig_match * 100, 3) if sig_match else None,
        "sigma_d_match_window": lb_match,
        "sigma_d_ewma094_pct": round(sig_ewma * 100, 3) if sig_ewma else None,
        "sigma_d_w60_pct": round(sig_60 * 100, 3) if sig_60 else None,
        "sigma_d_w250_pct": round(sig_250 * 100, 3) if sig_250 else None,
    }
    if sig_250 and sig_match:
        diag["regime_ratio_match_vs_w250"] = round(sig_match / sig_250, 3)

    if mode == "legacy":
        lb = lookback or LEGACY_LOOKBACK
        sig = _stdev(rets[-lb:]) if len(rets) >= lb else _stdev(rets)
        diag["sigma_d_legacy_window"] = lb
        basis = "legacy窗口%d日（2026-09-17 前旧行为，仅历史重算用）" % lb
    elif mode == "window":
        lb = lookback or LEGACY_LOOKBACK
        sig = _stdev(rets[-lb:]) if len(rets) >= lb else _stdev(rets)
        basis = "固定窗口%d日" % lb
    elif mode == "ewma":
        sig = sig_ewma
        basis = "EWMA λ=0.94（约11日半衰期）"
    elif mode == "conservative":
        cands = [x for x in (sig_match, sig_ewma, sig_250) if x]
        sig = max(cands)
        basis = "保守口径=max(期限匹配/EWMA/250日)"
    else:  # match
        sig, basis = sig_match, "期限匹配窗口%d日（与预测期限一致）" % lb_match
    return sig, basis, diag


def check_card(symbol, period_days, current, target_low, target_high, falsification,
               asof=None, sigma_mode="match", sigma_lookback=None,
               falsification_low=None):
    """返回 (ok_bool, report_dict)。ok=False 表示存在 ❌ 项。

    falsification_low：可选，双侧证伪位的下侧价位。给定时同时校验下侧距离。
    """
    closes = _load_closes(symbol, asof)
    report = {"symbol": symbol, "period_days": period_days,
              "current": current, "target_low": target_low,
              "target_high": target_high, "falsification": falsification,
              "sigma_mode": sigma_mode}
    if falsification_low is not None:
        report["falsification_low"] = falsification_low

    sigma_d, basis, diag = _pick_sigma(closes, period_days, sigma_mode, sigma_lookback)
    report.update(diag)
    report["sigma_basis"] = basis
    if sigma_d is None:
        report["error"] = "历史收盘价不足，无法估计日波动率"
        report["ok"] = False
        return False, report

    sigma_p = sigma_d * math.sqrt(period_days)
    r1 = (target_high - target_low) / sigma_p
    r2 = abs(current - falsification) / current / sigma_p
    r2_low = None
    if falsification_low is not None:
        r2_low = abs(current - falsification_low) / current / sigma_p

    issues = []      # ❌ 阻断项
    warnings = []    # ⚠️ 仅警告
    suggestions = {}

    # 幅度宽度比 R1
    if r1 < 1.0 - R1_EPS:
        suggestions["target_width_min_pct"] = round(sigma_p * 100, 2)
        issues.append("❌ 幅度区间过窄（R1=%.2f < 1.0），几乎必然落空" % r1)
    elif r1 > 3.0:
        warnings.append("⚠️ 幅度区间过宽（R1=%.2f > 3.0），判断无信息量" % r1)
        suggestions["target_width_suggest_pct"] = round(sigma_p * 2.0 * 100, 2)

    # 证伪距离比 R2
    if r2 < 1.5 - R2_EPS:
        suggestions["falsification_min_dist_pct"] = round(1.5 * sigma_p * 100, 2)
        issues.append("❌ 证伪位距现价过近（R2=%.2f < 1.5），%.0f 日内必被噪音打掉"
                      % (r2, period_days))
    elif r2 > 4.0:
        warnings.append("⚠️ 证伪位过远（R2=%.2f > 4.0），形同没有止损" % r2)

    if r2_low is not None and r2_low < 1.5 - R2_EPS:
        suggestions["falsification_low_min_dist_pct"] = round(1.5 * sigma_p * 100, 2)
        issues.append("❌ 下侧证伪位距现价过近（R2下=%.2f < 1.5）" % r2_low)

    # σ 口径敏感 / 制度切换警告
    rr = diag.get("regime_ratio_match_vs_w250")
    if rr is not None and not (REGIME_LO <= rr <= REGIME_HI):
        warnings.append(
            "⚠️ σ 制度切换：期限匹配 σ 为 250 日 σ 的 %.2f 倍（超出 [%.2f,%.2f]）——"
            "本卡量纲判定对 σ 口径高度敏感，报告必须显式声明 σ 口径与数值" % (rr, REGIME_LO, REGIME_HI))
    alt = {}
    for k, lbl in (("sigma_d_match_pct", "match"), ("sigma_d_ewma094_pct", "ewma"),
                   ("sigma_d_w250_pct", "w250")):
        v = diag.get(k)
        if v:
            alt[lbl] = round(v * math.sqrt(period_days), 2)
    report["sigma_p_pct_by_basis"] = alt
    # 同一张卡在不同 σ 口径下的证伪距离比与判定——用于暴露「口径敏感」
    dist = abs(current - falsification) / current
    report["r2_by_basis"] = {lbl: round(dist / (pct / 100.0), 2) for lbl, pct in alt.items()}
    report["verdict_by_basis"] = {
        lbl: ("pass" if (1.5 - R2_EPS) <= (dist / (pct / 100.0)) <= 4.0 else "fail")
        for lbl, pct in alt.items()}
    if len(set(report["verdict_by_basis"].values())) > 1:
        warnings.append("⚠️ 口径敏感：同一张卡在 match / ewma / w250 三种 σ 口径下判定不一致"
                        "（%s）——必须在报告中显式声明采用哪一口径及理由"
                        % report["verdict_by_basis"])

    report.update({
        "sigma_d_pct": round(sigma_d * 100, 3),
        "sigma_p_pct": round(sigma_p * 100, 3),
        "R1": round(r1, 3),
        "R2": round(r2, 3),
        "R2_low": round(r2_low, 3) if r2_low is not None else None,
        "issues": issues,
        "warnings": warnings,
        "suggestions": suggestions,
        "ok": len(issues) == 0,
    })
    return (len(issues) == 0), report


def main():
    ap = argparse.ArgumentParser(description="评分卡量纲一致性校验")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--period-days", type=int, required=True)
    ap.add_argument("--current", type=float, required=True, help="当前价")
    ap.add_argument("--target-low", type=float, required=True, help="幅度下界（小数，如0.05）")
    ap.add_argument("--target-high", type=float, required=True, help="幅度上界（小数，如0.15）")
    ap.add_argument("--falsification", type=float, required=True, help="证伪价位（上侧）")
    ap.add_argument("--falsification-low", type=float, default=None,
                    help="下侧证伪价位（双侧证伪时给）")
    ap.add_argument("--sigma-mode", default="match",
                    choices=["match", "ewma", "window", "conservative", "legacy"],
                    help="σ 估计口径（默认 match=期限匹配窗口）")
    ap.add_argument("--sigma-lookback", type=int, default=None,
                    help="配合 --sigma-mode window/legacy 使用")
    ap.add_argument("--asof", default=None)
    args = ap.parse_args()

    ok, rep = check_card(args.symbol, args.period_days, args.current,
                         args.target_low, args.target_high, args.falsification,
                         args.asof, args.sigma_mode, args.sigma_lookback,
                         args.falsification_low)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
