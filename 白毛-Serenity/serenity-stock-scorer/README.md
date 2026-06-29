# Serenity Stock Scorer

A Codex skill and small CLI for scoring stocks from a local Serenity Signal Ledger SQLite snapshot.

The skill turns Serenity/X cashtag mention history into a 0-100 signal score using mention frequency, recency, persistence, engagement, thesis fit, catalyst markers, and risk/caution markers.

## Contents

- `SKILL.md` - Codex skill instructions.
- `scripts/score_serenity_stock.py` - deterministic scorer CLI.
- `references/serenity-framework.md` - distilled scoring rubric and rating bands.
- `agents/openai.yaml` - optional Codex UI metadata.

## Usage

Provide a Serenity SQLite snapshot with the expected `tweets` and `mentions` tables, then run:

```bash
python skills/serenity-stock-scorer/scripts/score_serenity_stock.py MSFT --pretty
```

By default the CLI searches upward from the current directory and script location for `data/serenity.sqlite` or `api/instance/serenity.sqlite`. You can also pass a database path explicitly:

```bash
python skills/serenity-stock-scorer/scripts/score_serenity_stock.py MSFT --db /path/to/serenity.sqlite --pretty
```

Or set:

```bash
export SERENITY_DB_PATH=/path/to/serenity.sqlite
python skills/serenity-stock-scorer/scripts/score_serenity_stock.py MSFT --pretty
```

The CLI prints JSON with:

- `score` and `rating`
- component scores
- mention metrics
- top evidence tweet IDs/URLs

## Notes

This repository does not include the underlying Serenity tweet database. The framework is derived from aggregate patterns in a private local snapshot and is intended as a research signal, not financial advice.
