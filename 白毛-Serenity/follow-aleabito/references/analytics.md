# Follow AleaBito Analytics Reference

## Goal

Maintain a cumulative local data layer for `@aleabitoreddit` mention analytics. The first 60-day run is only a backfill seed. After that, the dataset grows permanently by appending new tweet/reply/quote events.

## Files

- `aleabito-mentions-events.csv`: event-level source of truth.
- `aleabito-stock-mentions-cumulative.csv`: cumulative ticker leaderboard.
- `aleabito-stock-mentions-daily.csv`: daily ticker counts for charts.
- `aleabito-mentions.meta.json`: status, output paths, page count, and API rate-limit metadata.

## Counting Rules

- `mentioned_posts` counts unique events mentioning a ticker.
- `raw_occurrences` counts cashtag occurrences inside event text.
- Replies count because this account often puts high-signal explanations in replies.
- Retweets are excluded.
- `primary_theme` and `research_priority` are deterministic labels for website filtering, not investment ratings.

## API Cost Rules

- Prefer `--incremental --resume` after the first backfill.
- Use a 24-48 hour overlap window so late or duplicated pages do not cause gaps.
- Use `--max-pages` in tests.
- Use `--rebuild-only` when changing classification logic or output formatting; it rebuilds summary/daily files from the existing events CSV without calling X.
- Use `--state /tmp/some-state.json` in tests so temporary runs do not overwrite the production analytics state.
- Do not rerun a full 60-day backfill unless the event CSV is missing or corrupted.
- If the API fails, keep the previous CSVs and update only `.meta.json` with the error.
