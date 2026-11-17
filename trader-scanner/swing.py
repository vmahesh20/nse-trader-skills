#!/usr/bin/env python3
"""Swing mode for NSE stocks (Yahoo .NS daily bars). Standard library only.

    python3 swing.py scan                         # after 15:30 or before 9:15: swing setups -> trader/watchlist.json
    python3 swing.py scan --symbols RELIANCE.NS,TCS.NS --limit 100
    python3 swing.py plan RELIANCE.NS --write     # entry above yesterday's high, swing stop, 2R -> trader/plan.json
    python3 swing.py open RELIANCE.NS --qty 20 --entry 1415 --stop 1380 --target 1485
    python3 swing.py positions                    # open swings: days held, R so far, distance to stop
    python3 swing.py trail --write                # move stops up (ma20 / low10) and flag time stops
    python3 swing.py close RELIANCE.NS --price 1480
    python3 swing.py check RELIANCE.NS            # swing limits: open positions, sector cap, market filter
    python3 swing.py backtest                     # every past signal, next-day entry, R per setup

Setups (completed daily bars only; today's bar counts after 15:30 IST):
  high_52w        close above the highest high of the prior 250 sessions, volume >= 1.5x its 50-day average
  pullback_20     uptrend (SMA20 > SMA50 > SMA200), the day's low touched the 20-day average, closed back above it
  pullback_50     uptrend (SMA50 > SMA200), low touched the 50-day average, closed above it but below the 20
  momentum_burst  up 4%+ on volume above the 50-day average and above the day before, the day before was
                  not a burst, close in the top 30% of the day's range; a likely upper-circuit close is skipped
  rs_leader       63/126-day return vs Nifty 50 in the top 20% of the scan, close above the 50-day average
Every hit also carries: sector (NSE industry) and whether that sector is a top-3 leader this month
(median 21-day return of its stocks), and the market filter: Nifty 50 above a rising 50-day average.

Liquidity: last close >= --min-price (50) and 50-day average volume >= --min-volume (500000).
Data: https://query2.finance.yahoo.com/v8/finance/chart/<SYM>?range=2y&interval=1d, cached per day in
trader/cache/daily/. --offline DIR reads <SYM>.json v8 files instead (^NSEI.json for the index).

The backtest uses today's universe (survivorship bias), next-day entry above the signal day's high,
the same stop/target rule as `plan`, a --time-stop (10) day limit, stop first if a day hits both, and
--cost-pct (0.2) round-trip charges. It is a check on a rule, not a promise.
"""

import argparse
import datetime
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
HOSTS = ("https://query2.finance.yahoo.com", "https://query1.finance.yahoo.com")
INDEX = "^NSEI"
TICK = 0.05
IST = datetime.timedelta(hours=5, minutes=30)
DAILY_DONE = datetime.time(15, 30)
NSE_HOLIDAYS = {
    "2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31", "2026-04-03", "2026-04-14",
    "2026-05-01", "2026-05-28", "2026-06-26", "2026-09-14", "2026-10-02", "2026-10-20", "2026-11-10",
    "2026-11-24", "2026-12-25",
}
SETUPS = ("high_52w", "pullback_20", "pullback_50", "momentum_burst", "rs_leader")


class SwingError(Exception):
    pass


# ---------------------------------------------------------------- clock

def now_ist(text=None):
    if text:
        return datetime.datetime.fromisoformat(text.strip())
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + IST


def trading_day(d):
    return d.weekday() < 5 and d.isoformat() not in NSE_HOLIDAYS


def next_trading_day(d):
    d += datetime.timedelta(days=1)
    while not trading_day(d):
        d += datetime.timedelta(days=1)
    return d


def plan_date(now):
    """The session the order is for: today during market hours, else the next trading day."""
    d = now.date()
    if trading_day(d) and now.time() < datetime.time(15, 15):
        return d
    return next_trading_day(d)


# ---------------------------------------------------------------- numbers

def tick_down(x):
    return round(math.floor(x / TICK + 1e-9) * TICK, 2)


