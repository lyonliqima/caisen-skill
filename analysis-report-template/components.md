# analysis-report-template · 组件参考（agent 必读）

**作用**：分析类报告（四方法论整合 / 九专家整合）只写「内容 + class」的 body 片段，本模板负责全部 CSS 与图表 JS。模型**不要**在 body 里写 `<head>`/`<style>`/`<script src>`，也不要重写任何 CSS —— 这能把每份报告的生成 token 量砍掉一半以上。

**流程**：
1. 按本文件写 `<主题>-报告.body.html`（仅内容 + class，以 `<section>` 开头）。
2. 跑 `render.py <body> <输出.html> --title="..."` 合成最终 HTML。
3. 在对话里输出合成后的 HTML（或直接给用户文件）。

**颜色约定（中国习惯）**：`.up`=涨/多(红)，`.down`=跌/空(绿)，`.gold`=关键位，`.warn`=风险/证伪，`.purple`=制度结构。

---

## 可用 class / 结构

### 区块容器
```html
<section class="block"><h2>标题</h2> ...内容... </section>
```

### 评分卡（核心结论，所有报告开头放一张）
```html
<div class="verdict">
  <span class="conf">置信度 72</span>
  <div class="dir up">看多 ▲</div>
  <ul>
    <li>逻辑1（≤20字）</li>
    <li>逻辑2（≤20字）</li>
  </ul>
</div>
```

### 方法论推导块（每个方法论一节）
```html
<section class="block"><h2>🔵 杨世光·宏观六步法推导</h2>
  <div class="card"><h3>结论</h3><p>...</p></div>
  <div class="evidence">关键证据：实际利率↓ + 美元弱 → 黄金多头信号</div>
  <div class="falsify"><b>证伪条件</b>：若美联储重启加息且美元指数突破106，则多头失效</div>
</section>
```

### 图表（只写 canvas + 一行调用）
```html
<div class="chart-box"><canvas id="c1"></canvas><div class="cap">图1：四方法论置信度对比</div></div>
<script>drawRadar('c1', ['宏观','制度','技术','数据','因果','风控'], [80,65,70,75,60,85], {color:'#4a9eff'});</script>
```
可用 helper：`drawLine(id,labels,datasets)` / `drawBar(id,labels,datasets)` / `drawRadar(id,axes,values)` / `drawDoughnut(id,labels,values)`。
- `datasets` 支持两种写法：`[{label,data,color}]` 或 `[[...],[...]]`。
- `color` 用 `--up/--down/--gold/--accent/--warn/--purple` 对应色值或十六进制。

### 交叉验证表
```html
<table>
  <tr><th>维度</th><th>杨</th><th>卢</th><th>蔡</th><th>笨鸟</th><th>结论</th></tr>
  <tr><td>方向</td><td class="cons">多</td><td class="div">分歧</td><td class="cons">多</td><td class="cons">多</td><td class="cons">共识·多</td></tr>
</table>
```
`.cons`=共识(绿)，`.div`=分歧(橙)。

### 兵棋推演树
```html
<div class="scenario">
  <span class="tag up">看多</span><span class="cond">若 Fed 降息</span><span class="arrow">→</span><span class="res">流动性宽松</span>
  <div class="child"><span class="cond">→ 风险资产重估</span><span class="arrow">→</span><span class="res">A股科技领涨</span></div>
</div>
```

### 先行指标 / 免责
- 先行指标清单用普通 `<ul>` 或 `.card` 包裹即可。
- `<footer class="disclaimer">` 已在 shell 里固定，body **不要**再写 footer。

---

## 不变量（自检）
- body 片段**不含** `<!DOCTYPE>`/`<html>`/`<head>`/`<style>`/`<body>`/`<footer>` 标签。
- body 以 `<section>` 或 `<div class="verdict">` 开头。
- 所有图表用 `drawXxx` helper，不写原生 Chart.js `new Chart(...)` 配置。
- 不满足任一条 = body 不合规，render 仍能合成但视觉会跑偏。
