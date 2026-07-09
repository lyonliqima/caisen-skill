#!/usr/bin/env node

import { mkdir, readFile, rename, writeFile } from "fs/promises";
import { existsSync } from "fs";
import { dirname, join } from "path";
import { homedir } from "os";

const USER_DIR = join(homedir(), ".follow-aleabito");
const ENV_PATH = join(USER_DIR, ".env");
const CONFIG_PATH = join(USER_DIR, "config.json");
const STATE_PATH = join(USER_DIR, "analytics-state.json");
const DEFAULT_WORKSPACE_REPORTS_DIR = join(
  homedir(),
  "Documents",
  "us stock marketplace",
  "reports",
);
const X_API_BASE = "https://api.x.com/2";

const DEFAULT_CONFIG = {
  handle: "aleabitoreddit",
  displayName: "Serenity",
};

const EVENT_HEADERS = [
  "tweet_id",
  "created_at",
  "kind",
  "text",
  "tickers",
  "source_url",
  "conversation_id",
  "referenced_tweet_id",
];

const SUMMARY_HEADERS = [
  "rank",
  "ticker",
  "mentioned_posts",
  "raw_occurrences",
  "post_mentions",
  "quote_mentions",
  "reply_mentions",
  "first_seen",
  "last_seen",
  "names",
  "primary_theme",
  "research_priority",
  "example_url",
];

const DAILY_HEADERS = [
  "date",
  "ticker",
  "mentioned_posts",
  "raw_occurrences",
  "post_mentions",
  "quote_mentions",
  "reply_mentions",
];

const THEMES = [
  {
    name: "CPO / photonics / optical",
    tickers: ["SIVE", "AAOI", "LITE", "COHR", "POET", "JBL", "AXTI", "SOI", "IQE", "TSEM", "MTSI", "LPK"],
    keywords: ["cpo", "photonics", "photonic", "laser", "optical", "transceiver", "lro", "inp", "silicon photonics", "sip"],
  },
  {
    name: "Power semiconductors / 800VDC",
    tickers: ["XFAB", "NVTS", "POWI", "WOLF", "ON"],
    keywords: ["800vdc", "800 vdc", "sic", "gan", "wide bandgap", "power semi", "power semiconductor"],
  },
  {
    name: "AI compute / memory / hyperscalers",
    tickers: ["NVDA", "AMD", "MU", "MRVL", "AVGO", "INTC", "MSFT", "AMZN", "GOOGL", "NBIS", "META", "IREN"],
    keywords: ["gpu", "hbm", "asic", "hyperscaler", "data center", "datacenter", "neocloud", "inference"],
  },
  {
    name: "Western supply chain / policy funding",
    tickers: ["SIVE", "XFAB", "SOI", "IQE", "GFS", "TSM"],
    keywords: ["chips act", "funding", "western", "supply chain", "sovereignty", "eu", "us gov", "nasdaq", "msci"],
  },
  {
    name: "Valuation / risk / trading behavior",
    tickers: [],
    keywords: ["valuation", "fwd p/e", "p/b", "margin", "revenue", "short", "fud", "atm", "volatility", "selloff", "dilution"],
  },
];

function argValue(name) {
  const idx = process.argv.indexOf(name);
  return idx === -1 ? null : process.argv[idx + 1] || null;
}

function hasFlag(name) {
  return process.argv.includes(name);
}

