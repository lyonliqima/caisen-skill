#!/usr/bin/env python3
import argparse
import json
import sqlite3
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "serenity.sqlite"
STATIC_DIR = ROOT / "dashboard"


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def one(con, sql, params=()):
    row = con.execute(sql, params).fetchone()
    return dict(row) if row else {}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            try:
                payload = self.route_api(parsed.path, parse_qs(parsed.query))
                self.send_json(payload)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=500)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def route_api(self, path, query):
        if not DB_PATH.exists():
            return {"error": f"database not found: {DB_PATH}"}
        con = db()
        if path == "/api/summary":
            return summary(con)
        if path == "/api/feed":
            limit = int((query.get("limit") or [80])[0])
            return {"items": [dict(r) for r in con.execute(
                """select m.symbol, m.mentioned_at, m.text, t.url, t.favorite_count, t.reply_count, t.source
                       from mentions m join tweets t on t.tweet_id=m.tweet_id
                       order by m.mentioned_at desc limit ?""", (limit,))]}
        if path.startswith("/api/symbol/"):
            symbol = unquote(path.rsplit("/", 1)[-1]).upper()
            return symbol_payload(con, symbol)
        return {"error": "unknown api"}


def summary(con):
    stats = one(con, """
        select (select count(*) from tweets) tweets,
               (select count(*) from mentions) mentions,
               (select count(distinct symbol) from mentions) symbols,
               (select max(mentioned_at) from mentions) latest_mention,
               (select count(distinct symbol) from prices) priced_symbols
    """)
    symbols = []
    for r in con.execute("""
        select m.symbol, count(*) mention_count, max(m.mentioned_at) latest_mention,
               min(m.mentioned_at) first_mention,
               (select close from prices p where p.symbol=m.symbol order by date desc limit 1) last_close,
               (select date from prices p where p.symbol=m.symbol order by date desc limit 1) last_price_date,
               (select count(*) from prices p where p.symbol=m.symbol) price_bars
        from mentions m
        group by m.symbol
        order by mention_count desc, latest_mention desc
    """):
        d = dict(r)
        d["has_prices"] = bool(d.pop("price_bars"))
        symbols.append(d)
    return {"stats": stats, "symbols": symbols}


def symbol_payload(con, symbol):
    prices = [dict(r) for r in con.execute(
        "select date, close, volume from prices where symbol=? order by date", (symbol,)
    )]
    mentions = [dict(r) for r in con.execute(
        """select m.symbol, m.mentioned_at, m.text, t.url, t.favorite_count, t.reply_count, t.retweet_count, t.source
               from mentions m join tweets t on t.tweet_id=m.tweet_id
               where m.symbol=? order by m.mentioned_at""", (symbol,)
    )]
    neighbors = [dict(r) for r in con.execute(
        """select m2.symbol, count(*) count
               from mentions m1 join mentions m2 on m1.tweet_id=m2.tweet_id and m1.symbol<>m2.symbol
               where m1.symbol=? group by m2.symbol order by count desc, m2.symbol limit 20""", (symbol,)
    )]
    return {"symbol": symbol, "prices": prices, "mentions": mentions, "neighbors": neighbors}


def main():
    ap = argparse.ArgumentParser(description="Serve the Serenity dashboard")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"dashboard: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
