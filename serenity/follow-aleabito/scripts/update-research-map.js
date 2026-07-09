#!/usr/bin/env node

import { mkdir, readFile, writeFile } from "fs/promises";
import { dirname } from "path";
import { existsSync } from "fs";

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

async function readJSON(path, fallback) {
  if (!path || !existsSync(path)) return fallback;
  return JSON.parse(await readFile(path, "utf-8"));
}

function numberValue(row, key) {
  const value = Number(row[key]);
  return Number.isFinite(value) ? value : 0;
}

function parseTickers(value) {
  return String(value || "")
    .split("|")
    .map((ticker) => ticker.trim().toUpperCase())
    .filter(Boolean);
}

function defaultBuffett(previous = {}) {
  return {
    moat: previous.moat || "unverified",
    profitability: previous.profitability || "unverified",
    customer_replacement_risk: previous.customer_replacement_risk || "unverified",
    buffett_style_business: previous.buffett_style_business || "not yet proven",
    current_conclusion: previous.current_conclusion || "research map",
  };
}

function recentEventsForTicker(events, ticker) {
  return events
    .filter((event) => parseTickers(event.tickers).includes(ticker))
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .slice(0, 5)
    .map((event) => ({
      created_at: event.created_at,
      kind: event.kind,
      source_url: event.source_url,
      text: String(event.text || "").slice(0, 360),
    }));
}

function buildMap({ events, summary, previous }) {
  const previousTickers = new Map((previous.tickers || []).map((row) => [row.ticker, row]));
  const tickers = summary.map((row) => {
    const prior = previousTickers.get(row.ticker) || {};
    return {
      ticker: row.ticker,
      stats: {
        rank: numberValue(row, "rank"),
        mentioned_posts: numberValue(row, "mentioned_posts"),
        raw_occurrences: numberValue(row, "raw_occurrences"),
        post_mentions: numberValue(row, "post_mentions"),
        quote_mentions: numberValue(row, "quote_mentions"),
        reply_mentions: numberValue(row, "reply_mentions"),
        first_seen: row.first_seen || null,
        last_seen: row.last_seen || null,
      },
      primary_theme: row.primary_theme || "Other / unclassified",
      research_priority: row.research_priority || "low",
      example_url: row.example_url || "",
      serenity_view: prior.serenity_view || "",
      first_principles_notes: prior.first_principles_notes || "",
      buffett: defaultBuffett(prior.buffett),
      open_questions: prior.open_questions || [
        "What evidence proves durable customer demand?",
        "What evidence proves real margin and cash-flow power?",
        "How easy is it for customers to qualify a second source?",
      ],
      recent_events: recentEventsForTicker(events, row.ticker),
      updated_at: new Date().toISOString(),
    };
  });

  return {
    generated_at: new Date().toISOString(),
    source: "follow-aleabito cumulative mention analytics",
    stats: {
      events: events.length,
      tickers: tickers.length,
      earliest_event: events.sort((a, b) => new Date(a.created_at) - new Date(b.created_at))[0]?.created_at || null,
      latest_event: events.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0]?.created_at || null,
    },
    tickers,
  };
}

function buildMarkdown(map) {
  const lines = [
    "# Follow AleaBito Research Map",
    "",
    `Generated: ${map.generated_at}`,
    `Events: ${map.stats.events}`,
    `Tickers: ${map.stats.tickers}`,
    "",
    "| Rank | Ticker | Mentions | Theme | Priority | Last seen | Buffett conclusion |",
    "|---:|---|---:|---|---|---|---|",
  ];
  for (const row of map.tickers.slice(0, 80)) {
    lines.push(
      `| ${row.stats.rank} | ${row.ticker} | ${row.stats.mentioned_posts} | ${row.primary_theme} | ${row.research_priority} | ${(row.stats.last_seen || "").slice(0, 10)} | ${row.buffett.current_conclusion} |`,
    );
  }
  lines.push("");
  lines.push("## Buffett Fields");
  lines.push("");
  lines.push("- moat: strong / medium / weak / unverified");
  lines.push("- profitability: proven / improving / unverified");
  lines.push("- customer_replacement_risk: low / medium / high / unverified");
  lines.push("- buffett_style_business: yes / not yet proven / no");
  lines.push("- current_conclusion: research map / investable conclusion / insufficient evidence");
  lines.push("");
  lines.push("Only promote a ticker from research map to investable conclusion after separate financial, customer, moat, valuation, and margin-of-safety work.");
  return `${lines.join("\n")}\n`;
}

async function main() {
  const eventsPath = argValue("--events");
  const summaryPath = argValue("--summary");
  const outputPath = argValue("--output");
  if (!eventsPath) throw new Error("Missing --events <events-csv>");
  if (!summaryPath) throw new Error("Missing --summary <cumulative-csv>");
  if (!outputPath) throw new Error("Missing --output <research-map-json>");

  const events = await readCsv(eventsPath);
  const summary = await readCsv(summaryPath);
  const previous = await readJSON(outputPath, { tickers: [] });
  const map = buildMap({ events, summary, previous });
  const mdPath = outputPath.replace(/\.json$/i, ".md");

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(map, null, 2)}\n`);
  await writeFile(mdPath, buildMarkdown(map));
  console.log(JSON.stringify({ status: "ok", output: outputPath, markdown: mdPath, tickers: map.tickers.length }, null, 2));
}

main().catch((err) => {
  console.error(JSON.stringify({ status: "error", error: err.message }, null, 2));
  process.exitCode = 1;
});
