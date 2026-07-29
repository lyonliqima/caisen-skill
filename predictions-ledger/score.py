#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
score.py — 预测台账 周度复盘引擎
====================================
读取 predictions-ledger/ledger.jsonl，做四件事：
  1) 列出「到期待复盘」记录（expiry <= 今天 且 status=open）→ reports/review-<date>.md
  2) 对已判定记录统计：命中率（总/按专家/按资产/按置信度区间）
  3) 超额命中率（本体系 − max(random_dir, ma_rule)）、校准曲线、Brier、CRPS、三色独立性
  4) 共识矩阵 × 超额收益、可预测性 × 命中率、专家分项命中率（--expert-matrix）、更新质量

子命令 / 标志
------------
  python3 score.py                      # 复盘 + 写 reports/
  python3 score.py --quiet             # 只打印，不写盘
  python3 score.py --due               # 只列到期待结算清单
  python3 score.py mark P-... --status hit --return 8.2
  python3 score.py --calibration       # 校准系数表 + Brier 三项分解（PRED 9；n<30 停用）
  python3 score.py --expert-matrix      # 专家分项命中率表（PRED 12；n<10 显示样本不足）

样本不足铁律：所有统计在 n<30 时只报原值/打印警告，绝不硬拟合。
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, date

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger.jsonl")
REPORTS = os.path.join(HERE, "reports")
TODAY = date.today()

DIR_PROB = {"多": "bull_prob", "空": "bear_prob", "中性": "base_prob"}
CONF_BUCKETS = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50),
                (50, 60), (60, 70), (70, 80), (80, 90), (90, 101)]
CONF_LABEL = {b: "%02d-%02d" % (b[0], min(b[1], 100)) for b in CONF_BUCKETS}
# PRED 9 校准桶（含 90-100）
CAL_BUCKETS = [(50, 60), (60, 70), (70, 80), (80, 90), (90, 101)]
CAL_LABEL = {b: "%02d-%02d" % (b[0], min(b[1], 100)) for b in CAL_BUCKETS}


