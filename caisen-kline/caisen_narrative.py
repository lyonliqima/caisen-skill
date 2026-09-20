#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔡森 K 线分析 · 文案自动生成层 (S3)
=====================================================
把 S2 的 ABSignal 变成**可直接出图/直接发**的文字，且**强制注入 C1–C4**。
设计铁律：
  - 所有数字都来自 ABSignal（计算结果驱动），零人工填参。
  - C1–C4 每段必带，不可跳过；C2 按市场分支（来自 caisen_data.Meta.short_mode）。
  - 不用 U+2212 减号（Hiragino 缺字），用 ASCII「-」。

依赖：ABSignal(caisen_ab) + Meta/AdjustBridge(caisen_data，可选)。
调用方可只传 sig + meta；如需图上标「复权价（盘面价）」则传 adjust 桥。
"""

from __future__ import annotations

from typing import Optional


# ===================================================================
# 0. 工具
# ===================================================================

def _px(p: float, adjust=None, nd: int = 2) -> str:
    """价格展示：有复权桥则同时给出盘面价，否则纯数字。"""
    if adjust is not None:
        return adjust.dual(p, nd)
    return f"{p:.{nd}f}"


def _nd_auto(ref: float) -> int:
    """按标的价格量级决定小数位。

    低价股（东软 8.54 元）若用 .0f 会把 8.06 显示成「8」、价差 0.40 显示成
    「亏 0」，结论直接失真；高价股（茅台 1400 元）则整数即可。
    以 last_close 等参考价定精度，跨市场自适应（含港股/期货小数报价）。
    """
    a = abs(float(ref))
    if a >= 1000:
        return 0
    if a >= 100:
        return 1
    if a >= 1:
        return 2
    if a >= 0.1:
        return 3
    return 4


def _amt(v: float, ref: float) -> str:
    """价差/形态高度等「金额型」数值，精度跟随标的价格量级。"""
    return f"{v:.{_nd_auto(ref)}f}"


def _dir_label(d: str) -> str:
    return "多头（看涨）" if d == "up" else "空头（看跌）"


def _cur_rr_line(sig, px, _amt) -> str:
    """S9-C 现价 R:R：按「现价进场」重算风报比，让用户看真实期望。

    - 现价 ≤ 停损（已破位/已止损）：风报比为负，纪律上应先离场，现价追进无意义。
    - 现价 ≥ 目标①：追进空间耗尽，风报比劣化。
    - 中间：算真实 (目标①-现价)/(现价-停损)。
    空头部对称处理。
    """
    lc, stp, t1 = sig.last_close, sig.stop, sig.target1
    up = sig.direction == "up"
    if up:
        if lc <= stp:
            return (f"· 现价 R:R（按现价进场）：现价 {px(lc)} 已 ≤ 停损 {px(stp)}，"
                    f"原结构已破，纪律上应先离场，现价追进风报比为负、无意义。\n")
        if lc >= t1:
            return (f"· 现价 R:R（按现价进场）：现价 {px(lc)} 已达/超过目标① {px(t1)}，"
                    f"追进空间耗尽，风报比劣化。\n")
        cur_r = (t1 - lc) / (lc - stp) if (lc - stp) > 1e-9 else 0.0
        return (f"· 现价 R:R（按现价进场）：{px(lc)} → 目标① {px(t1)} 赚 "
                f"{_amt(t1 - lc, lc)}；停损 {px(stp)} 亏 {_amt(lc - stp, lc)}；"
                f"R:R ≈ {cur_r:.1f} : 1。\n")
    else:
        if lc >= stp:
            return (f"· 现价 R:R（按现价进场）：现价 {px(lc)} 已 ≥ 停损 {px(stp)}，"
                    f"原结构已破，纪律上应先回补，现价追空风报比为负、无意义。\n")
        if lc <= t1:
            return (f"· 现价 R:R（按现价进场）：现价 {px(lc)} 已达/低于目标① {px(t1)}，"
                    f"追进空间耗尽，风报比劣化。\n")
        cur_r = (lc - t1) / (stp - lc) if (stp - lc) > 1e-9 else 0.0
        return (f"· 现价 R:R（按现价进场）：{px(lc)} → 目标① {px(t1)} 赚 "
                f"{_amt(lc - t1, lc)}；停损 {px(stp)} 亏 {_amt(stp - lc, lc)}；"
                f"R:R ≈ {cur_r:.1f} : 1。\n")


def _neck_touch_desc(sig) -> str:
    ts = sig.neck_touches[:3]
    if not ts:
        return "颈线取样点（详见下方关键价位）"
    nd = _nd_auto(getattr(sig, "last_close", None) or sig.neckline)
    return "、".join(f"{d} 高 {p:.{nd}f}" for d, p in ts)


# ===================================================================
# 1. C1–C4 强制约束（每次输出必带，C2 按市场分支）
# ===================================================================

def c1_text() -> str:
    return ("C1 幸存者偏差：目标①/② 为几何外推推算值，非保证到达。原书 60+ 案例"
            "全为成功案例，无回测、无胜率统计，实际到达率未知。")


def c2_text(sig, meta) -> str:
    """做空限制。空头形态按市场规则分支；多头形态也须提示后续转空的处理。

    健壮性（修 S3 漏洞）：meta 缺失 / short_mode 未知时，**默认从严（不可开空）**，
    绝不静默默认「可做空」——对散户工具这是安全底线。
    """
    sm = (getattr(meta, "short_mode", "") or "") if meta is not None else ""
    mk = getattr(meta, "market_label", "该标的") or "该标的"
    tl_raw = getattr(meta, "t_plus", 1)
    tl = f"T+{tl_raw}" if isinstance(tl_raw, int) else str(tl_raw)
    pl = getattr(meta, "price_limit", "涨跌停按市场规则")
    if sig.direction == "down":
        # 禁止开空类（A 股个股/北交/指数等）；未知市场一律从严
        if (not sm) or ("禁止" in sm) or ("只作" in sm) or ("不可交易" in sm):
            return (f"C2 做空限制：本信号为空头形态。【{mk}】{sm or '市场规则未识别'}"
                    f"（{tl}、涨跌停 {pl}）→ 只能减仓 / 离场 / 避险，不可开空单。")
        # 可做空类（期货/外汇/可融券ETF/美股/港股）
        return (f"C2 做空限制：本信号为空头形态。【{mk}】{sm}"
                f"→ 可做空，但须独立确认券源/机制，并注意杠杆与保证金风险。")
    # 多头信号：不触发做空，但给出后续转空的处置提示（仍属 C2 约束）
    return (f"C2 做空限制：当前为多头信号，不触发做空限制。若后续转空头形态，"
            f"按【{mk}】规则处理（{sm or '该市场规则'}）。")


def c3_text() -> str:
    return ("C3 交叉校验：目标② 若逼近前高套牢区或严重背离基本面（负价、跌破合理估值），"
            "纯量价支撑不足，须以业绩、估值等基本面交叉验证后方可采信。")


def c4_text(sig, meta) -> str:
    """仓位与频率：反推仓位 + 确认单/试错单标注 + 频率纪律 + 来源声明。"""
    bc = sig.breakout or {}
    is_confirmed = (sig.confidence == "高") and bool(bc.get("vol_confirm"))
    kind = "确认单" if is_confirmed else "试错单"
    tl_raw = getattr(meta, "t_plus", 1)
    tl = f"T+{tl_raw}" if isinstance(tl_raw, int) else str(tl_raw)
    # 真实成交亏损幅度（相对进场价），用于反推仓位；结构停损位（相对颈线）仅作标注
    risk_pct = abs(sig.stop - sig.entry) / sig.entry * 100 if sig.entry else sig.stop_pct * 100
    return (f"C4 仓位与频率：按「单笔亏损 ≤ 总资金 1–2%」反推仓位"
            f"（成交亏损约 {risk_pct:.1f}%、颈线下方结构止损 {sig.stop_pct * 100:.1f}%、{tl}）；"
            f"本单属【{kind}】（置信 {sig.confidence}）；同类信号一年数量有限，勿反复追单。")


def c1c4_block(sig, meta) -> str:
    """右侧第五块：C1–C4 整段（程序强制，不可跳过）。"""
    return "\n".join([
        c1_text(),
        c2_text(sig, meta),
        c3_text(),
        c4_text(sig, meta),
    ])


# ===================================================================
# 2. 文字副图（左右两栏）
# ===================================================================

def _cjk_width(s: str) -> float:
    """估算字符串显示宽度（中文/全角=1，半角字母数字≈0.55，标点≈0.3）。"""
    w = 0.0
    for ch in s:
        o = ord(ch)
        if o < 0x20 or (0x2000 <= o < 0x206F):
            w += 0.3
        elif (0x3000 <= o <= 0x303F) or (0xFF00 <= o <= 0xFFEF) or (0x4E00 <= o <= 0x9FFF):
            w += 1.0
        elif ch in '－–—':
            w += 1.0
        else:
            w += 0.55
    return w


def _wrap_block(text: str, width: float = 32.0) -> str:
    """按显示宽度给文字副图换行（matplotlib 不自动折行，长行会越界/互压）。
    续行沿用行首缩进，保持层级。
    """
    out = []
    for raw in text.split('\n'):
        stripped = raw.lstrip(' ')
        indent = raw[:len(raw) - len(stripped)]
        if _cjk_width(stripped) <= width:
            out.append(raw)
            continue
        cur, cur_w = '', 0.0
        for ch in stripped:
            cw = _cjk_width(ch)
            if cur_w + cw > width and cur:
                out.append(indent + cur)
                cur, cur_w = ch, cw
            else:
                cur += ch
                cur_w += cw
        if cur:
            out.append(indent + cur)
    return '\n'.join(out)


def _tf_line(sig) -> str:
    """S12 大周期定位在「结构判定」里的一行摘要（方向感知、不含歧义措辞）。"""
    t = getattr(sig, "tf_trend", "数据不足")
    al = getattr(sig, "tf_aligned", None)
    bars = getattr(sig, "tf_bars", 0)
    mo = getattr(sig, "tf_month_trend", "数据不足")
    mtxt = f"；月线 {mo}" if mo in ("上升", "下降", "震荡") else ""
    if t in ("上升", "下降"):
        tag = "顺势（同向）" if al else "警讯·逆势（反向，仅当反弹/回调操作）"
        return (f"周线 {t}（周收 {getattr(sig, 'tf_close', 0):.2f} / 周MA10 "
                f"{getattr(sig, 'tf_ma', 0):.2f}，{bars} 根）{mtxt} → 日线信号{tag}")
    if t == "震荡":
        return (f"周线 震荡（周收 {getattr(sig, 'tf_close', 0):.2f} 缠绕周MA10 "
                f"{getattr(sig, 'tf_ma', 0):.2f}，{bars} 根）{mtxt} → 无大方向背书，区间操作")
    return f"周线样本 {bars} 根（<20 不判）→ 大周期无法定位，仓位从严"


def build_text_blocks(sig, meta, df=None, adjust=None) -> tuple[str, str]:
    """返回 (text_left, text_right)，直接喂给 caisen_chart.render。

    左栏：一结构判定 / 二关键价位 / 三风险报酬
    右栏：四量价论据 / 五 C1–C4
    """
    px = lambda p: _px(p, adjust)
    dlabel = _dir_label(sig.direction)
    # S9-B 破位降级：方向标注带破位后缀，避免用户照多头目标位操作。
    # S13-B 分叉：形态走完过（曾达目标①）再破位 = 完成后回撤，不叫「形态失败」；
    # 从未达标就破位 = 假突破失败。两者对用户的含义不同，措辞必须分开。
    if getattr(sig, "broken", False):
        if getattr(sig, "completed", False):
            dlabel = f"{dlabel}（警讯·已破位·完成后回撤，形态已兑现）"
        else:
            dlabel = f"{dlabel}（警讯·已破位·形态失败）"

    # ---- 突破量能（需 df 取绝对量；否则退化为比率） ----
    bo = sig.breakout or {}
    vol_line = ""
    if df is not None and bo:
        try:
            bi = int(bo["i"])
            vol = float(df["volume"].iloc[bi])
            vmax = float(df["volume"].max())
            unit = getattr(meta, "vol_unit", "手") or "手"
            is_max = abs(vol - vmax) < 1e-6
            vol_line = (f"· 突破日 {bo['date']} 成交量 {vol:.0f}{unit}，"
                        f"为区间{'最大量' if is_max else '放量'}，量先价行 → "
                        f"{'突破有效性成立（非缩量假突破）。' if bo.get('vol_confirm') else '量能未明显放大，有效性待确认。'}\n")
        except Exception:
            vol_line = ""
    if not vol_line:
        vr = bo.get("vol_ratio", 0.0) if bo else 0.0
        vol_line = (f"· 突破日 {bo.get('date','')} 量能比 {vr:.1f}×"
                    f"（{'量先价行' if (bo or {}).get('vol_confirm') else '量能不足'}）。\n")

    # ---- 颈线触点描述 + 回踩 ----
    touch_desc = _neck_touch_desc(sig)
    pb = bo.get("pullback") if bo else None
    pull_line = ""
    if pb:
        held = pb.get("held")
        pull_line = (f"· 回踩 {pb.get('date','')} 于 {_px(pb.get('price', 0), adjust)} 缩量止跌，"
                     f"{'未破颈线 → 健康换手，突破确认。' if held else '一度跌破颈线，需警惕。'}\n")

    # ---- 三、风险报酬里的动态提示（复用 sig.notes） ----
    # S9/S10/S11/S12 扩展：关键警讯必须进图，否则修正形同虚设。
    # 按重要性排序并限 5 条：避免风险报酬栏被次要提示撑爆，导致真正该出现的看不见。
    # 注意：「大周期（S12）」已在【一、结构判定】块里完整呈现，不再重复塞进 H 栏，
    # 避免风险报酬栏被次要背景信息撑爆，导致「已破位」「套牢区」等紧急警讯被截掉。
    def _risk_priority(n):
        if "已破位" in n or "警讯·形态失败" in n:
            return 0
        if "套牢区" in n:
            return 1
        if "量能未确认" in n or "假突破嫌疑" in n:
            return 2
        if "颈线带" in n or "未脱离颈线带" in n:
            return 3
        if "回到颈线" in n:
            return 4
        if "目标①" in n and "达到" in n:
            return 5
        return 9
    # H 栏只放「必须立刻知道」的操作警讯；建议性/解释性内容由 _cur_rr_line 与结构判定承担。
    # 当警讯较多时，逐条换行会撑爆副图 → 合并为单行摘要，优先级低的以「…」提示去报告看。
    has_broken = any("已破位" in n for n in sig.notes)
    risk_notes = sorted(
        [n for n in sig.notes
         if (("目标①" in n and "达到" in n)
             or ("回到颈线" in n and not has_broken)   # 已破位时该提示冗余，去重
             or ("已破位" in n) or ("量能未确认" in n)
             or ("缩量" in n) or ("假突破嫌疑" in n) or ("已破位·失效" in n)
             or ("颈线带" in n) or ("未脱离颈线带" in n)
             or ("套牢区" in n))],
        key=_risk_priority,
    )
    if risk_notes:
        # 保留最多 2 条完整提示；更多时合并成一条摘要，避免爆栏
        if len(risk_notes) <= 2:
            risk_extra = "\n".join("· " + n for n in risk_notes)
        else:
            keywords = []
            for n in risk_notes[:4]:
                if "已破位" in n:
                    keywords.append("已破位")
                elif "套牢区" in n:
                    keywords.append("套牢区")
                elif "量能未确认" in n or "假突破嫌疑" in n:
                    keywords.append("量能封顶")
                elif "颈线带" in n or "未脱离颈线带" in n:
                    keywords.append("颈线带软")
                elif "回到颈线" in n:
                    keywords.append("回踩颈线")
                elif "目标①" in n and "达到" in n:
                    keywords.append("目标①到")
            risk_extra = "· 【警讯】" + " / ".join(keywords)
            if len(risk_notes) > 4:
                risk_extra += " …（其余详见文字报告）"
    else:
        risk_extra = ""

    # ====== 左栏 ======
    left = (
        "【一、结构判定】蔡森 A 招（颈线识别）+ B 招（等幅满足）\n"
        f"· 形态：{sig.pattern}。{sig.pattern_basis}\n"
        f"· 颈线（A 招）＝ {px(sig.neckline)}：由 {touch_desc} 连成的水平密集带。"
        "作用＝多空分界 + 进场基准 + 停损基准。\n"
        f"· 形态高度 H ＝ 颈线 {px(sig.neckline)} 减 形态底 {px(sig.extreme['price'])} "
        f"＝ {_amt(sig.height, sig.last_close)} 元。\n"
        f"· 等幅满足（B 招）：目标① ＝ 颈线＋H ＝ {px(sig.target1)}（一波满足）；"
        f"目标② ＝ 颈线＋2H ＝ {px(sig.target2)}（两波满足）。\n"
        f"· 方向：{dlabel}；突破日 {bo.get('date','')}；量能确认："
        f"{'是' if (bo or {}).get('vol_confirm') else '否'}；置信度：{sig.confidence}。\n"
        f"· 大周期（S12）：{_tf_line(sig)}\n"
        "\n"
        "【二、关键价位一览】\n"
        f"  颈线（进场基准）＝ {px(sig.neckline)}\n"
        f"  形态底（量高度）＝ {px(sig.extreme['price'])}　·　停损（{sig.stop_pct*100:.1f}%）＝ {px(sig.stop)}\n"
        f"  现价（收）＝ {px(sig.last_close)}\n"
        f"  目标①（1H）＝ {px(sig.target1)}　·　目标②（2H）＝ {px(sig.target2)}\n"
        "\n"
        "【三、风险报酬（H 模块）】\n"
        f"· 进场 {px(sig.entry)} → 目标① {px(sig.target1)} 赚 "
        f"{_amt(abs(sig.target1 - sig.entry), sig.last_close)}；"
        f"停损 {px(sig.stop)} 亏 {_amt(abs(sig.entry - sig.stop), sig.last_close)}；"
        f"R:R ≈ {sig.rr:.1f} : 1。\n"
        # S9-C 现价 R:R 并列：让用户看「现在买」的真实风报比，而非只给历史突破价 R:R
        + _cur_rr_line(sig, px, _amt)
    )
    if risk_extra:
        left += risk_extra + "\n"

    # --- 失败识别（K 招）段落 ---
    ft = getattr(sig, "failure_type", "") or ""
    fail = getattr(sig, "failure", None) or {}
    if ft:
        left += (
            "\n"
            "【失败识别（K 招）】\n"
            f"· 识别结果：{ft}（{'方向已翻转' if getattr(sig, 'orig_direction', '') else '警讯，方向未变'}）。\n"
            f"· 说明：{fail.get('reason', '')}\n"
        )

    # ====== 右栏 ======
    right = (
        "【四、论据·量价结构（G 招）】\n"
        + vol_line
        + pull_line
        + f"· 颈线 {len(sig.neck_touches)} 个触点：{touch_desc} → 点多为主，颈线可信。\n"
    )
    ft = getattr(sig, "failure_type", "") or ""
    fail = getattr(sig, "failure", None) or {}
    if ft:
        right += f"· K招失败识别：{ft} —— {fail.get('reason', '')}\n"
    right += (
        "\n"
        "【五、强制约束 C1–C4（每次输出必带）】\n"
        + c1c4_block(sig, meta)
    )
    # 文字副图不自动换行 → 按中文宽度折行，避免越界/互压（实测反馈）
    return _wrap_block(left), _wrap_block(right)


# ===================================================================
# 3. 水平价位线 + K线关键点（驱动出图，替代 run_600519 硬编码）
# ===================================================================

def build_levels(sig, meta=None, adjust=None) -> list[dict]:
    px = lambda p: _px(p, adjust)
    c_red, c_blue, c_orange, c_green, c_purple = "#c62828", "#1565c0", "#ef6c00", "#2e7d32", "#8e24aa"
    up = sig.direction == "up"
    broken = getattr(sig, "broken", False)
    # S9-B 破位降级：已破位的目标位/颈线/停损全部置灰并标注失效，不再误导按多头操作
    tgt_c = "#9e9e9e" if broken else c_red
    # S10 颈线带：中线+带区视觉对齐；破位时带区同步置灰
    band_c = "#9e9e9e" if broken else c_blue
    # S13-B：已兑现的目标位不该写「失效」（它确实到过），应写「已兑现」，
    # 否则用户看到 53.27 被标失效会以为算法没跑出来，反而误导。
    _done = getattr(sig, "completed", False)
    if broken:
        tgt_suffix = "（已兑现，形态完成后回撤，非操作依据）" if _done else \
            "（警讯·已破位·失效，非操作依据）"
    else:
        tgt_suffix = "（B招·两波等幅满足；C1：几何外推，非保证）"
    if broken:
        tgt1_suffix = "（目标①已兑现，形态已走完）" if _done else \
            "（警讯·已破位·失效，非操作依据）"
    else:
        tgt1_suffix = "（B招·一波等幅满足，第一停利参考）"
    neck_suffix = "（警讯·已破位·结构转弱，原突破失效）" if broken else \
        "（站上=进场基准；跌破=结构转弱）"
    stop_suffix = "（警讯·现价已跌破，形态完成后回撤）" if (broken and _done) else \
        ("（警讯·现价已跌破，原结构失败）" if broken
         else f"（破位无条件离场；风报比≈{sig.rr:.1f}:1）")
    # S11 套牢区：只有真正触发（目标②落入 或 现价逼近）才画带区，
    # 否则算出 zone 也不画——避免图上凭空多一条无意义的橙带
    _tz = getattr(sig, "trapped_zone", None)
    _t_hit = bool(_tz) and (getattr(sig, "trapped_at_t2", False)
                            or getattr(sig, "trapped_near", False))
    trap_band = _tz if _t_hit else None
    if getattr(sig, "trapped_at_t2", False) and not broken:
        tgt_suffix += f"\n（警讯·落入套牢区 {_tz[0]:.2f}–{_tz[1]:.2f}，卖压沉重·宜分段止盈）"
    # 现价相对颈线的方位 + 距目标①的剩余空间（方向感知，避免空头写成「站上」）
    if up:
        pos = f"已站上颈线 +{(sig.last_close / sig.neckline - 1) * 100:.1f}%"
        gap = f"距目标① 还差 {(sig.target1 / sig.last_close - 1) * 100:.1f}%"
    else:
        pos = f"已跌破颈线 {(sig.last_close / sig.neckline - 1) * 100:.1f}%"
        gap = f"距目标① 还差 {(sig.last_close / sig.target1 - 1) * 100:.1f}%"
    return [
        dict(y=sig.target2, c=tgt_c, ls=':', lw=1.4,
             txt=f'目标位② {px(sig.target2)}  ← 颈线 + 2倍形态高度\n{tgt_suffix}',
             band=trap_band,          # S11 套牢区：触发才画橙色压力带
             band_c="#9e9e9e" if broken else "#ef6c00"),
        dict(y=sig.target1, c=tgt_c, ls=':', lw=1.6,
             txt=f'目标位① {px(sig.target1)}  ← 颈线 + 1倍形态高度\n{tgt1_suffix}'),
        dict(y=sig.last_close, c=c_purple, ls='-', lw=1.4,
             txt=f'现价 {px(sig.last_close)}  ← 收盘\n（{pos}，{gap}）'),
        dict(y=sig.neckline, c=band_c, ls='--', lw=2.0,
             txt=f'颈线 {px(sig.neckline)}  ← A招核心线：多空分界\n{neck_suffix}',
             x0=getattr(sig, "neck_start_i", 0),   # S4：颈线从首触点画起（P1-2）
             band=getattr(sig, "neck_band", None)),  # S10 颈线带：中线+带区视觉对齐
        dict(y=sig.stop, c=c_orange, ls='-.', lw=1.5,
             txt=f'停损 {px(sig.stop)}  ← 颈线{sig.stop_pct*100:.1f}%\n{stop_suffix}'),
        dict(y=sig.extreme["price"], c=c_green, ls='--', lw=1.6,
             txt=f'{("形态底" if up else "形态顶")} {px(sig.extreme["price"])}  ← {sig.extreme["date"]} '
                 f'{"最低" if up else "最高"}\n（形态高度 H = |颈线减极| = '
                 f'{_amt(sig.height, sig.last_close)}）'),
    ]


def build_events(sig, df, meta=None, adjust=None) -> list[dict]:
    """主图 K 线关键点标注（2026-08-04 最终规则）。

    唯一硬约束：
      1. 标注框（文字 / 四象图）相互**绝不重叠**。
      2. 标注框只落在 K 线图「上方 / 右侧 / 下方」空白区，**不遮挡 K 线**。
      3. 箭头线**允许穿过 K 线内部**（可斜穿 / 弯曲 / 打折），不算违规。

    布局：四个角分布在空白边缘（左上 / 右上 / 左下 / 右下），
    水平方向两两错开、垂直方向在 K 线上 / 下方；框互不重叠，
    箭头自由斜指目标 K 线（可穿过 K 线，符合既有版式规则）。

    警讯 2026-08-04 定为最终定稿：后续 S5–S8 及正式 skill 一律遵守，
    不得回退（箭头可穿 K 线、框不重叠不遮挡）。任何改动须先跑
    verify_events_layout.py 确认「要点框重叠=0 / 压K线=0 / 价位标签重叠=0」。
    """
    if df is None:
        return []
    from caisen_chart import idx_of
    px = lambda p: _px(p, adjust)
    kh = float(df["high"].max()); kl = float(df["low"].min()); kr = kh - kl
    n = len(df)
    # 四角空白位置（data 坐标）：上带明显高于最高价、下带明显低于最低价，
    # 左右用 K 线索引比例错开 → 框天然互不重叠，也不压 K 线。
    # 偏移取 0.13 倍 K 线高（配合主图 0.20 倍留白 + 小字号），框边不探进 K 线带。
    y_top = kh + 0.13 * kr
    y_bot = kl - 0.13 * kr
    xL = max(3, int(n * 0.08))     # 左角 x
    xR = int(n * 0.58)             # 右角 x（与左角水平错开，避免互压）
    bo = sig.breakout or {}
    up = sig.direction == "up"
    ft = getattr(sig, "failure_type", "") or ""      # S5 失败类型
    fail = getattr(sig, "failure", None) or {}       # S5 失败信号 dict
    events = []

    # ① 突破 / 跌破：右上角空白（箭头可斜穿 K 线指向突破根）
    if bo and bo.get("i") is not None:
        bi = int(bo["i"])
        if ft in ("假突破", "假跌破/破底翻"):
            # 失败信号：① 框改为失败描述，箭头斜指失败确认根（trigger_i）
            ti = int(fail.get("trigger_i", bi))
            ti_price = float(df["low"].iloc[ti] if sig.direction == "down"
                             else df["high"].iloc[ti])
            verb = "警讯 假突破：原突破失效→翻空" if sig.direction == "down" \
                else "警讯 假跌破/破底翻：原跌破失效→翻多"
            events.append(dict(
                xy=(ti, ti_price),
                xytext=(xR, y_top), rad=0.18, fs=8.5,
                fc='#ffebee', ec='#c62828',
                txt=f'① {verb}\n{fail.get("trigger_date", "")} 确认 · 原 {bo["date"]}'))
        else:
            verb = "带量突破颈线" if up else "带量跌破颈线"
            concl = "有效突破（G招）" if up else "有效跌破（G招）"
            warn = f"\n警讯：{ft}" if ft else ""
            # S9-B 破位降级：已破位则主标注改为「突破已失效」，不再标「有效突破」误导。
            # S13-B：曾达目标① 的是「完成后回撤」，形态本已兑现，不能写成突破失效。
            if getattr(sig, "broken", False):
                if getattr(sig, "completed", False):
                    verb = "形态已兑现"
                    concl = (f"完成后回撤（{getattr(sig, 'completed_at', '')} 达目标①，"
                             f"现价跌破颈线 {sig.broken_pct * 100:.1f}%）")
                else:
                    verb = "警讯 突破已失效"
                    concl = f"形态破位（现价跌破颈线 {sig.broken_pct * 100:.1f}%）"
                warn = ""
            events.append(dict(
                xy=(bi, float(df["high"].iloc[bi] if up else df["low"].iloc[bi])),
                xytext=(xR, y_top), rad=0.18, fs=8.5,
                fc='#ffebee' if getattr(sig, "broken", False) else '#fff8e1',
                ec='#c62828',
                txt=f'① {bo["date"]} {verb}\n{concl}{warn}'))

    # ④ 回踩 / 反抽：左上角空白（如有）
    pb = bo.get("pullback") if bo else None
    if pb:
        pi = int(pb["i"])
        v4, c4 = ("缩量回踩颈线", "未破 → 突破确认") if up \
            else ("缩量反抽颈线", "未站回 → 跌破延续")
        events.append(dict(
            xy=(pi, float(pb["price"])),
            xytext=(xL, y_top), rad=0.18, fs=8.5,
            fc='#f3e5f5', ec='#6a1b9a',
            txt=f'④ {pb.get("date", "")} {v4}\n{c4}'))

    # ② 形态底 / 形态顶：左下角空白
    ei = int(sig.extreme["i"])
    events.append(dict(
        xy=(ei, sig.extreme["price"]),
            xytext=(xL, y_bot), rad=0.18, fs=8.5,
            fc='#e8f5e9', ec='#2e7d32',
        txt=f'② {sig.extreme["date"]} {"形态底" if up else "形态顶"} {px(sig.extreme["price"])}\n{sig.pattern}'))

    # ③ 颈线取样点：右下角空白
    if sig.neck_touches:
        t0 = sig.neck_touches[0]
        try:
            xi = idx_of(df, t0[0]) if isinstance(t0[0], str) else int(t0[0])
        except Exception:
            xi = 0
        events.append(dict(
            xy=(xi, sig.neckline),
            xytext=(xR, y_bot), rad=0.18, fs=8.5,
            fc='#e3f2fd', ec='#1565c0',
            txt=f'③ 颈线取样点 ×{len(sig.neck_touches)}\n点多为主 → 颈线可信'))
    return events


# ===================================================================
# 4. 一站式出图（run_600519 改用此函数即可零人工填参）
# ===================================================================

def render_signal(sig, df, meta, out, adjust=None, dpi=250, **kw):
    """由 ABSignal + df + meta 直接出图。等价于原 run_600519 全部硬编码，但全自动。

    健壮性（修 S3 漏洞）：sig.ok=False 时不崩、不编造数字，出一张「无形态」说明图。
    """
    from caisen_chart import render
    title = kw.pop("title", meta.title() if hasattr(meta, "title") else "蔡森 A+B 分析")
    footer = meta.footer() if hasattr(meta, "footer") else kw.pop("footer", None)
    vlabel = f'成交量（{getattr(meta, "vol_unit", "手")}）' if meta else "成交量"
    ylabel = kw.pop("ylabel", "价格")

    if not sig.ok:
        # 失败信号：明确告知「无形态」，宁可观望，不强行套用。
        left = (
            "【一、结构判定】蔡森 A 招（颈线识别）+ B 招（等幅满足）\n"
            f"· 未识别到可交易形态。\n· 原因：{getattr(sig, 'reason', '无有效形态')}\n"
            "· 按方法论纪律：无信号即无信号，不强行套用形态，宁可观望。\n"
        )
        try:
            import caisen_trend as _ct
            _tr = _ct.compute(df)
            left = (left.rstrip("\n") + "\n\n"
                    + _ct.summary_text(df, _tr, meta=meta,
                                       px=lambda v: _px(v, adjust)).rstrip("\n") + "\n")
        except Exception:
            pass
        right = (
            "【强制约束 C1–C4（每次输出必带）】\n"
            + c1_text() + "\n"
            + (c2_text(sig, meta) if meta else "C2 做空限制：市场未识别，默认从严（不可开空）。") + "\n"
            + c3_text() + "\n"
            + "C4 仓位与频率：需有效信号方可反推仓位；本单无信号，不开新仓。"
        )
        return render(df, meta=dict(title=title, ylabel=ylabel, vlabel=vlabel),
                      levels=[], events=[], measures=None, vol_events=None,
                      text_left=left, text_right=right, footer=footer, out=out,
                      dpi=dpi, **kw)

    left, right = build_text_blocks(sig, meta, df=df, adjust=adjust)
    # 四色K线节奏块（EMA12/50 展示层 + 量价读数 + 与形态方向的一致性交叉校验）
    # 挂右栏：左栏（一二三＋失败识别）已 30 行接近满，右栏（四＋五C1-C4）仅 22 行有富余
    try:
        import caisen_trend as _ct
        _tr = _ct.compute(df)
        right = (right.rstrip("\n") + "\n\n"
                 + _ct.summary_text(df, _tr, meta=meta,
                                    px=lambda v: _px(v, adjust),
                                    direction=sig.direction).rstrip("\n") + "\n")
    except Exception:
        pass
    levels = build_levels(sig, meta, adjust=adjust)
    events = build_events(sig, df, meta, adjust=adjust)
    measures = kw.pop("measures", None)
    if measures is None:
        n = len(df)
        # 垂直量距标尺：颈线→底(H) 与 颈线→目标①(=H)
        measures = [dict(x=n - 3.5, y0=sig.extreme["price"], y1=sig.neckline,
                         label=f'H={_amt(sig.height, sig.last_close)}', c='#2e7d32'),
                    dict(x=n - 3.5, y0=sig.neckline, y1=sig.target1,
                         label=f'=H {_amt(sig.height, sig.last_close)}', c='#c62828')]
    return render(df, meta=dict(title=title,
                                ylabel='价格（元）',
                                vlabel=vlabel),
                  levels=levels, events=events,
                  plain_arrows=kw.pop("plain_arrows", None),
                  measures=measures,
                  vol_events=kw.pop("vol_events", None),
                  text_left=left, text_right=right,
                  footer=footer, out=out, dpi=dpi, **kw)


# ===================================================================
# 5. 独立文字分析（Markdown，可直接发 / 存档）
# ===================================================================

def build_report(sig, meta, adjust=None) -> str:
    if not sig.ok:
        return (f"# 蔡森 A+B 分析（{getattr(meta,'name','标的')}）\n\n"
                f"警讯 未识别到可交易形态：{sig.reason}\n\n"
                f"> 数据：{getattr(meta,'market_label','')}　"
                f"方法论：蔡森《多空轉折一手抓》　本分析不构成投资建议。")
    left, right = build_text_blocks(sig, meta, df=None, adjust=adjust)

    def _md_section(text: str) -> str:
        # 只给「五大块」标题加 ##，不污染块内 C2/C4 的【市场】【确认单】等文字
        sec = {
            "【一、结构判定】": "## 一、结构判定\n",
            "【二、关键价位一览】": "## 二、关键价位一览\n",
            "【三、风险报酬（H 模块）】": "## 三、风险报酬（H 模块）\n",
            "【四、论据·量价结构（G 招）】": "## 四、论据·量价结构（G 招）\n",
            "【五、强制约束 C1–C4（每次输出必带）】": "## 五、强制约束 C1–C4（每次输出必带）\n",
        }
        for k, v in sec.items():
            text = text.replace(k, v)
        return text

    lines = [
        f"# {getattr(meta,'name','标的')} {getattr(meta,'code','')} · 蔡森 A+B 形态分析",
        "",
        f"> 数据：{getattr(meta,'market_label','')} {getattr(meta,'period_label','')}"
        f"（{getattr(meta,'adjust_label','')}）　|　方法论：蔡森《多空轉折一手抓》"
        f"　|　**本分析不构成任何投资建议**",
        "",
        _md_section(left),
        "",
        _md_section(right),
        "",
        "---",
        f"数据来源：通达信 tdx-connector（{getattr(meta,'adjust_label','')}）"
        f"　|　成交量单位：{getattr(meta,'vol_unit','')}"
        f"　|　快照：{getattr(meta,'snapshot','')}",
    ]
    return "\n".join(lines)
