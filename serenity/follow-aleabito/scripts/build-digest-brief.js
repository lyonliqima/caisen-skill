#!/usr/bin/env node

import { readFile, writeFile } from "fs/promises";

const DEFAULT_INPUT = "/tmp/follow-aleabito-updates.json";
const DEFAULT_OUTPUT = "/tmp/follow-aleabito-brief.md";

const HIGH_SIGNAL_KEYWORDS = [
  "cpo",
  "photonics",
  "photonic",
  "laser",
  "optical",
  "transceiver",
  "lro",
  "chips act",
  "chips",
  "800 vdc",
  "800vdc",
  "power semi",
  "sic",
  "wide bandgap",
  "revenue",
  "margin",
  "gross margin",
  "customer",
  "supplier",
  "capacity",
  "valuation",
  "tam",
  "m&a",
  "volume ramp",
  "mass production",
  "asp",
  "design out",
  "short",
  "funding",
  "supply chain",
  "inflow",
  "nasdaq",
  "msci",
  "blackrock",
  "vanguard",
];

const THEMES = [
  {
    name: "CPO / 光通信 / 激光器",
    tickers: ["SIVE", "AAOI", "LITE", "COHR", "POET", "JBL", "AXTI", "SOI", "IQE", "TSEM", "MTSI"],
    keywords: ["cpo", "photonics", "photonic", "laser", "optical", "transceiver", "lro", "inp", "silicon photonics", "sip"],
  },
  {
    name: "功率半导体 / 800VDC / 电源效率",
    tickers: ["XFAB", "NVTS", "POWI", "WOLF"],
    keywords: ["power semi", "800 vdc", "800vdc", "sic", "wide bandgap", "power semis", "power semiconductor"],
  },
  {
    name: "AI 算力 / 内存 / 大厂需求",
    tickers: ["NVDA", "AMD", "MU", "MRVL", "AVGO", "INTC", "MSFT", "AMZN", "GOOGL", "NBIS"],
    keywords: ["ai", "gpu", "memory", "hbm", "asic", "hyperscaler", "data center", "datacenter"],
  },
  {
    name: "政府补贴 / 西方供应链 / 资金流入",
    tickers: ["SIVE", "XFAB", "SOI", "IQE"],
    keywords: ["chips act", "government", "funding", "western", "supply chain", "sovereignty", "eu", "us gov", "nasdaq", "msci", "blackrock", "vanguard"],
  },
  {
    name: "风险 / 估值 / 交易行为",
    tickers: [],
    keywords: ["valuation", "fwd p/e", "p/b", "margin", "revenue", "short", "fud", "scam", "asp", "design out", "atm", "volatility", "selloff"],
  },
];

function argValue(name) {
  const idx = process.argv.indexOf(name);
  return idx === -1 ? null : process.argv[idx + 1] || null;
}

function compact(text, limit = 700) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  return value.length > limit ? `${value.slice(0, limit - 1)}...` : value;
}

function tickerList(tweet) {
  return Array.isArray(tweet.tickers) ? tweet.tickers : [];
}

function scoreTweet(tweet) {
  const text = String(tweet.text || "").toLowerCase();
  let score = 0;
  if (tweet.kind !== "reply") score += 3;
  score += Math.min(tickerList(tweet).length, 5);
  for (const keyword of HIGH_SIGNAL_KEYWORDS) {
    if (text.includes(keyword)) score += 1;
  }
  if ((tweet.text || "").length > 240) score += 1;
  return score;
}

function themeScore(tweet, theme) {
  const text = String(tweet.text || "").toLowerCase();
  let score = 0;
  for (const ticker of tickerList(tweet)) {
    if (theme.tickers.includes(ticker)) score += 2;
  }
  for (const keyword of theme.keywords) {
    if (text.includes(keyword)) score += 1;
  }
  return score;
}

function countKinds(tweets) {
  return tweets.reduce(
    (counts, tweet) => {
      const kind = tweet.kind || "post";
      counts[kind] = (counts[kind] || 0) + 1;
      return counts;
    },
    { post: 0, quote: 0, reply: 0 },
  );
}

