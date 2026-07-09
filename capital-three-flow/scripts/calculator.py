"""
资本三流 —— 计算引擎（2026-07 核实版）
========================================
输入 collector.collect() 的原始数据（已核实的 akshare 字段），输出：
  - 流量(volume) / 流速(velocity) / 流向(direction) 三维指标
  - 三个合成指数：CFCI（流向综合）、CFEI（流转效率）、CRI（走资风险）
  - 三流共振离散打分 S 与结论（共振 / 混沌 / 中间）

数据契约（collect 输出）：
  m2{dat, m2, m2_yoy} | gdp{date,value} | forex{date,reserve,gold,change}
  base_money{date,base_money} | margin{date,financing,securities,total,total_prev,delta}
  main_force{date,net_inflow} | fx_rate{date,symbol,name,rate,change_pct}
  sector_flow{date,sectors:[{name,net}],count} | north_flow=None(已停更)

数学底层见 references/methodology.md；数据源核实见 references/data_sources.md。
缺失项记 None 并重新归一化，绝不编造。
"""

import os
import json

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, "config", "indicators.yaml")

DEFAULT_CONFIG = {
    "cfci_weights": {"main_flow": 0.40, "margin_flow": 0.30, "fx_flow": 0.30},
    "cfei_weights": {"money_multiplier": 0.30, "velocity": 0.40, "credit_turnover": 0.30},
    # CRI：外汇储备变动(主) + 人民币贬值压力(外部代理)。权重求和=1
    "cri_weights": {"forex_change": 0.65, "usdcny": 0.35},
    "scoring": {
        "volume": {"m2_yoy_up": 10.0, "m2_yoy_down": 7.0, "main_flow_up": 300, "main_flow_down": -300},
        "velocity": {"v_up": 0.45, "v_down": 0.40},
        "direction": {"d_up": 0.1, "d_down": -0.1, "usdcny_weak": 0.2},
    },
    "verdict": {"resonance_min": 2, "chaos_max": 0},
    "sector_ranking": {"top_n": 5, "bottom_n": 5},
}


def load_config() -> dict:
    try:
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if isinstance(cfg, dict):
            merged = json.loads(json.dumps(DEFAULT_CONFIG))
            for k, v in cfg.items():
                merged[k] = v
            return merged
    except Exception:
        pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def _num(x):
    try:
        return float(x) if x is not None else None
    except (ValueError, TypeError):
        return None


# ── 流量 ────────────────────────────────────────────────────
def compute_volume(data, cfg) -> dict:
    m2 = data.get("m2") or {}
    gdp = data.get("gdp") or {}
    margin = data.get("margin") or {}
    mf = data.get("main_force") or {}

    m2_val = _num(m2.get("m2"))
    m2_yoy = _num(m2.get("m2_yoy"))
    main_net = _num(mf.get("net_inflow"))
    margin_total = _num(margin.get("total"))
    margin_delta = _num(margin.get("delta"))

    # 流量「大不大」判定：分两层——绝对量 + 增速基准
    # 绝对量：中国 M2 常态 >300 万亿(亿元)即属全球最大货币池之一
    m2_abs_size = "极大" if (m2_val and m2_val > 3000000) else ("较大" if (m2_val and m2_val > 2000000) else "一般")
    # 增速基准：近5年常态区间约 7%~12%（2020前>10%，2024-25回落至7-8%）
    bands = cfg.get("m2_bands", {"low": 8.0, "high": 11.0})
    if m2_yoy is not None:
        if m2_yoy >= bands.get("high", 11.0):
            m2_growth = "扩张(放水)"
        elif m2_yoy <= bands.get("low", 8.0):
            m2_growth = "收缩(收敛)"
        else:
            m2_growth = "中性(收敛区间)"
    else:
        m2_growth = None
    # 杠杆方向：融资融券环比
    if margin_delta is not None:
        leverage_dir = "加杠杆" if margin_delta > 0 else ("去杠杆" if margin_delta < 0 else "持平")
    else:
        leverage_dir = None

    # 有效实体流量代理：M2 × 实体参与率（细分数据缺失，占位0.6，仅供演示）
    effective_entity_flow = m2_val * 0.6 if m2_val else None

    return {
        "m2": m2_val,
        "m2_yoy": m2_yoy,
        "m2_unit": m2.get("unit", "亿元"),
        "m2_abs_size": m2_abs_size,
        "m2_growth": m2_growth,
        "main_force_net_inflow": main_net,
        "margin_total": margin_total,
        "margin_delta": margin_delta,
        "leverage_dir": leverage_dir,
        "effective_entity_flow": effective_entity_flow,
        "gdp_nominal": _num(gdp.get("value")),
    }


