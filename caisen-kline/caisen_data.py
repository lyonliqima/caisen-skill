#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔡森 K 线分析 · 数据适配层 (S1)
=================================================
职责：把 tdx-connector 返回的原始 JSON 变成 **可信的** DataFrame + 元数据。

设计铁律
--------
宁可抛错，绝不静默返回错标的 / 错价位。
（依据 AUDIT_2026-08-03.md：P0-1 静默返错标的、P0-2 复权未声明、
  P1-8 量单位跨市场不一致、P1-10 未收盘 K 线）

架构说明（重要）
----------------
MCP 工具只能由 Agent 调用，Python 进程无法直接访问。
所以本模块 = 「请求参数生成器」+「返回校验解析器」，中间那一步由 Agent 执行：

    1. Python : req = build_request("00700", market="HK", expect_name="腾讯控股")
    2. Agent  : 调 mcp__tdx-connector__tdx_kline(**req["tool_args"])
    3. Agent  : 原始 JSON 存到 data/raw/<key>.json
    4. Python : df, meta = load_and_validate("data/raw/<key>.json", req)

量单位实测结论（2026-08-03）
---------------------------
    Volume = RawVolume / Unit
    A股  Unit=100   RawVolume=7187261 股  → Volume=71872.61 手
    港股 Unit=0.01  RawVolume=317920 手   → Volume=31792000 股
  即 Volume 字段的物理含义 **跨市场不同**，图上不能硬编码「手」。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict, replace
from datetime import datetime, time
from pathlib import Path

import pandas as pd


# ===================================================================
# 1. 市场注册表
# ===================================================================
# target 规则（实测）：setcode ∈ {0,1,2} → "0"；其余一律 "1"
# 不传 target：港股会静默返回同代码 A 股！期货直接返空。

@dataclass(frozen=True)
class Market:
    key: str                 # 内部标识
    label: str               # 中文名
    setcodes: tuple          # 合法 setcode
    vol_unit: str            # 成交量单位中文（图上用）
    close_hhmm: int          # 当日收盘时刻 HHMM（判断最后一根是否收盘）
    t_plus: int              # T+N
    price_limit: str         # 涨跌停描述
    short_mode: str          # 做空可行性（C2 用）
    supported: bool = True   # tdx 是否真的能取到数据
    note: str = ""
    unit_expect: float | None = None   # AttachInfo.Unit 应等于此值；None=未实测，不做肯定式校验
    is_a_share: bool = False           # 使用沪深 A 股量纲（Unit=100）——「非A股却返回A股数据」否定式校验用
    #  D2/D3：与其它市场共用 setcode，故 **不进 setcode 反查表主槽**。
    #  只能靠「代码前缀推断（写入 expect.market）」或「Unit 消歧」命中。
    ambiguous: bool = False


