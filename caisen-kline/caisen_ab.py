#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔡森 K 线分析 · A+B 自动识别引擎 (S2)
=====================================================
把 methodology_A_B.md 的规格变成**零人工填参**的算法。

设计主线（为什么这么做）
------------------------
颈线不是"人看出来的一条线"，而是**多个反弹高点/回档低点在同一价位反复触碰**
留下的统计痕迹。所以流程是：

    ZigZag 摆动极值  →  价位聚类（同一水平的触点归堆）
                      →  按「点多为主」给每簇打分
                      →  最高分那簇 = 颈线
                      →  簇的首个触点 = 颈线起点（修 P1-2：不再画到全图最左端）
                      →  末次触碰之后找突破  →  等幅满足算目标

对照 run_600519.py：颈线 1265、突破日、取样点全是人工硬编码。
本模块换任何标的都自己算，人只提供 OHLCV。

诚实声明（写进代码，防止日后自欺）
----------------------------------
- 阈值（swing_pct / cluster_tol / 量能倍数）是**依据书中定性描述取的工程值**，
  书里没有给数字，也没有回测。不同市场波动率差异大，已做 ATR 自适应，
  但仍属未经验证的参数选择 —— 对应 C1 幸存者偏差。
- 本模块只负责「算出来」，不负责「说它一定对」。判定强度一律带 confidence。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal

import numpy as np
import pandas as pd


# ===================================================================
# 0. 参数（全部可调，默认值的由来写在注释里）
# ===================================================================

@dataclass
class ABParams:
    # --- ZigZag 摆动幅度阈值 ---
    # 注意：这里卡的是「相邻反向极值之间的腿幅」，不是单根 K 线振幅。
    # 1.6×ATR 对底部第二脚/弱势反弹太狠——茅台 06-12 反弹 1266.98 距前低 42 点、
    # 仅 ≈1.5×ATR 就被丢掉，导致 W 底颈线触点不够。调到 1.1，配合分形(k=2)已足够滤噪。
    swing_atr_mult: float = 1.1     # 摆动幅度 ≥ 1.1×ATR 才算一个转折（自适应波动率）
    swing_pct_floor: float = 0.012  # 且不低于 1.2%（防低波动品种把噪声当摆动）
    fractal_k: int = 2              # 分形确认：左右各 k 根都不超过它

    # --- 价位聚类（同一条水平线的触点归堆）---
    cluster_atr_mult: float = 0.8   # 两点价差 ≤ 0.8×ATR 视为同一水平
    min_touch: int = 2              # 至少 2 个触点才配称颈线（书：点多为主，≥2）

    # --- 整理区 ---
    min_bars: int = 15              # 规格 A1：整理区至少 15 根
    choppy_th: float = 0.4          # 规格 A1：极值标准差 / 区间高度 < 0.4

    # --- 基底回溯窗口（修「宽左肩漏触点」）---
    # 颈线只用「突破前基底」的分形来聚；基底起点 = 当前极点前 base_lookback 根。
    # 旧值写死 ext_i-15：左肩比头早超过 15 根的宽形态（如头肩底/大 W 底），
    # 左侧颈线触点会被截掉 → 簇触点不够 → 整条形态漏判。放宽到 60 根
    # （约 3 个月日线），足够覆盖绝大多数宽形态的左侧结构；同时不会引入
    # 旧 M 头误判——旧形态的颈线若没有近期向上突破，本就不会成为候选。
    base_lookback: int = 60

    # --- 突破有效性 ---
    break_body_ratio: float = 0.5   # 实体重心站上颈线（规格 A3）
    break_close_pct: float = 0.005  # 或收盘超出颈线 0.5% 以上
    vol_confirm_mult: float = 1.3   # 量先价行：突破日量 ≥ 1.3× 近 N 日均量
    vol_lookback: int = 20

    # --- 停损（修 P1-4：书说 2~7% 动态，不是固定 2%）---
    stop_atr_mult: float = 1.0      # 停损 = 颈线 -/+ 1×ATR
    stop_pct_min: float = 0.02
    stop_pct_max: float = 0.07


