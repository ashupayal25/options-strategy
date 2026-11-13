import math
import os

import numpy as np
import pandas as pd

import backtest as bt

from otm_strategy.paths import ROOT as HERE, OUTPUTS
OUTPUTS.mkdir(parents=True, exist_ok=True)
OPT = os.path.join(HERE, "data", "bhav", "nifty_options.csv")
CAPITAL, RISK_PCT = 1600000, 2.0


def load_opts():
    o = pd.read_csv(OPT, parse_dates=["TradDt", "XpryDt"])
    o = o.drop_duplicates(["TradDt", "XpryDt", "OptnTp", "StrkPric"])
    return o.set_index(["TradDt", "XpryDt", "OptnTp", "StrkPric"]).sort_index(), sorted(o.TradDt.unique())


def entries(df, kinds, hold, since):
    sig = {k: df[k].to_numpy() for k in "SBE"}
    last, out = -10**9, []
    for i in range(len(df) - hold):
        kind = next((k for k in kinds if sig[k][i]), None)
        if kind is None or i - last < hold:
            continue
        last = i
        if df.index[i] >= since:
            out.append((i, kind))
    return out


def trade(df, opts, days, i, kind, mult, slip, p):
    d = df.index[i]
    nxt = next((x for x in days if x > d), None)
    if nxt is None:
        return None, "no next day"
    exp = sorted(opts.loc[nxt].index.get_level_values("XpryDt").unique())
    e = next((x for x in exp if 5 <= (x - nxt).days <= 9), None)
    if e is None or e not in df.index:
        return None, "no weekly expiry"
    dte = (e - nxt).days
    first = opts.loc[(nxt, e)]
    spot = first["UndrlygPric"].iloc[0]
    lot = int(first["NewBrdLotQty"].iloc[0])
    vix = df["vix"].iloc[i]
    em = spot * vix / 100 * math.sqrt(dte / 365.0)
    st = df.loc[e, "Close"]
    pnl_real = pnl_model = credit_real = credit_model = 0.0
    width = 0.0
    for call, need in ((True, kind in "SE"), (False, kind in "SB")):
        if not need:
            continue
        sign, typ = (1, "CE") if call else (-1, "PE")
        ks = sign * math.ceil(sign * (spot + sign * em * mult) / p.step) * p.step
        kh = sign * math.ceil(sign * (spot + sign * em * (mult + p.hedge)) / p.step) * p.step
        if kh == ks:
            kh = ks + sign * p.step
        try:
            rs, rh = first.loc[(typ, float(ks))], first.loc[(typ, float(kh))]
        except KeyError:
            return None, "strike missing"
        if rs["OpnIntrst"] <= 0:
            return None, "short strike has no open interest"
        credit = rs["SttlmPric"] - rh["SttlmPric"]
        loss = min(max(sign * (st - ks), 0.0), abs(kh - ks))
        pnl_real += credit - loss - 2 * slip
        credit_real += credit
        a, b, _ = bt.spread_pnl(spot, em, mult, call, vix, st, dte, p)
        pnl_model += a
        credit_model += b
        width = max(width, abs(kh - ks))
    return dict(date=d, kind=kind, lot=lot, pnl=pnl_real, pnl_model=pnl_model, credit=credit_real,
                credit_model=credit_model, max_loss=width - credit_real + 2 * slip), None


def main():
    p = bt.make_parser().parse_args([])
    df = bt.build(bt.load("^NSEI", "nifty", p.start, False), bt.load("^INDIAVIX", "vix", p.start, False), p)
    opts, days = load_opts()
    since = pd.Timestamp(days[0])
    print(f"Option data: {days[0].date() if hasattr(days[0], 'date') else days[0]} to {days[-1]}, {len(days)} trading days")
    rows, last_trades = [], None
    for kinds_name, kinds in (("all", "SBE"), ("sideways", "S"), ("directional", "BE")):
        for mult in (1.2, 1.5, 1.8):
            for slip in (0.0, 1.0, 2.0):
                trades, skips = [], {}
                for i, kind in entries(df, kinds, 5, since):
                    t, why = trade(df, opts, days, i, kind, mult, slip, p)
                    if t is None:
                        skips[why] = skips.get(why, 0) + 1
                    else:
                        trades.append(t)
                t = pd.DataFrame(trades)
                if t.empty:
                    continue
                t["lots"] = np.floor(CAPITAL * RISK_PCT / 100 / (t.max_loss * t.lot)).astype(int)
                u = t[t.lots > 0].copy()
                u["rs"] = u.pnl * u.lots * u.lot
                eq = u.rs.cumsum()
                rows.append(dict(kinds=kinds_name, mult=mult, slip=slip, n=len(u), skipped=sum(skips.values()),
                                 credit=round(t.credit.mean(), 1), credit_model=round(t.credit_model.mean(), 1),
                                 win=round((u.pnl > 0).mean() * 100, 1), avg=round(u.pnl.mean(), 2),
                                 pnl_pts=round(u.pnl.sum()), model_pts=round(u.pnl_model.sum()),
                                 total_rs=round(u.rs.sum()), worst_rs=round(u.rs.min()),
                                 dd_rs=round((eq - eq.cummax()).min())))
                if (kinds_name, mult, slip) == ("all", 1.5, 1.0):
                    last_trades = u
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(OUTPUTS, "real_results.csv"), index=False)
    pd.set_option("display.width", 220)
    print(res.to_string(index=False))
    if last_trades is not None:
        last_trades.to_csv(os.path.join(OUTPUTS, "real_trades_all_1.5x.csv"), index=False)


if __name__ == "__main__":
    main()