MARKETS = {
    "CN_SH":   Market("CN_SH", "上交所A股", (1,), "手", 1500, 1, "10%（ST 5%，科创/创业 20%）",
                      "禁止开空（融券极难）→ 只作减仓/离场/避险",
                      unit_expect=100, is_a_share=True),
    "CN_SZ":   Market("CN_SZ", "深交所A股", (0,), "手", 1500, 1, "10%（ST 5%，创业板 20%）",
                      "禁止开空（融券极难）→ 只作减仓/离场/避险",
                      unit_expect=100, is_a_share=True),
    "CN_BJ":   Market("CN_BJ", "北交所",   (2,), "手", 1500, 1, "30%",
                      "禁止开空 → 只作减仓/离场/避险",
                      unit_expect=100, is_a_share=True),
    "HK":      Market("HK", "港股",        (31,), "股", 1600, 0, "无涨跌停（有市调机制 VCM）",
                      "可做空（须为可沽空名单 + 券源），需独立确认",
                      unit_expect=0.01),
    "FUT_SHFE": Market("FUT_SHFE", "上期所", (30,), "手", 1500, 0, "无涨跌停（有停板幅度+熔断）",
                       "可双向开仓（保证金交易，注意杠杆）", unit_expect=1),
    "FUT_DCE":  Market("FUT_DCE", "大商所",  (29,), "手", 1500, 0, "无涨跌停（有停板幅度）",
                       "可双向开仓（保证金交易，注意杠杆）", unit_expect=1),
    "FUT_CZCE": Market("FUT_CZCE", "郑商所", (28,), "手", 1500, 0, "无涨跌停（有停板幅度）",
                       "可双向开仓（保证金交易，注意杠杆）", unit_expect=1),
    "FUND":    Market("FUND", "基金/ETF",  (33,), "份", 1500, 0, "视品种而定",
                      "部分 ETF 可融券做空，需独立确认"),
    "INDEX":   Market("INDEX", "中证指数",  (62,), "点", 1500, 0, "指数无涨跌停",
                      "指数本身不可交易，需经 ETF/期货工具"),

    # ---- D2/D3：与沪深 A 股共用 setcode 的品种（ambiguous=True，见字段注释）----
    # 实测：上证指数 setcode=1 且 Unit=1；而沪市 A 股 setcode=1 且 Unit=100 → 可用 Unit 消歧。
    "INDEX_CN": Market("INDEX_CN", "中国指数", (1, 0), "点", 1500, 0, "指数无涨跌停",
                       "指数本身不可交易，需经 ETF/期货工具",
                       unit_expect=1, ambiguous=True,
                       note="上证(000xxx)/深证(399xxx)系列指数与 A 股共用 setcode 0/1，"
                            "靠 AttachInfo.Unit=1 消歧"),
    # 实测：510300 setcode=1 且 Unit=100 —— 与沪市 A 股 **完全同构**，Unit 无法消歧，
    #      只能靠代码前缀推断后写入 expect.market。故 parse 必须优先采信 expect.market。
    "ETF_SH":  Market("ETF_SH", "沪市ETF/LOF", (1, 33), "手", 1500, 1,
                      "跟随标的（宽基 10%，科创/创业 20%，跨境 10%）",
                      "部分 ETF 可融券做空，需独立确认",
                      unit_expect=None, is_a_share=True, ambiguous=True,
                      note="股票型 ETF 为 T+1；跨境(QDII)/债券/商品 ETF 多为 T+0，须按品种确认；"
                           "setcode 1=沪市股票ETF(Unit=100)，setcode 33=基金段QDII ETF(Unit=1)，二者均放行"),
    "ETF_SZ":  Market("ETF_SZ", "深市ETF/LOF", (0, 33), "手", 1500, 1,
                      "跟随标的（宽基 10%，创业 20%，跨境 10%）",
                      "部分 ETF 可融券做空，需独立确认",
                      unit_expect=None, is_a_share=True, ambiguous=True,
                      note="股票型 ETF 为 T+1；跨境(QDII)/债券/商品 ETF 多为 T+0，须按品种确认；"
                           "setcode 0=深市股票ETF(Unit=100)，setcode 33=基金段QDII ETF(Unit=1)，二者均放行"),

    # ---- 以下实测不可用，保留条目以便 **显式报错**，禁止静默返空 ----
    # D3：以下三家交易所本项目未实测通过 tdx 取数。登记成条目是为了让
    #     IF2512 / SC2601 / SI2601 这类代码 **报"暂不支持"** 而不是"无法推断市场"，
    #     避免用户误以为补个 market 参数就能跑。
    "FUT_CFFEX": Market("FUT_CFFEX", "中金所", tuple(), "手", 1515, 0, "有停板幅度+熔断",
                        "可双向开仓（保证金交易）", supported=False,
                        note="股指/国债期货（IF/IH/IC/IM/T/TF/TS/TL），tdx-connector 未实测覆盖"),
    "FUT_INE":   Market("FUT_INE", "上期能源", tuple(), "手", 1500, 0, "有停板幅度",
                        "可双向开仓（保证金交易）", supported=False,
                        note="原油 SC / 低硫燃油 LU / 20号胶 NR / 国际铜 BC，tdx-connector 未实测覆盖"),
    "FUT_GFEX":  Market("FUT_GFEX", "广期所", tuple(), "手", 1500, 0, "有停板幅度",
                        "可双向开仓（保证金交易）", supported=False,
                        note="工业硅 SI / 碳酸锂 LC / 多晶硅 PS，tdx-connector 未实测覆盖"),
    "US":      Market("US", "美股", (74,), "股", 1600, 0, "无涨跌停（有熔断）",
                      "可做空", supported=False,
                      note="实测 tdx_kline(setcode=74) 返回空 Rows；lookup 能查到代码但取不到 K 线"),
    "FX":      Market("FX", "外汇/汇率", tuple(), "手", 2400, 0, "无涨跌停",
                      "可双向", supported=False,
                      note="实测 tdx_lookup_stock 搜不到任何外汇品种，tdx 无此覆盖"),
}

# 期货合约代码：品种字母 + 3~4 位月份（RB2610 / m2509 / IF2512）
_FUT_CODE = re.compile(r"^([A-Za-z]{1,3})(\d{3,4})$")

# D3：期货品种字母 → 交易所。tdx 的 setcode 按交易所分，光看"字母+数字"判不出归属。
# 键一律大写，取代码的字母段直接查表（字母段已完整分离，无需试长短）。
_FUT_EXCHANGE = {
    # 上期所 SHFE
    **{k: "FUT_SHFE" for k in (
        "CU", "AL", "ZN", "PB", "NI", "SN", "AU", "AG", "RB", "WR", "HC", "SS",
        "FU", "BU", "RU", "SP", "AO", "BR")},
    # 大商所 DCE
    **{k: "FUT_DCE" for k in (
        "A", "B", "M", "Y", "P", "C", "CS", "JD", "RR", "LH", "J", "JM", "I",
        "L", "V", "PP", "EG", "EB", "PG", "FB", "BB")},
    # 郑商所 CZCE
    **{k: "FUT_CZCE" for k in (
        "SR", "CF", "CY", "TA", "MA", "FG", "SA", "RM", "OI", "RS", "ZC", "SF",
        "SM", "UR", "PF", "PK", "AP", "CJ", "SH", "PX", "WH", "PM", "RI", "LR", "JR")},
    # 以下三家未实测覆盖 —— 登记后可给出"暂不支持"的准话（见 MARKETS 注释）
    **{k: "FUT_CFFEX" for k in ("IF", "IH", "IC", "IM", "T", "TF", "TS", "TL")},
    **{k: "FUT_INE" for k in ("SC", "LU", "NR", "BC", "EC")},
    **{k: "FUT_GFEX" for k in ("SI", "LC", "PS")},
}

