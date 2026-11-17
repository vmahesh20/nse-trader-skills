---
name: trader-scanner
description: >-
  Chart Scanner for NSE stocks (Yahoo .NS), intraday and swing. Intraday:
  pre-market daily setups and opening-range breakouts on 5-minute bars.
  Swing (swing.py): 52-week-high breakouts, pullbacks to the 20/50-day
  average, momentum bursts, relative strength vs Nifty, sector leaders and
  a Nifty market filter, plus swing plan, trailing stop, open-swing tracker
  and per-setup backtest. Universe from NSE's Nifty 50-500 lists. Writes
  trader/watchlist.json. Use when the user says "scan the market", "find me
  setups", "opening range breakouts", "pre-market scan", "build my
  watchlist", "swing trade", "swing setups", "positional", "trail my stop",
  "my open swings", "backtest swing", or at the start of a trading day.
argument-hint: "[universe | daily | orb | swing scan|plan|trail|backtest]"
---

> **India mode (NSE).** Symbols are Yahoo NSE tickers like `RELIANCE.NS`. Session 9:15 to 15:15 IST, no new entries after 14:45, every day trade closed by 15:10. NSE 2026 holiday list built in. Money in Rs. NSE has no 1:00 p.m. early closes: ignore any mention of them below. Stops and targets are rounded to the NSE 0.05 tick.

> **Mode.** Read `"mode"` in `trader/config.json` (`"intraday"` or `"swing"`). If it is missing, ask the user once: "Intraday or swing?" and save the answer there. A request like "swing trade X" or "intraday ORB" overrides it for that trade.

# trader-scanner

The Chart Scanner is the first step of a day trade. It reads thousands of
free charts and lists the ones that match a rule. That is all it does. A scan
is a list of charts that match a rule, not a list of stocks to buy, and a
setup on a chart is not a prediction. Most people who day trade lose money;
the scanner does not change that. It only saves you from flipping through
5,000 charts by hand.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe                       # -> trader/universe.txt
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily                          # before the open -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --symbols RELIANCE.NS,INFY.NS,SBIN.NS  # or --watchlist FILE, --limit 200
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb                            # after 9:35 AM IST -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --at 10:15                 # cut the clock at 10:15 AM IST
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --watchlist trader/watchlist.json --json
```

Flags: `--min-price 5` and `--min-volume` (daily 1,000,000, orb 0),
`--or-minutes 15`, `--max-confirm 200` (orb stage 2),
`--now "2026-10-19 10:15"` (IST time) to pin the clock, `--offline PATH`
to read saved Yahoo files, `--no-write`, `--show N`, `--json`. Exit code 0
when the scan found something, 1 when it found nothing or could not run (the
reason is one plain line).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/universe.txt` | written by `universe`: one `SYMBOL\|Name` a line, read by `daily` and `orb` |
| `trader/watchlist.json` | written by `daily` and `orb`: `mode`, `as_of`, `universe`, `scanned`, `failed`, `hits[]`. trader-news and trader-entry read `hits[].symbol` |
| `trader/config.json` | read by `orb`: `no_entries_after` (default 14:45) |

## Swing mode (`swing.py`)

Used when the mode is `swing`. Run after 15:30 IST (or before 9:15) so the day's candle is complete.

```bash
python3 "${CLAUDE_SKILL_DIR}/swing.py" scan                  # setups -> trader/watchlist.json (mode: swing)
python3 "${CLAUDE_SKILL_DIR}/swing.py" plan SYMBOL --write   # entry, stop, 2R target -> trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/swing.py" check SYMBOL          # max open swings, sector cap, market filter
python3 "${CLAUDE_SKILL_DIR}/swing.py" open SYMBOL --qty N --entry X --stop Y --target Z --sector S   # after the fill
python3 "${CLAUDE_SKILL_DIR}/swing.py" positions             # open swings: R so far, days held, stop distance
python3 "${CLAUDE_SKILL_DIR}/swing.py" trail --write         # daily after close: raise stops, flag time stops
python3 "${CLAUDE_SKILL_DIR}/swing.py" close SYMBOL --price X   # journal: win rate, average R
python3 "${CLAUDE_SKILL_DIR}/swing.py" backtest              # every past signal per setup: trades, win %, avg R
```

