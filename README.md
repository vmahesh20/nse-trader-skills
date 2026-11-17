# NSE Trader Skills for Claude

**Intraday + swing trading skills for the Indian stock market (NSE), built for Claude.**

Scan the market, time the entry, set the stop and target, check the odds, size the position, pass a risk check, and get an order ticket for Zerodha or Dhan, all by asking Claude in plain words. Paper trading by default. Nothing is ever placed without your yes.

By **[Algo Traders Tamil](https://algotamil.com)** · Telegram [@Algotradersadmin](https://t.me/Algotradersadmin)
A modified version of **[day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) by Jake Schincariol** (MIT licence), the US original. See [Credits](#credits-and-licence) and [NOTICE.md](NOTICE.md).

---

## What it does

| Skill | Ask Claude | Job |
|---|---|---|
| `/trader-scanner` | "scan for ORB", "swing scan" | Opening-range breakouts on 5-min bars; daily setups; swing setups (52-week high, pullbacks, momentum burst, relative strength vs Nifty, sector leaders, market filter) |
| `/trader-news` | "any news on RELIANCE.NS" | Yahoo Finance India headlines and price moves for your watchlist |
| `/trader-entry` | "watch TCS.NS", "has it broken out" | Watches a setup bar by bar and calls the entry |
| `/trader-exit` | "set my stop and target" | Stop and target before you enter (range, %, ATR or your price), on the NSE 0.05 tick |
| `/trader-timemachine` | "what are the odds" | Replays the rest of the day 10,000 times from the stock's own 5-min bars, plus every past time the rule fired |
| `/trader-risk` | "check my order" | Max loss per trade, daily loss, trades per day, reward:risk, entry window, holidays: PASS or BLOCK |
| `/trader-budget` | "how many shares" | Sizes the position from your max loss, budget and cash buffer |
| `/trader-broker` | "place the order" | Order ticket for Zerodha (Kite MCP) or Dhan (DhanHQ MCP); paper by default; never without your yes |
| `/trader-alerts` | "alert me when", "is the market open" | Price, stop, target, opening bell and 3:10 PM square-off alerts |

## Two modes: intraday and swing

Set `"mode"` in `trader/config.json` to `"intraday"` or `"swing"`. If it is missing, Claude asks once.

| | Intraday | Swing |
|---|---|---|
| Scan | ORB (first 15 min), daily setups | 52-week high, pullback 20/50, momentum burst, RS vs Nifty, sector leaders, Nifty market filter |
| Plan | Range-midpoint stop, 2R target | 10-day-low / 2x ATR stop, 2R target, 20-day-average trail, 10-day time stop |
| Odds | Time Machine (10,000 replays) | `swing.py backtest` (every past signal, ~2 years) |
| Risk | Daily loss, trades per day, 9:30 to 2:45 entries | + 1% overnight gap buffer, max 5 open swings, max 2 per sector |
| Order | MIS, square off by 3:10 PM | CNC buy-stop + OCO exit (Zerodha GTT / Dhan Forever order) |

## India settings

- Symbols: Yahoo NSE tickers as they are: `RELIANCE.NS`, `TCS.NS`, `M&M.NS`
- Clock: IST. Session 9:15 to 3:15 PM, every day trade closed by 3:10 PM
- NSE 2026 trading holidays built in (add the 2027 list when NSE publishes it)
- Money in Rs. Defaults: Rs 1,000 max loss a trade, Rs 3,000 a day, minimum reward:risk 1.5
- Universe: NSE Nifty 50 / 100 / 200 / 500 lists from nseindia.com

## Install

**Claude (web / desktop):** download each `trader-*` folder as a zip and upload it in Settings → Capabilities → Skills.

**Claude Code:**
```bash
/plugin marketplace add vmahesh20/nse-trader-skills
/plugin install nse-trader-skills@nse-trader-skills
```
or copy the folders: `cp -r trader-* ~/.claude/skills/`

**Config:** copy `trader-budget/config.example.json` to `trader/config.json` in the folder you work from, then set your `budget`, `max_loss_per_trade_inr` and `broker` (`paper`, `zerodha` or `dhan`).

Requirements: Python 3.8+, standard library only. Data: Yahoo Finance (free, delayed, unofficial) and archives.nseindia.com. Run on your own computer (connect the folder in the Claude desktop app, or use Claude Code).

## First test

1. "Is the market open?" checks the clock and holidays
2. After 9:35 AM: "scan for ORB"
3. Pick one: "run the full paper flow for BALRAMCHIN.NS" (news → entry → exit → odds → size → risk → ticket)
4. After 3:30 PM: "swing scan", then "backtest swing"

## Brokers

- **Zerodha:** official Kite MCP server ([zerodha/kite-mcp-server](https://github.com/zerodha/kite-mcp-server)). Intraday: MIS entry, then SL-M stop and LIMIT target. Swing: CNC + GTT two-leg.
- **Dhan:** DhanHQ MCP ([docs.dhanhq.co](https://docs.dhanhq.co)). Intraday: one super order. Swing: CNC + Forever OCO.
- Paper (`"broker": "paper"`) is the default. Switch to live only when you mean it.

## Not covered (check yourself)

Quarterly results dates, NSE ASM/GSM surveillance lists, options and F&O, short selling, brokerage and taxes in P&L.

## Disclaimer

- **Education and tooling only. Not investment advice, not a research report and not a recommendation** to buy or sell any security. The authors are not SEBI-registered investment advisers or research analysts. Scans, odds and backtests are rule outputs, not tips.
- Trading in securities involves risk of loss. You are solely responsible for your own trades. Use paper mode until you understand every step, and consult a SEBI-registered adviser before investing.
- Backtests use today's index lists (survivorship bias) and exclude brokerage and taxes. Past results do not guarantee future ones.
- Data comes from free, delayed, unofficial sources and can be wrong or late. Your broker's price is the one that fills.
- The software is provided "as is", without warranty of any kind (see [LICENSE](LICENSE)). The authors are not liable for any loss from its use.
- Not affiliated with or endorsed by Anthropic, NSE, Zerodha, Dhan, Yahoo, TradingView or Jake Schincariol. All trademarks belong to their owners. See [NOTICE.md](NOTICE.md).

## Credits and licence

This project is a **modified version of [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) by Jake Schincariol**, used under the MIT licence. The original copyright and permission notice are kept in [LICENSE](LICENSE). The full list of changes is in [NOTICE.md](NOTICE.md).

- Original US skill pack (scanner, news, entry, exit, Time Machine, risk, budget, broker, alerts): **Jake Schincariol**
- NSE / India adaptation, swing mode, Zerodha / Dhan support: **[Algo Traders Tamil](https://algotamil.com)**, Telegram [@Algotradersadmin](https://t.me/Algotradersadmin)

MIT licence. Copyright (c) 2026 Jake Schincariol; modifications copyright (c) 2026 Algo Traders Tamil.
