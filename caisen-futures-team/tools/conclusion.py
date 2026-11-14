# -*- coding: utf-8 -*-
"""
期货团 · 结论生成器（R1–R5 执行器 · 2026-11-08 立 / 2026-11-10 补 R5）

依据：`caisen-futures-team/references/闸门执行修订-20261108.md`
用途：把「今日是否建仓 / 开多少仓」从**模板文案**改成**由 exec_score 对显式阈值推导**。
      替代 `_runs/shortscan_20261108/gen_report.py:89` 那类硬编码 hero。

设计约束（与修订文件一致）：
  - R1 时间闸按计划持有期分档：≤5 日 ≥20 交易日 / 20 日 ≥45 / ≥60 日及长持 ≥90。
  - R2 风险成本化：六闸 ✗ 折算乘性/减性 penalty，仅 H1/H2/H3 保留硬否决；「数据不可得」≠「证据 ✗」。
  - R3 三态：exec_score ≥60 可开仓 / 45–60 可证伪试仓 / <45 观望且必写量化改善清单。
  - R4 观望也必须落一条带 entry_price 的可结算台账记录（本模块只输出字段，落账仍用
    `predictions-ledger/append.py`）。
  - R5 三态硬约束（2026-11-10 补实现）：45–60 区间**还须** direction_score ≥60 且 RR ≥1.5
    才能判「可证伪试仓」，否则按 R5.1「其余 → 观望」降级。此前版本只按 exec_score 判态，
    会把 ZN2701（exec 45.1 / dir 50.1 / RR 1.38）误判为可试仓，属执行器缺口。
    `--no-enforce-r5` 可复现 11-08 的旧口径，仅用于归档对照，不得用于新报告。

用法：
  python3 conclusion.py --scan _runs/shortscan_20261108/scan.json \
      --holding-days 5 --out _runs/shortscan_20261108/r2_check.json

  # 模板合规校验（在生成 HTML 前调用）
  from conclusion import assert_no_hardcoded
  assert_no_hardcoded(template_html)

⚠️ 口径声明：`scan.json` 的 `days_left` 为**自然日**口径；本模块按 5/7 折算为估算交易日，
   输出中同时给出两者并标注 `trading_days_estimated=True`。下一轮必须改为交易日历精确计算，
   不得把估算值当精确值引用。
"""
import argparse
import json

TH_OPEN = 60.0     # R3.1 可开仓阈值
TH_TRIAL = 45.0    # R3.1 可证伪试仓阈值
TH_R5_DIR = 60.0   # R5.1 试仓附加门槛：方向分
TH_R5_RR = 1.5     # R5.1 试仓附加门槛：盈亏比
CAL_TO_TRADING = 5.0 / 7.0

# R1：计划持有期（日）→ 距死线交易日下限
R1_BANDS = ((5, 20), (20, 45), (60, 90))

# 禁止出现在报告模板里的结论串（R3.2）
FORBIDDEN = (
    "零新建空单", "今日不建仓", "现在不下单", "不扣扳机",
    "无合规合约", "今日零新建", "不建仓（含远月）",
)


def r1_required(holding_days):
    """R1：由评分卡的「期限」字段确定时间闸下限（交易日）。"""
    for h, req in R1_BANDS:
        if holding_days <= h:
            return req
    return 90


def trading_days(row, day_unit="calendar"):
    d = row.get("days_left")
    if d is None:
        return None
    return float(d) if day_unit == "trading" else float(d) * CAL_TO_TRADING


