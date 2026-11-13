import pandas as pd

import backtest as bt
import directional_naked as dn
import real_backtest as rb


def exit_pnl(r, df, opts, days, expiries, flip_to_none, stop, slip):
    e = next(x for x in expiries if (x - r.date).days >= 5)
    typ, call = ("CE", True) if r.side == "call" else ("PE", False)
    path = [pd.Timestamp(d) for d in days if r.date < pd.Timestamp(d) <= e]
    for n, d in enumerate(path[:-1]):
        k = df.index.get_loc(d)
        prev, cur = df["reg"].iloc[k - 1], df["reg"].iloc[k]
        hit = (cur == 1 and prev in (0, -1)) if call else (cur == -1 and prev in (0, 1))
        hit = hit or (flip_to_none and cur == 9 and prev != 9)
        v = opts.loc[(d, e, typ, float(r.strike)), "SttlmPric"] if (d, e, typ, float(r.strike)) in opts.index else None
        if stop is not None and v is not None and v >= r.credit * (1 + stop):
            return r.credit - v - 2 * slip, d, "stop"
        if hit:
            nd = path[n + 1]
            if nd == e:
                st = df.loc[e, "Close"]
                loss = max((st - r.strike) if call else (r.strike - st), 0.0)
                return r.credit - loss - 2 * slip, nd, "flip(expiry)"
            key = (nd, e, typ, float(r.strike))
            if key in opts.index:
                return r.credit - opts.loc[key, "SttlmPric"] - 2 * slip, nd, "flip"
    return r.pnl, e, "expiry"


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
            for label, none, stop in (("no exit", None, None), ("flip", False, None),
                                      ("flip + no-trade exit", True, None), ("flip + 2x stop", False, 2.0)):
                if none is None:
                    rs = u.pnl * u.lot
                else:
                    rs = pd.Series([exit_pnl(r, df, opts, days, expiries, none, stop, 1.0)[0] * r.lot for r in u.itertuples()])
                rows.append(dict(mult=mult, side=side, rule=label, n=len(u), win=round((rs > 0).mean() * 100, 1),
                                 avg_rs=round(rs.mean()), total_rs=round(rs.sum()), worst_rs=round(rs.min())))
    pd.set_option("display.width", 200)
    print(pd.DataFrame(rows).to_string(index=False))

    t = dn.run(df, opts, days, expiries, 1.2, 1.0, p, (1, -1))
    w = t[(t.side == "call") & (t.date == pd.Timestamp("2026-11-02"))].iloc[0]
    print("\nThe 2 Nov 2026 call, 1.2x: strike", w.strike, "credit", w.credit)
    for flip_none in (False, True):
        pnl, d, why = exit_pnl(w, df, opts, days, expiries, flip_none, None, 1.0)
        print(f"  flip rule (no-trade exit={flip_none}): exit {d.date()} via {why}, P&L {pnl:.1f} pts = Rs {pnl * w.lot:,.0f} per lot")
    e = next(x for x in expiries if (x - w.date).days >= 5)
    for d in [pd.Timestamp(x) for x in days if w.date < pd.Timestamp(x) <= e]:
        key = (d, e, "CE", float(w.strike))
        print("  ", d.date(), "regime", int(df.loc[d, "reg"]), "close", round(df.loc[d, "Close"]), "opt", opts.loc[key, "SttlmPric"] if key in opts.index and d != e else "-")


if __name__ == "__main__":
    main()
