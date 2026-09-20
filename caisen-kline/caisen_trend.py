# -*- coding: utf-8 -*-
"""四色K线趋势层（EMA12 / EMA50）—— 蔡森出图的固定配色层（作者 2026-09-20 定稿）

来源：作者提供的 Pine v5 指标「多空四色K线-连续趋势版」，本模块把它落地到
matplotlib 出图管线（mplfinance 不支持逐根任意配色，故自绘 K 线）。

Pine 原义（严格照抄，不改语义）：
    fast = ta.ema(close, 12)
    slow = ta.ema(close, 50)
    red    = close >= fast and close >= slow   → 多头强势区（连续红）
    yellow = close <  fast and close >= slow   → 多头回调
    blue   = close >= fast and close <  slow   → 空头反弹
    green  = close <  fast and close <  slow   → 空头弱势区（连续绿）

本模块的 3 条硬约定：
  1. **仅作展示层**。四色状态绝不参与 A/B/K 招（颈线/等幅/失败）判定 —— 蔡森体系是
     纯形态几何，掺进均线交叉会污染方法论（方法论内部矛盾属 C3 约束范畴）。
     四色只做两件事：给图上色 + 与形态方向做**一致性交叉校验**（背离时提示人工复核）。
  2. **颜色在白底可读**。Pine 的纯 yellow(#FFFF00)/green(#00FF00) 在白底几乎看不见，
     同语义改成可读色号（见 STATE_COLOR），语义不变、色号变。
  3. **暖机区如实标注**。EMA 无真值，靠递推衰减。种子影响衰减到 1% 以下所需根数
     （span=50 → 116 根，span=12 → 28 根）内的颜色**一律半透明**，并在图上画分隔线 +
     图下文字说明。数据不足时明确提示「建议加大取数根数」，不假装可信。
"""
from __future__ import annotations

import math

import pandas as pd

FAST_SPAN = 12
SLOW_SPAN = 50

STATE_ORDER = ('R', 'Y', 'B', 'G')

# 语义同 Pine，色号适配白底可读性
STATE_COLOR = {
    'R': '#d81e06',   # 多头强势区（原 color.red）
    'Y': '#e8a33d',   # 多头回调（原 color.yellow，提饱和以便白底可读）
    'B': '#1565c0',   # 空头反弹（原 color.blue）
    'G': '#12a13f',   # 空头弱势区（原 color.green，压暗以便白底可读）
}

STATE_LABEL = {
    'R': '多头强势区',
    'Y': '多头回调区',
    'B': '空头反弹区',
    'G': '空头弱势区',
}

# 多空阵营：R/Y = 多头侧（收盘在 EMA50 之上）；B/G = 空头侧
STATE_SIDE = {'R': 'bull', 'Y': 'bull', 'B': 'bear', 'G': 'bear'}

SIDE_LABEL = {'bull': '多头侧', 'bear': '空头侧'}

EMA_FAST_COLOR = '#ff9800'   # EMA12（原 Pine 脚本 fast 色）
EMA_SLOW_COLOR = '#7b1fa2'   # EMA50 —— 原 Pine 用 blue，这里改紫：避免与「空头反弹蓝」同色混淆

LEGEND_LINE = ('■ 红=多头强势  ■ 黄=多头回调  ■ 蓝=空头反弹  ■ 绿=空头弱势'
               '   ─ EMA12  ─ EMA50   实心=收阴 空心=收阳（颜色=EMA状态）')

WARMUP_ALPHA = 0.72          # 暖机区 K 线透明度（轻度淡化：既标出低置信，又不让图发白）
DATA_SHORT_ALPHA = 0.45      # 数据根数 < 暖机根数时：全图无一根可信，重淡化 + 红字警讯
WARMUP_TOL = 0.01            # 种子影响阈值（1%）


# ---------------------------------------------------------------- 基础计算

def alpha_of(span: int) -> float:
    """Pine/标准 EMA 平滑系数 α = 2/(span+1)。"""
    return 2.0 / (span + 1.0)


def warmup_bars(span: int, tol: float = WARMUP_TOL) -> int:
    """种子影响衰减到 tol 以下所需根数。

    误差 ∝ (1-α)^n → n = ln(tol)/ln(1-α)。span=50 → 116 根；span=12 → 28 根。
    （EMA 无解析真值，这是「多长之后颜色可以当准」的工程估计，非精确定理。）
    """
    a = alpha_of(span)
    if a >= 1.0:
        return 1
    if tol >= 1.0:
        return 0
    return int(math.ceil(math.log(tol) / math.log(1.0 - a)))


