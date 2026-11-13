import sys
import numpy as np
import pandas as pd
import backtest as bt
import real_backtest as rb

import os
SHORT_PX, HEDGE_PX, SLIP, CAPITAL = 10.0, float(os.environ.get("HEDGE_PX", 2.0)), 1.0, 1600000
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
    far = far[far.SttlmPric <= SHORT_PX]
    if far.empty:
        return None
    kh = (far.SttlmPric - HEDGE_PX).abs().idxmin()
    return ks, kh, cand.loc[ks].SttlmPric, far.loc[kh].SttlmPric


def trade(e, mode, stop, flip):
    entry = next((pd.Timestamp(x) for x in days if 5 <= (e - pd.Timestamp(x)).days <= 9 and (pd.Timestamp(x), e) in listed), None)
    if entry is None or e not in df.index:
        return None
    k0 = df.index.searchsorted(entry) - 1
    reg = df["reg"].iloc[k0]
    if mode == "regime":
        if reg not in (1, -1):
            return None
        typ = "CE" if reg == -1 else "PE"
    else:
        typ = mode
    day = opts.loc[(entry, e)]
    spot, lot = day["UndrlygPric"].iloc[0], int(day["NewBrdLotQty"].iloc[0])
    pk = pick(day.droplevel(0) if False else day, typ, spot)
    if pk is None:
        return None
    ks, kh, ps, ph = pk
    sgn = 1 if typ == "CE" else -1
    credit, width = ps - ph, abs(kh - ks)
    st = df.loc[e, "Close"]
    pnl = credit - min(max(sgn * (st - ks), 0.0), width) - 2 * SLIP
    ex = "expiry"
    for n, d in enumerate([pd.Timestamp(x) for x in days if entry < pd.Timestamp(x) < e]):
        j = df.index.get_loc(d)
        hit_stop = stop is not None and sgn * (df["Close"].iloc[j] / spot - 1) * 100 >= stop
        prev, cur = df["reg"].iloc[j - 1], df["reg"].iloc[j]
        hit_flip = flip and ((cur == 1 and prev in (0, -1)) if typ == "CE" else (cur == -1 and prev in (0, 1)) or (cur == 9 and prev != 9))
        if flip and typ == "CE":
            hit_flip = hit_flip or (cur == 9 and prev != 9)
        if hit_stop or hit_flip:
            a, b = (d, e, typ, float(ks)), (d, e, typ, float(kh))
            if a in opts.index and b in opts.index:
                pnl = credit - (opts.loc[a, "SttlmPric"] - opts.loc[b, "SttlmPric"]) - 4 * SLIP
                ex = "stop" if hit_stop else "flip"
                break
    return dict(entry=entry, typ=typ, lot=lot, credit=credit, width=width, pnl=pnl, ex=ex, dist=abs(ks / spot - 1) * 100)


def report(label, rows, start, lots):
    t = pd.DataFrame(rows)
    t = t[t.entry >= start]
    if t.empty:
        return
    rs = t.pnl * t.lot * lots
    eq = rs.cumsum()
    print(f"{label:34s} {len(t):4d} {(t.pnl > 0).mean()*100:5.0f} {t.credit.mean():6.1f} {t.width.mean():6.0f} {t.dist.mean():5.1f}% "
          f"{rs.sum():10,.0f} {rs.sum()/CAPITAL*100:6.1f}% {rs.min():10,.0f} {(eq-eq.cummax()).min():10,.0f} "
          f"{((t.width - t.credit) * t.lot * lots).max():10,.0f} {(t.ex != 'expiry').mean()*100:6.0f}")


lots = int(sys.argv[1]) if len(sys.argv) > 1 else 20
start = pd.Timestamp(sys.argv[2]) if len(sys.argv) > 2 else pd.Timestamp("2024-11-13")
print(f"Sell ~Rs{SHORT_PX:.0f} option, buy ~Rs{HEDGE_PX:.0f} option, weekly Nifty, real prices, {lots} lots, entries since {start.date()}, 1pt slippage per fill")
print(f"{'setup':34s} {'n':>4s} {'win%':>5s} {'cred':>6s} {'width':>6s} {'dist':>6s} {'total Rs':>10s} {'ret':>7s} {'worst Rs':>10s} {'maxDD Rs':>10s} {'maxloss Rs':>10s} {'exit%':>6s}")
for mode, name in (("PE", "put spread, every week"), ("CE", "call spread, every week"), ("regime", "regime-direction")):
    for stop, flip, sl in ((None, False, "no stop"), (2.0, False, "2% spot stop"), (3.0, False, "3% spot stop")) + (((None, True, "regime exit"), (3.0, True, "regime exit + 3% stop")) if mode == "regime" else ()):
        rows = [r for e in expiries if (r := trade(e, mode, stop, flip))]
        report(f"{name}, {sl}", rows, start, lots)
    print()
