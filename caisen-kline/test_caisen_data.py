#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""caisen_data.py 自检 —— 每条用例都对应 AUDIT 里的一个实测缺陷。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import caisen_data as cd

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw"

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f"\n      {detail}" if detail else ""))


def expect_raise(name, exc, fn, *a, **kw):
    try:
        fn(*a, **kw)
        check(name, False, "预期抛错但没抛 —— 防线失效！")
    except exc as e:
        check(name, True, f"已拦截：{str(e).splitlines()[0][:78]}")
    except Exception as e:
        check(name, False, f"抛了 {type(e).__name__}（预期 {exc.__name__}）：{e}")


print("=" * 74)
print("【1】请求构造 —— 修 P0-1 强制 target / P0-2 显式 tqFlag")
print("=" * 74)

r = cd.build_request("600519", "CN_SH", expect_name="贵州茅台", want_num=300)
check("A股 target='0'", r["tool_args"]["target"] == "0", str(r["tool_args"]))
check("tqFlag 显式带上", "tqFlag" in r["tool_args"])

r_hk = cd.build_request("00700", "HK", expect_name="腾讯控股")
check("港股 target='1'（不传会返回A股模塑科技）",
      r_hk["tool_args"]["target"] == "1" and r_hk["tool_args"]["setcode"] == "31")

r_fut = cd.build_request("RB2610", "FUT_SHFE", expect_name="螺纹2610")
check("期货 target='1'（不传直接返空）", r_fut["tool_args"]["target"] == "1")

check("代码推断：00700→港股", cd._guess_market("00700", None).key == "HK")
check("代码推断：600519→沪A", cd._guess_market("600519", None).key == "CN_SH")

expect_raise("美股拒发请求（P1-7 覆盖缺口）", cd.UnsupportedMarketError,
             cd.build_request, "DLTR", "US")
expect_raise("外汇拒发请求（P1-7 覆盖缺口）", cd.UnsupportedMarketError,
             cd.build_request, "EURUSD", "FX")
expect_raise("无法推断市场时拒绝", cd.UnsupportedMarketError,
             cd.build_request, "XYZ123", None)
# ---- S6 补全：美股/外汇代码一步说清暂不支持，不误导"请传 market" ----
expect_raise("美股代码一眼认出暂不支持", cd.UnsupportedMarketError,
             cd._guess_market, "AAPL", None)
expect_raise("外汇代码一眼认出暂不支持", cd.UnsupportedMarketError,
             cd._guess_market, "EURUSD", None)
expect_raise("setcode 与市场不符", cd.DataError,
             cd.build_request, "600519", "CN_SH", setcode=31)
expect_raise("wantNum 越界", cd.DataError,
             cd.build_request, "600519", "CN_SH", want_num=2000)

print()
print("=" * 74)
print("【2】真实样本解析 —— 茅台 / 腾讯（tdx 实测原文）")
print("=" * 74)

df_mt, m_mt = cd.load_and_validate(RAW / "600519_d3_tq1.json",
                                   cd.build_request("600519", "CN_SH", expect_name="贵州茅台"))
check("茅台解析成功", m_mt.name == "贵州茅台" and len(df_mt) == 3,
      f"{m_mt.title()}｜{m_mt.bars}根｜{m_mt.start}~{m_mt.end}")
check("A股量单位=手", m_mt.vol_unit == "手",
      f"08/03 量 {df_mt['volume'].iloc[-1]:.2f} 手 = RawVolume {df_mt['raw_volume'].iloc[-1]:.0f} 股 / 100")
check("复权标注=前复权", m_mt.adjust_label == "前复权")
check("A股制度：T+1 + 10%涨跌停 + 禁开空",
      m_mt.t_plus == 1 and "10%" in m_mt.price_limit and "禁止开空" in m_mt.short_mode)
check("15:30 行情 → 判定已收盘", m_mt.last_bar_closed is True,
      f"HqTime={m_mt.hq_time}")