# setcode → 市场 反查表。**跳过 ambiguous 市场**：它们与 A 股共用 setcode，
# 若一并塞进来会互相覆盖（dict 后者胜），导致沪市 A 股被误判成 ETF 之类。
SETCODE2MARKET = {sc: m for m in MARKETS.values() if not m.ambiguous
                  for sc in m.setcodes}

PERIODS = {1: "5分钟", 2: "15分钟", 3: "30分钟", 4: "日线", 5: "周线",
           6: "月线", 7: "1分钟", 8: "60分钟", 9: "季线", 10: "年线"}

TQ_LABEL = {0: "不复权", 1: "前复权", 2: "后复权"}


# ===================================================================
# 2. 异常（全部是"拒绝出图"级别）
# ===================================================================

class DataError(Exception):
    """数据层基础异常：触发即禁止出图。"""


class SymbolMismatchError(DataError):
    """返回标的与请求标的不符（P0-1 静默错标的）。"""


class UnsupportedMarketError(DataError):
    """tdx 不支持该市场（P1-7 覆盖缺口），禁止静默返空。"""


class EmptyDataError(DataError):
    """返回 Rows 为空。"""


class IntegrityError(DataError):
    """OHLC / 日期 / 量的完整性校验不过。"""


# ===================================================================
# 3. 请求构造
# ===================================================================

def _guess_market(code: str, market: str | None) -> Market:
    if not str(code).strip():
        raise DataError("code 不能为空")
    if market:
        key = market.upper()
        if key not in MARKETS:
            raise UnsupportedMarketError(
                f"未知市场 '{market}'。可选：{', '.join(MARKETS)}")
        return MARKETS[key]
    # 仅在未显式指定时做保守推断；有歧义一律要求显式传
    c = code.strip().upper()
    if re.fullmatch(r"\d{5}", c):
        return MARKETS["HK"]
    if re.fullmatch(r"6\d{5}", c):
        return MARKETS["CN_SH"]
    # D3：基金/ETF/LOF 必须排在 A 股规则之前 —— 深市基金 15/16/17/18 开头，
    #     若先撞上「(0|3)\d{5}」以外的规则会归错市场。
    if re.fullmatch(r"5\d{5}", c):
        return MARKETS["ETF_SH"]        # 沪市：50x LOF/封基、51x/56x/58x ETF
    if re.fullmatch(r"1[5-8]\d{4}", c):
        return MARKETS["ETF_SZ"]        # 深市：15x/16x/17x/18x 基金
    # D2：深证系列指数 399xxx 无歧义，可直接判；
    #     上证系列指数 000xxx 与深市 A 股 000xxx **完全撞码**（如 000001 既是
    #     上证指数又是平安银行），无法自动推断 → 落到下方 CN_SZ，需显式传 market。
    if re.fullmatch(r"399\d{3}", c):
        return MARKETS["INDEX_CN"]
    if re.fullmatch(r"(0|3)\d{5}", c):
        return MARKETS["CN_SZ"]
    if re.fullmatch(r"(4|8)\d{5}", c):
        return MARKETS["CN_BJ"]
    # D3：期货合约（字母品种 + 月份），按品种字母查交易所归属
    m_fut = _FUT_CODE.fullmatch(c)
    if m_fut:
        variety = m_fut.group(1).upper()
        mk_key = _FUT_EXCHANGE.get(variety)
        if mk_key is None:
            raise UnsupportedMarketError(
                f"代码 '{code}' 形如期货合约，但品种 '{variety}' 不在已登记表内，"
                f"无法确定交易所。→ 请显式传 market=（FUT_SHFE / FUT_DCE / FUT_CZCE），"
                f"或核对品种代码。")
        return MARKETS[mk_key]
    # ---- S6 补全：美股/外汇代码一眼认出，直接报"暂不支持"，不误导"请传 market" ----
    if re.fullmatch(r"[A-Z]{1,5}(\.[A-Z]{1,3})?", c):
        raise UnsupportedMarketError(
            f"代码 '{code}' 形如美股代码，但 tdx-connector 不支持【美股】：{MARKETS['US'].note}。"
            f"→ 该品种暂不支持，禁止静默出图（如需分析请改用兜底数据源）。")
    if re.fullmatch(r"[A-Z]{6}", c):
        raise UnsupportedMarketError(
            f"代码 '{code}' 形如外汇代码，但 tdx-connector 不支持【外汇/汇率】：{MARKETS['FX'].note}。"
            f"→ 该品种暂不支持，禁止静默出图。")
    raise UnsupportedMarketError(
        f"无法从代码 '{code}' 推断市场，请显式传 market=（{', '.join(MARKETS)}）")


def _default_setcode(mk: Market, code: str) -> int:
    """市场内部还分 setcode 时，按代码前缀给默认值（D2）。

    INDEX_CN 横跨 setcode 0/1：深证系列 399xxx 在 0，上证系列 000xxx/88xxxx 在 1。
    只取 setcodes[0] 会把深证成指发到沪市去，触发 setcode 不符。
    """
    c = str(code).strip().upper()
    if mk.key == "INDEX_CN":
        return 0 if c.startswith("399") else 1
    return mk.setcodes[0]


