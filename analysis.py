"""Reproducible historical stock/revenue comparison; run with --help."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
from plotly.subplots import make_subplots
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
BASE_URL = ('https://cf-courses-data.s3.us.cloud-object-storage.appdomain.cloud/'
            'IBMDeveloperSkillsNetwork-PY0220EN-SkillsNetwork/labs/project/')
COMPANIES = {'TSLA': ('Tesla', BASE_URL + 'revenue.htm'),
             'GME': ('GameStop', BASE_URL + 'stock.html')}
LOGGER = logging.getLogger(__name__)


def fetch_html(url: str) -> str:
    """Download a source with bounded timeouts, retrying transient GET failures."""
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    with requests.Session() as session:
        session.mount('https://', HTTPAdapter(max_retries=retry))
        response = session.get(url, timeout=(10, 45))
        response.raise_for_status()
        return response.text


def parse_revenue(html: str, company: str) -> pd.DataFrame:
    """Find a quarterly table by heading; return dates and USD millions.

    Blank revenue rows are excluded; malformed nonblank observations raise errors.
    Duplicate or negative observations are rejected instead of silently repaired.
    """
    soup = BeautifulSoup(html, 'html.parser')
    matches = [table for table in soup.find_all('table')
               if company.casefold() in table.get_text(' ', strip=True).casefold()
               and 'quarterly revenue' in table.get_text(' ', strip=True).casefold()]
    if len(matches) != 1:
        raise ValueError(f'Expected one {company} quarterly revenue table; found {len(matches)}')
    rows = []
    for row in matches[0].find_all('tr'):
        cells = row.find_all('td')
        if len(cells) != 2:
            continue
        date, amount = [cell.get_text(strip=True) for cell in cells]
        if not amount or amount in {'-', '—', 'N/A'}:
            continue
        amount = amount.replace('$', '').replace(',', '').strip()
        if amount.startswith('(') and amount.endswith(')'):
            amount = '-' + amount[1:-1]
        rows.append((date, amount))
    if not rows:
        raise ValueError(f'No revenue observations for {company}')
    data = pd.DataFrame(rows, columns=['Date', 'Revenue'])
    data['Date'] = pd.to_datetime(data['Date'], format='%Y-%m-%d', errors='raise')
    data['Revenue'] = pd.to_numeric(data['Revenue'], errors='raise').astype(float)
    if data['Date'].duplicated().any() or not np.isfinite(data['Revenue']).all() or (data['Revenue'] < 0).any():
        raise ValueError('Revenue contains duplicate dates, nonfinite values, or negative values')
    return data.sort_values('Date').reset_index(drop=True)


def validate_prices(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize daily prices and reject invalid observations."""
    if not {'Date', 'Close'}.issubset(data.columns) or data.empty:
        raise ValueError('Prices must contain nonempty Date and Close columns')
    data = data[['Date', 'Close']].copy()
    # Keep exchange-local trading dates when removing timezone information.
    dates = pd.to_datetime(data['Date'], errors='raise')
    if dates.dt.tz is not None:
        dates = dates.dt.tz_localize(None)
    data['Date'] = dates.dt.normalize()
    data['Close'] = pd.to_numeric(data['Close'], errors='raise')
    if (data['Date'].isna().any() or data['Date'].duplicated().any()
            or not np.isfinite(data['Close']).all() or (data['Close'] <= 0).any()):
        raise ValueError('Prices contain missing/duplicate dates or nonpositive/nonfinite values')
    return data.sort_values('Date').reset_index(drop=True)