function numberArg(name, fallback) {
  const value = argValue(name);
  if (value == null) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

async function readJSON(path, fallback) {
  if (!existsSync(path)) return fallback;
  return JSON.parse(await readFile(path, "utf-8"));
}

async function readEnv(path) {
  if (!existsSync(path)) return {};
  const env = {};
  const text = await readFile(path, "utf-8");
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    env[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
  }
  return env;
}

function defaultOutputDir() {
  return process.env.FOLLOW_ALEABITO_REPORTS_DIR || DEFAULT_WORKSPACE_REPORTS_DIR;
}

function normalizeText(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (/[",\r\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function csvLine(headers, row) {
  return headers.map((header) => csvEscape(row[header])).join(",");
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
  if (!existsSync(path)) return [];
  const text = await readFile(path, "utf-8");
  const lines = text.split(/\r?\n/).filter((line) => line.length > 0);
  if (lines.length === 0) return [];
  const headers = parseCsvLine(lines[0]);
  return lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    return Object.fromEntries(headers.map((header, idx) => [header, cells[idx] ?? ""]));
  });
}

async function atomicWrite(path, text) {
  await mkdir(dirname(path), { recursive: true });
  const tmp = `${path}.${process.pid}.${Date.now()}.tmp`;
  await writeFile(tmp, text);
  await rename(tmp, path);
}

function writeCsvRows(headers, rows) {
  return `${headers.join(",")}\n${rows.map((row) => csvLine(headers, row)).join("\n")}\n`;
}

function toIso(date) {
  return new Date(date).toISOString();
}

function addHours(iso, hours) {
  return toIso(new Date(iso).getTime() + hours * 60 * 60 * 1000);
}

function addDays(date, days) {
  return new Date(date.getTime() + days * 24 * 60 * 60 * 1000);
}

function localDateKey(iso, timeZone) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(iso));
  const get = (type) => parts.find((part) => part.type === type)?.value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function isValidTicker(ticker) {
  return /^[A-Z][A-Z0-9.\-]{0,11}$/.test(ticker) || /^\d{4,5}$/.test(ticker);
}

function extractTickers(text, entities = {}) {
  const tickers = new Set();
  for (const cashtag of entities.cashtags || []) {
    const ticker = String(cashtag.tag || cashtag.text || "")
      .replace(/^\$/, "")
      .replace(/[.,;:!?]+$/g, "")
      .toUpperCase();
    if (isValidTicker(ticker)) tickers.add(ticker);
  }

  const cashtagRegex = /(^|[^A-Za-z0-9_])\$([A-Za-z0-9][A-Za-z0-9.\-]{0,11})(?![A-Za-z0-9_])/g;
  for (const match of String(text || "").matchAll(cashtagRegex)) {
    const ticker = match[2].replace(/[.,;:!?]+$/g, "").toUpperCase();
    if (isValidTicker(ticker)) tickers.add(ticker);
  }
  return [...tickers].sort();
}

function countRawOccurrences(text, ticker) {
  const escaped = ticker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(`(^|[^A-Za-z0-9_])\\$${escaped}(?![A-Za-z0-9_])`, "gi");
  return [...String(text || "").matchAll(re)].length;
}

function kindFromReferences(references = []) {
  if (references.some((ref) => ref.type === "replied_to")) return "reply";
  if (references.some((ref) => ref.type === "quoted")) return "quote";
  return "post";
}

function referencedTweetId(references = []) {
  return references.find((ref) => ref.type === "replied_to")?.id || references.find((ref) => ref.type === "quoted")?.id || "";
}

function normalizeTweet(tweet, handle) {
  const references = tweet.referenced_tweets || tweet.referencedTweets || [];
  const text = normalizeText(tweet.note_tweet?.text || tweet.text || "");
  const tickers = extractTickers(text, tweet.entities || {});
  return {
    tweet_id: tweet.id,
    created_at: tweet.created_at || tweet.createdAt,
    kind: kindFromReferences(references),
    text,
    tickers: tickers.join("|"),
    source_url: `https://x.com/${handle}/status/${tweet.id}`,
    conversation_id: tweet.conversation_id || "",
    referenced_tweet_id: referencedTweetId(references),
  };
}

function parseTickers(value) {
  return String(value || "")
    .split("|")
    .map((ticker) => ticker.trim().toUpperCase())
    .filter((ticker) => ticker && isValidTicker(ticker));
}

function chooseEvent(existing, incoming) {
  if (!existing) return incoming;
  if ((incoming.text || "").length > (existing.text || "").length) return { ...existing, ...incoming };
  return existing;
}

