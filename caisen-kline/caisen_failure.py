#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蔡森 K 线分析 · S5 失败识别（K 招）
=====================================================
书里 K 招（形态失败的识别与应对）是全书最薄弱处，原书只有两张失败图。
本模块主动补强，避免 skill 继承幸存者偏差（只会一路唱多）。

识别的失败模式：
  1. 假突破：up 突破颈线后 FAIL_WINDOW 根内跌回颈线下 → 翻空（作空信号，书招 7/9）
  2. 假跌破/破底翻：down 突破颈线后 FAIL_WINDOW 根内站回颈线上 → 翻多（书招 2/3）
  3. 量价背离：突破后价升量缩（头部警讯，书 G 招）
  4. 异常量：突破后突发最大量但价未过前高（头部结构确认）
  5. 逃命线：跌破颈线后反弹站不回（多头最后离场）

设计要点：
  - 假突破/假跌破 → 返回 direction 反转，analyze 用 build_reversal_signal 翻转信号。
  - 量价背离/异常量/逃命线 → 不翻转方向，只作警讯证据记入 sig.failure + notes。
  - 所有判定为「几何观察」，非保证；对应 C1（书无回测）。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np
import pandas as pd

FAIL_WINDOW = 15  # 突破后回验窗口（根）。书里未给数字，取工程值：约 3 周日线。


@dataclass
class FailureSignal:
    type: str                       # 假突破/假跌破(破底翻)/量价背离/异常量/逃命线
    direction: str                 # 反转后方向 up/down；警讯类为 ""
    reason: str
    trigger_i: int
    trigger_date: str
    evidence: dict = field(default_factory=dict)


def check_failure(df, sig, p=None, window: int = FAIL_WINDOW) -> Optional[FailureSignal]:
    """analyze 选定 best 后调用。返回最严重的失败信号或 None。

    优先级：假突破/假跌破（翻转）> 量价背离 > 异常量 > 逃命线（警讯）。
    """
    if not sig.ok or not sig.breakout:
        return None
    bo = sig.breakout
    nk = sig.neckline
    direction = sig.direction
    n = len(df)
    bi = int(bo["i"])
    end = min(n, bi + 1 + window)
    if end <= bi + 1:
        return None
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    vol = df["volume"].values
    dates = df.index.strftime("%Y-%m-%d")
    eps = (p.break_close_pct if p else 0.005)

    bo_vol = float(df["volume"].iloc[bi])
    bo_close = float(df["close"].iloc[bi])

    # --- 1. 假突破 / 假跌破（最严重，翻转方向） ---
    if direction == "up":
        for i in range(bi + 1, end):
            if close[i] < nk * (1 - eps):
                return FailureSignal(
                    type="假突破", direction="down",
                    reason="突破颈线后未能站稳，很快跌回颈线之下——主力拉高出货骗线"
                           "（书招 7/9，最重要的作空信号）。原多头突破失效，转为空头。",
                    trigger_i=i, trigger_date=dates[i],
                    evidence={"break_date": bo["date"],
                               "fallback_close": round(float(close[i]), 4)})
    else:
        for i in range(bi + 1, end):
            if close[i] > nk * (1 + eps):
                return FailureSignal(
                    type="假跌破/破底翻", direction="up",
                    reason="跌破颈线后很快站回颈线上——甩轿洗浮额（书招 2/3，"
                           "比突破更早、更安全的进场点）。原空头跌破失效，转为多头。",
                    trigger_i=i, trigger_date=dates[i],
                    evidence={"break_date": bo["date"],
                               "reclaim_close": round(float(close[i]), 4)})

    # --- 2. 量价背离（头部警讯，不翻转） ---
    seg = slice(bi + 1, end)
    sc, sv = close[seg], vol[seg]
    if len(sc):
        hi = int(np.argmax(sc))
        if sc[hi] > bo_close and sv[hi] < bo_vol * 0.9:
            return FailureSignal(
                type="量价背离", direction="",
                reason="突破后价格创更高收盘价但成交量未超突破量——主力停止滚量作价，"
                       "头部警讯（书 G 招）。原方向未确认失败，但需警惕。",
                trigger_i=bi + 1 + hi, trigger_date=dates[bi + 1 + hi],
                evidence={"price_high": round(float(sc[hi]), 4),
                          "vol_ratio_vs_bo": round(float(sv[hi] / bo_vol), 2)})

    # --- 3. 异常量（头部结构确认，不翻转） ---
    if len(sv) and sv.max() >= bo_vol * 1.5:
        j = int(np.argmax(sv))
        if sc[j] < bo_close:  # 最大量但价未过突破价
            return FailureSignal(
                type="异常量", direction="",
                reason="突破后突发最大量（≥1.5×突破量）但价格未过突破价——头部结构确认证据"
                       "（书 G 招）。",
                trigger_i=bi + 1 + j, trigger_date=dates[bi + 1 + j],
                evidence={"vol_ratio_vs_bo": round(float(sv[j] / bo_vol), 2)})

    # --- 4. 逃命线（up 信号已跌破颈线，反弹站不回） ---
    if direction == "up" and close[-1] < nk:
        after = close[bi + 1:]
        if len(after) and after.max() < nk:
            j = int(np.argmax(after))
            return FailureSignal(
                type="逃命线", direction="",
                reason="跌破颈线后反弹但最高价仍低于颈线——多头最后离场机会"
                       "（书：逃命线）。",
                trigger_i=bi + 1 + j, trigger_date=dates[bi + 1 + j])

    return None