# ===================================================================
# 1. 基础量：ATR
# ===================================================================

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """真实波幅均值。用它让所有阈值自适应品种波动率——
    茅台一根 K 线动 20 元很正常，某个 3 元的票动 2 毛就是大事。"""
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=max(2, n // 3)).mean().bfill()


# ===================================================================
# 2. ZigZag 摆动极值
# ===================================================================

@dataclass
class Swing:
    i: int                  # 在 df 中的位置
    date: str
    price: float
    kind: Literal["H", "L"]

    def __repr__(self):
        return f"<{self.kind} {self.date} {self.price:.2f}>"


def find_swings(df: pd.DataFrame, p: ABParams, tail_guard: int = 0,
                i0: int = 0, i1: int | None = None) -> list[Swing]:
    """提取摆动高低点（标准 ZigZag）。

    算法主线（与旧版的关键区别）：
      反向极值**必须偏离上一个确认极值 ≥ 阈值**才算数，否则当噪声吞掉；
      同向极值只在「同一腿」内更新 last，绝不直接替换掉远方另一个合法极值。
      —— 旧版「同向更极端就替换」会把 W 底/头肩底里相隔几十根的左底直接吃掉，
         只剩头+右底（仅隔几根），导致 name_pattern 判「不独立」误报单底。

    分形判定：左右各 k 根都不超过它（局部极值）。窗口裁进 [i0, i1)，
    保证突破后的反弹高点不会把突破前的颈线触点「吸收」成非分形点；
    返回的 Swing.i 始终是**全量 df 坐标**，避免与突破/极点索引混用。
    """
    h, l = df["high"].values, df["low"].values
    a = atr(df).values
    n = len(df)
    k = p.fractal_k
    dates = df.index.strftime("%Y-%m-%d")
    lo = max(k, i0)
    hi = (n - k - tail_guard) if i1 is None else min(i1, n - k - tail_guard)
    wlo = i0
    whi = n if i1 is None else i1

    last = None   # (i, price, kind)
    out: list[Swing] = []
    for i in range(lo, hi):
        wi0 = max(i - k, wlo)
        wi1 = min(i + k + 1, whi)
        win_h = h[wi0:wi1]
        win_l = l[wi0:wi1]
        is_h = h[i] == win_h.max() and h[i] >= h[i - 1]
        is_l = l[i] == win_l.min() and l[i] <= l[i - 1]
        if not (is_h or is_l):
            continue
        if is_h and is_l:
            # 同时是高低点（极罕见）：取偏离 last 更大的方向
            if last is None:
                kind = "H"
            else:
                d_h = abs(h[i] - last[1]); d_l = abs(last[1] - l[i])
                kind = "H" if d_h >= d_l else "L"
        elif is_h:
            kind = "H"
        else:
            kind = "L"
        price = float(h[i]) if kind == "H" else float(l[i])

        if last is None:
            last = (i, price, kind)
            continue
        thr = max(a[i] * p.swing_atr_mult, price * p.swing_pct_floor)
        if kind == last[2]:
            # 同向：仅在同一腿内更新更极值（不影响远方另一个合法极值）
            more = (kind == "H" and price > last[1]) or \
                   (kind == "L" and price < last[1])
            if more:
                last = (i, price, kind)
        else:
            dev = abs(price - last[1])
            if dev >= thr:
                out.append(Swing(last[0], dates[last[0]], last[1], last[2]))
                last = (i, price, kind)
            else:
                # 偏离不足：当噪声。若比 last 更极端则更新 last（同腿延伸），否则忽略
                more = (kind == "H" and price > last[1]) or \
                       (kind == "L" and price < last[1])
                if more:
                    last = (i, price, kind)
    if last is not None:
        out.append(Swing(last[0], dates[last[0]], last[1], last[2]))
    return out


# ===================================================================
# 3. 价位聚类 —— 「点多为主」的算法化身
# ===================================================================

@dataclass
class Cluster:
    kind: Literal["H", "L"]
    price: float            # 簇代表价（触点中位数）
    touches: list           # [Swing]
    lo: float
    hi: float

    @property
    def n(self) -> int:
        return len(self.touches)

    @property
    def first_i(self) -> int:
        return min(t.i for t in self.touches)

    @property
    def last_i(self) -> int:
        return max(t.i for t in self.touches)

    @property
    def span(self) -> int:
        return self.last_i - self.first_i


def cluster_swings(swings: list[Swing], kind: str, tol: float) -> list[Cluster]:
    """把同方向、价位相近的摆动点归成一簇。tol 由 ATR 决定。"""
    pts = sorted([s for s in swings if s.kind == kind], key=lambda s: s.price)
    if not pts:
        return []
    groups, cur = [], [pts[0]]
    for s in pts[1:]:
        if s.price - cur[-1].price <= tol:
            cur.append(s)
        else:
            groups.append(cur)
            cur = [s]
    groups.append(cur)
    out = []
    for g in groups:
        ps = [t.price for t in g]
        out.append(Cluster(kind=kind, price=float(np.median(ps)),
                           touches=sorted(g, key=lambda t: t.i),
                           lo=float(min(ps)), hi=float(max(ps))))
    return out


def score_cluster(c: Cluster, n_bars: int, atr_v: float) -> float:
    """给簇打分，决定谁当颈线。

    权重取向（书里的"点多为主"只说了点数，其余是工程补充）：
      触点数最重要 —— 这是书的原话
      跨度次之     —— 3 天内碰 3 次不如 3 个月内碰 3 次有效
      紧密度再次   —— 触点越集中在同一价位，线越"实"
      近期性最后   —— 半年前的颈线参考价值低于上个月的
    """
    if c.n < 2:
        return 0.0
    touch = c.n * 3.0
    span = min(c.span / max(n_bars, 1), 1.0) * 2.0
    tight = (1.0 - min((c.hi - c.lo) / max(atr_v, 1e-9), 1.0)) * 1.5
    recent = (c.last_i / max(n_bars - 1, 1)) * 1.0
    return touch + span + tight + recent


# ===================================================================
# 4. 突破检测
# ===================================================================

@dataclass
class Breakout:
    i: int
    date: str
    close: float
    direction: Literal["up", "down"]
    body_ok: bool           # 实体重心站上/下颈线
    close_ok: bool          # 收盘超出阈值
    vol_ratio: float        # 突破日量 / 近 N 日均量
    vol_confirm: bool       # 量先价行
    pullback: dict | None = None   # 回踩确认


def detect_breakout(df: pd.DataFrame, neck: float, start_i: int,
                    direction: str, p: ABParams) -> Breakout | None:
    """从 start_i 之后找第一根有效突破 K 线。

    有效性两条（规格 A3）：实体重心站上颈线 **或** 收盘超出 0.5%。
    量能不作为有效性硬条件，只作为论据强弱 —— 书讲"量先价行"是加分项，
    不是没量就一定假突破。
    """
    o, c = df["open"].values, df["close"].values
    v = df["volume"].values
    n = len(df)
    vma = pd.Series(v).rolling(p.vol_lookback, min_periods=3).mean().values
    dates = df.index.strftime("%Y-%m-%d")

    for i in range(max(start_i + 1, 1), n):
        body_mid = (o[i] + c[i]) / 2.0
        if direction == "up":
            body_ok = body_mid > neck
            close_ok = c[i] > neck * (1 + p.break_close_pct)
        else:
            body_ok = body_mid < neck
            close_ok = c[i] < neck * (1 - p.break_close_pct)
        if not (body_ok or close_ok):
            continue
        ratio = float(v[i] / vma[i]) if vma[i] and vma[i] > 0 else 0.0
        return Breakout(i=i, date=dates[i], close=float(c[i]),
                        direction="up" if direction == "up" else "down",
                        body_ok=bool(body_ok), close_ok=bool(close_ok),
                        vol_ratio=round(ratio, 2),
                        vol_confirm=ratio >= p.vol_confirm_mult)
    return None


def find_pullback(df: pd.DataFrame, neck: float, bi: int, direction: str,
                  atr_v: float, max_bars: int = 25) -> dict | None:
    """突破后回踩颈线确认（颈线由压变撑 / 由撑变压）。"""
    seg = df.iloc[bi + 1: bi + 1 + max_bars]
    if seg.empty:
        return None
    if direction == "up":
        d = (seg["low"] - neck).abs()
        j = int(d.values.argmin())
        touched = seg["low"].iloc[j] <= neck + atr_v * 0.5
        held = seg["close"].iloc[j] >= neck
    else:
        d = (seg["high"] - neck).abs()
        j = int(d.values.argmin())
        touched = seg["high"].iloc[j] >= neck - atr_v * 0.5
        held = seg["close"].iloc[j] <= neck
    if not touched:
        return None
    row = seg.iloc[j]
    vseg = df["volume"].iloc[max(0, bi - 20):bi]
    return {
        "i": bi + 1 + j,
        "date": str(seg.index[j].date()),
        "price": float(row["low"] if direction == "up" else row["high"]),
        "held": bool(held),
        "shrink": bool(row["volume"] < vseg.mean()) if len(vseg) else None,
    }


# ===================================================================
# 5. 形态命名（修 P1-1：算法判定，禁人工套名）
# ===================================================================

def name_pattern(swings: list[Swing], neck: Cluster, extreme: Swing,
                 direction: str, df: pd.DataFrame) -> tuple[str, str]:
    """按底/顶的结构判形态名，返回 (形态名, 判定依据)。

    这里最容易犯的错，上次就犯了：茅台 06/26 低 1168、06/29 低 1151 是
    **连续两个交易日**，被我写成「W 底」。两个底之间必须隔着一次像样的反弹，
    否则那就是一个底，不是两个。
    """
    lows = [s for s in swings if s.kind == "L"]
    highs = [s for s in swings if s.kind == "H"]
    pool, opp = (lows, highs) if direction == "up" else (highs, lows)

    # 用「完整基底分形」判形态：base_sw 已限定在 [start_b : 突破bar) 内，
    # 所有触底/触顶都属于当前形态。绝不能按 neck.first_i 截断 —— 左底/左肩
    # 天然落在「首颈线触点」之前（W 底左底、头肩底左肩都是如此），一旦裁掉
    # 就只剩一个底，把双底/头肩底误判成单底反转。茅台的左肩恰好在首触点之后
    # 才侥幸正确，合成 W 底立刻暴露该 bug。
    seg = list(pool)
    if len(seg) < 1:
        return ("单底反转" if direction == "up" else "单顶反转"), "形态区内仅一个极值点"

    tol = float(atr(df).iloc[-1]) * 0.8
    if direction == "up":
        cand = sorted(seg, key=lambda s: s.price)[:3]
    else:
        cand = sorted(seg, key=lambda s: -s.price)[:3]
    cand = sorted(cand, key=lambda s: s.i)

    # 相邻极值必须隔着一次反向摆动，且间隔 ≥ 5 根，才算两个独立的底/顶
    def independent(a: Swing, b: Swing) -> bool:
        if b.i - a.i < 5:
            return False
        mid = [s for s in opp if a.i < s.i < b.i]
        if not mid:
            return False
        amp = abs(mid[0].price - (a.price + b.price) / 2)
        return amp >= tol

    if len(cand) >= 2 and independent(cand[0], cand[1]):
        p0, p1 = cand[0].price, cand[1].price
        if len(cand) >= 3 and independent(cand[1], cand[2]):
            mid_is_extreme = (p1 < min(p0, cand[2].price)) if direction == "up" \
                else (p1 > max(p0, cand[2].price))
            if mid_is_extreme:
                return ("头肩底" if direction == "up" else "头肩顶",
                        f"三个极值点 {cand[0].date}/{cand[1].date}/{cand[2].date}，中间点最极端（头）")
        near = abs(p0 - p1) <= tol
        nm = ("W 底" if direction == "up" else "M 头") if near else \
             ("双底（不等高）" if direction == "up" else "双顶（不等高）")
        return nm, (f"两个独立极值 {cand[0].date} {p0:.2f} / {cand[1].date} {p1:.2f}，"
                    f"间隔 {cand[1].i - cand[0].i} 根且中间有反向摆动")

    # 单底/单顶：区分"破前低后拉回"（破底翻）与普通单底
    prev = [s for s in pool if s.i < extreme.i]
    if prev:
        broke = (extreme.price < min(s.price for s in prev)) if direction == "up" \
            else (extreme.price > max(s.price for s in prev))
        if broke:
            return (("破底翻" if direction == "up" else "假突破/破顶翻"),
                    f"{extreme.date} 创出前低/前高之外的新极值 {extreme.price:.2f} 后反向，为单一极值点")
    return (("单底反转" if direction == "up" else "单顶反转"),
            f"形态区内仅 {extreme.date} 一个有效极值，相邻极值不满足独立性（间隔<5根或无反向摆动）")


# ===================================================================
# 5b. 候选生成（突破前基底聚颈线，破除「突破吸收颈线」）
# ===================================================================

def resample_tf(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """S12：把日线重采样成更大周期（'W' 周线 / 'ME' 月线）。

    刻意不额外向数据源请求周/月线：
      ① 少一次网络调用 = 少一个失败点与一致性风险（复权/停牌口径可能不一致）；
      ② 任何已落盘的日线夹具都能直接算大周期，测试可离线复现。
    """
    if df is None or len(df) == 0 or not isinstance(df.index, pd.DatetimeIndex):
        return pd.DataFrame()
    agg = {"open": "first", "high": "max",
           "low": "min", "close": "last", "volume": "sum"}
    try:
        o = df.resample(rule).agg(agg)
    except ValueError:
        # pandas <2.2 用 'M' 表示月末，2.2+ 改用 'ME'（旧写法告警/报错）
        alt = {"ME": "M", "M": "ME"}.get(rule)
        if not alt:
            raise
        o = df.resample(alt).agg(agg)
    return o.dropna(subset=["close"])


def tf_trend_of(df_tf: pd.DataFrame, ma_n: int = 10, slope_n: int = 4,
                min_bars: int = 20) -> tuple[str, float, float, int]:
    """S12：判定一个大周期的趋势。返回 (trend, ma_value, last_close, bars)。

    判据（两个条件都要满足才给方向，避免单一均线的假信号）：
      上升 = 收盘在 MA 之上 且 MA 近 slope_n 根向上
      下降 = 收盘在 MA 之下 且 MA 近 slope_n 根向下
      其余 = 震荡（无大方向背书）
    根数不足 min_bars 一律「数据不足」，不判、不降级——宁可不表态也不误导。
    """
    n = len(df_tf)
    if n < min_bars:
        return "数据不足", 0.0, (float(df_tf["close"].iloc[-1]) if n else 0.0), n
    ma = df_tf["close"].rolling(ma_n).mean()
    if pd.isna(ma.iloc[-1]) or pd.isna(ma.iloc[-1 - slope_n]):
        return "数据不足", 0.0, float(df_tf["close"].iloc[-1]), n
    ma_now = float(ma.iloc[-1])
    ma_prev = float(ma.iloc[-1 - slope_n])
    c_now = float(df_tf["close"].iloc[-1])
    up = c_now > ma_now and ma_now > ma_prev
    dn = c_now < ma_now and ma_now < ma_prev
    trend = "上升" if up else ("下降" if dn else "震荡")
    return trend, ma_now, c_now, n


def _recent_extreme_i(df: pd.DataFrame, direction: str, n: int) -> int:
    """当前演化形态的极点位置：后半段的最近底(up) / 最近顶(down)。
    只盯后半段，旧形态（窗口前半段的 M 头/W 底）自动出局。"""
    half = df.iloc[n // 2:]
    if direction == "up":
        return int(half["low"].values.argmin()) + n // 2
    return int(half["high"].values.argmax()) + n // 2


def _candidates_for(df: pd.DataFrame, p: ABParams, direction: str,
                    n: int, tol: float) -> list[tuple]:
    """生成 (neck: Cluster, bi: int, close_i: float) 候选。

    核心：颈线只用「突破前基底」的分形来聚——基底 = [形态起点 : 候选突破bar]，
    所以突破后那根放量长阳及其反弹高点被排除在外，颈线触点（如 7/16/7/17）
    才不会被「吸收」成非分形点。对每个候选突破 bar 都重提一次基底分形。

    每个颈线簇只取「首次上穿」那根作为突破点（bi 递增扫描，命中即标记，
    后续沿用此簇的 bar 不再重复生成，避免把"已站上多日"的末根当成突破）。
    """
    out: list[tuple] = []
    ext_i = _recent_extreme_i(df, direction, n)
    kind = "H" if direction == "up" else "L"
    start = max(0, ext_i - p.base_lookback)
    done: set[float] = set()        # 按颈线价位去重（同一颈线只取首次上穿）
    for bi in range(ext_i + 3, n):
        close_i = float(df["close"].iloc[bi])
        o = float(df["open"].iloc[bi])
        body_mid = (o + close_i) / 2.0
        # 基底 = [start : bi)，且用 i0/i1 限定扫描区间，保持全量 df 坐标
        base_sw = find_swings(df, p, i0=start, i1=bi)
        if len(base_sw) < 3:
            continue
        for c in cluster_swings(base_sw, kind, tol):
            if c.n < p.min_touch:
                continue
            key = round(c.price, 1)
            if key in done:
                continue
            ok = (body_mid > c.price or close_i > c.price * (1 + p.break_close_pct)) \
                if direction == "up" else \
                (body_mid < c.price or close_i < c.price * (1 - p.break_close_pct))
            if not ok:
                continue
            done.add(key)
            out.append((c, bi, close_i))
    return out


# ===================================================================
# 6. 主入口
# ===================================================================

@dataclass
class ABSignal:
    ok: bool
    reason: str = ""
    pattern: str = ""
    pattern_basis: str = ""
    direction: str = ""
    confidence: str = ""              # 高/中/低
    neckline: float = 0.0
    neck_touches: list = field(default_factory=list)   # [(date, price)]
    neck_start: str = ""              # 颈线起点日期（修 P1-2）
    neck_start_i: int = 0
    extreme: dict = field(default_factory=dict)        # 形态极点
    height: float = 0.0               # H = |极点 - 颈线|
    breakout: dict | None = None
    entry: float = 0.0
    stop: float = 0.0
    stop_pct: float = 0.0
    target1: float = 0.0
    target2: float = 0.0
    rr: float = 0.0                   # 风险报酬比（进场→目标1）
    last_close: float = 0.0
    atr: float = 0.0
    evidence: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    failure: dict | None = None          # S5：失败信号 dict（None=无失败）
    orig_direction: str = ""             # S5：翻转前的原方向
    failure_type: str = ""               # S5：假突破/假跌破(破底翻)/量价背离/异常量/逃命线
    broken: bool = False                 # S9-B 破位降级：现价大幅跌破颈线→形态失败
    broken_pct: float = 0.0              # S9-B 破位幅度（(颈线-现价)/颈线，方向感知）
    # S13 形态完成度：突破后是否曾兑现等幅目标。
    # 蔡森等幅满足是「形态走完」的判据：到了再回 = 获利回吐（完成后回撤）；
    # 没到就回 = 假突破失败。二者操作含义完全不同，不可一律判「形态失败」。
    completed: bool = False              # 突破后曾触及等幅目标①
    completed_at: str = ""               # 首次触及目标①的日期
    t2_reached: bool = False             # 突破后曾触及等幅目标②
    extreme_after: float = 0.0           # 突破后极值（up=最高 / down=最低）
    extreme_after_date: str = ""         # 突破后极值日期
    retrace_kind: str = ""               # "完成后回撤"/"未达标回撤"/""（仅破位时有值）
    # S10 颈线对齐：颈线不是一条 hairline，而是触点形成的阻力/支撑「带」。
    # 突破须脱离带远边(上沿/下沿)才算干净突破，仅过中位会被软封顶并提示。
    neck_band: tuple = (0.0, 0.0)       # S10 (lo, hi)：颈线带上下沿（触点极值的实际价位）
    neck_width: float = 0.0             # S10 颈线带宽度 = hi - lo
    clear_band: bool = True             # S10 突破收盘是否脱离颈线带远边（对齐可见阻力）
    # S11 套牢区检测：突破前历史密集成交区（解套卖压）检测
    trapped_zone: tuple | None = None   # S11 (zone_lo, zone_hi)：套牢区价格区间（None=无）
    trapped_at_t2: bool = False         # S11 等幅目标②落入套牢区
    trapped_near: bool = False          # S11 现价逼近套牢区外沿（追进风险报酬劣化）
    trapped_vol_pct: float = 0.0        # S11 套牢区成交量占突破前历史总量比重

    # S12 大周期定位：日线信号须与周线大方向校验（大周期定方向，小周期定进出场）
    tf_trend: str = "数据不足"          # S12 周线趋势："上升"/"下降"/"震荡"/"数据不足"
    tf_aligned: bool | None = None      # S12 日线方向与周线是否同向（None=无法判定）
    tf_ma: float = 0.0                  # S12 周线 MA10 值
    tf_close: float = 0.0               # S12 最近周线收盘
    tf_bars: int = 0                    # S12 可用周线根数
    tf_month_trend: str = "数据不足"    # S12 月线趋势（辅助，数据足够才给）

    def to_dict(self):
        return asdict(self)


def analyze(df: pd.DataFrame, p: ABParams | None = None) -> ABSignal:
    """A+B 全自动分析。输入只要 OHLCV，不需要任何人工指认。"""
    p = p or ABParams()
    if len(df) < 40:
        return ABSignal(ok=False, reason=f"仅 {len(df)} 根 K 线，不足以判定形态（需 ≥40）")

    a = atr(df)
    atr_v = float(a.iloc[-1])
    n = len(df)
    last_close = float(df["close"].iloc[-1])
    notes: list[str] = []

    swings = find_swings(df, p, tail_guard=3)
    if len(swings) < 3:
        return ABSignal(ok=False, reason=f"仅识别到 {len(swings)} 个摆动极值，"
                                         f"价格结构过于单调，无法画颈线")

    tol = atr_v * p.cluster_atr_mult
    best = None
    for direction in ("up", "down"):
        # 极值点（头/顶）位置：用于排除「肩顶/旧阻力」。
        # 颈线首触点须在头之前 0.5×base_lookback 内——超出即更早一波的旧阻力层
        # （茅台 1343 簇首触点 05-14 距头 31 根 > 阈值 30，是下跌途中反弹顶+右肩顶
        # 拼出的伪颈线，排除；1268 簇首触点 06-12 距头 10 根，夹着头部，是真颈线）。
        ext_i = _recent_extreme_i(df, direction, n)
        for c, bi, close_i in _candidates_for(df, p, direction, n, tol):
            # 用 detect_breakout 复用量能确认逻辑（从颈线末触点到候选突破 bar）
            bo = detect_breakout(df, c.price, c.last_i, direction, p) \
                if bi == c.last_i + 1 else None
            # detect_breakout 从 c.last_i+1 起扫，若 bi 恰是首个突破则匹配；否则自建
            if bo is None or bo.i != bi:
                o = float(df["open"].iloc[bi]); v = float(df["volume"].iloc[bi])
                vma = float(pd.Series(df["volume"].values).rolling(
                    p.vol_lookback, min_periods=3).mean().iloc[bi]) if bi > 0 else 0.0
                ratio = v / vma if vma > 0 else 0.0
                bo = type("BO", (), {
                    "i": bi, "date": df.index[bi].strftime("%Y-%m-%d"),
                    "close": close_i, "direction": direction,
                    "body_ok": (o + close_i) / 2 > c.price if direction == "up"
                               else (o + close_i) / 2 < c.price,
                    "close_ok": close_i > c.price * (1 + p.break_close_pct) if direction == "up"
                                else close_i < c.price * (1 - p.break_close_pct),
                    "vol_ratio": round(ratio, 2),
                    "vol_confirm": ratio >= p.vol_confirm_mult,
                    "pullback": None,
                })()

            sc = score_cluster(c, n, atr_v)
            # 形态极点（颈线区间内的反向极值），顺便算高度与目标（供显著性判定）
            # S13-A 修：搜索窗口须覆盖「完整基底」，不能只从颈线首触点 c.first_i 起。
            # W底/头肩底的第二谷（常为真实形态底）几乎总早于颈线首触点——
            # 旧窗口把它切在外面，改用更靠前的高点/低点当形态底，H 与目标位系统性偏小。
            # 实例 600460：旧窗口取 31.74，真实 W 底双谷在 24.62/25.44，
            # 目标①应为 ~53（实际到过 57.02），旧算法只给到 46.15。
            # 与 name_pattern 用同一 base 起点（ext_i - base_lookback），保持口径一致。
            base0 = max(0, ext_i - p.base_lookback)
            if direction == "up":
                seg = df.iloc[base0: bo.i + 1]
                ei = int(seg["low"].values.argmin()) + base0
                ep = float(df["low"].iloc[ei])
            else:
                seg = df.iloc[base0: bo.i + 1]
                ei = int(seg["high"].values.argmax()) + base0
                ep = float(df["high"].iloc[ei])
            height = abs(c.price - ep)
            t1 = c.price + height if direction == "up" else c.price - height
            ahead = (last_close < t1) if direction == "up" else (last_close > t1)

            # ---- 排除「肩顶/旧阻力」----
            # 颈线首触点距头超过 0.5×base_lookback = 更早一波的旧阻力层（伪颈线），排除。
            if (ext_i - c.first_i) > 0.5 * p.base_lookback:
                continue

            # ---- 优先级：近期性门槛 → 最高有效颈线(夹着头的教科书颈线) → 点多为主 → 幅度 ----
            # ① 近期性门槛：突破落在窗口后半段(>=50%)才计分，旧形态直接归零。
            # ② 贴头(最高有效颈线)：up 越高 / down 越低 越像真颈线——即夹着头的那道
            #    已破阻力（教科书颈线）；更高的「肩顶」已在上一步排除。
            # ③ 点多为主（书原话）：同水平触点越多越实，作次级决胜。④ 幅度仅次级。
            #    ahead 不进排序（它奖励「目标未达的高平台」反而把肩顶顶上来），
            #    只作为信号里的提示，见文末 notes。
            recent_gate = 2.5 if bo.i >= 0.5 * n else 0.0
            if direction == "up":
                level = c.price / last_close                # 越高(贴肩顶但已破)越优
            else:
                level = 1.0 - c.price / last_close           # 越低越优
            size = min(height / atr_v, 6.0) / 6.0
            touch = min(c.n, 4) / 4.0
            priority = (recent_gate * 10.0
                        + level * 20.0
                        + touch * 0.5
                        + size * 0.2
                        + (1.5 if bo.vol_confirm else 0.0))
            if best is None or priority > best[0]:
                best = (priority, sc, c, direction, bo, ei, ep, height, t1, ahead)

    if best is None:
        return ABSignal(ok=False,
                        reason="未找到「≥2 触点的水平颈线 + 其后的有效突破」组合。"
                               "可能是单边趋势中无整理区，或窗口太短。"
                               "→ 此时不应强行套用形态，无信号即无信号。")

    total, sc, neck, direction, bo, ei, ep, height, t1, ahead = best
    nk = neck.price

    # 形态极点已在选择循环内算好（ei/ep/height），这里直接复用
    extreme = Swing(ei, df.index[ei].strftime("%Y-%m-%d"), ep,
                    "L" if direction == "up" else "H")

    if height < atr_v * 1.2:
        notes.append(f"形态高度 {height:.2f} 不足 1.2×ATR（{atr_v:.2f}），"
                     f"幅度太小，等幅目标参考价值低")

    # 形态命名用「突破前基底」的分形（不带 tail_guard），避免突破临近末端时
    # 最近触点被裁掉导致误判为单底（修：name_pattern 此前吃全量 swings，
    # 末尾 3 根不参与分形，临近末端的颈线触点会被漏，把 W 底/头肩底误叫单底）。
    start_b = max(0, _recent_extreme_i(df, direction, n) - p.base_lookback)
    base_sw = find_swings(df, p, i0=start_b, i1=bo.i)
    pattern, basis = name_pattern(base_sw, neck, extreme, direction, df)

    # --- B 等幅满足 ---
    if direction == "up":
        t1, t2 = nk + height, nk + 2 * height
        raw_stop = nk - atr_v * p.stop_atr_mult
        stop = min(max(raw_stop, nk * (1 - p.stop_pct_max)), nk * (1 - p.stop_pct_min))
    else:
        t1, t2 = nk - height, nk - 2 * height
        raw_stop = nk + atr_v * p.stop_atr_mult
        stop = max(min(raw_stop, nk * (1 + p.stop_pct_max)), nk * (1 + p.stop_pct_min))
    stop_pct = abs(stop - nk) / nk

    # --- S13 形态完成度：突破后是否曾兑现等幅目标 ---
    # 蔡森等幅满足既是「目标」，也是「形态是否走完」的标尺：
    #   曾经触及目标① 再回落 = 形态已完成，回落是获利回吐/趋势反转；
    #   从未触及目标① 就回落 = 突破没被接受，是假突破失败。
    # 两者操作含义完全不同，此前一律写「形态可能失败」，属误导（600460 即例）。
    completed = False
    completed_at = ""
    t2_reached = False
    extreme_after = last_close
    extreme_after_date = df.index[-1].strftime("%Y-%m-%d")
    if bo is not None and 0 <= bo.i < n:
        post = df.iloc[bo.i:]
        if direction == "up":
            k = int(post["high"].values.argmax())
            extreme_after = float(post["high"].iloc[k])
            hit1 = post.index[post["high"] >= t1]
            hit2 = post.index[post["high"] >= t2]
        else:
            k = int(post["low"].values.argmin())
            extreme_after = float(post["low"].iloc[k])
            hit1 = post.index[post["low"] <= t1]
            hit2 = post.index[post["low"] <= t2]
        extreme_after_date = post.index[k].strftime("%Y-%m-%d")
        if len(hit1):
            completed = True
            completed_at = hit1[0].strftime("%Y-%m-%d")
        t2_reached = len(hit2) > 0

    # 真实进场 = 突破颈线那根收盘价（蔡森：突破当根进场，而非颈线价本身）。
    # 用颈线价当进场会低估真实风险、高估风报比，连带使 C4 仓位反推偏激进。
    entry = bo.close if bo else nk
    risk = abs(entry - stop)
    rr = abs(t1 - entry) / risk if risk > 1e-9 else 0.0

    # --- 回踩确认 ---
    bo.pullback = find_pullback(df, nk, bo.i, direction, atr_v)

    # --- 置信度：只由可数的证据决定，不拍脑袋 ---
    pts = 0
    pts += 1 if neck.n >= 3 else 0
    pts += 1 if bo.vol_confirm else 0
    pts += 1 if (bo.pullback and bo.pullback["held"]) else 0
    pts += 1 if height >= atr_v * 2 else 0
    pts += 1 if neck.span >= p.min_bars else 0
    confidence = "高" if pts >= 4 else ("中" if pts >= 2 else "低")

    # --- S9-A 量能封顶：蔡森「量先价行」，无量突破为假突破嫌疑 ---
    # 突破量未达近月均量 1.3× → 不得给「高」；实际缩量(<1.0×) → 封顶「低」。
    if not bo.vol_confirm:
        if confidence == "高":
            confidence = "中"
        notes.append(f"量能未确认（突破量 {bo.vol_ratio:.1f}× < {p.vol_confirm_mult:.1f}× 近月均量）："
                     f"蔡森『量先价行』，无量突破为假突破嫌疑，置信度已封顶，须放量确认方可加仓。")
    if bo.vol_ratio < 1.0:
        confidence = "低"
        notes.append(f"突破日量能比仅 {bo.vol_ratio:.1f}×（缩量），假突破嫌疑高，置信度降为「低」。")

    # --- S10 颈线对齐：颈线是一条「带」(触点 lo~hi)，不是 hairline ---
    # 突破收盘须脱离带远边(上沿/下沿)才算干净突破；仅过中位未脱离上沿，
    # 与图上可见颈线带对不齐，须软封顶并提示，避免「看似突破其实还在带内」。
    neck_band = (round(neck.lo, 4), round(neck.hi, 4))
    neck_width = round(neck.hi - neck.lo, 4)
    clear_band = True
    if bo is not None and bo.close is not None:
        clear_band = (bo.close > neck.hi) if direction == "up" else (bo.close < neck.lo)
        if not clear_band:
            if confidence == "高":
                confidence = "中"
            far_edge = "上沿" if direction == "up" else "下沿"
            notes.append(f"颈线带 {neck.lo:.2f}–{neck.hi:.2f}（宽 {neck_width:.2f}）："
                         f"突破收盘 {bo.close:.2f} 仅过颈线中位 {nk:.2f}，未脱离颈线带{far_edge}，"
                         f"有效性待确认，须放量站稳方可确认突破。")

    # --- S11 套牢区检测：目标②逼近前高套牢区 / 下方密集成交区 → 自动降级 ---
    # 蔡森「解套区」思想：底部起来的等幅目标②若落在前方密集成交（套牢盘堆积）区，
    # 上攻遇沉重解套卖压，目标②达成难度高；现价已逼近该区则追进风险报酬劣化。
    # 算法：突破前历史 K 线按价格分桶累加成交量，颈线同侧（上/下）显著高量桶邻域 = 套牢区。
    # 仅作「软降级」（高→中）+ 提示，不翻转方向、不给「低」（与破位降级的硬降级区分）。
    trapped_zone = None
    trapped_at_t2 = False
    trapped_near = False
    trapped_vol_pct = 0.0
    if bo is not None and bo.i and bo.i > 0:
        hist = df.iloc[: bo.i]                      # 突破前全部历史（排除突破放量污染）
        # 门槛 40 根：太短的历史谈不上「堆积」；不设 60 以免早突破样本漏检
        if len(hist) >= 40:
            hmin = float(hist["low"].min()); hmax = float(hist["high"].max())
            if hmax > hmin:
                nb = 40
                span = hmax - hmin
                vol_bin = np.zeros(nb)
                for _, r in hist.iterrows():
                    bi_ = int((r["close"] - hmin) / span * (nb - 1))
                    bi_ = min(max(bi_, 0), nb - 1)
                    vol_bin[bi_] += r["volume"]
                total_v = float(vol_bin.sum())
                # 只用「有量的桶」求中位数：空桶会把均值稀释到近零，
                # 那样任何横盘都能过阈值 → 全面误罚（S11 首版即栽在此）
                nz = vol_bin[vol_bin > 0]
                if direction == "up":
                    side = [i for i in range(nb)
                            if hmin + (i + 0.5) / nb * span > nk]
                else:
                    side = [i for i in range(nb)
                            if hmin + (i + 0.5) / nb * span < nk]
                if side and len(nz) >= 5 and total_v > 0:
                    med_v = float(np.median(nz))
                    top = max(side, key=lambda i: vol_bin[i])
                    # 判定①：峰值桶 ≥ 非空桶中位数 × 2.5（真·堆积，而非普通波动）
                    if med_v > 0 and vol_bin[top] >= med_v * 2.5:
                        # 自适应扩展：从峰值桶向两侧吸收「量 ≥ 中位数」的相邻桶，
                        # 最多 ±3 桶。密集区窄就窄，避免固定宽度在大价幅下虚胖吞掉目标②
                        z0 = z1 = top
                        for k in range(1, 4):
                            if top - k >= 0 and vol_bin[top - k] >= med_v:
                                z0 = top - k
                            else:
                                break
                        for k in range(1, 4):
                            if top + k <= nb - 1 and vol_bin[top + k] >= med_v:
                                z1 = top + k
                            else:
                                break
                        zone_v = float(vol_bin[z0: z1 + 1].sum())
                        zone_lo = hmin + z0 / nb * span
                        zone_hi = hmin + (z1 + 1) / nb * span
                        # 判定③：区间内「单根均量」须显著高于全历史均量。
                        # 只看桶总量会把「长时间缩量横盘」误判成套牢区——
                        # 停留久必然堆桶，但没人在那里放量接货，就没有解套盘。
                        # 蔡森讲的解套卖压来自成交量堆积，不是停留时间。
                        in_zone = hist[(hist["close"] >= zone_lo)
                                       & (hist["close"] <= zone_hi)]
                        all_bar_v = float(hist["volume"].mean())
                        dense = (len(in_zone) > 0 and all_bar_v > 0
                                 and float(in_zone["volume"].mean()) >= all_bar_v * 1.5)
                        # 判定②：该区间成交量占历史总量 ≥15%，才算「沉重」
                        if zone_v / total_v >= 0.15 and dense:
                            trapped_zone = (round(zone_lo, 4), round(zone_hi, 4))
                            trapped_vol_pct = round(zone_v / total_v, 4)
                            # t2 落入套牢区（up/down 同向比较，区间即压力/支撑堆积区）
                            trapped_at_t2 = (zone_lo <= t2 <= zone_hi)
                            # 现价紧贴套牢区（区内或外沿 3% 内）；已远离则不算「逼近」
                            trapped_near = (zone_lo * 0.97 <= last_close <= zone_hi * 1.03)
        if trapped_zone and (trapped_at_t2 or trapped_near):
            if confidence == "高":
                confidence = "中"
            zname = "前高套牢区" if direction == "up" else "下方密集成交区"
            ztxt = (f"{zname} {trapped_zone[0]:.2f}–{trapped_zone[1]:.2f}"
                    f"（占历史成交 {trapped_vol_pct * 100:.0f}%）")
            if trapped_at_t2:
                press = "解套卖压沉重" if direction == "up" else "承接买盘沉重"
                notes.append(f"【套牢区】等幅目标② {t2:.2f} 落入{ztxt}：{press}，"
                             f"目标②达成难度高，宜分段止盈、不宜盲目看满档。")
            if trapped_near:
                near_edge = "下沿" if direction == "up" else "上沿"
                verb = "上攻需放量化解解套盘" if direction == "up" else "下探需放量击穿承接盘"
                notes.append(f"【套牢区】现价 {last_close:.2f} 已逼近{ztxt}{near_edge}："
                             f"追进风险报酬劣化，{verb}。")

    # --- S12 大周期定位：日线信号必须与周线大方向校验 ---
    # 蔡森「大周期定方向，小周期定进出场」：逆着周线做的日线突破，
    # 多半只是反弹/回调，等幅目标②很难兑现 → 降一级 + 明确降低预期。
    # 只降一级（高→中→低），不翻方向、不否定信号：逆势也能做，但必须知道自己在做什么。
    tf_trend, tf_ma, tf_close, tf_bars = "数据不足", 0.0, 0.0, 0
    tf_month_trend = "数据不足"
    tf_aligned = None
    try:
        wk = resample_tf(df, "W")
        tf_trend, tf_ma, tf_close, tf_bars = tf_trend_of(wk)
        mo = resample_tf(df, "ME")
        tf_month_trend = tf_trend_of(mo, ma_n=6, slope_n=2, min_bars=12)[0]
    except Exception:
        pass
    _mtxt = f"，月线{tf_month_trend}" if tf_month_trend in ("上升", "下降", "震荡") else ""
    if tf_trend in ("上升", "下降"):
        tf_aligned = (tf_trend == ("上升" if direction == "up" else "下降"))
        if tf_aligned:
            notes.append(f"【大周期】周线{tf_trend}（周收 {tf_close:.2f} vs 周MA10 {tf_ma:.2f}"
                         f"，{tf_bars} 根{_mtxt}），与日线{'多' if direction == 'up' else '空'}方向同向："
                         f"顺势单，可按既定目标分段持有。")
        else:
            confidence = {"高": "中", "中": "低"}.get(confidence, confidence)
            _kind = "下跌中继的反弹" if direction == "up" else "上涨中继的回调"
            notes.append(f"【大周期】警讯 周线{tf_trend}（周收 {tf_close:.2f} vs 周MA10 {tf_ma:.2f}"
                         f"，{tf_bars} 根{_mtxt}），与日线{'多' if direction == 'up' else '空'}方向逆向："
                         f"本信号只能视为{_kind}，仓位减半、目标②不宜期待，见目标①即分批了结。")
    elif tf_trend == "震荡":
        notes.append(f"【大周期】周线震荡（周收 {tf_close:.2f} 缠绕周MA10 {tf_ma:.2f}"
                     f"，{tf_bars} 根{_mtxt}）：无大方向背书，按区间操作，"
                     f"颈线得失为唯一依据，不做趋势级加码。")
    else:
        notes.append(f"【大周期】周线样本仅 {tf_bars} 根（<20 根不判），大周期方向无法定位："
                     f"本信号缺大周期背书，仓位从严、只做短打。")

    # --- 反向提示（S5 会做完整失败识别，这里先给最基本的）---
    # S13-B：先问「形态走完没有」，再定性回落——
    # 走完了（曾达目标①）→ 回吐，不是假突破；没走完 → 假突破失败。
    if direction == "up" and last_close < nk:
        if completed:
            notes.append(f"提示 现价 {last_close:.2f} 已回到颈线 {nk:.2f} 之下，"
                         f"但形态已完成（{completed_at} 曾达目标① {t1:.2f}，"
                         f"突破后最高 {extreme_after:.2f}）：本次回落属完成后回吐，"
                         f"不是假突破；原多头单应已按纪律了结，不宜再按等幅目标追看")
        else:
            notes.append(f"警讯 现价 {last_close:.2f} 已回到颈线 {nk:.2f} 之下，"
                         f"且突破后最高仅 {extreme_after:.2f}、从未触及目标① {t1:.2f}"
                         f" → 假突破失败，形态不成立")
    if direction == "down" and last_close > nk:
        if completed:
            notes.append(f"提示 现价 {last_close:.2f} 已回到颈线 {nk:.2f} 之上，"
                         f"但形态已完成（{completed_at} 曾达目标① {t1:.2f}，"
                         f"突破后最低 {extreme_after:.2f}）：本次回升属完成后回补，"
                         f"不是假跌破；原空头单应已按纪律了结，不宜再按等幅目标追看")
        else:
            notes.append(f"警讯 现价 {last_close:.2f} 已回到颈线 {nk:.2f} 之上，"
                         f"且突破后最低仅 {extreme_after:.2f}、从未触及目标① {t1:.2f}"
                         f" → 假跌破失败，形态不成立")

    # --- S9-B 破位降级：现价大幅跌破颈线 → 形态失败，置信度封底、目标位失效 ---
    # 不翻转方向（翻转由 S5 假突破逻辑负责）；此处只做「软降级」：
    # 跌破幅度 ≥5% 或已低于停损，即判破位，目标位①/② 不再作为操作依据。
    broken = False
    broken_pct = 0.0
    retrace_kind = ""
    # S13-B 措辞分叉：先判「走完 vs 没走完」，再决定叫回撤还是失败。
    # 完成后回撤：形态已兑现，跌破颈线是回吐/反转，不该叫「形态失败」；
    # 未达标回撤：突破从未被接受，这才是假突破失败（旧版一律按后者表述，误导）。
    if direction == "up" and last_close < nk:
        broken_pct = (nk - last_close) / nk
        if last_close < stop or broken_pct >= 0.05:
            broken = True
            confidence = "低"
            if completed:
                retrace_kind = "完成后回撤"
                _t2 = f"，并触及目标② {t2:.2f}" if t2_reached else ""
                notes.append(f"【警讯】已破位，但属「完成后回撤」：等幅目标① {t1:.2f} 曾于 "
                             f"{completed_at} 兑现（突破后最高 {extreme_after:.2f}{_t2}），"
                             f"形态本身已走完；现价 {last_close:.2f} 跌破颈线 {nk:.2f} 约 "
                             f"{broken_pct * 100:.1f}%、并低于停损 {stop:.2f} → "
                             f"属获利回吐或趋势反转，不是假突破。"
                             f"原多头单纪律上早已了结，此处不宜再按目标①/② 操作，"
                             f"须等新结构（站回颈线 {nk:.2f}，或形成新的底/整理）再评估。")
            else:
                retrace_kind = "未达标回撤"
                notes.append(f"【警讯】形态失败（假突破）：突破后最高仅 {extreme_after:.2f}，"
                             f"从未触及等幅目标① {t1:.2f} 即回落；现价 {last_close:.2f} 跌破颈线 "
                             f"{nk:.2f} 约 {broken_pct * 100:.1f}%，且已低于停损 {stop:.2f} → "
                             f"原多头突破失效，目标位①/② 不再作为操作依据，"
                             f"按方法论应警惕翻空风险，纪律上离场/避险。")
    elif direction == "down" and last_close > nk:
        broken_pct = (last_close - nk) / nk
        if last_close > stop or broken_pct >= 0.05:
            broken = True
            confidence = "低"
            if completed:
                retrace_kind = "完成后回撤"
                _t2 = f"，并触及目标② {t2:.2f}" if t2_reached else ""
                notes.append(f"【警讯】已破位，但属「完成后回补」：等幅目标① {t1:.2f} 曾于 "
                             f"{completed_at} 兑现（突破后最低 {extreme_after:.2f}{_t2}），"
                             f"形态本身已走完；现价 {last_close:.2f} 站回颈线 {nk:.2f} 约 "
                             f"{broken_pct * 100:.1f}%、并高于停损 {stop:.2f} → "
                             f"属空头回补或趋势反转，不是假跌破。"
                             f"原空头单纪律上早已了结，此处不宜再按目标①/② 操作，"
                             f"须等新结构（跌回颈线 {nk:.2f}，或形成新的顶/整理）再评估。")
            else:
                retrace_kind = "未达标回撤"
                notes.append(f"【警讯】形态失败（假跌破）：突破后最低仅 {extreme_after:.2f}，"
                             f"从未触及等幅目标① {t1:.2f} 即回升；现价 {last_close:.2f} 站回颈线 "
                             f"{nk:.2f} 约 {broken_pct * 100:.1f}%，且已高于停损 {stop:.2f} → "
                             f"原空头跌破失效，目标位①/② 不再作为操作依据，"
                             f"按方法论应警惕翻多风险，纪律上离场/避险。")
    reached = (last_close >= t1) if direction == "up" else (last_close <= t1)
    if reached:
        notes.append(f"目标① {t1:.2f} 已达到（现价 {last_close:.2f}），"
                     f"后续为目标②区间，追进的风险报酬已劣化")
    if direction == "up" and last_close > entry:
        left = (t1 - last_close) / last_close
        back = (last_close - stop) / last_close
        if left < back:
            notes.append(f"现价距目标① 仅 {left * 100:+.1f}%，回到停损为 {-back * 100:.1f}%，"
                         f"此位置追进不划算")

    sig = ABSignal(
        ok=True, pattern=pattern, pattern_basis=basis, direction=direction,
        confidence=confidence,
        neckline=round(nk, 4),
        neck_touches=[(t.date, round(t.price, 4)) for t in neck.touches],
        neck_start=neck.touches[0].date, neck_start_i=neck.first_i,
        extreme={"date": extreme.date, "price": round(ep, 4), "i": ei},
        height=round(height, 4),
        breakout={"date": bo.date, "i": bo.i, "close": round(bo.close, 4),
                  "body_ok": bo.body_ok, "close_ok": bo.close_ok,
                  "vol_ratio": bo.vol_ratio, "vol_confirm": bo.vol_confirm,
                  "pullback": bo.pullback},
        entry=round(entry, 4), stop=round(stop, 4), stop_pct=round(stop_pct, 4),
        target1=round(t1, 4), target2=round(t2, 4), rr=round(rr, 2),
        last_close=round(last_close, 4), atr=round(atr_v, 4),
        broken=broken, broken_pct=round(broken_pct, 4),
        completed=completed, completed_at=completed_at, t2_reached=t2_reached,
        extreme_after=round(extreme_after, 4), extreme_after_date=extreme_after_date,
        retrace_kind=retrace_kind,
        neck_band=neck_band, neck_width=neck_width, clear_band=clear_band,
        trapped_zone=trapped_zone, trapped_at_t2=trapped_at_t2, trapped_near=trapped_near,
        trapped_vol_pct=trapped_vol_pct,
        tf_trend=tf_trend, tf_aligned=tf_aligned, tf_ma=round(tf_ma, 4),
        tf_close=round(tf_close, 4), tf_bars=tf_bars, tf_month_trend=tf_month_trend,
        evidence={
            "touch_count": neck.n,
            "touch_span_bars": neck.span,
            "cluster_width": round(neck.hi - neck.lo, 4),
            "volume_confirm": bo.vol_confirm,
            "vol_ratio": bo.vol_ratio,
            "pullback_held": bool(bo.pullback and bo.pullback["held"]),
            "score": round(total, 2),
            "swings_found": len(swings),
        },
        notes=notes,
    )

    # --- S5 失败识别（K 招）：补强书最薄弱处，避免只唱多 ---
    # 不在此 import 顶层（caisen_failure 延迟导入 caisen_ab，避免循环）。
    from caisen_failure import check_failure, build_reversal_signal
    fail = check_failure(df, sig, p)
    if fail and fail.direction:
        # 假突破/假跌破 → 翻转方向，重建反转信号（等幅目标/停损/置信度全重算）
        sig = build_reversal_signal(df, sig, fail, p)
    elif fail:
        # 量价背离/异常量/逃命线 → 不翻转，记证据 + 警讯
        sig.failure = asdict(fail)
        sig.failure_type = fail.type
        sig.notes.append(f"警讯 K招失败识别：{fail.type} —— {fail.reason}")
    return sig