function countTickers(tweets) {
  const counts = new Map();
  for (const tweet of tweets) {
    for (const ticker of new Set(tickerList(tweet))) {
      counts.set(ticker, (counts.get(ticker) || 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([ticker, count]) => ({ ticker, count }))
    .sort((a, b) => b.count - a.count || a.ticker.localeCompare(b.ticker));
}

function formatTweet(tweet) {
  const kindLabel = tweet.kind || "post";
  const tickers = tickerList(tweet).join(", ") || "-";
  return [
    `- ${tweet.createdAt || tweet.created_at || ""} | ${kindLabel} | ${tickers}`,
    `  ${tweet.sourceUrl || tweet.url || ""}`,
    `  ${compact(tweet.text)}`,
  ].join("\n");
}

function buildThemeSections(tweets) {
  return THEMES.map((theme) => {
    const items = tweets
      .map((tweet) => ({ tweet, score: themeScore(tweet, theme) + scoreTweet(tweet) * 0.1 }))
      .filter((item) => item.score >= 1)
      .sort((a, b) => b.score - a.score || new Date(b.tweet.createdAt) - new Date(a.tweet.createdAt))
      .slice(0, 8)
      .map((item) => item.tweet);
    return { theme: theme.name, items };
  }).filter((section) => section.items.length > 0);
}

async function main() {
  const inputPath = argValue("--input") || DEFAULT_INPUT;
  const outputPath = argValue("--output") || DEFAULT_OUTPUT;
  const payload = JSON.parse(await readFile(inputPath, "utf-8"));
  const tweets = (payload.tweets || []).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  const kindCounts = countKinds(tweets);
  const tickerCounts = countTickers(tweets);
  const highSignalReplies = tweets
    .filter((tweet) => tweet.kind === "reply")
    .map((tweet) => ({ tweet, score: scoreTweet(tweet) }))
    .filter((item) => item.score >= 3)
    .sort((a, b) => b.score - a.score || new Date(b.tweet.createdAt) - new Date(a.tweet.createdAt))
    .slice(0, 12)
    .map((item) => item.tweet);
  const themeSections = buildThemeSections(tweets);

  const lines = [
    `# Follow AleaBito Digest Brief`,
    "",
    `Generated: ${new Date().toISOString()}`,
    `Source: ${payload.source || "unknown"}`,
    `Window: ${payload.stats?.lookbackHours ?? "unknown"} hours`,
    `Fetched tweets: ${payload.stats?.fetchedTweets ?? tweets.length}`,
    `Returned tweets: ${tweets.length}`,
    `Kinds: ${kindCounts.post} posts, ${kindCounts.quote} quotes, ${kindCounts.reply} replies`,
    "",
    "## Codex Digest Instructions",
    "",
    "- Write in Chinese for a beginner investor.",
    "- Use plain language before technical terms; explain CPO, photonics, 800VDC, P/B, TAM, ASP when they appear.",
    "- For each major theme, use: 她的观点 -> 小白解释 -> 第一性原理 -> Buffett 直接判断.",
    "- Buffett 直接判断 must answer, not merely ask: moat strength, current profitability evidence, customer replacement risk, whether it is a Buffett-style business today, and whether it is only a research lead.",
    "- Do not make buy/sell recommendations. End with: 仅作信息跟踪，不构成投资建议。",
    "",
    "## Ticker Counts",
    "",
    tickerCounts.length
      ? "| Ticker | Mentioned posts |\n|---|---:|\n" +
        tickerCounts.slice(0, 25).map((row) => `| ${row.ticker} | ${row.count} |`).join("\n")
      : "No tickers found.",
    "",
    "## Theme Groups",
    "",
  ];

  for (const section of themeSections) {
    lines.push(`### ${section.theme}`, "");
    for (const tweet of section.items) lines.push(formatTweet(tweet), "");
  }

  lines.push("## High-Signal Replies", "");
  if (highSignalReplies.length === 0) {
    lines.push("No high-signal replies selected.", "");
  } else {
    for (const tweet of highSignalReplies) lines.push(formatTweet(tweet), "");
  }

  lines.push("## All Returned Items", "");
  for (const tweet of tweets.slice(0, 50)) lines.push(formatTweet(tweet), "");

  if (payload.warnings?.length) {
    lines.push("## Source Warnings", "");
    for (const warning of payload.warnings) lines.push(`- ${warning}`);
    lines.push("");
  }
  if (payload.errors?.length) {
    lines.push("## Source Errors", "");
    for (const error of payload.errors) lines.push(`- ${error}`);
    lines.push("");
  }

  await writeFile(outputPath, lines.join("\n"));
  console.log(
    JSON.stringify(
      {
        status: "ok",
        input: inputPath,
        output: outputPath,
        tweets: tweets.length,
        kinds: kindCounts,
        tickers: tickerCounts.length,
        highSignalReplies: highSignalReplies.length,
        themes: themeSections.length,
      },
      null,
      2,
    ),
  );
}

main().catch((err) => {
  console.error(JSON.stringify({ status: "error", message: err.message }, null, 2));
  process.exit(1);
});