def tick_up(x):
    return round(math.ceil(x / TICK - 1e-9) * TICK, 2)


def tick(x):
    return round(round(x / TICK) * TICK, 2)


def sma(xs, n, end=None):
    end = len(xs) if end is None else end
    if end < n:
        return None
    return sum(xs[end - n:end]) / float(n)


def atr(b, n=14, end=None):
    end = len(b["c"]) if end is None else end
    if end < n + 1:
        return None
    trs = []
    for i in range(end - n, end):
        h, l, pc = b["h"][i], b["l"][i], b["c"][i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / n


def ret(xs, n, end=None):
    end = len(xs) if end is None else end
    if end <= n or not xs[end - 1 - n]:
        return None
    return xs[end - 1] / xs[end - 1 - n] - 1.0


# ---------------------------------------------------------------- data

def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def parse_chart(text, sym):
    doc = json.loads(text) if isinstance(text, str) else text
    res = ((doc.get("chart") or {}).get("result") or [None])[0]
    if not res:
        err = (doc.get("chart") or {}).get("error") or {}
        raise SwingError("%s: no data (%s)" % (sym, err.get("description") or "empty"))
    q = (res.get("indicators") or {}).get("quote", [{}])[0]
    out = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    for i, ts in enumerate(res.get("timestamp") or []):
        row = [q.get(k, [None] * (i + 1))[i] if i < len(q.get(k) or []) else None for k in ("open", "high", "low", "close", "volume")]
        if None in row[:4]:
            continue
        d = (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=int(ts)) + IST).date().isoformat()
        if out["t"] and out["t"][-1] == d:  # live tick duplicate: keep the latest
            for k in "ohlcv":
                out[k].pop()
            out["t"].pop()
        out["t"].append(d)
        for k, v in zip("ohlcv", row):
            out[k].append(float(v or 0))
    return out


def complete_only(b, now):
    """Drop today's bar until the NSE daily candle closes (15:30 IST)."""
    today = now.date().isoformat()
    if b["t"] and b["t"][-1] == today and now.time() < DAILY_DONE:
        b = {k: v[:-1] for k, v in b.items()}
    return b


class Loader:
    def __init__(self, cache="trader/cache/daily", offline=None, pause=0.25, now=None):
        self.cache, self.offline, self.pause, self.now = cache, offline, pause, now or now_ist()
        self.errors = []

    def get(self, sym):
        if self.offline:
            p = os.path.join(self.offline, sym + ".json")
            if not os.path.exists(p):
                raise SwingError("%s: no offline file" % sym)
            with open(p, encoding="utf-8") as fh:
                return complete_only(parse_chart(fh.read(), sym), self.now)
        stamp = self.now.strftime("%Y-%m-%d") + ("-close" if self.now.time() >= DAILY_DONE else "")
        cp = os.path.join(self.cache, sym.replace("^", "_") + ".json")
        if os.path.exists(cp):
            try:
                with open(cp, encoding="utf-8") as fh:
                    doc = json.load(fh)
                if doc.get("stamp") == stamp:
                    return complete_only(doc["bars"], self.now)
            except (ValueError, KeyError):
                pass
        path = "/v8/finance/chart/%s?range=2y&interval=1d" % urllib.parse.quote(sym)
        last = None
        for host in HOSTS:
            try:
                bars = parse_chart(http_get(host + path), sym)
                break
            except urllib.error.HTTPError as e:
                last = "HTTP %d" % e.code
                if e.code == 429:
                    time.sleep(3)
            except (urllib.error.URLError, OSError, ValueError) as e:
                last = str(getattr(e, "reason", e))
        else:
            raise SwingError("%s: Yahoo %s" % (sym, last))
        os.makedirs(self.cache, exist_ok=True)
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump({"stamp": stamp, "bars": bars}, fh)
        if self.pause:
            time.sleep(self.pause)
        return complete_only(bars, self.now)


