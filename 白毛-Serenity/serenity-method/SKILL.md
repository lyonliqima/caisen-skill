---
name: serenity-method
description: Apply @aleabitoreddit ("Serenity")'s distilled stock-analysis method to ANY ticker, sector, or situation — critical-chokepoint / supply-chain-OSINT idea discovery, first-principles value-chain decomposition, a Buffett-style quality gate (moat / profitability / customer-replacement risk, all default unverified), and narrative-vs-fundamentals hygiene. Produces a beginner-friendly Chinese analysis (她的观点 / 小白解释 / 第一性原理 / Buffett 直接判断 / 当前结论) that classifies an idea as 研究地图 vs 可投资结论. Trigger on "analyze like Serenity / 用 aleabito 的方法分析 / 用 Serenity 框架 / critical chokepoint 分析 / 第一性原理 + Buffett 判断这只股 / supply-chain bottleneck thesis". Never emits buy/sell calls.
---

# Serenity Method

A distilled, reusable version of how Serenity (`@aleabitoreddit`) analyzes equities. Use it to analyze **any** stock, supply chain, or market situation — not only her feed. It captures her *method*, not her positions.

This skill is **method only**. It does not fetch data. To pull her live posts or build mention analytics, use the separate `follow-aleabito` skill; you can feed its output into this method, but this skill works standalone on any company you research yourself.

> One-line summary of the method: **find the real bottleneck, reason from first principles, gate it through Buffett-style quality questions, separate narrative from fundamentals, and label the result a research lead — not a buy.**

## When to use

- "Analyze $X the way Serenity / aleabito would."
- "Is $X a critical chokepoint? Map its supply chain."
- "Give me a first-principles + Buffett judgment on $X."
- Turning a Serenity post (or any thesis) into a structured, beginner-friendly analysis (中文 or English).

## What you produce

**Language / 语言:** respond in the **user's language** — 中文 by default, **English** when the request is in English or the user asks. The structure is identical in both; bilingual block labels are shown below.

For each ticker or theme, output these blocks, beginner-friendly, defining jargon on first use (see `references/glossary.md`):

1. **核心论点 / 她的观点 · Core thesis / Her view** — the one-paragraph thesis (if analyzing a Serenity post, ground it in the post + cite the source URL; if analyzing your own idea, state it plainly).
2. **小白解释 · Plain-language** — re-explain in plain language a beginner can follow.
3. **第一性原理 · First principles** — decompose with the five levers (Step 2).
4. **Buffett 直接判断 · Buffett verdict** — answer the five fields (Step 3). *Answer them, do not pose them as questions.*
5. **当前结论 · Conclusion** — classify: `研究地图 / research-map`(a lead worth tracking)vs `可投资结论 / investable-conclusion`(only after moat + financials + valuation + margin-of-safety work). Default to `研究地图`.

End every deliverable with the disclaimer in the output language: **仅作信息跟踪，不构成投资建议。** / **For information tracking only; not investment advice.**

For multi-name digests, compress blocks 2–4 into 1–3 paragraphs per name. Use the full template only for a single deep-dive. (This mirrors the dashboard digests in `reports/aleabito-digests/`.)

## The method (5 steps)

### Step 1 — Find the critical chokepoint (her signature move)
Start from a durable macro driver, walk the value chain, and locate the **bottleneck** — the link where demand is real, supply is scarce, and one company is hard to design out.

```
macro driver → demand for a capability → value-chain link that becomes the bottleneck
→ who is designed-in / certified there → sole or primary source? → at what market cap vs the opportunity?
```

A candidate is interesting when **all** hold: (a) customers *must* have the capability, (b) supply can't be added quickly, (c) the company is certified/designed-in, (d) it is cheap relative to the opportunity (un-priced). Missing any one → downgrade.

