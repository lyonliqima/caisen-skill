---
name: follow-aleabito
description: Track Serenity / @aleabitoreddit on X and turn the feed into (1) a beginner-friendly Chinese iMessage digest with first-principles + Buffett-style judgement, (2) cumulative 60-day ticker mention analytics CSVs for a website, (3) a Xiaohongshu writing brief, and (4) a durable private research map. Trigger on requests like "follow aleabitoreddit / AleaBito / Serenity", "daily Chinese updates from that X account", "60-day mention analytics", "ticker mention count", "写小红书 aleabito", "aleabito 研究地图 / research map", or any request for Chinese commentary derived from @aleabitoreddit posts.
---

# Follow AleaBito

## Purpose

Track `@aleabitoreddit` on X and produce deliverables grounded only in fetched posts. Always include source URLs. Treat the content as market commentary, not investment advice.

**Language / 语言:** deliverables default to **中文** (the digest and Xiaohongshu workflows are Chinese-first by design), but any of them can be produced in **English** when the user asks. The analytics CSVs and research map are language-neutral.

This skill handles four workflows. Pick the one(s) the user asked for and read the matching reference file only when needed:

| User intent | Workflow | Section |
| --- | --- | --- |
| Daily Chinese update / iMessage digest | Digest | [Daily Digest](#daily-digest-workflow) |
| 60-day mention CSVs, ticker leaderboard, website data | Analytics | [Mention Analytics](#cumulative-mention-analytics) + `references/analytics.md` |
| Xiaohongshu post | Xiaohongshu | [Xiaohongshu](#xiaohongshu-workflow) + `references/xhs-style.md` |
| Research map | Research map | [Research Map](#research-map-workflow) |

When producing any `AI 分析`, read `references/analysis-framework.md` first. **All Buffett-style fields default to `unverified`; escalation requires cited evidence.**

## Paths

Reports go under `$FOLLOW_ALEABITO_REPORTS_DIR`. If unset, default to `$HOME/Documents/aleabito-reports`. Treat all CSV / meta paths below as `$FOLLOW_ALEABITO_REPORTS_DIR/<filename>`.

## Data Sources

Use `scripts/fetch-updates.js`. It tries:

1. X API v2 when `X_BEARER_TOKEN` exists in `~/.follow-aleabito/.env`.
2. X public syndication fallback when no token is configured.
3. Logged-in Chrome/X page fallback on macOS when anonymous sources return nothing.

Caveats: the syndication fallback can miss the newest posts or truncate long ones. The Chrome fallback may open `https://x.com/aleabitoreddit` in the active Chrome tab — expand any `Show more` before extracting. If the JSON output contains `warnings`, mention them briefly in the digest or setup guidance.

Never invent posts, prices, positions, or links. If no fetched post has a URL, do not include it.

## Daily Digest Workflow

```bash
cd "${CODEX_HOME:-$HOME/.codex}/skills/follow-aleabito"
node scripts/fetch-updates.js --include-replies --lookback-hours 36 --max-tweets 50 --output /tmp/follow-aleabito-updates.json
node scripts/build-digest-brief.js --input /tmp/follow-aleabito-updates.json --output /tmp/follow-aleabito-brief.md
```

Read `/tmp/follow-aleabito-brief.md` (ticker counts, theme groups, high-signal replies, source links) before writing. Use the raw JSON only when the brief is insufficient.

If `tweets` is empty:
- If `config.notifyWhenEmpty` is true, send `今天 @aleabitoreddit 没有抓到新的可发送动态。`
- Otherwise stop without sending.

Digest structure (Chinese, iMessage-sized — signal over completeness):

- Title: `Serenity / @aleabitoreddit 今日动态`
- `今天她重点看什么`
- 2-4 key takeaways grouped by theme.
- For each included post/theme: `她的观点` → `小白解释` → `第一性原理` → `Buffett 直接判断`. Read `references/analysis-framework.md` for the judgement shape and default-unverified rules.
- Mentioned tickers/themes, original URL, created time.
- Footer: `仅作信息跟踪，不构成投资建议。`

Send via [iMessage](#imessage-delivery). Run `mark-seen.js` **only after** `send-imessage.js` returns `status: ok`.

## Cumulative Mention Analytics

Trigger when the user asks for 60-day analytics, ticker mention counts, website-readable CSVs, or ongoing tracking. The workflow is cumulative, not rolling — the 60-day backfill is a seed; later runs only append new events.

Commands:

```bash
# initial backfill (only run once unless the events CSV is missing/corrupted)
node scripts/analyze-mentions.js --backfill-days 60 --include-replies --resume

# daily incremental
node scripts/analyze-mentions.js --incremental --include-replies --resume

# rebuild summary CSVs from existing events without hitting the API
node scripts/analyze-mentions.js --rebuild-only --include-replies --resume
```

Outputs land in `$FOLLOW_ALEABITO_REPORTS_DIR`:

- `aleabito-mentions-events.csv` — event-level rows.
- `aleabito-stock-mentions-cumulative.csv` — leaderboard for website home/search.
- `aleabito-stock-mentions-daily.csv` — daily ticker trend.
- `aleabito-mentions.meta.json` — last update, API status, rate-limit metadata.

For counting rules, API cost rules, and overlap-window guidance, read `references/analytics.md`.

If the X API fails, keep the previous CSVs and write the failure to `.meta.json`. Never overwrite good data on failure.

## Xiaohongshu Workflow

Trigger when the user asks for a Xiaohongshu post derived from the mention analytics.

```bash
node scripts/build-xhs-brief.js \
  --input "$FOLLOW_ALEABITO_REPORTS_DIR/aleabito-stock-mentions-cumulative.csv" \
  --daily "$FOLLOW_ALEABITO_REPORTS_DIR/aleabito-stock-mentions-daily.csv" \
  --output /tmp/follow-aleabito-xhs-brief.md \
  --variants both
```

Read the generated brief, then write in Chinese. Default to producing both a full version and an under-1000-Chinese-character version unless the user asks for only one.

Read `references/xhs-style.md` for writing rules, required structure, and the default-unverified Buffett shape.

## Research Map Workflow

Trigger when the user wants a durable research map after analytics.

```bash
node scripts/update-research-map.js \
  --events "$FOLLOW_ALEABITO_REPORTS_DIR/aleabito-mentions-events.csv" \
  --summary "$FOLLOW_ALEABITO_REPORTS_DIR/aleabito-stock-mentions-cumulative.csv" \
  --output ~/.follow-aleabito/research-map.json
```

Also writes `~/.follow-aleabito/research-map.md`. Preserve existing manual notes and Buffett fields when refreshing. If evidence is missing, keep fields as `unverified` or `research map` — the deterministic script must not invent financial facts.

## iMessage Delivery

Recipient lives in `~/.follow-aleabito/config.json`:

```json
{
  "delivery": {
    "method": "imessage",
    "recipient": "+15551234567"
  }
}
```

```bash
node scripts/send-imessage.js --file /tmp/follow-aleabito-digest.txt
node scripts/mark-seen.js --file /tmp/follow-aleabito-updates.json   # only after send succeeds
```

If iMessage delivery fails because the recipient is missing, point the user to:

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/follow-aleabito/scripts/setup-config.js" --recipient "<phone-or-apple-id>"
```

On first run, the user must also grant Messages automation permission in System Settings → Privacy & Security → Automation.

## Setup

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/follow-aleabito/scripts/setup-config.js" --recipient "<phone-or-apple-id>"
cp ~/.follow-aleabito/.env.example ~/.follow-aleabito/.env   # then set X_BEARER_TOKEN
export FOLLOW_ALEABITO_REPORTS_DIR="$HOME/Documents/aleabito-reports"   # or wherever the website reads from
```

## Automation

For a daily cron, run in order: `fetch-updates.js` → write Chinese digest to `/tmp/follow-aleabito-digest.txt` → `send-imessage.js` → `mark-seen.js` only after success. Default recommended time: 8:00 AM in the user's timezone.