def ema(close: pd.Series, span: int) -> pd.Series:
    """标准递推 EMA（首根以首值为种子，与 Pine ta.ema 行为一致；不做 NaN 屏蔽，
    暖机区由 alpha 与标注单独处理）。"""
    return close.ewm(span=span, adjust=False, min_periods=1).mean()


def classify(close: pd.Series, fast: pd.Series, slow: pd.Series) -> pd.Series:
    """逐根判四色状态（严格照 Pine 语义，四个分支互斥且完备）。"""
    out = []
    for c, f, s in zip(close.astype(float), fast.astype(float), slow.astype(float)):
        if c >= f and c >= s:
            out.append('R')
        elif c < f and c >= s:
            out.append('Y')
        elif c >= f and c < s:
            out.append('B')
        else:
            out.append('G')
    return pd.Series(out, index=close.index, dtype=object)


def side_flips(state: pd.Series, min_persist: int = 3) -> list:
    """多空阵营（R/Y ↔ B/G）侧切换点。

    噪声过滤：新阵营必须**连续保持** min_persist 根才认，否则视为穿越噪声。
    返回 [{i, date, frm, to, state}]，frm/to ∈ {bull,bear}。
    """
    vals = list(state.values)
    idx = list(state.index)
    n = len(vals)

    def sd(k):
        return STATE_SIDE.get(vals[k])

    res, cur, i = [], None, 0
    while i < n:
        s = sd(i)
        if s is None:
            i += 1
            continue
        if cur is None:
            cur = s
            i += 1
            continue
        if s != cur:
            run, j = 0, i
            while j < n and run < min_persist:
                sj = sd(j)
                if sj is None:
                    j += 1
                    continue
                if sj != s:
                    break
                run += 1
                j += 1
            if run >= min_persist:
                res.append(dict(i=i, date=str(idx[i])[:10], frm=cur, to=s,
                                state=vals[i]))
                cur = s
                i = j
                continue
        i += 1
    return res


def state_span(state: pd.Series) -> tuple:
    """返回 (最新色连续根数, 最新阵营连续根数)。"""
    vals = list(state.values)
    if not vals:
        return 0, 0
    last = vals[-1]
    k = 0
    for v in reversed(vals):
        if v == last:
            k += 1
        else:
            break
    side = STATE_SIDE.get(last)
    j = 0
    for v in reversed(vals):
        if STATE_SIDE.get(v) == side:
            j += 1
        else:
            break
    return k, j


# ---------------------------------------------------------------- 量价读取