def read_universe(path):
    """trader/universe.txt lines SYM|Name|Industry -> [(sym, industry)]."""
    if not os.path.exists(path):
        raise SwingError("no %s: run scan.py universe first (or pass --symbols)" % path)
    out = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                parts = ln.split("|")
                out.append((parts[0].strip().upper(), parts[2].strip() if len(parts) > 2 else ""))
    return out


def read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, doc):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------- setups

def liquid(b, end, min_price, min_volume):
    if end < 60:
        return False
    av = sma(b["v"], 50, end)
    return b["c"][end - 1] >= min_price and (av or 0) >= min_volume


def setups_at(b, end):
    """Setups that fired on bar end-1 (end = number of bars visible)."""
    if end < 210:
        return []
    c, h, l, v = b["c"], b["h"], b["l"], b["v"]
    i = end - 1
    out = []
    s20, s50, s200 = sma(c, 20, end), sma(c, 50, end), sma(c, 200, end)
    av50 = sma(v, 50, end - 1) or 0
    if end > 252 and c[i] > max(h[i - 250:i]) and v[i] >= 1.5 * av50:
        out.append("high_52w")
    if s20 and s50 and s200 and s20 > s50 > s200:
        if l[i] <= s20 * 1.01 and c[i] > s20:
            out.append("pullback_20")
    if s50 and s200 and s50 > s200 and l[i] <= s50 * 1.01 and c[i] > s50 and (s20 is None or c[i] < s20):
        out.append("pullback_50")
    chg = c[i] / c[i - 1] - 1.0
    prev = c[i - 1] / c[i - 2] - 1.0
    rng = h[i] - l[i]
    upper = rng > 0 and (c[i] - l[i]) / rng >= 0.7
    circuit = chg >= 0.095 and abs(c[i] - h[i]) < 1e-6
    if chg >= 0.04 and prev < 0.04 and v[i] > av50 and v[i] > v[i - 1] and upper and not circuit:
        out.append("momentum_burst")
    return out


def rs_score(b, idx, end=None):
    """Weighted 63/126-day return minus Nifty's over the same window."""
    end = len(b["c"]) if end is None else end
    r63, r126 = ret(b["c"], 63, end), ret(b["c"], 126, end)
    if r63 is None or r126 is None:
        return None
    n = len(idx["c"])
    i63, i126 = ret(idx["c"], 63, n), ret(idx["c"], 126, n)
    if i63 is None or i126 is None:
        return None
    return 0.6 * (r63 - i63) + 0.4 * (r126 - i126)


def market_filter(idx):
    c = idx["c"]
    s50, s50_prev = sma(c, 50), sma(c, 50, len(c) - 5)
    if s50 is None or s50_prev is None:
        return {"state": "unknown", "nifty": c[-1] if c else None}
    on = c[-1] > s50 and s50 > s50_prev
    return {"state": "risk-on" if on else "caution", "nifty": round(c[-1], 2), "sma50": round(s50, 2),
            "note": "Nifty above a rising 50-day average" if on else
                    "Nifty below its 50-day average or the average is falling: smaller size or fewer new swings"}


# ---------------------------------------------------------------- plan

def make_plan(b, end=None, atr_mult=2.0, target_r=2.0):
    """Entry a tick above the signal day's high; stop under the 10-day low, no wider than atr_mult x ATR."""
    end = len(b["c"]) if end is None else end
    i = end - 1
    a = atr(b, 14, end)
    if a is None:
        raise SwingError("not enough bars for ATR")
    entry = tick_up(b["h"][i] + TICK)
    low10 = min(b["l"][end - 10:end])
    by_atr = low10 < entry - atr_mult * a
    stop = tick_down(max(low10, entry - atr_mult * a) - TICK)
    if stop >= entry:
        raise SwingError("stop %.2f is not below entry %.2f" % (stop, entry))
    risk = entry - stop
    target = tick(entry + target_r * risk)
    return {"entry": entry, "stop": stop, "target": target, "risk_per_share": round(risk, 2),
            "reward_risk": round((target - entry) / risk, 2), "atr14": round(a, 2), "low10": round(low10, 2),
            "stop_label": ("%.1fx ATR under the entry (the 10-day low %.2f is further)" % (atr_mult, low10)) if by_atr
                          else "under the 10-day low %.2f" % low10}


