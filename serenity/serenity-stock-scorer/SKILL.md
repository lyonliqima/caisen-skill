---
name: serenity-stock-scorer
description: Score a stock from 0-100 using the local Serenity Signal Ledger tweet corpus. Use when a user asks to rate, rank, analyze, or triage a ticker based on Serenity/X tweet evidence, cashtag mentions, Serenity-style AI supply-chain theses, or the project-local `data/serenity.sqlite` or `api/instance/serenity.sqlite` snapshot.
---

# Serenity Stock Scorer

## Quick Start

When asked to score a ticker, first use the bundled script if a Serenity SQLite snapshot is available:

```bash
python skills/serenity-stock-scorer/scripts/score_serenity_stock.py NVDA --pretty
```

If the repo-local database is not in the default location, pass `--db /path/to/serenity.sqlite` or set `SERENITY_DB_PATH`.

## Workflow

1. Normalize the input ticker to an uppercase cashtag symbol without `$`.
2. Run `skills/serenity-stock-scorer/scripts/score_serenity_stock.py <SYMBOL> --pretty` to get mention metrics, component scores, top topics, and evidence tweet IDs/URLs.
3. Read `references/serenity-framework.md` when you need the full rubric, rating bands, or qualitative overrides.
4. Convert the script output into a concise 0-100 score note; include the score, the Serenity-style thesis, evidence, risk caps, and what would move the score.
5. If the symbol has no mentions, say the Serenity corpus does not support scoring it directly; give a low evidence score unless the user supplies outside thesis material.

## Scoring Rules

Use the script score as the starting point, not an unquestioned final answer. Adjust only when the user provides fundamentals, recent price action, or qualitative facts not in the SQLite snapshot.

- Boost when the stock has repeated recent mentions, explicit long/position language, high engagement, and direct fit with Serenity's recurring themes: optical/photonics/CPO, AI infrastructure/neocloud, memory/storage, semicap/materials/substrates, power/grid, robotics/space/industrial, or select platform/fintech ideas.
- Boost when the thesis is second-order and supply-chain specific: bottlenecks, scarce components, reshoring, capacity constraints, underfollowed suppliers, or asymmetric rerating setup.
- Penalize for stale or one-off mentions, vague theme fit, crowded mega-cap proxy exposure, weak catalyst timing, stretched valuation, dilution/debt, customer concentration, geopolitical/tariff risk, or explicit caution/trim/sell language.
- Keep `85+` rare; require recent repeated evidence plus clear asymmetry and manageable risks.
- Never frame the score as financial advice; label it as a Serenity-corpus signal score.

## Output Template

```text
Score: NN/100 — <rating>

Why Serenity would care:
- <theme-fit point>
- <supply-chain/asymmetry point>
- <catalyst/timing point>

Evidence:
- Mentions: <n>; first/latest: <dates>; top topics: <topics>
- Tweet evidence: <tweet IDs or URLs>

Risks / score caps:
- <risk 1>
- <risk 2>

What would move the score:
- Up: <confirmation>
- Down: <invalidation>
```
