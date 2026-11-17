# Notice

## Original work

This project is a modified version of **day-trader-skill** by **Jake Schincariol**:

- Repository: https://github.com/Jakeschincariol/day-trader-skill
- Licence: MIT. Copyright (c) 2026 Jake Schincariol
- Based on the repository as cloned on 13 November 2026

The original copyright notice and the MIT permission notice are kept unchanged in [LICENSE](LICENSE), as the MIT licence requires.

This project is **not affiliated with, sponsored by or endorsed by** Jake Schincariol. His name is used only to credit the original work.

## What was changed (by Algo Traders Tamil, 2026)

- **Market:** US (NYSE/Nasdaq) changed to India (NSE). IST clock (UTC+5:30, no daylight saving), session 9:15 to 3:15 PM, intraday square-off by 3:10 PM, NSE 2026 trading holidays, rupee amounts, NSE 0.05 price tick, Yahoo `.NS` symbols.
- **Universe:** the Nasdaq Trader symbol lists were replaced by NSE's Nifty 50/100/200/500 constituent lists.
- **News:** Yahoo Finance India headlines. The US SEC EDGAR filings feature is switched off.
- **Brokers:** order tickets for Zerodha (Kite MCP) and Dhan (DhanHQ MCP) added; paper by default. The US broker sections (Alpaca, Interactive Brokers) are left in the text but are not used.
- **Swing mode (new):** `trader-scanner/swing.py` adds swing setups, a market filter, sector strength, swing plans, trailing stops, an open-swing tracker and a per-setup backtest, plus swing handling in risk, sizing, orders and alerts.
- **Risk defaults:** minimum reward:risk 1.5; sizing requires a fresh price.
- **Removed:** `trader-pelosi` (US Congress trades) and `trader-analyst` (SEC filings), both US-only. The original test suite was removed because it used US market fixtures.

## Third-party names and data

- Claude is a product of Anthropic. NSE, Nifty, Zerodha, Kite, Dhan, Yahoo, TradingView and other names are trademarks of their owners and are used only to describe compatibility. This project is not affiliated with or endorsed by any of them.
- **This repository contains no market data.** The scripts fetch public data at run time from Yahoo Finance (an unofficial, free, delayed source) and archives.nseindia.com. Users are responsible for following those sites' terms of use.
