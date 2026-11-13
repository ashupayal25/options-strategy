"""Builds the daily text report and the notification events (entry ticket, exit alerts, daily summary)."""
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .regime import RegimeParams, build
from .strategy import NAMES, first_call_exit, is_entry_day, next_expiry, strikes, symbol


@dataclass
class Event:
    kind: str  # "entry", "exit" or "summary"
    text: str
    urgent: bool = False


@dataclass
class Report:
    text: str
    events: list = field(default_factory=list)
    live_today: bool = False
    entry_day: bool = False


def build_report(today, cfg, nifty, vix, positions, *, entry_day="auto", spot=None, expiry=None, now=None, notes=()):
    p = RegimeParams(confirm=cfg.confirm)
    df_done = build(nifty[nifty.index.date < today], vix[vix.index.date < today], p)
    df_live = build(nifty[nifty.index.date <= today], vix[vix.index.date <= today], p)
    completed = [d.date() for d in df_done.index]
    live_today = df_live.index[-1].date() == today
    now = now or datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"SIGNAL REPORT (no orders are placed)  |  run {now}  |  report date {today}  |  data: Yahoo ^NSEI, ^INDIAVIX"
    L = [title, ""]
    L += [*notes, ""] if notes else []

    last = df_done.iloc[-1]
    reg_prior, reg_prior_prev = int(last.reg), int(df_done.reg.iloc[-2])
    head = [f"Last completed close: {completed[-1]}  Nifty {last.Close:,.1f}  |  regime {NAMES[reg_prior]} (previous day {NAMES[reg_prior_prev]})",
            f"  ADX {last.adx:.1f}  RSI {last.rsi:.1f}  VIX {last.vix:.1f} (50-day avg {last.vixavg:.1f})  SMA50 {last.sma50:,.0f}  SMA200 {last.sma200:,.0f}"]
    if live_today:
        cur = df_live.iloc[-1]
        head.append(f"Live bar today ({today}): Nifty {cur.Close:,.1f}  |  regime now {NAMES[int(cur.reg)]}  RSI {cur.rsi:.1f}   (provisional until the 3:30 PM close)")
    head.append("Last 6 regimes: " + ", ".join(f"{d.strftime('%d-%b')} {NAMES[int(r)][:4]}" for d, r in df_done.reg.tail(6).items()))
    L += head + [""]

    entry = entry_day == "yes" or (entry_day == "auto" and is_entry_day(today, completed, cfg.expiry_weekday))
    A = ["== A. ENTRY TODAY? == " + ("YES - today is the day after weekly expiry" if entry else "no (next entry is the day after the next weekly expiry)")]
    if entry:
        ref = spot or last.Close
        exp = datetime.strptime(expiry, "%Y-%m-%d").date() if expiry else next_expiry(today, cfg.expiry_weekday)
        qty = cfg.lots * cfg.lot_size
        A.append(f"Decision uses the prior close ({completed[-1]}): regime {NAMES[reg_prior]}, RSI {last.rsi:.1f}. Strikes from spot {ref:,.1f}"
                 + (" (prior close; pass --spot with the live price to recompute)" if not spot else " (your --spot)"))
        A.append(f"Contract expiry used: {exp} (verify in the option chain; a holiday moves it earlier)")
        if not live_today:
            A.append("WARNING: no bar for today yet (holiday or data delay). Confirm the market is open before trading.")
        side = None
        if reg_prior == 1:
            if last.rsi > cfg.rsi_skip:
                A.append(f"-> BULLISH but prior-close RSI {last.rsi:.2f} > {cfg.rsi_skip:.0f}: SKIP the put trade this week.")
            else:
                side = "PE"
        elif reg_prior == -1:
            side = "CE"
        elif reg_prior == 0:
            A.append("-> SIDEWAYS: stay out (sell-sideways is off)." if not cfg.sell_sideways else "-> SIDEWAYS: sell-sideways is on but not supported by this script yet; stay out.")
        else:
            A.append("-> NO TRADE regime: no new position.")
        if side:
            short, hedge = strikes(ref, side, cfg)
            name = "PUT spread (bull put)" if side == "PE" else "CALL spread (bear call)"
            A += [f"-> {name}, {cfg.lots} lots x {cfg.lot_size} = {qty} units",
                  f"   1) BUY  {qty} {symbol(exp, hedge, side)}   (hedge, margin relief; place first, limit order)",
                  f"   2) SELL {qty} {symbol(exp, short, side)}   (short; place after the hedge fills, limit order)",
                  f"   Short is {abs(short / ref - 1) * 100:.1f}% from spot, hedge {abs(hedge / short - 1) * 100:.1f}% beyond the short; width {abs(short - hedge)} points",
                  "   Before placing: check the short strike has open interest and a tight bid-ask, check the basket margin in Kite, and confirm the symbol and expiry in the chain.",
                  ("   Exit rule: HOLD TO EXPIRY (no stop). If Nifty closes below the hedge strike the loss is capped at (width - credit) x %d = about Rs %s before the credit." %
                   (qty, f"{abs(short - hedge) * qty:,.0f}")) if side == "PE" else
                  "   Exit rule: exit BOTH legs if the regime turns bullish or no-trade (checked at 3:20 PM each day).",
                  f"   After you trade, record it:  otm record --side {side} --short {short} --hedge {hedge} --expiry {exp} --lots {cfg.lots}"]
    L += A + [""]

    events = []
    if entry:
        events.append(Event("entry", "\n".join([f"NIFTY OTM - ENTRY DAY {today}", *notes, *head, "", *A])))

    L.append("== B. OPEN POSITIONS: EXIT CHECK ==")
    status, exit_count = [], 0
    if not positions:
        L.append("No positions recorded.")
    for r in positions:
        exp = datetime.strptime(r["expiry"], "%Y-%m-%d").date()
        entered = datetime.strptime(r["entry_date"], "%Y-%m-%d").date()
        kind = "PUT" if r["side"] == "PE" else "CALL"
        pos_head = f"#{r['id']} {kind} spread  short {r['short']} / hedge {r['hedge']}  expiry {exp}  lots {r['lots']}  entered {entered}"
        if exp < today:
            L.append(f"{pos_head}\n   EXPIRED: remove it with  otm close --id {r['id']}")
            status.append(f"#{r['id']} {kind}: expired, remove it")
            continue
        spot_now = df_live.iloc[-1].Close
        dist = (spot_now / r["short"] - 1) * 100
        pl = [pos_head, f"   Nifty {spot_now:,.1f} is {dist:+.1f}% vs the short strike; {(exp - today).days} days to expiry; regime {NAMES[int(df_live.iloc[-1].reg)]}"]
        if r["side"] == "PE":
            pl.append("   HOLD (puts are held to expiry; no exit rule). Hedge caps the loss.")
            status.append(f"#{r['id']} PUT {r['short']}/{r['hedge']}: hold ({dist:+.1f}% vs short)")
        else:
            flip = first_call_exit(df_live.reg, entered)
            if flip is not None:
                n = r["lots"] * cfg.lot_size
                pl += [f"   >>> EXIT NOW: regime change on {flip.date()} ({NAMES[int(df_live.reg.loc[flip])]}).",
                       f"       1) BUY BACK {n} {symbol(exp, r['short'], 'CE')}  (short)",
                       f"       2) SELL     {n} {symbol(exp, r['hedge'], 'CE')}  (hedge)",
                       f"       then:  otm close --id {r['id']}"]
                events.append(Event("exit", "\n".join([f"NIFTY OTM - EXIT CALL SPREAD #{r['id']} NOW", *pl]), urgent=True))
                status.append(f"#{r['id']} CALL {r['short']}/{r['hedge']}: EXIT")
                exit_count += 1
            else:
                pl.append("   HOLD (no regime exit yet).")
                status.append(f"#{r['id']} CALL {r['short']}/{r['hedge']}: hold ({dist:+.1f}% vs short)")
        L += pl
    L += ["", "Notes: the rules were backtested with settlement-price fills, not live fills; paper trade and compare. Not financial advice."]

    summary = [f"NIFTY OTM - daily check {today}", *notes,
               f"Regime (last close {completed[-1]}): {NAMES[reg_prior]}  RSI {last.rsi:.1f}  VIX {last.vix:.1f}"]
    if live_today:
        summary.append(f"Live: Nifty {df_live.iloc[-1].Close:,.1f}  regime now {NAMES[int(df_live.iloc[-1].reg)]}")
    summary.append(f"Open positions: {len(positions)}  |  exit alerts: {exit_count}")
    summary += [f"  {s}" for s in status]
    events.append(Event("summary", "\n".join(summary)))
    return Report("\n".join(L), events, live_today, entry)