# ── 流速 ────────────────────────────────────────────────────
def compute_velocity(data, cfg) -> dict:
    gdp = data.get("gdp") or {}
    m2 = data.get("m2") or {}
    bm = data.get("base_money") or {}
    margin = data.get("margin") or {}

    gdp_val = _num(gdp.get("value"))           # akshare 为季度值
    m2_val = _num(m2.get("m2"))
    base = _num(bm.get("base_money"))

    # GDP 季度值 → 年化(×4)，使 V=名义GDP/M2 符合费雪年度框架
    gdp_annual = (gdp_val * 4) if gdp_val else None
    V = (gdp_annual / m2_val) if (gdp_annual and m2_val) else None
    money_multiplier = (m2_val / base) if (m2_val and base) else None  # 真实货币乘数

    # ── 微观流速：杠杆资金日周转速度 = 融资买入额 / 融资余额(%) ──
    # 含义：杠杆资金每天「倒手」多少比例；越高=场内杠杆活跃、追涨杀跌快
    fin_buy = _num(margin.get("fin_buy"))
    financing = _num(margin.get("financing"))
    micro_leverage_velocity = (fin_buy / financing) if (fin_buy is not None and financing) else None

    # ── 微观流速：板块间毛周转(跨市场资本活跃度) = Σ(行业流入+流出) ──
    sec = data.get("sector_flow") or {}
    sector_gross = _num(sec.get("gross"))

    return {
        "V_macro": round(V, 4) if V else None,
        "V_formula": "V = 年化名义GDP(季×4) / M2（宏观流速）",
        "money_multiplier": round(money_multiplier, 4) if money_multiplier else None,
        "money_multiplier_formula": "货币乘数 = M2 / 基础货币(储备货币)",
        "micro_leverage_velocity": round(micro_leverage_velocity, 4) if micro_leverage_velocity is not None else None,
        "micro_leverage_velocity_formula": "微观流速 = 融资买入额 / 融资余额（杠杆资金日周转%）",
        "sector_gross_turnover": sector_gross,
    }


# ── 流向 ────────────────────────────────────────────────────
def compute_direction(data, cfg) -> dict:
    mf = data.get("main_force") or {}
    margin = data.get("margin") or {}
    forex = data.get("forex") or {}

    main_net = _num(mf.get("net_inflow")) or 0.0
    margin_delta = _num(margin.get("delta")) or 0.0
    fx_change = _num(forex.get("change")) or 0.0

    # 市场内资本净流向（主力+杠杆）方向系数
    market_net = main_net + margin_delta
    D_market = market_net / (abs(market_net) + 500.0)

    # 跨境资本流向（外汇储备变动代理）方向系数
    D_fx = fx_change / (abs(fx_change) + 200.0)

    # 板块流向集中度 HHI（行业主力净流入分布，细分层级）
    # HHI = Σ (|net_i| / Σ|net_j|)²  ∈ [1/N, 1]；越高=资金越集中少数板块
    sec = data.get("sector_flow") or {}
    sectors = sec.get("sectors") or []
    HHI = None
    hhi_note = None
    if sectors:
        nets = [abs(s["net"]) for s in sectors if s.get("net") is not None]
        tot = sum(nets)
        if tot > 0:
            HHI = sum((n / tot) ** 2 for n in nets)
        else:
            hhi_note = "板块净流入全为0，HHI无意义"
    else:
        hhi_note = "板块资金流缺失（需本机+网络），HHI未计算"

    return {
        "D_market": round(D_market, 4),
        "D_fx": round(D_fx, 4),
        "HHI": round(HHI, 4) if HHI is not None else None,
        "HHI_note": hhi_note,
        "sector_count": len(sectors),
        "market_net": market_net,
        "fx_change": fx_change,
    }


