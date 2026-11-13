import math
import numpy as np
import pandas as pd
import backtest as bt
import regime_full as rf

UNITS, SLIP, HEDGE = 65, 0.5, 2.0
start = pd.Timestamp("2019-02-11")


def entry_day(e, target_dte):
    c = [d for d in rf.dayset if (e - d).days <= target_dte and (e - d).days >= 1 and (d, e) in rf.listed]
    return max(c, key=lambda d: (e - d).days) if c else None


def put_leg(df, e, short_pct=1.0, k_em=None, target_dte=6, exit_mode="expiry", filt=None):
    entry = entry_day(e, target_dte)
    if entry is None or e not in df.index or entry < start or entry not in df.index: return None
    r = df.loc[entry]
    if r.reg != 1 or (filt is not None and not filt(df, entry)): return None
    day = rf.opts.loc[(entry, e)]
    spot = day["UndrlygPric"].iloc[0]
    dist = short_pct
    if k_em is not None:
        em = spot * r.vix / 100 * math.sqrt((e - entry).days / 365.0)
        dist = max(short_pct, k_em * em / spot * 100)
    s = day.xs("PE", level="OptnTp"); s = s[s.SttlmPric > 0]
    k = s.index.to_numpy()
    c1 = k[k <= spot * (1 - dist / 100)]
    if len(c1) == 0: return None
    ks = c1.max()
    if s.loc[ks].OpnIntrst <= 0: return None
    c2 = k[k <= ks * (1 - HEDGE / 100)]
    if len(c2) == 0: return None
    kh = c2.max()
    credit, width = s.loc[ks].SttlmPric - s.loc[kh].SttlmPric, ks - kh
    st = df.loc[e, "Close"]
    pnl = credit - min(max(ks - st, 0.0), width) - 2 * SLIP
    if exit_mode in ("regime", "strict"):
        for d in [x for x in rf.dayset if entry < x < e]:
            if d not in df.index: continue
            j = df.index.get_loc(d); prev, cur = df["reg"].iloc[j - 1], df["reg"].iloc[j]
            hit = (cur == -1 and prev in (0, 1)) or (cur == 9 and prev != 9)
            if exit_mode == "strict": hit = cur != 1 and prev == 1 or (cur != 1 and prev != 1 and d > entry and df["reg"].iloc[j - 1] == 1)
            if hit:
                a, b = (d, e, "PE", float(ks)), (d, e, "PE", float(kh))
                if a in rf.opts.index and b in rf.opts.index:
                    pnl = credit - (rf.opts.loc[a, "SttlmPric"] - rf.opts.loc[b, "SttlmPric"]) - 4 * SLIP
                    break
    return dict(entry=entry, credit=credit, width=width, pnl=pnl, dist=dist)


def stats(label, t, base=None):
    if t.empty: return f"{label:48s} no trades"
    rs = t.pnl * UNITS
    eq = rs.sort_index().cumsum()
    h1 = rs[t.entry < "2023-01-01"].sum(); h2 = rs[t.entry >= "2023-01-01"].sum()
    return (f"{label:48s} {len(t):4d} {(t.pnl>0).mean()*100:4.0f}% {rs.sum():9,.0f} {h1:9,.0f} {h2:9,.0f} {rs.min():9,.0f} {(eq-eq.cummax()).min():10,.0f} "
            f"{(rs[rs<0].sum()/ -rs[rs>0].sum())*100:5.0f}%")


def main():
    for confirm in (2, 1):
        p = bt.make_parser().parse_args([]); p.confirm = confirm
        df = bt.build(rf.nifty, rf.vixd, p)
        df["vix5"] = (df.vix / df.vix.shift(5) - 1) * 100
        df["ext20"] = (df.Close / df.sma20 - 1) * 100
        variants = [
            ("Baseline (1% / 2%, enter 6d out, hold)", dict()),
            ("Exit on regime change (current rule)", dict(exit_mode="regime")),
            ("Exit on ANY move away from bullish", dict(exit_mode="strict")),
            ("Short strike 1.5% (not 1%)", dict(short_pct=1.5)),
            ("Short strike 2.0%", dict(short_pct=2.0)),
            ("Adaptive: max(1%, 0.6 x expected move)", dict(k_em=0.6)),
            ("Adaptive: max(1%, 0.8 x expected move)", dict(k_em=0.8)),
            ("Adaptive: max(1%, 1.0 x expected move)", dict(k_em=1.0)),
            ("Enter 4 days before expiry", dict(target_dte=4)),
            ("Enter 1 day before expiry", dict(target_dte=1)),
            ("Skip if VIX up >10% in 5 days", dict(filt=lambda d, x: d.loc[x, "vix5"] <= 10)),
            ("Skip if VIX above its 50-day average", dict(filt=lambda d, x: d.loc[x, "vix"] <= d.loc[x, "vixavg"])),
            ("Skip if RSI > 70", dict(filt=lambda d, x: d.loc[x, "rsi"] <= 70)),
            ("Skip if close >4% above SMA20", dict(filt=lambda d, x: d.loc[x, "ext20"] <= 4)),
            ("Skip if ADX > 35", dict(filt=lambda d, x: d.loc[x, "adx"] <= 35)),
        ]
        print(f"\n===== confirmation {confirm}; puts only, 1 lot (65 units), Rs, 0.5pt slippage, hedge 2% =====")
        print(f"{'variant':48s} {'legs':>4s} {'win':>5s} {'total':>9s} {'2019-22':>9s} {'2023-26':>9s} {'worst':>9s} {'maxDD':>10s} {'loss/win':>6s}")
        for label, kw in variants:
            rows = [r for e in rf.expiries if (r := put_leg(df, e, **kw))]
            print(stats(label, pd.DataFrame(rows)))



if __name__ == "__main__":
    main()
