#!/usr/bin/env python3
"""Backfill the last ten completed weeks using observed historical closes."""
import json
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from difflib import SequenceMatcher
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from update_data import MARKETS, ROOT, quote_key

DATA = ROOT / "data"
CURRENT = json.loads((DATA / "weekly.json").read_text())
LATEST = date.fromisoformat(CURRENT["weekEnding"])
WEEKS = [(LATEST - timedelta(weeks=i)).isoformat() for i in range(10)]
START = (LATEST - timedelta(weeks=11)).isoformat()
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*"}
CG_LOCK = threading.Lock()
CG_NEXT = 0.0
PAPRIKA_LOCK = threading.Lock()
PAPRIKA_NEXT = 0.0
PAPRIKA_IDS = {}
STOCK_LOCK = threading.Lock()
STOCK_NEXT = 0.0
CACHE = Path('/tmp/movers-history-cache')
CACHE.mkdir(exist_ok=True)


def get_json(url, throttle=False, stock=False, paprika=False):
    global CG_NEXT, STOCK_NEXT, PAPRIKA_NEXT
    for attempt in range(5):
        if throttle:
            with CG_LOCK:
                now = time.monotonic()
                delay = max(0, CG_NEXT - now)
                CG_NEXT = max(now, CG_NEXT) + 3.0
            if delay:
                time.sleep(delay)
        if stock:
            with STOCK_LOCK:
                now = time.monotonic()
                delay = max(0, STOCK_NEXT - now)
                STOCK_NEXT = max(now, STOCK_NEXT) + 0.3
            if delay:
                time.sleep(delay)
        if paprika:
            with PAPRIKA_LOCK:
                now = time.monotonic()
                delay = max(0, PAPRIKA_NEXT - now)
                PAPRIKA_NEXT = max(now, PAPRIKA_NEXT) + 1.0
            if delay:
                time.sleep(delay)
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if paprika and exc.code in (402, 403, 404):
                return None
            if attempt == 4:
                print(f"Missing history: {url.split('?')[0]} ({exc})", flush=True)
                return None
            time.sleep(min(20, 2 ** attempt))
        except Exception as exc:
            if attempt == 4:
                print(f"Missing history: {url.split('?')[0]} ({exc})", flush=True)
                return None
            time.sleep(min(20, 2 ** attempt))


def stock_history(symbol):
    cache_path = CACHE / ('stock-' + symbol.replace(':', '-') + '.json')
    if cache_path.exists():
        return symbol, json.loads(cache_path.read_text())
    exchange, ticker = symbol.split(":", 1)
    closes = {}
    key = quote_key(symbol)
    if exchange in ("NASDAQ", "NYSE", "AMEX"):
        key += {"NASDAQ": ".OQ", "NYSE": ".N", "AMEX": ".AM"}[exchange]
    url = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param=" + f"{key},week,,,16"
    payload = get_json(url, stock=True)
    if isinstance(payload, dict):
        payload_data = payload.get("data")
        item = payload_data.get(key, {}) if isinstance(payload_data, dict) else {}
        bars = item.get("week") or []
        for bar in bars:
            try:
                day = date.fromisoformat(bar[0])
                friday = day + timedelta(days=4 - day.weekday())
                closes[friday.isoformat()] = float(bar[2])
            except (ValueError, IndexError, TypeError):
                pass
    if closes:
        cache_path.write_text(json.dumps(closes))
    return symbol, closes


def coin_history(coin_id):
    paprika_id = PAPRIKA_IDS.get(coin_id)
    cache_path = CACHE / ('coin-' + coin_id + '.json')
    if cache_path.exists() and paprika_id:
        return coin_id, json.loads(cache_path.read_text())
    if paprika_id:
        url = f"https://api.coinpaprika.com/v1/tickers/{urllib.parse.quote(paprika_id)}/historical?start={START}&end={(LATEST + timedelta(days=1)).isoformat()}&interval=24h"
        payload = get_json(url, paprika=True)
    else:
        payload = None
    if isinstance(payload, list) and payload:
        prices = {datetime.fromisoformat(point['timestamp'].replace('Z', '+00:00')).date(): point['price'] for point in payload}
        caps = {datetime.fromisoformat(point['timestamp'].replace('Z', '+00:00')).date(): point['market_cap'] for point in payload}
    else:
        url = f"https://api.coingecko.com/api/v3/coins/{urllib.parse.quote(coin_id)}/market_chart?vs_currency=usd&days=90&interval=daily"
        payload = get_json(url, throttle=True)
        if not isinstance(payload, dict):
            return coin_id, {}
        prices = {datetime.fromtimestamp(ms / 1000, timezone.utc).date(): price for ms, price in payload.get('prices', [])}
        caps = {datetime.fromtimestamp(ms / 1000, timezone.utc).date(): cap for ms, cap in payload.get('market_caps', [])}
    result = {}
    for week in WEEKS + [(LATEST - timedelta(weeks=10)).isoformat()]:
        # CoinGecko's Saturday 00:00 UTC sample marks Friday's UTC close.
        day = date.fromisoformat(week) + timedelta(days=1)
        if day in prices and day in caps and prices[day] > 0 and caps[day] > 0:
            result[week] = (prices[day], caps[day])
    if result:
        cache_path.write_text(json.dumps(result))
    return coin_id, result


