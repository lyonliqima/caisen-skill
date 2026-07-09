## CRITICAL: Parse User Intent

Before doing anything, parse the user's input for:

1. **TOPIC**: What they want to learn about (e.g., "web app mockups", "Claude Code skills", "image generation")
2. **TARGET TOOL** (if specified): Where they'll use the prompts (e.g., "Nano Banana Pro", "ChatGPT", "Midjourney")
3. **QUERY TYPE**: What kind of research they want:
   - **PROMPTING** - "X prompts", "prompting for X", "X best practices" → User wants to learn techniques and get copy-paste prompts
   - **RECOMMENDATIONS** - "best X", "top X", "what X should I use", "recommended X" → User wants a LIST of specific things
   - **NEWS** - "what's happening with X", "X news", "latest on X" → User wants current events/updates
   - **COMPARISON** - "X vs Y", "X versus Y", "compare X and Y", "X or Y which is better" → User wants a side-by-side comparison
   - **GENERAL** - anything else → User wants broad understanding of the topic

Common patterns:
- `[topic] for [tool]` → "web mockups for Nano Banana Pro" → TOOL IS SPECIFIED
- `[topic] prompts for [tool]` → "UI design prompts for Midjourney" → TOOL IS SPECIFIED
- Just `[topic]` → "iOS design mockups" → TOOL NOT SPECIFIED, that's OK
- "best [topic]" or "top [topic]" → QUERY_TYPE = RECOMMENDATIONS
- "what are the best [topic]" → QUERY_TYPE = RECOMMENDATIONS
- "X vs Y" or "X versus Y" → QUERY_TYPE = COMPARISON, TOPIC_A = X, TOPIC_B = Y (split on ` vs ` or ` versus ` with spaces)

**IMPORTANT: Do NOT ask about target tool before research.**
- If tool is specified in the query, use it
- If tool is NOT specified, run research first, then ask AFTER showing results

**Store these variables:**
- `TOPIC = [extracted topic]`
- `TARGET_TOOL = [extracted tool, or "unknown" if not specified]`
- `QUERY_TYPE = [RECOMMENDATIONS | NEWS | HOW-TO | COMPARISON | GENERAL]`
- `TOPIC_A = [first item]` (only if COMPARISON)
- `TOPIC_B = [second item]` (only if COMPARISON)

**Confirm the topic with a branded, truthful message. Build ACTIVE_SOURCES_LIST by checking what's configured in .env:**

- Always active: Reddit, Hacker News, Polymarket
- If gh CLI is installed (check `which gh`): add GitHub
- If digg-pp-cli is installed (check `which digg-pp-cli`): add Digg
- If AUTH_TOKEN/CT0 or XAI_API_KEY or FROM_BROWSER is set, or xurl CLI is installed and authenticated: add X
- If yt-dlp is installed (check `which yt-dlp`): add YouTube
- If SCRAPECREATORS_API_KEY is set: add TikTok, Instagram, Threads (suppress any of these via EXCLUDE_SOURCES)
- If SCRAPECREATORS_API_KEY is set and the user explicitly requested pinterest for this query (e.g. via `--search=pinterest`): add Pinterest
- If BSKY_HANDLE and BSKY_APP_PASSWORD are set: add Bluesky
- If OPENROUTER_API_KEY is set and INCLUDE_SOURCES contains perplexity: add Perplexity
- If EXCLUDE_SOURCES is set (comma-separated, case-insensitive): drop any matching source from the list above before displaying

Then display (use "and more" if 5+ sources, otherwise list all with Oxford comma):

For GENERAL / NEWS / RECOMMENDATIONS / PROMPTING queries:
```
/last30days - searching {ACTIVE_SOURCES_LIST} for what people are saying about {TOPIC}.
```

For COMPARISON queries:
```
/last30days - comparing {TOPIC_A} vs {TOPIC_B} across {ACTIVE_SOURCES_LIST}.
```

Do NOT show a multi-line "Parsed intent" block with TOPIC=, TARGET_TOOL=, QUERY_TYPE= variables. Do NOT promise a specific time. Do NOT list sources that aren't configured.

Then proceed immediately to Step 0.45.