df_hk, m_hk = cd.load_and_validate(RAW / "00700_d3_tq1.json",
                                   cd.build_request("00700", "HK", expect_name="腾讯控股"))
check("腾讯解析成功（target=1 生效）", m_hk.name == "腾讯控股")
check("港股量单位=股（与A股相反！）", m_hk.vol_unit == "股",
      f"08/03 量 {df_hk['volume'].iloc[-1]:,.0f} 股 = RawVolume {df_hk['raw_volume'].iloc[-1]:.0f} 手 / 0.01")
check("港股制度：T+0 + 无涨跌停 + 可做空需确认",
      m_hk.t_plus == 0 and "无涨跌停" in m_hk.price_limit and "需独立确认" in m_hk.short_mode)

print()
print("=" * 74)
print("【3】★ P0-1 静默错标的拦截（最危险的那条）")
print("=" * 74)

wrong = json.loads((RAW / "00700_d3_NO_TARGET_wrong.json").read_text(encoding="utf-8"))
print(f"  样本：请求港股 00700，tdx 实际返回【{wrong['AttachInfo']['Name']}】"
      f" 现价 {wrong['AttachInfo']['Now']}（A股 000700）")
expect_raise("★ 拦截「模塑科技冒充腾讯」", cd.SymbolMismatchError,
             cd.parse_kline_json, wrong,
             cd.build_request("00700", "HK", expect_name="腾讯控股")["expect"])

print(f"  注意：该样本 Code={wrong['Code']}、Setcode={wrong['Setcode']} 与请求**完全一致**，"
      f"只有 Name 和 Unit={wrong['AttachInfo']['Unit']} 露馅")

# ★ 复查新增：Agent 忘传 expect_name 是最现实的失守路径，必须双保险
expect_raise("★ 未传 expect_name 时拒绝构造请求（防线不可选）", cd.DataError,
             cd.build_request, "00700", "HK")
expect_raise("★ 即便关掉语义防线，Unit=100 否定式校验仍拦住（港股不该是A股量纲）",
             cd.SymbolMismatchError, cd.parse_kline_json, wrong,
             {"code": "00700", "setcode": 31})
expect_raise("★ Unit 与市场不符拦截（港股应 0.01）", cd.SymbolMismatchError,
             cd.parse_kline_json,
             {**wrong, "AttachInfo": {**wrong["AttachInfo"], "Name": "腾讯控股", "Unit": 100}},
             {"code": "00700", "setcode": 31, "name": "腾讯控股"})

good_mt = json.loads((RAW / "600519_d3_tq1.json").read_text(encoding="utf-8"))
expect_raise("代码不符拦截", cd.SymbolMismatchError, cd.parse_kline_json,
             good_mt, {"code": "000001", "setcode": 1, "name": "平安银行"})
expect_raise("★ 名称含数字差异拒绝放行（东方财富 ≠ 东方财富转3）", cd.SymbolMismatchError,
             cd.parse_kline_json,
             {**good_mt, "AttachInfo": {**good_mt["AttachInfo"], "Name": "东方财富转3"}},
             {"code": "600519", "setcode": 1, "name": "东方财富"})
_ok, _why = cd._name_matches("螺纹2610", "螺纹", cd.MARKETS["FUT_SHFE"])
check("期货合约月份差异应放行（螺纹 vs 螺纹2610）", _ok, _why)
_df_sn, _m_sn = cd.parse_kline_json(good_mt, {"code": "600519", "setcode": 1, "name": "茅台"})
check("简称匹配放行但留痕（茅台 vs 贵州茅台）",
      any("简称/全称" in w for w in _m_sn.warnings),
      [w for w in _m_sn.warnings if "简称" in w][0][:70])

print()
print("=" * 74)
print("【4】★ P0-2 复权换算（照图挂单会错 28 元的那条）")
print("=" * 74)

req0 = cd.build_request("600519", "CN_SH", expect_name="贵州茅台", tq_flag=0)
df_raw30, m_raw = cd.load_and_validate(RAW / "600519_d30_tq0.json", req0)
check("不复权数据解析成功", m_raw.adjust_label == "不复权", f"{m_raw.bars} 根")

