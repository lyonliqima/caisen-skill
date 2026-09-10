"""
把选股结果渲染成 HTML 报告（Chart.js 图表 + 漏斗 + 名单）

用法：
    python3 report.py                  # 读取最新 CSV，输出到 stock-screener-output/
    python3 report.py --date 20260830  # 指定日期

⚠️ 实现注意：HTML 里含大量 CSS/JS 大括号，用 f-string 会因大括号转义而报
   SyntaxError（Python 3.12+ 对 f-string 嵌套大括号限制更严）。
   所以模板一律用 __XXX__ 占位符 + str.replace 填充，不要改回 f-string。
"""
import argparse
import glob
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE.parent / "stock-screener-output"

RED = "#d92b2b"
GREEN = "#0f9960"
BLUE = "#2b6cb0"
ORANGE = "#dd6b20"
GRAY = "#718096"


def _latest(pattern: str, date: str = None):
    if date:
        p = OUT_DIR / f"{pattern}_{date}.csv"
        return p if p.exists() else None
    files = sorted(glob.glob(str(OUT_DIR / f"{pattern}_*.csv")))
    return Path(files[-1]) if files else None


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if s is not None else "")


def _fmt(v, nd=2):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return _esc(v)


def _table(df, cols, limit=15) -> str:
    if df is None or not len(df):
        return "<p class='empty'>本次无命中</p>"
    rows = []
    for _, r in df.head(limit).iterrows():
        tds = []
        for c in cols:
            v = r.get(c)
            if c == "代码":
                tds.append(f"<td class='code'>{_esc(v)}</td>")
            elif c == "名称":
                tds.append(f"<td class='nm'>{_esc(v)}</td>")
            else:
                tds.append(f"<td>{_fmt(v)}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    th = "".join(f"<th>{_esc(c)}</th>" for c in cols)
    return (f"<table class='tbl'><thead><tr>{th}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A股统一选股报告 · __DATE_FMT__</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box}
body{margin:0;padding:32px 20px 60px;background:#f7f8fa;color:#1a202c;
     font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
     line-height:1.65}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:26px;margin:0 0 6px;font-weight:700}
.sub{color:#718096;font-size:13px;margin-bottom:26px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:22px 24px;
      margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
h2{font-size:17px;margin:0 0 14px;padding-left:10px;border-left:4px solid __BLUE__}
.alert{background:#fffaf0;border:1px solid #f6ad55;border-left:4px solid __ORANGE__;
       border-radius:8px;padding:14px 18px;margin-bottom:20px;font-size:14px}
.alert b{color:__ORANGE__}
.alert.ok{background:#f0fff4;border-color:#9ae6b4;border-left-color:__GREEN__}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:900px){.grid2{grid-template-columns:1fr}}
table.tbl{width:100%;border-collapse:collapse;font-size:13px}
table.tbl th{background:#edf2f7;padding:9px 8px;text-align:right;font-weight:600;
             border-bottom:2px solid #cbd5e0;white-space:nowrap}
table.tbl th:first-child,table.tbl th:nth-child(2){text-align:left}
table.tbl td{padding:8px;border-bottom:1px solid #edf2f7;text-align:right;
             font-variant-numeric:tabular-nums}
table.tbl td.code{text-align:left;font-family:ui-monospace,Menlo,monospace;color:__GRAY__}
table.tbl td.nm{text-align:left;font-weight:600}
table.tbl tbody tr:hover{background:#f7fafc}
.empty{color:__GRAY__;font-size:14px;padding:8px 0}
.note{font-size:12.5px;color:#718096;margin-top:10px;line-height:1.7}
.note ul{margin:8px 0 0;padding-left:20px}
.note li{margin-bottom:5px}
ul{margin:8px 0 0;padding-left:20px}
li{margin-bottom:5px}
.kpi{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
@media(max-width:900px){.kpi{grid-template-columns:repeat(2,1fr)}}
.kpi div{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px;text-align:center}
.kpi .v{font-size:26px;font-weight:700;line-height:1.2}
.kpi .l{font-size:12px;color:#718096;margin-top:4px}
</style></head><body><div class="wrap">

<h1>A股统一选股报告</h1>
<div class="sub">数据截至 __DATE_FMT__ 收盘 · 三策略交叉验证 · 破底翻（左侧）× 碗口反弹（右侧）× Mi姐三维（确认）</div>

<div class="kpi">
  <div><div class="v">__SCANNED__</div><div class="l">扫描股票</div></div>
  <div><div class="v" style="color:__RED__">__N_PODI__</div><div class="l">破底翻命中</div></div>
  <div><div class="v" style="color:__BLUE__">__N_BOWL__</div><div class="l">碗口反弹命中</div></div>
  <div><div class="v" style="color:__GREEN__">__N_CROSS__</div><div class="l">交叉命中（最强）</div></div>
</div>

__ALERT__

<div class="grid2">
  <div class="card"><h2>选股漏斗</h2><canvas id="funnel" height="260"></canvas></div>
  <div class="card"><h2>各策略命中率对比</h2><canvas id="rate" height="260"></canvas></div>
</div>

<div class="card">
  <h2>综合排名 Top 15（交叉加权后）</h2>
  __T_COMBO__
  <div class="note">综合分 = 最强策略分 + (命中策略数-1) × 12；盈亏比 &lt; 2:1 的自动打八折。</div>
</div>

__CROSS_BLOCK__

<div class="grid2">
  <div class="card"><h2>破底翻 Top 15（左侧·底部反转）</h2>
    __T_PODI__
    <div class="note">左侧抄底：创新低后翻回前低，或守住前低站稳 N 天。
    含 A 类「破底翻」与 B 类「守住前低」。</div>
  </div>
  <div class="card"><h2>碗口反弹 Top 15（右侧·趋势回踩）</h2>
    __T_BOWL__
    <div class="note">右侧回调：上升趋势中回踩支撑 + KDJ 的 J 值超卖 + 近期有放量阳线。
    「回落碗中」= 价格夹在多空线与短期趋势线之间，是最强分类。</div>
  </div>
</div>

<div class="card">
  <h2>方法与局限</h2>
  <div class="note" style="font-size:13px">
  <ul>
    <li><b>三策略为什么不能合并成一套</b>：破底翻在单边下跌市假信号极多；碗口反弹在底部区域
        几乎筛不出票（它要求短期趋势线在多空线上方）；Mi姐最严但常日可能 0 命中。
        三者互为补集，交叉命中才是强信号。</li>
    <li><b>本引擎只看技术面与量能</b>，不含基本面、财报质量、行业景气度。
        入选不等于可以买，需过风控排雷与基本面复核。</li>
    <li><b>止损位是纪律不是建议</b>。破底翻止损锚定前低下方（跌回前低即证伪）；
        碗口反弹锚定多空线下方或 1×ATR。</li>
    <li><b>数据源</b>：新浪免费接口，偶有缺失。本次 __SCANNED__ 只中 __GOT_KLINE__ 只取到完整日K
        （__KLINE_PCT__%），未取到的多为停牌或长期停牌股。</li>
    <li>本报告为量化筛选结果，不构成投资建议。</li>
  </ul>
  </div>
</div>

<script>
const gridC='#e2e8f0', tickC='#4a5568';
new Chart(document.getElementById('funnel'), {
  type:'bar',
  data:{labels:['扫描股票','取到完整日K','破底翻命中','碗口反弹命中','Mi姐命中','交叉命中'],
    datasets:[{label:'股票数',
      data:[__SCANNED__,__GOT_KLINE__,__N_PODI__,__N_BOWL__,__N_MI__,__N_CROSS__],
      backgroundColor:['#cbd5e0','#a0aec0','__RED__','__BLUE__','#9ae6b4','#f6ad55'],
      borderRadius:4}]},
  options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false},title:{display:true,text:'从全市场到最终名单'}},
    scales:{x:{grid:{color:gridC},ticks:{color:tickC}},
            y:{grid:{display:false},ticks:{color:tickC}}}}
});
new Chart(document.getElementById('rate'), {
  type:'bar',
  data:{labels:['破底翻','碗口反弹','Mi姐三维','交叉命中'],
    datasets:[{label:'占有效样本比例 (%)',
      data:[__R_PODI__,__R_BOWL__,__R_MI__,__R_CROSS__],
      backgroundColor:['__RED__','__BLUE__','#9ae6b4','#f6ad55'],borderRadius:4}]},
  options:{responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false},title:{display:true,text:'命中率（占 __GOT_KLINE__ 只有效样本）'}},
    scales:{y:{grid:{color:gridC},ticks:{color:tickC,callback:function(v){return v+'%';}}},
            x:{grid:{display:false},ticks:{color:tickC}}}}
});
</script>
</div></body></html>"""


def build_html(date: str = None) -> str:
    f_podi = _latest("破底翻", date)
    f_bowl = _latest("碗口反弹", date)
    f_mi = _latest("Mi姐三维", date)
    f_combo = _latest("综合", date)
    if not f_combo:
        raise SystemExit("找不到综合结果 CSV，请先运行 screener.py")

    combo = pd.read_csv(f_combo, dtype={"代码": str})
    podi = pd.read_csv(f_podi, dtype={"代码": str}) if f_podi else pd.DataFrame()
    bowl = pd.read_csv(f_bowl, dtype={"代码": str}) if f_bowl else pd.DataFrame()
    mi = pd.read_csv(f_mi, dtype={"代码": str}) if f_mi else pd.DataFrame()

    run_date = f_combo.stem.split("_")[-1]
    date_fmt = f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}"

    scanned = int(combo["扫描总数"].iloc[0]) if "扫描总数" in combo.columns else len(combo)
    got = int(combo["有效K线数"].iloc[0]) if "有效K线数" in combo.columns else len(combo)
    denom = max(got, 1)

    n_podi, n_bowl, n_mi = len(podi), len(bowl), len(mi)
    cross = combo[combo["命中数"] >= 2] if "命中数" in combo.columns else pd.DataFrame()
    n_cross = len(cross)

    # 顶部警示：Mi姐 0 命中是市场状态信号，不是程序故障
    if n_mi == 0:
        alert = f"""<div class="alert">
  <b>⚠️ 市场状态警示：Mi姐三维策略全市场 0 命中。</b><br>
  Mi姐要求完美多头排列 —— 收盘价 &gt; 年线(MA250)，且 MA5&gt;MA10&gt;MA20&gt;MA60&gt;MA250，
  且站上周线60周线。<b>全市场 {got} 只股票没有一只满足</b>。这不是程序故障，
  而是市场处于<b>普跌、无主线</b>状态的硬证据。
  <ul>
    <li><b>右侧追高（碗口反弹类）胜率显著下降</b> —— 缺乏趋势支撑，反弹往往短命，仓位应下调</li>
    <li><b>左侧抄底（破底翻类）假信号率上升</b> —— 破底翻命中 {n_podi} 只
        （占 {n_podi/denom*100:.1f}%），说明大量个股深度下跌，
        但"跌得多"不等于"跌到位"，止损纪律必须严格执行</li>
    <li>交叉命中的 {n_cross} 只相对最扎实：既完成了底部结构，又已转出多头趋势</li>
  </ul>
</div>"""
    else:
        alert = (f'<div class="alert ok"><b>✓ Mi姐三维命中 {n_mi} 只</b> —— '
                 f'市场存在明确多头排列个股，右侧策略环境相对健康。</div>')

    cross_block = ""
    if n_cross:
        cross_block = f"""
<div class="card">
  <h2>⭐ 交叉命中（多策略共振，最值得看）</h2>
  {_table(cross, ["代码", "名称", "命中策略", "score", "最新价", "止损位", "目标位",
                  "盈亏比", "J值", "类型", "分类"], min(n_cross, 15))}
  <div class="note">同时被破底翻（底部结构成立）与碗口反弹（趋势已转多）命中，
  是本引擎认为信号强度最高的一类。</div>
</div>"""

    rep = {
        "__DATE_FMT__": date_fmt,
        "__SCANNED__": str(scanned),
        "__GOT_KLINE__": str(got),
        "__KLINE_PCT__": f"{got/max(scanned,1)*100:.0f}",
        "__N_PODI__": str(n_podi), "__N_BOWL__": str(n_bowl),
        "__N_MI__": str(n_mi), "__N_CROSS__": str(n_cross),
        "__R_PODI__": f"{n_podi/denom*100:.2f}", "__R_BOWL__": f"{n_bowl/denom*100:.2f}",
        "__R_MI__": f"{n_mi/denom*100:.2f}", "__R_CROSS__": f"{n_cross/denom*100:.2f}",
        "__ALERT__": alert,
        "__CROSS_BLOCK__": cross_block,
        "__T_COMBO__": _table(combo, ["代码", "名称", "命中策略", "score",
                                      "最新价", "止损位", "目标位", "盈亏比"], 15),
        "__T_PODI__": _table(podi, ["代码", "名称", "类型", "score", "最新价", "前低支撑",
                                    "站稳天数", "距年高跌幅%", "历史分位%", "止损位", "盈亏比"], 15),
        "__T_BOWL__": _table(bowl, ["代码", "名称", "分类", "score", "最新价", "J值",
                                    "放量倍数", "趋势强度%", "止损位", "目标位", "盈亏比"], 15),
        "__RED__": RED, "__GREEN__": GREEN, "__BLUE__": BLUE,
        "__ORANGE__": ORANGE, "__GRAY__": GRAY,
    }
    html = TEMPLATE
    for k, v in rep.items():
        html = html.replace(k, v)
    return html


def main():
    ap = argparse.ArgumentParser(description="生成选股 HTML 报告")
    ap.add_argument("--date", default=None, help="结果日期 YYYYMMDD，默认取最新")
    ap.add_argument("--out", default=None, help="输出文件路径")
    args = ap.parse_args()

    html = build_html(args.date)
    ts = args.date or datetime.now().strftime("%Y%m%d")
    out = Path(args.out) if args.out else OUT_DIR / f"选股报告_{ts}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ 报告已生成：{out}")
    return str(out)


if __name__ == "__main__":
    main()
