#!/usr/bin/env python3
"""Score a stock from the local Serenity Signal Ledger SQLite snapshot."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

def default_db_candidates() -> list[Path]:
    candidates: list[Path] = []
    if os.environ.get('SERENITY_DB_PATH'):
        candidates.append(Path(os.environ['SERENITY_DB_PATH']))

    search_roots = [Path.cwd(), *Path(__file__).resolve().parents]
    seen: set[Path] = set()
    for root in search_roots:
        for relative in ('data/serenity.sqlite', 'api/instance/serenity.sqlite'):
            path = root / relative
            if path not in seen:
                candidates.append(path)
                seen.add(path)
    return candidates

TOPICS = {
    'ai_infra_neocloud': ['neocloud', 'data center', 'datacenter', 'compute', 'gpu', 'asic', 'hyperscaler', 'capex', 'ai infra', 'inference', 'training', 'cluster', 'colo'],
    'optical_photonics_networking': ['optical', 'photonics', 'transceiver', '800g', '1.6t', 'infiniband', 'ethernet', 'cpo', 'switch', 'dsp', 'coherent', 'silicon photonics', 'laser'],
    'memory_storage': ['memory', 'dram', 'hbm', 'nand', 'ddr', 'micron', 'hynix', 'samsung', 'ssd'],
    'semi_materials_packaging': ['substrate', 'inp', 'silicon carbide', 'sic', 'wafer', 'etch', 'deposition', 'metrology', 'lithography', 'packaging', 'glass core', 'foundry', 'semicap'],
    'power_grid_energy': ['power', 'electricity', 'grid', 'natural gas', 'nuclear', 'utility', 'transformer', 'substation', 'energy'],
    'robotics_space_industrial': ['robot', 'robotic', 'space', 'rocket', 'defense', 'drone', 'aerospace', 'industrial'],
    'platforms_consumer_fintech': ['reddit', 'ads', 'advertising', 'consumer', 'ecommerce', 'marketplace', 'fintech', 'stablecoin', 'brokerage'],
}

MARKERS = {
    'conviction': ['went long', 'long $', 'own ', 'position', 'positions', 'started', 'bought', 'buying', 'cost average', 'high conviction'],
    'asymmetry': ['asymmetry', 'mispriced', 'rerate', 'undervalued', 'cheap', 'ignored', 'underappreciated', 'hidden', 'overlooked'],
    'supply_chain': ['supply chain', 'bottleneck', 'scarcity', 'capacity', 'shortage', 'lead time', 'constraints', 'monopoly', 'duopoly'],
    'catalyst': ['catalyst', 'earnings', 'guidance', 'guide', 'order', 'contract', 'launch', 'ramp', 'mass production', 'nasdaq listing', 'chips act'],
    'risk': ['risk', 'dilution', 'debt', 'uncertainty', 'tariff', 'execution', 'customer concentration', 'competition', 'overhang'],
    'caution': ['short term', 'trim', 'sold', 'take profit', 'too hot', 'overpriced', 'overvalued', 'bubble', 'expensive', 'crowded'],
}


def find_db(path_arg: str | None) -> Path:
    candidates = [Path(path_arg)] if path_arg else []
    candidates += default_db_candidates()
    for path in candidates:
        if path and path.exists():
            return path
    raise SystemExit('Serenity DB not found. Pass --db or set SERENITY_DB_PATH.')


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def count_hits(texts: list[str], keywords: list[str]) -> int:
    return sum(1 for text in texts if any(k in text.lower() for k in keywords))


def engagement(row: sqlite3.Row) -> int:
    return int(row['favorite_count'] or 0) + 2 * int(row['retweet_count'] or 0) + 2 * int(row['quote_count'] or 0) + int(row['reply_count'] or 0)


def score_symbol(db_path: Path, symbol: str, now: datetime | None = None) -> dict:
    symbol = symbol.upper().lstrip('$').strip()
    now = now or datetime.now(timezone.utc)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        select t.tweet_id, t.source, t.created_at, t.text, t.url,
               t.favorite_count, t.reply_count, t.retweet_count, t.quote_count
        from mentions m join tweets t on t.tweet_id=m.tweet_id
        where upper(m.symbol)=?
        order by datetime(t.created_at) asc, t.tweet_id asc
        """,
        (symbol,),
    ).fetchall()
    total_tweets = con.execute('select count(*) from tweets').fetchone()[0]
    total_mentions = con.execute('select count(*) from mentions').fetchone()[0]
    if not rows:
        return {
            'symbol': symbol,
            'score': 20,
            'rating': 'No Serenity evidence',
            'summary': 'No cashtag mention found in the Serenity snapshot; use external fundamentals or treat as out-of-scope.',
            'components': {'serenity_signal': 0, 'thesis_quality': 0, 'catalyst': 0, 'risk_penalty': 0},
            'snapshot': {'db_path': str(db_path), 'total_tweets': total_tweets, 'total_mentions': total_mentions},
        }

    texts = [r['text'] or '' for r in rows]
    dates = [parse_dt(r['created_at']) for r in rows if parse_dt(r['created_at'])]
    first_dt, last_dt = min(dates), max(dates)
    days_since = max(0, (now - last_dt).days) if last_dt else 999
    span_days = max(0, (last_dt - first_dt).days) if first_dt and last_dt else 0
    months = len({d.strftime('%Y-%m') for d in dates})
    avg_eng = sum(engagement(r) for r in rows) / len(rows)
    max_eng = max(engagement(r) for r in rows)

    n = len(rows)
    frequency = min(18.0, math.log1p(n) / math.log1p(50) * 18.0)
    recency = 10 if days_since <= 7 else 8 if days_since <= 30 else 5 if days_since <= 90 else 3 if days_since <= 180 else 1
    persistence = min(8.0, months * 1.4 + min(span_days, 180) / 180 * 3.0)
    engagement_score = min(10.0, math.log1p(avg_eng) / math.log1p(3000) * 10.0)

    marker_hits = {name: count_hits(texts, kws) for name, kws in MARKERS.items()}
    topic_hits = {name: count_hits(texts, kws) for name, kws in TOPICS.items()}
    top_topics = sorted(topic_hits.items(), key=lambda kv: kv[1], reverse=True)

    conviction = min(15.0, marker_hits['conviction'] * 1.7 + marker_hits['asymmetry'] * 1.4 + min(n, 20) * 0.15)
    theme_fit = min(15.0, sum(1 for _, c in topic_hits.items() if c) * 1.7 + min(max(topic_hits.values() or [0]), 20) * 0.35 + marker_hits['supply_chain'] * 0.9)
    catalyst = min(12.0, marker_hits['catalyst'] * 1.5 + marker_hits['supply_chain'] * 0.5)
    risk_penalty = min(18.0, marker_hits['risk'] * 1.4 + marker_hits['caution'] * 1.8)

    raw_score = 12 + frequency + recency + persistence + engagement_score + conviction + theme_fit + catalyst - risk_penalty
    score = round(clamp(raw_score), 1)
    rating = 'High-conviction Serenity fit' if score >= 80 else 'Constructive / worth work' if score >= 65 else 'Mixed or early' if score >= 45 else 'Weak Serenity signal'

    evidence = []
    for r in sorted(rows, key=engagement, reverse=True)[:5]:
        hits = []
        lower = (r['text'] or '').lower()
        for name, kws in {**TOPICS, **MARKERS}.items():
            if any(k in lower for k in kws):
                hits.append(name)
        evidence.append({
            'tweet_id': r['tweet_id'],
            'created_at': r['created_at'],
            'source': r['source'],
            'engagement': engagement(r),
            'url': r['url'],
            'signals': hits[:6],
        })

    return {
        'symbol': symbol,
        'score': score,
        'rating': rating,
        'summary': f'{n} Serenity mentions over {months} month(s); latest mention {days_since} day(s) ago; strongest topics: ' + ', '.join(f'{k}={v}' for k, v in top_topics[:3] if v),
        'components': {
            'frequency': round(frequency, 1),
            'recency': round(recency, 1),
            'persistence': round(persistence, 1),
            'engagement': round(engagement_score, 1),
            'conviction': round(conviction, 1),
            'theme_fit': round(theme_fit, 1),
            'catalyst': round(catalyst, 1),
            'risk_penalty': round(risk_penalty, 1),
        },
        'metrics': {
            'mentions': n,
            'first_mention': first_dt.isoformat().replace('+00:00', 'Z') if first_dt else None,
            'last_mention': last_dt.isoformat().replace('+00:00', 'Z') if last_dt else None,
            'days_since_last': days_since,
            'active_months': months,
            'span_days': span_days,
            'avg_engagement': round(avg_eng, 1),
            'max_engagement': max_eng,
            'marker_hits': marker_hits,
            'topic_hits': topic_hits,
        },
        'evidence': evidence,
        'snapshot': {'db_path': str(db_path), 'total_tweets': total_tweets, 'total_mentions': total_mentions},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Score one stock from Serenity tweet/mention evidence.')
    parser.add_argument('symbol', help='Ticker/cashtag, e.g. NVDA or $NVDA')
    parser.add_argument('--db', help='Path to serenity.sqlite; defaults to SERENITY_DB_PATH or project-local snapshot')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON')
    args = parser.parse_args()
    result = score_symbol(find_db(args.db), args.symbol)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == '__main__':
    main()