# ---------------------------------------------------------------- commands

def cmd_scan(a):
    now = now_ist(a.now)
    ld = Loader(offline=a.offline, pause=a.pause, now=now)
    if a.symbols:
        uni = [(s.strip().upper(), "") for s in a.symbols.split(",") if s.strip()]
    else:
        uni = read_universe(a.universe)
    if a.limit:
        uni = uni[:a.limit]
    idx = ld.get(INDEX)
    mf = market_filter(idx)
    data, fails = {}, []
    for k, (sym, ind) in enumerate(uni):
        try:
            data[sym] = (ld.get(sym), ind)
        except SwingError as e:
            fails.append(str(e))
        if not a.json and (k + 1) % 50 == 0:
            print("  fetched %d of %d" % (k + 1, len(uni)), file=sys.stderr)
    # sector strength: median 21-day return of each industry's stocks
    by_ind = {}
    for sym, (b, ind) in data.items():
        r = ret(b["c"], 21)
        if ind and r is not None:
            by_ind.setdefault(ind, []).append(r)
    sectors = sorted(((ind, statistics.median(rs)) for ind, rs in by_ind.items() if len(rs) >= 3),
                     key=lambda x: -x[1])
    leaders = {ind for ind, _ in sectors[:3]}
    scores = {}
    for sym, (b, ind) in data.items():
        if liquid(b, len(b["c"]), a.min_price, a.min_volume):
            s = rs_score(b, idx)
            if s is not None:
                scores[sym] = s
    cut = sorted(scores.values(), reverse=True)[max(0, int(len(scores) * 0.2) - 1)] if scores else None
    hits = []
    for sym, (b, ind) in data.items():
        end = len(b["c"])
        if not liquid(b, end, a.min_price, a.min_volume):
            continue
        found = setups_at(b, end)
        s50 = sma(b["c"], 50)
        if cut is not None and sym in scores and scores[sym] >= cut and s50 and b["c"][-1] > s50:
            found.append("rs_leader")
        if a.setup:
            found = [f for f in found if f in a.setup.split(",")]
        if not found:
            continue
        try:
            p = make_plan(b, atr_mult=a.atr_mult)
        except SwingError:
            p = {}
        hits.append({"symbol": sym, "setups": found, "close": round(b["c"][-1], 2), "date": b["t"][-1],
                     "sector": ind, "sector_leader": ind in leaders,
                     "rs": round(scores[sym] * 100, 1) if sym in scores else None, "plan": p})
    hits.sort(key=lambda h: (-len(h["setups"]), -(h["sector_leader"]), -(h["rs"] or -999)))
    doc = {"mode": "swing", "as_of": now.isoformat(timespec="minutes"), "market": mf,
           "leading_sectors": [{"sector": s, "median_21d_pct": round(r * 100, 1)} for s, r in sectors[:5]],
           "scanned": len(data), "failed": len(fails), "hits": hits, "source": "yahoo"}
    if not a.no_write:
        write_json(a.out, doc)
    if a.json:
        print(json.dumps(doc, indent=2))
        return 0 if hits else 1
    print("Market: %s (Nifty %s)%s" % (mf["state"].upper(), mf.get("nifty"), ". " + mf["note"] if mf.get("note") else ""))
    if sectors:
        print("Leading sectors (median 21-day): " + ", ".join("%s %+.1f%%" % (s, r * 100) for s, r in sectors[:3]))
    print("Scanned %d (%d failed). %d swing setups:" % (len(data), len(fails), len(hits)))
    for h in hits[:a.top]:
        p = h["plan"]
        print("  %-14s %-34s close %8.2f  RS %6s  %s%s" % (
            h["symbol"], ",".join(h["setups"]), h["close"], h["rs"] if h["rs"] is not None else "-",
            h["sector"] or "-", " *leader" if h["sector_leader"] else ""))
        if p:
            print("      plan: buy above %.2f, stop %.2f, target %.2f (risk %.2f/share)" % (
                p["entry"], p["stop"], p["target"], p["risk_per_share"]))
    if fails:
        print("Failed: " + "; ".join(fails[:5]) + (" ..." if len(fails) > 5 else ""))
    if not a.no_write:
        print("Wrote %s. A scan is a list of charts, not a list of buys. Next: swing.py plan SYMBOL --write." % a.out)
    return 0 if hits else 1


