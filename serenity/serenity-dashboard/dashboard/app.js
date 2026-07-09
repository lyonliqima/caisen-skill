let state = { symbols: [], active: null, filter: 'all', chart: null };
const $ = (id) => document.getElementById(id);
const fmtDate = (v) => v ? new Date(v).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-';
const money = (v) => v == null ? '-' : `$${Number(v).toFixed(2)}`;
const clip = (s, n = 220) => (s || '').length > n ? `${s.slice(0, n)}...` : (s || '');
const dateOnly = (v) => (v || '').slice(0, 10);

function wrapTooltipText(text, maxChars = 54, maxLines = 9) {
  const lines = [];
  const paragraphs = String(text || '').replace(/\s+/g, ' ').trim().split(/\n+/);
  for (const paragraph of paragraphs) {
    const words = paragraph.split(' ');
    let line = '';
    for (const word of words) {
      if (word.length > maxChars) {
        if (line) lines.push(line);
        for (let i = 0; i < word.length; i += maxChars) lines.push(word.slice(i, i + maxChars));
        line = '';
      } else if (!line || `${line} ${word}`.length <= maxChars) {
        line = line ? `${line} ${word}` : word;
      } else {
        lines.push(line);
        line = word;
      }
      if (lines.length >= maxLines) break;
    }
    if (line && lines.length < maxLines) lines.push(line);
    if (lines.length >= maxLines) break;
  }
  if (lines.length === maxLines && text.length > lines.join(' ').length) {
    lines[maxLines - 1] = `${lines[maxLines - 1].replace(/\.{3}$/, '')}...`;
  }
  return lines.length ? lines : [''];
}