Her OSINT discovery heuristics (use these to find/verify chokepoints — see `references/framework.md` for detail):
- **Regulatory & government filings** — NIST, CHIPS Act blueprints, Dept. of Commerce / export filings ("only high-volume X foundry in America" = government-stamped criticality).
- **Customer-side signals** — a customer removing a competitor from its website / vendor list; design-in language in earnings transcripts; "sole source" / "primary source".
- **Follow who actually does the work** — the headline brand is often too big; the value sits in a small subsidiary or upstream supplier (e.g. a conglomerate's packaging/test subsidiary, an epiwafer/substrate maker, an FAU supplier).
- **Corporate-action signals** — M&A hints, new board members with M&A/IPO backgrounds, dual-listing / uplisting, private placements to fund capacity.
- **Capital-flow catalysts (non-fundamental)** — index inclusion (MSCI / Nasdaq) forces passive buying; flag it as a *real but non-fundamental* catalyst, never as proof of quality.

### Step 2 — First-principles decomposition
Value = future owner cash flows. Reason from these five levers and state each explicitly:
1. **Durability of demand** — is the end-demand structural or a fad?
2. **Supply bottleneck** — is supply genuinely scarce, and for how long?
3. **Pricing power** — can it raise price / hold margin (certification, scarcity)?
4. **Capital intensity** — how much capex/dilution to grow? (foundries are heavy; don't judge on low P/B alone — look at ROIC, utilization, margins.)
5. **Rule-of-law / geopolitics** — property rights, subsidies, jurisdiction, supply-chain-sovereignty exposure.

Name the **strongest** and **weakest** link explicitly (she always does: "strongest here, weakest there").

### Step 3 — Buffett quality gate (default `unverified`)
Answer all five. **Every field starts at `unverified`; escalate only with cited evidence** (financials, transcripts, filings — *a single tweet/post is not evidence*). Reuse the exact rubric in `references/framework.md`.
- **护城河 (moat)** — `unverified` → `weak/medium/strong`, with a one-line reason (certification, switching cost, IP, scale, regulatory barrier).
- **赚钱能力 (profitability)** — `unverified` → `improving/proven`, only when revenue / gross margin / cash-flow numbers are cited.
- **客户替换风险 (customer-replacement risk)** — `unverified` → `low/medium/high` (certification cycle, second-source availability, customer concentration).
- **Buffett 式好公司** — `not yet` by default; `yes` needs moat + profitability + sane capital allocation all above `unverified`; `no` needs disqualifying evidence.
- **当前结论** — `证据不足` / `研究地图` / `可投资结论`. Tweets alone never reach `可投资结论`.

### Step 4 — Narrative-vs-fundamentals hygiene (the discipline that keeps it honest)
Serenity is loud and her names move on sentiment; this gate stops you from mistaking price action for proof.
- **Doubt-ladder ("质疑阶梯")** — bears move the goalposts (customers → execution → market share → revenue → can the supplier scale), each gets falsified, the stock re-rates. Note the pattern, but **re-rating ≠ proven fundamentals.**
- **Media FUD** — "meme / scam / overvalued" labels are *sentiment*, not analysis; they don't create or destroy value. Equally, being right before ≠ a moat for the *next* name.
- **Capital flows & squeezes** — index inclusion, institution-vs-retail shake-outs, gamma squeezes are real *catalysts* but **positioning, not value**. Keep them out of the moat/profitability fields.
- **Track record** — a strong hit-rate is worth noting; it is **not** per-name due diligence.

### Step 5 — Classify and stay disciplined
Default output is **研究地图** (a lead worth tracking), with the specific things to verify next (next-quarter revenue, capacity-partner disclosure, customer contracts, listing timeline, capex returns). Reach **可投资结论** only after independent moat + financials + valuation + margin-of-safety work — never from posts alone.

## Hard rules
- **Never** convert a post or thesis into a buy/sell instruction.
- **Never** invent moats, margins, customer lists, valuation multiples, or links. If evidence is missing, say `unverified` / `证据不足`.
- Keep a Buffett field above `unverified` **only** with cited evidence; downgrade on doubt.
- Treat price moves, follower counts, and media takes as **noise** until tied to cash-flow evidence.
- Define jargon on first use; write for a beginner.
- If analyzing a real Serenity post, **cite the source URL**; if no URL, don't attribute.

## References
| Need | Read |
| --- | --- |
| Full method detail: 5 levers, Buffett rubric + escalation, OSINT heuristics | `references/framework.md` |
| Worked, annotated examples from the corpus (SIVE, Foxconn→Shunsin, SOI, AAOI, XFAB) | `references/exemplars.md` |
| Plain-language definitions (CPO, photonics, 800VDC, TAM, ASP, P/B, FAU, second source…) | `references/glossary.md` |

## Optional: tie into the live feed
If the user wants this applied to her *latest* posts, run the `follow-aleabito` skill's fetch first (its `follow-aleabito/scripts/analyze-mentions.js --incremental --resume` for analytics, or `follow-aleabito/scripts/fetch-updates.js` for raw posts), then apply Steps 1–5 to the returned content. The output structure here is identical to the dashboard digests in `reports/aleabito-digests/`, so results drop straight into that pipeline.

---
仅作信息跟踪，不构成投资建议。 / For information tracking only; not investment advice.