def cmd_plan(a):
    now = now_ist(a.now)
    ld = Loader(offline=a.offline, pause=0, now=now)
    sym = a.symbol.upper()
    b = ld.get(sym)
    p = make_plan(b, atr_mult=a.atr_mult, target_r=a.target_r)
    found = setups_at(b, len(b["c"]))
    plan = {"mode": "swing", "symbol": sym, "side": "buy", "date": a.date or plan_date(now).isoformat(),
            "setup": a.setup or (found[0] if found else "swing"), "entry": p["entry"], "stop": p["stop"],
            "stop_rule": "10-day low, max %.1fx ATR" % a.atr_mult, "stop_label": p["stop_label"],
            "target": p["target"], "target_r": a.target_r, "target_label": "%gR" % a.target_r,
            "risk_per_share": p["risk_per_share"], "reward_risk": p["reward_risk"], "flat_by": None,
            "trail": a.trail, "time_stop_days": a.time_stop, "entry_type": "buy above the signal day's high",
            "signal_day": b["t"][-1], "atr14": p["atr14"]}
    if a.write:
        write_json(a.write, plan)
    if a.json:
        print(json.dumps(plan, indent=2))
        return 0
    print("SWING PLAN %s for %s (signal day %s, %s)" % (sym, plan["date"], plan["signal_day"], plan["setup"]))
    print("  Entry   %.2f  buy above the signal day's high (a buy-stop / SL order)" % plan["entry"])
    print("  Stop    %.2f  %s (ATR14 %.2f)" % (plan["stop"], plan["stop_label"], plan["atr14"]))
    print("  Target  %.2f  %s" % (plan["target"], plan["target_label"]))
    print("  Risk    %.2f a share; reward:risk %.2f" % (plan["risk_per_share"], plan["reward_risk"]))
    print("  Hold    trail by %s, time stop after %d sessions without 1R" % (a.trail, a.time_stop))
    if a.write:
        print("Wrote %s. Next: /trader-budget, /trader-risk, /trader-broker (CNC + OCO exit)." % a.write)
    return 0


def load_swings(path):
    return read_json(path, {"open": [], "closed": []})


def cmd_open(a):
    st = load_swings(a.state)
    sym = a.symbol.upper()
    if any(p["symbol"] == sym for p in st["open"]):
        raise SwingError("%s is already open; close it first" % sym)
    if a.stop >= a.entry:
        raise SwingError("stop must be below entry")
    now = now_ist(a.now)
    st["open"].append({"symbol": sym, "qty": a.qty, "entry": a.entry, "stop": tick_down(a.stop),
                       "initial_stop": tick_down(a.stop), "target": tick(a.target) if a.target else None,
                       "opened": a.date or now.date().isoformat(), "trail": a.trail, "time_stop_days": a.time_stop,
                       "sector": a.sector or ""})
    write_json(a.state, st)
    print("Opened swing %s: %d @ %.2f, stop %.2f%s." % (sym, a.qty, a.entry, a.stop,
                                                        (", target %.2f" % a.target) if a.target else ""))
    return 0


def sessions_between(d0, d1):
    d, n = datetime.date.fromisoformat(d0), 0
    end = datetime.date.fromisoformat(d1)
    while d < end:
        d += datetime.timedelta(days=1)
        if trading_day(d):
            n += 1
    return n


