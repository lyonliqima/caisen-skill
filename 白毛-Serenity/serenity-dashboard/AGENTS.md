# AGENTS.md

## Project Overview

This project analyzes X posts from `https://x.com/aleabitoreddit` and builds a local dashboard for tracking AI/semi-related stock symbols mentioned by the account.

The pipeline:

1. Uses curl commands in `x_curl/` to fetch X GraphQL timelines.
2. Stores raw X JSON responses in `data/raw/`.
3. Normalizes tweets, extracted symbols, mention timestamps, and prices into `data/serenity.sqlite`.
4. Serves a local dashboard that visualizes price curves and annotates mention times/content.

## Current Stack

- Python scripts for ingestion and local API server.
- SQLite for local storage.
- Vanilla HTML/CSS/JS dashboard.
- Chart.js for price visualization.
- Yahoo chart API for historical prices.

Key files:

- `scripts/ingest.py` - fetches X data, extracts symbols, downloads prices, writes SQLite.
- `scripts/server.py` - serves dashboard static files and JSON API.
- `dashboard/index.html` - dashboard page.
- `dashboard/styles.css` - dashboard visual design.
- `dashboard/app.js` - dashboard data fetching and chart logic.
- `data/serenity.sqlite` - local SQLite database.
- `data/raw/*.json` - raw downloaded X responses.
- `x_curl/*.curl` - browser-copied X GraphQL curl commands.

## Common Commands

Run the dashboard:

```bash
python3 scripts/server.py --port 8787
```

Open:

```text
http://127.0.0.1:8787
```

Fetch X posts/replies/premium posts and update prices:

```bash
python3 scripts/ingest.py all --max-pages 20 --days 700 --min-mentions 2
```

Fetch only X data:

```bash
python3 scripts/ingest.py fetch-x --max-pages 20
```

Fetch only prices:

```bash
python3 scripts/ingest.py prices --days 700 --min-mentions 2
```

Show local stats:

```bash
python3 scripts/ingest.py stats
```

Validate Python syntax:

```bash
python3 -m py_compile scripts/ingest.py scripts/server.py
```

## Development Notes

- Prefer keeping the app local-first. Do not introduce cloud services unless explicitly requested.
- Preserve `data/serenity.sqlite` and `data/raw/` unless the user explicitly asks to regenerate or clean data.
- The `x_curl/*.curl` files contain session cookies copied from a browser. They may expire. If X fetching returns empty/non-JSON responses, ask the user to refresh the curl commands from the browser.
- Avoid committing or exposing X cookies/tokens outside the local project.
- If adding dependencies, prefer lightweight options and document install/run steps in `README.md`.
- If migrating to a JS full-stack framework, SvelteKit or Next.js are reasonable defaults; SvelteKit is preferred for a compact dashboard-focused app.

## Data Model

SQLite tables currently used:

- `raw_pages` - raw X API pages with source/cursor/body.
- `tweets` - normalized tweets authored by `aleabitoreddit`.
- `mentions` - extracted symbols, mention timestamps, source tweet text.
- `prices` - daily close/volume per symbol.

Symbol extraction uses X `entities.symbols`, long-form note tweet entities, and `$SYMBOL` text matching. Some symbols may be unavailable from Yahoo or require exchange suffixes.

## UI Direction

The dashboard should feel like a signal-trading intelligence terminal, not a generic SaaS admin page.

Existing direction:

- Editorial/market-ledger aesthetic.
- Warm paper background with grid texture.
- Bold display typography.
- Green price lines and orange mention markers.
- Dense but readable symbol tape and latest-opinion feed.

When changing the frontend:

- Keep desktop and mobile layouts working.
- Keep mention markers visible on price charts.
- Keep latest tweet/opinion content accessible from the dashboard.
- Avoid generic white-card dashboard styling unless requested.

## Safety

This project is for research and visualization only. Do not present extracted mentions as financial advice. If adding user-facing copy, prefer neutral language such as "mentions", "views", "signals", or "opinion tape" rather than "buy/sell recommendations".
