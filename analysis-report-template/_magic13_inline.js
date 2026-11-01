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
