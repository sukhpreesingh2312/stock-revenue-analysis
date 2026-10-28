# Stock performance & business fundamentals

A portfolio extension of the IBM / Coursera stock-data extraction project, comparing Tesla (TSLA) and GameStop (GME) through a reproducible Python pipeline and an interactive dashboard.

**Question:** How do adjusted stock performance, downside risk, and quarterly revenue growth differ over the same historical period?

## Results from the included snapshots

The shared comparison runs from **July 1, 2010 to April 30, 2020**, across **2,475 common trading dates**.

| Metric | Tesla | GameStop |
|---|---:|---:|
| Adjusted-price change | +3,460.47% | −55.37% |
| Annualized daily volatility | 54.65% | 47.53% |
| Maximum drawdown within the window | −60.63% | −93.21% |

Returns alone conceal substantial drawdowns. Revenue provides context for the businesses, but does not establish why their prices moved. This is a historical descriptive case study, not an investment recommendation.

The GameStop revenue snapshot ends in April 2020; Tesla's ends in September 2022. The default deliberately uses the earlier end date. **This project does not analyze the 2021 GameStop trading episode or current company fundamentals.**

## Open the results

- `Stock_Revenue_Analysis.ipynb`: executed analysis, methods, results, and limitations.
- `reports/dashboard.html`: interactive report; open in a browser, no server required.
- `analysis.py`: reusable functions and command-line entry point.
- `reports/metrics.csv`, `reports/*_revenue.csv`, `reports/aligned_prices.csv`: exported results.
- `reports/manifest.json`: sources, actual comparison dates, sample size, and input hashes.
- `tests/`: offline regression tests for parsing, missing periods, alignment, and metrics.

## Setup and reproduce

Use Python 3.11 or newer. The delivered version was tested with Python 3.14 and the exact dependencies in `requirements-lock.txt`. That lock records the tested macOS environment; use `requirements.txt` for a fresh environment on other platforms.

From this project directory:

```bash
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python analysis.py
python -m pytest -q
```

The default reuses included inputs and works offline once dependencies are installed. Open the notebook in VS Code or another Jupyter-compatible editor using that environment. For the browser-based Jupyter interface, install JupyterLab separately (`python -m pip install jupyterlab`) and launch `jupyter lab`.

To intentionally replace cached inputs:

```bash
python analysis.py --refresh
```

Refresh requires network access and may fail if Yahoo rate-limits requests or source markup changes. Errors remain visible; a failed refresh does not silently use stale data. Download validation happens before each cached file is replaced. Refresh is per source rather than an all-or-nothing transaction. Regeneration overwrites report files.

A custom historical subwindow is supported:

```bash
python analysis.py --start 2015-01-01 --end 2020-04-30 --output reports_2015
```

The requested end cannot exceed shared revenue coverage. A wider window than the local price cache requires `--refresh`. The common observed trading dates determine the final chart bounds.

## Improvements over the exercise

- Replaced duplicated ticker-specific code and per-row DataFrame concatenation with reusable functions and one-pass construction.
- Replaced positional HTML table selection with company and quarterly-heading matching.
- Added HTTP timeouts, retry handling, numeric/date conversion, explicit validation, and meaningful errors.
- Removed blanket warning suppression, inline package installs, assignment prompts, and hidden chart cutoffs.
- Used explicit adjusted prices and the same trading dates for both companies.
- Added indexed performance, YoY and trailing twelve-month revenue, annualized volatility, and maximum drawdown.
- Added a self-contained interactive dashboard, CSV exports, source hashes, executed notebook, and 15 regression checks.

## Assumptions and limits

Revenue is in USD millions. Fiscal period ends are not earnings publication dates. YoY calculations use calendar-quarter bins to identify the preceding year's corresponding fiscal quarter; missing periods are not forward-filled. The companies have different fiscal calendars. Zero year-earlier revenue produces a missing growth estimate.

Volatility uses the sample standard deviation of daily simple returns and 252 trading days per year. Drawdown uses running peaks inside the selected window, so it does not include earlier peaks. Indexed performance starts at 100 on the first common observed trading date. Yahoo adjusted closes are provider-adjusted historical series, not original nominal prices; no second split adjustment is applied. Results exclude transaction costs and taxes and do not simulate an executable strategy.

The snapshots were downloaded on October 28, 2026. Observation dates are historical. Missing source trading sessions are not imputed; the comparison uses the intersection of available observations. Input hashes preserve provenance for this delivery; the manifest's generation timestamp is not a data-publication timestamp.

## Sources, attribution, and portfolio use

Based on the IBM / Coursera *Extracting and Visualizing Stock Data* exercise supplied in the original notebook, attributed there to Joseph Santarcangelo and Azim Hirjani. Original notice: **Copyright © 2020 IBM Corporation. All rights reserved.** The original notebook was not modified.

Revenue sources are the IBM-hosted historical Macrotrends snapshots:

- [Tesla revenue](https://cf-courses-data.s3.us.cloud-object-storage.appdomain.cloud/IBMDeveloperSkillsNetwork-PY0220EN-SkillsNetwork/labs/project/revenue.htm)
- [GameStop revenue](https://cf-courses-data.s3.us.cloud-object-storage.appdomain.cloud/IBMDeveloperSkillsNetwork-PY0220EN-SkillsNetwork/labs/project/stock.html)

Price source: Yahoo Finance through [yfinance](https://ranaroussi.github.io/yfinance/). Third-party data and archived HTML retain their existing rights and terms. This repository does not grant a license to those materials. Review provider terms before publicly redistributing the bundled data and HTML; the downloadable package includes them for reproducibility.

Describe this as an **extended course project** in your portfolio, and explain your engineering and analytical additions. Read through the functions and tests so you can discuss the design choices in an interview.

## Validation performed

The complete pipeline ran with real source data, all notebook cells executed successfully, and 15 offline regression checks passed. The notebook structure and saved outputs were validated. The browser tool blocked the local-file preview, so browser rendering and interactive controls were not visually verified in this environment.
