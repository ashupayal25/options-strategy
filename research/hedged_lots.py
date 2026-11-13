import math
import sys

import numpy as np
import pandas as pd

import backtest as bt
import real_backtest as rb

CAPITAL = 1600000


def price(opts, d, e, typ, k):
    key = (d, e, typ, float(k))
    return opts.loc[key, "SttlmPric"] if key in opts.index else None


def trades(df, opts, days, expiries, mult, slip, p, hedge):
    out = []
    for e in expiries:
        if e not in df.index:
            continue
        entry = next((pd.Timestamp(x) for x in days if 5 <= (e - pd.Timestamp(x)).days <= 9), None)
        if entry is None:
            continue
        k = df.index.searchsorted(entry) - 1
        reg = df["reg"].iloc[k]
        if k < 0 or reg not in (1, -1):
            continue
        call = reg == -1
        sign, typ = (1, "CE") if call else (-1, "PE")
        day = opts.loc[(entry, e)]
        spot, lot = day["UndrlygPric"].iloc[0], int(day["NewBrdLotQty"].iloc[0])
        em = spot * df["vix"].iloc[k] / 100 * math.sqrt((e - entry).days / 365.0)
        ks = sign * math.ceil(sign * (spot + sign * em * mult) / p.step) * p.step
        kh = sign * math.ceil(sign * (spot + sign * em * (mult + hedge)) / p.step) * p.step
        if kh == ks:
            kh = ks + sign * p.step
        ps, ph = price(opts, entry, e, typ, ks), price(opts, entry, e, typ, kh)
        if ps is None or ph is None or day.loc[(typ, float(ks))]["OpnIntrst"] <= 0:
            continue
        credit, width = ps - ph, abs(kh - ks)
        st = df.loc[e, "Close"]
        pnl = credit - min(max(sign * (st - ks), 0.0), width) - 2 * slip
        path = [pd.Timestamp(x) for x in days if entry < pd.Timestamp(x) <= e]
        for n, d in enumerate(path[:-1]):
            j = df.index.get_loc(d)
            prev, cur = df["reg"].iloc[j - 1], df["reg"].iloc[j]
            hit = (cur == 1 and prev in (0, -1)) if call else (cur == -1 and prev in (0, 1))
            if hit or (cur == 9 and prev != 9):
                nd = path[n + 1]
                if nd == e:
                    val = min(max(sign * (st - ks), 0.0), width)
                else:
                    a, b = price(opts, nd, e, typ, ks), price(opts, nd, e, typ, kh)
                    if a is None or b is None:
                        break
                    val = a - b
                pnl = credit - val - 4 * slip
                break
        out.append(dict(date=entry, side="call" if call else "put", lot=lot, credit=credit, width=width, pnl=pnl))
    return pd.DataFrame(out)


def main():
    lots = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    p = bt.make_parser().parse_args([])
    df = bt.build(bt.load("^NSEI", "nifty", p.start, False), bt.load("^INDIAVIX", "vix", p.start, False), p)
    opts, days = rb.load_opts()
    expiries = sorted(opts.index.get_level_values("XpryDt").unique())
    rows = []
    for mult in (1.2, 1.5):
        for slip in (0.0, 1.0, 2.0):
            t = trades(df, opts, days, expiries, mult, slip, p, 0.6)
            for side in ("put", "call", "both"):
                u = t if side == "both" else t[t.side == side]
                if u.empty:
                    continue
                rs = u.pnl * u.lot * lots
                maxloss = ((u.width - u.credit) * u.lot * lots).max()
                eq = rs.cumsum()
                rows.append(dict(mult=mult, slip=slip, side=side, n=len(u), win=round((u.pnl > 0).mean() * 100, 1),
                                 credit=round(u.credit.mean(), 1), width=round(u.width.mean()),
                                 total_rs=round(rs.sum()), ret_pct=round(rs.sum() / CAPITAL * 100, 1),
                                 worst_rs=round(rs.min()), dd_rs=round((eq - eq.cummax()).min()),
                                 max_possible_loss_rs=round(maxloss)))
    pd.set_option("display.width", 220)
    print(f"{lots} lots, hedged spreads, regime exit, real prices, capital Rs {CAPITAL:,}")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
