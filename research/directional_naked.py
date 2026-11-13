import math

import numpy as np
import pandas as pd

import backtest as bt
import real_backtest as rb


def run(df, opts, days, expiries, mult, slip, p, regimes):
    out = []
    for e in expiries:
        if e not in df.index:
            continue
        entry = next((x for x in days if 5 <= (e - pd.Timestamp(x)).days <= 9), None)
        if entry is None:
            continue
        entry = pd.Timestamp(entry)
        k = df.index.searchsorted(entry) - 1
        if k < 0:
            continue
        reg = df["reg"].iloc[k]
        if reg not in regimes:
            continue
        call = reg == -1
        sign, typ = (1, "CE") if call else (-1, "PE")
        day = opts.loc[(entry, e)]
        spot, lot = day["UndrlygPric"].iloc[0], int(day["NewBrdLotQty"].iloc[0])
        em = spot * df["vix"].iloc[k] / 100 * math.sqrt((e - entry).days / 365.0)
        ks = sign * math.ceil(sign * (spot + sign * em * mult) / p.step) * p.step
        try:
            row = day.loc[(typ, float(ks))]
        except KeyError:
            continue
        if row["OpnIntrst"] <= 0:
            continue
        st = df.loc[e, "Close"]
        loss = max(sign * (st - ks), 0.0)
        out.append(dict(date=entry, side="call" if call else "put", strike=ks, credit=row["SttlmPric"],
                        pnl=row["SttlmPric"] - loss - slip, lot=lot, spot=spot, loss_pts=loss))
    return pd.DataFrame(out)


def main():
    p = bt.make_parser().parse_args([])
    df = bt.build(bt.load("^NSEI", "nifty", p.start, False), bt.load("^INDIAVIX", "vix", p.start, False), p)
    opts, days = rb.load_opts()
    expiries = sorted(opts.index.get_level_values("XpryDt").unique())
    rows = []
    for mult in (1.0, 1.2, 1.5):
        for slip in (0.0, 1.0):
            t = run(df, opts, days, expiries, mult, slip, p, (1, -1))
            for side in ("put", "call", "both"):
                u = t if side == "both" else t[t.side == side]
                if u.empty:
                    continue
                rs = u.pnl * u.lot
                rows.append(dict(mult=mult, slip=slip, side=side, n=len(u), per_year=round(len(u) / 2.35, 1),
                                 credit_pts=round(u.credit.mean(), 1), win=round((u.pnl > 0).mean() * 100, 1),
                                 avg_rs_per_lot=round(rs.mean()), total_rs_per_lot=round(rs.sum()),
                                 worst_pts=round(u.pnl.min(), 1), worst_rs_per_lot=round(rs.min())))
    pd.set_option("display.width", 200)
    print(pd.DataFrame(rows).to_string(index=False))
    t = run(df, opts, days, expiries, 1.2, 1.0, p, (1, -1))
    t["rs"] = t.pnl * t.lot
    t["month"] = pd.to_datetime(t.date).dt.to_period("M")
    m = t.groupby("month").rs.sum()
    print("\nMonthly P&L per lot at 1.2x, 1pt slippage: positive months", int((m > 0).sum()), "of", len(m),
          "| best", round(m.max()), "| worst", round(m.min()))
    print(t.nsmallest(5, "rs")[["date", "side", "strike", "spot", "credit", "loss_pts", "rs"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