def vol_price_read(df: pd.DataFrame, ma: int = 5, look: int = 5) -> dict:
    """量价配合读数（近 look 根 vs 前 look 根，量能 + 价格双维）。"""
    vol = df['volume'].astype(float)
    close = df['close'].astype(float)
    v_ma = vol.rolling(ma, min_periods=1).mean()
    last_v = float(vol.iloc[-1])
    last_ma = float(v_ma.iloc[-1])
    v_ratio = (last_v / last_ma) if last_ma else float('nan')

    n = len(df)
    k = min(look, max(1, n // 4))
    dpx = float(close.iloc[-1] - close.iloc[-1 - k])
    pct = dpx / float(close.iloc[-1 - k]) if float(close.iloc[-1 - k]) else 0.0
    v_now = float(vol.iloc[-k:].mean())
    v_prev = float(vol.iloc[-2 * k:-k].mean()) if n > 2 * k else float('nan')
    v_chg = (v_now / v_prev - 1.0) if (v_prev and v_prev == v_prev) else float('nan')

    up = pct > 0.005
    dn = pct < -0.005
    heavy = (v_chg == v_chg) and v_chg > 0.10
    light = (v_chg == v_chg) and v_chg < -0.10

    if up and heavy:
        tag, warn = "价升量增（量能配合，健康）", False
    elif up and light:
        tag, warn = "价升量减（量价背离，上行缺量支撑）", True
    elif dn and heavy:
        tag, warn = "价跌量增（抛压释放中，须等缩量企稳）", True
    elif dn and light:
        tag, warn = "价跌量缩（缩量止跌，仍需地量+持仓确认）", False
    else:
        tag, warn = "量价平稳（无明确量能信号）", False

    return dict(v_ma=last_ma, v_ratio=v_ratio, dpx=dpx, pct=pct,
                v_chg=v_chg, look=k, tag=tag, warn=warn,
                v_now=v_now, v_prev=v_prev)


# ---------------------------------------------------------------- 汇总

def compute(df: pd.DataFrame, fast: int = FAST_SPAN, slow: int = SLOW_SPAN,
            min_persist: int = 3, vol_ma: int = 5) -> dict:
    """一次算全：EMA、四色状态、暖机区、侧切换。

    返回 dict：
      ema_fast/ema_slow : pd.Series（与 df.index 对齐）
      state             : pd.Series of 'R'/'Y'/'B'/'G'
      warmup            : 暖机根数（前 N 根颜色低置信）
      warmup_fast       : 快线暖机根数（用于文案）
      flips             : 侧切换列表
      span_color/span_side : 最新色/最新阵营连续根数
      data_short        : 数据根数 < 暖机根数（全线低置信，需提示加大取数）
    """
    close = df['close'].astype(float)
    f = ema(close, fast)
    s = ema(close, slow)
    st = classify(close, f, s)
    wu = warmup_bars(slow)
    wu_f = warmup_bars(fast)
    kc, ks = state_span(st)
    return dict(
        ema_fast=f, ema_slow=s, state=st,
        warmup=wu, warmup_fast=wu_f,
        flips=side_flips(st, min_persist=min_persist),
        span_color=kc, span_side=ks,
        data_short=len(df) < wu,
        fast_span=fast, slow_span=slow, vol_ma=int(vol_ma),
    )


def summary_text(df: pd.DataFrame, trend: dict, meta=None, px=None,
                 direction: str | None = None) -> str:
    """四色节奏文字块（供文字副图「六」栏使用，压成 4~5 行避免撑爆文字副图）。

    px        : 价格格式化函数（可空）
    direction : 形态方向 'up'/'down'，给了就附「交叉校验」行
    """
    fmt = px or (lambda v: f"{v:g}")
    st = trend['state']
    last = str(st.index[-1])[:10]
    cur = st.values[-1]
    f = float(trend['ema_fast'].iloc[-1])
    s = float(trend['ema_slow'].iloc[-1])
    c = float(df['close'].astype(float).iloc[-1])
    kc, ks = trend['span_color'], trend['span_side']
    vr = vol_price_read(df)

    if trend['flips']:
        x = trend['flips'][-1]
        fl = (f"最近侧切换 {x['date']} {SIDE_LABEL[x['frm']]}→{SIDE_LABEL[x['to']]}"
              f"（≥3根确认）")
        if len(trend['flips']) >= 2:
            y = trend['flips'][-2]
            fl += f"；上一次 {y['date']} {SIDE_LABEL[y['frm']]}→{SIDE_LABEL[y['to']]}"
    else:
        fl = "区间内无确认的侧切换"

    vm = int(trend.get('vol_ma', 5))
    if vr['v_ratio'] == vr['v_ratio']:
        vt = (f"{vr['v_ratio']:.2f}×量MA{vm}"
              f"（{'放量' if vr['v_ratio'] >= 1.1 else ('缩量' if vr['v_ratio'] <= 0.9 else '平量')}）")
    else:
        vt = "量能数据不足"
    if vr['v_chg'] == vr['v_chg']:
        vc = (f"近{vr['look']}根均量 {vr['v_chg'] * 100:+.0f}%、"
              f"价格 {vr['pct'] * 100:+.1f}% → {vr['tag']}")
    else:
        vc = f"近{vr['look']}根量能基准不足，量价配合待确认"

    lines = [
        "【六、四色K线节奏（EMA12/EMA50·展示层，不参与A/B/K招判定）】",
        f"· 现状：{STATE_LABEL[cur]}｜该色已 {kc} 根、{SIDE_LABEL[STATE_SIDE[cur]]}已 {ks} 根｜{fl}",
        f"· 量价：最新量 {vt}｜{vc}",
    ]
    note = consistency_note(trend, direction) if direction else ""
    if note:
        lines.append(note.rstrip())
    # 暖机区/取数不足的提示不占文字副图行数：已写入主图与量图之间的图例带（见 caisen_chart）
    return "\n".join(lines) + "\n"


def consistency_note(trend: dict, direction: str) -> str:
    """四色阵营 vs 形态方向的一致性交叉校验（背离时提示人工复核，不自动改判）。"""
    if not trend or trend['state'].empty:
        return ""
    cur = trend['state'].values[-1]
    side = STATE_SIDE.get(cur)
    if side is None:
        return ""
    label = SIDE_LABEL[side]
    if direction == "up" and side == "bear":
        return (f"· 交叉校验：四色处于{label}（{STATE_LABEL[cur]}）而形态方向偏多 → "
                f"量价未转强前视为反弹，突破需量能确认。")
    if direction == "down" and side == "bull":
        return (f"· 交叉校验：四色处于{label}（{STATE_LABEL[cur]}）而形态方向偏空 → "
                f"下方仍有承接，破位需带量，缩量破位易假摔。")
    return f"· 交叉校验：四色{label}与形态方向一致 → 无背离，按形态纪律执行。"