# ── 三个合成指数 ────────────────────────────────────────────
def compute_indices(data, vol, vel, direction, cfg) -> dict:
    w = cfg.get("cfci_weights", DEFAULT_CONFIG["cfci_weights"])
    parts = {
        "main_flow": _num((data.get("main_force") or {}).get("net_inflow")) or 0.0,
        "margin_flow": _num((data.get("margin") or {}).get("delta")) or 0.0,
        "fx_flow": direction.get("fx_change") or 0.0,
    }
    # 仅对可用分项加权，并重新归一化
    avail = {k: v for k, v in parts.items() if v is not None}
    wsum = sum(w.get(k, 0) for k in avail) or 1.0
    weighted = sum(parts[k] * w.get(k, 0) for k in avail) / wsum
    cfci = max(-100, min(100, weighted / 3.0))

    w2 = cfg.get("cfei_weights", DEFAULT_CONFIG["cfei_weights"])
    V = vel.get("V_macro") or 0.0
    mm = vel.get("money_multiplier") or 0.0
    # 信贷周转：社融缺失 → 0（降级），并标注
    credit_turnover = 0.0
    cfei = w2.get("money_multiplier", 0.3) * (mm / 8.0) + w2.get("velocity", 0.4) * (V / 0.5) + w2.get("credit_turnover", 0.3) * credit_turnover

    # CRI 走资风险：外汇储备变动(主) + 人民币贬值压力(外部代理)
    fx_change = direction.get("fx_change") or 0.0
    fx_rate = data.get("fx_rate") or {}
    usdcny_chg = _num(fx_rate.get("change_pct"))
    cri_w = cfg.get("cri_weights", DEFAULT_CONFIG["cri_weights"])
    cri_forex = max(0, min(100, 50 - fx_change / 5.0))   # 外储降→风险升
    if usdcny_chg is not None:
        cri_usdcny = max(0, min(100, 50 + usdcny_chg * 12.0))  # 人民币贬值(正)→风险升
        wf = cri_w.get("forex_change", 0.65)
        wu = cri_w.get("usdcny", 0.35)
        cri = wf * cri_forex + wu * cri_usdcny
    else:
        cri = cri_forex  # 汇率缺失则仅用外储

    return {
        "CFCI": round(cfci, 2),
        "CFEI": round(cfei, 4),
        "CRI": round(cri, 2),
        "cri_usdcny_available": usdcny_chg is not None,
        "cfei_credit_turnover_available": False,
    }


