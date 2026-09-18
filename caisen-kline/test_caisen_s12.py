#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔡森 K 线分析 · S12 大周期定位 专项 + 对抗测试（脚本式，sys.exit 汇总）
======================================================================
锁死 S12 行为，防日后回退：
  S12-A 顺势：日线多 + 周线上升 → tf_aligned=True、不降级、note 含「同向」。
  S12-B 逆势：日线多 + 周线下降 → tf_aligned=False、置信度降一级、
        note 含「逆向」「反弹」，且措辞为「下跌中继的反弹」。
  S12-C 震荡（真实样本 600718）：tf_aligned=None、不降级、note 含「无大方向背书」。
  S12-D 数据不足（周线 <20 根）：tf_trend=「数据不足」、aligned=None、不降级、不崩。
  S12-E down 对称：镜像样本方向与措辞全部翻转（「上涨中继的回调」）。
  S12-F 真实回归：600460 逆势降级结论稳定；build_levels 仍 6 条；出图不崩。
  S12-G 文案进图：结构判定块含「大周期（S12）」，逆势须带「警讯」。
  S12-H 重采样正确性：OHLCV 聚合 = first/max/min/last/sum，月线 ME 兼容旧版 pandas。
  S12-I 不双重惩罚：置信度已「低」时逆势不报错、不越界。

