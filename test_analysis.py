"""Offline regression checks for data integrity and financial calculations."""
import numpy as np
import pandas as pd
import pytest

from analysis import common_prices, parse_revenue, price_metrics, revenue_features, validate_prices


def table(rows, heading='Tesla Quarterly Revenue'):
    return '<table><tr><th>' + heading + '</th></tr>' + ''.join(
        f'<tr><td>{date}</td><td>{amount}</td></tr>' for date, amount in rows) + '</table>'


def test_table_selection_cleaning_and_sorting():
    html = table([('2020', '$999')], 'Tesla Annual Revenue') + table([
        ('2020-06-30', '$2,000'), ('2020-03-31', '$1,000'), ('2019-12-31', '')])
    result = parse_revenue(html, 'Tesla')
    assert result['Revenue'].tolist() == [1000, 2000]
    assert result['Date'].is_monotonic_increasing


@pytest.mark.parametrize('rows', [
    [('2020-03-31', 'oops')], [('2020-03-31', '($100)')],
    [('2020-03-31', '$1'), ('2020-03-31', '$2')], [('invalid', '$1')],
])
def test_reject_corrupt_revenue(rows):
    with pytest.raises(ValueError):
        parse_revenue(table(rows), 'Tesla')


def test_missing_heading_fails():
    with pytest.raises(ValueError, match='Expected one'):
        parse_revenue('<table></table>', 'Tesla')


def test_missing_quarter_does_not_create_false_yoy_or_ttm():
    frame = pd.DataFrame({'Date': pd.to_datetime([
        '2019-03-31', '2019-06-30', '2019-12-31', '2020-03-31', '2020-06-30']),
        'Revenue': [100., 200., 300., 150., 400.]})
    result = revenue_features(frame)
    assert result['Revenue_YoY_pct'].iloc[-2] == pytest.approx(50)
    assert result['Revenue_YoY_pct'].iloc[-1] == pytest.approx(100)
    assert np.isnan(result['Revenue_TTM'].iloc[-1])


def test_zero_denominator_yoy_is_missing():
    dates = pd.date_range('2019-03-31', periods=5, freq='QE')
    result = revenue_features(pd.DataFrame({'Date': dates, 'Revenue': [0, 1, 2, 3, 4]}))
    assert np.isnan(result['Revenue_YoY_pct'].iloc[-1])


def test_metrics_use_running_peak():
    prices = pd.DataFrame({'TEST': [100., 120., 90., 110.]})
    result = price_metrics(prices).loc['TEST']
    assert result['Return_pct'] == pytest.approx(10)
    assert result['Max_drawdown_pct'] == pytest.approx(-25)
    assert result['Annualized_volatility_pct'] == pytest.approx(
        np.std([.2, -.25, 110 / 90 - 1], ddof=1) * np.sqrt(252) * 100)


def test_common_dates_prevent_different_baselines():
    a = pd.DataFrame({'Date': pd.to_datetime(['2020-01-01', '2020-01-02', '2020-01-03']), 'Close': [1, 2, 3]})
    b = a.iloc[1:]
    aligned = common_prices({'A': a, 'B': b}, '2020-01-01', '2020-01-03')
    assert len(aligned) == 2
    assert aligned.index.min() == pd.Timestamp('2020-01-02')


@pytest.mark.parametrize('values', [[0, 1], [-1, 1], [np.nan, 1], [np.inf, 1]])
def test_invalid_prices_fail(values):
    with pytest.raises(ValueError):
        validate_prices(pd.DataFrame({'Date': ['2020-01-01', '2020-01-02'], 'Close': values}))


def test_timezone_preserves_exchange_date():
    dates = pd.date_range('2020-01-01', periods=2, tz='America/New_York')
    frame = validate_prices(pd.DataFrame({'Date': dates, 'Close': [1, 2]}))
    assert frame['Date'].dt.tz is None
    assert frame['Date'].iloc[0] == pd.Timestamp('2020-01-01')