req1 = cd.build_request("600519", "CN_SH", expect_name="贵州茅台", tq_flag=1)
df_qfq30, _ = cd.load_and_validate(RAW / "600519_d30_tq1.json", req1)

br = cd.build_adjust_bridge(df_qfq30, df_raw30)
check("检出除权除息日 2026-06-26", "2026-06-26" in br.ex_dates, f"ex_dates={br.ex_dates}")
check("offset ≈ 0（06/26 之后两序列已重合）", abs(br.offset) < 0.01, f"offset={br.offset}")

# 历史段（除权日之前）的换算才是关键
hist = cd.build_adjust_bridge(df_qfq30.loc[:"2026-06-25"], df_raw30.loc[:"2026-06-25"])
check("★ 除权前 offset = 28.02（每股派息）", abs(hist.offset - 28.02) < 0.05,
      f"offset={hist.offset}　→ 前复权颈线 1265 ↔ 客户端盘面 {hist.to_board(1265):.2f}")
check("双栏价位输出", "不复权盘面" in hist.dual(1265.0), hist.dual(1265.0))
check("★ 全区间：当前段 offset=0 仍提示历史形态错位",
      "当前段 offset ＝ 0" in br.notice() and "2026-06-26" in br.notice()
      and f"{br.max_offset:.2f}" in br.notice(),
      f"max_offset={br.max_offset}")
check("提示可复现性风险（未来分红会漂移）", "整体下移" in br.notice())
print("      ── 全区间提示语 ──")
print(f"      {br.notice()}")
print("      ── 历史段提示语 ──")
print(f"      {hist.notice()}")

print()
print("=" * 74)
print("【5】完整性校验 + 未收盘处理")
print("=" * 74)

base = json.loads((RAW / "600519_d3_tq1.json").read_text(encoding="utf-8"))


def mutate(fn):
    d = json.loads(json.dumps(base))
    fn(d)
    return d


expect_raise("空 Rows 拦截（美股就栽这）", cd.EmptyDataError,
             cd.parse_kline_json, mutate(lambda d: d.__setitem__("Rows", [])), None)
# ---- S6 补全：US 覆盖缺口的两条拒绝路径都要锁死 ----
expect_raise("★ US 空 Rows → EmptyDataError（带美股提示）", cd.EmptyDataError,
             cd.parse_kline_json,
             mutate(lambda d: (d.__setitem__("Setcode", 74), d.__setitem__("Rows", []))), None)
expect_raise("★ 非空美股原始 JSON 绕过 build_request 也被拒（纵深防御）", cd.UnsupportedMarketError,
             cd.parse_kline_json, mutate(lambda d: d.__setitem__("Setcode", 74)), None)
expect_raise("OHLC 逻辑错误拦截", cd.IntegrityError, cd.parse_kline_json,
             mutate(lambda d: d["Rows"][1].__setitem__("High", "1.0")), None)
expect_raise("重复日期拦截", cd.IntegrityError, cd.parse_kline_json,
             mutate(lambda d: d["Rows"][1].__setitem__("Data", d["Rows"][0]["Data"])), None)
expect_raise("负成交量拦截", cd.IntegrityError, cd.parse_kline_json,
             mutate(lambda d: d["Rows"][1].__setitem__("Volume", -5)), None)
expect_raise("缺字段拦截", cd.IntegrityError, cd.parse_kline_json,
             mutate(lambda d: d.pop("AttachInfo")), None)

mid = mutate(lambda d: d["AttachInfo"].__setitem__("HqTime", "103000"))
df_m, meta_m = cd.parse_kline_json(mid, {"code": "600519", "setcode": 1,
                                         "name": "贵州茅台", "tq_flag": 1})
check("★ 盘中 10:30 → 判定未收盘", meta_m.last_bar_closed is False,
      [w for w in meta_m.warnings if "未收盘" in w][0][:70])
