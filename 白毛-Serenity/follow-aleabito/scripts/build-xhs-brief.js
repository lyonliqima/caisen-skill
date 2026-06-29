#!/usr/bin/env node

import { readFile, writeFile } from "fs/promises";
import { existsSync } from "fs";

const DEFAULT_OUTPUT = "/tmp/follow-aleabito-xhs-brief.md";

function argValue(name) {
  const idx = process.argv.indexOf(name);
  return idx === -1 ? null : process.argv[idx + 1] || null;
}

function parseCsvLine(line) {
  const cells = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') {
        cell += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        cell += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      cells.push(cell);
      cell = "";
    } else {
      cell += ch;
    }
  }
  cells.push(cell);
  return cells;
}

async function readCsv(path) {
  if (!path || !existsSync(path)) return [];
  const text = await readFile(path, "utf-8");
  const lines = text.split(/\r?\n/).filter((line) => line.length > 0);
  if (lines.length === 0) return [];
  const headers = parseCsvLine(lines[0]);
  return lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    return Object.fromEntries(headers.map((header, idx) => [header, cells[idx] ?? ""]));
  });
}

function numberValue(row, key) {
  const value = Number(row[key]);
  return Number.isFinite(value) ? value : 0;
}

function markdownTable(rows) {
  if (rows.length === 0) return "No ticker rows found.";
  const lines = [
    "| Rank | Ticker | Mentioned posts | Raw occurrences | Theme | Priority | Last seen |",
    "|---:|---|---:|---:|---|---|---|",
  ];
  for (const row of rows) {
    lines.push(
      `| ${row.rank || ""} | ${row.ticker} | ${row.mentioned_posts} | ${row.raw_occurrences} | ${row.primary_theme || ""} | ${row.research_priority || ""} | ${(row.last_seen || "").slice(0, 10)} |`,
    );
  }
  return lines.join("\n");
}

function lastNDaysDaily(dailyRows, days) {
  if (dailyRows.length === 0) return [];
  const dates = [...new Set(dailyRows.map((row) => row.date).filter(Boolean))].sort();
  const selectedDates = new Set(dates.slice(-days));
  const byTicker = new Map();
  for (const row of dailyRows) {
    if (!selectedDates.has(row.date)) continue;
    const ticker = row.ticker;
    if (!byTicker.has(ticker)) byTicker.set(ticker, { ticker, mentioned_posts: 0, raw_occurrences: 0 });
    const bucket = byTicker.get(ticker);
    bucket.mentioned_posts += numberValue(row, "mentioned_posts");
    bucket.raw_occurrences += numberValue(row, "raw_occurrences");
  }
  return [...byTicker.values()].sort(
    (a, b) => b.mentioned_posts - a.mentioned_posts || b.raw_occurrences - a.raw_occurrences || a.ticker.localeCompare(b.ticker),
  );
}

function topTickersByTheme(rows) {
  const themes = new Map();
  for (const row of rows) {
    const theme = row.primary_theme || "Other / unclassified";
    if (!themes.has(theme)) themes.set(theme, []);
    themes.get(theme).push(row);
  }
  return [...themes.entries()]
    .map(([theme, items]) => ({
      theme,
      items: items
        .sort((a, b) => numberValue(b, "mentioned_posts") - numberValue(a, "mentioned_posts"))
        .slice(0, 5),
    }))
    .sort((a, b) => numberValue(b.items[0] || {}, "mentioned_posts") - numberValue(a.items[0] || {}, "mentioned_posts"));
}

function buildFullDraft(topRows, recentRows) {
  const top = topRows.slice(0, 10);
  const topNames = top.slice(0, 5).map((row) => `$${row.ticker}`).join(", ");
  const recentNames = recentRows.slice(0, 5).map((row) => `$${row.ticker}`).join(", ") || topNames;
  return [
    "## Full Version Draft Scaffold",
    "",
    "标题备选：",
    "- 我把 Serenity 最近所有提到的股票做成表：热度最高的是谁？",
    "- AleaBito 到底在反复看哪些股票？一张表讲清楚",
    "- 别急着抄作业：先看她反复提到的股票地图",
    "",
    "正文方向：",
    "",
    `我把 @aleabitoreddit / Serenity 提到的股票做了累计统计。先说最重要的一点：提到次数多，不等于可以买。它只说明“她最近反复在研究或讨论这里”，适合拿来做研究地图。`,
    "",
    `目前热度最靠前的是：${topNames || "暂无数据"}。最近几天更活跃的是：${recentNames || "暂无数据"}。`,
    "",
    "小白怎么理解这张表：",
    "- mentioned_posts = 有多少条不同内容提到这只股票，比较适合看关注度。",
    "- raw_occurrences = ticker 总共出现几次，适合看她是不是在一条内容里反复强调。",
    "- replies 也算，因为她很多高信号观点是在回复里补充的。",
    "",
    "第一性原理：",
    "一家公司长期值钱，最后不是因为网上提到多，而是因为它能不能持续卖出有需求的产品，并把收入变成现金利润。半导体、光通信、AI 基建这类公司尤其要看三件事：需求是不是真的增长、产能/技术是不是稀缺、客户会不会轻易换供应商。",
    "",
    "Buffett 框架怎么落地：",
    "- 护城河：先看技术认证、客户绑定、切换成本，不是看故事热不热。",
    "- 赚钱能力：先看收入、毛利率、自由现金流，没证明就只能算研究线索。",
    "- 客户替换风险：如果客户很集中、二供很多、产品差异不大，风险就高。",
    "- 是否 Buffett 式好公司：稳定赚钱、资本开支可控、长期竞争优势清楚，才更接近。",
    "",
    "结论：这份表适合当“研究地图”，不是买入清单。下一步应该从最高频 ticker 里挑少数几家公司，继续查财报、客户、利润率、估值和风险。",
    "",
    "仅作信息跟踪，不构成投资建议。",
  ].join("\n");
}