def compute_exec(row, holding_days=5, day_unit="calendar", market_open=True,
                 price_traceable=True):
    """R1+R2：返回单合约的可开仓分与扣分明细。"""
    dl = trading_days(row, day_unit)
    req = r1_required(holding_days)
    veto = None
    if dl is None or dl < 20:
        veto = "H1 距自然人/法人最后平仓日 <20 交易日"
    elif (row.get("vol") or 0) <= 0 or (row.get("oi") or 0) <= 0:
        veto = "H2 无报价 / 无法成交"
    elif not price_traceable:
        veto = "H3 关键价格无法追溯到来源+时间戳"
    if veto:
        return dict(sym=row.get("sym"), exec_score=0.0, veto=veto,
                    hits=[], mult=0.0, penalty=0,
                    direction_score=float(row.get("direction_score") or 0),
                    rr=round(float(row.get("rr") or 0), 2),
                    days_left=row.get("days_left"), trading_days_est=None if dl is None else round(dl, 1),
                    r1_required=req)

    d = float(row.get("direction_score") or 0)
    m, p, hits = 1.0, 0.0, []

    def mul(code, why, factor):
        nonlocal m
        m *= factor
        hits.append(dict(code=code, why=why, kind="mult", value=factor))

    def sub(code, why, points):
        nonlocal p
        p += points
        hits.append(dict(code=code, why=why, kind="sub", value=-points))

    # G3-t：R1 分档不达标（但 >=20，否则已被 H1 否决）
    if dl < req:
        mul("G3-t", "R1 分档不达标 %.0f < %d 交易日" % (dl, req), 0.50)
    # G3-l：流动性
    if not row.get("g_liq"):
        mul("G3-l", "成交 < 主力 5% 或持仓 <2 万手", 0.40)
    # G3-c：换月成本
    # R2 补实现（2026-11-08 二次修正）：carry 数据不可得 ≠ 证据 ✗。
    # scan.py 把 carry_ann=None 的合约一律记为 g_carry=False，若照单全扣 ×0.70，
    # 等于用「数据缺失」做全市场惩罚，违反 R2「数据不可得只扣 5 分、该证据不计票」。
    # 真实超阈才罚；缺失统一交给 P-na 扣 5 分，不重复计罚。
    car = row.get("carry_ann")
    if car is None:
        pass
    elif abs(car) > 0.05:
        mul("G3-c", "到接续合约年化租 >5%%（%.1f%%）" % (car * 100), 0.70)
    # G3-s：期限结构
    sr = row.get("struct_risk")
    if sr not in (None, "flat", "NA", ""):
        mul("G3-s", "期限结构 %s" % sr, 0.50)
    # G4-a：60 天内第 2 次同向且无「上次错在哪」段落
    if row.get("g4_flag"):
        mul("G4-a", "60 天内同向且无上次错因段落", 0.50)
    # G4-b：逾期未结算（不阻断，只扣分）
    if (row.get("prior_unsettled") or 0) > 0:
        mul("G4-b", "同品种存在 %d 条逾期未结算" % row["prior_unsettled"], 0.80)
    # G5：位置三口径失效
    if not row.get("g5_ok"):
        mul("G5", "三口径 gap≥25pp，位置因子失效", 0.80)
    # P-rr：赔率
    rr = row.get("rr") or 0
    if rr < 1.0:
        mul("P-rr", "RR %.2f <1（方向分先折减）" % rr, 0.75)
        sub("P-rr", "RR<1 减分", 10)
    # P-fill：无法即时成交（左侧挂单 / 非交易日）
    if not market_open:
        sub("P-fill", "当日非交易日 / 挂单为左侧条件单", 10)
    # P-na：数据不可得（不计票，只扣 5 分，禁止当 ✗ 证据）
    sub("P-na", "席位双边总量等数据不可得，该证据不计票", 5)

    score = max(0.0, min(100.0, d * m - p))
    return dict(sym=row.get("sym"), exec_score=round(score, 1), veto=None,
                hits=hits, mult=round(m, 4), penalty=p,
                direction_score=d, rr=round(rr, 2),
                days_left=row.get("days_left"),
                trading_days_est=round(dl, 1), r1_required=req)


def r5_trial_ok(x):
    """R5.1：45–60 区间的合约，还须 direction_score ≥60 且 RR ≥1.5 才可试仓。"""
    return (float(x.get("direction_score") or 0) >= TH_R5_DIR
            and float(x.get("rr") or 0) >= TH_R5_RR)


def gap_list(best, th=TH_TRIAL):
    """R3.1：观望/试仓态下，列「距离开仓还差什么」——逐项算移除该 penalty 能补回多少分。"""
    if not best or best.get("veto"):
        return []
    d, m, p = best["direction_score"], best["mult"], best["penalty"]
    base = max(0.0, d * m - p)
    out = []
    for h in best["hits"]:
        if h["kind"] == "mult":
            recover = max(0.0, d * (m / h["value"]) - p) - base
        else:
            recover = max(0.0, d * m - (p + h["value"])) - base
        out.append(dict(code=h["code"], why=h["why"],
                        recover_points=round(recover, 1)))
    out.sort(key=lambda z: -z["recover_points"])
    return dict(need_to_trial=round(max(0.0, th - base), 1),
                need_to_open=round(max(0.0, TH_OPEN - base), 1),
                items=out[:8])


