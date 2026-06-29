# Serenity Method — Full Framework

Read this when you need the detailed rubric behind the 5 steps in `SKILL.md`. Distilled from Serenity's (`@aleabitoreddit`) repeated practice across ~60 days of posts and the daily digests in `reports/aleabito-digests/`.

---

## 1. Critical-chokepoint discovery (Step 1, expanded)

Her edge is **finding the link in a value chain that the market under-prices**. The repeatable procedure:

1. **Pick a durable macro driver.** Examples she uses: AI compute growth, 800VDC data-center power, the CPO/photonics "supercycle", supply-chain sovereignty (US/EU vs China).
2. **Walk the value chain to the bottleneck.** Demand for the driver flows down until it hits a link where supply is hard to add. E.g. AI compute → data movement → optical interconnect → **laser/light source** becomes the bottleneck; or 800VDC → high-voltage power → **SiC/GaN foundry**; or CPO modules → **packaging/test + FAU (fiber-array unit)**.
3. **Identify who is designed-in there.** Look for certification, "sole source" / "primary source" language, customer reference designs.
4. **Check it's un-priced.** Compare market cap to the opportunity. She prefers small/mid caps where the bottleneck role isn't reflected in price yet.

A chokepoint is high-quality only if **all four** hold:
- (a) customers **must** have the capability,
- (b) supply **cannot** be added quickly (capacity, certification time, capital),
- (c) the company is **certified / designed-in** (not a hopeful entrant),
- (d) it is **cheap relative to the opportunity**.

Miss any one and downgrade to a watch-item.

### OSINT heuristics (how she finds & verifies)
- **Government / regulatory filings** — NIST, CHIPS Act 2 blueprints, Dept. of Commerce, export-control filings. Government language like "only high-volume SiC foundry in America" is a *criticality* stamp.
- **Customer-side moves** — a customer quietly removing a competitor from its website/vendor list; transcript phrases like "sole source", "primary source", "design-in", "qualification".
- **Follow who actually does the work** — the brand on the headline (a big conglomerate, a hyperscaler) is usually too diluted to express the bottleneck. The value is in the **subsidiary or upstream supplier** that physically does the packaging/test/substrate/light-source. Map the headline → the real worker.
- **Corporate-action signals** — M&A hints; new board members with M&A or capital-markets backgrounds; dual-listing / uplisting (more liquidity → passive inflows); private placements that fund capacity (a *de-risk* of the "can they scale?" doubt).
- **Capital-flow catalysts** — MSCI / Nasdaq index inclusion forces passive buying on a known date. Real, but **non-fundamental**; track it separately from quality.
- **Triangulate, don't trust one post.** A thesis is "supply-chain mapping done before earnings; results just confirm it" — i.e. multiple independent signals, not a single headline.

---

## 2. First-principles decomposition (Step 2, expanded)

> Value comes from future owner cash flows. Always reason from these five levers, and **name the strongest and weakest** explicitly.

1. **Durability of demand** — structural (e.g. AI data movement) vs fad. Ask what breaks the demand.
2. **Supply bottleneck** — is supply genuinely scarce? For how long? What ends the scarcity (new capacity, substitution)?
3. **Pricing power** — can it raise price / hold gross margin? Source: certification, scarcity, switching cost. (60% gross-margin *guidance* is a pricing-power *signal*, not yet proof.)
4. **Capital intensity** — capex and dilution to grow. **Do not judge a foundry on low P/B alone** — look at ROIC, utilization, gross margin, customer commitments. ATM/secondary raises = dilution overhang.
5. **Rule-of-law / geopolitics** — property rights, subsidies, jurisdiction, sovereignty exposure; for non-US/Taiwan names add liquidity, disclosure, and geopolitical risk.

The value of a *bottleneck asset* specifically rests on two things: **customers must have it**, and **others can't supply it short-term**. If both hold → pricing power + capacity premium. If capacity over-expands, customers find a substitute, or management keeps diluting → the story discounts.

---

## 3. Buffett quality gate (Step 3, the exact rubric)