async function json(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

async function init() {
  const summary = await json('/api/summary');
  state.symbols = summary.symbols || [];
  renderKpis(summary.stats || {});
  renderSymbols();
  renderFeed((await json('/api/feed?limit=36')).items || []);
  const first = state.symbols.find(s => s.has_prices) || state.symbols[0];
  if (first) selectSymbol(first.symbol);
}

function renderKpis(s) {
  const items = [
    ['tweets', '帖子入库'], ['mentions', 'symbol 提及'], ['symbols', '唯一 symbol'], ['priced_symbols', '已下载价格'], ['latest_mention', '最新提及']
  ];
  $('kpis').innerHTML = items.map(([k, label]) => `
    <div class="kpi"><b>${k === 'latest_mention' ? fmtDate(s[k]) : (s[k] ?? 0)}</b><span>${label}</span></div>
  `).join('');
}

function visibleSymbols() {
  const q = $('symbolSearch').value.trim().toUpperCase();
  return state.symbols.filter(s => {
    if (q && !s.symbol.includes(q)) return false;
    if (state.filter === 'priced' && !s.has_prices) return false;
    if (state.filter === 'hot' && s.mention_count < 5) return false;
    return true;
  });
}

function renderSymbols() {
  $('symbols').innerHTML = visibleSymbols().map(s => `
    <button class="symbol-row ${state.active === s.symbol ? 'active' : ''}" data-symbol="${s.symbol}">
      <span class="ticker">${s.symbol}</span>
      <span><b>${s.mention_count}</b> mentions<br><span class="tiny">latest ${fmtDate(s.latest_mention)}</span></span>
      <span class="badge">${s.has_prices ? money(s.last_close) : 'no price'}</span>
    </button>
  `).join('');
  document.querySelectorAll('.symbol-row').forEach(btn => btn.onclick = () => selectSymbol(btn.dataset.symbol));
}

async function selectSymbol(symbol) {
  state.active = symbol;
  renderSymbols();
  const data = await json(`/api/symbol/${encodeURIComponent(symbol)}`);
  const info = state.symbols.find(s => s.symbol === symbol) || {};
  $('activeTitle').textContent = `$${symbol}`;
  $('activeMeta').innerHTML = [
    `${info.mention_count || 0} mentions`,
    `${data.prices.length} bars`,
    `first ${fmtDate(info.first_mention)}`,
    `latest ${fmtDate(info.latest_mention)}`
  ].map(x => `<span>${x}</span>`).join('');
  $('neighbors').innerHTML = (data.neighbors || []).slice(0, 12).map(n => `<span>${n.symbol} x${n.count}</span>`).join('');
  renderChart(data);
}

function renderChart(data) {
  const allPrices = data.prices || [];
  const mentions = data.mentions || [];
  const firstMentionDate = mentions.reduce((min, m) => {
    const d = dateOnly(m.mentioned_at);
    return d && (!min || d < min) ? d : min;
  }, '');
  const prices = firstMentionDate ? allPrices.filter(p => p.date >= firstMentionDate) : allPrices;
  const priceByDate = new Map(prices.map(p => [p.date, p.close]));
  const mentionPoints = mentions.map(m => {
    const d = dateOnly(m.mentioned_at);
    const nearest = prices.find(p => p.date >= d) || prices[prices.length - 1];
    const chartDate = priceByDate.has(d) ? d : nearest?.date;
    return chartDate ? { x: chartDate, y: priceByDate.get(chartDate), mention: m } : null;
  }).filter(Boolean).filter(p => p.y != null);

  const ctx = $('priceChart');
  if (state.chart) state.chart.destroy();
  state.chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: prices.map(p => p.date),
      datasets: [
        { label: `${data.symbol} close`, data: prices.map(p => p.close), borderColor: '#1f7a4f', borderWidth: 2.5, pointRadius: 0, tension: .22, fill: true, backgroundColor: 'rgba(31,122,79,.10)' },
        { type: 'scatter', label: 'mentions', data: mentionPoints, parsing: false, pointRadius: 6, pointHoverRadius: 9, pointBackgroundColor: '#ff6b35', pointBorderColor: '#182019', pointBorderWidth: 1.5 }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: false },
      onHover: (event, elements) => {
        event.native.target.style.cursor = elements.some(el => el.datasetIndex === 1) ? 'pointer' : 'default';
      },
      onClick: (event, elements) => {
        const point = elements.find(el => el.datasetIndex === 1);
        if (!point) return;
        const mention = state.chart.data.datasets[1].data[point.index]?.mention;
        if (mention?.url) window.open(mention.url, '_blank', 'noopener,noreferrer');
      },
      scales: {
        x: { grid: { color: 'rgba(24,32,25,.08)' }, ticks: { maxTicksLimit: 8 } },
        y: { grid: { color: 'rgba(24,32,25,.08)' }, ticks: { callback: v => `$${v}` } }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          padding: 14,
          bodySpacing: 5,
          callbacks: {
            title: items => items[0].raw?.mention ? fmtDate(items[0].raw.mention.mentioned_at) : items[0].label,
            label: item => {
              if (!item.raw?.mention) return `${money(item.parsed.y)}`;
              return [`${data.symbol} close ${money(item.parsed.y)}`, ...wrapTooltipText(item.raw.mention.text)];
            }
          }
        }
      }
    }
  });
}

function renderFeed(items) {
  $('feed').innerHTML = items.map(i => `
    <article class="feed-item">
      <div><span class="ticker">$${i.symbol}</span> <span class="tiny">${fmtDate(i.mentioned_at)} / ${i.source}</span></div>
      <p>${escapeHtml(clip(i.text, 340))}</p>
      <a href="${i.url}" target="_blank" rel="noreferrer">open on X</a>
    </article>
  `).join('');
}

function escapeHtml(s) {
  return (s || '').replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}

document.querySelectorAll('.tabs button').forEach(btn => btn.onclick = () => {
  document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  state.filter = btn.dataset.filter;
  renderSymbols();
});
$('symbolSearch').addEventListener('input', renderSymbols);
init().catch(err => document.body.insertAdjacentHTML('afterbegin', `<pre>${escapeHtml(err.message)}</pre>`));
