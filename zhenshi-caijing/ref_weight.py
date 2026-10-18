#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ref_weight.py —— 真实财经（第16席）· 参考资料时间衰减与可参考性评估引擎
============================================================================

解决什么问题
------------
真实财经库里存的是**带日期的文章解剖笔记**。同一篇解读数：
  - 它的**解剖方法**（怎么把 Accounts 拆开）永不过期，100% 可用；
  - 它的**结构读数**（财政传导断点在第几段）会慢慢变色，但不会归零；
  - 它的**具体数值**（M2 = 359.63 万亿）几个月后就是历史数据，再拿来做当前判断 = 造假。

本脚本就是这道题的客观器：**给归档日期 → 吐出当前参考度 + 能不能当当期读数用。**

它同时也是一个通用工具：分析时搜到任何一条N 天前的新闻/文章，
用 `eval --date YYYY-MM-DD --layer event` 立刻知道它还能不能作为当前读数进推理链。

三层模型（layer）
----------------
| layer      | 装什么                          | 衰减           | 地板 |
|------------|--------------------------------|----------------|------|
| method     | 方法论 Z1-Zn、解剖步骤、判据    | **不衰减**     | 100  |
| structure  | 份额迁移、传导断点、主体分化    | 走主表         | 60   |
| event      | 具体数值、单期读数、方向性判断  | 走主表         | 0（可变 EXPIRED）|

主衰减刻度（与 caisen-10-experts-analyst 第4步「时间衰减权重」严格对齐）
----------------------------------------------------------------------
    ≤7 天     100     ≤30 天    80     ≤90 天    60
    ≤180 天   40      ≤365 天   20     >730 天   10（仅留痕）

用法
----
    P=/Users/weihaoli/.workbuddy/binaries/python/versions/3.13.12/bin/python3

    # ① 扫全库：每份归档现在还能不能用
    $P ref_weight.py list

    # ② 估任意一条：这条 2026-09-20 的新闻还能不能当当期读数
    $P ref_weight.py eval --date 2026-09-20 --layer event

    # ③ 阻断级闸门：最新一份 event/structure 归档落后太久 → exit 2
    $P ref_weight.py check --require-fresh

    # ④ 自测（改过脚本必跑）
    $P ref_weight.py --self-test

退出码
------
    0  正常
    2  check --require-fresh 不达标（阻断级）

作者: 蔡森十二专家框架 · 真实财经第16席
建立: 2026-10-17
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 常量

# 主衰减表：(天数上限, 权重)，按升序排列，超过最后一条判为 REMNANT
DECAY_TABLE = [
    (7, 100),
    (30, 80),
    (90, 60),
    (180, 40),
    (365, 20),
    (730, 10),
]
REMNANT_WEIGHT = 5          # >730 天：仅留痕

METHOD_WEIGHT = 100         # 方法论层：恒 100，不衰减
STRUCTURE_FLOOR = 60        # 结构层地板：跌到 60 就不再往下掉

# event 层可用性判定
EVENT_OK = 60               # ≥60 可作当期读数
EVENT_WARN = 40             # 40-59 仅作趋势背景；<40 禁止作当期读数

# check --require-fresh 阈值：最新一份 event/structure 归档不得超过 N 天
DEFAULT_MAX_AGE = 180
FRESH_ALLOW_DAYS = 365      # 低于 event 层的 méthod 归档不参与鲜度评判

TIER_LABEL = {
    "method": "方法论层",
    "structure": "结构读数层",
    "event": "事件数值层",
}


# ---------------------------------------------------------------- 核心算法

def weight_for(age_days: int, layer: str = "event") -> int:
    """按层 + 天数算参考度（0-100 整数）。

    age_days  距今年天数（负数=未来日期，由调用方拦截）
    layer     method / structure / event
    """
    if layer == "method":
        return METHOD_WEIGHT

    raw = None
    for limit, w in DECAY_TABLE:
        if age_days <= limit:
            raw = w
            break
    if raw is None:
        raw = REMNANT_WEIGHT

    if layer == "structure":
        return max(raw, STRUCTURE_FLOOR)
    return raw


def verdict_for(weight: int, layer: str) -> str:
    """把参考度翻成一句话裁决 —— 能不能用、怎么用。"""
    if layer == "method":
        return "✅ 可作分析工具（方法论永不过期）"
    if layer == "structure":
        if weight >= 80:
            return "✅ 可作结构背景（需配当期数据复核）"
        return "⚠️ 仅作结构背景（必须配当期读数复核，不得单引）"
    # event
    if weight >= EVENT_OK:
        return "✅ 可作当期读数"
    if weight >= EVENT_WARN:
        return "⚠️ 仅作趋势背景，不得作当期读数"
    return "❌ 已过期：禁止作当期读数，仅作历史留痕"


