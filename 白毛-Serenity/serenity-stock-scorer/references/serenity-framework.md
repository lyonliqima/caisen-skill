# Serenity Stock Scoring Framework

This reference distills the local Serenity Signal Ledger snapshot (`617` tweets, `1,561` cashtag mentions, `305` symbols, `2025-11-17` to `2026-05-29`). It is derived from aggregate patterns, not a dump of tweet text.

## Corpus Patterns

- Sources: `posts=249`, `premium=188`, `replies=180`.
- Most-mentioned symbols in this snapshot: `SIVE`, `AXTI`, `LITE`, `NVDA`, `AAOI`, `SOI`, `TSM`, `COHR`, `INTC`, `TSEM`, `JBL`, `RDDT`, `SNDK`, `EWY`, `POET`, `MRVL`, `NBIS`, `IQE`, `AMZN`, `AVGO`, `MSFT`, `MU`, `GOOGL`, `LPK`, `AEHR`.
- Dominant thesis clusters: optical/photonics/networking; AI infrastructure and neocloud; memory/storage; semiconductor materials/substrates/packaging; power/grid/energy; robotics/space/industrial; selected platform/consumer/fintech ideas.
- Common alpha pattern: second-order supply-chain beneficiaries rather than obvious mega-cap winners; look for bottlenecks, scarce suppliers, Western/US reshoring, capacity constraints, and unloved small/mid caps tied to AI capex.
- Common writing stance: explicit positions/longs are frequent; Serenity favors asymmetric setups where market structure, supply chain mapping, or investor neglect may create rerating potential.
- Common risk stance: near-term overextension, crowdedness, dilution/debt, tariff/geopolitical exposure, customer concentration, and execution risk can override otherwise strong themes.

## 0-100 Scoring Rubric

Use the script first when the SQLite snapshot is available, then layer qualitative judgment. If the user gives fundamentals or recent price action, incorporate them as overrides rather than blindly trusting mention counts.

### Serenity Signal Strength: 0-35

- Mention frequency and persistence: repeated mentions across weeks/months score higher than a single viral mention.
- Recency: latest mentions within 7-30 days are materially stronger than stale mentions.
- Engagement: higher replies/likes/reposts/quotes imply more market attention, but do not substitute for thesis quality.
- Source quality: standalone posts and premium posts usually carry more weight than casual replies; replies can still matter when they clarify thesis or risk.

### Thesis Fit: 0-30

- Award high scores for direct fit with Serenity's recurring themes: optical/photonics/CPO, AI data centers/neoclouds, memory/HBM/NAND, semicap/materials/substrates, power/grid, robotics/space/industrial.
- Add weight for second-order or non-consensus positioning: component suppliers, substrate vendors, test equipment, packaging, power semis, regional supply chain plays.
- Prefer evidence of structural demand, capacity bottlenecks, monopoly/duopoly dynamics, or supply-chain indispensability.
- Penalize if the stock is only tangentially related to the theme or is just a broad mega-cap proxy with no unique leverage.

### Catalyst And Timing: 0-15

- Positive catalysts: earnings/guidance inflection, order ramp, mass production, listing/up-listing, customer win, CHIPS/reshoring funding, capacity expansion, product cycle, AI capex acceleration.
- Higher score when catalyst timing is explicit and close enough to matter, but not already fully priced.
- Lower score when thesis depends on vague multi-year hope without confirming milestones.

### Valuation / Asymmetry: 0-15

- Reward underappreciated revenue leverage, low expectations, valuation disconnects, rerating setups, and credible paths to multi-year upside.
- Treat small-cap illiquidity as both opportunity and risk.
- Penalize if the idea looks crowded, priced for perfection, or requires heroic assumptions.

### Risk Penalty: 0 to -25

Subtract for: stretched short-term chart, heavy dilution/debt, weak balance sheet, execution uncertainty, customer concentration, policy/geopolitical/tariff risk, commoditization, supply constraints that hurt the company rather than help it, or Serenity expressing caution/selling/trimming.

## Rating Bands

- `85-100`: Exceptional Serenity-style idea; repeated, recent, high-conviction evidence plus clear asymmetry and catalysts.
- `70-84`: Strong candidate; meaningful Serenity signal and thesis fit, with manageable risks.
- `55-69`: Watchlist / more work needed; promising theme but incomplete evidence, valuation uncertainty, or stale mentions.
- `35-54`: Weak or mixed; few mentions, indirect thesis, or clear risks.
- `0-34`: No Serenity support or thesis conflicts with the framework.

## Output Format

Return a concise investment-style note:

1. `Score: N/100` and one-line rating.
2. `Why Serenity would care`: 2-4 bullets tied to corpus themes.
3. `Evidence`: mention count, first/latest mention, top topics, and 2-4 tweet IDs/URLs if available.
4. `Risks / score caps`: the strongest reasons not to over-score.
5. `What would move the score`: concrete confirmations or invalidations.

Do not present the score as financial advice. State when the result is based only on Serenity tweet evidence and lacks current market/fundamental verification.
