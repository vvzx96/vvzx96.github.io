#!/usr/bin/env python3
"""Build a weekly, reproducible market snapshot for the static dashboard."""
import json
import re
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ["NEM", "AEM", "KGC", "WPM", "FNV", "AU", "HMY", "GFI", "IAG", "BTG", "EGO", "CDE", "HL", "OR", "EQX", "AGI", "RGLD", "NGD", "SAND", "SSRM", "DRD", "SA", "MUX", "GAU"]
STABLECOINS = {"tether", "usd-coin", "dai", "usds", "ethena-usde", "first-digital-usd", "paypal-usd", "usdd", "true-usd", "frax", "world-liberty-financial-usd"}
MARKETS = {
    "a": {"scanner": "china", "bands": [(0, 5e9), (5e9, 10e9), (10e9, 50e9), (50e9, 200e9), (200e9, None)]},
    "hk": {"scanner": "hongkong", "bands": [(0, 2e9), (2e9, 10e9), (10e9, 100e9), (100e9, 500e9), (500e9, None)]},
    "us": {"scanner": "america", "bands": [(0, 1e9), (1e9, 2e9), (2e9, 10e9), (10e9, 50e9), (50e9, None)]},
    "gold": {"scanner": "america", "bands": [(0, 2e9), (2e9, 5e9), (5e9, 20e9), (20e9, 50e9), (50e9, None)]},
}
COLUMNS = ["name", "description", "close", "change|1W", "market_cap_basic", "volume", "currency"]


def fetch(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0 WeeklyMovers/1.0", "Content-Type": "application/json", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def scan(market, lower, upper, direction):
    filters = [
        {"left": "type", "operation": "equal", "right": "stock"},
        {"left": "market_cap_basic", "operation": "greater", "right": lower},
        {"left": "volume", "operation": "greater", "right": 100000},
        {"left": "close", "operation": "greater", "right": 1},
    ]
    if upper is not None:
        filters.append({"left": "market_cap_basic", "operation": "less", "right": upper})
    if market == "gold":
        filters.append({"left": "name", "operation": "in_range", "right": GOLD})
    if market == "hk":
        filters.append({"left": "currency", "operation": "equal", "right": "HKD"})
    query = {"filter": filters, "options": {"lang": "en"}, "columns": COLUMNS,
             "sort": {"sortBy": "change|1W", "sortOrder": direction}, "range": [0, 49]}
    result = fetch(f"https://scanner.tradingview.com/{MARKETS[market]['scanner']}/scan", query)
    rows = []
    for item in result.get("data", []):
        symbol, values = item["s"], item["d"]
        ticker, name, price, change, cap, volume, currency = values
        if market == "a" and not symbol.startswith(("SSE:", "SZSE:")):
            continue
        if market == "hk" and not symbol.startswith("HKEX:"):
            continue
        if market == "us" and not symbol.startswith(("NASDAQ:", "NYSE:", "AMEX:")):
            continue
        if change is None or cap is None or price is None:
            continue
        if direction == "desc" and change <= 0 or direction == "asc" and change >= 0:
            continue
        rows.append({"symbol": symbol, "ticker": ticker, "name": name, "price": price,
                     "change": round(change, 3), "cap": round(cap), "currency": currency,
                     "volume": volume, "url": f"https://www.tradingview.com/symbols/{symbol.replace(':', '-')}/"})
    return rows[:25], result.get("totalCount", 0)


def quote_key(symbol):
    exchange, ticker = symbol.split(":", 1)
    return ({"SSE": "sh", "SZSE": "sz", "HKEX": "hk"}.get(exchange, "us")
            + (ticker.zfill(5) if exchange == "HKEX" else ticker))


def localize_names(markets):
    """Tencent quotes provide Chinese names; retain English when no translation exists."""
    cache_path = ROOT / "data" / "name-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    symbols = {row["symbol"] for market in ("a", "hk", "us", "gold")
               for group in markets[market] for side in ("gainers", "losers") for row in group[side]}
    missing = [symbol for symbol in sorted(symbols) if symbol not in cache]
    for offset in range(0, len(missing), 50):
        batch = missing[offset:offset + 50]
        url = "https://qt.gtimg.cn/q=" + ",".join(quote_key(symbol) for symbol in batch)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as response:
                body = response.read().decode("gbk", "replace")
            names = dict(re.findall(r'v_([^=]+)="[^"\n]*?~([^~]+)~', body))
            for symbol in batch:
                name = names.get(quote_key(symbol), "").strip()
                if name:
                    cache[symbol] = name
        except Exception as exc:
            print(f"Chinese-name lookup skipped: {exc}")
        time.sleep(0.2)
    for market in ("a", "hk", "us", "gold"):
        for group in markets[market]:
            for side in ("gainers", "losers"):
                for row in group[side]:
                    if market in ("us", "gold"):
                        row["englishName"] = row["name"]
                    translated = cache.get(row["symbol"])
                    if translated and (market in ("a", "hk") or re.search(r"[\u3400-\u9fff]", translated)):
                        row["name"] = translated
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    print(f"Chinese-name cache: {len(cache)} symbols")