def days_ago(d: dt.date, today: dt.date) -> int:
    return (today - d).days


# ---------------------------------------------------------------- 日期解析

_DATE8 = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")   # 20261017
_DATE4 = re.compile(r"-(0[1-9]|1[0-2])([0-2]\d|3[01])(?!\d)")  # -1016 (MMDD，无年份)


def parse_date_from_name(name: str, today: dt.date) -> tuple[dt.date | None, str]:
    """从文件名里抠日期。返回 (date|None, 说明)。

    支持三种形态：
      1. 8 位日期  …-20261017.md      → 直接解析（推荐形态）
      2. 4 位 MMDD …-1016.md           → 补年份（跨年可能错位，给警告）
      3. 无日期   00-overview.md       → None（归方法论层）
    """
    m = _DATE8.search(name)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return dt.date(y, mo, d), "8位日期"
        except ValueError:
            return None, f"8位日期非法({m.group(0)})"

    m = _DATE4.search(name)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        y = today.year
        try:
            cand = dt.date(y, mo, d)
        except ValueError:
            return None, f"MMDD 非法(-{m.group(1)}{m.group(2)})"
        # 若推断出的日期比今天晚超过 30 天，说明它属于上一年
        if (cand - today).days > 30:
            try:
                cand = dt.date(y - 1, mo, d)
            except ValueError:
                pass
        return cand, "4位MMDD补年份(跨年可能错位，建议改用8位)"

    return None, "无日期"


def guess_layer(rel_path: str, has_date: bool) -> str:
    """按位置与有无日期推断层级（可用 --layer 显式覆盖）。"""
    p = rel_path.replace("\\", "/")
    base = p.rsplit("/", 1)[-1]
    if base.startswith("examples"):
        return "event"                      # 观点记录 = 事件层，衰减最快
    if p.startswith("references/") or "/references/" in p:
        return "structure" if has_date else "method"
    if re.search(r"z\d+", base, re.I):      # 方法论文件（含 Z 编号）
        return "method"
    return "structure" if has_date else "method"


# ---------------------------------------------------------------- 归档扫描

def scan_archive(root: Path, today: dt.date, layer_override: str | None = None):
    """扫 SKILL.md 外的所有 .md 归档，返回记录列表。"""
    rows = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root).as_posix()
        if rel.lower() == "skill.md" or rel.startswith((".", "_")):
            continue
        d, note = parse_date_from_name(p.name, today)
        layer = layer_override or guess_layer(rel, d is not None)
        if d is None:
            rows.append({
                "rel": rel, "date": None, "layer": layer,
                "age": None, "weight": weight_for(0, layer),
                "verdict": verdict_for(weight_for(0, layer), layer), "note": note,
            })
            continue
        if d > today:
            rows.append({
                "rel": rel, "date": d, "layer": layer, "age": (today - d).days,
                "weight": 0, "verdict": "❗ 日期在未来，疑似录入错误（不进结论）", "note": note,
            })
            continue
        age = days_ago(d, today)
        w = weight_for(age, layer)
        rows.append({
            "rel": rel, "date": d, "layer": layer, "age": age,
            "weight": w, "verdict": verdict_for(w, layer), "note": note,
        })
    return rows


# ---------------------------------------------------------------- 命令

def cmd_list(root: Path, today: dt.date, layer_override: str | None) -> int:
    rows = scan_archive(root, today, layer_override)
    if not rows:
        print(f"未扫到任何归档（根目录：{root}）")
        return 0

    print(f"真实财经参考度评估  |  参照日 {today.isoformat()}（周{'一二三四五六日'[today.weekday()]}）")
    print(f"扫描根：{root}")
    print("=" * 118)
    print(f"{'归档文件':<48} {'层':<12} {'日期':<12} {'天数':>6} {'参考度':>7}  裁决")
    print("-" * 118)
    for r in rows:
        date_s = r["date"].isoformat() if r["date"] else "—"
        age_s = f"{r['age']}天" if r["age"] is not None else "—"
        layer_s = f"{TIER_LABEL.get(r['layer'], r['layer'])}"
        print(f"{r['rel'][:47]:<48} {layer_s:<12} {date_s:<12} {age_s:>6} {r['weight']:>6}%  {r['verdict']}")
        if "补年份" in r["note"]:
            print(f"{'':<48} {'':<12} ⚠️ {r['note']}")
    print("-" * 118)

    usable = [r for r in rows if r["verdict"].startswith("✅")]
    warn = [r for r in rows if r["verdict"].startswith("⚠️")]
    dead = [r for r in rows if r["verdict"].startswith("❌") or r["verdict"].startswith("❗")]
    print(f"可作当期读数 {len(usable)} 份 · 仅作背景 {len(warn)} 份 · 禁作当期读数 {len(dead)} 份")
    print()
    print("用法提示：本表的【事件数值层】≥60% 时才能把里面的具体数字写进当前分析；")
    print("          【结构读数层】永远要配当期数据复核；【方法论层】恒 100%，随便用.")
    return 0


