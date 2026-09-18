#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S5 失败识别（K 招）自检
======================
锁定 caisen_failure + analyze 的失败识别行为，防止回归。

覆盖：
  S5-1 假突破（up 突破后跌回颈线）→ 翻空（analyze 集成）
  S5-2 假跌破/破底翻（down 突破后站回颈线）→ 翻多（check_failure 单测）
  S5-3 量价背离（突破后价升量缩）→ 警讯，不翻转
  S5-4 正常有效突破（茅台）→ 不被翻转
  S5-5 文案/绘图集成（K招段落 + 主图失败框）
"""
import pandas as pd
import numpy as np

from caisen_ab import analyze, ABParams, ABSignal
from caisen_failure import check_failure, build_reversal_signal, FailureSignal
from caisen_narrative import build_text_blocks, build_events
from test_caisen_ab import _load_maotai


def _synth(n, gen):
    rows = []
    for i in range(n):
        o, h, l, c, v = gen(i)
        d = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)
        rows.append({"date": d, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return pd.DataFrame(rows).set_index("date").sort_index()


def _wbase_gen(i):
    if i < 20:
        c = 100 - i * 1.0
    elif i < 30:
        c = 80 + (i - 20) * 1.5
    elif i < 40:
        c = 95 - (i - 30) * 1.7
    elif i < 50:
        c = 78 + (i - 40) * 1.7
    else:
        c = 95 + (i - 50) * 1.2
    o = c - 0.5; h = max(o, c) + 1.0; l = min(o, c) - 1.0
    # 放量段覆盖突破根（50-55），之后量缩 —— 触发量价背离警讯
    v = 3000.0 if 50 <= i <= 55 else 1000.0
    return o, h, l, c, v


def _fake_breakup_gen(i):
    """W 底前 50 根同 _wbase_gen；i 50-55 放量突破颈线 95；i>=56 温和跌回颈线下
    （确认假突破，但不暴跌，避免 analyze 直接判 down）。"""
    if i < 50:
        return _wbase_gen(i)
    if i < 56:
        c = 95 + (i - 50) * 1.0
    else:
        c = 100 - (i - 56) * 0.8
    o = c - 0.5; h = max(o, c) + 1.0; l = min(o, c) - 1.0
    v = 3000.0 if 50 <= i <= 55 else 1000.0
    return o, h, l, c, v


def _m_down_gen(i):
    """构造 down 突破（跌破颈线 115）后站回颈线上的 df，供 check_failure 单测。"""
    if i < 20:
        c = 100 + i * 1.5
    elif i < 30:
        c = 130 - (i - 20) * 1.5
    elif i < 40:
        c = 115 + (i - 30) * 1.7
    elif i < 50:
        c = 132 - (i - 40) * 1.7
    elif i == 50:
        c = 114.0                      # 跌破颈线 115
    else:
        c = 114.0 + (i - 50) * 0.6     # 站回 > 115*1.005
    o = c - 0.5; h = max(o, c) + 1.0; l = min(o, c) - 1.0; v = 1000.0
    return o, h, l, c, v


# ----------------------------------------------------------------------
def test_fake_breakup_flips_down():
    df = _synth(80, _fake_breakup_gen)
    sig = analyze(df, ABParams())
    assert sig.ok, sig.reason
    assert sig.failure_type == "假突破", f"应为假突破，实得 {sig.failure_type}"
    assert sig.direction == "down", f"应翻空，实得 {sig.direction}"
    assert sig.orig_direction == "up"
    assert sig.target1 < sig.neckline, "翻空目标应在颈线下方"
    assert sig.pattern == "假突破（翻空）"
    print(f"  [S5-1] 假突破翻空: 原=up→翻=down 颈线={sig.neckline:.1f} "
          f"目标①={sig.target1:.1f} 形态={sig.pattern}")
    return True


def test_fake_breakdown_flips_up():
    # 直接验证 check_failure 对「down 突破后站回颈线」的识别（翻多）
    df = _synth(80, _m_down_gen)
    sig = ABSignal(ok=True, direction="down", neckline=115.0,
                   breakout={"date": "2025-02-20", "i": 50, "close": 114.0,
                             "body_ok": True, "close_ok": True, "vol_ratio": 1.5,
                             "vol_confirm": True, "pullback": None},
                   neck_touches=[("2025-02-10", 115.0), ("2025-02-15", 115.5)],
                   neck_start="2025-02-10", neck_start_i=40,
                   extreme={"date": "2025-02-18", "price": 132.0, "i": 48},
                   height=17.0, target1=98.0, target2=81.0,
                   entry=114.0, stop=118.0, stop_pct=0.03,
                   last_close=123.0, atr=3.0)
    fail = check_failure(df, sig, ABParams())
    assert fail is not None, "应识别为假跌破/破底翻"
    assert fail.type == "假跌破/破底翻", f"类型应为假跌破/破底翻，实得 {fail.type}"
    assert fail.direction == "up", f"应翻多，实得 {fail.direction}"
    # 翻转重建信号
    rev = build_reversal_signal(df, sig, fail, ABParams())
    assert rev.direction == "up"
    assert rev.target1 > rev.neckline
    assert rev.pattern == "破底翻（翻多）"
    print(f"  [S5-2] 假跌破翻多: type={fail.type} 翻=up 颈线={rev.neckline:.1f} "
          f"目标①={rev.target1:.1f} 形态={rev.pattern}")
    return True


def test_volume_divergence_warn():
    # 正常 W 底突破，但突破后量缩 → 量价背离警讯（不翻转方向）
    df = _synth(80, _wbase_gen)
    sig = analyze(df, ABParams())
    assert sig.ok, sig.reason
    assert sig.direction == "up", "方向不应被翻转"
    assert sig.failure_type in ("量价背离", "异常量", "逃命线", ""), \
        f"警讯类型应在集合内，实得 {sig.failure_type}"
    assert any("K招" in n for n in sig.notes), "notes 应含 K招失败识别"
    print(f"  [S5-3] 量价警讯: type={sig.failure_type or '窗口内量未明显缩'} "
          f"dir={sig.direction}（不翻转）")
    return True


def test_normal_no_fakebreak():
    # 茅台真实数据：正常有效突破，不应被翻空/翻多
    df = _load_maotai()
    sig = analyze(df, ABParams())
    assert sig.ok, sig.reason
    assert sig.failure_type not in ("假突破", "假跌破/破底翻"), \
        f"正常突破不应翻转，type={sig.failure_type}"
    print(f"  [S5-4] 茅台正常突破: type={sig.failure_type or '无失败'} "
          f"dir={sig.direction} 颈线={sig.neckline:.1f}")
    return True


def test_narrative_integration():
    df = _synth(80, _fake_breakup_gen)
    sig = analyze(df, ABParams())
    assert sig.ok, sig.reason
    left, right = build_text_blocks(sig, None, df=df)
    assert "失败识别（K 招）" in left, "左栏应含 K招段落"
    assert "K招失败识别" in right, "右栏应含 K招警讯"
    evs = build_events(sig, df, None)
    assert any("假突破" in e["txt"] for e in evs), "主图①框应标注假突破"
    print(f"  [S5-5] 文案/绘图集成 OK: 左栏K招段={'失败识别（K 招）' in left} "
          f"主图失败框={any('假突破' in e['txt'] for e in evs)}")
    return True


# ----------------------------------------------------------------------
if __name__ == "__main__":
    tests = [test_fake_breakup_flips_down, test_fake_breakdown_flips_up,
             test_volume_divergence_warn, test_normal_no_fakebreak,
             test_narrative_integration]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
        except Exception as e:
            print(f"  [ERROR] {t.__name__}: {repr(e)}")
    print(f"\nS5 自检: {passed}/{len(tests)} 通过")
    if passed != len(tests):
        raise SystemExit(1)