def review(a, write):
    now = now_ist(a.now)
    ld = Loader(offline=a.offline, pause=0, now=now)
    st = load_swings(a.state)
    rows = []
    for p in st["open"]:
        try:
            b = ld.get(p["symbol"])
        except SwingError as e:
            rows.append((p, None, str(e)))
            continue
        last = b["c"][-1]
        risk0 = p["entry"] - p["initial_stop"]
        r_now = (last - p["entry"]) / risk0 if risk0 > 0 else 0
        held = sessions_between(p["opened"], b["t"][-1])
        new_stop = p["stop"]
        if p.get("trail") == "low10":
            cand = tick_down(min(b["l"][-10:]) - TICK)
        else:
            s20 = sma(b["c"], 20)
            cand = tick_down(s20 - TICK) if s20 and last > s20 else p["stop"]
        if cand > new_stop and cand < last:
            new_stop = cand
        notes = []
        if new_stop > p["stop"]:
            notes.append("TRAIL: raise stop %.2f -> %.2f (modify the GTT / Forever order)" % (p["stop"], new_stop))
        if last <= p["stop"]:
            notes.append("STOP HIT: last close %.2f is at or under the stop" % last)
        if held >= int(p.get("time_stop_days") or 10) and r_now < 1.0:
            notes.append("TIME STOP: %d sessions and only %.2fR: exit or tighten" % (held, r_now))
        rows.append((p, {"last": last, "r": r_now, "held": held, "new_stop": new_stop,
                         "to_stop_pct": (last / p["stop"] - 1) * 100}, notes))
        if write:
            p["stop"] = new_stop
    if write:
        write_json(a.state, st)
    return rows


def print_rows(rows):
    if not rows:
        print("No open swings (swing.py open SYMBOL ... after a fill).")
        return
    for p, m, notes in rows:
        if m is None:
            print("%-14s  data error: %s" % (p["symbol"], notes))
            continue
        print("%-14s qty %-5d entry %8.2f  last %8.2f  %+5.2fR  held %2d  stop %8.2f (%.1f%% away)" % (
            p["symbol"], p["qty"], p["entry"], m["last"], m["r"], m["held"], p["stop"], m["to_stop_pct"]))
        for n in notes:
            print("    " + n)


def cmd_positions(a):
    print_rows(review(a, write=False))
    return 0


def cmd_trail(a):
    rows = review(a, write=a.write)
    print_rows(rows)
    if a.write:
        print("Saved new stops to %s." % a.state)
    return 0


def cmd_close(a):
    st = load_swings(a.state)
    sym = a.symbol.upper()
    keep = [p for p in st["open"] if p["symbol"] != sym]
    gone = [p for p in st["open"] if p["symbol"] == sym]
    if not gone:
        raise SwingError("%s is not open" % sym)
    p = gone[0]
    risk0 = p["entry"] - p["initial_stop"]
    r = (a.price - p["entry"]) / risk0 if risk0 > 0 else 0
    p.update({"exit": a.price, "closed": a.date or now_ist(a.now).date().isoformat(), "r": round(r, 2),
              "pnl": round((a.price - p["entry"]) * p["qty"], 2)})
    st["open"], st["closed"] = keep, st.get("closed", []) + [p]
    write_json(a.state, st)
    print("Closed %s @ %.2f: %+.2fR, P&L Rs %s." % (sym, a.price, r, "{:,.2f}".format(p["pnl"])))
    closed = st["closed"]
    wins = [c for c in closed if c["r"] > 0]
    print("Journal: %d closed, win rate %.0f%%, average %+.2fR." % (
        len(closed), 100.0 * len(wins) / len(closed), sum(c["r"] for c in closed) / len(closed)))
    return 0