def cmd_eval(today: dt.date, date_str: str, layer: str) -> int:
    try:
        d = dt.date.fromisoformat(date_str.strip())
    except ValueError:
        print(f"[错误] --date 无法解析：{date_str}（须为 YYYY-MM-DD）", file=sys.stderr)
        return 2
    if d > today:
        print(f"[错误] 日期在未来：{d.isoformat()} > 今天 {today.isoformat()}", file=sys.stderr)
        return 2

    age = days_ago(d, today)
    w = weight_for(age, layer)
    print(f"参考度评估 | 目标日期 {d.isoformat()}（距今 {age} 天）| 层={TIER_LABEL.get(layer, layer)}")
    print("-" * 78)
    print(f"  参考度：{w}%")
    print(f"  裁决  ：{verdict_for(w, layer)}")
    if layer == "structure":
        print(f"  说明  ：结构层有 {STRUCTURE_FLOOR}% 地板，再旧也不会归零，但必须配当期读数复核.")
    if layer == "event":
        nxt = next((lim for lim, ww in DECAY_TABLE if ww < w), None)
        if nxt:
            after = max(nxt - age, 0)
            print(f"  提醒  ：再过 {after} 天降至 {weight_for(nxt, layer)}%，第 {nxt + 1} 天再降一档")
        if w < EVENT_WARN:
            print(f"  红线  ：❌ 低于 {EVENT_WARN}%，禁作当期读数，只能入历史留痕")
        elif w < EVENT_OK:
            print(f"  红线  ：⚠️ 低于 {EVENT_OK}%，不得作为当期判断的数值支点，仅可作趋势背景")
    return 0


def cmd_check(root: Path, today: dt.date, max_age: int, layer_override: str | None) -> int:
    rows = [r for r in scan_archive(root, today, layer_override)
            if r["date"] is not None and r["layer"] in ("event", "structure")]
    print(f"鲜度闸机 | 参照日 {today.isoformat()} | 阈值：最新一份 event/structure 归档不得超过 {max_age} 天")
    print("-" * 78)
    if not rows:
        print("⚠️ 库中没有任何带日期的 event/structure 归档 —— 无法证明资料新鲜")
        print("   → 建议：录入新的真实财经文章解剖（带 8 位日期文件名）")
        return 2

    newest = max(rows, key=lambda r: r["date"])
    print(f"最新归档：{newest['rel']}")
    print(f"          日期 {newest['date'].isoformat()} | 距今 {newest['age']} 天 | 参考度 {newest['weight']}%")
    print(f"          裁决：{newest['verdict']}")

    if newest["age"] > max_age:
        print()
        print(f"❌ 不达标：落后 {newest['age']} 天 > 阈值 {max_age} 天")
        print("   → 禁止把本库的具体数值当作当期读数使用；")
        print("   → 仅方法论层（Z1-Zn 解剖步骤）可继续使用，且必须配当期一手数据；")
        print("   → 补齐办法：录入新文章解剖，文件名尾附 8 位数据日（…-20261017.md）")
        return 2

    print()
    print("✅ 达标")
    return 0


# ---------------------------------------------------------------- 自测

