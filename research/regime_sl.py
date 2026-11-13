import os, sys
import numpy as np
import pandas as pd
import backtest as bt
import real_backtest as rb

CAPITAL, START = 1600000, pd.Timestamp("2024-11-13")
nifty, vixd = bt.load("^NSEI", "nifty", "2007-09-17", False), bt.load("^INDIAVIX", "vix", "2007-09-17", False)
opts, days = rb.load_opts()
expiries = sorted(opts.index.get_level_values("XpryDt").unique())
listed = set(zip(opts.index.get_level_values("TradDt"), opts.index.get_level_values("XpryDt")))


def pick(day, typ, spot, short_px, hedge_px):
    s = day.xs(typ, level="OptnTp"); s = s[s.OpnIntrst > 0]
    s = s[s.index > spot] if typ == "CE" else s[s.index < spot]
    cand = s[s.SttlmPric > 0]
    if cand.empty: return None
    ks = (cand.SttlmPric - short_px).abs().idxmin()
    far = cand[cand.index > ks] if typ == "CE" else cand[cand.index < ks]
    far = far[(far.SttlmPric <= short_px) & (far.SttlmPric > 0)]
    if far.empty: return None
    kh = (far.SttlmPric - hedge_px).abs().idxmin()
    return ks, kh, cand.loc[ks].SttlmPric, far.loc[kh].SttlmPric


def legs(df, e, sideways, short_px, hedge_px, slip):
    entry = next((pd.Timestamp(x) for x in days if 5 <= (e - pd.Timestamp(x)).days <= 9 and (pd.Timestamp(x), e) in listed), None)
    if entry is None or e not in df.index or entry < START or entry not in df.index: return []
    reg = df.loc[entry, "reg"]
    types = {1: ["PE"], -1: ["CE"], 0: ["PE", "CE"] if sideways else []}.get(reg, [])
    day = opts.loc[(entry, e)]
    spot, lot = day["UndrlygPric"].iloc[0], int(day["NewBrdLotQty"].iloc[0])
    out = []
    for typ in types:
        pk = pick(day, typ, spot, short_px, hedge_px)
        if pk is None: continue
        ks, kh, ps, ph = pk
        sgn = 1 if typ == "CE" else -1
        credit, width = ps - ph, abs(kh - ks)
        st = df.loc[e, "Close"]
        pnl, how = credit - min(max(sgn * (st - ks), 0.0), width) - 2 * slip, "expiry"
        for d in [pd.Timestamp(x) for x in days if entry < pd.Timestamp(x) < e]:
            if d not in df.index: continue
            j = df.index.get_loc(d); prev, cur = df["reg"].iloc[j - 1], df["reg"].iloc[j]
            hit = (cur == 1 and prev in (0, -1)) if typ == "CE" else (cur == -1 and prev in (0, 1))
            hit = hit or (cur == 9 and prev != 9)
            if hit:
                a, b = (d, e, typ, float(ks)), (d, e, typ, float(kh))
                if a in opts.index and b in opts.index:
                    pnl, how = credit - (opts.loc[a, "SttlmPric"] - opts.loc[b, "SttlmPric"]) - 4 * slip, "regime"
                    break
        out.append(dict(entry=entry, typ=typ, reg=reg, lot=lot, credit=credit, width=width, pnl=pnl, how=how))
    return out


print("SL = regime change only (checked at the daily close). Real prices, entries since 2024-11-13. Rs per 1 lot, last ~2 years.")
print(f"{'confirm':>7s} {'sell/hedge':>10s} {'sideways':>8s} {'slip':>4s} {'legs':>4s} {'win%':>5s} {'regime-exit%':>12s} {'total/lot':>10s} {'worst/lot':>10s} {'avg maxloss/lot':>15s} {'lots for 1.5%/mo':>16s}")
for confirm in (2, 1):
    p = bt.make_parser().parse_args([]); p.confirm = confirm
    df = bt.build(nifty, vixd, p)
    for short_px, hedge_px in ((5, 1), (10, 2), (16, 3)):
        for sideways in (False, True):
            for slip in (0.5, 1.0):
                rows = [r for e in expiries for r in legs(df, e, sideways, short_px, hedge_px, slip)]
                if not rows: continue
                t = pd.DataFrame(rows); rs = t.pnl * t.lot; tot = rs.sum()
                need = CAPITAL * 0.015 * 24 / tot if tot > 0 else float("nan")
                print(f"{confirm:7d} {short_px:>5d}/{hedge_px:<4d} {str(sideways):>8s} {slip:4.1f} {len(t):4d} {(t.pnl>0).mean()*100:5.0f} {(t.how=='regime').mean()*100:12.0f} {tot:10,.0f} {rs.min():10,.0f} {((t.width-t.credit)*t.lot).mean():15,.0f} {need:16.0f}")
