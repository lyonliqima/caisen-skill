"""
资本三流 —— 每日监控编排器
============================
采集 → 计算 → 生成报告（JSON + Markdown），可选启动 Streamlit 大屏。

用法：
  python monitor.py                 # 真实采集（需 akshare + 网络）
  python monitor.py --demo          # 离线样例数据，验证整条流水线
  python monitor.py --demo --dashboard   # 样例 + 启动大屏
  python monitor.py --force         # 强制刷新缓存
  python monitor.py --output DIR    # 指定报告输出目录

说明：真实采集依赖 akshare（pip install akshare）与可访问的数据源；
沙箱/离线环境请用 --demo。数据缺失项会在报告中标注，绝不编造。
"""

import os
import sys
import json
import argparse
from datetime import datetime, date

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))

from collector import collect
from calculator import run_all

REPORTS_DIR = os.path.join(SKILL_DIR, "reports")


def write_reports(result: dict, output_dir: str) -> tuple:
    os.makedirs(output_dir, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    json_path = os.path.join(output_dir, f"capital_three_flow_{today}.json")
    md_path = os.path.join(output_dir, f"capital_three_flow_{today}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    md = render_markdown(result)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    return json_path, md_path


def render_markdown(r: dict) -> str:
    as_of = r.get("as_of", str(date.today()))
    demo = "（DEMO 样例数据）" if r.get("demo") else ""
    vol = r.get("volume", {})
    vel = r.get("velocity", {})
    dr = r.get("direction", {})
    idx = r.get("indices", {})
    sc = r.get("score", {})

    def fmt(v, unit=""):
        if v is None:
            return "缺失"
        return f"{v}{unit}"

    lines = []
    lines.append(f"# 资本三流每日观测报告 {demo}")
    lines.append(f"\n**观测日期**：{as_of}  \n**底层逻辑**：费雪方程式 M·V=P·Q 三流拆解（流量/流向/流速）\n")
    if r.get("north_flow_note"):
        lines.append(f"> ⚠️ {r['north_flow_note']}\n")
    # 缺失分项提示（已剔除并重新归一化，缺失为空时不输出该行）
    missing = idx.get("missing_components") or []
    if missing:
        lines.append(f"> **本期缺失分项**：{'、'.join(missing)}（已剔除并重新归一化）\n")
    lines.append("## 一、三维核心指标")
    lines.append("| 维度 | 指标 | 数值 |")
    lines.append("|------|------|------|")
    lines.append(f"| 流量 | M2（同比） | {fmt(vol.get('m2'), ' '+str(vol.get('m2_unit','')))}（同比 {fmt(vol.get('m2_yoy'),'%')}） |")
    lines.append(f"| 流量 | 大盘主力净流入 | {fmt(vol.get('main_force_net_inflow'),' 亿元')} |")
    lines.append(f"| 流量 | 融资融券余额(Δ) | {fmt(vol.get('margin_total'),' 亿元')}（变动 {fmt(vol.get('margin_delta'),' 亿元')}） |")
    lines.append(f"| 流速 | 货币流通速度 V=GDP/M2 | {fmt(vel.get('V_macro'))} |")
    lines.append(f"| 流速 | 货币乘数 M2/基础货币 | {fmt(vel.get('money_multiplier'))} |")
    lines.append(f"| 流向 | 市场净流向系数 D_market | {fmt(dr.get('D_market'))} |")
    lines.append(f"| 流向 | 跨境流向系数 D_fx(外储Δ) | {fmt(dr.get('D_fx'))} |")
    # 人民币汇率（外部压力代理）
    fxr = r.get("fx_rate") or {}
    if fxr:
        lines.append(f"| 流向(外部) | 人民币汇率 USD/CNY | {fmt(fxr.get('rate'))}（当日 {fmt(fxr.get('change_pct'),'%')}） |")
    else:
        lines.append(f"| 流向(外部) | 人民币汇率 USD/CNY | 缺失 |")
    # 板块资金流 HHI（细分层级集中度）
    hhi = dr.get('HHI')
    scnt = dr.get('sector_count')
    hnote = dr.get('HHI_note')
    if hhi is not None:
        hhi_label = "高度集中" if (hhi >= 0.18) else ("分散" if (hhi <= 0.08) else "中度集中")
        lines.append(f"| 流向 | 板块资金流 HHI（{scnt}行业） | {hhi}（{hhi_label}） |")
    else:
        lines.append(f"| 流向 | 板块资金流 HHI | 缺失（{hnote or '无数据'}） |")
    lines.append("")
    lines.append("## 二、三个合成指数")
    lines.append("| 指数 | 含义 | 数值 | 解读 |")
    lines.append("|------|------|------|------|")
    lines.append(f"| CFCI | 资本流向综合 (-100~+100) | {fmt(idx.get('CFCI'))} | 正=净流入主导，负=净流出主导 |")
    lines.append(f"| CFEI | 资本流转效率 | {fmt(idx.get('CFEI'))} | 越高=周转效率越好，空转越少 |")
    lines.append(f"| CRI  | 走资风险 (0~100) | {fmt(idx.get('CRI'))} | 越高=外逃/沉没风险越大 |")
    lines.append("")
    lines.append("## 三、三流共振判定")
    lines.append(f"- 流量打分 S_flow：{sc.get('S_flow')}")
    lines.append(f"- 流速打分 S_velocity：{sc.get('S_velocity')}")
    lines.append(f"- 流向打分 S_direction：{sc.get('S_direction')}")
    lines.append(f"- **综合得分 S = {sc.get('S_total')}**")
    lines.append(f"- **结论**：{sc.get('verdict')}")
    if sc.get("notes"):
        for n in sc["notes"]:
            lines.append(f"  - 注：{n}")
    lines.append("")

    # ── 股票交易参考（方法论翻译，非投资建议）──
    tr = r.get("trading_reference") or {}
    if tr:
        lines.append("## 四、股票交易参考（方法论翻译，非投资建议）")
        lines.append(f"- **流动性背景（仓位参考）**：{tr.get('liquidity_regime')}")
        lines.append(f"  - {tr.get('liquidity_detail')}")
        lines.append(f"- **资本流向（多空参考）**：{tr.get('risk_appetite')}")
        lines.append(f"  - 跨境：{tr.get('cross_flow')}")
        lines.append(f"  - A股内部：{tr.get('internal_preference')}")
        lines.append(f"  - 板块净流入合计：{fmt(tr.get('sector_net_sum'), ' 亿元')}（{tr.get('sector_count')} 行业）")
        lines.append(f"- **微观流速（策略参考）**：{tr.get('micro_velocity_note')}")
        lines.append(f"- **策略倾向**：{tr.get('strategy_tilt')}")
        top = tr.get("sector_top") or []
        bot = tr.get("sector_bottom") or []
        if top or bot:
            lines.append("")
            lines.append("**板块资金多空榜**（净流入排序，单位依数据源，仅作方向参考）")
            lines.append("| 方向 | 行业 | 净流入 | 当日涨跌幅 |")
            lines.append("|------|------|--------|------------|")
            for s in top:
                lines.append(f"| 多 | {s.get('name')} | {fmt(s.get('net'))} | {fmt(s.get('pct'), '%')} |")
            for s in bot:
                lines.append(f"| 空 | {s.get('name')} | {fmt(s.get('net'))} | {fmt(s.get('pct'), '%')} |")
        lines.append("")

    # ── 向心坍缩全球风险早期预警（卢麒元 M3 扩展）──
    cr = r.get("collapse_risk") or {}
    if cr:
        lines.append("## 五、向心坍缩全球风险早期预警（卢麒元 M3 扩展）")
        lines.append(f"- **当前阶段判定**：**{cr.get('stage')}**")
        c = cr.get("counts", {})
        lines.append(f"- **分级计数**：观察预警 {c.get('watch')} ｜ 风险升温 {c.get('warm')} ｜ "
                     f"坍缩临界点 {c.get('critical')} ｜ 平稳 {c.get('normal')} ｜ 缺失/手动 {c.get('missing')}")
        cats = cr.get("catalysts") or []
        if cats:
            lines.append(f"- ⚠️ **已触发坍缩重大催化项**：{', '.join(cats)} → 直接上调至加速坍缩预警")
        if cr.get("cftc_jpy_unwind"):
            lines.append("- ⚠️ CFTC 日元投机空头连续两周快速回落（套息平仓前兆）")
        rows = cr.get("indicators", []) or []
        if rows:
            lines.append("")
            lines.append("| 指标 | 数值 | 级别 | 组 |")
            lines.append("|------|------|------|----|")
            for it in rows:
                v = it.get("value")
                vstr = f"{v}{it.get('unit') or ''}" if v is not None else "缺失/手动"
                lines.append(f"| {it.get('name')} | {vstr} | {it.get('level')} | {it.get('group')} |")
        # 屏障观测（不触发崩盘阈值，区分外部冲击 vs 本土风险）
        tr = cr.get("transmission") or {}
        tr_on = [k for k, v in tr.items() if v]
        if tr_on:
            lines.append("")
            lines.append(f"- **国内传导屏障观测（已触发）**：{', '.join(tr_on)}")
        lines.append("")
        lines.append("> 判定纪律：单一指标越线 ≠ 风险成立；须多指标同步突破临界区间，方判踩踏进入加速阶段。"
                     "越靠前组（日元套息/美元流动性）越具先导性。完整阈值见 lu-qiyuan-analysis/references/collapse-risk-indicators.md。")
        lines.append("")

    lines.append("## 六、数据说明与免责声明")
    lines.append("> 数据源：akshare（M2/GDP/外储/基础货币/融资融券/主力资金/人民币汇率/板块资金流），函数名见 references/data_sources.md。")
    lines.append("> 北向/南向净流量自2024-08-19起停更、akshare已移除；跨境流向以外汇储备变动代理，并辅以人民币汇率(USD/CNY)作外部贬值压力代理。")
    lines.append("> 板块资金流 HHI 由行业主力净流入分布计算，衡量资金集中度（越高越集中少数板块）。")
    if not idx.get("cri_usdcny_available"):
        lines.append("> ⚠️ 人民币汇率缺失，CRI 仅由外汇储备变动计算。")
    lines.append("> 以上仅为基于卢麒元资本三流框架的方法论量化演示，不构成任何投资建议；缺失项已标注\"缺失\"。")
    return "\n".join(lines) + "\n"


def maybe_launch_dashboard():
    try:
        import subprocess
        dashboard = os.path.join(SKILL_DIR, "scripts", "dashboard.py")
        subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", dashboard],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print("[monitor] Streamlit 大屏已启动，浏览器打开 http://localhost:8501")
    except Exception as e:
        print(f"[monitor] 启动大屏失败（需安装 streamlit）：{e}")


def main():
    ap = argparse.ArgumentParser(description="资本三流每日监控")
    ap.add_argument("--demo", action="store_true", help="使用离线样例数据")
    ap.add_argument("--force", action="store_true", help="强制刷新缓存")
    ap.add_argument("--dashboard", action="store_true", help="完成后启动 Streamlit 大屏")
    ap.add_argument("--output", default=REPORTS_DIR, help="报告输出目录")
    ap.add_argument("--quiet", action="store_true", help="不打印摘要")
    args = ap.parse_args()

    raw = collect(demo=args.demo, force=args.force)
    result = run_all(raw)
    json_path, md_path = write_reports(result, args.output)

    if not args.quiet:
        sc = result.get("score", {})
        print(f"[monitor] 观测日期: {result.get('as_of')}  demo={result.get('demo')}")
        print(f"[monitor] CFCI={result['indices']['CFCI']}  CFEI={result['indices']['CFEI']}  CRI={result['indices']['CRI']}")
        print(f"[monitor] 三流得分 S={sc.get('S_total')} → {sc.get('verdict')}")
        cr = result.get("collapse_risk") or {}
        if cr:
            cc = cr.get("counts", {})
            print(f"[monitor] 向心坍缩风险阶段：{cr.get('stage')} "
                  f"（观察 {cc.get('watch')} / 升温 {cc.get('warm')} / 临界 {cc.get('critical')}）")
        print(f"[monitor] 报告: {md_path}")
        print(f"[monitor] 数据: {json_path}")

    if args.dashboard:
        maybe_launch_dashboard()

    return result


if __name__ == "__main__":
    main()
