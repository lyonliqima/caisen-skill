#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔡森 K 线分析 · S13 专项测试（脚本式，sys.exit 汇总）
=====================================================
锁死 S13 两处修正，防日后回退：

  S13-A 形态极点窗口：形态底须在「完整基底」内找，不能只从颈线首触点起。
      W底/头肩底的第二谷常早于颈线首触点，旧窗口把它切在外面 →
      H 与等幅目标系统性偏小（600460：取 31.74 而非真实双谷 24.62）。

  S13-B 形态完成度判别：破位时先问「形态走完没有」——
      曾达目标① 再回落 = 完成后回撤（获利回吐/反转），不是假突破；
      从未达目标① 就回落 = 假突破失败。
      旧版一律写「形态可能失败」，误导（600460 形态其实已超额兑现）。

用法：python3 test_caisen_s13.py
"""
import json
import sys

import pandas as pd

sys.path.insert(0, ".")
from caisen_ab import analyze
from caisen_data import parse_kline_json
from caisen_narrative import build_text_blocks

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


# ----------------------------------------------------------------------
# 合成构造器：W底 → 放量突破 → 冲到 peak → 回落到 drop
# peak 高于等幅目标① = 形态已走完；peak 低于目标① = 从未兑现
# ----------------------------------------------------------------------
def _synth(n, gen):
    rows = []
    for i in range(n):
        o, h, l, c, v = gen(i)
        d = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)
        rows.append({"date": d, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return pd.DataFrame(rows).set_index("date").sort_index()


def _w_then(peak, drop, n=80):
    """i<20 下跌 → 20-30 反弹(颈线触点1) → 30-40 谷2(更低) → 40-50 回颈线(触点2)
    → 50 放量突破 → 50-60 冲到 peak → 60-80 回落到 drop"""

    def gen(i):
        if i < 20:
            c = 100.0 - i * 1.0
        elif i < 30:
            c = 81.0 + (i - 20) * 1.4
        elif i < 40:
            c = 95.0 - (i - 30) * 1.7
        elif i < 50:
            c = 78.0 + (i - 40) * 1.7
        elif i < 60:
            c = 95.0 + (i - 50) * ((peak - 95.0) / 10.0)
        else:
            c = peak - (i - 60) * ((peak - drop) / max(n - 60, 1))
        o = c - 0.4
        h = max(o, c) + 1.0
        l = min(o, c) - 1.0
        v = 3500.0 if i == 50 else 1000.0
        return o, h, l, c, v

    return _synth(n, gen)


def _w_late(peak, drop, n=95, rise_end=70):
    """同 _w_then，但把回落推迟到突破后 FAIL_WINDOW(15) 根之外。

    S5 假突破翻转只扫 [bi+1, bi+1+15)，跌破若发生在该窗口内 → 走翻转路径；
    要让 S9-B 的「未达标回撤」分支被覆盖，跌破必须落在窗口之后。
    """
    def gen(i):
        if i < 20:
            c = 100.0 - i * 1.0
        elif i < 30:
            c = 81.0 + (i - 20) * 1.4
        elif i < 40:
            c = 95.0 - (i - 30) * 1.7
        elif i < 50:
            c = 78.0 + (i - 40) * 1.7
        elif i < rise_end:
            c = 95.0 + (i - 50) * ((peak - 95.0) / (rise_end - 50))
        else:
            c = peak - (i - rise_end) * ((peak - drop) / max(n - rise_end, 1))
        o = c - 0.4
        h = max(o, c) + 1.0
        l = min(o, c) - 1.0
        v = 3500.0 if i == 50 else 1000.0
        return o, h, l, c, v

    return _synth(n, gen)


# ======================================================================
print("【S13-A 形态极点窗口：H 须取真实形态底】")
# 600460 实证：W底双谷 03-24(25.44)/04-03(24.62)，颈线 38.95。
# 旧窗口从颈线首触点起 → 取 31.74，H≈7.2、目标①≈46.15（实际到过 57.02，目标偏小）。
# 修后应取到真实谷区 → H≈14.3、目标①≈53.3。
df460, m460 = load("600460")
s460 = analyze(df460)
print(f"     实测：颈线={s460.neckline:.2f} 形态底={s460.extreme['price']:.2f} "
      f"H={s460.height:.2f} 目标①={s460.target1:.2f} 目标②={s460.target2:.2f}")
check("600460 形态底取到真实谷区(<26，非 31.74)", s460.extreme["price"] < 26.0,
      f"形态底={s460.extreme['price']:.2f}")
check("600460 形态高度 H 显著放大(>13)", s460.height > 13.0, f"H={s460.height:.2f}")
check("600460 等幅目标① 上修(>50，旧值 46.15)", s460.target1 > 50.0,
      f"目标①={s460.target1:.2f}")
check("600460 H = |颈线 - 形态底|（自洽）",
      abs(s460.height - abs(s460.neckline - s460.extreme["price"])) < 0.01,
      f"H={s460.height:.2f} vs {abs(s460.neckline - s460.extreme['price']):.2f}")

# ======================================================================
print("\n【S13-B 分支一：曾达目标① → 完成后回撤（非假突破）】")
# 突破后冲到 130（> 目标①≈111.7），再跌回 85（跌破颈线 95 约 10%）
sA = analyze(_w_then(peak=130.0, drop=85.0))
print(f"     实测：颈线={sA.neckline:.2f} 目标①={sA.target1:.2f} "
      f"completed={sA.completed} 达阵日={sA.completed_at} "
      f"突破后最高={sA.extreme_after:.2f} kind={sA.retrace_kind!r}")
check("A 形态已判定完成(completed=True)", sA.completed is True,
      f"completed={sA.completed}")
check("A 记录了达标日期", bool(sA.completed_at), f"completed_at={sA.completed_at!r}")
check("A 突破后极值 ≥ 目标①", sA.extreme_after >= sA.target1,
      f"extreme_after={sA.extreme_after:.2f} t1={sA.target1:.2f}")
check("A 已破位(broken=True)", sA.broken is True, f"broken={sA.broken}")
check("A 定性为「完成后回撤」", sA.retrace_kind == "完成后回撤",
      f"retrace_kind={sA.retrace_kind!r}")
_a_notes = " ".join(sA.notes)
check("A notes 含「完成后回撤」", "完成后回撤" in _a_notes)
check("A notes 不得称「形态失败」", "形态失败" not in _a_notes,
      "出现『形态失败』即为 S13 回退")
leftA, _ = build_text_blocks(sA, None, df=None)
check("A 方向标注为「已破位·完成后回撤」", "已破位·完成后回撤" in leftA)

# ======================================================================
print("\n【S13-B 分支二：从未达目标① → 假突破失败（S9-B 未达标回撤）】")
# 突破后只冲到 100（< 目标①≈111.7），且跌破发生在 S5 回验窗口之外 → 走 S9-B 路径
# 参数约束（踩过的坑，勿随意改）：
#   ① 回落不得跌破形态底(78)，否则 _recent_extreme_i 会把「后半段最低点」钉在末尾，
#      bi 从此之后再无上穿候选 → 整段无信号；
#   ② n=78 使后半段起点 = 谷2 位置(39)，形态底才落在后半段内被取为 ext_i；
#   ③ 跌破须发生在突破后 15 根(S5 回验窗口)之外，否则走 S5 翻转而非 S9-B 破位。
sB = analyze(_w_late(peak=102.0, drop=88.0, n=78, rise_end=66))
print(f"     实测：颈线={sB.neckline:.2f} 目标①={sB.target1:.2f} "
      f"completed={sB.completed} 突破后最高={sB.extreme_after:.2f} "
      f"kind={sB.retrace_kind!r}")
check("B 形态未完成(completed=False)", sB.completed is False,
      f"completed={sB.completed}")
check("B 突破后极值 < 目标①", sB.extreme_after < sB.target1,
      f"extreme_after={sB.extreme_after:.2f} t1={sB.target1:.2f}")
check("B 已破位(broken=True)", sB.broken is True, f"broken={sB.broken}")
check("B 定性为「未达标回撤」", sB.retrace_kind == "未达标回撤",
      f"retrace_kind={sB.retrace_kind!r}")
_b_notes = " ".join(sB.notes)
check("B notes 判为假突破失败", ("假突破" in _b_notes) and ("形态失败" in _b_notes),
      "未达标破位必须判假突破失败")
leftB, _ = build_text_blocks(sB, None, df=None)
check("B 方向标注为「已破位·形态失败」", "已破位·形态失败" in leftB)

# ======================================================================
print("\n【S13-C 不误伤：健康突破（未破位）不得乱标回撤】")
# 突破后持续上行，现价仍在颈线之上 → 不该有破位措辞
sC = analyze(_w_then(peak=120.0, drop=112.0, n=70))
print(f"     实测：颈线={sC.neckline:.2f} 现价={sC.last_close:.2f} "
      f"broken={sC.broken} completed={sC.completed} kind={sC.retrace_kind!r}")
check("C 未破位(broken=False)", sC.broken is False, f"broken={sC.broken}")
check("C 无回撤定性(retrace_kind 为空)", sC.retrace_kind == "",
      f"retrace_kind={sC.retrace_kind!r}")
_c_notes = " ".join(sC.notes)
check("C 不出现「已破位」措辞", "已破位" not in _c_notes)
check("C 方向为多头", sC.direction == "up", f"dir={sC.direction}")

# ======================================================================
print("\n【S13-D S5 翻转路径：原形态完成度须随反转信号传递（不得丢字段）】")
# 突破后仅冲到 100（< 目标①）且 15 根内跌回颈线 → S5 判「假突破」翻空。
# 此前 build_reversal_signal 重建信号时漏传 S13 字段（extreme_after 变 0.00），
# 导致「已完成反转 vs 典型假突破」的诊断信息丢失 → 此处锁死。
sD = analyze(_w_then(peak=100.0, drop=85.0))
print(f"     实测：方向={sD.direction} 失败类型={sD.failure_type!r} "
      f"completed={sD.completed} 原形态突破后最高={sD.extreme_after:.2f}")
check("D 走 S5 翻转路径(方向翻空)", sD.direction == "down", f"dir={sD.direction}")
check("D 失败类型为假突破", "假突破" in (sD.failure_type or ""),
      f"failure_type={sD.failure_type!r}")
check("D 原形态未完成(completed=False)", sD.completed is False,
      f"completed={sD.completed}")
check("D 突破后极值已传递(≠0，修复前为 0.00)", sD.extreme_after > 0,
      f"extreme_after={sD.extreme_after:.2f}")
_d_notes = " ".join(sD.notes)
check("D notes 给出「典型假突破」定性", "典型假突破" in _d_notes)

print("\n" + "=" * 70)
print(f"结果：通过 {PASS} / 失败 {FAIL}")
print("=" * 70)
sys.exit(1 if FAIL else 0)