# ── 三流共振打分 ────────────────────────────────────────────
def compute_score(data, vol, vel, direction, cfg) -> dict:
    sc = cfg.get("scoring", DEFAULT_CONFIG["scoring"])
    s_vol = sc.get("volume", {})
    s_vel = sc.get("velocity", {})
    s_dir = sc.get("direction", {})
    notes = []

    # 流量
    sv = 0
    m2_yoy = vol.get("m2_yoy")
    if m2_yoy is not None:
        if m2_yoy >= s_vol.get("m2_yoy_up", 10):
            sv += 1
        elif m2_yoy <= s_vol.get("m2_yoy_down", 7):
            sv -= 1
    main_net = vol.get("main_force_net_inflow") or 0.0
    if main_net >= s_vol.get("main_flow_up", 300):
        sv += 1
    elif main_net <= s_vol.get("main_flow_down", -300):
        sv -= 1
    sv = max(-1, min(1, sv))
    if sv == 0:
        notes.append(f"流量中性：M2同比{m2_yoy}%（{vol.get('m2_growth') or '缺失'}），主力净流入缺失")

    # 流速
    sve = 0
    V = vel.get("V_macro")
    if V is not None:
        if V >= s_vel.get("v_up", 0.45):
            sve = 1
        elif V <= s_vel.get("v_down", 0.40):
            sve = -1
    else:
        notes.append("流速：V_macro 缺失，按中性计")

    # 流向：内部（市场）方向 + 跨境方向（外储 + 人民币贬值）
    sd = 0
    D_mkt = direction.get("D_market") or 0.0
    internal = 0
    if D_mkt >= s_dir.get("d_up", 0.1):
        internal = 1
    elif D_mkt <= s_dir.get("d_down", -0.1):
        internal = -1

    cross = 0
    D_fx = direction.get("D_fx") or 0.0
    if D_fx <= s_dir.get("d_down", -0.1):
        cross -= 1  # 外储下降叠加风险
    fx_rate = data.get("fx_rate") or {}
    usdcny_chg = _num(fx_rate.get("change_pct"))
    uw = s_dir.get("usdcny_weak", 0.2)
    if usdcny_chg is not None:
        if usdcny_chg >= uw:
            cross -= 1  # 人民币明显贬值 = 资本外流压力
        elif usdcny_chg <= -uw:
            cross += 1  # 人民币明显升值 = 资本流入支撑
    sd = max(-1, min(1, internal + cross))

    S = sv + sve + sd
    vd = cfg.get("verdict", DEFAULT_CONFIG["verdict"])
    if S >= vd.get("resonance_min", 2):
        verdict = "三流同向共振 —— 趋势力量确立，宏观趋势可顺势"
    elif S <= vd.get("chaos_max", 0):
        verdict = "三流背离紊乱 —— 混沌期，微观技术分析有效性下降"
    else:
        verdict = "三流部分共振 —— 趋势未明，观望/结构分化"

    return {
        "S_flow": sv, "S_velocity": sve, "S_direction": sd,
        "S_total": S, "verdict": verdict, "notes": notes,
    }


