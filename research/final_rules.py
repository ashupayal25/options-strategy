import math
import numpy as np
import pandas as pd
import backtest as bt
import regime_full as rf

UNITS = 65
start = pd.Timestamp("2019-02-11")


def entry_day(e):
    c = [d for d in rf.dayset if 1 <= (e - d).days <= 6 and (d, e) in rf.listed]
    return max(c, key=lambda d: (e - d).days) if c else None


def legs(df, e, typ, short_pct, hedge_pct, slip, rsi_skip, regime_exit, hard_kill):
    entry = entry_day(e)
    if entry is None or e not in df.index or entry < start or entry not in df.index: return None
    j0 = df.index.get_loc(entry)
    if j0 == 0: return None
    prior = df.iloc[j0 - 1]
    want = 1 if typ == "PE" else -1
    if prior.reg != want: return None
    if typ == "PE" and rsi_skip and prior.rsi > 70: return None
    sgn = -1 if typ == "PE" else 1
    day = rf.opts.loc[(entry, e)]
    s = day.xs(typ, level="OptnTp"); s = s[s.SttlmPric > 0]
    k = s.index.to_numpy()
    tgt = prior.Close * (1 + sgn * short_pct / 100)
    c1 = k[k <= tgt] if sgn < 0 else k[k >= tgt]
    if len(c1) == 0: return None
    ks = c1.max() if sgn < 0 else c1.min()
    if s.loc[ks].OpnIntrst <= 0: return None
    th = ks * (1 + sgn * hedge_pct / 100)
    c2 = k[k <= th] if sgn < 0 else k[k >= th]
    if len(c2) == 0: return None
    kh = c2.max() if sgn < 0 else c2.min()
    credit, width = s.loc[ks].SttlmPric - s.loc[kh].SttlmPric, abs(kh - ks)
    st = df.loc[e, "Close"]
    pnl, how = credit - min(max(sgn * (st - ks), 0.0), width) - 2 * slip, "expiry"
    for d in [x for x in rf.dayset if entry < x < e]:
        if d not in df.index: continue
        j = df.index.get_loc(d); prev, cur = df["reg"].iloc[j - 1], df["reg"].iloc[j]
        hit_reg = regime_exit and (((cur == 1 and prev in (0, -1)) if typ == "CE" else (cur == -1 and prev in (0, 1))) or (cur == 9 and prev != 9))
        cl = df.Close.iloc[j]
        hit_hard = hard_kill and ((typ == "PE" and cl <= ks) or (typ == "CE" and cl >= ks))
        if hit_reg or hit_hard:
            a, b = (d, e, typ, float(ks)), (d, e, typ, float(kh))
            if a in rf.opts.index and b in rf.opts.index:
                pnl = credit - (rf.opts.loc[a, "SttlmPric"] - rf.opts.loc[b, "SttlmPric"]) - 4 * slip
                how = "hard" if hit_hard else "regime"
                break
    return dict(entry=entry, credit=credit, width=width, pnl=pnl, how=how)


def run(df, typ, short_pct, hedge_pct, slip, rsi_skip, regime_exit, hard_kill):
    rows = [r for e in rf.expiries if (r := legs(df, e, typ, short_pct, hedge_pct, slip, rsi_skip, regime_exit, hard_kill))]
    return pd.DataFrame(rows)


def row(label, t):
    if t.empty: return f"{label:58s} no trades"
    rs = t.pnl * UNITS; eq = rs.sort_index().cumsum()
    return (f"{label:58s} {len(t):4d} {(t.pnl>0).mean()*100:4.0f}% {t.credit.mean():5.0f} {rs.sum():9,.0f} {rs[t.entry<'2023-01-01'].sum():9,.0f} {rs[t.entry>='2023-01-01'].sum():9,.0f} "
            f"{rs.min():9,.0f} {(eq-eq.cummax()).min():9,.0f} {(t.how!='expiry').mean()*100:5.0f}%")


if __name__ == "__main__":
    for confirm in (2, 1):
        p = bt.make_parser().parse_args([]); p.confirm = confirm
        df = bt.build(rf.nifty, rf.vixd, p)
        print(f"\n===== confirm {confirm}; entry = day after expiry using PRIOR-close regime/RSI; per lot (65 units), Rs =====")
        print(f"{'setup':58s} {'legs':>4s} {'win':>5s} {'cred':>5s} {'total':>9s} {'2019-22':>9s} {'2023-26':>9s} {'worst':>9s} {'maxDD':>9s} {'exit%':>6s}")
        for typ, short, name in (("PE", 2.0, "PUT 2% short"), ("PE", 4.0, "PUT 4% short (your earlier setting)"), ("CE", 3.0, "CALL 3% short (bearish)")):
            for rsi_skip in ((True, False) if typ == "PE" else (False,)):
                for regime_exit, hard, en in ((False, False, "hold to expiry"), (True, False, "regime exit"), (True, True, "regime exit + hard kill")):
                    for slip in (0.5, 1.0):
                        t = run(df, typ, short, 2.0, slip, rsi_skip, regime_exit, hard)
                        print(row(f"{name} | {'RSI skip' if rsi_skip else 'no RSI skip'} | {en} | slip {slip}", t))
                print()
