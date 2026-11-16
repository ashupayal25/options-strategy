import pandas as pd
import backtest as bt
import regime_full as rf
from delta_strikes import leg

UNITS, CAPITAL = 65, 1600000
LOTS = 25


def legs(df, mode, put_sel, call_sel, slip, call_exit):
    rows = []
    for e in rf.expiries:
        for typ, sel, fixed in (("PE", put_sel, 2.0), ("CE", call_sel, 3.0)):
            if (r := leg(df, e, typ, mode if sel else "fixed", sel or 0, fixed, slip, call_exit)):
                rows.append({**r, "typ": typ, "expiry": e})
    return pd.DataFrame(rows).sort_values("entry")


def report(label, t):
    rs = t.pnl * UNITS * LOTS
    eq = rs.cumsum(); dd = (eq - eq.cummax()).min()
    yrs = (t.entry.max() - t.entry.min()).days / 365.25
    print(f"{label:46s} {len(t):4d} {(t.pnl>0).mean()*100:4.0f}% {rs.sum():11,.0f} {rs.sum()/CAPITAL*100/yrs:6.1f}% {rs.min():10,.0f} {rs.min()/CAPITAL*100:6.1f}% {dd:10,.0f} {dd/CAPITAL*100:6.1f}%")
    return rs


if __name__ == "__main__":
    p = bt.make_parser().parse_args([]); p.confirm = 2
    df = bt.build(rf.nifty, rf.vixd, p)
    for slip in (0.5, 1.0):
        print(f"\n=== {LOTS} lots ({LOTS*UNITS} units), capital Rs 16L, slip {slip} pt, 2019-02 to 2026-11 ===")
        print(f"{'setup':46s} {'legs':>4s} {'win':>5s} {'total Rs':>11s} {'/yr':>7s} {'worst leg':>10s} {'%cap':>7s} {'max DD':>10s} {'%cap':>7s}")
        for label, mode, ps, cs, ce in (
            ("fixed 2% put / 3% call (both exits)", "fixed", 0, 0, "both"),
            ("15 delta chain IV, call exit regime+SMA50", "chain", 15, 15, "both"),
            ("15 delta chain IV, call exit SMA50 only", "chain", 15, 15, "sma50"),
            ("15 delta flat VIX (app guide), regime+SMA50", "vix", 15, 15, "both"),
            ("15 delta chain IV puts only", "chain", 15, 0, "both"),
            ("15 delta chain IV puts, fixed 3% calls, SMA50", "chain", 15, 0, "sma50"),
        ):
            t = legs(df, mode, ps if mode != "fixed" else 0, cs if mode != "fixed" else 0, slip, ce)
            if label.endswith("puts only"): t = t[t.typ == "PE"]
            rs = report(label, t)
            if slip == 0.5 and label.startswith("15 delta chain IV, call exit regime"):
                by = rs.groupby(t.entry.dt.year).sum(); print("   by year:", ", ".join(f"{y}: {v:,.0f}" for y, v in by.items()))
                for typ in ("PE", "CE"):
                    x = t[t.typ == typ]; print(f"   {typ}: legs {len(x)}, total {x.pnl.sum()*UNITS*LOTS:,.0f}")