function summarizeEvents(events, timeZone) {
  const byTicker = new Map();
  const byDailyTicker = new Map();

  for (const event of events) {
    const kind = event.kind || "post";
    const text = event.text || "";
    const tickers = [...new Set(parseTickers(event.tickers))];
    for (const ticker of tickers) {
      if (!byTicker.has(ticker)) {
        byTicker.set(ticker, {
          ticker,
          mentioned_posts: 0,
          raw_occurrences: 0,
          post_mentions: 0,
          quote_mentions: 0,
          reply_mentions: 0,
          first_seen: event.created_at,
          last_seen: event.created_at,
          names: "",
          example_url: event.source_url,
          sample_texts: [],
        });
      }
      const row = byTicker.get(ticker);
      row.mentioned_posts += 1;
      row.raw_occurrences += Math.max(1, countRawOccurrences(text, ticker));
      if (kind === "reply") row.reply_mentions += 1;
      else if (kind === "quote") row.quote_mentions += 1;
      else row.post_mentions += 1;
      if (new Date(event.created_at) < new Date(row.first_seen)) row.first_seen = event.created_at;
      if (new Date(event.created_at) > new Date(row.last_seen)) {
        row.last_seen = event.created_at;
        row.example_url = event.source_url;
      }
      if (row.sample_texts.length < 8) row.sample_texts.push(text);

      const date = localDateKey(event.created_at, timeZone);
      const key = `${date}|${ticker}`;
      if (!byDailyTicker.has(key)) {
        byDailyTicker.set(key, {
          date,
          ticker,
          mentioned_posts: 0,
          raw_occurrences: 0,
          post_mentions: 0,
          quote_mentions: 0,
          reply_mentions: 0,
        });
      }
      const daily = byDailyTicker.get(key);
      daily.mentioned_posts += 1;
      daily.raw_occurrences += Math.max(1, countRawOccurrences(text, ticker));
      if (kind === "reply") daily.reply_mentions += 1;
      else if (kind === "quote") daily.quote_mentions += 1;
      else daily.post_mentions += 1;
    }
  }

  const summary = [...byTicker.values()]
    .sort((a, b) => b.mentioned_posts - a.mentioned_posts || b.raw_occurrences - a.raw_occurrences || a.ticker.localeCompare(b.ticker))
    .map((row, idx) => ({
      rank: idx + 1,
      ticker: row.ticker,
      mentioned_posts: row.mentioned_posts,
      raw_occurrences: row.raw_occurrences,
      post_mentions: row.post_mentions,
      quote_mentions: row.quote_mentions,
      reply_mentions: row.reply_mentions,
      first_seen: row.first_seen,
      last_seen: row.last_seen,
      names: row.names,
      primary_theme: inferTheme(row.ticker, row.sample_texts),
      research_priority: inferResearchPriority(row),
      example_url: row.example_url,
    }));

  const daily = [...byDailyTicker.values()].sort(
    (a, b) => a.date.localeCompare(b.date) || a.ticker.localeCompare(b.ticker),
  );

  return { summary, daily };
}

function inferTheme(ticker, sampleTexts = []) {
  const lowerText = sampleTexts.join(" ").toLowerCase();
  for (const theme of THEMES) {
    if (theme.tickers.includes(ticker)) return theme.name;
  }
  for (const theme of THEMES) {
    if (theme.keywords.some((keyword) => lowerText.includes(keyword))) return theme.name;
  }
  return "Other / unclassified";
}

function inferResearchPriority(row) {
  if (row.mentioned_posts >= 50) return "high";
  if (row.mentioned_posts >= 15) return "medium";
  if (row.mentioned_posts >= 5) return "watchlist";
  return "low";
}

async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 30000);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function getUserId(handle, bearerToken, state) {
  if (state.handle === handle && state.user_id) return { id: state.user_id, cached: true };
  const res = await fetchWithTimeout(
    `${X_API_BASE}/users/by/username/${encodeURIComponent(handle)}?user.fields=description,public_metrics`,
    { headers: { Authorization: `Bearer ${bearerToken}` } },
  );
  if (!res.ok) throw new Error(`X user lookup failed: HTTP ${res.status}`);
  const payload = await res.json();
  if (!payload.data?.id) throw new Error(`X user lookup returned no user for @${handle}`);
  return { id: payload.data.id, cached: false, profile: payload.data };
}