check("preflight 阻断未收盘出图", any("未收盘" in b for b in cd.preflight(meta_m)))
df_c, meta_c = cd.drop_unclosed(df_m, meta_m)
check("drop_unclosed 剔除末根", len(df_c) == len(df_m) - 1 and meta_c.last_bar_closed,
      f"{len(df_m)} → {len(df_c)} 根，分析截至 {meta_c.end}")
check("窗口过短告警（P1-9）", any("窗口偏短" in w for w in m_mt.warnings))
check("★ drop_unclosed 清掉过时的「尚未收盘」警告（不自相矛盾）",
      not any("尚未收盘" in w for w in meta_c.warnings),
      f"剩余 {len(meta_c.warnings)} 条警告")
check("★ drop_unclosed 无副作用（不污染调用方的 meta）",
      meta_c is not meta_m and meta_m.last_bar_closed is False,
      f"原对象 last_bar_closed 仍为 {meta_m.last_bar_closed}")

print()
print("=" * 74)
print("【5b】★ 复查补测：结构缺陷必须抛 DataError，不许 KeyError/TypeError 崩栈")
print("=" * 74)

expect_raise("顶层缺 Period", cd.IntegrityError, cd.parse_kline_json,
             mutate(lambda d: d.pop("Period")), None)
for _k in ("Open", "High", "Low", "Close", "Volume"):
    expect_raise(f"行内缺 {_k}", cd.IntegrityError, cd.parse_kline_json,
                 mutate(lambda d, k=_k: [r.pop(k, None) for r in d["Rows"]]), None)
    expect_raise(f"行内 {_k} 为 null", cd.IntegrityError, cd.parse_kline_json,
                 mutate(lambda d, k=_k: [r.__setitem__(k, None) for r in d["Rows"]]), None)
_df_na, _ = cd.parse_kline_json(
    mutate(lambda d: [r.__setitem__("RawAmount", None) for r in d["Rows"]]),
    {"code": "600519", "setcode": 1, "name": "贵州茅台"})
check("可选字段 RawAmount=null 不崩（降级取 Amount）", len(_df_na) == 3,
      f"amount 首值 {_df_na['amount'].iloc[0]:,.0f}")
expect_raise("请求日线却返回周线 → 拦截", cd.IntegrityError, cd.parse_kline_json,
             mutate(lambda d: d.__setitem__("Period", 5)),
             cd.build_request("600519", "CN_SH", expect_name="贵州茅台", period=4)["expect"])
expect_raise("空 code 拒绝构造请求", cd.DataError, cd.build_request, "", "CN_SH")
_hint = cd.build_request("600519", "CN_SH", expect_name="贵州茅台", want_num=100)["hints"]
check("wantNum<250 给出窗口偏短提示（不再是空 pass）",
      any("偏小" in h for h in _hint), _hint[0][:70] if _hint else "无")

print()
print("=" * 74)
print("【7】D1-D5 跨品种覆盖 —— 7 类真标的实测暴露，逐条钉死")
print("=" * 74)

# ---------- D1：深市 setcode=0 被 JSON 省略 ----------
def sz_sample():
    """把茅台夹具改造成深市样本：Setcode 键整个消失（与平安银行/宁德时代实测一致）。"""
    return mutate(lambda d: (d.pop("Setcode", None),
                             d.__setitem__("Code", "000001"),
                             d["AttachInfo"].__setitem__("Name", "平安银行")))


_df_sz, _m_sz = cd.parse_kline_json(
    sz_sample(), {"code": "000001", "setcode": 0, "name": "平安银行", "market": "CN_SZ"})
check("D1 深市 Setcode 键缺失 → 按请求回填 0（深市主板+创业板不再全线不可用）",
      _m_sz.setcode == 0 and _m_sz.market == "CN_SZ", _m_sz.market_label)
check("D1 回填必须留痕，不默默改数据",
      any("回填" in w for w in _m_sz.warnings),
      next((w for w in _m_sz.warnings if "回填" in w), "无"))