用法：python3 test_caisen_s12.py
"""
import sys
import json
import pandas as pd

from caisen_ab import analyze, ABParams, resample_tf, tf_trend_of
from caisen_narrative import build_levels, build_text_blocks
from caisen_data import parse_kline_json
from caisen_pipeline import run

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


def _synth(n, gen):
    rows = []
    for i in range(n):
        o, h, l, c, v = gen(i)
        d = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)
        rows.append(dict(date=d, open=o, high=h, low=l, close=c, volume=v))
    return pd.DataFrame(rows).set_index("date").sort_index()


def flip_up_to_down(df_up, M=400.0):
    rows = []
    for idx, r in df_up.iterrows():
        rows.append(dict(date=idx, open=M - r["open"], high=M - r["low"],
                         low=M - r["high"], close=M - r["close"], volume=r["volume"]))
    return pd.DataFrame(rows).set_index("date").sort_index()


def _bar(c):
    return c - 0.5, max(c - 0.5, c) + 1.0, min(c - 0.5, c) - 1.0, c


def long_trend_then_w(start, slope, base):
    """前 130 根单边趋势 → 紧凑 W 底(30 根) → 突破。

    形态刻意压缩到 30 根，好让周 MA10（覆盖最近 70 日）仍由长期趋势主导，
    从而可控地造出「日线突破 vs 周线反向」的逆势场景。
    """
    def gen(i):
        if i < 130:
            c = start + i * slope
        elif i < 135:
            c = base - (i - 130) * 1.0
        elif i < 140:
            c = (base - 5) + (i - 135) * 1.0
        elif i < 145:
            c = base - (i - 140) * 1.0
        elif i < 150:
            c = (base - 5) + (i - 145) * 1.0
        else:
            c = base + (i - 150) * 1.0
        v = 3000.0 if 150 <= i <= 156 else 1000.0
        o, h, l, c = _bar(c)
        return o, h, l, c, v
    return gen


print("【S12-A 顺势：日线多 + 周线上升 → 同向、不降级】")
# 长期陡涨 100→280，末端紧凑 W 后再突破 → 周线仍上升
dfA = _synth(160, long_trend_then_w(100.0, (280.0 - 100.0) / 130.0, 280.0))
sA = analyze(dfA, ABParams())
check("顺势样本被识别为 up", sA.ok and sA.direction == "up",
      f"reason={sA.reason} dir={sA.direction}")
if sA.ok:
    check("周线判为上升", sA.tf_trend == "上升",
          f"tf={sA.tf_trend} close={sA.tf_close} ma={sA.tf_ma} bars={sA.tf_bars}")
    check("tf_aligned=True（顺势）", sA.tf_aligned is True, f"aligned={sA.tf_aligned}")
    check("顺势 note 含『同向』", any("大周期" in n and "同向" in n for n in sA.notes))
    check("顺势 note 不含『警讯』", not any("大周期" in n and "警讯" in n for n in sA.notes))
    leftA, _ = build_text_blocks(sA, None, df=dfA)
    check("结构判定块含『大周期（S12）』", "大周期（S12）" in leftA)
    check("顺势文案标『顺势（同向）』", "顺势（同向）" in leftA)

print("【S12-B 逆势：日线多 + 周线下降 → 降一级 + 反弹定性】")
# 长期陡跌 300→120，末端紧凑 W 后突破 → 周收仍低于周MA10 且 MA 下行
dfB = _synth(160, long_trend_then_w(300.0, (120.0 - 300.0) / 130.0, 120.0))
sB = analyze(dfB, ABParams())
check("逆势样本被识别为 up", sB.ok and sB.direction == "up",
      f"reason={sB.reason} dir={sB.direction}")
if sB.ok:
    check("周线判为下降", sB.tf_trend == "下降",
          f"tf={sB.tf_trend} close={sB.tf_close} ma={sB.tf_ma} bars={sB.tf_bars}")
    check("tf_aligned=False（逆势）", sB.tf_aligned is False, f"aligned={sB.tf_aligned}")
    check("逆势置信度不得为「高」（已降一级）", sB.confidence != "高", f"conf={sB.confidence}")
    nB = [n for n in sB.notes if "大周期" in n]
    check("逆势 note 含『警讯』+『逆向』",
          bool(nB) and "警讯" in nB[0] and "逆向" in nB[0], f"note={nB[0] if nB else None}")
    check("逆势 up 定性为『下跌中继的反弹』",
          bool(nB) and "下跌中继的反弹" in nB[0], f"note={nB[0] if nB else None}")
    check("逆势明确『目标②不宜期待』", bool(nB) and "目标②不宜期待" in nB[0])
    leftB, _ = build_text_blocks(sB, None, df=dfB)
    check("逆势提示进图(左栏可见)", "大周期" in leftB and "逆势" in leftB)

print("【S12-C 震荡（真实样本 600718）→ 不降级、只提示】")
raw718 = json.load(open("data/raw/600718_d4_tq1.json", encoding="utf-8"))
df718, _m718 = parse_kline_json(raw718, {"code": "600718", "name": "东软集团",
                                         "market": "CN_SH"})
sC = analyze(df718, ABParams())
check("600718 被识别", sC.ok, f"reason={sC.reason}")
if sC.ok:
    check("600718 周线判为震荡", sC.tf_trend == "震荡",
          f"tf={sC.tf_trend} close={sC.tf_close} ma={sC.tf_ma}")
    check("震荡时 tf_aligned=None（不表态）", sC.tf_aligned is None, f"a={sC.tf_aligned}")
    check("震荡 note 含『无大方向背书』",
          any("大周期" in n and "无大方向背书" in n for n in sC.notes))
    check("震荡 note 不含『警讯』", not any("大周期" in n and "警讯" in n for n in sC.notes))

print("【S12-D 数据不足（周线<20 根）→ 不判、不降级、不崩】")
dfD = _synth(80, long_trend_then_w(100.0, (116.0 - 100.0) / 130.0, 116.0))  # 80 日历日 ≈ 12 周
sD = analyze(dfD, ABParams())
check("短样本不崩", True)
if sD.ok:
    check("周线数据不足时 tf_trend=『数据不足』", sD.tf_trend == "数据不足",
          f"tf={sD.tf_trend} bars={sD.tf_bars}")
    check("数据不足时 aligned=None（不表态）", sD.tf_aligned is None)
    check("数据不足 note 提示仓位从严",
          any("大周期" in n and "仓位从严" in n for n in sD.notes))

print("【S12-E down 对称：镜像样本方向与措辞全部翻转】")
dfE1 = flip_up_to_down(dfA)      # 原顺势多头 → 顺势空头（周线下降 + 日线空）
sE1 = analyze(dfE1, ABParams())
check("镜像顺势样本为 down", sE1.ok and sE1.direction == "down",
      f"reason={sE1.reason} dir={sE1.direction}")
if sE1.ok:
    check("down 顺势：周线下降且 aligned=True",
          sE1.tf_trend == "下降" and sE1.tf_aligned is True,
          f"tf={sE1.tf_trend} a={sE1.tf_aligned}")

dfE2 = flip_up_to_down(dfB)      # 原逆势多头 → 逆势空头（周线上升 + 日线空）
sE2 = analyze(dfE2, ABParams())
check("镜像逆势样本为 down", sE2.ok and sE2.direction == "down",
      f"reason={sE2.reason} dir={sE2.direction}")
if sE2.ok:
    check("down 逆势：周线上升且 aligned=False",
          sE2.tf_trend == "上升" and sE2.tf_aligned is False,
          f"tf={sE2.tf_trend} a={sE2.tf_aligned}")
    nE = [n for n in sE2.notes if "大周期" in n]
    check("down 逆势定性为『上涨中继的回调』（不是反弹）",
          bool(nE) and "上涨中继的回调" in nE[0] and "下跌中继" not in nE[0],
          f"note={nE[0] if nE else None}")

print("【S12-F 真实回归：600460 逆势结论稳定 + 出图不崩】")
raw460 = json.load(open("data/raw/600460_d4_tq1.json", encoding="utf-8"))
df460, _m460 = parse_kline_json(raw460, {"code": "600460", "name": "士兰微",
                                         "market": "CN_SH"})
sF = analyze(df460, ABParams())
check("600460 识别", sF.ok, f"reason={sF.reason}")
if sF.ok:
    check("600460 周线下降 + 日线多 → 逆势",
          sF.tf_trend == "下降" and sF.tf_aligned is False,
          f"tf={sF.tf_trend} a={sF.tf_aligned}")
    check("600460 月线同步下降", sF.tf_month_trend == "下降", f"mo={sF.tf_month_trend}")
    lvF = build_levels(sF, None)
    check("build_levels 仍 6 条(不破坏 S3)", len(lvF) == 6, f"len={len(lvF)}")
    resF = run(raw460, query="600460", expect_name="士兰微", market_hint="CN_SH",
               period=4, out_dir="/tmp", dpi=80)
    check("600460 出图不崩", resF.get("png") is not None)

print("【S12-G 文案：逆势必须带警讯，顺势不得带】")
if sF.ok:
    leftF, _ = build_text_blocks(sF, None, df=df460)
    check("600460 结构判定含大周期行", "大周期（S12）" in leftF)
    check("600460 逆势标『警讯·逆势』", "警讯·逆势" in leftF)

print("【S12-H 重采样正确性：OHLCV 聚合 + 月线兼容】")
dfH = _synth(14, lambda i: (100.0 + i, 100.0 + i + 2, 100.0 + i - 2, 100.0 + i, 500.0))
wkH = resample_tf(dfH, "W")
check("周线重采样非空", len(wkH) > 0, f"len={len(wkH)}")
if len(wkH) > 0:
    first_wk = wkH.iloc[0]
    # 2025-01-01 是周三 → 首个自然周只含 1/1~1/5 共 5 根（i=0..4）
    check("open=区间首根", abs(first_wk["open"] - 100.0) < 1e-6, f"o={first_wk['open']}")
    check("close=区间末根", abs(first_wk["close"] - 104.0) < 1e-6, f"c={first_wk['close']}")
    check("high=区间最大", abs(first_wk["high"] - 106.0) < 1e-6, f"h={first_wk['high']}")
    check("low=区间最小", abs(first_wk["low"] - 98.0) < 1e-6, f"l={first_wk['low']}")
    check("volume=区间累加", abs(first_wk["volume"] - 2500.0) < 1e-6, f"v={first_wk['volume']}")
moH = resample_tf(dfH, "ME")
check("月线重采样兼容当前 pandas（不抛异常）", len(moH) >= 1, f"len={len(moH)}")
t, ma, c, bars = tf_trend_of(wkH)
check("周线不足 20 根 → 返回『数据不足』", t == "数据不足", f"t={t} bars={bars}")

print("【S12-I 不双重惩罚：conf 已『低』时逆势不越界、不报错】")
if sF.ok:
    check("600460（已破位 conf=低）仍能正常产出", sF.confidence in ("低", "中", "高"),
          f"conf={sF.confidence}")
    check("逆势降级不会产生非法置信度",
          all(x.confidence in ("低", "中", "高")
              for x in [sA, sB, sC, sF] if x.ok))

print(f"\nS12 专项+对抗结果：通过 {PASS} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