function buildUnder1000Draft(topRows, recentRows) {
  const top = topRows.slice(0, 8);
  const topNames = top.map((row) => `$${row.ticker}`).join(", ");
  const recentNames = recentRows.slice(0, 5).map((row) => `$${row.ticker}`).join(", ") || topNames;
  return [
    "## Under 1000 Chinese Characters Draft",
    "",
    "我把 @aleabitoreddit / Serenity 提到的股票做了累计统计。",
    "",
    `热度靠前：${topNames || "暂无数据"}。`,
    `最近更活跃：${recentNames || "暂无数据"}。`,
    "",
    "小白版解释：提到次数多，不等于可以买，只代表她反复在讨论，适合放进研究清单。",
    "",
    "第一性原理看股票：公司最后值不值钱，取决于它能不能长期卖出真实需要的产品，并把收入变成利润和现金流。",
    "",
    "Buffett 看法要更严格：",
    "1. 有没有护城河？看技术、认证、客户切换成本。",
    "2. 能不能赚钱？看收入、毛利率、现金流。",
    "3. 客户会不会换掉它？看客户集中度和二供风险。",
    "4. 是不是 Buffett 式好公司？没稳定赚钱前，只能算研究地图，不是投资结论。",
    "",
    "我的结论：这份数据最有价值的地方，是帮我们知道她最近重点盯哪里。真正下判断，还要回到财报、客户、利润率和估值。",
    "",
    "仅作信息跟踪，不构成投资建议。",
  ].join("\n");
}

async function main() {
  const inputPath = argValue("--input");
  const dailyPath = argValue("--daily");
  const outputPath = argValue("--output") || DEFAULT_OUTPUT;
  const variants = argValue("--variants") || "both";
  const topN = Number(argValue("--top") || 20);
  if (!inputPath) throw new Error("Missing --input <cumulative-csv>");

  const rows = (await readCsv(inputPath)).sort(
    (a, b) => numberValue(a, "rank") - numberValue(b, "rank") || a.ticker.localeCompare(b.ticker),
  );
  const dailyRows = await readCsv(dailyPath);
  const recentRows = lastNDaysDaily(dailyRows, 7);
  const topRows = rows.slice(0, topN);
  const themeGroups = topTickersByTheme(rows);

  const lines = [
    "# Follow AleaBito Xiaohongshu Brief",
    "",
    `Generated: ${new Date().toISOString()}`,
    `Input: ${inputPath}`,
    dailyPath ? `Daily input: ${dailyPath}` : "Daily input: not provided",
    `Ticker rows: ${rows.length}`,
    "",
    "## Writing Instructions",
    "",
    "- Write in Chinese for beginner retail investors.",
    "- Do not make buy/sell calls.",
    "- Explain jargon before using it.",
    "- Use first principles: demand, supply bottleneck, pricing power, cash profit, customer switching cost.",
    "- Buffett answers must be direct: moat, profitability, customer replacement risk, Buffett-style business, current conclusion.",
    "- Treat mention frequency as a research map, not conviction.",
    "",
    "## Top Ticker Table",
    "",
    markdownTable(topRows),
    "",
    "## Last 7 Active Tickers",
    "",
    recentRows.length
      ? "| Ticker | Mentioned posts | Raw occurrences |\n|---|---:|---:|\n" +
        recentRows.slice(0, 15).map((row) => `| ${row.ticker} | ${row.mentioned_posts} | ${row.raw_occurrences} |`).join("\n")
      : "Daily CSV not provided or empty.",
    "",
    "## Theme Groups",
    "",
  ];

  for (const group of themeGroups.slice(0, 8)) {
    lines.push(`### ${group.theme}`, "");
    lines.push(group.items.map((row) => `- $${row.ticker}: ${row.mentioned_posts} mentioned posts, priority ${row.research_priority}`).join("\n"));
    lines.push("");
  }

  if (variants === "both" || variants === "full") {
    lines.push(buildFullDraft(topRows, recentRows), "");
  }
  if (variants === "both" || variants === "under-1000") {
    lines.push(buildUnder1000Draft(topRows, recentRows), "");
  }

  await writeFile(outputPath, `${lines.join("\n")}\n`);
  console.log(JSON.stringify({ status: "ok", output: outputPath, rows: rows.length, variants }, null, 2));
}

main().catch((err) => {
  console.error(JSON.stringify({ status: "error", error: err.message }, null, 2));
  process.exitCode = 1;
});
