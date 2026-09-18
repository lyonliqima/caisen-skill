#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔡森 K 线分析 · S9 方法论修正专项测试（脚本式，sys.exit 汇总）
==============================================================
锁死 S9 三处修正行为，防日后回退：

  S9-A 量能封顶：无量突破（vol_confirm=False）不得给「高」；缩量(<1.0×)封「低」。
  S9-B 破位降级：现价大幅跌破颈线 → broken=True、置信度「低」、目标位置灰失效。
  S9-C 现价 R:R：风险报酬段必须并列「按现价进场」的真实风报比。

用法：python3 test_caisen_s9.py
"""
import json
import sys

from caisen_ab import analyze
from caisen_data import parse_kline_json
from caisen_narrative import build_text_blocks, build_levels

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {extra}")


def load(code, fn=None):
    fn = fn or f"{code}_d4_tq1.json"
    raw = json.load(open(f"data/raw/{fn}", encoding="utf-8"))
    df, meta = parse_kline_json(
        raw, {"code": code, "name": raw.get("AttachInfo", {}).get("Name", ""),
              "market": "CN_SH" if code.startswith("6") else "CN_SZ"})
    return df, meta


def sig_of(code, fn=None):
    df, meta = load(code, fn)
    return analyze(df), meta, df


print("【S9-A 量能封顶】")
# 600718 突破量 0.9×（缩量）→ 封顶「低」，且不得给「高」
s718, m718, _ = sig_of("600718")
check("600718 突破量未确认(vol_confirm=False)", s718.breakout
      and s718.breakout["vol_confirm"] is False,
      f"vol_confirm={s718.breakout.get('vol_confirm') if s718.breakout else None}")
check("600718 置信度被封顶为「低」", s718.confidence == "低",
      f"conf={s718.confidence}")
check("600718 不得出现「高」置信度", s718.confidence != "高")
left718, _ = build_text_blocks(s718, m718, df=load("600718")[0])
check("600718 文案出现量能封顶警讯", ("量能未确认" in left718) or ("假突破嫌疑" in left718))

print("【S9-B 破位降级】")
# 600460 现价 28.47 跌破颈线 38.95 约 27% → 破位
s460, m460, df460 = sig_of("600460")
check("600460 判为破位 broken=True", s460.broken is True, f"broken={s460.broken}")
check("600460 破位幅度≈27%", abs(s460.broken_pct - 0.269) < 0.01,
      f"broken_pct={s460.broken_pct:.3f}")
check("600460 破位后置信度降「低」", s460.confidence == "低", f"conf={s460.confidence}")
left460, _ = build_text_blocks(s460, m460, df=df460)
check("600460 文案出现「已破位」", "已破位" in left460)
# S13-B 修正：600460 突破后曾达目标①（实际最高 57.02 > 目标①）→ 形态已走完，
# 破位属「完成后回撤」，不再误称「形态失败」。旧断言已被 S13 取代。
check("600460 形态已完成(曾达目标①)", s460.completed is True,
      f"completed={getattr(s460, 'completed', None)}")
check("600460 方向标注带「已破位·完成后回撤」", "已破位·完成后回撤" in left460)
# 出图层级：破位时目标线/颈线/停损应置灰且标注失效
lv = build_levels(s460, m460)
tgt_color = [d["c"] for d in lv if d["y"] == s460.target1][0]
neck_txt = [d["txt"] for d in lv if d["y"] == s460.neckline][0]
check("600460 目标线置灰(#9e9e9e)", tgt_color == "#9e9e9e", f"color={tgt_color}")
check("600460 颈线标注「已破位·结构转弱」", "已破位·结构转弱" in neck_txt)

print("【S9-C 现价 R:R 并列】")
check("600460 风险报酬段含「现价 R:R」", "现价 R:R" in left460)
# 现价 ≤ 停损 → 应明确「先离场/风报比为负」
check("600460 现价已破位提示离场", ("应先离场" in left460) or ("无意义" in left460))
# 600718 未破位但有现价 R:R（介于停损与目标①之间）
check("600718 风险报酬段含「现价 R:R」", "现价 R:R" in left718)

print("【S9 不得误伤正常带量突破】")
# 600460 突破量 1.74× 已确认，仅因破位降级，不该触发量能封顶文案
check("600460 不出现量能封顶误判", ("量能未确认" not in left460) and ("假突破嫌疑" not in left460))

print(f"\n结果：通过 {PASS} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