def universe(market):
    return {row["symbol"]: row for group in CURRENT["markets"][market]
            for side in ("gainers", "losers") for row in group[side]}


def paprika_ids(coins):
    cache_path = CACHE / 'paprika-coins.json'
    if cache_path.exists():
        catalog = json.loads(cache_path.read_text())
    else:
        catalog = get_json('https://api.coinpaprika.com/v1/coins')
        cache_path.write_text(json.dumps(catalog))
    by_symbol = defaultdict(list)
    for coin in catalog:
        if coin.get('is_active'):
            by_symbol[coin['symbol'].upper()].append(coin)
    found = {}
    for coin_id, row in coins.items():
        candidates = by_symbol[row['ticker']]
        exact = [c for c in candidates if c['name'].casefold() == row['name'].casefold()]
        if exact:
            found[coin_id] = min(exact, key=lambda c: c.get('rank') or 999999)['id']
        elif len(candidates) == 1 and SequenceMatcher(None, candidates[0]['name'].casefold(), row['name'].casefold()).ratio() >= 0.55:
            found[coin_id] = candidates[0]['id']
    return found


def build_group(market, rows, histories, week, previous, lower, upper):
    selected = []
    for row in rows.values():
        history = histories.get(row["symbol"], {})
        if week not in history or previous not in history:
            continue
        price, cap = history[week] if market == "crypto" else (history[week], row["cap"])
        old_price = history[previous][0] if market == "crypto" else history[previous]
        if not old_price or not price or cap < lower or (upper is not None and cap >= upper):
            continue
        change = (price / old_price - 1) * 100
        item = dict(row)
        item.update(price=price, change=round(change, 3), cap=round(cap))
        selected.append(item)
    return {"min": lower, "max": upper,
            "gainers": sorted((r for r in selected if r["change"] > 0), key=lambda r: -r["change"])[:25],
            "losers": sorted((r for r in selected if r["change"] < 0), key=lambda r: r["change"])[:25],
            "universeCount": len(selected)}


def main():
    global PAPRIKA_IDS
    stocks = {}
    coins = universe("crypto")
    for market in ("a", "hk", "us", "gold"):
        stocks.update(universe(market))
    print(f"Fetching {len(stocks)} equity histories", flush=True)
    with ThreadPoolExecutor(max_workers=12) as pool:
        stock_data = dict(pool.map(stock_history, stocks))
    print(f"Equity histories available: {sum(bool(v) for v in stock_data.values())}/{len(stocks)}", flush=True)
    print(f"Fetching {len(coins)} crypto histories", flush=True)
    PAPRIKA_IDS = paprika_ids(coins)
    print(f"CoinPaprika matches: {len(PAPRIKA_IDS)}/{len(coins)}", flush=True)
    coin_data = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(coin_history, coin_id): coin_id for coin_id in sorted(coins, key=lambda key: coins[key]['cap'], reverse=True)}
        for i, future in enumerate(as_completed(futures), 1):
            key, bars = future.result()
            coin_data[key] = bars
            if i % 25 == 0:
                print(f"Crypto histories: {i}/{len(coins)}", flush=True)
    print(f"Crypto histories available: {sum(bool(v) for v in coin_data.values())}/{len(coins)}", flush=True)

    history_dir = DATA / "history"
    history_dir.mkdir(exist_ok=True)
    for i, week in enumerate(WEEKS[1:], 1):
        previous = (date.fromisoformat(week) - timedelta(weeks=1)).isoformat()
        snapshot = {"updatedAt": datetime.now(timezone.utc).isoformat(), "weekEnding": week,
                    "source": "Tencent weekly closes / CoinPaprika and CoinGecko daily prices and caps",
                    "backfilled": True, "universeAsOf": CURRENT["weekEnding"], "markets": {}}
        for market in ("a", "hk", "us", "gold", "crypto"):
            rows = universe(market)
            current_groups = CURRENT["markets"][market]
            histories = coin_data if market == "crypto" else stock_data
            snapshot["markets"][market] = [build_group(market, rows, histories, week, previous, g["min"], g["max"])
                                           for g in current_groups]
        (history_dir / f"{week}.json").write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(week, {m: sum(g["universeCount"] for g in snapshot["markets"][m]) for m in snapshot["markets"]}, flush=True)
    (history_dir / "index.json").write_text(json.dumps(WEEKS, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
