#!/usr/bin/env node

import { mkdir, readFile, writeFile } from "fs/promises";
import { existsSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { spawn } from "child_process";

const USER_DIR = join(homedir(), ".follow-aleabito");
const CACHE_DIR = join(USER_DIR, "cache");
const CONFIG_PATH = join(USER_DIR, "config.json");
const STATE_PATH = join(USER_DIR, "state.json");
const ENV_PATH = join(USER_DIR, ".env");
const CACHE_PATH = join(CACHE_DIR, "latest-fetch.json");
const X_API_BASE = "https://api.x.com/2";
const DEFAULT_CONFIG = {
  handle: "aleabitoreddit",
  displayName: "Serenity",
  language: "zh",
  lookbackHours: 24,
  maxTweets: 5,
  dedupe: true,
  chromeFallback: true,
  notifyWhenEmpty: true,
  delivery: { method: "imessage", recipient: "" },
};

const TWEET_RESULT_FEATURES = [
  "creator_subscriptions_tweet_preview_api_enabled",
  "premium_content_api_read_enabled",
  "communities_web_enable_tweet_community_results_fetch",
  "c9s_tweet_anatomy_moderator_badge_enabled",
  "responsive_web_grok_analyze_button_fetch_trends_enabled",
  "responsive_web_grok_analyze_post_followups_enabled",
  "rweb_cashtags_composer_attachment_enabled",
  "responsive_web_jetfuel_frame",
  "responsive_web_grok_share_attachment_enabled",
  "responsive_web_grok_annotations_enabled",
  "articles_preview_enabled",
  "responsive_web_edit_tweet_api_enabled",
  "rweb_conversational_replies_downvote_enabled",
  "graphql_is_translatable_rweb_tweet_is_translatable_enabled",
  "view_counts_everywhere_api_enabled",
  "longform_notetweets_consumption_enabled",
  "responsive_web_twitter_article_tweet_consumption_enabled",
  "content_disclosure_indicator_enabled",
  "content_disclosure_ai_generated_indicator_enabled",
  "responsive_web_grok_show_grok_translated_post",
  "responsive_web_grok_analysis_button_from_backend",
  "post_ctas_fetch_enabled",
  "rweb_cashtags_enabled",
  "freedom_of_speech_not_reach_fetch_enabled",
  "standardized_nudges_misinfo",
  "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled",
  "longform_notetweets_rich_text_read_enabled",
  "longform_notetweets_inline_media_enabled",
  "profile_label_improvements_pcf_label_in_post_enabled",
  "responsive_web_profile_redirect_enabled",
  "rweb_tipjar_consumption_enabled",
  "verified_phone_label_enabled",
  "responsive_web_grok_image_annotation_enabled",
  "responsive_web_grok_imagine_annotation_enabled",
  "responsive_web_grok_community_note_auto_translation_is_enabled",
  "responsive_web_graphql_skip_user_profile_image_extensions_enabled",
  "responsive_web_graphql_timeline_navigation_enabled",
];

const TWEET_RESULT_FIELD_TOGGLES = {
  withArticleRichContentState: true,
  withArticlePlainText: true,
  withArticleSummaryText: true,
  withArticleVoiceOver: true,
  withGrokAnalyze: true,
  withDisallowedReplyControls: true,
};

function argValue(name) {
  const idx = process.argv.indexOf(name);
  return idx === -1 ? null : process.argv[idx + 1] || null;
}

function hasFlag(name) {
  return process.argv.includes(name);
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

function decodeEntities(text) {
  return String(text || "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function extractTickers(text, entities = {}) {
  const tickers = new Set();
  for (const cashtag of entities.cashtags || []) {
    const ticker = String(cashtag.tag || cashtag.text || "")
      .replace(/^\$/, "")
      .replace(/[.,;:!?]+$/g, "")
      .toUpperCase();
    if (/^[A-Z][A-Z0-9.\-]{0,11}$/.test(ticker)) tickers.add(ticker);
  }

  const cashtagRegex = /(^|[^A-Za-z0-9_])\$([A-Za-z][A-Za-z0-9.\-]{0,11})(?![A-Za-z0-9_])/g;
  for (const match of String(text || "").matchAll(cashtagRegex)) {
    const ticker = match[2].replace(/[.,;:!?]+$/g, "").toUpperCase();
    if (/^[A-Z][A-Z0-9.\-]{0,11}$/.test(ticker)) tickers.add(ticker);
  }

  return [...tickers].sort();
}

function kindFromReferences(references = []) {
  if (references.some((ref) => ref.type === "replied_to")) return "reply";
  if (references.some((ref) => ref.type === "quoted")) return "quote";
  return "post";
}

function normalizeTweet(tweet) {
  const text = decodeEntities(tweet.text || "");
  const referencedTweets = tweet.referencedTweets || [];
  const kind = tweet.kind || kindFromReferences(referencedTweets);
  return {
    id: tweet.id,
    text,
    createdAt: tweet.createdAt,
    url: tweet.url,
    sourceUrl: tweet.sourceUrl || tweet.url,
    kind,
    tickers: tweet.tickers || extractTickers(text, tweet.entities),
    likes: tweet.likes ?? 0,
    retweets: tweet.retweets ?? 0,
    replies: tweet.replies ?? 0,
    isQuote: Boolean(tweet.isQuote) || kind === "quote",
    quotedTweetId: tweet.quotedTweetId ?? null,
    replyToTweetId: tweet.replyToTweetId ?? null,
    referencedTweets,
  };
}

async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 20000);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function runAppleScript(script, args = []) {
  return new Promise((resolve, reject) => {
    const child = spawn("osascript", ["-e", script, ...args], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("close", (code) => {
      if (code === 0) resolve(stdout.trim());
      else reject(new Error(stderr.trim() || `osascript exited with code ${code}`));
    });
  });
}

function relativeTimeToDate(raw) {
  const value = String(raw || "").trim();
  const match = value.match(/^(\d+)([mhd])$/i);
  if (!match) return null;

  const amount = Number(match[1]);
  const unit = match[2].toLowerCase();
  const ms =
    unit === "m"
      ? amount * 60 * 1000
      : unit === "h"
        ? amount * 60 * 60 * 1000
        : amount * 24 * 60 * 60 * 1000;
  return new Date(Date.now() - ms).toISOString();
}

function extractChromeTweet(article, handle) {
  const text = article.text || "";
  if (!text || text.startsWith("Pinned")) return null;

  const statusUrl = (article.links || []).find((link) =>
    new RegExp(`https://(?:x|twitter)\\.com/${handle}/status/\\d+`).test(link),
  );
  const id = statusUrl?.match(/\/status\/(\d+)/)?.[1];
  if (!id || !statusUrl) return null;

  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const timeIndex = lines.findIndex((line) => /^(\d+)([mhd])$/i.test(line));
  if (timeIndex === -1) return null;

  const createdAt = relativeTimeToDate(lines[timeIndex]);
  if (!createdAt) return null;

  let bodyLines = lines.slice(timeIndex + 1);
  const quoteIndex = bodyLines.findIndex((line) => line === "Quote");
  if (quoteIndex !== -1) bodyLines = bodyLines.slice(0, quoteIndex);
  bodyLines = bodyLines.filter(
    (line) => !["Show more", "Show less", "Subscribed", "Subscribers"].includes(line),
  );
  while (bodyLines.length > 0 && /^[\d,.]+[KMB]?$/i.test(bodyLines.at(-1))) {
    bodyLines.pop();
  }

  return normalizeTweet({
    id,
    text: bodyLines.join("\n"),
    createdAt,
    url: `https://x.com/${handle}/status/${id}`,
    kind: text.includes("\nQuote\n") ? "quote" : "post",
    likes: 0,
    retweets: 0,
    replies: 0,
    isQuote: text.includes("\nQuote\n"),
    quotedTweetId: null,
  });
}

async function readChromeTimeline(config) {
  const js =
    "JSON.stringify(Array.from(document.querySelectorAll('article')).slice(0,20).map((a,i)=>({i,text:a.innerText,links:Array.from(a.querySelectorAll('a[href]')).map(x=>x.href)})))";
  const expandJs = `
(() => {
  const isShowMore = (el) => (el.innerText || el.textContent || "").trim() === "Show more";
  const candidates = Array.from(document.querySelectorAll('button, [role="button"], span'))
    .filter(isShowMore);
  let clicked = 0;
  for (const el of candidates) {
    const target = el.closest('button, [role="button"], a') || el;
    target.click();
    clicked += 1;
  }
  return String(clicked);
})()
`;
  const script = `
on run argv
  set handleName to item 1 of argv
  set jsCode to item 2 of argv
  set expandJsCode to item 3 of argv
  set targetUrl to "https://x.com/" & handleName
  tell application "Google Chrome"
    if (count of windows) is 0 then make new window
    set currentUrl to URL of active tab of front window
    if currentUrl does not contain ("x.com/" & handleName) and currentUrl does not contain ("twitter.com/" & handleName) then
      set URL of active tab of front window to targetUrl
      delay 6
    end if
    tell active tab of front window
      repeat 3 times
        execute javascript expandJsCode
        delay 1
      end repeat
      execute javascript jsCode
    end tell
  end tell
end run
`;
  return JSON.parse(await runAppleScript(script, [config.handle, js, expandJs]));
}

async function getXWebClientConfig(config) {
  const pageRes = await fetchWithTimeout(`https://x.com/${config.handle}`, {
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  const page = await pageRes.text();
  const mainUrl =
    [...page.matchAll(/<script[^>]+src="(https:\/\/abs\.twimg\.com\/responsive-web\/client-web\/main\.[^"]+\.js)"/g)][0]?.[1] ||
    "https://abs.twimg.com/responsive-web/client-web/main.c467243a.js";
  const mainRes = await fetchWithTimeout(mainUrl, {
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  const mainJs = await mainRes.text();
  const bearer = mainJs.match(/Bearer ([A-Za-z0-9%_-]+)/)?.[1];
  const tweetResultQueryId = mainJs.match(/queryId:"([^"]+)",operationName:"TweetResultByRestId"/)?.[1];
  if (!bearer || !tweetResultQueryId) return null;
  return { bearer: decodeURIComponent(bearer), tweetResultQueryId };
}

async function fetchFullTweetTexts(tweetIds, config, errors) {
  const fullTexts = new Map();
  if (tweetIds.length === 0) return fullTexts;

  let webConfig;
  try {
    webConfig = await getXWebClientConfig(config);
  } catch (err) {
    errors.push(`Chrome fallback: could not load X web client config: ${err.message}`);
    return fullTexts;
  }
  if (!webConfig) return fullTexts;

  let guestToken;
  try {
    const tokenRes = await fetchWithTimeout("https://api.x.com/1.1/guest/activate.json", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${webConfig.bearer}`,
        "User-Agent": "Mozilla/5.0",
      },
    });
    guestToken = (await tokenRes.json()).guest_token;
  } catch (err) {
    errors.push(`Chrome fallback: could not activate X guest token: ${err.message}`);
    return fullTexts;
  }

  const features = Object.fromEntries(TWEET_RESULT_FEATURES.map((key) => [key, true]));
  for (const tweetId of tweetIds) {
    try {
      const variables = { tweetId, withCommunity: false, includePromotedContent: false, withVoice: false };
      const url =
        `https://twitter.com/i/api/graphql/${webConfig.tweetResultQueryId}/TweetResultByRestId` +
        `?variables=${encodeURIComponent(JSON.stringify(variables))}` +
        `&features=${encodeURIComponent(JSON.stringify(features))}` +
        `&fieldToggles=${encodeURIComponent(JSON.stringify(TWEET_RESULT_FIELD_TOGGLES))}`;
      const res = await fetchWithTimeout(url, {
        headers: {
          Authorization: `Bearer ${webConfig.bearer}`,
          "x-guest-token": guestToken,
          "User-Agent": "Mozilla/5.0",
          "x-twitter-active-user": "yes",
          "x-twitter-client-language": "en",
        },
      });
      if (!res.ok) continue;
      const payload = await res.json();
      const result = payload?.data?.tweetResult?.result;
      const tweet = result?.tweet || result;
      const fullText =
        tweet?.note_tweet?.note_tweet_results?.result?.text || tweet?.legacy?.full_text || null;
      if (fullText) fullTexts.set(tweetId, fullText);
    } catch (err) {
      errors.push(`Chrome fallback: could not fetch full text for ${tweetId}: ${err.message}`);
    }
  }
  return fullTexts;
}

async function fetchFromChrome(config, errors) {
  if (process.platform !== "darwin") return null;

  let articles;
  try {
    articles = await readChromeTimeline(config);
  } catch (err) {
    errors.push(`Chrome fallback: ${err.message}`);
    return null;
  }

  let tweets = articles.map((article) => extractChromeTweet(article, config.handle)).filter(Boolean);
  const fullTexts = await fetchFullTweetTexts(tweets.map((tweet) => tweet.id), config, errors);
  tweets = tweets.map((tweet) =>
    fullTexts.has(tweet.id) ? { ...tweet, text: decodeEntities(fullTexts.get(tweet.id)) } : tweet,
  );

  if (tweets.length === 0) return null;
  return {
    source: "chrome-x",
    profile: {
      name: config.displayName,
      handle: config.handle,
      bio: "",
      followers: null,
    },
    tweets,
    warnings: [
      "Using logged-in Chrome/X page fallback because anonymous X sources did not return current posts.",
    ],
  };
}

async function fetchFromXApi(config, bearerToken, options = {}) {
  const handle = config.handle;
  const userRes = await fetchWithTimeout(
    `${X_API_BASE}/users/by/username/${encodeURIComponent(handle)}?user.fields=description,public_metrics`,
    { headers: { Authorization: `Bearer ${bearerToken}` } },
  );

  if (!userRes.ok) throw new Error(`X user lookup failed: HTTP ${userRes.status}`);
  const userPayload = await userRes.json();
  const user = userPayload.data;
  if (!user?.id) throw new Error(`X user lookup returned no user for @${handle}`);

  const cutoff = new Date(Date.now() - config.lookbackHours * 60 * 60 * 1000);
  const params = new URLSearchParams({
    max_results: String(Math.max(5, Math.min(100, config.maxTweets * 3))),
    "tweet.fields": "created_at,public_metrics,referenced_tweets,note_tweet,entities,conversation_id",
    exclude: options.includeReplies ? "retweets" : "retweets,replies",
    start_time: cutoff.toISOString(),
  });
  const tweetsRes = await fetchWithTimeout(`${X_API_BASE}/users/${user.id}/tweets?${params}`, {
    headers: { Authorization: `Bearer ${bearerToken}` },
  });

  if (!tweetsRes.ok) throw new Error(`X tweets lookup failed: HTTP ${tweetsRes.status}`);
  const tweetsPayload = await tweetsRes.json();
  const tweets = (tweetsPayload.data || []).map((t) => {
    const referencedTweets = t.referenced_tweets || [];
    return normalizeTweet({
      id: t.id,
      text: t.note_tweet?.text || t.text,
      createdAt: t.created_at,
      url: `https://x.com/${handle}/status/${t.id}`,
      sourceUrl: `https://x.com/${handle}/status/${t.id}`,
      kind: kindFromReferences(referencedTweets),
      entities: t.entities,
      likes: t.public_metrics?.like_count || 0,
      retweets: t.public_metrics?.retweet_count || 0,
      replies: t.public_metrics?.reply_count || 0,
      isQuote: referencedTweets.some((r) => r.type === "quoted"),
      quotedTweetId: referencedTweets.find((r) => r.type === "quoted")?.id || null,
      replyToTweetId: referencedTweets.find((r) => r.type === "replied_to")?.id || null,
      referencedTweets,
    });
  });

  return {
    source: "x-api",
    profile: {
      name: user.name || config.displayName,
      handle,
      bio: user.description || "",
      followers: user.public_metrics?.followers_count ?? null,
    },
    tweets,
    warnings: [],
  };
}

async function fetchFromSyndication(config) {
  const handle = config.handle;
  const res = await fetchWithTimeout(
    `https://syndication.twitter.com/srv/timeline-profile/screen-name/${encodeURIComponent(handle)}`,
    {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
      },
    },
  );

  if (!res.ok) throw new Error(`X syndication fetch failed: HTTP ${res.status}`);
  const html = await res.text();
  const match = html.match(/<script id="__NEXT_DATA__" type="application\/json">([\s\S]*?)<\/script>/);
  if (!match) throw new Error("X syndication response did not include timeline JSON");

  const data = JSON.parse(match[1]);
  const entries = data?.props?.pageProps?.timeline?.entries || [];
  const tweetEntries = entries.filter((entry) => entry.type === "tweet" && entry.content?.tweet);

  const tweets = tweetEntries.map((entry) => {
    const t = entry.content.tweet;
    return normalizeTweet({
      id: t.id_str,
      text: t.full_text || t.text,
      createdAt: new Date(t.created_at).toISOString(),
      url: `https://x.com${t.permalink}`,
      sourceUrl: `https://x.com${t.permalink}`,
      kind: t.quoted_status_id_str ? "quote" : "post",
      likes: t.favorite_count || 0,
      retweets: t.retweet_count || 0,
      replies: t.reply_count || 0,
      isQuote: Boolean(t.quoted_status_id_str),
      quotedTweetId: t.quoted_status_id_str || null,
    });
  });

  const user = tweetEntries[0]?.content?.tweet?.user || {};
  return {
    source: "x-syndication",
    profile: {
      name: user.name || config.displayName,
      handle,
      bio: decodeEntities(user.description || ""),
      followers: user.followers_count ?? user.normal_followers_count ?? null,
    },
    tweets,
    warnings: [
      "Using X public syndication fallback because X_BEARER_TOKEN is not configured or X API failed. It may miss the newest posts and can truncate long posts.",
    ],
  };
}

function filterTweets(tweets, config, state, options) {
  const cutoff = new Date(Date.now() - config.lookbackHours * 60 * 60 * 1000);
  const seen = state.seenTweets || {};
  const includeSeen = options.includeSeen || options.all;
  const ignoreLookback = options.all;

  return tweets
    .filter((tweet) => tweet.id && tweet.url && tweet.text)
    .filter((tweet) => ignoreLookback || new Date(tweet.createdAt) >= cutoff)
    .filter((tweet) => includeSeen || !config.dedupe || !seen[tweet.id])
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
    .slice(0, config.maxTweets);
}

function countTweetKinds(tweets) {
  return tweets.reduce(
    (counts, tweet) => {
      counts[tweet.kind || "post"] = (counts[tweet.kind || "post"] || 0) + 1;
      return counts;
    },
    { post: 0, quote: 0, reply: 0 },
  );
}

async function main() {
  await mkdir(USER_DIR, { recursive: true });
  await mkdir(CACHE_DIR, { recursive: true });

  const config = { ...DEFAULT_CONFIG, ...(await readJSON(CONFIG_PATH, {})) };
  config.delivery = { ...DEFAULT_CONFIG.delivery, ...(config.delivery || {}) };
  config.lookbackHours = Number(argValue("--lookback-hours") ?? config.lookbackHours);
  config.maxTweets = Number(argValue("--max-tweets") ?? config.maxTweets);

  const options = {
    all: hasFlag("--all"),
    includeSeen: hasFlag("--include-seen"),
    includeReplies: hasFlag("--include-replies"),
    noCache: hasFlag("--no-cache"),
    chrome: hasFlag("--chrome"),
  };
  const cachePath = options.includeReplies
    ? join(CACHE_DIR, "latest-fetch-with-replies.json")
    : CACHE_PATH;
  const env = { ...process.env, ...(await readEnv(ENV_PATH)) };
  const state = await readJSON(STATE_PATH, { seenTweets: {} });

  const errors = [];
  let result;
  let usedCache = false;
  const tryChrome = async () => {
    const chromeResult = await fetchFromChrome(config, errors);
    if (!chromeResult) return false;
    result = chromeResult;
    usedCache = false;
    return true;
  };

  if (env.X_BEARER_TOKEN) {
    try {
      result = await fetchFromXApi(config, env.X_BEARER_TOKEN, options);
    } catch (err) {
      errors.push(err.message);
    }
  }
  if (!result) {
    try {
      result = await fetchFromSyndication(config);
    } catch (err) {
      errors.push(err.message);
    }
  }

  if (!result && (options.chrome || config.chromeFallback)) {
    await tryChrome();
  }

  if (!result && !options.noCache && existsSync(cachePath)) {
    result = JSON.parse(await readFile(cachePath, "utf-8"));
    usedCache = true;
    result.warnings = [
      ...(result.warnings || []),
      "Live fetch failed, so this output used the last cached fetch. Treat it as stale unless tweet timestamps are inside the requested window.",
    ];
  }

  if (!result) {
    const output = {
      status: "degraded",
      generatedAt: new Date().toISOString(),
      source: null,
      config,
      profile: { name: config.displayName, handle: config.handle, bio: "", followers: null },
      tweets: [],
      stats: { fetchedTweets: 0, returnedTweets: 0, lookbackHours: config.lookbackHours },
      warnings: [
        "No live X source was available. Configure X_BEARER_TOKEN in ~/.follow-aleabito/.env for reliable daily delivery.",
      ],
      errors,
      statePath: STATE_PATH,
    };
    const outputPath = argValue("--output");
    if (outputPath) await writeFile(outputPath, JSON.stringify(output, null, 2) + "\n");
    console.log(JSON.stringify(output, null, 2));
    return;
  }

  result.tweets = (result.tweets || []).map((tweet) => normalizeTweet(tweet));

  if (!result.warnings?.some((warning) => warning.includes("cached fetch"))) {
    await writeFile(cachePath, JSON.stringify(result, null, 2) + "\n");
  }

  let tweets = filterTweets(result.tweets, config, state, options);
  if (
    (options.chrome && usedCache) ||
    (result.source !== "chrome-x" && (options.chrome || (config.chromeFallback && tweets.length === 0)))
  ) {
    if (await tryChrome()) {
      tweets = filterTweets(result.tweets, config, state, options);
      if (!result.warnings?.some((warning) => warning.includes("cached fetch"))) {
        await writeFile(cachePath, JSON.stringify(result, null, 2) + "\n");
      }
    }
  }
  const fetchedKinds = countTweetKinds(result.tweets);
  const returnedKinds = countTweetKinds(tweets);
  const output = {
    status: "ok",
    generatedAt: new Date().toISOString(),
    source: result.source,
    config,
    profile: result.profile,
    tweets,
    stats: {
      fetchedTweets: result.tweets.length,
      returnedTweets: tweets.length,
      fetchedKinds,
      returnedKinds,
      lookbackHours: config.lookbackHours,
      includeReplies: options.includeReplies,
    },
    warnings: result.warnings,
    errors: errors.length ? errors : undefined,
    statePath: STATE_PATH,
  };

  const outputPath = argValue("--output");
  if (outputPath) {
    await writeFile(outputPath, JSON.stringify(output, null, 2) + "\n");
  }
  console.log(JSON.stringify(output, null, 2));
}

main().catch((err) => {
  console.error(JSON.stringify({ status: "error", message: err.message }, null, 2));
  process.exit(1);
});