def _load():
    recs = []
    if not os.path.exists(LEDGER):
        return recs
    with open(LEDGER, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception as e:
                sys.stderr.write("⚠️ 第%d行解析失败，跳过: %s\n" % (ln, e))
    return recs


def _parse_expiry(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _due(recs):
    out = []
    for r in recs:
        if str(r.get("status", "open")) != "open":
            continue
        ex = _parse_expiry(r.get("expiry"))
        if ex and ex <= TODAY:
            out.append(r)
    return out


def print_due(recs):
    due = _due(recs)
    if not due:
        future = [r for r in recs
                  if str(r.get("status", "open")) == "open" and _parse_expiry(r.get("expiry"))]
        future.sort(key=lambda r: _parse_expiry(r.get("expiry")))
        if future:
            nxt = future[0]
            ex = _parse_expiry(nxt.get("expiry"))
            days = (ex - TODAY).days
            print("本期无到期预测，最近到期日：%s（还有 %d 天）→ %s %s"
                  % (nxt.get("expiry"), days, nxt.get("id"), nxt.get("symbol")))
        else:
            print("本期无到期预测，且无未来到期日记录。")
        return
    print("待结算清单（expiry <= %s 且 status=open）：" % TODAY.isoformat())
    print("%-16s %-24s %-6s %-4s %-10s %s" % ("id", "标的", "方向", "置信度", "期限", "到期"))
    for r in due:
        print("%-16s %-24s %-6s %-4s %-10s %s" % (
            r.get("id"), r.get("symbol"), r.get("direction"),
            r.get("confidence"), r.get("time_window"), r.get("expiry")))


def _is_judged(r):
    return str(r.get("status", "open")) in ("hit", "miss", "partial") \
        and r.get("actual_return") is not None


def _outcome(r):
    return {"hit": 1.0, "miss": 0.0, "partial": 0.5}.get(str(r.get("status")), None)


def _market_prior(r):
    mp = r.get("market_prior")
    if isinstance(mp, dict) and mp.get("applicable") is True:
        return mp
    return None


def _main_prob(r):
    sc = r.get("scenarios") or {}
    key = DIR_PROB.get(r.get("direction"))
    if key and isinstance(sc.get(key), int):
        return sc[key] / 100.0
    c = r.get("confidence")
    return (c / 100.0) if isinstance(c, int) else None


def _hit_rate(grp):
    n = len(grp)
    if n == 0:
        return (0, 0.0)
    s = sum(_outcome(r) for r in grp)
    return (n, s / n)


def _bench_hit_rate(r):
    """该记录可用的基准命中率（取 random_dir / ma_rule 中较大的 hit_rate）。"""
    best = None
    for fld in ("random_dir", "ma_rule"):
        v = r.get(fld)
        if isinstance(v, dict) and isinstance(v.get("hit_rate"), (int, float)):
            best = v["hit_rate"] if best is None else max(best, v["hit_rate"])
    return best


def stats(recs):
    # 设计缺陷隔离（PRED 4）：sanity.pass==False 的记录不计入判断准确率
    jud = [r for r in recs if _is_judged(r)]
    design_defect = [r for r in jud if isinstance(r.get("sanity"), dict)
                     and r["sanity"].get("pass") is False]
    jud_valid = [r for r in jud if r not in design_defect]

    n = len(jud_valid)
    overall = _hit_rate(jud_valid)

    by_skill = {}
    by_asset = {}
    by_conf = {"≤60": [], "61-70": [], "71-80": [], ">80": []}
    for r in jud_valid:
        by_skill.setdefault(r.get("source_skill", "?"), []).append(r)
        by_asset.setdefault(r.get("asset_class", "?"), []).append(r)
        c = r.get("confidence") or 0
        if c <= 60:
            by_conf["≤60"].append(r)
        elif c <= 70:
            by_conf["61-70"].append(r)
        elif c <= 80:
            by_conf["71-80"].append(r)
        else:
            by_conf[">80"].append(r)

    dq = {"未记录": [], "0-60": [], "60-70": [], "70-85": [], "85-100": []}
    for r in jud_valid:
        q = r.get("data_quality")
        if not isinstance(q, int):
            dq["未记录"].append(r)
        elif q < 60:
            dq["0-60"].append(r)
        elif q < 70:
            dq["60-70"].append(r)
        elif q < 85:
            dq["70-85"].append(r)
        else:
            dq["85-100"].append(r)

    cal = {lab: [] for lab in CONF_LABEL.values()}
    for r in jud_valid:
        c = r.get("confidence") or 0
        for (lo, hi) in CONF_BUCKETS:
            if lo <= c < hi:
                cal[CONF_LABEL[(lo, hi)]].append(r)
                break

    briers = [(_main_prob(r), _outcome(r)) for r in jud_valid if _main_prob(r) is not None]
    brier = (sum((p - o) ** 2 for p, o in briers) / len(briers)) if briers else None

    # 三色（PRED 6：兼容旧单值字符串与新对象计数）
    colors = {"🟢": 0, "🔵": 0, "🟡": 0}
    for r in recs:
        col = r.get("independence_color")
        if isinstance(col, dict):
            colors["🟢"] += int(col.get("green", 0) or 0)
            colors["🔵"] += int(col.get("blue", 0) or 0)
            colors["🟡"] += int(col.get("yellow", 0) or 0)
        elif col in colors:
            colors[col] += 1

    # 超额命中率（PRED 1）
    my_rate = overall[1] if overall[0] else None
    bench_vals = [b for b in (_bench_hit_rate(r) for r in jud_valid) if b is not None]
    bench_avg = (sum(bench_vals) / len(bench_vals)) if bench_vals else None
    excess = (my_rate - bench_avg) if (my_rate is not None and bench_avg is not None) else None

    # 可预测性 × 命中率（PRED 3）
    by_pred = {}
    for r in jud_valid:
        rating = r.get("predictability")
        if rating in ("高", "中", "低", "接近随机"):
            by_pred.setdefault(rating, []).append(r)

    # 共识矩阵 × 超额收益（PRED 5）
    by_cell = {}
    for r in jud_valid:
        cell = r.get("consensus_cell")
        if cell in ("共识-已定价", "共识-未定价", "分歧-已定价", "分歧-未定价"):
            by_cell.setdefault(cell, []).append(r)

    # CRPS（PRED 11）
    crps_list = [r for r in jud_valid if r.get("crps") is not None]

    # 市场先验
    mp_recs = [r for r in jud_valid if _market_prior(r)]
    div = [r for r in mp_recs
           if isinstance(_market_prior(r).get("divergence_pct"), (int, float))
           and abs(_market_prior(r)["divergence_pct"]) >= 10]
    beat = [r for r in mp_recs
            if (_market_prior(r).get("divergence_pct") or 0) > 0]
    mp = dict(n=len(mp_recs), all=_hit_rate(mp_recs),
              divergent_n=len(div), divergent=_hit_rate(div),
              beat_n=len(beat), beat=_hit_rate(beat))

    return dict(n=n, overall=overall, by_skill=by_skill, by_asset=by_asset,
                by_conf=by_conf, dq=dq, cal=cal, brier=brier, colors=colors,
                my_rate=my_rate, bench_avg=bench_avg, excess=excess,
                by_pred=by_pred, by_cell=by_cell, crps_list=crps_list,
                design_defect=design_defect, mp=mp)


def fmt_rate(t):
    n, r = t
    return "—" if n == 0 else "%.0f%% (%d条)" % (r * 100, n)


def _conclusion_excess(st):
    n = st["n"]
    ex = st["excess"]
    if ex is None:
        return "（基准字段不足，无法计算超额命中率）"
    if n < 30:
        return "样本不足（n=%d < 30），暂不评价超额" % n
    if ex > 0.05:
        return "✅ 体系有效（超额 +%.0f%%）" % (ex * 100)
    if ex < -0.05:
        return "⚠️ 体系跑输基准，当前配置为负 alpha（超额 %.0f%%）" % (ex * 100)
    return "➖ 与基准无显著差异（超额 %+.0f%%）" % (ex * 100)


def render(recs, quiet):
    due = _due(recs)
    st = stats(recs)
    lines = []
    lines.append("# 预测台账复盘 · %s\n" % TODAY.isoformat())
    lines.append("> 共 %d 条记录；已判定(有效) %d 条；设计缺陷隔离 %d 条；到期待复盘 %d 条。\n"
                 % (len(recs), st["n"], len(st["design_defect"]), len(due)))

    lines.append("## 一、到期待复盘（逐条判对错）\n")
    if due:
        lines.append("| id | 标的 | 方向 | 置信度 | 期限 | 证伪位 | 到期 | 证据快照 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in due:
            lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                r.get("id"), r.get("symbol"), r.get("direction"),
                r.get("confidence"), r.get("time_window"),
                r.get("falsification"), r.get("expiry"),
                r.get("evidence_ref") or "—"))
    else:
        lines.append("（无到期待复盘记录）\n")

    lines.append("## 二、命中率 与 超额命中率（PRED 1）\n")
    lines.append("- 总体命中率：**%s**" % fmt_rate(st["overall"]))
    lines.append("- 基准平均命中率（max(random_dir, ma_rule)）：**%s**"
                 % ("%.0f%%" % (st["bench_avg"] * 100) if st["bench_avg"] is not None else "—"))
    lines.append("- **超额命中率 = 本体系 − 基准 = %s**" % (
        "%+.0f%%" % (st["excess"] * 100) if st["excess"] is not None else "—"))
    lines.append("- 结论：**%s**" % _conclusion_excess(st))
    lines.append("\n### 按资产类别")
    lines.append("| 资产 | 命中率 |")
    lines.append("|---|---|")
    for k in sorted(st["by_asset"]):
        lines.append("| %s | %s |" % (k, fmt_rate(_hit_rate(st["by_asset"][k]))))

    lines.append("\n## 三、可预测性评级 × 命中率（PRED 3）\n")
    lines.append("| 评级 | n | 命中率 |")
    lines.append("|---|---|---|")
    for k in ("高", "中", "低", "接近随机"):
        if k in st["by_pred"]:
            lines.append("| %s | %d | %s |" % (k, len(st["by_pred"][k]),
                                               fmt_rate(_hit_rate(st["by_pred"][k]))))
    if st["by_pred"]:
        near = st["by_pred"].get("接近随机")
        high = st["by_pred"].get("高")
        if near and _hit_rate(near)[1] > 0.55:
            lines.append("\n⚠️ 「接近随机」组命中率 >55%，可预测性评级可能过于保守。")
        if high and _hit_rate(high)[1] < 0.70:
            lines.append("\n⚠️ 「高」组命中率 <70%，可预测性评级可能过于乐观。")
    else:
        lines.append("（无 predictability 标注记录）")

    lines.append("\n## 四、共识矩阵 × 超额收益（PRED 5）\n")
    lines.append("| 落格 | n | 平均实际收益% |")
    lines.append("|---|---|---|")
    cell_ret = {}
    for k in ("共识-未定价", "分歧-未定价", "共识-已定价", "分歧-已定价"):
        if k in st["by_cell"]:
            grp = st["by_cell"][k]
            rs = [r.get("actual_return") for r in grp if isinstance(r.get("actual_return"), (int, float))]
            avg = (sum(rs) / len(rs)) if rs else None
            cell_ret[k] = avg
            lines.append("| %s | %d | %s |" % (k, len(grp), ("%.1f" % avg if avg is not None else "—")))
    if "共识-未定价" in cell_ret and cell_ret["共识-未定价"] is not None:
        others = [v for k, v in cell_ret.items() if k != "共识-未定价" and v is not None]
        if others and cell_ret["共识-未定价"] <= max(others):
            lines.append("\n⚠️ 「共识-未定价」格超额收益未显著高于其他格，市场定价读数可能取错。")

    lines.append("\n## 五、校准曲线（预测置信度 vs 实际命中）\n")
    lines.append("| 置信度桶 | 样本 | 实际命中 | 预测中点 | 偏差 |")
    lines.append("|---|---|---|---|---|")
    for lab in CONF_LABEL.values():
        grp = st["cal"][lab]
        if not grp:
            continue
        n, rr = _hit_rate(grp)
        mid = int(lab.split("-")[0]) + 5
        dev = rr * 100 - mid
        lines.append("| %s | %d | %.0f%% | %d%% | %+d |" % (lab, n, rr * 100, mid, round(dev)))

    lines.append("\n## 六、Brier 概率评分\n")
    lines.append("- Brier = **%s**（越低越好；0=完美，0.25=随机）"
                 % ("%.3f" % st["brier"] if st["brier"] is not None else "—"))

    lines.append("\n## 七、独立性三色审计（防回声室 · PRED 6）\n")
    c = st["colors"]
    tot = sum(c.values()) or 1
    lines.append("| 颜色 | 含义 | 计数 | 占比 |")
    lines.append("|---|---|---|---|")
    lines.append("| 🟢 | 独立推导·恰与专家一致 | %d | %.0f%% |" % (c["🟢"], c["🟢"] / tot * 100))
    lines.append("| 🔵 | 独立推导·与专家分歧 | %d | %.0f%% |" % (c["🔵"], c["🔵"] / tot * 100))
    lines.append("| 🟡 | 假说验证中 | %d | %.0f%% |" % (c["🟡"], c["🟡"] / tot * 100))
    if c["🔵"] / tot < 0.15 and tot >= 5:
        lines.append("\n⚠️ **回声室警告**：🔵（独立分歧）长期 <15%，十二专家的边际信息量可能接近零，"
                     "考虑削减专家数量或加强输入切片（PRED 6）。")

    lines.append("\n## 八、CRPS 连续概率评分（PRED 11）\n")
    if st["crps_list"]:
        lines.append("| id | 方向对错 | Brier | CRPS |")
        lines.append("|---|---|---|---|")
        for r in st["crps_list"]:
            ok = "对" if str(r.get("status")) == "hit" else ("半" if str(r.get("status")) == "partial" else "错")
            lines.append("| %s | %s | %s | %s |" % (
                r.get("id"), ok,
                ("%.3f" % _main_prob(r) if _main_prob(r) is not None else "—"),
                ("%.3f" % r["crps"] if isinstance(r.get("crps"), (int, float)) else "—")))
    else:
        lines.append("（暂无比对 CRPS 的记录；回填 scenarios 中点后生效）")

    lines.append("\n## 九、设计缺陷隔离（PRED 4 · 量纲假失败）\n")
    if st["design_defect"]:
        for r in st["design_defect"]:
            lines.append("- %s %s：%s" % (r.get("id"), r.get("symbol"),
                                         r.get("sanity", {}).get("reason", "量纲校验未通过")))
    else:
        lines.append("（无被量纲校验隔离的设计缺陷记录）")

    lines.append("\n## 十、与市场共识分歧的预测命中率（真正 alpha 读数）\n")
    mp = st["mp"]
    if mp["n"]:
        lines.append("- 含市场先验记录：**%d** 条；其中与市场分歧（偏差≥10pct）**%d** 条。" % (mp["n"], mp["divergent_n"]))
        lines.append("- 全部含先验预测命中率：**%s**" % fmt_rate(mp["all"]))
        lines.append("- **分歧预测**（|偏差|≥10pct）命中率：**%s**" % fmt_rate(mp["divergent"]))
    else:
        lines.append("- 暂无含 `market_prior` 的判定记录。")

    lines.append("\n## 十一、数据质量分 × 命中率\n")
    lines.append("| 数据质量分 | 命中率 |")
    lines.append("|---|---|")
    for k in ("0-60", "60-70", "70-85", "85-100", "未记录"):
        lines.append("| %s | %s |" % (k, fmt_rate(_hit_rate(st["dq"][k]))))

    lines.append("\n---\n*本文件由 predictions-ledger/score.py 自动生成，判定数据由人工 / mx-moni 回填。*")
    text = "\n".join(lines) + "\n"

    print("📊 台账复盘 %s" % TODAY.isoformat())
    print("  记录 %d · 有效判定 %d · 设计缺陷隔离 %d · 待复盘 %d"
          % (len(recs), st["n"], len(st["design_defect"]), len(due)))
    print("  总体命中率 %s · 超额 %s" % (
        fmt_rate(st["overall"]),
        ("%+.0f%%" % (st["excess"] * 100) if st["excess"] is not None else "—")))
    print("  Brier %s · 🔵独立性 %d/%d" % (
        "%.3f" % st["brier"] if st["brier"] is not None else "—", c["🔵"], tot))
    if c["🔵"] / tot < 0.15 and tot >= 5:
        print("  ⚠️ 回声室警告：🔵 长期 <15%")

    if not quiet:
        os.makedirs(REPORTS, exist_ok=True)
        p = os.path.join(REPORTS, "score-%s.md" % TODAY.strftime("%Y%m%d"))
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        print("  ✓ 报告 → %s" % p)
        if due:
            rp = os.path.join(REPORTS, "review-%s.md" % TODAY.strftime("%Y%m%d"))
            with open(rp, "w", encoding="utf-8") as f:
                f.write("# 待复盘清单 %s\n\n" % TODAY.isoformat()
                        + "\n".join("- [ ] %s %s %s/%s/%s → `%s`" % (
                            r.get("id"), r.get("symbol"), r.get("direction"),
                            r.get("confidence"), r.get("time_window"),
                            "python3 score.py mark %s --status hit --return 0.0" % r.get("id"))
                          for r in due) + "\n")
            print("  ✓ 待复盘 → %s" % rp)
    return text


# ─────────────────── PRED 9：校准回路 + Brier 分解 ───────────────────
def _crps_of(rec):
    sc = rec.get("scenarios") or {}
    xs, ps = [], []
    for key in ("bull", "base", "bear"):
        mid = sc.get("%s_midpoint" % key)
        prob = sc.get("%s_prob" % key)
        if isinstance(mid, (int, float)) and isinstance(prob, (int, float)):
            xs.append(mid)
            ps.append(prob / 100.0)
    if len(xs) < 2 or abs(sum(ps) - 1.0) > 0.01:
        return None
    y = rec.get("actual_return")
    if not isinstance(y, (int, float)):
        return None
    term1 = sum(p * abs(x - y) for x, p in zip(xs, ps))
    term2 = 0.5 * sum(p1 * p2 * abs(x1 - x2)
                      for x1, p1 in zip(xs, ps) for x2, p2 in zip(xs, ps))
    return term1 - term2


def _brier_components(recs):
    """Brier = 可靠性 − 分辨率 + 不确定性。"""
    pairs = []
    for r in recs:
        p = _main_prob(r)
        o = _outcome(r)
        if p is not None and o is not None:
            pairs.append((round(p, 2), o))
    if not pairs:
        return None
    n = len(pairs)
    o_bar = sum(o for _, o in pairs) / n
    uncertainty = o_bar * (1 - o_bar)
    # 按预测 p 分桶
    from collections import defaultdict
    g = defaultdict(list)
    for p, o in pairs:
        g[p].append(o)
    rel, res = 0.0, 0.0
    for p, os_ in g.items():
        ng = len(os_)
        mean_o = sum(os_) / ng
        rel += ng / n * (p - mean_o) ** 2
        res += ng / n * (mean_o - o_bar) ** 2
    brier = rel - res + uncertainty
    return {"reliability": round(rel, 4), "resolution": round(res, 4),
            "uncertainty": round(uncertainty, 4), "brier": round(brier, 4),
            "n": n}


def cmd_calibration(recs):
    jud = [r for r in recs if _is_judged(r)]
    n = len(jud)
    print("=== 校准回路（PRED 9）===")
    if n < 30:
        print("样本不足（n=%d/30），校准未启用。返回原值，不做收缩。" % n)
    # 分桶
    buckets = {lab: [] for lab in CAL_LABEL.values()}
    for r in jud:
        c = r.get("confidence") or 0
        for (lo, hi) in CAL_BUCKETS:
            if lo <= c < hi:
                buckets[CAL_LABEL[(lo, hi)]].append(r)
                break
    print("%-8s %5s %8s %8s %10s %s" % ("桶", "n", "原命中", "中点", "收缩后", "状态"))
    for (lo, hi) in CAL_BUCKETS:
        lab = CAL_LABEL[(lo, hi)]
        grp = buckets[lab]
        nb = len(grp)
        if nb == 0:
            print("%-8s %5s %8s %8s %10s %s" % (lab, 0, "—", (lo + hi) // 2, "—", "样本0"))
            continue
        hr = sum(_outcome(r) for r in grp) / nb
        mid = (lo + min(hi, 100)) / 2 / 100.0
        k = 10
        if nb < 5:
            shrunk = hr  # 桶内 n<5 不参与校准，返回原值
            status = "n<5 不校准"
        else:
            shrunk = (nb * hr + k * mid) / (nb + k)
            status = "已收缩" if n >= 30 else "样本不足未启用"
        print("%-8s %5d %7.0f%% %8.2f %9.0f%% %s" % (
            lab, nb, hr * 100, mid, shrunk * 100, status))

    # 全局校准后映射示例
    print("\n[全局] 样本 n=%d → %s" % (n, "校准已启用" if n >= 30 else "校准未启用（返回原值）"))

    # Brier 三项分解
    comp = _brier_components(jud)
    if comp:
        print("\n=== Brier 三项分解 ===")
        print("  Brier        = %.4f" % comp["brier"])
        print("  可靠性 reliab = %.4f  （差→校准有问题，用回路修）" % comp["reliability"])
        print("  分辨率 resol  = %.4f  （差→判断本身没区分度，加校准也没用）" % comp["resolution"])
        print("  不确定性 unc   = %.4f" % comp["uncertainty"])
    return


# ─────────────────── PRED 12：专家分项命中率矩阵 ───────────────────
def cmd_expert_matrix(recs):
    print("=== 专家分项命中率矩阵（PRED 12）===")
    cells = {}
    for r in recs:
        views = r.get("expert_views")
        if not isinstance(views, list):
            continue
        ret = r.get("actual_return")
        if not isinstance(ret, (int, float)):
            continue
        actual = 1 if ret > 0 else (-1 if ret < 0 else 0)
        if actual == 0:
            continue
        ac = r.get("asset_class", "?")
        for v in views:
            if not isinstance(v, dict):
                continue
            ex = v.get("expert")
            d = v.get("direction")
            if not ex or d not in ("多", "空", "中性"):
                continue
            ds = 1 if d == "多" else (-1 if d == "空" else 0)
            if ds == 0:
                continue
            cells.setdefault((ex, ac), []).append(1 if ds == actual else 0)
    if not cells:
        print("（无 expert_views 数据；样本不足，无法计算单专家命中率）")
        return
    print("%-12s %-14s %5s %8s %10s %8s" % ("专家", "资产类别", "n", "命中率", "基准命中", "超额"))
    for (ex, ac), outcomes in sorted(cells.items()):
        nb = len(outcomes)
        hr = sum(outcomes) / nb
        bench = "样本不足" if nb < 10 else "—"
        excess = "样本不足" if nb < 10 else "%.0f%%" % ((hr - 0.5) * 100)
        print("%-12s %-14s %5d %7.0f%% %10s %8s" % (ex, ac, nb, hr * 100, bench, excess))
        if nb >= 10 and (hr - 0.5) < -0.05:
            print("  ⚠️ 专家 %s 在 %s 类别上长期负超额（%.0f%%），建议降权或停用" % (ex, ac, (hr - 0.5) * 100))


# ─────────────────── PRED 8：更新质量 ───────────────────
def cmd_update_quality(recs):
    print("=== 更新质量（PRED 8）===")
    flagged = 0
    for r in recs:
        ur = r.get("update_rule")
        if not isinstance(ur, dict):
            continue
        ncd = _parse_expiry(ur.get("next_check_date"))
        ups = r.get("updates")
        if isinstance(ups, list) and ups:
            last = ups[-1]
            ud = _parse_expiry(last.get("date"))
            if ncd and ud and ud > ncd:
                print("⚠️ %s 更新晚于预定检验时点（%s < %s）" % (r.get("id"), ur.get("next_check_date"), last.get("date")))
                flagged += 1
        else:
            print("⚠️ %s 有 update_rule 但未执行任何更新（next_check=%s）"
                  % (r.get("id"), ur.get("next_check_date")))
            flagged += 1
    if flagged == 0:
        print("（无含 update_rule 的记录，或均已按规则更新）")


def mark(rec_id, status, ret, bench_json):
    recs = _load()
    target = None
    for r in recs:
        if r.get("id") == rec_id:
            target = r
            break
    if not target:
        sys.stderr.write("✗ 未找到 id=%s\n" % rec_id)
        sys.exit(2)
    if status:
        target["status"] = status
    if ret is not None:
        target["actual_return"] = ret
    if bench_json:
        try:
            target["benchmark"] = json.loads(bench_json)
        except Exception as e:
            sys.stderr.write("✗ benchmark JSON 解析失败: %s\n" % e)
            sys.exit(2)
    target["review_date"] = TODAY.isoformat()
    p = _main_prob(target)
    o = _outcome(target)
    target["brier"] = round((p - o) ** 2, 4) if (p is not None and o is not None) else None
    crps = _crps_of(target)
    if crps is not None:
        target["crps"] = round(crps, 4)

    with open(LEDGER, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("✓ 已更新 %s → status=%s actual_return=%s brier=%s crps=%s"
          % (rec_id, target.get("status"), target.get("actual_return"),
             target.get("brier"), target.get("crps")))


def main():
    ap = argparse.ArgumentParser(description="预测台账复盘引擎")
    ap.add_argument("cmd", nargs="?", default="review", choices=["review", "mark"])
    ap.add_argument("rec_id", nargs="?", help="mark 模式的记录 id")
    ap.add_argument("--status", help="hit / miss / partial")
    ap.add_argument("--return", dest="ret", type=float, help="实际区间收益%%")
    ap.add_argument("--benchmark", help='基准 JSON，如 \'{"hold_csi300":2.0}\'')
    ap.add_argument("--quiet", action="store_true", help="只打印不写盘")
    ap.add_argument("--due", action="store_true", help="只列到期待结算清单")
    ap.add_argument("--calibration", action="store_true", help="校准系数表 + Brier 分解（PRED 9）")
    ap.add_argument("--expert-matrix", action="store_true", help="专家分项命中率矩阵（PRED 12）")
    args = ap.parse_args()

    recs = _load()

    if args.due:
        print_due(recs)
        return
    if args.calibration:
        cmd_calibration(recs)
        return
    if args.expert_matrix:
        cmd_expert_matrix(recs)
        return
    if args.cmd == "mark":
        if not args.rec_id:
            sys.stderr.write("✗ mark 需要 rec_id\n")
            sys.exit(2)
        mark(args.rec_id, args.status, args.ret, args.benchmark)
    else:
        render(recs, args.quiet)
        # 同时跑更新质量检查（轻量）
        cmd_update_quality(recs)


if __name__ == "__main__":
    main()