def build_reversal_signal(df, sig, fail, p=None):
    """由失败信号翻转方向，重建一份 ABSignal（等幅目标/停损/置信度全重算）。

    反转极点取「突破后窗口 [bi+1, trigger_i]」内最极端的那根：
      down（假突破翻空）→ 窗口内最高 high 当头，H = 头 - 颈线，目标向下等幅；
      up（假跌破翻多/破底翻）→ 窗口内最低 low 当底，H = 颈线 - 底，目标向上等幅。
    进场取「失败确认根」(trigger_i) 收盘价，停损锁在颈线另一侧（跌破/站回即确认）。
    """
    from caisen_ab import ABParams, atr, ABSignal
    p = p or ABParams()
    a = atr(df)
    atr_v = float(a.iloc[-1])
    n = len(df)
    nk = sig.neckline
    bi = int(sig.breakout["i"])
    new_dir = fail.direction
    bo = sig.breakout
    bo_vol = float(df["volume"].iloc[bi])

    end = min(n, fail.trigger_i + 1)
    seg = df.iloc[bi + 1: end]
    if new_dir == "down":
        ei = int(seg["high"].values.argmax()) + bi + 1
        ep = float(df["high"].iloc[ei])
        height = ep - nk
        t1, t2 = nk - height, nk - 2 * height
        raw_stop = nk + atr_v * p.stop_atr_mult
        stop = min(max(raw_stop, nk * (1 + p.stop_pct_min)), nk * (1 + p.stop_pct_max))
    else:
        ei = int(seg["low"].values.argmin()) + bi + 1
        ep = float(df["low"].iloc[ei])
        height = nk - ep
        t1, t2 = nk + height, nk + 2 * height
        raw_stop = nk - atr_v * p.stop_atr_mult
        stop = max(min(raw_stop, nk * (1 - p.stop_pct_min)), nk * (1 - p.stop_pct_max))
    stop_pct = abs(stop - nk) / nk
    last_close = float(df["close"].iloc[-1])
    entry = float(df["close"].iloc[fail.trigger_i])   # 失败确认根收盘进场
    risk = abs(entry - stop)
    rr = abs(t1 - entry) / risk if risk > 1e-9 else 0.0

    # 置信度：幅度 + 失败类型
    pts = 0
    pts += 1 if height >= atr_v * 1.2 else 0
    pts += 1 if height >= atr_v * 2 else 0
    pts += 1 if fail.type == "假突破" else 0
    pts += 1 if fail.type == "假跌破/破底翻" else 0
    confidence = "高" if pts >= 2 else ("中" if pts >= 1 else "低")

    vma = float(pd.Series(df["volume"].values).rolling(
        p.vol_lookback, min_periods=3).mean().iloc[bi]) if bi > 0 else 0.0
    bo_vol_ratio = round(bo_vol / vma, 2) if vma > 0 else 0.0

    # S13：原形态的「完成度事实」必须随反转信号传下来，否则丢失关键诊断——
    #   原形态曾兑现等幅目标再翻空 → 完成后反转（获利回吐/趋势反转）；
    #   从未达标就翻空            → 教科书假突破（突破从未被市场接受）。
    # 二者性质不同，缺了它反转信号只剩一句「假突破」，容易误导。
    _o_done = bool(getattr(sig, "completed", False))
    _o_after = float(getattr(sig, "extreme_after", 0.0) or 0.0)
    _o_at = str(getattr(sig, "completed_at", "") or "")
    if _o_done:
        _s13_note = (f"原形态曾于 {_o_at} 兑现等幅目标①（突破后最高 {_o_after:.2f}）→ "
                     f"本次翻空属「完成后反转」，不是突破当日即失败的典型假突破。")
    else:
        _s13_note = (f"原形态突破后最高仅 {_o_after:.2f}，从未触及等幅目标① "
                     f"{sig.target1:.2f} → 典型假突破，突破自始未被市场接受。")

    return ABSignal(
        ok=True,
        pattern=("假突破（翻空）" if new_dir == "down" else "破底翻（翻多）"),
        pattern_basis=fail.reason,
        direction=new_dir,
        confidence=confidence,
        neckline=round(nk, 4),
        neck_touches=sig.neck_touches,
        neck_start=sig.neck_start, neck_start_i=sig.neck_start_i,
        extreme={"date": df.index[ei].strftime("%Y-%m-%d"), "price": round(ep, 4), "i": ei},
        height=round(height, 4),
        breakout={**bo, "failed": True},
        entry=round(entry, 4), stop=round(stop, 4), stop_pct=round(stop_pct, 4),
        target1=round(t1, 4), target2=round(t2, 4), rr=round(rr, 2),
        last_close=round(last_close, 4), atr=round(atr_v, 4),
        evidence={**sig.evidence, "reversal_type": fail.type,
                  "vol_ratio_vs_bo": bo_vol_ratio},
        notes=[
            f"警讯 K招失败识别：{fail.type}（{fail.trigger_date}）→ 方向翻转至"
            f"{('空头' if new_dir == 'down' else '多头')}。原突破 {bo['date']} 失效。",
            f"反转形态高度 {height:.2f}，等幅目标① {t1:.2f}（C1：几何外推非保证）。",
            _s13_note,
        ],
        failure=asdict(fail),
        orig_direction=sig.direction,
        failure_type=fail.type,
        # S13 原形态完成度事实（见上方 _s13_note 说明）
        completed=_o_done, completed_at=_o_at,
        t2_reached=bool(getattr(sig, "t2_reached", False)),
        extreme_after=round(_o_after, 4),
        extreme_after_date=str(getattr(sig, "extreme_after_date", "") or ""),
        retrace_kind="",   # 已翻转：破位定性由 failure_type 表达，此处留空
    )
