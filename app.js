const MARKETS = {
  a: { label: 'A 股', title: 'A 股市场', note: '沪深上市股票', currency: 'CNY', caps: ['全部市值', '< ¥50亿', '¥50–100亿', '¥100–500亿', '¥500–2,000亿', '≥ ¥2,000亿'] },
  hk: { label: '港股', title: '香港市场', note: '港交所上市股票', currency: 'HKD', caps: ['全部市值', '< HK$20亿', 'HK$20–100亿', 'HK$100–1,000亿', 'HK$1,000–5,000亿', '≥ HK$5,000亿'] },
  us: { label: '美股', title: '美国市场', note: 'NYSE / NASDAQ / AMEX', currency: 'USD', caps: ['全部市值', '< $10亿', '$10–20亿', '$20–100亿', '$100–500亿', '$500–2,000亿', '$2,000–5,000亿', '≥ $5,000亿'] },
  gold: { label: '黄金', title: '黄金矿业', note: '美股上市黄金矿业与贵金属公司', currency: 'USD', caps: ['全部市值', '< $20亿', '$20–50亿', '$50–200亿', '$200–500亿', '≥ $500亿'] },
  crypto: { label: '加密货币', title: '加密资产', note: '按美元市值排名前 500 的资产', currency: 'USD', caps: ['全部市值', '< $1亿', '$1–10亿', '$10–50亿', '$50–100亿', '≥ $100亿'] }
};
const state = { market: 'us', cap: 5, limit: 10, data: null, weeks: [], latest: null, weekRequest: 0 };
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
  return items.map((item, i) => {
    const usListing = state.market === 'us' || state.market === 'gold';
    const hasChinese = /[\u3400-\u9fff]/.test(item.name);
    const displayName = usListing && !hasChinese ? item.ticker : item.name;
    const secondary = usListing ? (item.englishName || item.name) : `${item.ticker} · ${item.currency}`;
    return `<a class="row" href="${html(item.url)}" target="_blank" rel="noopener noreferrer" title="${html(item.name)} · ${html(item.ticker)}">
    <span class="rank">${String(i + 1).padStart(2, '0')}</span>
    <span class="asset"><span class="avatar">${html(item.ticker.slice(0, 2).toUpperCase())}</span><span class="asset-info"><span class="asset-name">${html(displayName)}${usListing && hasChinese ? `<span class="inline-ticker">${html(item.ticker)}</span>` : ''}</span><span class="asset-symbol">${html(secondary)}</span></span></span>
    <span class="bar-track"><span class="bar ${kind}-bar" style="display:block;width:${Math.max(4, Math.abs(item.change) / max * 100)}%"></span></span>
    <span class="change ${kind === 'gain' ? 'positive' : 'negative'}">${pct(item.change)}</span>
  </a>`;
  }).join('');
}