def cmd_check(a):
    """Swing-only limits on top of trader-risk: open positions, sector cap, market filter."""
    cfg = read_json(a.config, {})
    st = load_swings(a.state)
    sym = a.symbol.upper()
    max_open = int(cfg.get("max_open_swings", 5))
    max_sector = int(cfg.get("max_swings_per_sector", 2))
    blocks, warns = [], []
    if any(p["symbol"] == sym for p in st["open"]):
        blocks.append("%s is already an open swing" % sym)
    if len(st["open"]) >= max_open:
        blocks.append("%d open swings, your max_open_swings is %d" % (len(st["open"]), max_open))
    sector = a.sector
    if not sector:
        wl = read_json(a.watchlist, {})
        sector = next((h.get("sector") for h in wl.get("hits", []) if h.get("symbol") == sym), "")
    if sector:
        n = sum(1 for p in st["open"] if p.get("sector") == sector)
        if n >= max_sector:
            blocks.append("%d open swings already in %s, your max_swings_per_sector is %d" % (n, sector, max_sector))
    else:
        warns.append("sector unknown: pass --sector to check the sector cap")
    wl = read_json(a.watchlist, {})
    mk = (wl.get("market") or {}).get("state")
    if mk == "caution":
        warns.append("market filter is CAUTION (Nifty under a rising 50-day average): consider half size")
    warns.append("check the results date and NSE's ASM/GSM lists for %s before holding overnight" % sym)
    print("%s %s" % ("BLOCK" if blocks else "PASS", sym))
    for x in blocks:
        print("  block: " + x)
    for x in warns:
        print("  note: " + x)
    return 1 if blocks else 0


def simulate(b, i, plan, time_stop, cost_pct):
    """Signal on bar i; enter on i+1 if price trades above the entry. -> (R, days) or None."""
    n = len(b["c"])
    if i + 1 >= n:
        return None
    e, s, t = plan["entry"], plan["stop"], plan["target"]
    j = i + 1
    if b["h"][j] < e:
        return None  # never triggered next day
    fill = max(b["o"][j], e)
    risk = e - s
    cost_r = fill * cost_pct / 100.0 / risk
    for k in range(j, min(n, j + time_stop)):
        o, h, l = b["o"][k], b["h"][k], b["l"][k]
        if k > j and o <= s:
            return ((o - fill) / risk - cost_r, k - j + 1)
        if l <= s:
            return ((s - fill) / risk - cost_r, k - j + 1)
        if k > j and o >= t:
            return ((o - fill) / risk - cost_r, k - j + 1)
        if h >= t:
            return ((t - fill) / risk - cost_r, k - j + 1)
    k = min(n, j + time_stop) - 1
    return ((b["c"][k] - fill) / risk - cost_r, k - j + 1)


