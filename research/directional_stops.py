import pandas as pd

import backtest as bt
import directional_naked as dn
import real_backtest as rb


def with_stop(t, opts, days, expiries, stop, slip):
    out = []
    for r in t.itertuples():
        e = next(x for x in expiries if (x - r.date).days >= 5)
        typ = "CE" if r.side == "call" else "PE"
        path = [d for d in days if r.date < pd.Timestamp(d) < e]
        pnl = r.pnl
        for d in path:
            try:
                v = opts.loc[(pd.Timestamp(d), e, typ, float(r.strike)), "SttlmPric"]
            except KeyError:
                continue
            if v >= r.credit * (1 + stop):
                pnl = r.credit - v - 2 * slip
                break
        out.append(pnl * r.lot)
    return pd.Series(out)


def main():
    p = bt.make_parser().parse_args([])
    df = bt.build(bt.load("^NSEI", "nifty", p.start, False), bt.load("^INDIAVIX", "vix", p.start, False), p)
    opts, days = rb.load_opts()
    expiries = sorted(opts.index.get_level_values("XpryDt").unique())
    rows = []
    for mult in (1.2, 1.5):
        t = dn.run(df, opts, days, expiries, mult, 1.0, p, (1, -1))
        for side in ("put", "call"):
            u = t[t.side == side].reset_index(drop=True)
            for stop in (None, 1.0, 2.0, 3.0):
                rs = (u.pnl * u.lot) if stop is None else with_stop(u, opts, days, expiries, stop, 1.0)
                rows.append(dict(mult=mult, side=side, stop=stop, n=len(u), win=round((rs > 0).mean() * 100, 1),
                                 avg_rs=round(rs.mean()), total_rs=round(rs.sum()), worst_rs=round(rs.min())))
    pd.set_option("display.width", 200)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
