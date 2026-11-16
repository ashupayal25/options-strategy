"""Backtest matching Pine 'OTM Seller Regime System v2' defaults on real NSE bhav 2019-2026.

Rules (defaults):
- Regime: ADX/SMA/BB + DI confirmation, confirmBars=2
- Entry: day after weekly expiry; decision from PRIOR completed close (regime + RSI)
- Puts: 2% OTM, hedge 2% beyond short, skip if prior RSI > 70, HOLD TO EXPIRY
- Calls: 3% OTM, hedge 2% beyond short, exit on regime change to bull / sideways / no-trade
- Sideways: no new trades; hard kill off; call block off
- Fill proxy: entry/exit at settlement; 0.5 and 1.0 pt slippage per fill
- PnL scaled to 65 units per lot (current Nifty lot)
"""
import math
import os
import sys

import pandas as pd

import backtest as bt
import regime_full as rf
from otm_strategy.paths import OUTPUTS
from otm_strategy.strategy import call_exit_hit, put_exit_hit

OUTPUTS.mkdir(parents=True, exist_ok=True)
UNITS = 65
START = pd.Timestamp("2019-02-11")
PUT_OTM = 2.0
CALL_OTM = 3.0
HEDGE_EXTRA = 2.0
RSI_SKIP = 70.0
STEP = 50


def entry_day(e):
    """First trading day after the previous weekly cycle with this expiry listed (day-after-expiry proxy)."""
    c = [d for d in rf.dayset if 1 <= (e - d).days <= 6 and (d, e) in rf.listed]
    return max(c, key=lambda d: (e - d).days) if c else None


def pick_strikes(day, typ, ref_spot, short_pct, hedge_pct):
    s = day.xs(typ, level="OptnTp")
    s = s[(s.SttlmPric > 0) & (s.OpnIntrst > 0)]
    if s.empty:
        return None
    k = s.index.to_numpy()
    if typ == "PE":
        tgt = math.floor(ref_spot * (1 - short_pct / 100) / STEP) * STEP
        c1 = k[k <= tgt]
        if len(c1) == 0:
            return None
        ks = float(c1.max())
        th = math.floor(ks * (1 - hedge_pct / 100) / STEP) * STEP
        th = min(th, ks - STEP)
        c2 = k[k <= th]
        if len(c2) == 0:
            return None
        kh = float(c2.max())
    else:
        tgt = math.ceil(ref_spot * (1 + short_pct / 100) / STEP) * STEP
        c1 = k[k >= tgt]
        if len(c1) == 0:
            return None
        ks = float(c1.min())
        th = math.ceil(ks * (1 + hedge_pct / 100) / STEP) * STEP
        th = max(th, ks + STEP)
        c2 = k[k >= th]
        if len(c2) == 0:
            return None
        kh = float(c2.min())
    return ks, kh, float(s.loc[ks].SttlmPric), float(s.loc[kh].SttlmPric)


def settle(d, e, typ, ks, kh):
    a, b = (d, e, typ, float(ks)), (d, e, typ, float(kh))
    if a not in rf.opts.index or b not in rf.opts.index:
        return None
    return float(rf.opts.loc[a, "SttlmPric"] - rf.opts.loc[b, "SttlmPric"])


def one_leg(df, e, typ, slip, put_regime_exit=False, call_regime_exit=True,
            exit_sideways=True, hard_kill=False, rsi_skip_on=True):
    entry = entry_day(e)
    if entry is None or e not in df.index or entry < START or entry not in df.index:
        return None
    j0 = df.index.get_loc(entry)
    if j0 == 0:
        return None
    prior = df.iloc[j0 - 1]
    want = 1 if typ == "PE" else -1
    if int(prior.reg) != want:
        return None
    if typ == "PE" and rsi_skip_on and prior.rsi > RSI_SKIP:
        return None

    day = rf.opts.loc[(entry, e)]
    short_pct = PUT_OTM if typ == "PE" else CALL_OTM
    pk = pick_strikes(day, typ, float(prior.Close), short_pct, HEDGE_EXTRA)
    if pk is None:
        return None
    ks, kh, ps, ph = pk
    sgn = -1 if typ == "PE" else 1
    credit, width = ps - ph, abs(kh - ks)
    spot_entry = float(day["UndrlygPric"].iloc[0])
    lot = int(day["NewBrdLotQty"].iloc[0])
    st = float(df.loc[e, "Close"])
    pnl, how = credit - min(max(sgn * (st - ks), 0.0), width) - 2 * slip, "expiry"

    regime_exit = put_regime_exit if typ == "PE" else call_regime_exit
    for d in [x for x in rf.dayset if entry < x < e]:
        if d not in df.index:
            continue
        j = df.index.get_loc(d)
        prev, cur = int(df["reg"].iloc[j - 1]), int(df["reg"].iloc[j])
        cl = float(df.Close.iloc[j])
        if typ == "CE":
            hit_reg = regime_exit and call_exit_hit(prev, cur, exit_sideways=exit_sideways)
        else:
            hit_reg = regime_exit and put_exit_hit(prev, cur, exit_sideways=exit_sideways)
        hit_hard = hard_kill and ((typ == "PE" and cl <= ks) or (typ == "CE" and cl >= ks))
        if hit_reg or hit_hard:
            debit = settle(d, e, typ, ks, kh)
            if debit is None:
                continue
            pnl = credit - debit - 4 * slip
            how = "hard" if hit_hard and not hit_reg else "regime"
            if hit_hard:
                how = "hard"
            break

    return dict(
        entry=entry, expiry=e, typ=typ, reg=int(prior.reg), rsi=float(prior.rsi),
        prior_close=float(prior.Close), spot=spot_entry, ks=ks, kh=kh,
        otm_pct=abs(ks - float(prior.Close)) / float(prior.Close) * 100,
        credit=credit, width=width, lot=lot, pnl=pnl, how=how,
    )