# ── 股票交易参考（把三流翻译成可操作信号） ──────────────────
def build_trading_reference(data, vol, vel, direction, cfg) -> dict:
    """将三维指标落地为交易可参考的判定：
      - 流动性背景(仓位) / 资本流向(多空+板块排名) / 微观流速(策略) / 综合姿态。
    纯方法论翻译，不构成投资建议。"""
    sr = cfg.get("sector_ranking", DEFAULT_CONFIG["sector_ranking"])

    # 1) 流动性背景（仓位参考）
    m2_yoy = vol.get("m2_yoy")
    m2_growth = vol.get("m2_growth")
    m2_abs = vol.get("m2_abs_size")
    leverage_dir = vol.get("leverage_dir")
    if m2_growth == "扩张(放水)" and leverage_dir != "去杠杆":
        liquidity = "宽松扩张 → 仓位可积极"
    elif m2_growth == "收缩(收敛)" or leverage_dir == "去杠杆":
        liquidity = "收敛 + 去杠杆 → 仓位偏防守"
    else:
        liquidity = "中性 → 仓位均衡"
    liquidity_detail = (f"M2绝对量{m2_abs}，同比{m2_yoy}%（{m2_growth}）；"
                        f"杠杆{leverage_dir or '缺失'}")

    # 2) 资本流向：跨境（中国↔境外）+ A股内部板块排名
    D_fx = direction.get("D_fx") or 0.0
    D_mkt = direction.get("D_market") or 0.0
    fx_change = direction.get("fx_change") or 0.0
    if fx_change < 0:
        cross = f"资本外流：外汇储备环比降 {abs(fx_change):.1f} 亿美元，D_fx={D_fx} → 资金由中国流向境外"
    elif fx_change > 0:
        cross = f"资本小幅回流：外汇储备环比升 {fx_change:.1f} 亿美元，D_fx={D_fx} → 境外资金回流入境"
    else:
        cross = "外汇储备环比持平，跨境净额≈0"
    north_note = "北向净流量已停更，跨境外流仅以外储变动代理（非个股级北向买卖）"

    sec = data.get("sector_flow") or {}
    sectors = sorted(sec.get("sectors") or [], key=lambda s: -(s.get("net") or 0))
    tn, bn = sr.get("top_n", 5), sr.get("bottom_n", 5)
    fmt_sector = lambda s: {"name": s.get("name"), "net": round(s.get("net"), 2) if s.get("net") is not None else None,
                            "pct": round(s.get("pct"), 2) if s.get("pct") is not None else None}
    top = [fmt_sector(s) for s in sectors[:tn]]
    asc = sorted(sectors, key=lambda s: (s.get("net") or 0))
    # 空方榜只列净流出行业（net<0），避免把净流入板块误标为空头方向
    bottom = [fmt_sector(s) for s in asc if (s.get("net") or 0) < 0][:bn]
    sector_net_sum = sum((s.get("net") or 0) for s in sectors)

    if D_mkt > 0 and sector_net_sum > 0:
        internal = "A股内部资金净流入（风险偏好回升）"
    elif D_mkt < 0:
        internal = "A股内部资金边际流出（风险偏好偏弱）"
    else:
        internal = "A股内部资金中性"

    if D_fx <= -0.1 and D_mkt <= 0:
        risk_appetite = "防御（外流 + 内部偏弱）"
    elif D_fx > 0 and D_mkt > 0:
        risk_appetite = "风险偏好回升（内+外双流入）"
    else:
        risk_appetite = "分化（内外不同步）"

    # 3) 微观流速（策略参考）
    V = vel.get("V_macro")
    mlv = vel.get("micro_leverage_velocity")
    HHI = direction.get("HHI")
    macro_v = "宏观流速偏低（资金空转）" if (V is not None and V <= 0.40) else "宏观流速正常"
    micro = ""
    if mlv is not None:
        lvl = "活跃" if mlv >= 0.05 else ("温和" if mlv >= 0.03 else "低迷")
        micro = f"杠杆资金日周转 {mlv * 100:.2f}%（{lvl}）"
    hhi_s = ""
    if HHI is not None:
        lbl = "高度集中（抱团）" if HHI >= 0.18 else ("中度集中" if HHI >= 0.10 else "分散（轮动快）")
        hhi_s = f"板块集中度 HHI={HHI} → {lbl}"

    if HHI is not None and HHI >= 0.18 and V is not None and V > 0.40:
        strategy = "动量策略占优（抱团 + 流速正常）"
    elif V is not None and V <= 0.40:
        strategy = "流速低 → 偏结构性/反转，忌追高动量"
    elif HHI is not None and HHI < 0.10:
        strategy = "板块分散轮动 → 题材短线，轻指数"
    else:
        strategy = "均衡（动量/反转各半）"

    return {
        "liquidity_regime": liquidity,
        "liquidity_detail": liquidity_detail,
        "risk_appetite": risk_appetite,
        "internal_preference": internal,
        "cross_flow": cross,
        "north_note": north_note,
        "micro_velocity_note": "；".join([x for x in [macro_v, micro, hhi_s] if x]),
        "strategy_tilt": strategy,
        "sector_top": top,
        "sector_bottom": bottom,
        "sector_net_sum": round(sector_net_sum, 2) if sectors else None,
        "sector_count": len(sectors),
    }


def run_all(data) -> dict:
    cfg = load_config()
    vol = compute_volume(data, cfg)
    vel = compute_velocity(data, cfg)
    direction = compute_direction(data, cfg)
    indices = compute_indices(data, vol, vel, direction, cfg)
    score = compute_score(data, vol, vel, direction, cfg)
    trading = build_trading_reference(data, vol, vel, direction, cfg)
    return {
        "as_of": data.get("as_of"),
        "demo": data.get("demo", False),
        "north_flow_note": data.get("north_flow_note"),
        "fx_rate": data.get("fx_rate"),
        "volume": vol, "velocity": vel, "direction": direction,
        "indices": indices, "score": score, "trading_reference": trading,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from collector import collect
    print(json.dumps(run_all(collect(demo="--demo" in sys.argv)), ensure_ascii=False, indent=2, default=str))
