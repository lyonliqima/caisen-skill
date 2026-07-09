#!/usr/bin/env node
// Serenity radar: turn @aleabitoreddit's mention archive into attention-momentum
// signals — what she is heating up on, what is newly emerging, and how themes are
// rotating. Read-only over the events CSV. Output is a CANDIDATE LIST, not advice.
//
// Usage:
//   node radar.js [--events <path>] [--asof <YYYY-MM-DD>] [--window 14] [--top 20] [--json]
// Defaults: events = $FOLLOW_ALEABITO_REPORTS_DIR/aleabito-mentions-events.csv (or the
// workspace reports dir), asof = latest event date in the data, window = 14 days.

import { readFileSync, existsSync } from "fs";
import { join } from "path";
import { homedir } from "os";

const THEMES = [
  { name: "CPO / photonics / optical", tickers: ["SIVE","AAOI","LITE","COHR","POET","JBL","AXTI","SOI","IQE","TSEM","MTSI","LPK","AEHR","CRDO","GLW","AEVA","LPTH","OSS","VLN","ALRIB","NOK"], keywords: ["cpo","photonic","laser","optical","transceiver","silicon photonics","inp","epiwafer","epitaxial","substrate","pluggable","co-packaged","fau","els"] },
  { name: "Power semis / 800VDC / grid", tickers: ["XFAB","NVTS","POWI","WOLF","ON","IFNNY","ETN","GEV","PWR","HPS.A"], keywords: ["800vdc","800 vdc","sic","gan","wide bandgap","power semi","power semiconductor","transformer","grid"] },
  { name: "AI compute / neocloud / memory", tickers: ["NVDA","AMD","MU","MRVL","AVGO","INTC","MSFT","AMZN","GOOGL","META","NBIS","IREN","CIFR","CRWV","WULF","ALAB","TSM","GFS","AAPL","ORCL","HUT","BITF","CLSK","MARA","SNDK"], keywords: ["gpu","hbm","asic","hyperscaler","data center","datacenter","neocloud","inference","maia","tpu","memory","mining"] },
  { name: "Western supply chain / policy", tickers: ["RPI"], keywords: ["chips act","funding","supply chain","sovereignty","nist","msci","nasdaq","index inclusion","europe","reshoring"] },
  { name: "Space / defense", tickers: ["RKLB","ASTS","SPCE","SPCX","LMT","NOC"], keywords: ["satcom","satellite","space","defense"] },
  { name: "Fintech / crypto / consumer / squeeze", tickers: ["HOOD","SOFI","BULL","ETORO","KSPI","COIN","IBIT","BTC","MSTR","CRCL","HIMS","UPWK","GME","DNUT","NVO","UNH","OSCR","BKKT","RDDT","PYPL","V","SG","OKLO","IONQ","QBTS"], keywords: ["short interest","squeeze","etf","stablecoin","dilution","ipo"] },
];

function arg(name, fallback) { const i = process.argv.indexOf(name); return i === -1 ? fallback : (process.argv[i + 1] ?? fallback); }
function hasFlag(name) { return process.argv.includes(name); }

function parseCsv(text) {
  const rows = []; let row = [], f = "", q = false;
  for (let i = 0; i < text.length; i++) { const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; }
    else { if (c === '"') q = true; else if (c === ",") { row.push(f); f = ""; } else if (c === "\n") { row.push(f); rows.push(row); row = []; f = ""; } else if (c === "\r") {} else f += c; } }
  if (f.length || row.length) { row.push(f); rows.push(row); }
  return rows;
}

function dayDiff(a, b) { return Math.round((new Date(a + "T00:00:00Z") - new Date(b + "T00:00:00Z")) / 86400000); }

function resolveEvents() {
  const cli = arg("--events", null);
  if (cli) return cli;
  const base = process.env.FOLLOW_ALEABITO_REPORTS_DIR || join(homedir(), "Documents", "us stock marketplace", "reports");
  return join(base, "aleabito-mentions-events.csv");
}

function themeOf(ticker, text) {
  const t = (text || "").toLowerCase();
  for (const th of THEMES) {
    if (th.tickers.includes(ticker)) return th.name;
    if (th.keywords.some((k) => t.includes(k))) return th.name;
  }
  return "Other";
}