def run_side(df, typ, slip, **kw):
    rows = [r for e in rf.expiries if (r := one_leg(df, e, typ, slip, **kw))]
    return pd.DataFrame(rows)


def stats(t, units=UNITS):
    if t.empty:
        return None
    rs = t.pnl * units
    eq = rs.cumsum()
    return dict(
        legs=len(t),
        win=round((t.pnl > 0).mean() * 100),
        credit=round(t.credit.mean(), 1),
        total=round(rs.sum()),
        y1=round(rs[t.entry < "2023-01-01"].sum()),
        y2=round(rs[t.entry >= "2023-01-01"].sum()),
        worst=round(rs.min()),
        maxdd=round((eq - eq.cummax()).min()),
        exit_pct=round((t.how != "expiry").mean() * 100),
        hard_pct=round((t.how == "hard").mean() * 100),
        avg_otm=round(t.otm_pct.mean(), 2),
    )


def fmt(label, s):
    if s is None:
        return f"{label:62s} no trades"
    return (
        f"{label:62s} {s['legs']:4d} {s['win']:3d}% {s['credit']:5.0f} "
        f"{s['total']:9,.0f} {s['y1']:9,.0f} {s['y2']:9,.0f} "
        f"{s['worst']:9,.0f} {s['maxdd']:9,.0f} {s['exit_pct']:5.0f}% {s['avg_otm']:5.2f}"
    )


def yearly(t, units=UNITS):
    t = t.copy()
    t["rs"] = t.pnl * units
    t["year"] = t.entry.dt.year
    return t.groupby("year").agg(
        legs=("rs", "size"),
        win=("pnl", lambda x: round((x > 0).mean() * 100)),
        total=("rs", "sum"),
        worst=("rs", "min"),
        exit_pct=("how", lambda x: round((x != "expiry").mean() * 100)),
    ).round(0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        START = pd.Timestamp(sys.argv[1])

    print("Pine v2 backtest — real NSE settlements")
    print(f"Option data: {rf.dayset[0].date()} to {rf.dayset[-1].date()} ({len(rf.dayset)} days)")
    print(f"Backtest start: {START.date()}")
    print(
        f"Rules: PE {PUT_OTM}% hold + RSI>{RSI_SKIP:.0f} skip | CE {CALL_OTM}% regime-exit "
        f"(bull/side/none) | hedge +{HEDGE_EXTRA}% | DI confirms trend | day-after-expiry entry | "
        f"prior-close decision | hard kill OFF | sideways OFF | per lot {UNITS} units"
    )

    kw = dict(
        put_regime_exit=False,
        call_regime_exit=True,
        exit_sideways=True,
        hard_kill=False,
        rsi_skip_on=True,
    )

    for confirm in (2, 1):
        p = bt.make_parser().parse_args([])
        p.confirm = confirm
        df = bt.build(rf.nifty, rf.vixd, p)
        print(f"\n===== confirm {confirm} completed close(s) =====")
        print(
            f"{'setup':62s} {'legs':>4s} {'win':>4s} {'cred':>5s} {'total':>9s} "
            f"{'2019-22':>9s} {'2023-26':>9s} {'worst':>9s} {'maxDD':>9s} {'exit%':>6s} {'otm%':>5s}"
        )

        for slip in (0.5, 1.0):
            pe = run_side(df, "PE", slip, **kw)
            ce = run_side(df, "CE", slip, **kw)
            both = pd.concat([pe, ce], ignore_index=True).sort_values("entry") if not pe.empty or not ce.empty else pd.DataFrame()
            print(fmt(f"PUT 2% | RSI skip | hold to expiry | slip {slip}", stats(pe)))
            print(fmt(f"CALL 3% | regime exit (incl sideways) | slip {slip}", stats(ce)))
            print(fmt(f"COMBINED (as traded) | slip {slip}", stats(both)))
            print()

        # Primary report: confirm 2, slip 0.5
        if confirm == 2:
            pe = run_side(df, "PE", 0.5, **kw)
            ce = run_side(df, "CE", 0.5, **kw)
            both = pd.concat([pe, ce], ignore_index=True).sort_values("entry")
            both["rs"] = both.pnl * UNITS
            out = OUTPUTS / "pine_v2_trades.csv"
            both.to_csv(out, index=False)
            print("By year COMBINED (confirm 2, slip 0.5), Rs per lot:")
            print(yearly(both).to_string())
            print("\nBy year PUTS only:")
            print(yearly(pe).to_string() if not pe.empty else "none")
            print("\nBy year CALLS only:")
            print(yearly(ce).to_string() if not ce.empty else "none")
            print("\nWorst 10 legs (combined, Rs/lot):")
            cols = ["entry", "typ", "reg", "prior_close", "ks", "otm_pct", "credit", "width", "pnl", "rs", "how"]
            show = both.nsmallest(10, "rs")[cols].copy()
            show["entry"] = show["entry"].dt.date
            print(show.round(1).to_string(index=False))
            print(f"\nSaved {out}")