def cmd_backtest(a):
    now = now_ist(a.now)
    ld = Loader(offline=a.offline, pause=a.pause, now=now)
    if a.symbols:
        uni = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    else:
        uni = [s for s, _ in read_universe(a.universe)]
    if a.limit:
        uni = uni[:a.limit]
    want = a.setup.split(",") if a.setup else [s for s in SETUPS if s != "rs_leader"]
    res = {s: [] for s in want}
    for sym in uni:
        try:
            b = ld.get(sym)
        except SwingError:
            continue
        n = len(b["c"])
        last_sig = {}
        for end in range(252, n - 1):
            if not liquid(b, end, a.min_price, a.min_volume):
                continue
            for s in setups_at(b, end):
                if s not in res or end - last_sig.get(s, -99) < 5:  # one signal per setup per 5 sessions
                    continue
                try:
                    p = make_plan(b, end, atr_mult=a.atr_mult, target_r=a.target_r)
                except SwingError:
                    continue
                out = simulate(b, end - 1, p, a.time_stop, a.cost_pct)
                if out:
                    res[s].append(out)
                    last_sig[s] = end
    doc = {}
    for s, outs in res.items():
        if not outs:
            doc[s] = {"trades": 0}
            continue
        rs = [r for r, _ in outs]
        doc[s] = {"trades": len(rs), "win_pct": round(100.0 * sum(1 for r in rs if r > 0) / len(rs), 1),
                  "avg_r": round(sum(rs) / len(rs), 2), "median_r": round(statistics.median(rs), 2),
                  "avg_days": round(sum(d for _, d in outs) / len(outs), 1)}
    if a.json:
        print(json.dumps({"symbols": len(uni), "time_stop": a.time_stop, "target_r": a.target_r,
                          "cost_pct": a.cost_pct, "results": doc}, indent=2))
        return 0
    print("Backtest on %d symbols, ~2 years of daily bars, next-day entry above the signal high," % len(uni))
    print("stop under the 10-day low (max %.1fx ATR), target %gR, time stop %d sessions, costs %.2f%%." % (
        a.atr_mult, a.target_r, a.time_stop, a.cost_pct))
    print("%-16s %7s %7s %7s %8s %8s" % ("setup", "trades", "win%", "avg R", "median R", "avg days"))
    for s, d in doc.items():
        if d["trades"]:
            print("%-16s %7d %6.1f%% %+7.2f %+8.2f %8.1f" % (s, d["trades"], d["win_pct"], d["avg_r"],
                                                          d["median_r"], d["avg_days"]))
        else:
            print("%-16s %7d" % (s, 0))
    print("Avg R above 0 after costs = the rule had an edge on this data. Today's universe only "
          "(survivorship bias); past results are not a promise.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Swing mode for NSE stocks.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--now", help="IST time, e.g. \"2026-11-13 16:00\"")
        p.add_argument("--offline", metavar="DIR")
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("scan"); common(p)
    p.add_argument("--universe", default="trader/universe.txt")
    p.add_argument("--symbols")
    p.add_argument("--limit", type=int)
    p.add_argument("--setup", help="comma list: " + ",".join(SETUPS))
    p.add_argument("--min-price", type=float, default=50.0)
    p.add_argument("--min-volume", type=int, default=500000)
    p.add_argument("--atr-mult", type=float, default=2.0)
    p.add_argument("--pause", type=float, default=0.25)
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--out", default="trader/watchlist.json")
    p.add_argument("--no-write", action="store_true")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("plan"); common(p)
    p.add_argument("symbol")
    p.add_argument("--date")
    p.add_argument("--setup")
    p.add_argument("--atr-mult", type=float, default=2.0)
    p.add_argument("--target-r", type=float, default=2.0)
    p.add_argument("--trail", default="ma20", choices=["ma20", "low10"])
    p.add_argument("--time-stop", type=int, default=10)
    p.add_argument("--write", nargs="?", const="trader/plan.json")
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("open"); common(p)
    p.add_argument("symbol")
    p.add_argument("--qty", type=int, required=True)
    p.add_argument("--entry", type=float, required=True)
    p.add_argument("--stop", type=float, required=True)
    p.add_argument("--target", type=float)
    p.add_argument("--date")
    p.add_argument("--sector")
    p.add_argument("--trail", default="ma20", choices=["ma20", "low10"])
    p.add_argument("--time-stop", type=int, default=10)
    p.add_argument("--state", default="trader/swings.json")
    p.set_defaults(fn=cmd_open)

    for name, fn in (("positions", cmd_positions), ("trail", cmd_trail)):
        p = sub.add_parser(name); common(p)
        p.add_argument("--state", default="trader/swings.json")
        if name == "trail":
            p.add_argument("--write", action="store_true", help="save the raised stops")
        p.set_defaults(fn=fn)

    p = sub.add_parser("close"); common(p)
    p.add_argument("symbol")
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--date")
    p.add_argument("--state", default="trader/swings.json")
    p.set_defaults(fn=cmd_close)

    p = sub.add_parser("check"); common(p)
    p.add_argument("symbol")
    p.add_argument("--sector")
    p.add_argument("--config", default="trader/config.json")
    p.add_argument("--state", default="trader/swings.json")
    p.add_argument("--watchlist", default="trader/watchlist.json")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("backtest"); common(p)
    p.add_argument("--universe", default="trader/universe.txt")
    p.add_argument("--symbols")
    p.add_argument("--limit", type=int)
    p.add_argument("--setup")
    p.add_argument("--min-price", type=float, default=50.0)
    p.add_argument("--min-volume", type=int, default=500000)
    p.add_argument("--atr-mult", type=float, default=2.0)
    p.add_argument("--target-r", type=float, default=2.0)
    p.add_argument("--time-stop", type=int, default=10)
    p.add_argument("--cost-pct", type=float, default=0.2)
    p.add_argument("--pause", type=float, default=0.25)
    p.set_defaults(fn=cmd_backtest)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except SwingError as e:
        print("swing: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