expect_raise("D1 只补 0：声明 setcode=1 却缺键仍报错（不给伪造 setcode 开口子）",
             cd.IntegrityError, cd.parse_kline_json, sz_sample(),
             {"code": "000001", "setcode": 1, "name": "平安银行"})
expect_raise("D1 无 expect 时缺键照样报错", cd.IntegrityError,
             cd.parse_kline_json, sz_sample(), None)
expect_raise("D1 Setcode 键在但值为 null → 报错而非裸崩 TypeError",
             cd.IntegrityError, cd.parse_kline_json,
             mutate(lambda d: d.__setitem__("Setcode", None)), None)
expect_raise("D1 Rows 键整个缺失 → 归入空数据（比'缺字段'准确）", cd.EmptyDataError,
             cd.parse_kline_json, mutate(lambda d: d.pop("Rows")), None)

# ---------- D2：指数与 A 股共用 setcode，靠 Unit 消歧 ----------
_idx = mutate(lambda d: (d.__setitem__("Code", "000001"),
                         d["AttachInfo"].__setitem__("Name", "上证指数"),
                         d["AttachInfo"].__setitem__("Unit", 1)))
_df_ix, _m_ix = cd.parse_kline_json(
    _idx, {"code": "000001", "setcode": 1, "name": "上证指数"})
check("D2 setcode=1 且 Unit=1 → 判为中国指数（此前一律被 Unit 校验拒收）",
      _m_ix.market == "INDEX_CN" and _m_ix.vol_unit == "点",
      f"{_m_ix.market_label} / 量单位 {_m_ix.vol_unit}")
check("D2 消歧结果进 warnings（含'指数不可直接交易'提示）",
      any("指数" in w for w in _m_ix.warnings),
      next((w for w in _m_ix.warnings if "指数" in w), "无")[:70])
_df_ix2, _m_ix2 = cd.parse_kline_json(
    _idx, {"code": "000001", "setcode": 1, "name": "上证指数", "market": "CN_SH"})
check("D2 调用方误标成 CN_SH，Unit=1 仍纠偏为指数", _m_ix2.market == "INDEX_CN")
check("D2 反查表剔除 ambiguous 市场，setcode 0/1 仍稳定指向 A 股",
      cd.SETCODE2MARKET[1].key == "CN_SH" and cd.SETCODE2MARKET[0].key == "CN_SZ",
      f"1→{cd.SETCODE2MARKET[1].key}　0→{cd.SETCODE2MARKET[0].key}")
check("D2 深证系指数 399xxx 默认 setcode=0、上证系=1（否则发错市场）",
      cd._default_setcode(cd.MARKETS["INDEX_CN"], "399001") == 0
      and cd._default_setcode(cd.MARKETS["INDEX_CN"], "000300") == 1)

# ---------- D3：ETF / 期货 代码前缀推断 ----------
def _g(c):
    return cd._guess_market(c, None).key


for _code, _want in [("510300", "ETF_SH"), ("588000", "ETF_SH"), ("159915", "ETF_SZ"),
                     ("399001", "INDEX_CN"), ("RB2610", "FUT_SHFE"), ("m2509", "FUT_DCE"),
                     ("MA2601", "FUT_CZCE"), ("600718", "CN_SH"), ("000001", "CN_SZ"),
                     ("300750", "CN_SZ"), ("00700", "HK"),
                     # 广期所 2026-09-20 实测通过，setcode=66，从"拒绝"移入"正常推断"
                     ("SI2610", "FUT_GFEX"), ("lc2609", "FUT_GFEX"), ("PS2701", "FUT_GFEX")]:
    _got = _g(_code)
    check(f"D3 {_code} → {_want}", _got == _want, "" if _got == _want else f"实得 {_got}")
expect_raise("D3 未登记的期货品种 → 报错，不乱猜交易所",
             cd.UnsupportedMarketError, cd._guess_market, "ZZ2601", None)
