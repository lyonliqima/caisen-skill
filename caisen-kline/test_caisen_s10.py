#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔡森 K 线分析 · S10 颈线对齐 专项测试（脚本式，sys.exit 汇总）
==============================================================
锁死 S10 颈线带对齐行为，防日后回退：
  S10-A 颈线带记录：pattern 成立时 neck_band=(lo,hi)/neck_width 必须记录且 width>0。
  S10-B 突破须脱离可见颈线带远边：仅过中位未脱离上沿 → clear_band=False、
        置信度软封顶(高→中)、提示「未脱离颈线带上沿」。
        脱离上沿 → clear_band=True、不误罚。
  S10-C 图表：build_levels 须含 band 条目；render_signal 带 band 不崩、出图成功。

用法：python3 test_caisen_s10.py
"""
import json
import sys
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


def w_band(slope_post):
    """颈线触点拉宽到 ~99–101（中位 100），突破后按 slope_post 缓/陡升。
    slope 小 → 突破收盘落在带内(未脱离上沿)；slope 大 → 突破收盘远超带上沿。"""
    def gen(i):
        if i < 20:
            c = 100 - i * 1.0
        elif i < 30:
            c = 80 + (i - 20) * 1.8          # 峰 ~98
        elif i < 40:
            c = 98 - (i - 30) * 2.0          # 回落到 78
        elif i < 50:
            c = 78 + (i - 40) * 1.7          # 峰 ~95
        else:
            c = 95 + (i - 50) * slope_post    # 突破段：slope 决定是否脱离带上沿
        v = 3000.0 if 50 <= i <= 56 else 1000.0
        return c - 0.5, max(c - 0.5, c) + 1.0, min(c - 0.5, c) - 1.0, c, v
    return gen


print("【S10-A 颈线带记录】")
# 真实夹具：颈线带必须记录且 width>0
raw = json.load(open("data/raw/600460_d4_tq1.json", encoding="utf-8"))
df_r, meta_r = parse_kline_json(raw, {"code": "600460", "name": "士兰微", "market": "CN_SH"})
s_r = analyze(df_r, ABParams())
check("600460 颈线带记录且 width>0", s_r.ok and s_r.neck_width > 0
      and len(s_r.neck_band) == 2 and s_r.neck_band[0] < s_r.neck_band[1],
      f"band={s_r.neck_band} width={s_r.neck_width}")
# 真实紧颈线带：突破已脱离上沿，不应误罚
check("600460 紧带已脱离上沿 clear_band=True", s_r.clear_band is True)

print("【S10-B 突破未脱离颈线带 → 软封顶+提示】")
s_slow = analyze(_synth(80, w_band(1.0)), ABParams())   # 缓升：突破落在带内
check("宽带合成样本被识别", s_slow.ok, f"reason={s_slow.reason}")
if s_slow.ok:
    lo, hi = s_slow.neck_band
    check("宽颈线带 width 明显>0", s_slow.neck_width > 1.0, f"width={s_slow.neck_width}")
    check("突破未脱离上沿 clear_band=False", s_slow.clear_band is False,
          f"close={s_slow.breakout['close']:.2f} hi={hi}")
    # 缓升时若本可给高，须被封顶为「中」
    check("未脱离上沿置信度被封顶(≤中)", s_slow.confidence in ("中", "低"),
          f"conf={s_slow.confidence}")
    left_slow, _ = build_text_blocks(s_slow, None, df=_synth(80, w_band(1.0)))
    check("提示含「未脱离颈线带上沿」", "未脱离颈线带上沿" in left_slow)

print("【S10-B 突破脱离颈线带 → 不误罚】")
s_fast = analyze(_synth(80, w_band(3.5)), ABParams())   # 陡升：突破远超带上沿
check("陡升宽带有样本被识别", s_fast.ok, f"reason={s_fast.reason}")
if s_fast.ok:
    lo, hi = s_fast.neck_band
    check("陡升突破脱离上沿 clear_band=True", s_fast.clear_band is True,
          f"close={s_fast.breakout['close']:.2f} hi={hi}")
    # 脱离上沿不应触发「未脱离颈线带」提示
    left_fast, _ = build_text_blocks(s_fast, None, df=_synth(80, w_band(3.5)))
    check("脱离上沿不误出颈线带提示", "未脱离颈线带上沿" not in left_fast)

print("【S10-C 图表带区】")
lv = build_levels(s_slow, None)
check("build_levels 含 band 条目", any("band" in d for d in lv))
# 带 band 渲染不崩、出图成功
res = run(raw, query="600460", expect_name="士兰微", market_hint="CN_SH",
          period=4, out_dir="/tmp", dpi=80)
check("带 band 渲染出图成功", res.get("png") and __import__("os").path.exists(res["png"]),
      f"png={res.get('png')}")

print(f"\n结果：通过 {PASS} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
