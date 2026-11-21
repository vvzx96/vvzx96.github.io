#!/usr/bin/env python3
"""Validate source data before publishing a new snapshot."""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

data = json.loads((Path(__file__).resolve().parents[1] / 'data/weekly.json').read_text())
stamp = datetime.fromisoformat(data['updatedAt'])
if '--allow-stale' not in sys.argv:
    assert (datetime.now(timezone.utc) - stamp).total_seconds() < 86400, 'Snapshot is stale'
assert set(data['markets']) == {'a', 'hk', 'us', 'gold', 'crypto'}
for market, groups in data['markets'].items():
    assert len(groups) == 3, market
    for group in groups:
        assert group['universeCount'] >= len(group['gainers'])
        assert group['universeCount'] >= len(group['losers'])
        for kind, sign in [('gainers', 1), ('losers', -1)]:
            rows = group[kind]
            assert len(rows) <= 25
            assert len({row['symbol'] for row in rows}) == len(rows)
            changes = [row['change'] for row in rows]
            assert changes == sorted(changes, reverse=sign == 1)
            for row in rows:
                assert sign * row['change'] > 0 and math.isfinite(row['change'])
                assert row['cap'] >= group['min']
                assert group['max'] is None or row['cap'] < group['max']
                assert row['price'] > 0
                if market != 'crypto':
                    assert row['currency'] == {'a': 'CNY', 'hk': 'HKD', 'us': 'USD', 'gold': 'USD'}[market]
        print(market, group['min'], len(group['gainers']), len(group['losers']))
print('Snapshot validation passed')