for _code, _ex in [("IF2512", "中金所"), ("SC2601", "上期能源")]:
    expect_raise(f"D3 {_code}（{_ex}）未覆盖 → 构造请求阶段即拒（不误导'补个 market 就行'）",
                 cd.UnsupportedMarketError, cd.build_request, _code, expect_name="x")

# D3b：广期所已放行 —— 必须能正常构造请求且 setcode=66
_gf_req = cd.build_request("SI2610", "FUT_GFEX", expect_name="工业硅2610")
check("D3b 广期所 setcode=66", str(_gf_req["tool_args"]["setcode"]) == "66",
      str(_gf_req["tool_args"]["setcode"]))
check("D3b 广期所 market 识别", _gf_req["expect"]["market"] == "FUT_GFEX",
      str(_gf_req["expect"].get("market")))
check("D3b 广期所 target=1（非沪深京）", _gf_req["tool_args"]["target"] == "1",
      str(_gf_req["tool_args"]["target"]))
check("D3b 广期所 tool 指向 tdx_kline", _gf_req["tool"].endswith("tdx_kline"),
      _gf_req["tool"])
_gf_mk = cd.MARKETS["FUT_GFEX"]
check("D3b 广期所 supported=True", _gf_mk.supported is True, str(_gf_mk.supported))
check("D3b setcode 反查表 66 → 广期所",
      cd.SETCODE2MARKET.get(66) is _gf_mk, str(cd.SETCODE2MARKET.get(66)))
# 不带 market 也应能从代码自动推断到广期所
_gf_auto = cd.build_request("SI2610", expect_name="工业硅2610")
check("D3b 广期所 免传 market 自动推断", _gf_auto["expect"]["market"] == "FUT_GFEX",
      str(_gf_auto["expect"].get("market")))
check("D3b 广期所 自动推断 setcode 仍为 66",
      str(_gf_auto["tool_args"]["setcode"]) == "66", str(_gf_auto["tool_args"]["setcode"]))

_etf = mutate(lambda d: (d.__setitem__("Code", "510300"),
                         d["AttachInfo"].__setitem__("Name", "沪深300ETF华泰柏瑞")))
_df_e, _m_e = cd.parse_kline_json(
    _etf, cd.build_request("510300", expect_name="沪深300ETF华泰柏瑞")["expect"])
check("D3 ETF 与沪市A股完全同构(setcode=1/Unit=100) → 只能靠 expect.market 命中",
      _m_e.market == "ETF_SH", _m_e.market_label)
check("D3 ETF 的做空规则不照抄 A 股禁空", "可融券" in _m_e.short_mode, _m_e.short_mode)

# ---------- D5：整包 req 喂进来时四道语义校验被架空 ----------
_req_ok = cd.build_request("600519", "CN_SH", expect_name="贵州茅台")
_req_bad = cd.build_request("600519", "CN_SH", expect_name="五粮液")
_df_d5, _m_d5 = cd.parse_kline_json(base, _req_ok)          # 整包 req
check("D5 整包 req 仍能正常解析（向后兼容）", _m_d5.name == "贵州茅台")
expect_raise("D5★ 整包 req + 错名 → 必须拦（修复前四道校验全部静默跳过）",
             cd.SymbolMismatchError, cd.parse_kline_json, base, _req_bad)
expect_raise("D5 整包 req + 错周期 → 必须拦", cd.IntegrityError, cd.parse_kline_json,
             mutate(lambda d: d.__setitem__("Period", 5)), _req_ok)

print()
print("=" * 74)
print("【6】footer 合规 —— 每张图必带")
print("=" * 74)
f = m_mt.footer()
print("  " + f)
for kw in ("通达信", "前复权", "快照", "蔡森", "手", "不构成任何投资建议"):
    check(f"footer 含「{kw}」", kw in f)

print()
print("=" * 74)
print(f"结果：通过 {len(PASS)} / 失败 {len(FAIL)}")
if FAIL:
    print("失败项：" + "、".join(FAIL))
print("=" * 74)
sys.exit(1 if FAIL else 0)
