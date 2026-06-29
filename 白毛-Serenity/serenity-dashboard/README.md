# Serenity Signal Dashboard

本项目抓取 `x_curl/` 中的 X GraphQL curl，解析 `@aleabitoreddit` 的帖子、回复、订阅帖，抽取 `$SYMBOL`，写入本地 SQLite，并用 Yahoo chart 接口下载日线价格。

![Serenity dashboard screenshot](docs/assets/serenity-dashboard.png)

## 直接体验

如果你不想自己搭建本地环境，可以订阅 [@iamai_omni](https://x.com/iamai_omni/creator-subscriptions/subscribe)，然后访问 [app.k2ai.dev](https://app.k2ai.dev) 直接使用托管版。也可以扫码直接打开订阅页：

<img src="docs/assets/iamai-omni-subscribe-qr.png" alt="Subscribe to @iamai_omni QR code" width="220">

> 本项目仅用于研究和可视化，不构成投资建议。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

python3 scripts/ingest.py all --max-pages 10 --days 500 --min-mentions 3
python3 scripts/server.py --port 8787
```

打开 `http://127.0.0.1:8787`。

## 从 Chrome 复制 X curl

`scripts/ingest.py fetch-x` 会读取 `x_curl/` 目录中的浏览器请求。首次使用或登录态过期时，需要从 Chrome DevTools 重新复制。

1. 用 Chrome 登录 X，并打开 `https://x.com/aleabitoreddit`。
2. 打开 DevTools：`F12` 或 `Cmd/Ctrl + Shift + I`。
3. 切到 `Network` 面板，筛选 `Fetch/XHR`，也可以在过滤框输入 `UserTweets`。
4. 刷新页面，滚动几次，触发帖子、回复或订阅内容加载。
5. 找到以下 GraphQL 请求，右键选择 `Copy` -> `Copy as cURL`。
6. 分别保存为这些文件名：

```text
x_curl/UserTweets.curl
x_curl/UserTweetsAndReplies.curl
x_curl/UserSuperFollowTweets.curl
```

大致样例，真实内容会更长，并包含你的 cookie/token：

```bash
mkdir -p x_curl
cat > x_curl/UserTweets.curl <<'EOF_CURL'
curl 'https://x.com/i/api/graphql/.../UserTweets?variables=...&features=...' \
  -H 'authorization: Bearer ...' \
  -H 'cookie: auth_token=...; ct0=...' \
  -H 'x-csrf-token: ...' \
  -H 'x-twitter-active-user: yes'
EOF_CURL
```

注意：`x_curl/*.curl` 包含登录 cookie/token，已经被 `.gitignore` 忽略；不要提交或分享这些文件。

## 数据位置

- SQLite: `data/serenity.sqlite`
- 原始 X JSON: `data/raw/*.json`
- Dashboard: `dashboard/index.html`, `dashboard/styles.css`, `dashboard/app.js`

## 常用命令

```bash
python3 scripts/ingest.py fetch-x --max-pages 20
python3 scripts/ingest.py prices --days 700 --min-mentions 2
python3 scripts/ingest.py stats
```

注意：`x_curl/*.curl` 内的登录态可能过期；若抓取返回空或报错，重新从浏览器复制 curl 后再运行。

## Codex Skill

本仓库内置了可开源分发的 Codex skill：`skills/serenity-stock-scorer`。它会基于本地 Serenity SQLite 快照，对单个 ticker 输出 0-100 的 Serenity 语料信号分。

```bash
python3 skills/serenity-stock-scorer/scripts/score_serenity_stock.py NVDA --pretty
```

该 skill 默认查找 `data/serenity.sqlite`；如果数据库在其他位置，可以传 `--db /path/to/serenity.sqlite` 或设置 `SERENITY_DB_PATH`。

---

# Serenity Signal Dashboard (English)

This project reads X GraphQL curl commands from `x_curl/`, parses posts, replies, and premium posts from `@aleabitoreddit`, extracts `$SYMBOL` mentions, stores them in a local SQLite database, and downloads daily price bars from Yahoo's chart API.

![Serenity dashboard screenshot](docs/assets/serenity-dashboard.png)

## Try It Directly

If you do not want to set up the local project yourself, subscribe to [@iamai_omni](https://x.com/iamai_omni/creator-subscriptions/subscribe), then visit [app.k2ai.dev](https://app.k2ai.dev) to use the hosted version directly. You can also scan this QR code to open the subscription page:

<img src="docs/assets/iamai-omni-subscribe-qr.png" alt="Subscribe to @iamai_omni QR code" width="220">

> This project is for research and visualization only. It is not financial advice.

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

python3 scripts/ingest.py all --max-pages 10 --days 500 --min-mentions 3
python3 scripts/server.py --port 8787
```

Open `http://127.0.0.1:8787`.

## Copy X Requests From Chrome

`scripts/ingest.py fetch-x` reads browser-copied requests from `x_curl/`. You need to refresh these files when setting up the project or when the X session expires.

1. Log in to X with Chrome and open `https://x.com/aleabitoreddit`.
2. Open DevTools with `F12` or `Cmd/Ctrl + Shift + I`.
3. Go to `Network`, select `Fetch/XHR`, and optionally filter by `UserTweets`.
4. Refresh the page and scroll a few times so X loads posts, replies, or premium content.
5. Find the GraphQL requests below, right-click each one, then choose `Copy` -> `Copy as cURL`.
6. Save them with these exact filenames:

```text
x_curl/UserTweets.curl
x_curl/UserTweetsAndReplies.curl
x_curl/UserSuperFollowTweets.curl
```

Approximate example; the real command is longer and includes your cookie/token values:

```bash
mkdir -p x_curl
cat > x_curl/UserTweets.curl <<'EOF_CURL'
curl 'https://x.com/i/api/graphql/.../UserTweets?variables=...&features=...' \
  -H 'authorization: Bearer ...' \
  -H 'cookie: auth_token=...; ct0=...' \
  -H 'x-csrf-token: ...' \
  -H 'x-twitter-active-user: yes'
EOF_CURL
```

Warning: `x_curl/*.curl` contains login cookies/tokens and is ignored by `.gitignore`. Do not commit or share these files.

## Data Files

- SQLite: `data/serenity.sqlite`
- Raw X JSON: `data/raw/*.json`
- Dashboard: `dashboard/index.html`, `dashboard/styles.css`, `dashboard/app.js`

## Common Commands

```bash
python3 scripts/ingest.py fetch-x --max-pages 20
python3 scripts/ingest.py prices --days 700 --min-mentions 2
python3 scripts/ingest.py stats
```

If X fetching returns empty or invalid responses, copy fresh curl commands from Chrome and run the ingestion again.

## Codex Skill

This repo includes an open-source-ready Codex skill at `skills/serenity-stock-scorer`. It scores a single ticker from the local Serenity SQLite snapshot as a 0-100 Serenity corpus signal.

```bash
python3 skills/serenity-stock-scorer/scripts/score_serenity_stock.py NVDA --pretty
```

The skill looks for `data/serenity.sqlite` by default. If your database lives elsewhere, pass `--db /path/to/serenity.sqlite` or set `SERENITY_DB_PATH`.
