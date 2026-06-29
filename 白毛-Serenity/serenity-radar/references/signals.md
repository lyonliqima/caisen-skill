# Serenity Radar — Signal Math & Interpretation

How `scripts/radar.js` turns the raw mention archive into signals, how to read each, and where the data lies. Read this before trusting numbers.

## Input
`aleabito-mentions-events.csv` (one row per tweet that mentions ≥1 ticker), columns include `created_at`, `text`, `tickers` (pipe-delimited). The script counts a ticker once per tweet (deduped within a tweet). `--asof` defaults to the latest event date in the data; `--window` (default 14) sets both the recent and prior window lengths.

## The four signals

### 🔥 Heating — `velocity = recent − prior`
- `recent` = tweets mentioning the ticker in `[asof − W, asof]`; `prior` = the window before that, `[asof − 2W, asof − W]`.
- Filter: `recent ≥ 2 AND velocity > 0`. Sort by velocity, then recent volume.
- **Read as:** acceleration of her attention. A big positive Δ means she is ramping coverage *now*. `velocity` near 0 on a high-`recent` name = steady (already a core name, not newly heating).

### 🆕 New entrants — `age_days ≤ W`
- `age_days` = days from the ticker's first-ever appearance (in the whole archive) to `asof`.
- Filter: first appeared within the window AND `recent ≥ 2`.
- **Read as:** a name she just started seeding. Her pattern (§4 of patterns.md) is quiet seed → ramp, so a New entrant that is also Heating is the strongest "emerging next focus" signal.

### 🎯 Conviction watch — sustained + active + loud
- Filter: `recent ≥ 4 AND recency ≤ W/2 AND age_days ≥ W` (active for a while, still posting in the last half-window, high recent volume).
- **Read as:** her current core book — names she repeats and defends. Watch for a Conviction name *dropping out of Heating*: attention decelerating can mean the thesis is maturing toward realization/exit.

### 🔄 Theme rotation — share recent vs prior
- Buckets each tweet's tickers/keywords into themes (CPO/photonics, power semis, AI-compute/neocloud, supply-chain/policy, fintech/crypto-squeeze, Other) and compares mention counts recent vs prior window.
- **Read as:** which narrative she is rotating *into* (▲) or *out of* (▼). Pair with Heating: a heating name inside an ▲ theme is corroborated; a heating name in a ▼ theme may be idiosyncratic.

## Cross-reading (the useful combinations)
- **New entrant + Heating + theme ▲** → strongest "she's opening a new front here." (This is how `XFAB` showed up at end-May: new entrant since ~05-27, heating Δ+12, supply-chain/power-semi themes ticking up.)
- **Conviction + cooling (not in Heating)** → maturing core position; possible catalyst/realization window.
- **Heating but reply-driven** → check the source posts; conversation volume ≠ a thesis.

## Where the data lies (limits — always disclose)
- **Reply inflation.** With `--include-replies`, a name can "heat up" because she's *arguing* about it, not initiating. The script can't tell a thesis post from a defensive reply — confirm via `follow-aleabito` raw posts before calling it conviction.
- **Recency artifacts.** The newest day may be partial (fetched mid-day), slightly understating `recent`. Re-run after a fresh incremental fetch.
- **Theme buckets are coarse.** Unmapped tickers fall into "Other"; a large/ rising "Other" means the bucket lists in `radar.js`/`patterns.md` need new names, not that nothing is happening.
- **Survivorship + single-account bias** (see SKILL.md Caveats) — the whole signal set reflects one person's attention in one era. It forecasts *her interest*, never price or correctness.

## Tuning
- `--window 7` for a fast, twitchy read (good right after a catalyst); `--window 21` to smooth out reply noise.
- `--asof <past date>` to *backtest* the radar: pick a date, see what it would have surfaced, then check what she actually ramped next. This is the honest way to judge whether the radar adds signal before relying on it.
