import pandas as pd
import backtest as bt
import regime_full as rf
from final_rules import entry_day, start

UNITS, HEDGE, CALL_OTM = 65, 2.0, 3.0


def call_leg(df, e, slip, exit_rule=None, entry_filter=None):
    entry = entry_day(e)
    if entry is None or e not in df.index or entry < start or entry not in df.index: return None
    j0 = df.index.get_loc(entry)
    if j0 == 0: return None
    prior = df.iloc[j0 - 1]
    if prior.reg != -1: return None
    if entry_filter is not None and not entry_filter(prior): return None
    day = rf.opts.loc[(entry, e)]
    s = day.xs("CE", level="OptnTp"); s = s[s.SttlmPric > 0]
    k = s.index.to_numpy()
    c1 = k[k >= prior.Close * (1 + CALL_OTM / 100)]
    if len(c1) == 0: return None
    ks = c1.min()
    if s.loc[ks].OpnIntrst <= 0: return None
    c2 = k[k >= ks * (1 + HEDGE / 100)]
    if len(c2) == 0: return None
    kh = c2.min()
    credit, width = s.loc[ks].SttlmPric - s.loc[kh].SttlmPric, kh - ks
    pnl = credit - min(max(df.loc[e, "Close"] - ks, 0.0), width) - 2 * slip
    how = "expiry"
    if exit_rule is not None:
        for d in [x for x in rf.dayset if entry < x < e]:
            if d not in df.index: continue
            j = df.index.get_loc(d)
            if exit_rule(df, j, prior, ks):
                a, b = (d, e, "CE", float(ks)), (d, e, "CE", float(kh))
                if a in rf.opts.index and b in rf.opts.index:
                    pnl = credit - (rf.opts.loc[a, "SttlmPric"] - rf.opts.loc[b, "SttlmPric"]) - 4 * slip
                    how = "exit"
                    break
    return dict(entry=entry, credit=credit, pnl=pnl, how=how)


def regime_exit(df, j, prior, ks):
    prev, cur = df["reg"].iloc[j - 1], df["reg"].iloc[j]
    return (cur == 1 and prev in (0, -1)) or (cur == 9 and prev != 9)


def left_bearish(df, j, prior, ks):
    return df["reg"].iloc[j] != -1


def above_sma20(df, j, prior, ks):
    return df.Close.iloc[j] > df.sma20.iloc[j]


def above_sma50(df, j, prior, ks):
    return df.Close.iloc[j] > df.sma50.iloc[j]


def rally(pct):
    return lambda df, j, prior, ks: df.Close.iloc[j] >= prior.Close * (1 + pct / 100)


def near_short(pct):
    return lambda df, j, prior, ks: df.Close.iloc[j] >= ks * (1 - pct / 100)


def either(*fs):
    return lambda df, j, prior, ks: any(f(df, j, prior, ks) for f in fs)


def summarize(label, t):
    if t.empty:
        print(f"{label:52s} no trades"); return
    rs = t.pnl * UNITS; eq = rs.sort_index().cumsum()
    print(f"{label:52s} {len(t):4d} {(t.pnl>0).mean()*100:4.0f}% {rs.sum():9,.0f} {rs[t.entry<'2023-01-01'].sum():9,.0f} "
          f"{rs[t.entry>='2023-01-01'].sum():9,.0f} {rs.min():9,.0f} {(eq-eq.cummax()).min():9,.0f} {(t.how!='expiry').mean()*100:5.0f}%")


if __name__ == "__main__":
    p = bt.make_parser().parse_args([]); p.confirm = 2
    df = bt.build(rf.nifty, rf.vixd, p)
    rules = [
        ("hold to expiry", None, None),
        ("current: regime exit (to bullish / no-trade)", regime_exit, None),
        ("exit when regime leaves bearish", left_bearish, None),
        ("exit on close > SMA20", above_sma20, None),
        ("exit on close > SMA50", above_sma50, None),
        ("exit on +1.5% rally from entry ref close", rally(1.5), None),
        ("exit on +2% rally from entry ref close", rally(2.0), None),
        ("exit when close within 1% of short", near_short(1.0), None),
        ("exit when close within 1.5% of short", near_short(1.5), None),
        ("regime exit OR close > SMA20", either(regime_exit, above_sma20), None),
        ("regime exit OR +2% rally", either(regime_exit, rally(2.0)), None),
        ("regime exit OR within 1% of short", either(regime_exit, near_short(1.0)), None),
        ("regime exit, skip entry if RSI < 35", regime_exit, lambda r: r.rsi >= 35),
        ("regime exit, skip entry if RSI < 40", regime_exit, lambda r: r.rsi >= 40),
        ("regime exit, skip entry if close>5% below SMA20", regime_exit, lambda r: r.Close >= r.sma20 * 0.95),
        ("regime exit, skip entry if VIX > 20", regime_exit, lambda r: r.vix <= 20),
        ("regime exit, skip entry if VIX > 25", regime_exit, lambda r: r.vix <= 25),
    ]
    for slip in (0.5, 1.0):
        print(f"\n=== CALL 3% short / 2% hedge, bearish prior-close regime, confirm 2, slip {slip}, per lot (65 units) ===")
        print(f"{'rule':52s} {'legs':>4s} {'win':>5s} {'total':>9s} {'2019-22':>9s} {'2023-26':>9s} {'worst':>9s} {'maxDD':>9s} {'exit%':>6s}")
        for name, ex, filt in rules:
            rows = [r for e in rf.expiries if (r := call_leg(df, e, slip, ex, filt))]
            summarize(name, pd.DataFrame(rows))
