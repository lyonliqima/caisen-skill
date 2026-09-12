#!/usr/bin/env node
/**
 * verify_charts.js — 报告图表结构校验器（生成报告后必跑）
 *
 * 用法： node verify_charts.js <报告.html>
 *
 * 它干三件事：
 *   1. 抽出 body 里的 drawXxx 调用，在 Node 里用假的 Chart 对象跑一遍；
 *   2. 断言每个 dataset 的 data 都是数组、长度与 labels 一致、label/颜色齐全；
 *   3. 顺手检查 <canvas> 数量与 draw 调用数量是否匹配（少调用 = 图空白）。
 *
 * 退出码 0 = 通过；1 = 有问题（打印到 stdout）。
 * 为什么要跑：Chart.js 对 data 为标量 / dataset 不是对象 **不报错、只渲染空白**，
 * 肉眼在 HTML 源码里看不出来，必须机器校验。
 */
const fs = require('fs');
const path = process.argv[2];
if (!path) { console.error('用法: node verify_charts.js <报告.html>'); process.exit(2); }
const html = fs.readFileSync(path, 'utf8');

// 收集所有 <script> 块（无 src 属性）。helper 在渲染时位于 head，每个 draw 调用各自独立成块。
// 不再假设「最后两块=helper+calls」，而是：helper = 含 drawXxx 函数定义的块；calls = 其余所有块。
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (!blocks.length) { console.error('FAIL 找不到任何 <script> 块'); process.exit(1); }
const helper = blocks.find(b => /function draw(?:Bar|Line|Radar|Doughnut)\b/.test(b)) || blocks[0];
const callBlocks = blocks.filter(b => b !== helper);

const canvases = [...html.matchAll(/<canvas id="(c[\w-]+)"/g)].map(m => m[1]);
const drawn = callBlocks.flatMap(b => [...b.matchAll(/draw(?:Bar|Line|Radar|Doughnut)\('(c[\w-]+)'/g)].map(m => m[1]));

const charts = [];
const colorTrap = [];
global.document = { getElementById: (id) => ({ id }) };
global.Chart = function (ctx, cfg) { charts.push({ id: ctx.id, type: cfg.type, cfg }); };
// 挂钩 _base，捕获「单数据集 + opts.colors 逐柱配色」的静默失效：
// _base 内取色写的是 `opts.colors[i]`，而 i 是「数据集索引」，单数据集恒为 0，
// 于是逐柱色数组被丢弃、只取 colors[0] —— 图注写的配色与实际渲染不符，
// 但 borderColor 仍然存在，旧版校验器会报 PASS（2026-09-12 实锤）。fail-safe：挂钩失败则跳过。
global.__pre = function (data, opts) {
  if (!opts || !Array.isArray(opts.colors)) return;
  const nds = (data && data.datasets ? data.datasets.length : 0);
  const nl = (data && data.labels ? data.labels.length : 0);
  // 只有当该数据集没有自带 color 时才会真正读 opts.colors（_base 里 d.color 优先级最高）。
  // drawDoughnut 走的是 dataset.color 路径，必须排除，否则误报（2026-09-12 实锤误报）。
  const d0 = (data && data.datasets && data.datasets[0]) || null;
  const hasOwnColor = !!(d0 && d0.color);
  if (nds === 1 && !hasOwnColor && opts.colors.length > 1 && nl > 1) {
    colorTrap.push('单数据集 + opts.colors(' + opts.colors.length + '项) 而 labels ' + nl +
      ' 项：该数据集无自带 color，helper 只会取 colors[0]，逐柱配色被静默丢弃。改用 [{label,data,color:[...]}] 标准对象写法');
  }
};
const hookedHelper = helper.indexOf('new Chart(ctx,{') >= 0
  ? helper.replace('new Chart(ctx,{', '__pre(data,opts), new Chart(ctx,{')
  : helper;
if (hookedHelper === helper) console.log('NOTE 未能挂钩 _base（helper 已改版），逐柱配色检查跳过');
eval(hookedHelper);
for (const cb of callBlocks) eval(cb);

let bad = 0;
const problems = [];
if (colorTrap.length) { bad++; colorTrap.forEach(p => problems.push(p)); }
for (const c of charts) {
  const ds = c.cfg.data.datasets, labels = c.cfg.data.labels, iss = [];
  if (!Array.isArray(ds) || !ds.length) iss.push('datasets 为空');
  (ds || []).forEach((d, i) => {
    if (!Array.isArray(d.data)) iss.push(`ds${i}.data 非数组(${typeof d.data})`);
    else if (labels && d.data.length !== labels.length) iss.push(`ds${i}.data 长度 ${d.data.length} ≠ labels ${labels.length}`);
    if (!d.label) iss.push(`ds${i} 缺 label`);
    if (!d.borderColor) iss.push(`ds${i} 缺颜色`);
  });
  if (iss.length) { bad++; problems.push(`${c.id}: ${iss.join('; ')}`); }
}

const missing = canvases.filter(id => !drawn.includes(id));
const orphan = drawn.filter(id => !canvases.includes(id));

console.log(`canvas: ${canvases.length}  |  draw 调用: ${drawn.length}  |  实渲染: ${charts.length}`);
if (missing.length) { bad++; problems.push(`有 canvas 但无 draw 调用（必空白）: ${missing.join(', ')}`); }
if (orphan.length) problems.push(`有 draw 调用但无 canvas（无效）: ${orphan.join(', ')}`);
problems.forEach(p => console.log('FAIL ' + p));
console.log(bad === 0 ? `PASS 全部 ${charts.length} 张图表结构合法` : `共 ${bad} 处问题`);
process.exit(bad === 0 ? 0 : 1);