def build_request(code: str, market: str | None = None, *,
                  expect_name: str | None = None,
                  period: int = 4, want_num: int = 300,
                  tq_flag: int = 1, setcode: int | None = None,
                  allow_unnamed: bool = False) -> dict:
    """生成 tdx_kline 调用参数（Agent 拿去调 MCP）。

    强制项：
      - target 显式传（setcode∈{0,1,2}→"0"，其余→"1"）  ← 修 P0-1
      - expect_name 必填，否则拒绝构造请求               ← 修 P0-1（复查补）
      - tqFlag 显式传，不吃默认值                        ← 修 P0-2
      - 不支持的市场直接抛错，不发请求                    ← 修 P1-7

    为什么 expect_name 必填：
      实测错误样本 00700_d3_NO_TARGET_wrong.json 的 Code=00700、Setcode=31
      **与请求完全一致**，只有 AttachInfo.Name 是「模塑科技」。
      也就是说代码校验、setcode 校验统统拦不住 —— 名字是唯一的语义防线。
      确实拿不到预期名时，须显式 allow_unnamed=True，届时改由 Unit 否定式校验兜底。
    """
    mk = _guess_market(code, market)
    if not mk.supported:
        raise UnsupportedMarketError(
            f"tdx-connector 不支持【{mk.label}】：{mk.note}\n"
            f"→ 请改用兜底数据源，或明确告知用户此品种暂不支持。禁止静默出图。")
    if not expect_name and not allow_unnamed:
        raise DataError(
            "expect_name 必填 —— 这是拦截「静默返回错标的」的唯一语义防线。\n"
            "  实测：请求港股 00700 时 tdx 曾返回 A 股【模塑科技】，"
            "而 Code/Setcode 与请求完全一致，只有名字不同。\n"
            "  → 先用 tdx_lookup_stock 查到准确名称再取数；"
            "确实无法预知名称时显式传 allow_unnamed=True。")
    if setcode is None:
        setcode = _default_setcode(mk, code)
    if setcode not in mk.setcodes:
        raise DataError(f"setcode={setcode} 与市场 {mk.label} 不匹配（应为 {mk.setcodes}）")
    if period not in PERIODS:
        raise DataError(f"period={period} 非法，可选 {sorted(PERIODS)}")
    if tq_flag not in TQ_LABEL:
        raise DataError(f"tqFlag={tq_flag} 非法，可选 {sorted(TQ_LABEL)}")
    if not 1 <= want_num <= 1000:
        raise DataError("wantNum 需在 1~1000（实测上限 1000）")

    hints = []
    if period == 4 and want_num < 250:
        hints.append(f"wantNum={want_num} 偏小：日线形态判定建议 ≥250 根，"
                     f"否则区间极值可能是窗口边界值（P1-9）")

    target = "0" if setcode in (0, 1, 2) else "1"
    return {
        "tool": "mcp__tdx-connector__tdx_kline",
        "tool_args": {
            "code": code, "setcode": str(setcode), "period": str(period),
            "wantNum": str(want_num), "tqFlag": str(tq_flag), "target": target,
        },
        "expect": {
            "code": code, "setcode": setcode, "market": mk.key,
            "name": expect_name, "period": period, "tq_flag": tq_flag,
        },
        "hints": hints,
    }


# ===================================================================
# 4. 元数据
# ===================================================================

@dataclass
class Meta:
    name: str
    code: str
    setcode: int
    market: str
    market_label: str
    period: int
    period_label: str
    tq_flag: int
    adjust_label: str
    vol_unit: str
    bars: int
    start: str
    end: str
    hq_date: str
    hq_time: str
    last_bar_closed: bool
    t_plus: int
    price_limit: str
    short_mode: str
    snapshot: str
    warnings: list = field(default_factory=list)

    def title(self) -> str:
        return f"{self.name} {self.code} · {self.market_label} {self.period_label}"

    def footer(self, extra: str = "") -> str:
        """合规 footer：来源 + 复权 + 快照 + 免责。**每张图必须带**。"""
        tail = f"　|　{extra}" if extra else ""
        return (f"数据：通达信 tdx-connector（{self.adjust_label}非实时快照 {self.snapshot}）"
                f"　|　方法论：蔡森《多空轉折一手抓》"
                f"　|　成交量单位：{self.vol_unit}{tail}"
                f"　|　本图为方法论演示，不构成任何投资建议")

    def to_dict(self) -> dict:
        return asdict(self)


# ===================================================================
# 5. 核心：解析 + 校验
# ===================================================================

_PUNCT = re.compile(r"[\s\-_·．.、（）()＊*]")


def _norm_name(s: str) -> str:
    return _PUNCT.sub("", str(s)).upper()


