import math
import numpy as np
import pandas as pd
import backtest as bt
import regime_full as rf
from final_rules import entry_day, start

UNITS, HEDGE, R = 65, 2.0, 0.065
ncdf = bt.ncdf


def price(s, k, t, v, call):
    return bt.bs(s, k, t, v, R, call)


def implied_vol(p, s, k, t, call):
    intrinsic = max((s - k) if call else (k - s), 0.0) * math.exp(-R * t)
    if p <= intrinsic + 1e-6: return float("nan")
    lo, hi = 0.01, 3.0
    if price(s, k, t, hi, call) < p: return float("nan")
    for _ in range(50):
        mid = (lo + hi) / 2
        if price(s, k, t, mid, call) > p: hi = mid
        else: lo = mid
    return (lo + hi) / 2


def delta(s, k, t, v, call):
    d1 = (math.log(s / k) + (R + v * v / 2) * t) / (v * math.sqrt(t))
    return ncdf(d1) if call else ncdf(d1) - 1


def pick_short(s_chain, typ, spot, t, mode, target, vix, prior_close, fixed_pct):
    """Return the short strike for the selector. mode: fixed | chain | vix."""
    call = typ == "CE"
    k = s_chain.index.to_numpy()
    if mode == "fixed":
        tgt = prior_close * (1 + (fixed_pct if call else -fixed_pct) / 100)
        c = k[k >= tgt] if call else k[k <= tgt]
        return (c.min() if call else c.max()) if len(c) else None
    best = None
    for kk in k:
        if (kk <= spot) if call else (kk >= spot): continue
        if s_chain.loc[kk].OpnIntrst <= 0: continue
        v = implied_vol(s_chain.loc[kk].SttlmPric, spot, kk, t, call) if mode == "chain" else vix / 100
        if not v or math.isnan(v): continue
        dl = abs(delta(spot if mode == "chain" else prior_close, kk, t, v, call))
        if dl <= target / 100 and (best is None or dl > best[0]): best = (dl, kk)
    return best[1] if best else None


def leg(df, e, typ, mode, target, fixed_pct, slip, call_exit="both", put_exit="none"):
    entry = entry_day(e)
    if entry is None or e not in df.index or entry < start or entry not in df.index: return None
    j0 = df.index.get_loc(entry)
    if j0 == 0: return None
    prior = df.iloc[j0 - 1]
    call = typ == "CE"
    if prior.reg != (-1 if call else 1): return None
    if not call and prior.rsi > 70: return None
    day = rf.opts.loc[(entry, e)]
    s = day.xs(typ, level="OptnTp"); s = s[s.SttlmPric > 0]
    t = (e - entry).days / 365.0
    spot = float(day["UndrlygPric"].iloc[0])
    ks = pick_short(s, typ, spot, t, mode, target, prior.vix, prior.Close, fixed_pct)
    if ks is None or s.loc[ks].OpnIntrst <= 0: return None
    k = s.index.to_numpy()
    th = ks * (1 + HEDGE / 100) if call else ks * (1 - HEDGE / 100)
    c2 = k[k >= th] if call else k[k <= th]
    if len(c2) == 0: return None
    kh = c2.min() if call else c2.max()
    credit, width = s.loc[ks].SttlmPric - s.loc[kh].SttlmPric, abs(kh - ks)
    sgn = 1 if call else -1
    pnl = credit - min(max(sgn * (df.loc[e, "Close"] - ks), 0.0), width) - 2 * slip
    how = "expiry"
    if not call and put_exit != "none":
        for d in [x for x in rf.dayset if entry < x < e]:
            if d not in df.index: continue
            j = df.index.get_loc(d)
            pv, cu = df["reg"].iloc[j - 1], df["reg"].iloc[j]
            hit = ((cu == -1 and pv in (0, 1)) or (cu == 9 and pv != 9)) if put_exit == "regime" else df.Close.iloc[j] <= ks
            if hit:
                a, b = (d, e, "PE", float(ks)), (d, e, "PE", float(kh))
                if a in rf.opts.index and b in rf.opts.index:
                    pnl = credit - (rf.opts.loc[a, "SttlmPric"] - rf.opts.loc[b, "SttlmPric"]) - 4 * slip
                    how = "exit"
                    break
    if call:
        for d in [x for x in rf.dayset if entry < x < e]:
            if d not in df.index: continue
            j = df.index.get_loc(d)
            pv, cu = df["reg"].iloc[j - 1], df["reg"].iloc[j]
            if (call_exit == "both" and ((cu == 1 and pv in (0, -1)) or (cu == 9 and pv != 9))) or df.Close.iloc[j] > df.sma50.iloc[j]:
                a, b = (d, e, "CE", float(ks)), (d, e, "CE", float(kh))
                if a in rf.opts.index and b in rf.opts.index:
                    pnl = credit - (rf.opts.loc[a, "SttlmPric"] - rf.opts.loc[b, "SttlmPric"]) - 4 * slip
                    how = "exit"
                    break
    return dict(entry=entry, credit=credit, pnl=pnl, how=how, otm=abs(ks / prior.Close - 1) * 100)


def summarize(label, t):
    if t.empty:
        print(f"{label:30s} no trades"); return
    rs = t.pnl * UNITS; eq = rs.sort_index().cumsum()
    print(f"{label:30s} {len(t):4d} {(t.pnl>0).mean()*100:4.0f}% {t.otm.mean():5.1f} {t.credit.mean():5.1f} {rs.sum():9,.0f} "
          f"{rs[t.entry<'2023-01-01'].sum():9,.0f} {rs[t.entry>='2023-01-01'].sum():9,.0f} {rs.min():9,.0f} {(eq-eq.cummax()).min():9,.0f} {(t.how!='expiry').mean()*100:5.0f}%")


if __name__ == "__main__":
    p = bt.make_parser().parse_args([]); p.confirm = 2
    df = bt.build(rf.nifty, rf.vixd, p)
    for typ, fixed, name in (("PE", 2.0, "PUT (hold to expiry, RSI>70 skip)"), ("CE", 3.0, "CALL (regime/SMA50 exit)")):
        for slip in (0.5, 1.0):
            print(f"\n=== {name}, hedge 2% beyond, slip {slip}, per lot (65 units) ===")
            print(f"{'selector':30s} {'legs':>4s} {'win':>5s} {'%OTM':>5s} {'cred':>5s} {'total':>9s} {'2019-22':>9s} {'2023-26':>9s} {'worst':>9s} {'maxDD':>9s} {'exit%':>6s}")
            summarize(f"fixed {fixed:.0f}% OTM", pd.DataFrame([r for e in rf.expiries if (r := leg(df, e, typ, "fixed", 0, fixed, slip))]))
            for mode in ("chain", "vix"):
                for dl in (5, 7, 10, 15, 20):
                    summarize(f"{dl} delta ({mode} {'IV' if mode == 'chain' else 'VIX'})",
                              pd.DataFrame([r for e in rf.expiries if (r := leg(df, e, typ, mode, dl, fixed, slip))]))