Every field starts at `unverified` / `insufficient evidence`. **Escalate only with cited evidence** from financials, transcripts, or filings. *A single tweet/post is never evidence for "strong" or "proven".* Answer the fields; never leave them as open questions.

- **护城河 (moat)** — `unverified` by default. → `weak` / `medium` / `strong` only with a one-sentence reason rooted in evidence: certification, switching cost, network effect, regulatory barrier, unique IP, scale economics. Technology moats erode easily under new capacity/substitution — be conservative.
- **赚钱能力 (profitability)** — `unverified` by default. → `improving` or `proven` only when revenue, gross/operating margin, or cash-flow numbers are cited. *Guidance and pipeline ("+77% pipeline", "60% future margin") are `improving` signals at best, not `proven`.*
- **客户替换风险 (customer-replacement risk)** — `unverified` by default. → `low` / `medium` / `high` with reasons: certification cycle, switching cost, second-source availability, customer concentration. Big customers almost always cultivate a second source → rarely `low`.
- **Buffett 式好公司** — `not yet` by default. `yes` requires moat + 赚钱能力 + reasonable capital allocation all above `unverified`. `no` requires explicit disqualifying evidence.
- **当前结论** — `证据不足` by default. `研究地图` when there's a lead worth tracking. `可投资结论` requires moat + financials + valuation + margin-of-safety — **never from posts alone**.

If a local `$buffett` skill is installed (`${CODEX_HOME:-$HOME/.codex}/skills/buffett/SKILL.md`), read only the chapter you need: business/moat → `references/03-business-moat.md`; management/buybacks/dilution/capital allocation → `04-management-governance.md` + `06-valuation-capital.md`; China/regulatory/leverage/value-trap/exit → `07-risk-behavior.md`; tech/semis/AI-infra → `08-industry-playbooks.md`. If not installed, proceed with first-principles only and keep Buffett fields `unverified`.

---

## 4. Narrative-vs-fundamentals hygiene (Step 4, expanded)

These keep you from mistaking *motion* for *value*. Each is a real phenomenon in her names; each must be quarantined from the Buffett fields.

- **Doubt-ladder (质疑阶梯)** — the bear case keeps moving (customers → execution → market-share vs incumbent → revenue opportunity → can the upstream partner scale). Each rung gets falsified and the stock re-rates up a level. **Useful as a sentiment map; re-rating is not proven fundamentals.**
- **Media FUD** — "meme / scam / overvalued / speculative" are *sentiment labels*. They neither create nor destroy cash flows. (Being later proven right is satisfying but is **not** a moat for the next name.)
- **Capital flows / squeezes** — index inclusion (MSCI/Nasdaq), institution-vs-retail shake-outs (as she frames NBIS/RKLB), gamma/short squeezes. These are **positioning catalysts**, not value. Keep them out of moat/profitability.
- **Virality / track record** — follower counts and a strong hit-rate are context, not company quality. Each name still needs its own due diligence.

**Rule:** anything in this section may appear in `她的观点` / `当前结论` *as context*, but may **not** lift a Buffett field above `unverified`.

---

## 5. Output discipline (Steps 1–5 → deliverable)

- Default classification is **研究地图**, paired with an explicit **"verify next"** list (next-quarter revenue print, capacity-partner disclosure, customer contracts, listing/M&A timeline, capex returns, dilution).
- Compress to 1–3 paragraphs per name in multi-name digests; full template only for single deep-dives.
- Beginner-friendly always; define jargon on first use (`references/glossary.md`).
- Cite source URLs when grounding on real posts; never attribute without a link.
- End with: **仅作信息跟踪，不构成投资建议。**

## Hard rules (non-negotiable)
1. Never produce buy/sell instructions.
2. Never invent moat, margins, customer lists, valuation multiples, or links.
3. Distinguish `研究地图` from `可投资结论`; the latter needs moat + financials + valuation + margin-of-safety.
4. Treat price action, follower counts, and media takes as noise until tied to cash-flow evidence.
5. On missing evidence, say so. Downgrade on doubt.
