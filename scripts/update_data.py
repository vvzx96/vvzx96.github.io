#!/usr/bin/env python3
"""Build a weekly, reproducible market snapshot for the static dashboard."""
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ["NEM", "AEM", "KGC", "WPM", "FNV", "AU", "HMY", "GFI", "IAG", "BTG", "EGO", "CDE", "HL", "OR", "EQX", "AGI", "RGLD", "NGD", "SAND", "SSRM", "DRD", "SA", "MUX", "GAU"]
STABLECOINS = {"tether", "usd-coin", "dai", "usds", "ethena-usde", "first-digital-usd", "paypal-usd", "usdd", "true-usd", "frax", "world-liberty-financial-usd"}
MARKETS = {
    "a": {"scanner": "china", "bands": [(0, 10e9), (10e9, 50e9), (50e9, None)]},
    "hk": {"scanner": "hongkong", "bands": [(0, 10e9), (10e9, 100e9), (100e9, None)]},
    "us": {"scanner": "america", "bands": [(0, 2e9), (2e9, 10e9), (10e9, None)]},
    "gold": {"scanner": "america", "bands": [(0, 5e9), (5e9, 20e9), (20e9, None)]},
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


def main():
    output = {"updatedAt": datetime.now(timezone.utc).isoformat(), "source": "TradingView / CoinGecko", "markets": {}}
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
    for lower, upper in [(0, 1e9), (1e9, 10e9), (10e9, None)]:
        selected = [c for c in coins if c["cap"] >= lower and (upper is None or c["cap"] < upper)]
        groups.append({"min": lower, "max": upper, "gainers": sorted((c for c in selected if c["change"] > 0), key=lambda c: -c["change"])[:25],
                       "losers": sorted((c for c in selected if c["change"] < 0), key=lambda c: c["change"])[:25],
                       "universeCount": len(selected)})
    output["markets"]["crypto"] = groups
    path = ROOT / "data" / "weekly.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Wrote {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
