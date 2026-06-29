#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""源杰科技 vs 长光华芯 综合对比分析报告生成器（含蔡森60日日线画线）"""
import json

def load(f):
    return json.load(open(f))

yj = load('yuanjie_kline.json')
cg = load('changguang_kline.json')

# 紧凑OHLCV数组
def compact(rows):
    return [[r['open'],r['high'],r['low'],r['close'],r['volume']] for r in rows]

yj_d = compact(yj)
cg_d = compact(cg)
yj_dates = [r['date'] for r in yj]
cg_dates = [r['date'] for r in cg]

html = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>源杰科技 vs 长光华芯 · 光芯片双雄深度对比</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root{
    --bg:#0d1117;--card:#161b22;--border:#30363d;--txt:#e6edf3;--muted:#8b949e;
    --yj:#FF6B00;--cg:#4a9eff;--up:#e74c3c;--down:#2ecc71;--warn:#f39c12;--danger:#e74c3c;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--txt);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.7;padding:20px;max-width:1280px;margin:0 auto}
  h1{font-size:26px;text-align:center;background:linear-gradient(90deg,#FF6B00,#4a9eff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}
  .sub{text-align:center;color:var(--muted);font-size:13px;margin-bottom:24px}
  h2{font-size:19px;border-left:4px solid var(--yj);padding-left:10px;margin:28px 0 14px}
  h2.cg{border-color:var(--cg)}
  h3{font-size:15px;color:var(--muted);margin:18px 0 8px}
  .card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px;margin-bottom:16px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
  @media(max-width:760px){.grid2,.grid3{grid-template-columns:1fr}}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{padding:8px 10px;border-bottom:1px solid var(--border);text-align:left}
  th{color:var(--muted);font-weight:600;background:#1c2128}
  td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
  .yj-c{color:var(--yj);font-weight:700}.cg-c{color:var(--cg);font-weight:700}
  .tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;margin:2px}
  .tag-yj{background:rgba(255,107,0,.15);color:#FF6B00;border:1px solid rgba(255,107,0,.4)}
  .tag-cg{background:rgba(74,158,255,.15);color:#4a9eff;border:1px solid rgba(74,158,255,.4)}
  .tag-danger{background:rgba(231,76,60,.15);color:#e74c3c;border:1px solid rgba(231,76,60,.4)}
  .tag-ok{background:rgba(46,204,113,.15);color:#2ecc71;border:1px solid rgba(46,204,113,.4)}
  .tag-warn{background:rgba(243,156,18,.15);color:#f39c12;border:1px solid rgba(243,156,18,.4)}
  .kpi{font-size:24px;font-weight:800}
  .kpilbl{font-size:11px;color:var(--muted)}
  .chart-box{background:#0a0e14;border:1px solid var(--border);border-radius:8px;padding:8px;margin-top:10px}
  canvas{display:block;width:100%}
  .warn-box{border-left:4px solid var(--danger);background:rgba(231,76,60,.06);padding:12px 16px;border-radius:0 8px 8px 0;margin:12px 0}
  .ok-box{border-left:4px solid var(--down);background:rgba(46,204,113,.06);padding:12px 16px;border-radius:0 8px 8px 0;margin:12px 0}
  .info-box{border-left:4px solid var(--warn);background:rgba(243,156,18,.06);padding:12px 16px;border-radius:0 8px 8px 0;margin:12px 0}
  ul{padding-left:20px}li{margin:4px 0}
  .conclusion{font-size:15px;background:linear-gradient(135deg,rgba(255,107,0,.08),rgba(74,158,255,.08));border:1px solid var(--border);padding:18px;border-radius:10px}
  .disclaimer{font-size:11px;color:var(--muted);text-align:center;margin-top:24px;padding-top:14px;border-top:1px solid var(--border)}
  .legend span{display:inline-block;margin-right:14px;font-size:12px}
  .dot{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:middle}
</style>
</head>
<body>

<h1>源杰科技 vs 长光华芯 · 光芯片双雄深度对比</h1>
<p class="sub">数据截至 2026-06-18 · 妙想金融数据 + 东方财富股吧舆情 + 蔡森形态学（60日日线量化画线）</p>

<!-- 定位对比 -->
<h2>一、核心定位对比</h2>
<div class="grid2">
  <div class="card">
    <h3 class="yj-c">源杰科技 688498.SH</h3>
    <p><b>纯光通信光芯片IDM龙头</b>。2013年成立，陕西西安，董事长 ZHANG XINGANG，员工716人。</p>
    <p style="margin-top:8px"><b>产品结构（2025）：数据中心激光器芯片占65.4%（毛利率71.3%）</b>，电信激光器芯片34.3%（毛利率25.9%）。</p>
    <p style="margin-top:8px">核心产品：2.5G-50G 磷化铟(InP) DFB/EML 激光器芯片、大功率CW连续波激光器（100mW/300mW CPO）。深度绑定AI算力光模块（旭创等头部供应链）。</p>
    <div style="margin-top:8px">
      <span class="tag tag-yj">AI算力直供</span><span class="tag tag-yj">CW光源</span><span class="tag tag-yj">100G EML</span><span class="tag tag-yj">CPO 300mW</span><span class="tag tag-yj">H股2072</span>
    </div>
  </div>
  <div class="card">
    <h3 class="cg-c">长光华芯 688048.SH</h3>
    <p><b>高功率半导体激光芯片IDM平台</b>。2012年成立，江苏苏州，董事长闵大勇，员工506人。</p>
    <p style="margin-top:8px"><b>产品结构（2025）：高功率单管系列占80.9%（工业激光泵浦）</b>，VCSEL及光通讯芯片仅占8.6%，高功率巴条6.1%。</p>
    <p style="margin-top:8px">核心产品：高功率半导体激光器芯片（GaAs/InP/GaN三材料平台）、VCSEL、光通信芯片（DFB/EML/PIN）。前瞻布局硅光集成（星钥光子8英寸线）、薄膜铌酸锂。</p>
    <div style="margin-top:8px">
      <span class="tag tag-cg">工业激光</span><span class="tag tag-cg">硅光8英寸</span><span class="tag tag-cg">薄膜铌酸锂</span><span class="tag tag-cg">央视背书</span><span class="tag tag-cg">三材料平台</span>
    </div>
  </div>
</div>
<div class="info-box">
  <b>关键差异：</b>源杰是<b>纯光通信光芯片</b>（AI数据中心直接受益，高毛利）；长光华芯主业是<b>工业激光芯片</b>（占81%），光通信只是边际增量（占8.6%）。这决定了源杰业绩弹性远超长光，但也意味着源杰的估值溢价更依赖AI叙事的兑现。
</div>

<!-- 财务对比 -->
<h2>二、财务业绩对比（数据来源：妙想金融）</h2>
<div class="card">
<table>
<tr><th>指标</th><th class="n">源杰科技 688498</th><th class="n">长光华芯 688048</th><th class="n">胜出</th></tr>
<tr><td>2025营收</td><td class="n">6.01亿 <span style="color:#2ecc71">(+138.5%)</span></td><td class="n">4.77亿 <span style="color:#2ecc71">(+75.1%)</span></td><td class="n yj-c">源杰</td></tr>
<tr><td>2025归母净利</td><td class="n">1.91亿 <span style="color:#2ecc71">(+3213%)</span></td><td class="n">0.22亿 <span style="color:#2ecc71">(+121.8%)</span></td><td class="n yj-c">源杰(9倍)</td></tr>
<tr><td>2025扣非净利</td><td class="n">1.67亿</td><td class="n" style="color:#e74c3c">-0.33亿(亏损)</td><td class="n yj-c">源杰</td></tr>
<tr><td>2025毛利率</td><td class="n">58.11%</td><td class="n">34.54%</td><td class="n yj-c">源杰</td></tr>
<tr><td>2026Q1营收</td><td class="n">3.55亿 <span style="color:#2ecc71">(+320.9%)</span></td><td class="n">1.30亿 <span style="color:#2ecc71">(+37.8%)</span></td><td class="n yj-c">源杰</td></tr>
<tr><td>2026Q1归母净利</td><td class="n">1.79亿 <span style="color:#2ecc71">(+1153%)</span></td><td class="n">0.045亿 <span style="color:#2ecc71">(+159.7%)</span></td><td class="n yj-c">源杰(40倍)</td></tr>
<tr><td>2026Q1毛利率</td><td class="n" style="color:#2ecc71">77.81%（同业第1）</td><td class="n">30.09%</td><td class="n yj-c">源杰</td></tr>
<tr><td>2025研发费用</td><td class="n">0.81亿（占营收13%）</td><td class="n">1.15亿（占营收24%）</td><td class="n cg-c">长光(占比)</td></tr>
<tr><td>最新总市值</td><td class="n yj-c">2083亿</td><td class="n cg-c">689亿</td><td class="n">—</td></tr>
<tr><td>最新PE(TTM)</td><td class="n" style="color:#f39c12">585倍</td><td class="n" style="color:#e74c3c">2043倍</td><td class="n">—</td></tr>
<tr><td>最新PB</td><td class="n">82.5倍</td><td class="n">22.9倍</td><td class="n">—</td></tr>
<tr><td>换手率(6/18)</td><td class="n">3.58%</td><td class="n">9.43%</td><td class="n">—</td></tr>
</table>
</div>

<div class="grid2">
  <div class="chart-box"><canvas id="revChart"></canvas></div>
  <div class="chart-box"><canvas id="profitChart"></canvas></div>
</div>

<div class="warn-box">
  <b>财务核心结论：</b>源杰盈利能力<b>全面碾压</b>长光华芯——2026Q1净利润是长光的<b>40倍</b>，毛利率77.81%（同业第一）vs 30.09%。源杰已进入"印钞机"模式，长光华芯扣非仍在亏损。但<b>两家估值都极度昂贵</b>：源杰PE 585倍、长光PE 2043倍，远超合理区间，需靠未来3年高增长消化。
</div>

<!-- 蔡森技术分析 -->
<h2>三、蔡森技术分析（60日日线 · 量化形态识别画线）</h2>
<p style="color:var(--muted);font-size:13px">画线遵循蔡森形态学规范：局部极值检测(lookback=3)+形态优先级识别。配色：橙色=底部颈线、红色=顶部阻力、绿色=支撑/上升线、灰色=破底前支撑、绿色虚线=测幅满足、蓝色=测幅竖线。四色K线：红=强势阳、黄=假阴、绿=假阳、蓝=强势阴。</p>

<h3 class="yj-c">源杰科技 · 日线画线（41日窗口）</h3>
<div class="chart-box"><canvas id="yjChart" height="380"></canvas></div>
<div class="card" style="margin-top:10px">
<p><b>形态研判：</b>41日区间1000→1767→1673，振幅77%。走势为<b>从1000元底部主升浪拉升77%至1766.88元高点，随后高位震荡</b>。</p>
<ul>
  <li><span class="dot" style="background:#999"></span><b>灰色破底前支撑@1000元</b>：4月底低点，本轮主升浪起点</li>
  <li><span class="dot" style="background:#e74c3c"></span><b>红色顶部阻力@1766.88元</b>：本轮高点，M头左肩风险位</li>
  <li><span class="dot" style="background:#2ecc71"></span><b>绿色上升趋势线</b>：连接1000底与近期回调低点，多头防线</li>
  <li><span class="dot" style="background:#4a9eff"></span><b>蓝色测幅竖线</b>：标注1766高点测幅位</li>
</ul>
<p style="margin-top:8px"><b>量价信号：</b>近5日成交量持续萎缩（974→440万股），末日量比<b>0.67（缩量）</b>，<b>上攻动能减弱</b>。当前处于高位整理，<b>缩量滞涨</b>是警示信号。</p>
<p style="margin-top:8px"><span class="tag tag-warn">高位整理</span><span class="tag tag-warn">缩量滞涨</span><span class="tag tag-warn">警惕M头</span><span class="tag tag-danger">追高风险极高</span></p>
</div>

<h3 class="cg-c">长光华芯 · 日线画线（41日窗口）</h3>
<div class="chart-box"><canvas id="cgChart" height="380"></canvas></div>
<div class="card" style="margin-top:10px">
<p><b>形态研判：</b>41日区间296→463→391，振幅57%。走势为<b>冲高463.37元后回调，在323-330区间构筑双底</b>。</p>
<ul>
  <li><span class="dot" style="background:#FF6B00"></span><b>橙色W底颈线@323-330元</b>：双底差值仅2.1%（≤5%标准），<b>符合W底/双底形态</b></li>
  <li><span class="dot" style="background:#e74c3c"></span><b>红色顶部阻力@463.37元</b>：前高颈线，突破即打开空间</li>
  <li><span class="dot" style="background:#2ed573"></span><b>绿色测幅满足线</b>：W底突破后的量度目标位</li>
  <li><span class="dot" style="background:#2ecc71"></span><b>支撑@323元</b>：双底防线，跌破失效</li>
</ul>
<p style="margin-top:8px"><b>量价信号：</b>近5日成交量放大（1460→1662万股），末日量比<b>1.20（放量）</b>，资金回流迹象。W底构筑后放量尝试向上，<b>形态偏多</b>。</p>
<p style="margin-top:8px"><span class="tag tag-ok">W底构筑</span><span class="tag tag-ok">放量回升</span><span class="tag tag-ok">形态偏多</span><span class="tag tag-warn">需突破463确认</span></p>
</div>

<div class="info-box">
  <b>技术面对比结论：</b>源杰处于<b>主升浪后的高位整理</b>（缩量滞涨，警惕双顶/M头）；长光华芯处于<b>回调后的W底构筑</b>（放量回升，形态更健康）。<b>从蔡森形态学角度，长光华芯的技术形态优于源杰</b>——但需注意这是"强势股回调"vs"高位股风险"的差异，不代表长光基本面更强。
</div>

<!-- 舆情分析 -->
<h2>四、东方财富股吧舆情分析</h2>
<div class="grid2">
  <div class="card">
    <h3 class="yj-c">源杰科技股吧 · 极度分化（顶部信号）</h3>
    <p><b>看多派（狂热）：</b></p>
    <ul style="font-size:12px;color:var(--muted)">
      <li>"光芯片国内第一，很快会超过两千"</li>
      <li>"下周可能要去摸2000块了"</li>
      <li>"今天已杠杆满仓梭哈！"</li>
      <li>"目标2500"</li>
    </ul>
    <p><b>看空派（清醒/恐慌）：</b></p>
    <ul style="font-size:12px;color:var(--muted)">
      <li>"一年净利润2亿，市值2000亿，过分"</li>
      <li>"历史大顶，主力找人接盘"</li>
      <li>"散户已经没有资格接盘了"</li>
      <li>"63600的市盈率，真的夸张"</li>
      <li>"哪怕利润率百分百，都要一两百年挣回市值"</li>
    </ul>
    <p style="margin-top:8px"><span class="tag tag-danger">极度贪婪</span><span class="tag tag-danger">顶部分歧</span><span class="tag tag-warn">杠杆追高</span></p>
  </div>
  <div class="card">
    <h3 class="cg-c">长光华芯股吧 · 偏多+理性</h3>
    <p><b>看多派：</b></p>
    <ul style="font-size:12px;color:var(--muted)">
      <li>"年底200量产，明年400量产"</li>
      <li>"MACD金叉，下周进主升"</li>
      <li>"央视背书+硅光8英寸产线"</li>
      <li>"英伟达要求CW扩产翻倍"</li>
    </ul>
    <p><b>质疑派：</b></p>
    <ul style="font-size:12px;color:var(--muted)">
      <li>"463元已见十年大顶"</li>
      <li>"董事长承认良率不高，怎么传90%"</li>
      <li>"央视站台=主力出货信号"</li>
      <li>"被东山精密抢风头，题材边缘化"</li>
    </ul>
    <p style="margin-top:8px"><span class="tag tag-ok">基本面讨论</span><span class="tag tag-warn">良率争议</span><span class="tag tag-ok">相对理性</span></p>
  </div>
</div>
<div class="warn-box">
  <b>舆情反常信号：</b>源杰股吧出现典型<b>"顶部特征"</b>——极度贪婪（杠杆满仓）与极度恐惧（喊大顶）并存，散户大谈"散户没资格接盘"、"一两百年回本"，这种<b>极端分化本身就是见顶预警</b>（笨鸟M4反常信号）。长光华芯讨论更聚焦基本面（200G EML、良率、硅光），狂热程度低于源杰。
</div>

<!-- 重大事件 -->
<h2>五、重大事件与风险</h2>
<div class="warn-box">
  <p style="font-size:16px;font-weight:700;color:#e74c3c">⚠ 源杰科技：副总经理陈文君被刑事拘留（2026-05-14）</p>
  <p style="margin-top:8px">陈文君<b>分管销售及营销</b>，是公司商业化、客户体系的核心负责人。5月14日晚公告因"涉嫌刑事犯罪"被公安机关刑拘，公司当日紧急召开董事会<b>解聘其副总经理职务</b>。</p>
  <p style="margin-top:8px"><b>为何重要：</b>光芯片下游客户高度集中于头部光模块厂商（旭创等）、云厂商、AI数据中心。销售负责人被刑拘，可能涉及<b>商业贿赂/客户合规/价格体系</b>问题。同期Q1销售费用同比<b>暴涨145%</b>，值得警惕。这一事件发生在业绩暴增、股价11倍涨幅的节点，构成<b>重大治理风险</b>。</p>
</div>
<div class="info-box">
  <p style="font-weight:700;color:#f39c12">⚡ 两家公司共同风险</p>
  <ul style="margin-top:6px">
    <li><b>估值泡沫</b>：源杰PE 585倍、长光PE 2043倍，均需未来3年业绩持续高增长消化，一旦AI资本开支放缓即戴维斯双杀</li>
    <li><b>AI叙事依赖</b>：股价涨幅（源杰一年+1400%）已严重透支业绩，"光芯片紧缺至2026年底"的预期若证伪，回调剧烈</li>
    <li><b>技术迭代</b>：CPO/硅光/薄膜铌酸锂等新技术路线若加速，现有DFB/EML产品可能被替代</li>
  </ul>
</div>

<!-- 机构预测 -->
<h2>六、机构盈利预测对比</h2>
<div class="card">
<table>
<tr><th>机构</th><th>标的</th><th>评级</th><th class="n">2026E净利</th><th class="n">2027E净利</th><th class="n">2026E PE</th></tr>
<tr><td>群益证券</td><td class="yj-c">源杰科技</td><td>买进</td><td class="n">7.98亿</td><td class="n">13.46亿</td><td class="n">130倍</td></tr>
<tr><td>太平洋证券</td><td class="cg-c">长光华芯</td><td>买入</td><td class="n">0.74亿</td><td class="n">1.54亿</td><td class="n">805倍</td></tr>
</table>
<p style="margin-top:8px;color:var(--muted);font-size:12px">注：按机构预测，源杰2026年PE可降至130倍（仍贵但业绩兑现度高），长光华芯2026年PE仍高达805倍（业绩兑现度低）。<b>源杰的"业绩消化估值"能力远强于长光华芯</b>。</p>
</div>

<!-- 综合结论 -->
<h2>七、综合对比结论</h2>
<div class="conclusion">
<table>
<tr><th>维度</th><th class="yj-c">源杰科技</th><th class="cg-c">长光华芯</th></tr>
<tr><td>AI纯度</td><td>★★★★★（纯光通信，CW光源直供旭创）</td><td>★★★（光通信仅占8.6%）</td></tr>
<tr><td>盈利质量</td><td>★★★★★（毛利率77.8%，印钞机）</td><td>★★（扣非仍亏损）</td></tr>
<tr><td>业绩弹性</td><td>★★★★★（Q1净利+1153%）</td><td>★★★（Q1净利+160%）</td></tr>
<tr><td>估值消化力</td><td>★★★（PE 585→130倍可消化）</td><td>★（PE 2043倍，难消化）</td></tr>
<tr><td>技术形态</td><td>★★（高位整理，警惕M头）</td><td>★★★★（W底构筑，放量）</td></tr>
<tr><td>治理风险</td><td>★（副总被刑拘，重大利空）</td><td>★★★★（相对干净）</td></tr>
<tr><td>催化预期</td><td>CPO 300mW、1.6T光模块放量</td><td>硅光8英寸线、央视背书、200G EML</td></tr>
<tr><td>舆情温度</td><td>过热（顶部信号）</td><td>温和偏多</td></tr>
</table>

<p style="margin-top:14px"><b>总结论：</b></p>
<ul>
  <li><b>源杰科技是"业绩型选手"</b>：基本面最强、AI纯度最高、盈利能力碾压，但<b>估值泡沫最大、高管刑拘是重大治理黑天鹅、股吧过热见顶信号明显、技术面高位滞涨</b>。适合<b>已持有者警惕止盈、未持有者切忌追高</b>。</li>
  <li><b>长光华芯是"题材型选手"</b>：基本面弱（扣非亏损）、估值更夸张，但<b>硅光/薄膜铌酸锂前瞻布局有想象力、技术形态更健康（W底）、治理相对干净、舆情未过热</b>。属于<b>高风险高赔率的博弈标的，需等业绩验证</b>。</li>
  <li><b>两者不宜现价追高</b>。若必须二选一：<b>中线看源杰（业绩兑现），短线博弈看长光（形态+催化）</b>，但都要严格控制仓位与止损。</li>
</ul>
</div>

<p class="disclaimer">
本报告由七专家分析框架（妙想数据+东方财富舆情+蔡森形态学）生成，仅供研究参考，不构成投资建议。<br>
股市有风险，光芯片板块当前估值处于历史极端水平，请独立判断、理性决策。
</p>

<script>
// ============ K线数据 ============
const YJ = __YJ_DATA__;
const YJ_D = __YJ_DATES__;
const CG = __CG_DATA__;
const CG_D = __CG_DATES__;

// ============ 蔡森K线画线函数 ============
function drawCaisen(canvas, data, dates, lines, labels, title, color){
  const dpr=window.devicePixelRatio||1;
  const W=canvas.clientWidth, H=canvas.clientHeight;
  canvas.width=W*dpr; canvas.height=H*dpr;
  const ctx=canvas.getContext('2d'); ctx.scale(dpr,dpr);
  ctx.fillStyle='#0a0e14'; ctx.fillRect(0,0,W,H);
  const padL=54,padR=70,padT=30,padB=46;
  const pw=W-padL-padR, ph=H-padT-padB;
  const volH=46;
  const priceH=ph-volH-8;
  // 价格范围
  let minP=1e9,maxP=0,maxV=0;
  data.forEach(d=>{minP=Math.min(minP,d[2]);maxP=Math.max(maxP,d[1]);maxV=Math.max(maxV,d[4]);});
  const pad=(maxP-minP)*0.08;
  minP-=pad; maxP+=pad;
  const n=data.length;
  const x=i=>padL+(i+0.5)/n*pw;
  const yp=p=>padT+(maxP-p)/(maxP-minP)*priceH;
  const yv=v=>padT+priceH+8+(1-v/maxV)*volH;
  // 网格
  ctx.strokeStyle='#1c2230'; ctx.lineWidth=1; ctx.font='10px monospace'; ctx.fillStyle='#5a6373';
  for(let g=0;g<=4;g++){
    const p=minP+(maxP-minP)*g/4, y=yp(p);
    ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(padL+pw,y); ctx.stroke();
    ctx.textAlign='right'; ctx.fillText(p.toFixed(0),padL-6,y+3);
  }
  // 成交量均线
  const ma5=[]; 
  for(let i=0;i<n;i++){let s=0,c=0;for(let k=Math.max(0,i-4);k<=i;k++){s+=data[k][4];c++;}ma5.push(s/c);}
  // K线
  const cw=pw/n*0.62;
  data.forEach((d,i)=>{
    const [o,h,l,c,v]=d;
    const cx=x(i);
    // 四色K线判定
    let upColor, bodyColor;
    const body=Math.abs(c-o), range=h-l;
    if(c>=o){
      if(body>range*0.6){upColor='#e74c3c';} // 强势阳 红
      else{upColor='#2ecc71';} // 假阳 绿
    }else{
      if(body>range*0.6){upColor='#3498db';} // 强势阴 蓝
      else{upColor='#f1c40f';} // 假阴 黄
    }
    // 影线
    ctx.strokeStyle=upColor; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(cx,yp(h)); ctx.lineTo(cx,yp(l)); ctx.stroke();
    // 实体
    ctx.fillStyle=upColor;
    const yo=yp(o),yc=yp(c);
    const top=Math.min(yo,yc),bh=Math.max(2,Math.abs(yc-yo));
    ctx.fillRect(cx-cw/2,top,cw,bh);
    // 成交量
    ctx.globalAlpha=0.55;
    ctx.fillRect(cx-cw/2,yv(v),cw,padT+priceH+8+volH-yv(v));
    ctx.globalAlpha=1;
  });
  // 量能均线
  ctx.strokeStyle='#f39c12'; ctx.lineWidth=1.2; ctx.beginPath();
  ma5.forEach((v,i)=>{i===0?ctx.moveTo(x(i),yv(v)):ctx.lineTo(x(i),yv(v));}); ctx.stroke();
  // 画线
  lines.forEach(ln=>{
    ctx.strokeStyle=ln.color; ctx.lineWidth=ln.w||2;
    ctx.setLineDash(ln.dash||[]);
    if(ln.type==='h'){ // 水平线
      const y=yp(ln.val);
      ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(padL+pw,y); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle=ln.color; ctx.textAlign='left';
      ctx.font='10px monospace'; ctx.fillText(ln.label+' '+ln.val.toFixed(0), padL+pw+4, y+3);
    } else if(ln.type==='seg'){ // 线段
      ctx.beginPath();
      ln.pts.forEach((p,k)=>{const px=x(p[0]),py=yp(p[1]);k===0?ctx.moveTo(px,py):ctx.lineTo(px,py);});
      ctx.stroke();
    }
    ctx.setLineDash([]);
  });
  // 标注
  ctx.font='bold 11px sans-serif';
  labels.forEach(lb=>{
    const px=x(lb.i), py=yp(lb.p);
    ctx.fillStyle=lb.color;
    ctx.textAlign='center';
    if(lb.marker){
      ctx.beginPath(); ctx.arc(px,py,4,0,7); ctx.fill();
    }
    ctx.fillText(lb.t, px, py+(lb.below?14:-8));
  });
  // 日期轴
  ctx.fillStyle='#5a6373'; ctx.font='9px monospace'; ctx.textAlign='center';
  const step=Math.ceil(n/6);
  for(let i=0;i<n;i+=step){ctx.fillText(String(dates[i]).slice(5), x(i), H-8);}
  // 标题
  ctx.fillStyle=color; ctx.font='bold 13px sans-serif'; ctx.textAlign='left';
  ctx.fillText(title, padL, 18);
}

// ============ 绘制 ============
// 源杰画线参数
drawCaisen(document.getElementById('yjChart'), YJ, YJ_D, [
  {type:'h',val:1000.08,color:'#999',label:'破底支撑',dash:[4,4]},
  {type:'h',val:1766.88,color:'#e74c3c',label:'顶部阻力',dash:[4,4]},
  {type:'h',val:1673.36,color:'#FF6B00',label:'现价'},
  {type:'seg',color:'#2ecc71',w:2,pts:[[0,1388],[40,1673]]},
],[
  {i:0,p:1388,t:'起',color:'#999',marker:true},
  {i:7,p:1000.08,t:'底',color:'#2ecc71',marker:true,below:true},
  {i:30,p:1766.88,t:'顶',color:'#e74c3c',marker:true},
  {i:40,p:1673.36,t:'现',color:'#FF6B00',marker:true,below:true},
], '源杰科技 688498 · 高位整理(缩量警惕M头)', '#FF6B00');

// 长光画线参数
drawCaisen(document.getElementById('cgChart'), CG, CG_D, [
  {type:'h',val:463.37,color:'#e74c3c',label:'顶部阻力',dash:[4,4]},
  {type:'h',val:323.2,color:'#FF6B00',label:'W底支撑',dash:[6,3]},
  {type:'h',val:391.07,color:'#4a9eff',label:'现价'},
  {type:'seg',color:'#2ed573',w:1.8,dash:[3,3],pts:[[5,463],[15,323]]},
],[
  {i:5,p:463.37,t:'前高',color:'#e74c3c',marker:true},
  {i:15,p:323.2,t:'底1',color:'#FF6B00',marker:true,below:true},
  {i:22,p:330.0,t:'底2',color:'#FF6B00',marker:true,below:true},
  {i:40,p:391.07,t:'现',color:'#4a9eff',marker:true,below:true},
], '长光华芯 688048 · W底构筑(放量偏多)', '#4a9eff');

// ============ Chart.js 财务图 ============
Chart.defaults.color='#8b949e';
new Chart(document.getElementById('revChart'),{
  type:'bar',
  data:{labels:['2023','2024','2025','2026Q1'],datasets:[
    {label:'源杰营收(亿)',data:[1.44,2.52,6.01,3.55],backgroundColor:'#FF6B00'},
    {label:'长光营收(亿)',data:[2.90,2.73,4.77,1.30],backgroundColor:'#4a9eff'}
  ]},
  options:{plugins:{title:{display:true,text:'营业收入对比(亿元)',color:'#e6edf3'}},
    scales:{y:{grid:{color:'#1c2230'}}}}
});
new Chart(document.getElementById('profitChart'),{
  type:'bar',
  data:{labels:['2023','2024','2025','2026Q1'],datasets:[
    {label:'源杰归母净利(亿)',data:[0.19,-0.06,1.91,1.79],backgroundColor:'#FF6B00'},
    {label:'长光归母净利(亿)',data:[-0.92,-1.00,0.22,0.045],backgroundColor:'#4a9eff'}
  ]},
  options:{plugins:{title:{display:true,text:'归母净利润对比(亿元)',color:'#e6edf3'}},
    scales:{y:{grid:{color:'#1c2230'}}}}
});
</script>
</body>
</html>
'''

# 注入数据
html = html.replace('__YJ_DATA__', json.dumps(yj_d))
html = html.replace('__YJ_DATES__', json.dumps(yj_dates))
html = html.replace('__CG_DATA__', json.dumps(cg_d))
html = html.replace('__CG_DATES__', json.dumps(cg_dates))

open('源杰vs长光华芯_深度对比.html','w',encoding='utf-8').write(html)
print('✅ 报告已生成: 源杰vs长光华芯_深度对比.html')
print(f'  源杰K线 {len(yj_d)} 日, 长光K线 {len(cg_d)} 日')