def _name_matches(actual: str, expect: str, mk: "Market | None" = None) -> tuple[bool, str]:
    """标的名比对。返回 (是否放行, 说明)。

    分三档，别一刀切：
      ① 归一后相等                        → 放行，无话可说
      ② 一方是另一方的子串，差异 **不含数字** → 放行 + 警告（简称/全称之别）
      ③ 差异 **含数字**                    → 期货放行（合约月份 RB2610），
                                            其余一律拒（转债「转3」、权证、分级 B）

    第 ③ 档是关键：老版本 `e in a` 会让「东方财富」放行「东方财富转3」，
    那是两个完全不同的标的。
    """
    a, e = _norm_name(actual), _norm_name(expect)
    if not a or not e:
        return False, "名称为空"
    if a == e:
        return True, ""
    if a.startswith(e) or e.startswith(a) or e in a or a in e:
        long_, short_ = (a, e) if len(a) >= len(e) else (e, a)
        diff = long_.replace(short_, "", 1)
        if any(ch.isdigit() for ch in diff):
            if mk is not None and mk.key.startswith("FUT_"):
                return True, f"期货合约名差异「{diff}」（合约月份），已放行"
            return False, (f"名称差异「{diff}」含数字 —— 疑为可转债/权证/分级/不同合约，"
                           f"属不同标的，拒绝放行")
        return True, f"名称非完全一致（简称/全称之别，差异「{diff}」），已放行但请复核"
    return False, "名称完全不匹配"


def _normalize_raw(raw: dict, expect: dict) -> tuple[dict, list[str]]:
    """补回 tdx「因取值 falsy 而被省略」的键（D1）。返回新 dict，不改调用方入参。

    实测：深市 setcode=0 时返回 JSON **根本没有 Setcode 这个键**
    （平安银行 000001、宁德时代 300750 均复现）→ 完整性校验判数据不可信
    → 深市主板 + 创业板全线不可用，占 A 股半壁江山。

    只补 0，绝不补别的：setcode 非 0 时 tdx 一定会给键，缺了就是真异常，照样报错。
    这样既救回深市，又不给"伪造 setcode 绕过校验"开口子。
    """
    out = dict(raw)
    fixed: list[str] = []
    if "Setcode" not in out and expect.get("setcode") is not None:
        try:
            want = int(expect["setcode"])
        except (TypeError, ValueError):
            want = None
        if want == 0:
            out["Setcode"] = 0
            fixed.append("Setcode 键缺失，已按请求声明回填 0"
                         "（深市；tdx 对取值为 0 的字段会省略该键）")
    if "Rows" not in out:
        out["Rows"] = []      # 让它走 C2 的 EmptyDataError，报错比"缺字段"准确
    return out, fixed


def _resolve_market(got_sc: int, unit: float | None,
                    expect: dict) -> tuple[Market | None, list[str]]:
    """确定市场。三级：expect.market 优先 → setcode 反查 → Unit 消歧修正（D2/D3）。

    为什么 expect.market 要排第一：实测 510300（沪深300ETF）的
    setcode=1 且 Unit=100，与沪市 A 股 **完全同构**，解析阶段没有任何信号
    可区分二者，只能采信请求端按代码前缀推断的结果。
    """
    notes: list[str] = []
    mk: Market | None = None

    # ① 采信 expect.market（build_request 已按代码前缀推断并写入）
    key = expect.get("market")
    if key and key in MARKETS:
        cand = MARKETS[key]
        if got_sc in cand.setcodes:
            mk = cand
        else:
            notes.append(f"请求市场【{cand.label}】不含返回的 setcode={got_sc}，"
                         f"改按 setcode 判定")
    # ② setcode 反查（ambiguous 市场不在表内，不会误命中）
    if mk is None:
        mk = SETCODE2MARKET.get(got_sc)
    # ③ Unit 消歧：沪深 setcode 下 Unit=1 的是指数，不是个股/ETF（实测上证指数 Unit=1）
    if (unit is not None and got_sc in (0, 1) and abs(unit - 1.0) < 1e-9
            and (mk is None or mk.key != "INDEX_CN")):
        prev = mk.label if mk else f"未知(setcode={got_sc})"
        mk = MARKETS["INDEX_CN"]
        notes.append(f"AttachInfo.Unit=1 → 判定为指数并已切换为【中国指数】"
                     f"（原按 setcode 判为【{prev}】）；指数不可直接交易")
    return mk, notes