def download_prices(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch adjusted closes; yfinance end is exclusive, so add one day."""
    import yfinance as yf

    history = yf.Ticker(ticker).history(
        start=start, end=(pd.Timestamp(end) + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
        auto_adjust=True, actions=False, timeout=30,
    )
    return validate_prices(history.reset_index())


def revenue_features(data: pd.DataFrame) -> pd.DataFrame:
    """Calculate YoY growth by fiscal period, leaving missing periods unfilled."""
    result = data.copy()
    periods = result['Date'].dt.to_period('Q')
    if periods.duplicated().any():
        raise ValueError('Multiple revenue observations in one quarter')
    series = pd.Series(result['Revenue'].to_numpy(), index=periods)
    calendar = pd.period_range(periods.min(), periods.max(), freq='Q')
    complete = series.reindex(calendar)
    prior = complete.shift(4).replace(0, np.nan)
    growth = (complete / prior - 1) * 100
    result['Revenue_YoY_pct'] = growth.reindex(periods).to_numpy()
    result['Revenue_TTM'] = complete.rolling(4, min_periods=4).sum().reindex(periods).to_numpy()
    return result


def common_prices(prices: dict[str, pd.DataFrame], start: str, end: str) -> pd.DataFrame:
    """Align trading dates so both stocks use the same comparison window."""
    aligned = pd.concat({ticker: data.set_index('Date')['Close']
                         for ticker, data in prices.items()}, axis=1).dropna()
    aligned = aligned.loc[start:end]
    if len(aligned) < 2:
        raise ValueError('Need at least two common trading dates in the selected window')
    return aligned


def price_metrics(prices: pd.DataFrame) -> pd.DataFrame:
    """Return, annualized daily volatility, and within-window maximum drawdown."""
    returns = prices.pct_change(fill_method=None).iloc[1:]
    drawdown = prices.div(prices.cummax()) - 1
    return pd.DataFrame({
        'Return_pct': (prices.iloc[-1] / prices.iloc[0] - 1) * 100,
        'Annualized_volatility_pct': returns.std(ddof=1) * np.sqrt(252) * 100,
        'Max_drawdown_pct': drawdown.min() * 100,
    }).rename_axis('Ticker')


def dashboard(prices: pd.DataFrame, revenues: dict[str, pd.DataFrame]) -> go.Figure:
    """Create a self-contained, interactive comparison without double y axes."""
    fig = make_subplots(rows=2, cols=2, subplot_titles=(
        'Adjusted price · first common date = 100', 'Quarterly revenue · USD millions',
        'Daily drawdown from running peak · %', 'Revenue change vs. same quarter last year · %'))
    colors = {'TSLA': '#2563eb', 'GME': '#ea580c'}
    for ticker in prices:
        color = colors[ticker]
        normalized = prices[ticker] / prices[ticker].iloc[0] * 100
        drawdown = (prices[ticker] / prices[ticker].cummax() - 1) * 100
        revenue = revenues[ticker]
        revenue = revenue.loc[revenue['Date'].between(prices.index.min(), prices.index.max())]
        for values, dates, row, col in [
            (normalized, prices.index, 1, 1),
            (revenue['Revenue'], revenue['Date'], 1, 2),
            (drawdown, prices.index, 2, 1),
            (revenue['Revenue_YoY_pct'], revenue['Date'], 2, 2),
        ]:
            fig.add_trace(go.Scatter(x=dates, y=values, name=ticker,
                                    legendgroup=ticker, showlegend=(row, col) == (1, 1),
                                    mode='lines', line={'color': color, 'width': 2},
                                    connectgaps=False), row=row, col=col)
    fig.update_layout(
        title={'text': 'Stock performance & business fundamentals<br>'
               f'<sup>{prices.index.min():%b %d, %Y} – {prices.index.max():%b %d, %Y}'
               ' · Historical course snapshots · Fiscal dates are not publication dates</sup>'},
        template='plotly_white', height=850, hovermode='x unified',
        margin={'t': 110, 'b': 70}, legend={'orientation': 'h', 'y': -0.08},
    )
    fig.update_yaxes(title_text='Indexed adjusted close', row=1, col=1)
    fig.update_yaxes(title_text='USD millions', row=1, col=2)
    fig.update_yaxes(title_text='Percent', row=2, col=1)
    fig.update_yaxes(title_text='Percent', row=2, col=2)
    return fig


def run(output: Path = ROOT / 'reports', refresh: bool = False,
        start: str = '2010-07-01', end: str | None = None) -> dict:
    """Load local snapshots by default; refresh explicitly replaces source files.

    The default end date is the older of the companies' final revenue dates.
    No stale-cache fallback occurs when a refresh fails.
    """
    raw = ROOT / 'data' / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    revenues, provenance = {}, {}
    for ticker, (company, url) in COMPANIES.items():
        path = raw / f'{ticker}_revenue.html'
        if refresh or not path.exists():
            html = fetch_html(url)
            parse_revenue(html, company)  # Validate before replacing a cache.
            path.write_text(html, encoding='utf-8')
        revenues[ticker] = revenue_features(parse_revenue(path.read_text(encoding='utf-8'), company))
        provenance[ticker] = {'revenue_url': url, 'revenue_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                              'revenue_last_date': str(revenues[ticker]['Date'].max().date())}
    shared_end = min(frame['Date'].max() for frame in revenues.values())
    requested_end = pd.Timestamp(end) if end else shared_end
    if requested_end > shared_end:
        raise ValueError(f'End exceeds shared revenue coverage ({shared_end.date()})')
    if pd.Timestamp(start) >= requested_end:
        raise ValueError('Start must be before end')
    end = str(requested_end.date())
    prices = {}
    for ticker in COMPANIES:
        path = raw / f'{ticker}_prices.csv'
        if refresh or not path.exists():
            data = download_prices(ticker, start, end)
            data.to_csv(path, index=False)
        prices[ticker] = validate_prices(pd.read_csv(path))
        if prices[ticker]['Date'].min() > pd.Timestamp(start) + pd.Timedelta(days=7) or prices[ticker]['Date'].max() < requested_end - pd.Timedelta(days=7):
            raise ValueError(f'{ticker} cache does not cover requested dates; use --refresh')
        provenance[ticker]['prices_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        provenance[ticker]['price_source'] = 'Yahoo Finance via yfinance; auto_adjust=True'
    aligned = common_prices(prices, start, end)
    metrics = price_metrics(aligned)
    figure = dashboard(aligned, revenues)
    figure.write_html(output / 'dashboard.html', include_plotlyjs=True, full_html=True)
    metrics.to_csv(output / 'metrics.csv')
    aligned.to_csv(output / 'aligned_prices.csv')
    for ticker, frame in revenues.items():
        frame.to_csv(output / f'{ticker}_revenue.csv', index=False)
    manifest = {'generated_at_utc': pd.Timestamp.now(tz='UTC').isoformat(),
                'comparison_start': str(aligned.index.min().date()),
                'comparison_end': str(aligned.index.max().date()),
                'common_trading_days': len(aligned), 'sources': provenance,
                'limitations': ['Historical snapshots, not current fundamentals.',
                                'Fiscal quarter ends are not earnings release dates.',
                                'Adjusted closes can be revised by provider; cached files preserve this run.',
                                'Revenue is not profit. No causal or predictive claims.']}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    LOGGER.info('Exported %s common trading dates to %s', len(aligned), output)
    return {'prices': aligned, 'revenues': revenues, 'metrics': metrics,
            'figure': figure, 'manifest': manifest}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Re-download sources (network required)')
    parser.add_argument('--start', default='2010-07-01', help='Inclusive YYYY-MM-DD')
    parser.add_argument('--end', help='Inclusive YYYY-MM-DD; defaults to shared revenue coverage')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    run(output=args.output, refresh=args.refresh, start=args.start, end=args.end)