function render() {
  if (!state.data) return;
  const config = MARKETS[state.market], result = selectedRows();
  const gainers = result.gainers.slice(0, state.limit), losers = result.losers.slice(0, state.limit);
  $('market-tabs').innerHTML = Object.entries(MARKETS).map(([key, m]) => `<button class="market-tab ${state.market === key ? 'active' : ''}" role="tab" aria-selected="${state.market === key}" data-market="${key}">${m.label}</button>`).join('');
  $('cap-select').innerHTML = config.caps.map((label, i) => `<option value="${i}">${label}</option>`).join('');
  $('cap-select').value = state.cap;
  $('week-select').value = state.data.weekEnding;
  const weekIndex = state.weeks.indexOf(state.data.weekEnding);
  $('older-week').disabled = weekIndex < 0 || weekIndex >= state.weeks.length - 1;
  $('newer-week').disabled = weekIndex <= 0;
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
  $('period-label').textContent = state.market === 'crypto' ? '过去 7 日' : (state.data.weekEnding === state.latest.weekEnding ? '本周' : '历史周');
  $('period-note').textContent = state.market === 'crypto' ? '快照时点向前滚动 7 日' : '周线收盘价变化';
  $('gain-count').textContent = `TOP ${gainers.length}`;
  $('loss-count').textContent = `TOP ${losers.length}`;
  $('gainers').innerHTML = renderRows(gainers, 'gain');
  $('losers').innerHTML = renderRows(losers, 'loss');
  const method = state.market === 'crypto'
    ? '加密资产来自 CoinGecko 市值排名前 500，涨跌幅为快照时点向前 7 日的价格变化；市值单位为美元。可切换最近 10 个已结束交易周。数据仅供市场观察。'
    : `股票涨跌幅和市值来自 TradingView，中文名称优先取自腾讯行情；无可用中文名称时保留英文。涨跌幅为周线价格变动，不含股息；市值按 ${config.currency} 分档。${state.market === 'gold' ? '黄金板块仅包含美股上市的黄金矿业与贵金属公司，不代表现货金走势。' : ''}榜单仅纳入价格高于 1、成交量高于 10 万的股票。可切换最近 10 个已结束交易周。数据仅供市场观察。`;
  $('method-text').textContent = state.data.backfilled
    ? `历史回填榜单以 ${state.data.universeAsOf} 的追踪样本为范围。股票历史收盘价来自腾讯行情，按相邻两周收盘价计算涨跌幅，未做拆股或分红复权；股票市值分档沿用 ${state.data.universeAsOf} 的市值。加密资产历史价格和市值来自 CoinPaprika、CoinGecko；无法核实的币种不纳入回填。回填榜单不代表当时全市场排名。`
    : method;
}

function boot(data) {
  if (!data?.weekEnding || !data?.markets || Object.keys(MARKETS).some(m => !Array.isArray(data.markets[m]) || data.markets[m].length !== MARKETS[m].caps.length - 1)) throw new Error('数据结构不完整');
  state.data = data;
  const stamp = new Date(data.updatedAt);
  document.querySelector('.meta-label').textContent = data.weekEnding === state.latest.weekEnding ? '最新快照' : '历史快照';
  $('snapshot-date').textContent = data.weekEnding;
  $('header-date').textContent = `${data.weekEnding} 周快照`;
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
async function switchWeek(week) {
  const requestId = ++state.weekRequest;
  try {
    if (week === state.latest.weekEnding) return boot(state.latest);
    const response = await fetch(`./data/history/${week}.json`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (requestId === state.weekRequest) boot(data);
  } catch (error) {
    $('week-select').value = state.data.weekEnding;
    alert(`无法加载该周数据：${error.message}`);
  }
}
$('week-select').addEventListener('change', event => switchWeek(event.target.value));
$('older-week').addEventListener('click', () => switchWeek(state.weeks[state.weeks.indexOf(state.data.weekEnding) + 1]));
$('newer-week').addEventListener('click', () => switchWeek(state.weeks[state.weeks.indexOf(state.data.weekEnding) - 1]));
fetch('./data/weekly.json', { cache: 'no-store' }).then(response => {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}).then(async data => {
  state.latest = data;
  try {
    const response = await fetch('./data/history/index.json', { cache: 'no-store' });
    state.weeks = response.ok ? await response.json() : [data.weekEnding];
  } catch { state.weeks = [data.weekEnding]; }
  if (!state.weeks.includes(data.weekEnding)) state.weeks.unshift(data.weekEnding);
  $('week-select').innerHTML = state.weeks.map((week, i) => `<option value="${html(week)}">${html(week)}${i === 0 ? ' · 最新' : ''}</option>`).join('');
  boot(data);
}).catch(error => {
  $('snapshot-date').textContent = '数据暂不可用';
  $('market-note').textContent = `加载失败：${error.message}`;
  $('gainers').innerHTML = '<div class="empty">暂时无法加载榜单，请稍后重试。</div>';
  $('losers').innerHTML = '<div class="empty">暂时无法加载榜单，请稍后重试。</div>';
});