function main() {
  const path = resolveEvents();
  if (!existsSync(path)) { console.error(`events CSV not found: ${path}`); process.exit(1); }
  const rows = parseCsv(readFileSync(path, "utf8"));
  const h = rows[0]; const idx = Object.fromEntries(h.map((x, i) => [x, i]));
  const ev = rows.slice(1)
    .map((r) => ({ date: (r[idx.created_at] || "").slice(0, 10), text: r[idx.text] || "", tickers: (r[idx.tickers] || "").split("|").filter(Boolean) }))
    .filter((e) => e.date);

  const W = Number(arg("--window", 14));
  const TOP = Number(arg("--top", 20));
  const allDates = ev.map((e) => e.date).sort();
  const asof = arg("--asof", allDates[allDates.length - 1]);

  // per-ticker stats
  const stat = new Map();
  for (const e of ev) {
    const d = dayDiff(asof, e.date); // days before asof (>=0 means on/before asof)
    if (d < 0) continue;
    for (const t of new Set(e.tickers)) {
      if (!stat.has(t)) stat.set(t, { ticker: t, total: 0, recent: 0, prev: 0, first: e.date, last: e.date });
      const s = stat.get(t);
      s.total++;
      if (e.date < s.first) s.first = e.date;
      if (e.date > s.last) s.last = e.date;
      if (d < W) s.recent++; else if (d < 2 * W) s.prev++;
    }
  }
  const list = [...stat.values()].map((s) => ({ ...s, velocity: s.recent - s.prev, ageDays: dayDiff(asof, s.first), recencyDays: dayDiff(asof, s.last) }));

  // 1) HEATING: positive velocity, currently active, ranked by velocity then recent volume
  const heating = list.filter((s) => s.recent >= 2 && s.velocity > 0)
    .sort((a, b) => b.velocity - a.velocity || b.recent - a.recent).slice(0, TOP);

  // 2) NEW ENTRANTS: first seen within the recent window
  const fresh = list.filter((s) => s.ageDays <= W && s.recent >= 2).sort((a, b) => b.recent - a.recent || a.ageDays - b.ageDays).slice(0, TOP);

  // 3) CONVICTION WATCH: high recent volume AND sustained (active for >= W days), still hot
  const conviction = list.filter((s) => s.recent >= 4 && s.recencyDays <= Math.ceil(W / 2) && s.ageDays >= W)
    .sort((a, b) => b.recent - a.recent).slice(0, TOP);

  // 4) THEME ROTATION: theme share recent vs prior window
  const themeRecent = new Map(), themePrev = new Map();
  for (const e of ev) {
    const d = dayDiff(asof, e.date); if (d < 0 || d >= 2 * W) continue;
    const bucket = d < W ? themeRecent : themePrev;
    const themes = new Set(e.tickers.map((t) => themeOf(t, e.text)));
    if (e.tickers.length === 0) themes.add(themeOf("", e.text));
    for (const th of themes) bucket.set(th, (bucket.get(th) || 0) + 1);
  }
  const themes = [...new Set([...themeRecent.keys(), ...themePrev.keys()])]
    .map((th) => ({ theme: th, recent: themeRecent.get(th) || 0, prev: themePrev.get(th) || 0 }))
    .map((t) => ({ ...t, delta: t.recent - t.prev })).sort((a, b) => b.recent - a.recent);

  const out = {
    asof, window_days: W,
    heating: heating.map((s) => ({ ticker: s.ticker, recent: s.recent, prev: s.prev, velocity: s.velocity, total: s.total, last: s.last })),
    new_entrants: fresh.map((s) => ({ ticker: s.ticker, recent: s.recent, first_seen: s.first, age_days: s.ageDays })),
    conviction_watch: conviction.map((s) => ({ ticker: s.ticker, recent: s.recent, total: s.total, active_days: s.ageDays })),
    theme_rotation: themes.map((t) => ({ theme: t.theme, recent: t.recent, prev: t.prev, delta: t.delta })),
  };

  if (hasFlag("--json")) { console.log(JSON.stringify(out, null, 2)); return; }

  const fmt = (arr, cols) => arr.map((r) => cols.map((c) => `${c[0]}=${r[c[1]]}`).join("  ")).join("\n");
  console.log(`# Serenity radar — asof ${asof}, window ${W}d (recent ${W}d vs prior ${W}d)\n`);
  console.log(`## 🔥 Heating (attention momentum — recent vs prior mentions)`);
  console.log(fmt(out.heating, [["ticker","ticker"],["Δ","velocity"],["recent","recent"],["prev","prev"]]) || "(none)");
  console.log(`\n## 🆕 New entrants (first appeared within ${W}d)`);
  console.log(fmt(out.new_entrants, [["ticker","ticker"],["recent","recent"],["since","first_seen"]]) || "(none)");
  console.log(`\n## 🎯 Conviction watch (repeated + still active)`);
  console.log(fmt(out.conviction_watch, [["ticker","ticker"],["recent","recent"],["total","total"]]) || "(none)");
  console.log(`\n## 🔄 Theme rotation (recent vs prior window)`);
  console.log(out.theme_rotation.map((t) => `${t.delta >= 0 ? "▲" : "▼"} ${t.theme}: ${t.recent} (was ${t.prev}, Δ${t.delta >= 0 ? "+" : ""}${t.delta})`).join("\n"));
  console.log(`\n— Candidate signals only. Run each through the serenity-method checklist before treating as a thesis. Not investment advice.`);
}

main();
