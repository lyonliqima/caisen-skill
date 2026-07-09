#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import logging
import sqlite3
from pathlib import Path

from tradingview_scraper.symbols.stream import Streamer

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "serenity.sqlite"


def fetch_ohlc(exchange: str, tv_symbol: str, timeframe: str, candles: int):
    logging.disable(logging.CRITICAL)
    streamer = Streamer(export_result=False)
    result = streamer.stream(
        exchange=exchange,
        symbol=tv_symbol,
        timeframe=timeframe,
        numb_price_candles=candles,
    )
    if isinstance(result, dict):
        return result.get("ohlc") or []

    # export_result=False returns a generator; keep this path for package API changes.
    for packet in result:
        data = streamer._extract_ohlc_from_stream(packet)
        if data:
            return data
    return []


def save_prices(rows, db_symbol: str):
    con = sqlite3.connect(DB_PATH)
    inserted = 0
    for row in rows:
        date = dt.datetime.fromtimestamp(row["timestamp"], dt.timezone.utc).date().isoformat()
        con.execute(
            "insert or replace into prices(symbol, date, close, volume) values (?, ?, ?, ?)",
            (db_symbol.upper(), date, float(row["close"]), int(row.get("volume") or 0)),
        )
        inserted += 1
    con.commit()
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Fetch TradingView OHLC candles into the local SQLite price table.")
    parser.add_argument("--exchange", required=True, help="TradingView exchange, e.g. OTC")
    parser.add_argument("--tv-symbol", required=True, help="TradingView symbol, e.g. SIVEF")
    parser.add_argument("--db-symbol", required=True, help="Local dashboard symbol, e.g. SIVE")
    parser.add_argument("--timeframe", default="1d", help="1d, 1w, 1m, etc.; default: 1d")
    parser.add_argument("--candles", type=int, default=200)
    parser.add_argument("--also-save-tv-symbol", action="store_true")
    args = parser.parse_args()

    rows = fetch_ohlc(args.exchange.upper(), args.tv_symbol.upper(), args.timeframe, args.candles)
    if not rows:
        raise SystemExit("no TradingView OHLC rows returned")

    inserted = save_prices(rows, args.db_symbol)
    if args.also_save_tv_symbol and args.tv_symbol.upper() != args.db_symbol.upper():
        save_prices(rows, args.tv_symbol)

    first = dt.datetime.fromtimestamp(rows[0]["timestamp"], dt.timezone.utc).date().isoformat()
    last = dt.datetime.fromtimestamp(rows[-1]["timestamp"], dt.timezone.utc).date().isoformat()
    print(json.dumps({
        "tv_symbol": f"{args.exchange.upper()}:{args.tv_symbol.upper()}",
        "db_symbol": args.db_symbol.upper(),
        "rows": inserted,
        "first": first,
        "last": last,
        "last_close": rows[-1]["close"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
