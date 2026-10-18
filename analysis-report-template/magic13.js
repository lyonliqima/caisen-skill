/* ═══════════════════════════════════════════════════════════════
   神奇13节拍 · Chart.js 版（2026-10-18 用户定制，画图强制使用）
   ═══════════════════════════════════════════════════════════════
   来源：用户通达信主图源码（比国内"神奇9转"更严格的 13 计数版）：
     上升计数 A1:=C>REF(C,4)  连续成立天数 → 数到 13 标在最高价*1.02 上方，紫色
     下跌计数 B1:=C<REF(C,4)  连续成立天数 → 数到 13 标在最低价*0.98 下方，绿色
   显示规则与 TDX 版逐条等价：
     - BACKSET(TJ11>0,13)：某方向计数首次到达 13 的那根 K 线，回标前 13 根，显示 1..13
     - ISLASTBAR AND BETWEEN(NT,5,12)：最新一根若计数在 5..12（未数满），回标当前段
       （盘中实时显示，收盘才算数——数字会随盘中走势增减）
   含义：13 = 单边动能极端衰竭区。下跌段绿色 11/12/13 = 左侧超跌反弹的观察窗；
         上升段紫色 13 = 逼空末端衰竭警示。
   ⚠️ 本实现是"Setup 直接数到 13"，非德马克原版 TD Countdown（原版倒数用
      C<REF(C,2) 且有启动/取消规则），作为衰竭指示器使用，勿当原版 TD 序列引用。

   ── 用法（主图 Chart.js，两行接入）──
   <script src="magic13.js内容 或 内联"></script>
   const m13 = magic13(D.k60.c, D.k60.h, D.k60.l);   // closes, highs?, lows?
                                                     // 无高低价时省略，自动用收盘价定位
   new Chart(document.getElementById('c1'), {
     data:{...原主图配置...},
     options:{...},
     plugins:[magic13Plugin(m13)]        // ← 挂这里，数字直接画在主图上
   });
   ── 可选参数 ──
   magic13Plugin(m13, {upColor:'#e879f9', dnColor:'#3fb950',
                       upFactor:1.02, dnFactor:0.98, minShow:5})
   ── 直接取数（不想画图、只想引用节拍数时）──
   m13.upCnt[i] / m13.dnCnt[i] = 第 i 根的上升/下跌节拍计数
   m13.up / m13.dn = [[下标, 显示数字], ...] 待标列表
   ═══════════════════════════════════════════════════════════════ */

function magic13(closes, highs, lows){
  const n = closes.length;
  const up = new Array(n).fill(0), dn = new Array(n).fill(0);
  for(let i=4;i<n;i++){
    up[i] = closes[i] > closes[i-4] ? up[i-1]+1 : 0;
    dn[i] = closes[i] < closes[i-4] ? dn[i-1]+1 : 0;
  }
  function marks(cnt){
    const m = [];
    // 已完结段：计数恰为 13 的那根 → 回标前 13 根（TDX BACKSET(x,13) 语义）
    for(let i=4;i<n;i++){
      if(cnt[i]===13){ for(let k=0;k<13;k++) m.push([i-k, 13-k]); }
    }
    // 末根在数的段：5..12 回标当前段（ISLASTBAR AND BETWEEN 语义）
    const L = cnt[n-1];
    if(L>=5 && L<=12){ for(let k=0;k<L;k++) m.push([n-1-k, L-k]); }
    return m;
  }
  return {
    up: marks(up), dn: marks(dn),
    upCnt: up, dnCnt: dn,
    highs: highs || closes, lows: lows || closes,
    fallback: !(highs && lows)   // 无高低价时 true，定位改用收盘价
  };
}

function magic13Plugin(m13, opts){
  opts = opts || {};
  const upC = opts.upColor || '#e879f9';    // 紫（浅品红，深色底可读）
  const dnC = opts.dnColor || '#3fb950';    // 绿
  const upF = opts.upFactor || 1.02;
  const dnF = opts.dnFactor || 0.98;
  const minShow = opts.minShow != null ? opts.minShow : 5;  // <5 不显示（同 TDX）
  return {
    id: 'magic13',
    afterDatasetsDraw(chart){
      const ys = chart.scales.y, xs = chart.scales.x;
      if(!ys || !xs || !m13) return;
      const ctx = chart.ctx, area = chart.chartArea;
      ctx.save();
      ctx.font = 'bold 10px -apple-system,"PingFang SC",sans-serif';
      ctx.textAlign = 'center';
      ctx.globalAlpha = .95;
      m13.up.forEach(function(p){
        if(p[1] < minShow) return;
        const px = xs.getPixelForValue(p[0]);
        const py = ys.getPixelForValue(m13.highs[p[0]] * upF);
        if(px < area.left || px > area.right || py < area.top) return;
        ctx.fillStyle = upC;
        ctx.fillText(String(p[1]), px, py - 2);
      });
      m13.dn.forEach(function(p){
        if(p[1] < minShow) return;
        const px = xs.getPixelForValue(p[0]);
        const py = ys.getPixelForValue(m13.lows[p[0]] * dnF);
        if(px < area.left || px > area.right || py > area.bottom) return;
        ctx.fillStyle = dnC;
        ctx.fillText(String(p[1]), px, py + 10);
      });
      ctx.restore();
    }
  };
}

/* Node 端自检：node -e 'require("./magic13.js") 时不执行（浏览器全局挂载）'
   自检脚本见同目录 _selftest_magic13.js（若存在） */
if(typeof module !== 'undefined' && module.exports){ module.exports = {magic13, magic13Plugin}; }
