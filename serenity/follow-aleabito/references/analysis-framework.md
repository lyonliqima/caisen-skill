# Follow AleaBito AI Analysis Framework

This file defines how to add `AI 分析` to digests, Xiaohongshu posts, and research map entries. Read this only when you actually need to produce analysis output.

## Scope

For daily digests, do not use the full Buffett output template unless the user asks for a deep dive on one company. Compress the analysis into 1-3 paragraphs and reuse the shape below.

## First Principles

Value comes from future owner cash flows. Always reason from:

- Durability of demand.
- Supply bottlenecks.
- Pricing power.
- Capital intensity.
- Rule-of-law / property-rights stability.

## Beginner-Friendly Wording

Define terms the first time they appear, including but not limited to: CPO, photonics, 800VDC, P/B, TAM, ASP, margin, cash flow, customer switching cost, second source, certification cycle.

## Buffett References

Use the local `$buffett` skill if it exists at `${CODEX_HOME:-$HOME/.codex}/skills/buffett/SKILL.md`. Read only the chapters you need:

- Business quality / moat claims → `$buffett/references/03-business-moat.md`.
- Management, acquisitions, buybacks, dilution, capital allocation → `$buffett/references/04-management-governance.md` and `$buffett/references/06-valuation-capital.md`.
- China / regulatory / policy risk, leverage, value traps, exit timing → `$buffett/references/07-risk-behavior.md`.
- Technology / semiconductor / AI infrastructure themes → the technology chapter in `$buffett/references/08-industry-playbooks.md`.

If `$buffett` is not installed, proceed with first-principles reasoning only and mark Buffett fields as `unverified`.

## Required Output Shape

For each important ticker or theme:

1. `她的观点` — what Serenity said, grounded in the fetched post.
2. `小白解释` — plain-language reframing.
3. `第一性原理` — apply the first-principles list above.
4. `Buffett 直接判断` — answer the fields below.

## Buffett Direct Judgement — Default Unverified

Every field starts at `unverified` / `insufficient evidence`. Escalate only when you can cite specific evidence from the fetched post, the Buffett references, or verified public financials. A single tweet is not evidence for "strong" or "proven".

- `护城河`: `unverified` by default. Escalate to `weak` / `medium` / `strong` only with a one-sentence reason rooted in evidence (certifications, switching cost, network effect, regulatory barrier, unique IP, scale economics).
- `赚钱能力`: `unverified` by default. Escalate to `improving` or `proven` only when revenue, gross margin, operating margin, or cash flow numbers are cited.
- `客户替换风险`: `unverified` by default. Escalate to `low` / `medium` / `high` only with reasons (certification cycle, switching cost, second-source availability, customer concentration).
- `Buffett 式好公司`: `not yet` by default. `yes` requires moat + 赚钱能力 + reasonable capital allocation all rated above unverified. `no` requires explicit disqualifying evidence.
- `当前结论`: `insufficient evidence` by default. `research map` is acceptable when there is a lead worth tracking. `investable conclusion` requires moat, financials, valuation, and margin-of-safety work — never from tweets alone.

Do not ask Buffett-style questions in the final output. Answer them, even if the honest answer is `unverified`.

## Hard Rules

- Never turn Serenity's posts into direct buy/sell instructions.
- Distinguish `研究地图` (leads worth tracking) from `可投资结论` (only valid after moat, financials, valuation, and margin-of-safety work).
- If evidence is missing, say so. Do not invent moat, margins, customer lists, or valuation multiples.