def main():
    now = datetime.now(timezone.utc)
    china_day = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
    week_ending = china_day - timedelta(days=(china_day.weekday() - 4) % 7)
    output = {"updatedAt": now.isoformat(), "weekEnding": week_ending.isoformat(), "source": "TradingView / CoinGecko / Tencent Quotes", "markets": {}}
    for market, config in MARKETS.items():
        groups = []
        for lower, upper in config["bands"]:
            gainers, gain_count = scan(market, lower, upper, "desc")
            losers, loss_count = scan(market, lower, upper, "asc")
            groups.append({"min": lower, "max": upper, "gainers": gainers, "losers": losers,
                           "universeCount": max(gain_count, loss_count)})
        output["markets"][market] = groups
        print(f"{market}: " + ", ".join(f"{len(g['gainers'])}/{len(g['losers'])}" for g in groups))

    coins = []
    for page in (1, 2):
        data = fetch(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page={page}&price_change_percentage=7d")
        for coin in data:
            change = coin.get("price_change_percentage_7d_in_currency")
            if coin.get("id") not in STABLECOINS and coin.get("market_cap") and change is not None and coin.get("current_price") is not None:
                coins.append({"symbol": coin["id"], "ticker": coin["symbol"].upper(), "name": coin["name"],
                              "price": coin["current_price"], "change": round(change, 3),
                              "cap": coin["market_cap"], "currency": "USD", "volume": coin.get("total_volume"),
                              "url": f"https://www.coingecko.com/en/coins/{coin['id']}"})
        time.sleep(1)
    groups = []
    for lower, upper in [(0, 100e6), (100e6, 1e9), (1e9, 5e9), (5e9, 10e9), (10e9, None)]:
        selected = [c for c in coins if c["cap"] >= lower and (upper is None or c["cap"] < upper)]
        groups.append({"min": lower, "max": upper, "gainers": sorted((c for c in selected if c["change"] > 0), key=lambda c: -c["change"])[:25],
                       "losers": sorted((c for c in selected if c["change"] < 0), key=lambda c: c["change"])[:25],
                       "universeCount": len(selected)})
    output["markets"]["crypto"] = groups
    localize_names(output["markets"])
    path = ROOT / "data" / "weekly.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")
    history = path.parent / "history"
    history.mkdir(exist_ok=True)
    (history / f"{week_ending.isoformat()}.json").write_text(path.read_text())
    weeks = sorted((p.stem for p in history.glob("????-??-??.json")), reverse=True)
    (history / "index.json").write_text(json.dumps(weeks, separators=(",", ":")) + "\n")
    print(f"Wrote {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
