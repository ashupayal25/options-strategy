import sys
import numpy as np
import pandas as pd
import backtest as bt
import real_backtest as rb

import os
SHORT_PX, HEDGE_PX, CAPITAL = float(os.environ.get("SHORT_PX", 5.0)), float(os.environ.get("HEDGE_PX", 1.0)), 1600000
TYPES = os.environ.get("TYPES", "CE,PE").split(",")
START = pd.Timestamp("2024-11-13")
p = bt.make_parser().parse_args([])
df = bt.build(bt.load("^NSEI", "nifty", p.start, False), bt.load("^INDIAVIX", "vix", p.start, False), p)
opts, days = rb.load_opts()
expiries = sorted(opts.index.get_level_values("XpryDt").unique())
listed = set(zip(opts.index.get_level_values("TradDt"), opts.index.get_level_values("XpryDt")))


def pick(day, typ, spot):
    s = day.xs(typ, level="OptnTp")
    s = s[s.OpnIntrst > 0]
    s = s[s.index > spot] if typ == "CE" else s[s.index < spot]
    cand = s[s.SttlmPric > 0]
    if cand.empty:
        return None
    ks = (cand.SttlmPric - SHORT_PX).abs().idxmin()
    far = cand[cand.index > ks] if typ == "CE" else cand[cand.index < ks]
    far = far[(far.SttlmPric <= SHORT_PX) & (far.SttlmPric > 0)]
    if far.empty:
        return None
    kh = (far.SttlmPric - HEDGE_PX).abs().idxmin()
    return ks, kh, cand.loc[ks].SttlmPric, far.loc[kh].SttlmPric


def leg(e, typ, kind, val, slip):
    entry = next((pd.Timestamp(x) for x in days if 5 <= (e - pd.Timestamp(x)).days <= 9 and (pd.Timestamp(x), e) in listed), None)
    if entry is None or e not in df.index or entry < START:
        return None
    day = opts.loc[(entry, e)]
    spot, lot = day["UndrlygPric"].iloc[0], int(day["NewBrdLotQty"].iloc[0])
    pk = pick(day, typ, spot)
    if pk is None:
        return None
    ks, kh, ps, ph = pk
    sgn = 1 if typ == "CE" else -1
    credit, width = ps - ph, abs(kh - ks)
    st = df.loc[e, "Close"]
    pnl = credit - min(max(sgn * (st - ks), 0.0), width) - 2 * slip
    stopped = False
    for d in [pd.Timestamp(x) for x in days if entry < pd.Timestamp(x) < e]:
        a, b = (d, e, typ, float(ks)), (d, e, typ, float(kh))
        if a not in opts.index or b not in opts.index:
            continue
        sp, hp = opts.loc[a, "SttlmPric"], opts.loc[b, "SttlmPric"]
        hit = (kind == "prem" and sp >= ps * val) or (kind == "spot" and sgn * (df.loc[d, "Close"] / spot - 1) * 100 >= val)
        if hit:
            pnl, stopped = credit - (sp - hp) - 4 * slip, True
            break
    return dict(entry=entry, typ=typ, lot=lot, credit=credit, pnl=pnl, stopped=stopped, width=width)


print("Sell ~Rs5 option each side weekly, hedge ~Rs1 (margin only), real prices, entries since 2024-11-13. Rs per 1 lot over ~2 years.")
print(f"{'stop':18s} {'slip':>5s} {'legs':>5s} {'win%':>5s} {'cred':>5s} {'stopped%':>8s} {'total/lot':>10s} {'worst/lot':>10s} {'lots for 1.5%/mo':>16s} {'worst @ that size':>18s}")
for slip in (0.5, 1.0):
    for label, kind, val in (("no stop", None, None), ("premium x2", "prem", 2.0), ("premium x3", "prem", 3.0), ("premium x5", "prem", 5.0),
                             ("spot 2%", "spot", 2.0), ("spot 3%", "spot", 3.0)):
        rows = [r for e in expiries for typ in TYPES if (r := leg(e, typ, kind, val, slip))]
        t = pd.DataFrame(rows)
        rs = t.pnl * t.lot
        tot = rs.sum()
        need = (CAPITAL * 0.015 * 24) / tot if tot > 0 else float("nan")
        print(f"{label:18s} {slip:5.1f} {len(t):5d} {(t.pnl>0).mean()*100:5.0f} {t.credit.mean():5.1f} {t.stopped.mean()*100:8.0f} {tot:10,.0f} {rs.min():10,.0f} {need:16.0f} {rs.min()*need:18,.0f}")
    print()
