const MARKETS = {
  a: { label: 'A 股', title: 'A 股市场', note: '沪深上市股票', currency: 'CNY', caps: ['全部市值', '小盘 · < ¥100亿', '中盘 · ¥100–500亿', '大盘 · ≥ ¥500亿'] },
  hk: { label: '港股', title: '香港市场', note: '港交所上市股票', currency: 'HKD', caps: ['全部市值', '小盘 · < HK$100亿', '中盘 · HK$100–1,000亿', '大盘 · ≥ HK$1,000亿'] },
  us: { label: '美股', title: '美国市场', note: 'NYSE / NASDAQ / AMEX', currency: 'USD', caps: ['全部市值', '小盘 · < $20亿', '中盘 · $20–100亿', '大盘 · ≥ $100亿'] },
  gold: { label: '黄金', title: '黄金矿业', note: '美股上市黄金矿业与贵金属公司', currency: 'USD', caps: ['全部市值', '小盘 · < $50亿', '中盘 · $50–200亿', '大盘 · ≥ $200亿'] },
  crypto: { label: '加密货币', title: '加密资产', note: '按美元市值排名前 500 的资产', currency: 'USD', caps: ['全部市值', '小盘 · < $10亿', '中盘 · $10–100亿', '大盘 · ≥ $100亿'] }
};
const state = { market: 'us', cap: 3, limit: 10, data: null };
const $ = id => document.getElementById(id);
const html = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = value => `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
const num = value => new Intl.NumberFormat('zh-CN').format(value);

function selectedRows() {
  const groups = state.data.markets[state.market];
  if (state.cap) return groups[state.cap - 1];
  const gainers = groups.flatMap(g => g.gainers).sort((a, b) => b.change - a.change).slice(0, 25);
  const losers = groups.flatMap(g => g.losers).sort((a, b) => a.change - b.change).slice(0, 25);
  return { gainers, losers, universeCount: groups.reduce((n, g) => n + g.universeCount, 0) };
}

function renderRows(items, kind) {
  if (!items.length) return '<div class="empty">该范围暂无符合条件的资产</div>';
  const max = Math.max(...items.map(x => Math.abs(x.change)), 1);
  return items.map((item, i) => `<a class="row" href="${html(item.url)}" target="_blank" rel="noopener noreferrer" title="${html(item.name)} · ${html(item.ticker)}">
    <span class="rank">${String(i + 1).padStart(2, '0')}</span>
    <span class="asset"><span class="avatar">${html(item.ticker.slice(0, 2).toUpperCase())}</span><span class="asset-info"><span class="asset-name">${html(item.name)}</span><span class="asset-symbol">${html(item.ticker)} · ${html(item.currency)}</span></span></span>
    <span class="bar-track"><span class="bar ${kind}-bar" style="display:block;width:${Math.max(4, Math.abs(item.change) / max * 100)}%"></span></span>
    <span class="change ${kind === 'gain' ? 'positive' : 'negative'}">${pct(item.change)}</span>
  </a>`).join('');
}

function render() {
  if (!state.data) return;
  const config = MARKETS[state.market], result = selectedRows();
  const gainers = result.gainers.slice(0, state.limit), losers = result.losers.slice(0, state.limit);
  $('market-tabs').innerHTML = Object.entries(MARKETS).map(([key, m]) => `<button class="market-tab ${state.market === key ? 'active' : ''}" role="tab" aria-selected="${state.market === key}" data-market="${key}">${m.label}</button>`).join('');
  $('cap-select').innerHTML = config.caps.map((label, i) => `<option value="${i}">${label}</option>`).join('');
  $('cap-select').value = state.cap;
  $('limit-select').value = state.limit;
  $('market-title').textContent = config.title;
  $('market-note').textContent = config.note;
  $('cap-label').textContent = config.caps[state.cap];
  $('universe-count').textContent = `样本 ${num(result.universeCount)}`;
  $('max-gain').textContent = gainers.length ? pct(gainers[0].change) : '—';
  $('max-gain-name').textContent = gainers[0]?.name || '暂无数据';
  $('max-loss').textContent = losers.length ? pct(losers[0].change) : '—';
  $('max-loss-name').textContent = losers[0]?.name || '暂无数据';
  $('coverage').textContent = `${gainers.length + losers.length} 只`;
  $('period-label').textContent = state.market === 'crypto' ? '过去 7 日' : '本周';
  $('period-note').textContent = state.market === 'crypto' ? '快照时点向前滚动 7 日' : '周线收盘价变化';
  $('gain-count').textContent = `TOP ${gainers.length}`;
  $('loss-count').textContent = `TOP ${losers.length}`;
  $('gainers').innerHTML = renderRows(gainers, 'gain');
  $('losers').innerHTML = renderRows(losers, 'loss');
  $('method-text').textContent = state.market === 'crypto'
    ? '加密资产来自 CoinGecko 市值排名前 500，涨跌幅为快照时点向前 7 日的价格变化；市值单位为美元。每周六生成快照。数据仅供市场观察。'
    : `股票数据来自 TradingView，涨跌幅为周线价格变动，不含股息；市值按 ${config.currency} 分档。${state.market === 'gold' ? '黄金板块仅包含美股上市的黄金矿业与贵金属公司，不代表现货金走势。' : ''}每周六生成快照，榜单仅纳入价格高于 1、成交量高于 10 万的股票。数据仅供市场观察。`;
}

function boot(data) {
  if (!data?.markets || Object.keys(MARKETS).some(m => !Array.isArray(data.markets[m]) || data.markets[m].length !== 3)) throw new Error('数据结构不完整');
  state.data = data;
  const stamp = new Date(data.updatedAt);
  const date = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(stamp);
  $('snapshot-date').textContent = date;
  $('header-date').textContent = `${date} 快照`;
  $('updated-at').textContent = `生成于 ${new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'short' }).format(stamp)}（北京时间）`;
  render();
}

$('market-tabs').addEventListener('click', event => {
  const button = event.target.closest('[data-market]');
  if (!button) return;
  state.market = button.dataset.market;
  state.cap = 0;
  render();
});
$('cap-select').addEventListener('change', event => { state.cap = Number(event.target.value); render(); });
$('limit-select').addEventListener('change', event => { state.limit = Number(event.target.value); render(); });
fetch('./data/weekly.json', { cache: 'no-store' }).then(response => {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}).then(boot).catch(error => {
  $('snapshot-date').textContent = '数据暂不可用';
  $('market-note').textContent = `加载失败：${error.message}`;
  $('gainers').innerHTML = '<div class="empty">暂时无法加载榜单，请稍后重试。</div>';
  $('losers').innerHTML = '<div class="empty">暂时无法加载榜单，请稍后重试。</div>';
});