def build_conclusion(rows, holding_days=5, day_unit="calendar",
                     market_open=True, price_traceable=True, enforce_r5=True):
    """R3 + R5：由 max(exec_score) 对阈值生成结论，禁止任何硬编码结论串。

    R5.1 三态：exec≥60 可开仓 / 45–60 且 dir≥60 且 RR≥1.5 可证伪试仓 / 其余观望。
    `enforce_r5=False` 只用于复现 11-08 旧口径做归档对照，不得用于新报告。
    """
    scored = [compute_exec(r, holding_days, day_unit, market_open, price_traceable)
              for r in rows]
    valid = [x for x in scored if x["veto"] is None]
    n_veto = len(scored) - len(valid)
    best = max(valid, key=lambda z: z["exec_score"]) if valid else None
    max_exec = best["exec_score"] if best else 0.0
    best_sym = best["sym"] if best else "—"

    open_pool = [x for x in valid if x["exec_score"] >= TH_OPEN]
    trial_raw = [x for x in valid if TH_TRIAL <= x["exec_score"] < TH_OPEN]
    trial_ok = [x for x in trial_raw if r5_trial_ok(x)] if enforce_r5 else trial_raw
    ok_syms = {x["sym"] for x in trial_ok}
    rejected = [x for x in trial_raw if x["sym"] not in ok_syms]

    if open_pool:
        state, action = "可开仓", "单品种 ≤3% 名义；须给入场/止损/目标/证伪位/结算日"
    elif trial_ok:
        state, action = "可证伪试仓", "≤1% 名义、止损 ×0.6、≤5 日、须落台账 trial=1"
    else:
        state, action = "观望", "必写量化改善清单；并落一条带 entry_price 的可结算台账记录"

    r5 = dict(enforced=bool(enforce_r5),
              dir_threshold=TH_R5_DIR, rr_threshold=TH_R5_RR,
              trial_pool_raw=len(trial_raw), trial_pool_ok=len(trial_ok),
              n_downgraded=len(rejected),
              rejected=[dict(sym=x["sym"], exec_score=x["exec_score"],
                             direction_score=x["direction_score"], rr=x["rr"],
                             why="%s%s" % (
                                 "dir<60 " if x["direction_score"] < TH_R5_DIR else "",
                                 "RR<1.5" if x["rr"] < TH_R5_RR else ""))
                        for x in rejected])

    hero = ("结论：%s｜全市场最高可开仓分 %.1f/100（%s）｜阈值 60 / 45｜计划持有期 %d 日"
            % (state, max_exec, best_sym, holding_days))
    top_dir = max(scored, key=lambda z: z["direction_score"]) if scored else None

    return dict(
        rule="闸门执行修订-20261108.md R1/R2/R3/R5",
        generated_from="exec_score + R5 复判（非模板硬编码）",
        hero=hero, state=state, action=action,
        max_exec_score=max_exec, best_sym=best_sym,
        th_open=TH_OPEN, th_trial=TH_TRIAL,
        holding_days=holding_days,
        r1_required_trading_days=r1_required(holding_days),
        day_unit=day_unit,
        trading_days_estimated=(day_unit == "calendar"),
        n_rows=len(scored), n_hard_veto=n_veto,
        n_open=len(open_pool),
        n_trial=len(trial_ok),
        n_watch=len(valid) - len(open_pool) - len(trial_ok),
        r5=r5,
        direction_leader=dict(sym=top_dir["sym"], direction_score=top_dir["direction_score"],
                              exec_score=top_dir["exec_score"],
                              veto=top_dir["veto"]) if top_dir else None,
        best=best,
        gap=gap_list(best),
        top10=sorted(valid, key=lambda z: -z["exec_score"])[:10],
    )


def assert_no_hardcoded(template_text):
    """R3.2：模板里出现写死的结论串即抛错（报告作废重生成）。"""
    found = [s for s in FORBIDDEN if s in template_text]
    if found:
        raise ValueError("R3.2 违规：报告模板硬编码结论串 %s；结论必须由 exec_score 推导" % found)
    return True


def main():
    ap = argparse.ArgumentParser(description="由 exec_score + R5 复判生成期货结论（R1–R5）")
    ap.add_argument("--scan", required=True, help="scan.json 路径")
    ap.add_argument("--holding-days", type=int, default=5, help="评分卡的期限（日）")
    ap.add_argument("--day-unit", choices=("calendar", "trading"), default="calendar")
    ap.add_argument("--market-open", action="store_true", default=False,
                    help="当日可即时成交（默认否，扣 P-fill）")
    ap.add_argument("--no-enforce-r5", action="store_true", default=False,
                    help="关闭 R5 附加门槛（仅用于复现 11-08 旧口径，不得用于新报告）")
    ap.add_argument("--out", help="结果 JSON 输出路径")
    a = ap.parse_args()

    d = json.load(open(a.scan, encoding="utf-8"))
    rows = d["rows"] if isinstance(d, dict) else d
    res = build_conclusion(rows, a.holding_days, a.day_unit, a.market_open,
                           enforce_r5=not a.no_enforce_r5)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    print(res["hero"])
    print("态=%s｜可开仓 %d / 试仓 %d / 观望 %d｜硬否决 %d / 共 %d"
          % (res["state"], res["n_open"], res["n_trial"], res["n_watch"],
             res["n_hard_veto"], res["n_rows"]))
    print("方向分最高：%s %s（可开仓分 %s，否决 %s）"
          % (res["direction_leader"]["sym"], res["direction_leader"]["direction_score"],
             res["direction_leader"]["exec_score"], res["direction_leader"]["veto"]))
    if res["r5"]["enforced"] and res["r5"]["n_downgraded"]:
        print("R5 复判：45–60 区间 %d 个，仅 %d 个达标；被打回：%s"
              % (res["r5"]["trial_pool_raw"], res["r5"]["trial_pool_ok"],
                 ", ".join("%s(exec %.1f/dir %.1f/RR %.2f)"
                           % (x["sym"], x["exec_score"], x["direction_score"], x["rr"])
                           for x in res["r5"]["rejected"])))
    print("距试仓阈值还差 %.1f 分，距可开仓阈值还差 %.1f 分"
          % (res["gap"]["need_to_trial"], res["gap"]["need_to_open"]))
    for it in res["gap"]["items"][:5]:
        print("  可补回 %5.1f 分 ← %s %s" % (it["recover_points"], it["code"], it["why"]))


if __name__ == "__main__":
    main()
