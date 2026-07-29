#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
score.py — 预测台账 周度复盘引擎
====================================
读取 predictions-ledger/ledger.jsonl，做四件事：
  1) 列出「到期待复盘」记录（expiry <= 今天 且 status=open）→ reports/review-<date>.md
  2) 对已判定记录统计：命中率（总/按专家/按资产/按置信度区间）
  3) 校准曲线（预测置信度 vs 实际命中率）、Brier 概率评分、三色独立性占比
  4) 朴素基准对比槽位（持有沪深300 / 随机方向 / 简单均线）、walk-forward 纪律提示

用法
----
  python3 score.py                 # 复盘 + 写 reports/
  python3 score.py --quiet       # 只打印，不写盘
  python3 score.py mark P-20260709-001 --status hit --return 8.2
                                    # 回填某条：status + 实际收益% + 自动算 brier
  python3 score.py mark P-... --status partial --return -3.1 --benchmark '{"hold_csi300":2.0,"random_dir":-1.1,"ma_rule":0.5}'

说明
----
- 命中定义：hit=1, miss=0, partial=0.5（用于命中率与校准）。
- Brier：主情景概率 p（多→bull_prob / 空→bear_prob / 中性→base_prob）对实际 0/1（partial=0.5）的均方误差，越低越好（0=完美）。
- 校准：把置信度按 10 分桶聚合，看「标 70 分的是否约七成兑现」。LLM 通病是系统性过度自信——校准曲线是最诚实的镜子。
- 三色：🟢独立一致 / 🔵独立分歧 / 🟡假说验证。若 🔵 长期≈0，说明「独立推导」是表演、模型在顺人格先验走（回声室）。
- 基准：九专家全家桶若扣除交易成本后没跑赢「持有沪深300」，那整套机器在增加仪式感而不是 alpha。此对比残酷但必须做。
- walk-forward：破底翻等经验胜率必须前段定参、后段验证，禁止用全历史调参再用全历史验证。
"""
import argparse, json, os, sys, re
from datetime import datetime, date

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger.jsonl")
REPORTS = os.path.join(HERE, "reports")
TODAY = date.today()

DIR_PROB = {"多": "bull_prob", "空": "bear_prob", "中性": "base_prob"}
CONF_BUCKETS = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50),
                (50, 60), (60, 70), (70, 80), (80, 90), (90, 101)]
CONF_LABEL = {b: "%02d-%02d" % (b[0], min(b[1], 100)) for b in CONF_BUCKETS}


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
    # 退化：用 confidence 当主情景概率
    c = r.get("confidence")
    return (c / 100.0) if isinstance(c, int) else None


def _hit_rate(grp):
    n = len(grp)
    if n == 0:
        return (0, 0.0)
    s = sum(_outcome(r) for r in grp)
    return (n, s / n)


def stats(recs):
    jud = [r for r in recs if _is_judged(r)]
    n = len(jud)
    overall = _hit_rate(jud)

    by_skill = {}
    by_asset = {}
    by_conf = {"≤60": [], "61-70": [], "71-80": [], ">80": []}
    for r in jud:
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

    # 数据质量分 × 命中率（复盘归因三类错误：判断错/数据错/数据缺）
    dq = {"未记录": [], "0-60": [], "60-70": [], "70-85": [], "85-100": []}
    for r in jud:
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

    # 校准曲线
    cal = {lab: [] for lab in CONF_LABEL.values()}
    for r in jud:
        c = r.get("confidence") or 0
        for (lo, hi) in CONF_BUCKETS:
            if lo <= c < hi:
                cal[CONF_LABEL[(lo, hi)]].append(r)
                break

    # Brier
    briers = [(_main_prob(r), _outcome(r)) for r in jud if _main_prob(r) is not None]
    brier = (sum((p - o) ** 2 for p, o in briers) / len(briers)) if briers else None

    # 三色
    colors = {"🟢": 0, "🔵": 0, "🟡": 0}
    for r in recs:
        col = r.get("independence_color")
        if col in colors:
            colors[col] += 1

    # 基准覆盖
    bench_filled = sum(1 for r in jud if isinstance(r.get("benchmark"), dict)
                      and any(isinstance(r["benchmark"].get(k), (int, float))
                              for k in ("hold_csi300", "random_dir", "ma_rule")))

    # walk-forward：破底翻按期限分组命中
    wf = {}
    for r in jud:
        if "破底翻" in str(r.get("methodology", "")):
            wf.setdefault(r.get("time_window", "?"), []).append(r)

    # 市场先验 / 与市场共识分歧的命中率（真正的 alpha 读数）
    mp_recs = [r for r in jud if _market_prior(r)]
    div = [r for r in mp_recs
           if isinstance(_market_prior(r).get("divergence_pct"), (int, float))
           and abs(_market_prior(r)["divergence_pct"]) >= 10]
    beat = [r for r in mp_recs
            if (_market_prior(r).get("divergence_pct") or 0) > 0]
    mp = dict(n=len(mp_recs),
              all=_hit_rate(mp_recs),
              divergent_n=len(div),
              divergent=_hit_rate(div),
              beat_n=len(beat),
              beat=_hit_rate(beat))

    return dict(n=n, overall=overall, by_skill=by_skill, by_asset=by_asset,
               by_conf=by_conf, dq=dq, cal=cal, brier=brier, colors=colors,
               bench_filled=bench_filled, wf=wf, mp=mp)


def fmt_rate(t):
    n, r = t
    return "—" if n == 0 else "%.0f%% (%d条)" % (r * 100, n)


def render(recs, quiet):
    due = _due(recs)
    st = stats(recs)
    lines = []
    lines.append("# 预测台账复盘 · %s\n" % TODAY.isoformat())
    lines.append("> 共 %d 条记录；已判定 %d 条；到期待复盘 %d 条。\n"
                % (len(recs), st["n"], len(due)))

    lines.append("## 一、到期待复盘（逐条判对错）\n")
    if due:
    lines.append("| id | 标的 | 方向 | 置信度 | 期限 | 证伪位 | 到期 | 证据快照 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in due:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r.get("id"), r.get("symbol"), r.get("direction"),
            r.get("confidence"), r.get("time_window"),
            r.get("falsification"), r.get("expiry"),
            r.get("evidence_ref") or "—")))
        lines.append("\n回填命令示例：")
        lines.append("`python3 score.py mark %s --status hit --return 8.2`\n"
                    % (due[0].get("id") if due else "P-YYYYMMDD-001"))
    else:
        lines.append("（无到期待复盘记录）\n")

    lines.append("## 二、命中率\n")
    lines.append("- 总体：**%s**" % fmt_rate(st["overall"]))
    lines.append("\n### 按专家 / 来源")
    lines.append("| 来源 | 命中率 |")
    lines.append("|---|---|")
    for k in sorted(st["by_skill"]):
        lines.append("| %s | %s |" % (k, fmt_rate(_hit_rate(st["by_skill"][k]))))
    lines.append("\n### 按资产类别")
    lines.append("| 资产 | 命中率 |")
    lines.append("|---|---|")
    for k in sorted(st["by_asset"]):
        lines.append("| %s | %s |" % (k, fmt_rate(_hit_rate(st["by_asset"][k]))))
    lines.append("\n### 按置信度区间")
    lines.append("| 区间 | 命中率 |")
    lines.append("|---|---|")
    for k in ("≤60", "61-70", "71-80", ">80"):
        lines.append("| %s | %s |" % (k, fmt_rate(_hit_rate(st["by_conf"][k]))))

    lines.append("\n## 三、校准曲线（预测置信度 vs 实际命中）\n")
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

    lines.append("\n## 四、Brier 概率评分\n")
    lines.append("- Brier = **%s**（越低越好；0=完美，0.25=随机）"
                % ("%.3f" % st["brier"] if st["brier"] is not None else "—"))
    lines.append("- 计算口径：主情景概率（多→bull_prob / 空→bear_prob / 中性→base_prob）对实际 0/1 的均方误差。")

    lines.append("\n## 五、独立性三色审计（防回声室）\n")
    c = st["colors"]
    tot = sum(c.values()) or 1
    lines.append("| 颜色 | 含义 | 占比 |")
    lines.append("|---|---|---|")
    lines.append("| 🟢 | 独立推导·恰与专家一致 | %d (%.0f%%) |" % (c["🟢"], c["🟢"] / tot * 100))
    lines.append("| 🔵 | 独立推导·与专家分歧 | %d (%.0f%%) |" % (c["🔵"], c["🔵"] / tot * 100))
    lines.append("| 🟡 | 假说验证中 | %d (%.0f%%) |" % (c["🟡"], c["🟡"] / tot * 100))
    if c["🔵"] == 0 and tot >= 5:
        lines.append("\n⚠️ **回声室警告**：🔵（独立分歧）长期为 0，说明「独立推导」可能在表演，模型顺着人格先验走。")

    lines.append("\n## 六、朴素基准对比（跑赢基准才算有信息量）\n")
    if st["bench_filled"]:
        lines.append("- 已回填基准 %d 条；详见台账 benchmark 字段。" % st["bench_filled"])
    else:
        lines.append("- ⚠️ 尚未回填基准。每次复盘请补填同期：①持有沪深300 收益% ②随机方向 收益% ③简单均线规则 收益%。")
        lines.append("- 若九专家组合扣除交易成本后没跑赢「持有沪深300」，整套机器在增加仪式感而非 alpha。")

    lines.append("\n## 七、Walk-forward 纪律（破底翻经验胜率）\n")
    if st["wf"]:
        lines.append("| 期限 | 命中率 |")
        lines.append("|---|---|")
        for k in sorted(st["wf"]):
            lines.append("| %s | %s |" % (k, fmt_rate(_hit_rate(st["wf"][k]))))
    else:
        lines.append("- 暂无破底翻判定样本。建经验胜率表时务必：参数在前一段定、在后一段验，禁止全历史调参+全历史验证。")

    lines.append("\n## 八、与市场共识分歧的预测命中率（真正 alpha 读数）\n")
    mp = st["mp"]
    if mp["n"]:
        lines.append("- 含市场先验记录：**%d** 条；其中与市场分歧（偏差≥10pct）**%d** 条。" % (mp["n"], mp["divergent_n"]))
        lines.append("- 全部含先验预测命中率：**%s**" % fmt_rate(mp["all"]))
        lines.append("- **分歧预测**（|偏差|≥10pct）命中率：**%s**" % fmt_rate(mp["divergent"]))
        lines.append("- 比市场更确信（偏差>0）的预测命中率：**%s**" % fmt_rate(mp["beat"]))
        lines.append("- 解读：体系的 alpha 不在「跟市场一致时对」，而在「跟市场分歧且对」。分歧预测命中率长期 > 整体命中率 = 你有信息优势；反之 = 在瞎抬杠。")
    else:
        lines.append("- 暂无含 `market_prior` 的判定记录（宏观/事件类评分卡未填 Polymarket 先验）。")

    lines.append("\n## 九、数据质量分 × 命中率（复盘归因三类错误）\n")
    lines.append("| 数据质量分 | 命中率 |")
    lines.append("|---|---|")
    for k in ("0-60", "60-70", "70-85", "85-100", "未记录"):
        lines.append("| %s | %s |" % (k, fmt_rate(_hit_rate(st["dq"][k]))))
    lines.append("\n- 若高质量分区的命中率并不更高，说明瓶颈在推理层而非数据层，应改方法论而不是加信源。")

    lines.append("\n---\n*本文件由 predictions-ledger/score.py 自动生成，判定数据由人工 / mx-moni 回填。*")
    text = "\n".join(lines) + "\n"

    # 控制台摘要
    print("📊 台账复盘 %s" % TODAY.isoformat())
    print("  记录 %d · 已判定 %d · 待复盘 %d" % (len(recs), st["n"], len(due)))
    print("  总体命中率 %s" % fmt_rate(st["overall"]))
    print("  Brier %s · 🔵独立性 %d/%d" % (
        "%.3f" % st["brier"] if st["brier"] is not None else "—",
        c["🔵"], tot))
    if c["🔵"] == 0 and tot >= 5:
        print("  ⚠️ 回声室警告：🔵 长期为 0")
    if st["mp"]["divergent_n"]:
        print("  分歧预测命中率 %s (n=%d)" % (fmt_rate(st["mp"]["divergent"]), st["mp"]["divergent_n"]))

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
    # 重算 brier
    p = _main_prob(target)
    o = _outcome(target)
    target["brier"] = round((p - o) ** 2, 4) if (p is not None and o is not None) else None

    with open(LEDGER, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("✓ 已更新 %s → status=%s actual_return=%s brier=%s"
          % (rec_id, target.get("status"), target.get("actual_return"), target.get("brier")))


def main():
    ap = argparse.ArgumentParser(description="预测台账复盘引擎")
    ap.add_argument("cmd", nargs="?", default="review", choices=["review", "mark"])
    ap.add_argument("rec_id", nargs="?", help="mark 模式的记录 id")
    ap.add_argument("--status", help="hit / miss / partial")
    ap.add_argument("--return", dest="ret", type=float, help="实际区间收益%")
    ap.add_argument("--benchmark", help='基准 JSON，如 \'{"hold_csi300":2.0}\'')
    ap.add_argument("--quiet", action="store_true", help="只打印不写盘")
    args = ap.parse_args()

    if args.cmd == "mark":
        if not args.rec_id:
            sys.stderr.write("✗ mark 需要 rec_id\n")
            sys.exit(2)
        mark(args.rec_id, args.status, args.ret, args.benchmark)
    else:
        render(_load(), args.quiet)


if __name__ == "__main__":
    main()