Setups: `high_52w`, `pullback_20`, `pullback_50`, `momentum_burst` (liquidity filtered, likely upper-circuit closes skipped), `rs_leader` (top 20% vs Nifty). Each hit shows its sector and whether the sector is a top-3 leader (median 21-day return), plus the market filter (Nifty above a rising 50-day average = risk-on; caution = smaller size).

Plan rule: buy-stop a tick above the signal day's high; stop under the 10-day low, never wider than 2x ATR; target 2R; trail by the 20-day average (or `--trail low10`); time stop after 10 sessions without 1R.

Swing flow and timing:
- Evening (after 15:30): `swing.py scan`, then `swing.py plan SYMBOL --write`. The plan is dated the next trading day.
- Next morning (9:20 to 15:15): /trader-budget (adds the gap buffer), `swing.py check` + /trader-risk, /trader-broker (CNC buy-stop + OCO exit after the fill), then `swing.py open`. Budget and risk refuse an evening run: the plan is for the next session and the market is closed.
- If the stock opens above the plan entry, do not chase: the buy-stop would be rejected or fill far above the plan. Skip it, or wait for a new signal and a new plan.
- Every evening: `swing.py trail --write`, then modify any raised stop in the broker's GTT / Forever order.

Before any swing entry tell the user to check the results date and NSE's ASM/GSM lists: this pack cannot read them. Run `backtest` before trusting a setup, and say its limits (today's Nifty 500 list, so survivorship bias; costs 0.2%).

## The universe

`universe` downloads an NSE index constituents CSV from
archives.nseindia.com/content/indices/ (`--index nifty500` by default; also
`nifty50`, `nifty100`, `nifty200`) and keeps EQ-series rows, written as Yahoo
symbols like `RELIANCE.NS`. You can also pass your own list with
`--symbols RELIANCE.NS,TCS.NS` or `--watchlist FILE`.

India session: 9:15 to 15:15 IST, every day trade closed by 15:10, NSE holiday
list built in. Liquidity floors: price Rs 50+, daily volume 5 lakh+ shares.

## The daily scan (before the open)

Yahoo's spark endpoint returns closes for 20 symbols a request, so 5,942
symbols take 298 requests. On Oct 20 2026 that took 145 seconds with the
polite pause (0.3 s). Liquidity comes from the spark meta: last price at
least `--min-price` and last session's volume at least `--min-volume`. Run it
before the open or after the close: during the session the volume is the
day's so far, and today's daily bar is left out until 4:00 PM.

The setups are computed from daily closes only (spark has no highs or lows),
so they are close cousins of the reel's `refs/scan.py`, which used highs and
lows:

| setup | the rule on closes |
| --- | --- |
| `breakout_20d` | the last close is above every close of the 20 sessions before it |
| `bull_flag` | up more than 10 % over the 10 sessions before the last 5, then the last 5 closes inside a 5 % range |
| `reclaim_ma20` | the close before was under its 20-day average, the last close is above it |
| `oversold` | RSI 14 (Wilder) under 30 |
| `oversold_bounce` | RSI 14 was under 30 yesterday and today closed up |

A closing-high breakout fires more often than an intraday-high one (KO on
Oct 16 broke its 20-day closing high, not its 20-day intraday high). Hits are
listed most traded first (price times volume).

## The opening-range breakout scan (during the session)

The opening range is the first `--or-minutes` (15) of the session: the 9:15,
9:20 and 9:25 five-minute bars. A hit is the first completed 5-minute bar
to CLOSE above the range high, at that bar's close time.

1. Stage 1, every symbol: spark closes of today's 5-minute bars, 20 a
   request. A chart goes on only if a completed bar after the range closed at
   or above the highest close of the range. That is a necessary condition
   (the range high is at least every range close), so no breakout is lost.
2. Stage 2, each candidate: the v8 chart with real highs and lows, one
   request each. Range high = the highest high of the range bars, range low =
   the lowest low. On a strong morning most charts are candidates, so stage 2
   checks at most `--max-confirm` (200) of them, the most traded first (price
   times volume so far), and prints PARTIAL with the count it skipped.
   `--max-confirm 0` checks them all.

Timing, live on Tue Oct 20 2026 (a strong morning): 100 liquid names at
10:01 AM took 35 seconds (5 spark requests, 70 v8 charts, 51 of 91 usable
charts broke out). The whole universe at 10:03 AM took about 4 minutes (298
spark requests, then 200 v8 charts): 2,448 usable charts, 1,782 candidates,
the 200 most traded checked, 119 of those broke out. For a fast answer, scan
the daily watchlist or a list of names you trade (`--watchlist`, `--symbols`).