def parse_kline_json(raw: dict, expect: dict | None = None) -> tuple[pd.DataFrame, Meta]:
    """解析并校验 tdx_kline 原始 JSON。任一校验不过 → 抛错（禁止出图）。

    expect 既可传 build_request() 返回里的 "expect" 子字典，也可直接传整个返回值
    （见下方兼容处理）—— 后者曾让四道语义校验被静默架空，必须兜住。
    """
    expect = expect or {}
    # D5【严重】兼容整包 req：早期 pipeline 直接把 build_request() 的返回值喂进来，
    # 而校验读的是它的 "expect" 子字典 → expect.get("name") 恒为 None，
    # **标的名 / 代码 / setcode / 周期 四道校验全部静默跳过**，P0-1 语义防线形同虚设。
    if isinstance(expect.get("expect"), dict):
        expect = expect["expect"]
    warns: list[str] = []

    # --- C0 归一化被省略的 falsy 键（D1）---
    raw, _fixed = _normalize_raw(raw, expect)
    warns.extend(_fixed)

    # --- C1 顶层结构 ---
    for k in ("Rows", "AttachInfo", "Setcode", "Code", "Period"):
        if k not in raw:
            raise IntegrityError(f"返回缺少字段 '{k}'，数据不可信")
    info, rows = raw["AttachInfo"], raw["Rows"]
    if not isinstance(info, dict):
        raise IntegrityError("AttachInfo 结构异常（非对象）")
    try:
        period = int(raw["Period"])
    except (TypeError, ValueError):
        raise IntegrityError(f"Period 字段非法：{raw['Period']!r}")
    # Setcode 提前 int 化：键在但值为 null 时不能让 int() 裸崩
    try:
        got_sc = int(raw["Setcode"])
    except (TypeError, ValueError):
        raise IntegrityError(f"Setcode 字段非法：{raw['Setcode']!r}")

    # --- C2 Rows 非空（美股就栽在这，必须显式报错）---
    if not rows:
        mk = SETCODE2MARKET.get(got_sc)
        hint = f"（{mk.label} 实测不可用：{mk.note}）" if mk and not mk.supported else \
               "（检查 target 是否显式传：期货不传 target 会返空）"
        raise EmptyDataError(f"Rows 为空，无 K 线数据 {hint}")

    # --- C3 代码 / setcode 一致 ---
    got_code = str(raw["Code"]).strip()
    if expect.get("code") and str(expect["code"]).strip().upper() != got_code.upper():
        raise SymbolMismatchError(f"代码不符：请求 {expect['code']}，返回 {got_code}")
    if expect.get("setcode") is not None and int(expect["setcode"]) != got_sc:
        raise SymbolMismatchError(f"setcode 不符：请求 {expect['setcode']}，返回 {got_sc}")

    # Unit 需在定市场前读出（指数消歧要用），实际校验仍在 C4b
    _unit_raw = info.get("Unit")
    try:
        unit = float(_unit_raw) if _unit_raw is not None else None
    except (TypeError, ValueError):
        unit = None

    mk, _mnotes = _resolve_market(got_sc, unit, expect)
    warns.extend(_mnotes)
    if mk is None:
        raise UnsupportedMarketError(f"未知 setcode={got_sc}，无法确定市场规则")
    # ---- S6 补全：纵深防御。即便有人绕过 build_request 直接喂非空的美股/外汇原始 JSON，
    #      也在此处拦截，绝不默默处理不支持的市场（P1-7）。 ----
    if not mk.supported:
        raise UnsupportedMarketError(
            f"tdx-connector 不支持【{mk.label}】：{mk.note}。"
            f"→ 即便已取到数据也禁止处理，请改用兜底数据源或明确告知用户此品种暂不支持。")

    # --- C4 【P0-1 核心·语义防线】标的名校验 ---
    got_name = str(info.get("Name", "")).strip()
    if not got_name:
        raise SymbolMismatchError("AttachInfo.Name 为空，无法确认标的身份")
    exp_name = expect.get("name")
    if exp_name:
        ok, why = _name_matches(got_name, exp_name, mk)
        if not ok:
            raise SymbolMismatchError(
                f"警讯 标的不符！请求【{exp_name}】，实际返回【{got_name}】（{got_code}）。\n"
                f"   判定依据：{why}\n"
                f"   典型成因：target 未显式传，tdx 静默返回同代码 A 股。\n"
                f"   已拒绝出图 —— 若继续，将得到一份完全错误标的的分析。")
        if why:
            warns.append(f"标的名核对：{why}（请求【{exp_name}】/ 返回【{got_name}】）")
    else:
        warns.append(f"警讯 未提供 expect_name，语义防线关闭，仅靠 Unit 否定式校验兜底"
                     f"（当前返回【{got_name}】，请人工确认是否为目标标的）")

    # --- C4b 【P0-1 复查补·结构防线】Unit 交叉校验 ---
    # 错误样本实测：Code=00700、Setcode=31 全部与请求一致，只有 Name 与 Unit 露馅。
    # Unit 不依赖调用方是否记得传名字，是无人值守下的最后一道锁。
    # （unit 已在定市场前读出，见上方；此处只做校验）
    if unit is None:
        warns.append("AttachInfo.Unit 缺失，无法做量单位交叉校验")
    else:
        if (not mk.is_a_share) and abs(unit - 100) < 1e-9:
            raise SymbolMismatchError(
                f"警讯 数据疑似被替换为 A 股！请求市场【{mk.label}】(setcode={got_sc})，"
                f"但返回 Unit=100（A 股专有量纲），标的名【{got_name}】。\n"
                f"   典型成因：target 未显式传。请补 target 后重取。已拒绝出图。")
        if mk.unit_expect is not None and abs(unit - mk.unit_expect) > 1e-9:
            raise SymbolMismatchError(
                f"警讯 Unit 与市场不符！【{mk.label}】应为 Unit={mk.unit_expect}，"
                f"实际返回 Unit={unit}（标的【{got_name}】）。\n"
                f"   数据来源存疑，已拒绝出图。")

    # --- C4c 周期交叉校验（请求日线却返回周线会毁掉全部形态判定）---
    if expect.get("period") is not None and int(expect["period"]) != period:
        raise IntegrityError(
            f"周期不符：请求 {PERIODS.get(int(expect['period']), expect['period'])}"
            f"，返回 {PERIODS.get(period, period)}")

    # --- C5 逐行转 DataFrame ---
    def _req_f(r, i, key):
        """必需数值字段：缺失 / null / 非数 一律 IntegrityError，绝不 KeyError 崩栈。"""
        if key not in r or r[key] is None:
            raise IntegrityError(f"第 {i} 行缺少必需字段 '{key}'，数据不完整")
        try:
            v = float(r[key])
        except (TypeError, ValueError):
            raise IntegrityError(f"第 {i} 行字段 '{key}' 非数值：{r[key]!r}")
        if v != v:                                  # NaN
            raise IntegrityError(f"第 {i} 行字段 '{key}' 为 NaN")
        return v

    def _opt_f(r, *keys, default=0.0):
        """可选数值字段：任一可用即取，全不可用返回默认值。"""
        for k in keys:
            if r.get(k) is not None:
                try:
                    return float(r[k])
                except (TypeError, ValueError):
                    continue
        return default

    recs = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            raise IntegrityError(f"第 {i} 行结构异常（非对象）：{r!r}")
        try:
            d = pd.to_datetime(str(r["Data"]), format="%Y%m%d")
        except Exception as e:
            raise IntegrityError(f"第 {i} 行日期非法：{r.get('Data')!r}（{e}）")
        rec = {
            "date": d,
            "open":  _req_f(r, i, "Open"),  "high":  _req_f(r, i, "High"),
            "low":   _req_f(r, i, "Low"),   "close": _req_f(r, i, "Close"),
            "volume": _req_f(r, i, "Volume"),      # 已按 Unit 归一（含义见模块头）
            "raw_volume": _opt_f(r, "RawVolume"),
            "amount": _opt_f(r, "RawAmount", "Amount"),
        }
        if r.get("Settle") is not None:            # 期货结算价
            try:
                rec["settle"] = float(r["Settle"])
            except (TypeError, ValueError):
                pass
        recs.append(rec)

    df = pd.DataFrame(recs).set_index("date").sort_index()

    # --- C6 完整性 ---
    if df.index.has_duplicates:
        dup = df.index[df.index.duplicated()].strftime("%Y-%m-%d").tolist()
        raise IntegrityError(f"存在重复日期：{dup[:5]}")
    bad = df[(df.high < df[["open", "close", "low"]].max(axis=1) - 1e-6) |
             (df.low > df[["open", "close", "high"]].min(axis=1) + 1e-6)]
    if len(bad):
        raise IntegrityError(
            f"{len(bad)} 根 K 线 OHLC 逻辑错误（high<max 或 low>min），"
            f"首例 {bad.index[0].date()}")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise IntegrityError("存在非正价格")
    if (df.volume < 0).any():
        raise IntegrityError("存在负成交量")
    zero_vol = int((df.volume == 0).sum())
    if zero_vol:
        warns.append(f"{zero_vol} 根 K 线成交量为 0（停牌/无成交），形态判定需排除")

    # --- C7 【P1-10】最后一根是否收盘 ---
    hq_date, hq_time = str(info.get("HqDate", "")), str(info.get("HqTime", "")).zfill(6)
    closed = _bar_closed(df.index[-1], hq_date, hq_time, mk, period)
    if not closed:
        warns.append(
            f"警讯 最后一根（{df.index[-1].date()}）尚未收盘（行情时刻 {hq_time[:2]}:{hq_time[2:4]}）"
            f"，收盘价仍会变，形态判定失真 → 建议剔除或标注「未收盘」")

    # --- C8 【P1-9】窗口长度 ---
    if period == 4 and len(df) < 250:
        warns.append(f"仅 {len(df)} 根日线，窗口偏短：区间最高/最低/最大量可能是窗口边界值而非真实极值")

    # --- C9 【P0-2】复权声明 ---
    tq = int(expect.get("tq_flag", 1))
    if "tq_flag" not in expect:
        warns.append("未记录 tqFlag，默认按前复权处理 —— 图上价位可能与客户端盘面不符")

    meta = Meta(
        name=got_name, code=got_code, setcode=got_sc,
        market=mk.key, market_label=mk.label,
        period=period, period_label=PERIODS.get(period, str(period)),
        tq_flag=tq, adjust_label=TQ_LABEL.get(tq, "未知复权"),
        vol_unit=mk.vol_unit, bars=len(df),
        start=str(df.index[0].date()), end=str(df.index[-1].date()),
        hq_date=hq_date, hq_time=hq_time, last_bar_closed=closed,
        t_plus=mk.t_plus, price_limit=mk.price_limit, short_mode=mk.short_mode,
        snapshot=datetime.now().strftime("%Y-%m-%d %H:%M"),
        warnings=warns,
    )
    return df, meta


