#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔡森 K 线分析 · S11 套牢区检测 专项 + 对抗测试（脚本式，sys.exit 汇总）
====================================================================
锁死 S11 行为，防日后回退：
  S11-A 有套牢区且目标②落入：trapped_zone 非空、trapped_at_t2=True、
        置信度软降级（不得为「高」）、notes 含「套牢区」且进图、目标②条目带 band。
  S11-B 无密集堆积（clean，全程均量）：不误触发、无「套牢区」误提示。
        —— 首版漏洞：mean_v 含空桶被稀释，导致任何横盘都误罚。
  S11-C 现价逼近套牢区外沿（trapped_near）：触发提示，且目标②不在区内时 at_t2=False。
  S11-D down 方向对称：镜像样本堆积区在下方，目标②落入 → 等价降级。
  S11-E 真实样本回归：600460 仍 ok、build_levels 仍 6 条、出图不崩。
  S11-F 边界：历史不足 40 根 → 不检测、不崩（早突破样本）。
  S11-G 措辞方向感知：down 的 near 提示须写「上沿」而非「下沿」（S10 同款坑）。
  S11-H 未触发不画带：目标②条目 band 必须为 None（不在图上凭空多一条橙带）。

用法：python3 test_caisen_s11.py
"""
import sys
import json
import pandas as pd

from caisen_ab import analyze, ABParams
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


def flip_up_to_down(df_up, M=200.0):
    rows = []
    for idx, r in df_up.iterrows():
        rows.append(dict(date=idx, open=M - r["open"], high=M - r["low"],
                         low=M - r["high"], close=M - r["close"], volume=r["volume"]))
    return pd.DataFrame(rows).set_index("date").sort_index()


def _bar(c):
    return c - 0.5, max(c - 0.5, c) + 1.0, min(c - 0.5, c) - 1.0, c


# ---- 共用骨架：前高 top_px 横盘堆积 → 跌到 95 → W 底(颈线≈102/底≈93.5) → 突破 ----
def w_shape(top_px, heavy, slope_post):
    """heavy=True 前高段放巨量(套牢盘)；False 则全程均量(clean 对照)。"""
    def gen(i):
        if i < 15:
            c = top_px + (i % 2) * 0.5
        elif i < 25:
            c = top_px - (i - 15) * ((top_px - 95.0) / 10.0)
        elif i < 35:
            c = 95 + (i - 25) * 0.5
        elif i < 45:
            c = 100 - (i - 35) * 0.5
        elif i < 55:
            c = 95 + (i - 45) * 0.5
        else:
            c = 100 + (i - 55) * slope_post
        if heavy:
            v = 5000.0 if i < 15 else (3000.0 if 55 <= i <= 61 else 1000.0)
        else:
            v = 1000.0
        o, h, l, c = _bar(c)
        return o, h, l, c, v
    return gen


print("【S11-A 有套牢区且目标②落入 → 降级+提示+可视化】")
dfA = _synth(80, w_shape(119.0, True, 1.0))     # 前高堆积 119，t2≈119 落入
sA = analyze(dfA, ABParams())
check("w_trapped 被识别", sA.ok, f"reason={sA.reason}")
if sA.ok:
    check("套牢区被检出 trapped_zone 非空", sA.trapped_zone is not None,
          f"zone={sA.trapped_zone}")
    check("目标②落入套牢区 trapped_at_t2=True", sA.trapped_at_t2 is True,
          f"t2={sA.target2} zone={sA.trapped_zone}")
    check("套牢区量占比被记录 >0", sA.trapped_vol_pct > 0,
          f"pct={sA.trapped_vol_pct}")
    check("触发套牢区后置信度不得为「高」(软降级)", sA.confidence != "高",
          f"conf={sA.confidence}")
    check("notes 含『套牢区』提示", any("套牢区" in x for x in sA.notes),
          f"notes={sA.notes}")
    leftA, _ = build_text_blocks(sA, None, df=dfA)
    check("套牢区提示进图(左栏可见)", "套牢区" in leftA)
    lvA = build_levels(sA, None)
    check("build_levels 仍 6 条(不破坏 S3)", len(lvA) == 6, f"len={len(lvA)}")
    t2A = lvA[0]
    check("目标②条目带 band(套牢区可视化)", t2A.get("band") is not None,
          f"band={t2A.get('band')}")
    check("套牢区带色为橙色压力色", t2A.get("band_c") == "#ef6c00",
          f"band_c={t2A.get('band_c')}")
    check("目标②文案标注套牢区", "套牢区" in t2A.get("txt", ""))

print("【S11-B 无密集堆积（clean 全程均量）→ 不误罚】")
dfB = _synth(80, w_shape(119.0, False, 1.0))
sB = analyze(dfB, ABParams())
check("w_clean 被识别", sB.ok, f"reason={sB.reason}")
if sB.ok:
    no_trap = (sB.trapped_zone is None) or (not sB.trapped_at_t2 and not sB.trapped_near)
    check("clean 样本不误触发套牢区降级", no_trap,
          f"zone={sB.trapped_zone} at_t2={sB.trapped_at_t2} near={sB.trapped_near}")
    check("clean 样本无『套牢区』误提示", not any("套牢区" in x for x in sB.notes),
          f"notes={sB.notes}")

print("【S11-C 现价逼近套牢区外沿（trapped_near）→ 触发且目标②不在区内】")
dfC = _synth(80, w_shape(110.0, True, 0.42))    # 堆积 110，t2≈119 在区外，现价停 110
sC = analyze(dfC, ABParams())
check("w_near 被识别", sC.ok, f"reason={sC.reason}")
if sC.ok:
    check("套牢区检出", sC.trapped_zone is not None, f"zone={sC.trapped_zone}")
    check("trapped_near 触发(现价贴套牢区)", sC.trapped_near is True,
          f"near={sC.trapped_near} zone={sC.trapped_zone} last={sC.last_close}")
    check("目标②在区外时 at_t2=False(不虚报)", sC.trapped_at_t2 is False,
          f"t2={sC.target2} zone={sC.trapped_zone}")
    check("trapped_near 场景 notes 含『套牢区』", any("套牢区" in x for x in sC.notes))
    nearC = [x for x in sC.notes if "逼近" in x]
    check("up 措辞为『下沿』", bool(nearC) and "下沿" in nearC[0],
          f"note={nearC[0] if nearC else None}")

print("【S11-D down 方向对称：镜像样本堆积区在下方，目标②落入→等价降级】")
dfD = flip_up_to_down(dfA)
sD = analyze(dfD, ABParams())
check("down 镜像样本被识别且为 down", sD.ok and sD.direction == "down",
      f"reason={sD.reason} dir={sD.direction}")
if sD.ok:
    check("down 套牢区检出", sD.trapped_zone is not None, f"zone={sD.trapped_zone}")
    check("down 目标②落入套牢区", sD.trapped_at_t2 is True,
          f"t2={sD.target2} zone={sD.trapped_zone}")
    check("down 触发后置信度不得为「高」", sD.confidence != "高", f"conf={sD.confidence}")
    check("down notes 含『套牢区』", any("套牢区" in x for x in sD.notes))
    check("down 措辞为『下方密集成交区』而非『前高』",
          any("下方密集成交区" in x for x in sD.notes),
          f"notes={[x for x in sD.notes if '套牢区' in x]}")

print("【S11-E 真实样本回归：600460 不崩不误罚】")
raw = json.load(open("data/raw/600460_d4_tq1.json", encoding="utf-8"))
df_r, meta_r = parse_kline_json(raw, {"code": "600460", "name": "士兰微", "market": "CN_SH"})
sE = analyze(df_r, ABParams())
check("600460 识别", sE.ok, f"reason={sE.reason}")
if sE.ok:
    lvE = build_levels(sE, None)
    check("600460 build_levels 返回 6 条(不破坏 S3)", len(lvE) == 6, f"len={len(lvE)}")
    res = run(raw, query="600460", expect_name="士兰微", market_hint="CN_SH",
              period=4, out_dir="/tmp", dpi=80)
    check("600460 出图不崩", res.get("png") is not None)

print("【S11-F 边界：历史不足 40 根 → 不检测、不崩】")
dfF = _synth(46, w_shape(119.0, True, 1.0))     # 突破前历史 < 40
sF = analyze(dfF, ABParams())
check("短样本不崩(有无信号均可)", True)
if sF.ok:
    check("短样本不做套牢区检测", sF.trapped_zone is None, f"zone={sF.trapped_zone}")

print("【S11-G down 的 near 措辞方向感知（须『上沿』）】")
dfG = flip_up_to_down(_synth(80, w_shape(110.0, True, 0.42)))
sG = analyze(dfG, ABParams())
if sG.ok and sG.trapped_near:
    nearG = [x for x in sG.notes if "逼近" in x]
    check("down 措辞为『上沿』而非『下沿』",
          bool(nearG) and "上沿" in nearG[0] and "下沿" not in nearG[0],
          f"note={nearG[0] if nearG else None}")
else:
    check("down near 样本成立", False, f"ok={sG.ok} near={getattr(sG,'trapped_near',None)}")

print("【S11-H 未触发不画带：目标②条目 band 必须 None】")
if sB.ok:
    lvB = build_levels(sB, None)
    check("clean 样本目标②无 band", lvB[0].get("band") is None,
          f"band={lvB[0].get('band')}")
    check("clean 样本目标②文案无套牢区字样", "套牢区" not in lvB[0].get("txt", ""))

print(f"\nS11 专项+对抗结果：通过 {PASS} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