async function fetchTimelineRange({ userId, handle, bearerToken, startTime, endTime, includeReplies, maxPages }) {
  let pages = 0;
  let cursor = null;
  let currentEndTime = endTime;
  let oldestSeen = null;
  let exhausted = false;
  const events = [];
  const pageDetails = [];
  let rateLimit = {};

  while (pages < maxPages && !exhausted) {
    const params = new URLSearchParams({
      max_results: "100",
      "tweet.fields": "created_at,public_metrics,referenced_tweets,note_tweet,entities,conversation_id",
      exclude: includeReplies ? "retweets" : "retweets,replies",
      start_time: startTime,
      end_time: currentEndTime,
    });
    if (cursor) params.set("pagination_token", cursor);

    const res = await fetchWithTimeout(`${X_API_BASE}/users/${userId}/tweets?${params}`, {
      headers: { Authorization: `Bearer ${bearerToken}` },
    });
    rateLimit = {
      limit: res.headers.get("x-rate-limit-limit") || "",
      remaining: res.headers.get("x-rate-limit-remaining") || "",
      reset: res.headers.get("x-rate-limit-reset") || "",
    };
    if (!res.ok) throw new Error(`X tweets lookup failed: HTTP ${res.status}`);

    const payload = await res.json();
    const rows = payload.data || [];
    pages += 1;

    for (const tweet of rows) {
      const event = normalizeTweet(tweet, handle);
      if (!event.tweet_id || !event.created_at || !event.text) continue;
      events.push(event);
      if (!oldestSeen || new Date(event.created_at) < new Date(oldestSeen)) oldestSeen = event.created_at;
    }

    pageDetails.push({
      page: pages,
      result_count: payload.meta?.result_count ?? rows.length,
      data_count: rows.length,
      next_token: Boolean(payload.meta?.next_token),
      end_time: currentEndTime,
      oldest_seen: oldestSeen,
    });

    if (payload.meta?.next_token) {
      cursor = payload.meta.next_token;
      continue;
    }

    if (rows.length === 0) {
      if (cursor && oldestSeen && new Date(oldestSeen) > new Date(startTime)) {
        currentEndTime = addHours(oldestSeen, -1 / 3600);
        cursor = null;
        continue;
      }
      exhausted = true;
      break;
    }

    if (oldestSeen && new Date(oldestSeen) > new Date(startTime)) {
      currentEndTime = addHours(oldestSeen, -1 / 3600);
      cursor = null;
      continue;
    }

    exhausted = true;
  }

  return {
    events,
    pages,
    pageDetails,
    rateLimit,
    complete: exhausted,
  };
}

// Full-archive backfill via /2/tweets/search/all (no ~3200-tweet timeline cap).
// Requires an X API project entitled to full-archive search (Pro/Enterprise).
async function fetchArchiveRange({ handle, bearerToken, startTime, endTime, includeReplies, maxPages }) {
  let pages = 0;
  let cursor = null;
  let exhausted = false;
  let oldestSeen = null;
  const events = [];
  const pageDetails = [];
  let rateLimit = {};
  const query = includeReplies
    ? `from:${handle} -is:retweet`
    : `from:${handle} -is:retweet -is:reply`;

  while (pages < maxPages && !exhausted) {
    const params = new URLSearchParams({
      query,
      max_results: "100",
      "tweet.fields": "created_at,public_metrics,referenced_tweets,note_tweet,entities,conversation_id",
      start_time: startTime,
      end_time: endTime,
    });
    if (cursor) params.set("next_token", cursor);

    const res = await fetchWithTimeout(`${X_API_BASE}/tweets/search/all?${params}`, {
      headers: { Authorization: `Bearer ${bearerToken}` },
    });
    rateLimit = {
      limit: res.headers.get("x-rate-limit-limit") || "",
      remaining: res.headers.get("x-rate-limit-remaining") || "",
      reset: res.headers.get("x-rate-limit-reset") || "",
    };
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`X search/all failed: HTTP ${res.status} ${detail.slice(0, 200)}`);
    }

    const payload = await res.json();
    const rows = payload.data || [];
    pages += 1;

    for (const tweet of rows) {
      const event = normalizeTweet(tweet, handle);
      if (!event.tweet_id || !event.created_at || !event.text) continue;
      events.push(event);
      if (!oldestSeen || new Date(event.created_at) < new Date(oldestSeen)) oldestSeen = event.created_at;
    }

    pageDetails.push({
      page: pages,
      result_count: payload.meta?.result_count ?? rows.length,
      data_count: rows.length,
      next_token: Boolean(payload.meta?.next_token),
      oldest_seen: oldestSeen,
      reason: "archive",
    });

    if (payload.meta?.next_token) {
      cursor = payload.meta.next_token;
      await new Promise((resolve) => setTimeout(resolve, 1100)); // search/all ~1 req/sec
      continue;
    }
    exhausted = true;
  }

  return { events, pages, pageDetails, rateLimit, complete: exhausted };
}

