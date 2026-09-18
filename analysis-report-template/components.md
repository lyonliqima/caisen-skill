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

`datasets` 支持 **三种写法**（2026-09-11 修正：旧版 helper 会把嵌套/扁平数组错塞进 `data` 标量，导致图表全白，已修复）：

| 写法 | 示例 | 说明 |
|---|---|---|
| 扁平数组 | `[1,2,3]` | 单系列 |
| 嵌套数组 | `[[1,2],[3,4]]` | 多系列；配 `opts.names:['甲','乙']` 给图例命名 |
| 标准对象 | `[{label:'甲',data:[1,2],color:'#f00'}]` | 完全控制，`color` 优先级最高 |

```html
<!-- 多系列柱状图，带图例 -->
<canvas id="c9"></canvas>
<script>drawBar('c9', ['1月','2月','3月'], [[1.2,2.0,1.8],[0.9,1.5,2.2]],
  {colors:['#ff9f43','#4a9eff'], names:['生猪','红枣']});</script>
```

- `opts.colors[i]` 与第 i 个系列一一对应；`opts.names[i]` 是第 i 个系列的图例名。
- `opts.fill:true` 给折线图加面积填充。
- **虚线（预测线）**（2026-09-18 新增）：用标准对象写法给单个系列加 `borderDash`，或给整图加 `{dash:true}`。
  ```html
  <script>drawLine('c11', ['现价','10月','11月','12月'],
    [{label:'焦煤·实际', data:[1580]},
     {label:'焦煤·预测', data:[1580,1510,1450,1460], color:'#1ec77a', borderDash:[0,6,6]}],
    {fill:false});</script>
  ```
  带 `borderDash` 的系列会自动改用方形点（`rectRot`）并把点放大到 3px，便于区分「实测」与「预测」。
- **颜色用十六进制**（`--up/--down/--gold/--accent/--warn/--purple` 的色值或自定义），不要写 `var(--x)`，Chart.js 画布不认 CSS 变量。
- 雷达图：`drawRadar(id,axes,values,{color:'#4a9eff',label:'评分（1–5）'})`。
  - ⚠️ **雷达图只用于「同一对象的多个维度打分」**（如四方法论置信度）。**不要**用它画 2×2 博弈矩阵/离散结局——雷达的首尾相连会伪造出根本不存在的连续性，把 4 个离散结局画成一个闭合环。离散结局一律用 `drawBar`。
- **离线可用**：合图后如需脱离网络打开，把 `<script src=".../chart.js"></script>` 换成内联的 chart.umd.js 全文即可（约 205KB，一次 curl 下载）。

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
- **每个 `<canvas id="cN">` 必须有且仅有一条对应的 `drawXxx('cN', ...)` 调用。**
- **⚠️ `datasets` 里不得出现 `null` / `undefined` 数据集（2026-09-13 实锤，2026-09-18 补充边界）**：崩溃的是「**数据集本身**为 null」——`verify_charts.js` 会崩在 `Cannot read properties of null (reading 'color')`，报错信息不指向真正的图表，排查成本高。**若某序列缺某期数据，必须同时裁掉对应的 label**，不能写 `[null, 6.79, ...]` 占位。
  - **唯一例外**：多系列共享同一组 label、而**只有某一条序列**提前终止（典型场景 = 近月合约到期，如 LH2611 在 11 月后不再有价格）。此时给该序列尾部填 `null` 是**正确**做法（Chart.js 会在 null 处断线，视觉上恰好表示「合约已结束」），并为它单独标注。注意：该序列的 `data.length` 仍须等于 `labels.length`，不能靠裁 label 解决。
- 渲染完成后**必须**跑一次图表结构校验（Chart.js 对坏数据只白屏、不报错）：
  ```bash
  node analysis-report-template/verify_charts.js <输出.html>
  ```
  输出 `PASS 全部 N 张图表结构合法` 才算过关。
- 不满足任一条 = body 不合规，render 仍能合成但视觉会跑偏。

---

## 定稿前三查（2026-09-16 大金重工实战新增）

> 以下三条是 render → verify 之间最容易漏掉的坑，都曾真实翻车。

1. **render 会删掉 body 片段**。`render.py` 输出末行 `[render] 已清理 body 片段: xxx.body.html` —— 合成之后 body 文件**已不存在**。想在合成后再修正，只能直接改**最终 HTML**；想保留可复算的中间产物，先 `cp` 一份。
2. **`verify_charts.js` 只查结构，不查数值**。它校验的是「canvas ↔ draw 调用一一对应」+「每条 dataset 长度 == labels 长度」，**不校验日期与数值是否对齐**。本次 c3 三条序列各写 6 值、labels 只写 5 个 → FAIL 报出；但只要长度凑齐、日期错位（本次原稿正是把 9/14 的 `13600.80` 漏掉、把 9/15 的 `62377.93` 顶上来），校验会**静默通过**。→ 图表数据必须先用取数源逐日对表，再写进 `drawXxx`，不能凭记忆拼数组。
3. **body 里手写 Markdown `**加粗**` 不会被渲染**，会原样显示星号。本次定稿前残留 22 处。→ 定稿前必跑一次：
   ```bash
   grep -o '\*\*' <输出.html> | wc -l   # 必须为 0
   ```
   替换时用 Python 逐段处理并跳过 `<script>...</script>`，避免误改图表代码：
   ```python
   parts = re.split(r'(<script[\s\S]*?</script>)', s)
   out = [seg if seg.startswith('<script') else re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', seg) for seg in parts]
   ```

**补充自检（快）**：标签平衡 + canvas 清单一次跑完
```python
body = re.sub(r'<script[\s\S]*?</script>', '', s)
for t in ['div','p','table','tr','td','th','ul','li','section','b','span','canvas']:
    o, c = len(re.findall(r'<%s[\s>]' % t, body)), len(re.findall(r'</%s>' % t, body))
    if o != c: print('不平衡', t, o, c)
```

4. **图表数值必须回算，与正文口径对齐（2026-09-18 黑金/生猪实战新增）**。`verify_charts.js` 只查结构，不查数值一致性。本次 c11 原稿写焦煤末值 1440，而正文目标是「1450–1500、−8.2%」——图与文自相矛盾，且**图注说「10 月中为最低点」而数据的最低点在 12 月中**。
   → 定稿前对每张「预测类」折线图做三查：① 末值是否落在正文给的目标区间内；② 图注的文字描述（「最低点/最抗跌/跌幅最大」）是否能从数据数组直接读出来；③ 百分数用 `(末值-起点)/起点` 现算一遍，别凭手感写。
   ```python
   ser = {'焦煤': [1580,1510,1470,1450,1460], '焦炭': [2043.5,1960,1905,1880,1890]}
   for k,v in ser.items(): print(k, 'min', min(v), '跌幅 %.1f%%' % ((min(v)-v[0])/v[0]*100))
   ```

5. **桌面主副本与镜像的关系（2026-09-18 核实）**：`~/.workbuddy/skills/caisen-10-experts-analyst/analysis-report-template` 是**软链接**，指向 `/Users/weihaoli/Desktop/蔡森 skill/analysis-report-template`。**改桌面即改镜像，无需手工同步**；`market-data-cache`、`tools` 同理。但 `SKILL.md` / `agent.md` / `references/` 是**真实副本**，那三处仍需「先改桌面、再同步镜像」并做 md5 校验。