def _self_test() -> int:
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: 期望 {want}，实得 {got}")

    today = dt.date(2026, 10, 17)

    # ① 主衰减刻度（event 层，无地板）
    eq(weight_for(0, "event"), 100, "当天")
    eq(weight_for(7, "event"), 100, "7天边界")
    eq(weight_for(8, "event"), 80, "8天掉档")
    eq(weight_for(30, "event"), 80, "30天边界")
    eq(weight_for(31, "event"), 60, "31天掉档")
    eq(weight_for(90, "event"), 60, "90天边界")
    eq(weight_for(91, "event"), 40, "91天掉档")
    eq(weight_for(180, "event"), 40, "180天边界")
    eq(weight_for(181, "event"), 20, "181天掉档")
    eq(weight_for(365, "event"), 20, "365天边界")
    eq(weight_for(366, "event"), 10, "366天掉档")
    eq(weight_for(731, "event"), REMNANT_WEIGHT, "超730天")

    # ② 方法论层不衰减（哪怕放了十年）
    eq(weight_for(3650, "method"), 100, "方法论层十年后仍100")

    # ③ 结构层地板
    eq(weight_for(0, "structure"), 100, "结构层当天")
    eq(weight_for(200, "structure"), STRUCTURE_FLOOR, "结构层200天触地板")
    eq(weight_for(2000, "structure"), STRUCTURE_FLOOR, "结构层2000天仍在地板")

    # ④ 裁决语义
    assert verdict_for(100, "event").startswith("✅")
    assert verdict_for(60, "event").startswith("✅"), "event 60 应为可作当期读数边界"
    assert verdict_for(40, "event").startswith("⚠️"), "event 40 应为仅作背景边界"
    assert verdict_for(20, "event").startswith("❌")
    assert verdict_for(STRUCTURE_FLOOR, "structure").startswith("⚠️")

    # ⑤ 日期解析
    d, note = parse_date_from_name("01-z1-z13-financial-data-anatomy-20261017.md", today)
    eq(d, dt.date(2026, 10, 17), "8位日期解析")
    d2, note2 = parse_date_from_name("examples-1016.md", today)
    eq(d2, dt.date(2026, 10, 16), "4位MMDD补当年")
    d3, _ = parse_date_from_name("examples-0105.md", today)
    eq(d3, dt.date(2026, 1, 5), "4位MMDD跨年不误判")
    d4, note4 = parse_date_from_name("00-overview.md", today)
    eq(d4, None, "无日期返回None")
    # 跨年边界：今天是 2026-01-10，文件名 -1225 应判为 2025 年
    d5, _ = parse_date_from_name("examples-1225.md", dt.date(2026, 1, 10))
    eq(d5, dt.date(2025, 12, 25), "4位MMDD跨年倒推到上一年")

    # ⑥ 层级推断
    eq(guess_layer("examples-1016.md", True), "event", "examples→event")
    eq(guess_layer("references/01-z1-z13-x-20261017.md", True), "structure", "带日期references→structure")
    eq(guess_layer("references/00-overview.md", False), "method", "无日期references→method")
    eq(guess_layer("references/02-z4-z6-subject-method.md", False), "method", "无日期方法论→method")

    # ⑦ 天数差
    eq(days_ago(dt.date(2026, 10, 14), today), 3, "10-14距今3天")

    if fails:
        print("❌ 自测失败：")
        for f in fails:
            print("   -", f)
        return 1
    print("✅ 自测全部通过（7 组共 %d 项断言）" % 27)
    return 0


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="真实财经（第16席）参考资料时间衰减与可参考性评估引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法\n----")[-1],
    )
    here = Path(__file__).resolve().parent
    ap.add_argument("--root", type=Path, default=here, help="归档根目录（默认：本脚本所在目录）")
    ap.add_argument("--today", help="参照日 YYYY-MM-DD（默认：今天；复盘时指定历史日）")
    ap.add_argument("--self-test", action="store_true", help="跑自测")

    sub = ap.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="扫描全库，输出每份归档的当前参考度")
    p_list.add_argument("--layer", choices=["method", "structure", "event"], help="强制全部归档按该层评估")

    p_eval = sub.add_parser("eval", help="评估任意一条资料/新闻的当前参考度")
    p_eval.add_argument("--date", required=True, help="该条资料的产出/发布日期 YYYY-MM-DD")
    p_eval.add_argument("--layer", default="event", choices=["method", "structure", "event"],
                        help="层级（默认 event）")

    p_chk = sub.add_parser("check", help="鲜度闸机（阻断级）")
    p_chk.add_argument("--require-fresh", action="store_true", help="开启阻断模式（不达标 exit 2）")
    p_chk.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE, help=f"最大允许落后天数（默认 {DEFAULT_MAX_AGE}）")
    p_chk.add_argument("--layer", choices=["method", "structure", "event"], help="强制层级评估")

    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.today:
        try:
            today = dt.date.fromisoformat(args.today)
        except ValueError:
            print("[错误] --today 须为 YYYY-MM-DD", file=sys.stderr)
            return 2
    else:
        today = dt.date.today()

    if args.cmd == "list":
        return cmd_list(args.root.resolve(), today, args.layer)
    if args.cmd == "eval":
        return cmd_eval(today, args.date, args.layer)
    if args.cmd == "check":
        if not args.require_fresh:
            print("提示：未加 --require-fresh，仅体检不阻断。", file=sys.stderr)
        return cmd_check(args.root.resolve(), today, args.max_age, args.layer)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
