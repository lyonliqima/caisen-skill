---
name: serenity-radar
description: Use @aleabitoreddit ("Serenity")'s full mention archive (built by the follow-aleabito skill) to anticipate where her attention is moving and generate candidate ideas in her style. Two modes — (1) RADAR reads the live mention data for attention momentum (which tickers she is heating up on, new entrants, conviction core, theme rotation) via scripts/radar.js; (2) GENERATOR applies her empirically-mined patterns (theme-rotation logic, selection signature, catalyst playbook) to propose her likely next focus. Every candidate is gated through the serenity-method checklist. This is a CANDIDATE GENERATOR + CHECKLIST, never an oracle or buy/sell signal. Trigger on "what is Serenity ramping on / her next pick / aleabito radar / predict her next move / generate ideas like her / 她下一个可能看什么".
---

# Serenity Radar

A data-driven companion to `serenity-method`. Where `serenity-method` teaches **how she analyzes**, this skill uses her **actual 11-month archive** (2025-07-02 → present, ~6,120 posts / 750 tickers) to estimate **where her attention is going** and to **generate candidates the way she would**.

> **What this is NOT.** Not a predictor, not a buy/sell signal, not "she will pump X next." It is a *candidate generator + checklist*. A single account is fragile; virality ≠ correctness; her archive has survivorship bias (winners get re-cited, losers fade). Read the **Caveats** section before using output. Always end with: 仅作信息跟踪，不构成投资建议。

## Prerequisites
- The mention archive must exist (the `follow-aleabito` skill produces it). Default path: `$FOLLOW_ALEABITO_REPORTS_DIR/aleabito-mentions-events.csv` (else the workspace `reports/`).
- Keep it current with `follow-aleabito`'s incremental fetch (`analyze-mentions.js --incremental --resume`) before running radar, so signals reflect the latest days.
- For the analytical gate, use the local `serenity-method` skill.

## Mode 1 — RADAR (data-driven, run this first)
Run the signal extractor:
```bash
FOLLOW_ALEABITO_REPORTS_DIR="<reports dir>" node skills/serenity-radar/scripts/radar.js --window 14 --top 20
# add --json for machine-readable output; --asof YYYY-MM-DD to evaluate a past date; --window 7 for a tighter read
```
It prints four signal blocks (see `references/signals.md` for the exact math):
- **🔥 Heating** — tickers whose mention count is *accelerating* (recent window vs prior window). This is the core "she's ramping attention here" signal.
- **🆕 New entrants** — tickers that first appeared within the window. Candidate *next focus* — she often seeds a name quietly, then ramps.
- **🎯 Conviction watch** — high recent volume + sustained + still active. Her *core book* right now (defended, repeated).
- **🔄 Theme rotation** — theme mention-share recent vs prior. Tells you which narrative she is rotating *into* / *out of*.

**How to read it:** a name that is *both* a New entrant *and* Heating, in a theme that is *rotating up*, is the strongest "emerging focus" signal. A Conviction-watch name that is *cooling* (falling out of Heating) may be maturing toward exit/realization. Cross-check a heating name's recent posts (via `follow-aleabito`) to confirm it is a genuine thesis, not a one-off reply.

## Mode 2 — GENERATOR (pattern-driven, for "her likely next move")
When the user wants ideas she *hasn't surfaced yet*, apply her empirical patterns (full detail in `references/patterns.md`). Her behavior is remarkably consistent; the three levers that predict her next focus:
1. **Move UP the supply chain** — from today's hot end-product to the upstream chokepoint that isn't priced. (She went interconnect → laser → InP substrate → **red phosphorus**.) Ask: *what is the bottleneck of the current bottleneck?*
2. **Move EARLIER in the cycle** — front-run a dated catalyst (ETF approval, index inclusion, earnings read-through, government filing, M&A). Ask: *what catalyst is ~1-2 quarters out that the market hasn't mapped?*
3. **Move SMALLER / less-covered** — toward a sub-$3B, designed-in, often FUD-labelled name. Ask: *who actually does the work (the subsidiary / upstream supplier), not the headline brand?*

Generate 3-5 candidates by running these levers off the current Heating/Conviction themes, then gate each.

## The gate (mandatory for every candidate)
A radar signal or generated idea is **only a lead**. Before presenting it as a thesis, run it through `serenity-method` (Steps 1-5: chokepoint test → first principles → Buffett quality gate (default `unverified`) → narrative-vs-fundamentals hygiene → classify as `研究地图` vs `可投资结论`). Output should show the candidate **and** its gate result. Never promote a signal to a recommendation.

## Output shape
**Language / 语言:** respond in the user's language — 中文 by default, English on request. Bilingual labels below.

For each surfaced candidate, give:
1. **信号 · Signal** — why it surfaced (heating Δ, new entrant since X, conviction core, theme rotating up).
2. **她的角度(推测) · Her angle (inferred)** — the likely Serenity-style thesis (chokepoint / catalyst / un-priced), clearly marked as inference.
3. **闸门结果 · Gate result** — the `serenity-method` verdict (almost always `研究地图 / research-map`, with the specific things to verify).
4. **可信度 · Confidence** — high/medium/low, with the caveat that drove it down (one-off reply, no fundamentals, single-account risk).

## Caveats (read before trusting any output)
- **Candidate generator, not oracle.** Attention momentum predicts *her interest*, not price or correctness.
- **Survivorship bias.** Her archive over-weights names that worked; the radar inherits it. Treat "she ramped X and it ran" as *not* evidence X will repeat.
- **Single-account fragility.** One person, one style, one era (a mostly-AI-up-cycle, though it does include the Nov-2025 drawdown where IREN −38% / NBIS −35% — proof she is *not* infallible and holds through pain).
- **Reply noise.** A heating name driven by replies (conversation) ≠ a conviction post. Confirm with the source.
- **No front-running.** This surfaces public attention patterns for research; do not use it to trade ahead of or against anyone, and never emit buy/sell calls.

## References
| Need | Read |
| --- | --- |
| Her empirical patterns: theme-rotation logic, selection signature, catalyst playbook, conviction tells, track record | `references/patterns.md` |
| Exact radar math + how to read each signal + data caveats | `references/signals.md` |
| The analytical gate every candidate must pass | the `serenity-method` skill |
| Keeping the archive current / pulling raw posts | the `follow-aleabito` skill |

---
仅作信息跟踪，不构成投资建议。 / For information tracking only; not investment advice.
