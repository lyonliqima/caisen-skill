# -*- coding: utf-8 -*-
# D6：QDII 跨境 ETF（setcode=33 / Unit=1）放行契约
#   513130 恒生科技ETF 在 tdx 体系里归为基金段 setcode=33、Unit=1，
#   与股票型 ETF（510300 等 setcode=1/Unit=100）不同。
#   修复前 ETF_SH.setcodes=(1,)/unit_expect=100 会把这类标的整体拒绝。
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from caisen_data import build_request, parse_kline_json

FAIL = 0
def check(cond, msg):
    global FAIL
    print(("  ✅ " if cond else "  ❌ "), msg)
    if not cond: FAIL += 1

# 1) build_request 不抛，市场命中 ETF_SH
try:
    req = build_request("513130", market="ETF_SH",
                        expect_name="恒生科技ETF华泰柏瑞", setcode=33)
    check(req["expect"]["market"] == "ETF_SH", f"D6 market=ETF_SH (got {req['expect']['market']})")
    check(req["expect"]["setcode"] == 33, "D6 setcode=33 传递无误")
    print("  ✅ D6 build_request 未抛异常")
except Exception as e:
    check(False, f"D6 build_request 抛异常: {e}")

# 2) 构造 513130 真实形态 raw（Setcode=33 / Unit=1 / Name 匹配）→ parse 放行
raw = {
    "Setcode": 33, "Code": "513130", "Period": 4,
    "AttachInfo": {"Name": "恒生科技ETF华泰柏瑞", "Unit": 1,
                   "HqDate": "20260805", "HqTime": "150000"},
    "Rows": [{"Data": "20260805", "Second": "0", "Open": "0.6184",
              "High": "0.6184", "Low": "0.6184", "Close": "0.6184",
              "Amount": 0, "VolInStock": "0", "Volume": 0, "Settle": "0",
              "up": "0", "down": "0", "RawVolume": 0, "Unit": 1, "RawAmount": 0}],
}
try:
    df, meta = parse_kline_json(raw, req["expect"])
    check(meta.market == "ETF_SH", f"D6 parse 市场=ETF_SH (got {meta.market})")
    check(meta.vol_unit == "手", "D6 vol_unit=手")
    print("  ✅ D6 parse_kline_json 对 QDII ETF(Unit=1) 放行，未拒绝出图")
except Exception as e:
    check(False, f"D6 parse 拒绝 QDII ETF: {e}")

# 3) 否定校验：同名但实际是港股（Unit=0.01）应被名称防线拦（非 Unit 漏过）
raw_bad = dict(raw)
raw_bad["AttachInfo"] = {"Name": "模塑科技", "Unit": 0.01,
                         "HqDate": "20260805", "HqTime": "150000"}
try:
    parse_kline_json(raw_bad, req["expect"])
    check(False, "D6 港股伪装未被拦（名称防线失效）")
except Exception:
    print("  ✅ D6 名称不符仍被拦，语义防线有效")

print(f"\nD6 结果：{'通过' if FAIL == 0 else '失败 ' + str(FAIL)}")
sys.exit(1 if FAIL else 0)
