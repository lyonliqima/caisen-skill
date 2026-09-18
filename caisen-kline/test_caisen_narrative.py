#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S3 文案自动生成 + C1–C4 强制注入 自检。
覆盖：
  N1 文字副图左右栏结构齐全（一~五块）
  N2 C1–C4 必带，且 C2 按市场分支（A股禁空 / 期货可空）
  N3 levels/events 由信号自动生成，非空
  N4 独立 Markdown 报告含 C1–C4
  N5 数字全部来自 ABSignal（不出现无意义硬编码）
"""
import os
import sys
import tempfile
from types import SimpleNamespace
sys.path.insert(0, ".")
import pandas as pd
from caisen_ab import analyze, ABParams
from caisen_narrative import (build_text_blocks, build_levels, build_events,
                              build_report, render_signal, c2_text, c1c4_block)


HERE = os.path.dirname(os.path.abspath(__file__))
# 测试产物一律写临时目录，**不得写进技能目录**（否则会在用户机器上留 1.3MB 垃圾，
# 且打包时被误收进发行包——2026-09-11 实测踩过）。
TMP = tempfile.mkdtemp(prefix="caisen_test_narrative_")


def _load_maotai():
    df = pd.read_csv(os.path.join(HERE, "data", "600519_daily.csv"), parse_dates=["date"]).set_index("date")
    return df.rename(columns={"vol": "volume"}).astype(float)


def _meta(market_label, short_mode, t_plus=1, price_limit="10%", vol_unit="手"):
    return SimpleNamespace(name="测试标的", code="X", market_label=market_label,
                           short_mode=short_mode, t_plus=t_plus, price_limit=price_limit,
                           vol_unit=vol_unit)


def _make_df(closes):
    n = len(closes)
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    recs = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        hi = max(o, c) + 1.0
        lo = min(o, c) - 1.0
        recs.append(dict(date=dates[i], open=o, high=hi, low=lo, close=c,
                         volume=1000 + (i % 5) * 100))
    return pd.DataFrame(recs).set_index("date").sort_index()


def _build_mtop(n=100):
    """合成 M 头（空头），供真实 down 信号端到端测试。"""
    cl = [100.0] * n
    for i in range(0, 20):
        cl[i] = 100.0 + (130 - 100) * (i / 19)
    cl[20] = 130.0
    for i in range(21, 35):
        cl[i] = 130.0 - (130 - 110) * ((i - 20) / 15)
    cl[35] = 110.0
    for i in range(36, 50):
        cl[i] = 110.0 + (130 - 110) * ((i - 35) / 15)
    cl[50] = 130.0
    for i in range(51, 70):
        cl[i] = 130.0 - (130 - 90) * ((i - 50) / 19)
    cl[70] = 90.0
    for i in range(71, n):
        cl[i] = 90.0 + (i - 70) * 0.1
    return _make_df(cl)


PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")


print("=== S3 文案自动生成 + C1–C4 ===")
df = _load_maotai()
sig = analyze(df, ABParams())
assert sig.ok, sig.reason

# N1 结构齐全
left, right = build_text_blocks(sig, _meta("上交所A股", "禁止开空（融券极难）→ 只作减仓/离场/避险"))
check("N1 左栏含 一/二/三 块", all(k in left for k in ["【一、结构判定】", "【二、关键价位一览】", "【三、风险报酬"]),
      f"len_left={len(left)}")
check("N1 右栏含 四/五 块", all(k in right for k in ["【四、论据·量价结构（G 招）】", "【五、强制约束 C1–C4"]),
      f"len_right={len(right)}")
check("N1 文字来自信号(颈线值出现在文案)", f"{sig.neckline:.0f}" in left,
      f"neckline={sig.neckline:.0f}")

# N2 C1–C4 必带 + C2 市场分支
a_share_meta = _meta("上交所A股", "禁止开空（融券极难）→ 只作减仓/离场/避险")
block = c1c4_block(sig, a_share_meta)
check("N2 C1–C4 四段齐全", all(k in block for k in ["C1", "C2", "C3", "C4"]))

# 空头信号：验证 C2 按市场分支（用 down 假信号，与茅台 up 信号解耦）
down_sig = SimpleNamespace(direction="down", confidence="中", stop_pct=0.05,
                           neckline=100.0, extreme={"price": 90.0}, last_close=98.0,
                           target1=80.0, target2=70.0, stop=95.0, entry=100.0, rr=2.0,
                           pattern="M 头", pattern_basis="测试", height=10.0,
                           neck_touches=[], notes=[], breakout={"vol_confirm": False})
check("N2 A股空头分支=禁开空", "不可开空" in c2_text(down_sig, a_share_meta) and "减仓 / 离场 / 避险" in c2_text(down_sig, a_share_meta))
# 期货：可做空分支
fut_meta = _meta("上期所", "可双向开仓（保证金交易，注意杠杆）", t_plus=0, price_limit="无涨跌停（有停板幅度+熔断）", vol_unit="手")
c2f = c2_text(down_sig, fut_meta)
check("N2 期货分支=可做空+杠杆提示", "可做空" in c2f and "杠杆" in c2f, c2f[:30])
# 多头信号下 C2 不误报禁空
up_meta = a_share_meta
c2up = c2_text(sig, up_meta)  # 茅台 sig 是 up
check("N2 多头信号 C2 不触发禁空处置", "不触发做空限制" in c2up, c2up[:30])

# N3 levels/events 自动生成
levels = build_levels(sig)
check("N3 levels 自动生成 6 条", len(levels) == 6, f"n={len(levels)}")
check("N3 levels 含颈线/目标/停损/底", all(any(tok in lv["txt"] for lv in levels)
      for tok in ["颈线", "目标位①", "目标位②", "停损", "形态底"]))
events = build_events(sig, df, up_meta)
check("N3 events 自动生成(突破/底/颈线取样)", len(events) >= 3, f"n={len(events)}")

# N4 独立报告含 C1–C4
rep = build_report(sig, up_meta)
check("N4 报告含 C1–C4", all(k in rep for k in ["C1", "C2", "C3", "C4"]))
check("N4 报告含结构判定", "## 一、结构判定" in rep)

# N5 数字来自信号（levels 文案含 neckline 数值，非魔法数）
neck_str = f"{sig.neckline:.0f}"
check("N5 颈线值进入 levels 文案", any(neck_str in lv["txt"] for lv in levels),
      f"neck={neck_str}")

# --- 真实 down 信号端到端（对抗 S3 空头漏洞 + S4 颈线 x0）---
mtop_df = _build_mtop()
down_sig = analyze(mtop_df, ABParams())
check("D1 analyze 产出真实空头 M 头", down_sig.ok and down_sig.direction == "down",
      f"ok={down_sig.ok} dir={down_sig.direction} pattern={down_sig.pattern}")

fut_meta = _meta("上期所", "可双向开仓（保证金交易，注意杠杆）", t_plus=0,
                 price_limit="无涨跌停（有停板幅度+熔断）", vol_unit="手")
a_meta = _meta("上交所A股", "禁止开空（融券极难）→ 只作减仓/离场/避险")
check("D2 真实空头+期货 C2=可做空", "可做空" in c2_text(down_sig, fut_meta) and "不可开空" not in c2_text(down_sig, fut_meta))
check("D3 真实空头+A股 C2=禁开空", "不可开空" in c2_text(down_sig, a_meta))

down_levels = build_levels(down_sig, fut_meta)
check("D4 空头 levels 写「形态顶」", any("形态顶" in lv["txt"] for lv in down_levels))
check("D5 空头 levels 写「已跌破颈线」", any("已跌破颈线" in lv["txt"] for lv in down_levels))
check("D6 颈线 level 带 x0 起点", any("颈线" in lv["txt"] and lv.get("x0") is not None for lv in down_levels),
      f"neck_start_i={down_sig.neck_start_i}")

# render_signal 真实空头不崩
try:
    render_signal(down_sig, mtop_df, fut_meta, os.path.join(TMP, "_test_mtop.png"))
    check("D7 render_signal 真实空头不崩", True)
except Exception as e:
    check("D7 render_signal 真实空头不崩", False, repr(e))

# --- 失败信号 render_signal 不崩（核心健壮性）---
flat_df = _make_df([100.0] * 100)
fsig = analyze(flat_df, ABParams())
check("F1 analyze 失败信号 ok=False", not fsig.ok, fsig.reason)
try:
    render_signal(fsig, flat_df, fut_meta, os.path.join(TMP, "_test_fail.png"))
    check("F2 render_signal 失败信号不崩", True)
except Exception as e:
    check("F2 render_signal 失败信号不崩", False, repr(e))

# --- meta=None / short_mode 未知时 C2 默认从严 ---
check("F3 meta=None+空头 C2 默认禁开空", "不可开空" in c2_text(down_sig, None))

print(f"\nS3 自检: {len(PASS)} 通过 / {len(FAIL)} 失败")
sys.exit(1 if FAIL else 0)
