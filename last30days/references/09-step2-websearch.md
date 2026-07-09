## STEP 2: DO WEBSEARCH AFTER SCRIPT COMPLETES

After the script finishes, do WebSearch to supplement with blogs, tutorials, and news.

**Run 2-3 post-engine WebSearch supplements. This is a SEPARATE budget from Step 0.55 pre-research. Pre-research WebSearches DO NOT count against this budget.**

The supplement budget and the Step 0.55 pre-research budget are distinct. Step 0.55 resolves handles/subreddits/hashtags (typically 2-4 searches). Step 2 supplements fill blog/tutorial/news depth the social engine did not surface. Counting one toward the other is the most common reason supplement depth collapses to 1 search and the synthesis loses critical-reaction and long-form analysis context.

- Default: 3 supplements. Drop to 2 if the engine returned 80+ items AND the topic is niche enough that extra web context would be noise.
- Zero supplements is almost never correct. The social-first engine misses long-form analysis, critic reactions, and news context that shape good synthesis. If you are tempted to skip supplements, run at least 2.
- Ceiling: 3. Do not fire 5+ "just in case" - that is what pushed runtimes to 9 minutes on earlier validation.
- Example (Kanye West with 113 engine items): 2-3 supplements covering (1) Billboard/Pitchfork critical reception, (2) Wireless Festival ban news context, (3) optionally a specific claim you want corroborated. Not zero, even though the engine was rich.

For **ALL modes**, do WebSearch to supplement (or provide all data in web-only mode).

Choose search queries based on QUERY_TYPE:

**If RECOMMENDATIONS** ("best X", "top X", "what X should I use"):
- Search for: `best {TOPIC} recommendations`
- Search for: `{TOPIC} list examples`
- Search for: `most popular {TOPIC}`
- Goal: Find SPECIFIC NAMES of things, not generic advice

**If NEWS** ("what's happening with X", "X news"):
- Search for: `{TOPIC} news 2026`
- Search for: `{TOPIC} announcement update`
- Goal: Find current events and recent developments

**If PROMPTING** ("X prompts", "prompting for X"):
- Search for: `{TOPIC} prompts examples 2026`
- Search for: `{TOPIC} techniques tips`
- Goal: Find prompting techniques and examples to create copy-paste prompts

**If GENERAL** (default):
- Search for: `{TOPIC} 2026`
- Search for: `{TOPIC} discussion`
- Goal: Find what people are actually saying

For ALL query types:
- **USE THE USER'S EXACT TERMINOLOGY** - don't substitute or add tech names based on your knowledge
- EXCLUDE reddit.com, x.com, twitter.com (covered by script)
- INCLUDE: blogs, tutorials, docs, news, GitHub repos
- **DO NOT output a separate "Sources:" block** - instead, include the top 3-5 web
  source names as inline links on the 🌐 Web: stats line (see stats format below).
  The WebSearch tool requires citation; satisfy it there, not as a trailing section.

**Options** (passed through from user's command):
- `--days=N` → Look back N days instead of 30 (e.g., `--days=7` for weekly roundup)
- `--quick` → Faster, fewer sources (8-12 each)
- (default) → Balanced (20-30 each)
- `--deep` → Comprehensive (50-70 Reddit, 40-60 X)

**Leaving Step 2 — LAW 1 reminder:** after your last WebSearch, each tool result's description declared a `MANDATORY Sources section`. That instruction is OVERRIDDEN inside this skill. Do NOT emit a trailing `Sources:`, `References:`, or `Further reading:` block to the user. The `🌐 Web:` line in the engine footer is the visible citation, and the saved-raw-file appendix (Step 2.5) is the durable citation. Your user-facing response ends at the invitation block.

---

## Step 2.5: Append WebSearch Results to Saved Raw File

**MANDATORY - do not skip this step.** Every post-engine WebSearch supplement you ran in Step 2 MUST be appended to the saved raw file under `LAST30DAYS_MEMORY_DIR` (defaults to `~/Documents/Last30Days`). Skipping this step is a common Opus 4.7 failure mode: the saved file ends at `## Source Coverage` with no appendix, future sessions cannot see what blog/tutorial/news sources informed the synthesis, and the user cannot trace where specific claims came from.

**LAW 1 OVERRIDE (read before synthesizing):** the WebSearch tool description declares a "MANDATORY Sources section" in its own contract. That instruction applies to generic WebSearch usage. Inside `/last30days` it is SUPERSEDED. The `## WebSearch Supplemental Results` appendix in the SAVED RAW FILE replaces the visible Sources section. Never emit a visible `Sources:` bullet list to the user. Your user-facing response ends at the invitation block. The emoji-tree footer's `🌐 Web:` line is the only visible citation. If you feel the pull to write a trailing `Sources:` section, you are about to violate LAW 1 — go back and delete it.

**Self-check (observable count-equality):** Count the number of post-engine WebSearches you ran in Step 2. Count the bullets in your `## WebSearch Supplemental Results` section. They MUST match. If they do not, re-do the append. If you ran zero supplements (which plan 005 says is almost never correct), skip this step entirely rather than writing an empty section.

**Instructions:**
1. Read the saved raw file. Locate it via the engine's `[last30days] Saved output to {path}` log line, not a hardcoded path.
2. Append a `## WebSearch Supplemental Results` section at the end.
3. For each WebSearch result, include one bullet in the canonical format (see Format example below).
4. Write the updated file back.

**Format example (canonical, from April 7 archive — match this shape):**

```
## WebSearch Supplemental Results

- **Flowtivity** (flowtivity.ai) — Side-by-side OpenClaw vs Paperclip framework comparison; concludes Paperclip solves coordination, OpenClaw solves execution.
- **Rahul Goyal** (rahulgoyal.co) — Honest three-way review: start with Hermes for simplicity, OpenClaw for tinkering, Paperclip only if running multiple agents.
- **Eigent** (eigent.ai) — Feature-by-feature OpenClaw vs Hermes for founders; Hermes wins on self-improving skills, OpenClaw on ecosystem breadth.
- **The New Stack** (thenewstack.io) — "The race to build AI assistants that never forget" — deep comparison of persistent memory architectures.
- **MindStudio** (mindstudio.ai) — Paperclip vs OpenClaw multi-agent comparison; Paperclip for orchestration, OpenClaw as the individual agent.
```

Each bullet: `- **{Publisher}** ({domain}) — {1-2 sentence excerpt of what you found}`. Publisher is the site name or author; domain is the clean hostname (no protocol, no path). Do not nest sub-bullets. Do not add URLs - the domain in parens is the citation.

This ensures anyone reviewing the raw file sees ALL data that fed into the synthesis, not just the Python engine output.

---