def _bar_closed(last_bar, hq_date: str, hq_time: str, mk: Market, period: int) -> bool:
    """最后一根 K 线是否已收盘。行情日期晚于该 K 线 → 必然收盘。"""
    try:
        hq_d = pd.to_datetime(hq_date, format="%Y%m%d")
    except Exception:
        return True                      # 拿不到行情时间，保守当已收盘并由 warning 提示
    if hq_d.date() > last_bar.date():
        return True
    if hq_d.date() < last_bar.date():
        return False
    try:
        hh, mm = int(hq_time[:2]), int(hq_time[2:4])
    except Exception:
        return True
    return time(hh, mm) >= time(mk.close_hhmm // 100, mk.close_hhmm % 100)


# ===================================================================
# 6. 文件入口
# ===================================================================

def load_and_validate(path: str | Path, req: dict | None = None
                      ) -> tuple[pd.DataFrame, Meta]:
    """从 Agent 落盘的原始 JSON 读取并校验。"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_kline_json(raw, (req or {}).get("expect"))


def drop_unclosed(df: pd.DataFrame, meta: Meta) -> tuple[pd.DataFrame, Meta]:
    """剔除未收盘的最后一根（形态判定前调用）。

    无副作用：返回新的 Meta 副本，不改调用方手里的对象（同 P2-1 教训）。
    同时清掉「尚未收盘」这条已经过时的警告，避免图上出现自相矛盾的两句话。
    """
    if meta.last_bar_closed or len(df) < 2:
        return df, meta
    df2 = df.iloc[:-1]
    m2 = replace(meta,
                 bars=len(df2),
                 end=str(df2.index[-1].date()),
                 last_bar_closed=True,
                 warnings=[w for w in meta.warnings if "尚未收盘" not in w] +
                          [f"已剔除未收盘的 {df.index[-1].date()}，分析截至 {df2.index[-1].date()}"])
    return df2, m2


# ===================================================================
# 7. 【P0-2】复权价 ↔ 盘面价换算
# ===================================================================

@dataclass
class AdjustBridge:
    """前复权价 ↔ 不复权（客户端盘面）价的换算桥。

    实测：茅台 2026-06-26 除息 28.02 元/股。
      06/25 收盘  前复权 1184.08  ↔  不复权 1212.10   （差 28.02）
      06/26 之后  两序列重合                          （差 0）

    两类风险要分开讲，别混为一谈：
      ① 挂单价风险 —— 只看**当前段** offset。若为 0，照图挂单无误。
      ② 形态错位风险 —— 只要区间内有除权日，客户端设为「不复权」时
         除权前那段 K 线整体高 max_offset 元，看图会与本图对不上。
      ③ 可复现性风险 —— 未来再分红，今天的前复权坐标会整体下移。
    """
    offset: float            # 当前段 offset = 不复权 - 前复权（最新一根）
    max_offset: float        # 区间内最大 offset（衡量历史段错位幅度）
    ex_dates: list           # 检测到的除权除息日
    span: tuple              # (起, 止)
    tq_label: str = "前复权"

    def to_board(self, p: float) -> float:
        """复权价 → 当前客户端盘面价"""
        return p + self.offset

    def dual(self, p: float, nd: int = 2) -> str:
        if abs(self.offset) < 1e-6:
            return f"{p:.{nd}f}"
        return f"{p:.{nd}f}（不复权盘面 {self.to_board(p):.{nd}f}）"

    def notice(self) -> str:
        if not self.ex_dates and abs(self.max_offset) < 1e-6:
            return f"区间 {self.span[0]}~{self.span[1]} 内无除权除息，复权价＝盘面价，可直接照图挂单。"
        parts = []
        if abs(self.offset) >= 1e-6:
            parts.append(f"警讯 挂单请注意：本图为{self.tq_label}坐标，"
                         f"当前段 offset ＝ {self.offset:+.2f} 元，"
                         f"客户端若为不复权，实际挂单价需按括号内盘面价。")
        else:
            parts.append(f"✔ 当前段 offset ＝ 0，图上价位可直接照单挂，无需换算。")
        if self.ex_dates:
            parts.append(f"但区间内有除权除息（{'、'.join(self.ex_dates)}），"
                         f"除权前 K 线在不复权坐标下整体高约 {self.max_offset:.2f} 元 —— "
                         f"请把客户端切到{self.tq_label}，否则形态位置对不上。")
        parts.append("另：前复权坐标会随日后每次分红整体下移，本图结论仅在当前快照下可复现。")
        return "　".join(parts)


def build_adjust_bridge(df_qfq: pd.DataFrame, df_raw: pd.DataFrame,
                        tol: float = 0.01) -> AdjustBridge:
    """比对前复权与不复权两份数据，定位除权日并算出 offset。

    用法：Agent 对同一标的分别用 tqFlag=1 / tqFlag=0 各取一次。
    """
    idx = df_qfq.index.intersection(df_raw.index)
    if len(idx) < 2:
        raise DataError("两份数据重叠不足，无法建立复权换算")
    diff = (df_raw.loc[idx, "close"] - df_qfq.loc[idx, "close"]).round(4)
    ex_dates = [str(d.date()) for d, ch in
                zip(idx[1:], diff.values[1:] - diff.values[:-1]) if abs(ch) > tol]
    return AdjustBridge(
        offset=round(float(diff.iloc[-1]), 4),
        max_offset=round(float(diff.abs().max()), 4),
        ex_dates=ex_dates,
        span=(str(idx[0].date()), str(idx[-1].date())),
    )


# ===================================================================
# 8. 制度约束（供 S3 的 C2 自动注入）
# ===================================================================

def regime(meta: Meta) -> dict:
    return {
        "market": meta.market_label,
        "t_plus": f"T+{meta.t_plus}",
        "price_limit": meta.price_limit,
        "short": meta.short_mode,
        "vol_unit": meta.vol_unit,
    }


def preflight(meta: Meta) -> list[str]:
    """出图前置检查清单，返回阻断项（非空即禁止出图）。"""
    blocks = []
    if meta.bars < 30:
        blocks.append(f"仅 {meta.bars} 根 K 线，不足以判定形态（至少 30 根）")
    if not meta.last_bar_closed:
        blocks.append("最后一根未收盘，请先 drop_unclosed() 或显式标注")
    return blocks