function planFetchRanges({ mode, backfillDays, overlapHours, existingEvents, nowIso, resume }) {
  if (!resume || existingEvents.length === 0) {
    const days = mode === "incremental" ? backfillDays : backfillDays;
    return [{ startTime: toIso(addDays(new Date(nowIso), -days)), endTime: nowIso, reason: "initial-backfill" }];
  }

  const sorted = [...existingEvents].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  const earliest = sorted[0]?.created_at;
  const latest = sorted.at(-1)?.created_at;
  if (mode === "incremental") {
    return [{ startTime: addHours(latest, -overlapHours), endTime: nowIso, reason: "incremental-overlap" }];
  }

  const targetStart = toIso(addDays(new Date(nowIso), -backfillDays));
  const ranges = [];
  if (new Date(earliest) > new Date(targetStart)) {
    ranges.push({
      startTime: targetStart,
      endTime: addHours(earliest, -1 / 3600),
      reason: "older-gap",
    });
  }
  const latestWithOverlap = addHours(latest, -overlapHours);
  if (new Date(latest) < new Date(addHours(nowIso, -overlapHours))) {
    ranges.push({ startTime: latestWithOverlap, endTime: nowIso, reason: "newer-gap" });
  }
  return ranges;
}

async function main() {
  await mkdir(USER_DIR, { recursive: true });
  const config = { ...DEFAULT_CONFIG, ...(await readJSON(CONFIG_PATH, {})) };
  const env = { ...process.env, ...(await readEnv(ENV_PATH)) };

  const outputDir = argValue("--output-dir") || defaultOutputDir();
  const statePath = argValue("--state") || STATE_PATH;
  const handle = argValue("--handle") || config.handle || DEFAULT_CONFIG.handle;
  const includeReplies = hasFlag("--include-replies");
  const incremental = hasFlag("--incremental");
  const rebuildOnly = hasFlag("--rebuild-only");
  const useArchive = hasFlag("--archive");
  const resume = hasFlag("--resume") || incremental;
  const backfillDays = numberArg("--backfill-days", 60);
  const maxPages = numberArg("--max-pages", Number.POSITIVE_INFINITY);
  const overlapHours = numberArg("--overlap-hours", 48);
  const timeZone = argValue("--timezone") || process.env.TZ || "America/Los_Angeles";

  const eventsPath = argValue("--events") || join(outputDir, "aleabito-mentions-events.csv");
  const summaryPath = argValue("--summary") || join(outputDir, "aleabito-stock-mentions-cumulative.csv");
  const dailyPath = argValue("--daily") || join(outputDir, "aleabito-stock-mentions-daily.csv");
  const metaPath = argValue("--meta") || join(outputDir, "aleabito-mentions.meta.json");
  const nowIso = new Date().toISOString();

  const state = await readJSON(statePath, {});
  const existingEvents = await readCsv(eventsPath);
  let fetchedEvents = [];
  let pagesUsed = 0;
  let complete = true;
  let pageDetails = [];
  let rateLimit = {};
  const mode = rebuildOnly ? "rebuild" : incremental ? "incremental" : "backfill";
  const fetchRanges = rebuildOnly
    ? []
    : planFetchRanges({
        mode,
        backfillDays,
        overlapHours,
        existingEvents,
        nowIso,
        resume,
      });

  if (fetchRanges.length > 0 && !env.X_BEARER_TOKEN) {
    const meta = {
      status: "degraded",
      generated_at: nowIso,
      handle,
      error: "X_BEARER_TOKEN is missing in ~/.follow-aleabito/.env",
      files: { events: eventsPath, summary: summaryPath, daily: dailyPath, meta: metaPath },
      stats: { existing_events: existingEvents.length, added_events: 0 },
    };
    await atomicWrite(metaPath, `${JSON.stringify(meta, null, 2)}\n`);
    console.log(JSON.stringify(meta, null, 2));
    process.exitCode = 1;
    return;
  }

  try {
    const user = fetchRanges.length > 0 ? await getUserId(handle, env.X_BEARER_TOKEN, state) : null;
    let remainingPages = maxPages;
    for (const range of fetchRanges) {
      if (remainingPages <= 0) {
        complete = false;
        break;
      }
      if (new Date(range.startTime) >= new Date(range.endTime)) continue;
      const result = useArchive
        ? await fetchArchiveRange({
            handle,
            bearerToken: env.X_BEARER_TOKEN,
            startTime: range.startTime,
            endTime: range.endTime,
            includeReplies,
            maxPages: remainingPages,
          })
        : await fetchTimelineRange({
            userId: user.id,
            handle,
            bearerToken: env.X_BEARER_TOKEN,
            startTime: range.startTime,
            endTime: range.endTime,
            includeReplies,
            maxPages: remainingPages,
          });
      fetchedEvents = fetchedEvents.concat(result.events);
      pagesUsed += result.pages;
      remainingPages -= result.pages;
      complete = complete && result.complete;
      pageDetails = pageDetails.concat(result.pageDetails.map((page) => ({ ...page, reason: range.reason })));
      rateLimit = result.rateLimit;
    }

    const eventMap = new Map();
    for (const event of existingEvents) eventMap.set(event.tweet_id, event);
    for (const event of fetchedEvents) eventMap.set(event.tweet_id, chooseEvent(eventMap.get(event.tweet_id), event));
    const events = [...eventMap.values()]
      .filter((event) => event.tweet_id && event.created_at && event.text)
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at) || String(a.tweet_id).localeCompare(String(b.tweet_id)));
    const addedEvents = events.filter((event) => !existingEvents.some((existing) => existing.tweet_id === event.tweet_id)).length;
    const { summary, daily } = summarizeEvents(events, timeZone);
    const generatedAt = new Date().toISOString();
    const datedSnapshot = join(outputDir, `aleabito-stock-mentions-${generatedAt.slice(0, 10)}.csv`);
    const meta = {
      status: complete ? "ok" : "partial",
      generated_at: generatedAt,
      handle,
      mode,
      include_replies: includeReplies,
      resume,
      backfill_days: backfillDays,
      overlap_hours: overlapHours,
      timezone: timeZone,
      fetch_ranges: fetchRanges,
      files: {
        events: eventsPath,
        summary: summaryPath,
        daily: dailyPath,
        dated_summary_snapshot: datedSnapshot,
        meta: metaPath,
        state: statePath,
      },
      stats: {
        existing_events: existingEvents.length,
        fetched_events: fetchedEvents.length,
        added_events: addedEvents,
        total_events: events.length,
        tickers: summary.length,
        pages_used: pagesUsed,
        earliest_event: events[0]?.created_at || null,
        latest_event: events.at(-1)?.created_at || null,
      },
      rate_limit: rateLimit,
      page_details: pageDetails,
    };

    await atomicWrite(eventsPath, writeCsvRows(EVENT_HEADERS, events));
    await atomicWrite(summaryPath, writeCsvRows(SUMMARY_HEADERS, summary));
    await atomicWrite(dailyPath, writeCsvRows(DAILY_HEADERS, daily));
    await atomicWrite(datedSnapshot, writeCsvRows(SUMMARY_HEADERS, summary));
    await atomicWrite(metaPath, `${JSON.stringify(meta, null, 2)}\n`);
    await atomicWrite(
      statePath,
      `${JSON.stringify(
        {
          ...state,
          handle,
          user_id: user?.id || state.user_id,
          last_run_at: generatedAt,
          last_status: meta.status,
          latest_event_at: meta.stats.latest_event,
          earliest_event_at: meta.stats.earliest_event,
          files: meta.files,
        },
        null,
        2,
      )}\n`,
    );

    console.log(JSON.stringify(meta, null, 2));
  } catch (err) {
    const meta = {
      status: "degraded",
      generated_at: new Date().toISOString(),
      handle,
      mode,
      include_replies: includeReplies,
      error: err.message,
      files: { events: eventsPath, summary: summaryPath, daily: dailyPath, meta: metaPath },
      stats: {
        existing_events: existingEvents.length,
        fetched_events: fetchedEvents.length,
        added_events: 0,
        pages_used: pagesUsed,
      },
      rate_limit: rateLimit,
      page_details: pageDetails,
    };
    await atomicWrite(metaPath, `${JSON.stringify(meta, null, 2)}\n`);
    console.log(JSON.stringify(meta, null, 2));
    process.exitCode = 1;
  }
}

main();
