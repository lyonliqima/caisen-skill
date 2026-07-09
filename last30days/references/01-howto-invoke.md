# HOW TO INVOKE THIS SKILL (READ FIRST, FOLLOW EVERY TIME)

**STEP 0 - LOAD WEBSEARCH FIRST.** Your literal first tool call on every `/last30days` invocation MUST be:

```
ToolSearch select:WebSearch
```

WebSearch is a **deferred tool** in Claude Code v2.1.114. The frontmatter of this file authorizes it (`allowed-tools: ... WebSearch`) but the runtime lists it as "schemas are NOT loaded." Calling WebSearch without `ToolSearch select:WebSearch` first will fail or do nothing. That friction is the documented cause of the second-most-common failure mode of this skill: the model sees "WebSearch is there but deferred," takes the low-friction path, skips Step 0.5 and 0.55, and runs the engine bare with only keyword search. The output looks fine but misses founder X timelines, GitHub repo activity, and subreddit-specific threads.

Load WebSearch first. No exceptions. Then proceed to the branching rule below.

**STEP 1 - RUN THE ENGINE. You MUST run `scripts/last30days.py` via Bash. Do not produce output from WebSearch alone.**

The single most common failure mode of this skill is the model reading this file, skimming the section headers, and then answering the user's topic with 3-10 WebSearch calls followed by a prose summary. That is wrong output. The Python engine is the skill. Web-only synthesis is not the skill.

Branching rule:

- **If the user provided a topic** (e.g. `/last30days Kanye West`, `/last30days nvidia earnings`): proceed to Step 0.5 / Step 0.55 / Step 0.75 / Research Execution below. Do not skip straight to WebSearch. WebSearch is a **supplement after** the Python engine runs (see Step 2). It is **not a substitute**.
- **If the user provided no topic**: ask the user for a topic with a single short question. Do not run research. Do not run WebSearch. Wait.

If you are about to write a response without having run `scripts/last30days.py` at least once, stop. Return to Research Execution and run the engine. Every valid output from this skill includes the emoji-tree footer (`✅ All agents reported back!`) that the engine produces data for. No footer means you did not run the skill.

Before Step 0.5, run Step 0.45 Query Quality Pre-Flight. If the topic is a keyword trap (demographic shopping like "gift for 42 year old man", numeric/age trap, overly-literal concept phrase like "how to use Docker", or generic single-noun like "sneakers"), reframe or ask ONE clarifying question before calling the engine. Skipping Step 0.45 on a keyword-trap topic is the named failure mode of the 2026-04-18 "Birthday gift for 42 year old man" disaster: the engine ran on the literal phrase and returned 5 minutes of r/todayilearned / r/japannews / r/LivestreamFail noise because no human posts "I bought a 42 year old man a gift" on Reddit.

If your Bash call to `last30days.py` does NOT include the FULL pre-flight checklist resolved (see Step 0.5 Pre-Flight Checklist), that is a Step 0.5/0.55 skip. The engine will emit a `## Pre-Research Status` warning block in its output. Pass the warning through verbatim; do not try to hide it. The warning tells the user to rerun with WebSearch loaded.

**For person topics specifically (developers, creators, CEOs, founders): the Bash command MUST include MINIMUM `--x-handle={handle}` AND `--github-user={handle}` AND `--subreddits={list}`, and typically `--x-related={list}`, unless an explicit "no account" note was produced during Step 0.5.** A person-topic command with ONLY `--x-handle` is the Peter Steinberger disaster #2 failure mode (2026-04-18): the model read the X-handle subsection literally, stopped there, and skipped the rest of the checklist. Result: weak Reddit targeting, no GitHub person-mode scoping, no related-voices enrichment, and a thin corpus. The fix is to read the Step 0.5 Pre-Flight Checklist FIRST and resolve every applicable flag before running the engine.

---

# last30days v3.3.1: Research Any Topic from the Last 30 Days

> **Permissions overview:** Reads public web/platform data and optionally saves research briefings to `LAST30DAYS_MEMORY_DIR` (defaults to `~/Documents/Last30Days`). X/Twitter search uses optional user-provided tokens (AUTH_TOKEN/CT0 env vars). Bluesky search uses optional app password (BSKY_HANDLE/BSKY_APP_PASSWORD env vars - create at bsky.app/settings/app-passwords). All credential usage and data writes are documented in the [Security & Permissions](#security--permissions) section.

Research ANY topic across Reddit, X, YouTube, and other sources. Surface what people are actually discussing, recommending, betting on, and debating right now.

## Runtime Preflight

Before running any `last30days.py` command in this skill, resolve a Python 3.12+ interpreter once and keep it in `LAST30DAYS_PYTHON`:

```bash
for py in python3.14 python3.13 python3.12 python3; do
  command -v "$py" >/dev/null 2>&1 || continue
  "$py" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' || continue
  LAST30DAYS_PYTHON="$py"
  break
done

if [ -z "${LAST30DAYS_PYTHON:-}" ]; then
  echo "ERROR: last30days v3 requires Python 3.12+. Install python3.12 or python3.13 and rerun." >&2
  exit 1
fi

LAST30DAYS_MEMORY_DIR="${LAST30DAYS_MEMORY_DIR:-$HOME/Documents/Last30Days}"
```

## Configuration

Set `LAST30DAYS_MEMORY_DIR` before invoking the skill to choose where raw research files are saved. If it is not set, the skill defaults to `~/Documents/Last30Days`.

## Step 0: First-Run Setup Wizard

Before proceeding to Step 1, handle first-run setup.

**First-run detection (silent, no commands, no output to user):**
- If `~/.config/last30days/.env` does NOT exist, this is a first run.
- If the file exists and contains `SETUP_COMPLETE=true`, skip Step 0 entirely and go to Step 1 (CRITICAL: Parse User Intent below). Do NOT announce that setup is complete. The user does not need a status message on every run.

**If this IS a first run:**
- Use the Read tool to load `skills/last30days/nux-wizard.md` (relative to the skill root).
- Follow the wizard's instructions end-to-end. The wizard handles platform detection (OpenClaw vs Claude Code), auto vs manual setup, ScrapeCreators opt-in, and the initial topic picker.
- After the wizard writes `SETUP_COMPLETE=true` to `~/.config/last30days/.env`, proceed to research.

The wizard lives in a separate file so the common-case (already set up) path through this file is short and the voice-contract rules further down stay in context.

---