A chart is usable only when every 5-minute bar from 9:15 to the cutoff is
there; a missing bar means a halt or a thin stock. Null closes are dropped,
a bar off the 5-minute grid (the live tick, like 10:58:07) is dropped, and a
bar counts only once it is complete (start + 5 minutes). Before 9:50 AM, on a
weekend or holiday, after the close, or after `no_entries_after` (an expired
setup) it prints one plain line and writes nothing. The 1:00 PM early closes
are in the calendar.

## Data and limits

- Yahoo's chart and spark endpoints are free, unofficial and can lag. Bars are
  5-minute bars, bar by bar, never tick by tick. query2 first, query1 on a 429
  or 5xx, one retry after a 5-second wait on a 429.
- Partial results are said as partial: "Fetched 4,980 of 5,259 charts (279
  failed or had no data)". Never round a partial scan up to "the whole market".
- NSE holidays and early closes for 2026 and 2027 (nseindia.com, read 2026-10-13).

## Steps

1. Once a week or so: `scan.py universe`.
2. Before the open: `scan.py daily`. Tell the user the counts (fetched,
   liquid, scanned, hits) and the top few by setup.
3. After 9:50 AM IST (10:15 is the classic): `scan.py orb`. Tell the user how
   many usable charts broke their range and when, and that a later hit is
   closer to the price now.
4. The user picks one chart. Hand it on: `/trader-news TICKER` (what is moving
   it), then `/trader-entry TICKER` (the entry bar by bar). Never pick for them.

## Example: the reel

Monday Oct 19 2026, scan at 10:15 AM over the reel's 234-ticker wall
(`tests/fixtures/trader-scanner/wall5m-2026-10-19.json.gz`, real Yahoo charts):

```
python3 scan.py orb --offline wall5m-2026-10-19.json.gz --now "2026-10-19 10:15" --min-price 0
Fetched 233 of 234 charts (1 failed or had no data); 231 usable; 95 candidates, 95 confirmed with real highs and lows.
42 of 231 charts closed above their opening-range high by 10:15 AM:
   9:50 AM  AMC         $2.97  range 2.90 to 2.96  +0.50% over
  ...
  10:15 AM  RELIANCE.NS      $364.18  range 354.47 to 362.18  +0.55% over
```

The reel's wall had no price floor (AMC at $2.97 is one of the 42), hence
`--min-price 0`; with the default $5 floor it is 41. RELIANCE.NS's range is the 9:15
to 9:40 bars, high 362.18, low 354.47; the 10:10 bar closed at 364.18, 0.55 %
over the high, at 10:15 AM. The user picks RELIANCE.NS and Claude hands it to
`/trader-news RELIANCE.NS`, then `/trader-entry RELIANCE.NS`. In the reel the universe was
5,259 US stocks; this tool's rule gives 5,943 on the same files.

The pre-market scan that morning (closes through Fri Oct 16, the reel's daily
charts) tags BLK, CI, XOM and HD a 20-day breakout, CCL a bull flag, F, JPM
and GE a reclaim of the 20-day average, and BAC, MS, RIVN and PLUG oversold,
as the reel did. On closes it also tags KO (breakout), RCL (flag) and PNC (an
oversold bounce).

## Rules

- Say what was scanned: how many symbols, how many charts came back, how many
  were usable, and the time of the data.
- Say "matched a rule", never "a buy", "a winner" or "a good trade".
- Never print a P&L, a return or a profit figure.
- A hit is stale once the price has moved on. Re-run before acting on it.

## What it never does

It never places, sizes or checks an order, never says which stock to buy,
never calls data real time, and never promises that a setup works.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Paper trading by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order except trader-broker, and only when all three hold: trader-risk
  passed that exact order today, the user typed an explicit yes for that one order in the chat, and the
  user clicked Allow once on Claude's own card because the order tool is set to "Needs approval"
  (Customize > Connectors > tool permissions). Never set an order tool to "Always allow".
- No options, margin, short selling or leverage unless the config allows it and the user confirms.
- Broker keys live in environment variables or the Claude Desktop config, never in the chat.
