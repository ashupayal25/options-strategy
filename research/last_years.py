import argparse
import math

import numpy as np
import pandas as pd

import backtest as bt

CONFIGS = [
    ("all entries, 1.2x", "SBE", 1.2),
    ("all entries, 1.5x", "SBE", 1.5),
    ("directional only, 1.2x", "BE", 1.2),
    ("directional only, 1.5x", "BE", 1.5),
    ("sideways only, 1.5x", "S", 1.5),
]


def size_and_pnl(t, capital, risk_pct, lot):
    budget = capital * risk_pct / 100
    t = t.copy()
    t["lots"] = np.floor(budget / (t.max_loss * lot)).astype(int)
    skipped = int((t.lots == 0).sum())
    t = t[t.lots > 0].copy()
    t["rupees"] = t.pnl * t.lots * lot
    t["risk_rs"] = t.max_loss * t.lots * lot
    return t, skipped


def report(label, t, capital):
    if t.empty:
        return dict(config=label, trades=0)
    eq = t.rupees.cumsum()
    dd = (eq - eq.cummax()).min()
    return dict(config=label, trades=len(t), win_pct=round((t.rupees > 0).mean() * 100, 1),
                avg_lots=round(t.lots.mean(), 1), total_rs=round(t.rupees.sum()),
                ret_pct=round(t.rupees.sum() / capital * 100, 1),
                worst_rs=round(t.rupees.min()), max_dd_rs=round(dd),
                max_risk_rs=round(t.risk_rs.max()))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--capital", type=float, default=1600000)
    a.add_argument("--risk-pct", type=float, default=2.0)
    a.add_argument("--lot", type=int, default=75)
    a.add_argument("--years", type=float, default=2.0)
    o = a.parse_args()

    p = bt.make_parser().parse_args([])
    df = bt.build(bt.load("^NSEI", "nifty", p.start, False), bt.load("^INDIAVIX", "vix", p.start, False), p)
    end = df.index[-1]
    print(f"Capital Rs {o.capital:,.0f}, risk per trade {o.risk_pct}% (Rs {o.capital * o.risk_pct / 100:,.0f}), "
          f"lot size {o.lot}, data to {end.date()}")

    for yrs in (1.0, o.years):
        start = end - pd.DateOffset(days=int(365 * yrs))
        rows, skipped_total = [], {}
        for label, kinds, mult in CONFIGS:
            t = bt.backtest(df, kinds, "A", 5, 7, mult, p)
            t = t[pd.to_datetime(t.date) >= start]
            t, skipped = size_and_pnl(t, o.capital, o.risk_pct, o.lot)
            rows.append(report(label, t, o.capital))
            skipped_total[label] = skipped
        print(f"\n=== last {yrs:g} year(s): {start.date()} to {end.date()}, weekly Nifty, no VIX filter ===")
        print(pd.DataFrame(rows).to_string(index=False))
        print("Trades skipped because one lot exceeded the risk budget:", skipped_total)

    start = end - pd.DateOffset(days=int(365 * o.years))
    t = bt.backtest(df, "SBE", "A", 5, 7, 1.5, p)
    t = t[pd.to_datetime(t.date) >= start]
    t, _ = size_and_pnl(t, o.capital, o.risk_pct, o.lot)
    t["month"] = pd.to_datetime(t.date).dt.to_period("M")
    m = t.groupby("month").agg(trades=("rupees", "size"), pnl_rs=("rupees", "sum")).round(0)
    print("\n=== monthly P&L, all entries, 1.5x ===")
    print(m.to_string())
    cols = ["date", "kind", "spot", "vix", "lots", "credit", "pnl", "max_loss", "rupees", "touched"]
    print("\n=== five worst trades, all entries, 1.5x ===")
    print(t.nsmallest(5, "rupees")[cols].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
