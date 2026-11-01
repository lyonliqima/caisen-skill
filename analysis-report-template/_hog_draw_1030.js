
drawLine('c1', HD_D, [
  {label:'LH2701 收盘', data:HD_C, color:'#ffd166'},
  {label:'MA5', data:HD_MA5, color:'#4a9eff'},
  {label:'MA20', data:HD_MA20, color:'#ff9f43'},
  {label:'MA60', data:HD_MA60, color:'#c084fc'}
]);
drawBar('c2', CONT, CONT_PX, {label:'2026-10-30 收盘价(元/吨)', colors:'#ffd166'});
drawLine('c2b', CONT.slice(1), [
  {label:'相邻合约年化持有成本(%)', data:CONT_ANN, color:'#ff4d4f'}
]);
drawLine('c3', BASIS_D, [
  {label:'LH2701 期货', data:FUT, color:'#ffd166'},
  {label:'现货·养猪网口径', data:SPOT_ZY, color:'#1ec77a'},
  {label:'现货·猪易通瘦肉型口径', data:SPOT_CJ, color:'#4a9eff', borderDash:[6,4]}
]);
drawLine('c4', NF_LABEL, [
  {label:'钢联样本能繁(万头)', data:NF_STEEL, color:'#4a9eff'},
  {label:'统计局能繁(万头)', data:NF_STAT, color:'#ffd166'}
]);
drawBar('c5', VAR_D, [OUTPUT_YOY, SLAUGHTER_YOY], {names:['猪肉产量同比(%)','生猪出栏同比(%)']});
drawLine('c6', PL_D, [
  {label:'猪粮比', data:PL_RATIO, color:'#ff9f43'},
  {label:'自繁自养利润(元/头,右轴)', data:PL_PROFIT, color:'#ff4d4f'}
]);
drawLine('c7', WT_D, [
  {label:'全国均重(kg)', data:WT_ALL, color:'#ffd166'},
  {label:'集团均重(kg)', data:WT_GRP, color:'#4a9eff'},
  {label:'散户均重(kg)', data:WT_IND, color:'#ff4d4f'}
]);
drawLine('c8', FR_D, [
  {label:'冻品库容率(%)', data:FR_RATE, color:'#c084fc'},
  {label:'屠宰开工率(%)', data:PK_RATE, color:'#1ec77a'}
]);
drawBar('c9', SEAT_N, SEAT_V, {label:'LH2701 前20席净持仓(手, 负=净空)', colors:'#ff4d4f'});
drawBar('c10', EMO_N, EMO_V, {label:'情绪分项读数(-10~+10)', colors:'#ff9f43'});
drawBar('c11', EXP_N, EXP_C, {label:'各席置信度(0-100)', colors:'#4a9eff'});
drawDoughnut('c12', ['看空/偏空','观望/不出单边','看多(不可执行)'], [6, 6, 1]);
drawLine('c13', COST_D, [
  {label:'公开完全成本(元/kg)', data:COST_LINE, color:'#ffd166'},
  {label:'成本·动态收缩修正后', data:COST_ADJ, color:'#c084fc', borderDash:[6,4]},
  {label:'现货均价(元/kg)', data:SPOT_LINE, color:'#ff4d4f'}
]);
drawLine('c14', FUT_LABELS, [
  {label:'LH2703 历史收盘', data:HIST_TAIL.concat(Array(FUTD.length).fill(null)), color:'#ffd166'},
  {label:'LH2703 预测中枢', data:Array(N_PREV).fill(null).concat(FC), color:'#4a9eff', borderDash:[6,4]},
  {label:'预测上沿', data:Array(N_PREV).fill(null).concat(UPPER), color:'#1ec77a', borderDash:[3,3]},
  {label:'预测下沿', data:Array(N_PREV).fill(null).concat(LOWER), color:'#ff4d4f', borderDash:[3,3]}
], {fill:true});
