import sys
import numpy as np
import pandas as pd
import backtest as bt
import regime_full as rf

UNITS, CAP = 65, 1600000
start = pd.Timestamp("2019-02-11")


def strike_legs(df, e, short_pct, hedge_pct, slip, exit_mode):
    entry = next((d for d in rf.dayset if 5 <= (e - d).days <= 9 and (d, e) in rf.listed), None)
    if entry is None or e not in df.index or entry < start or entry not in df.index:
        return []
    reg = df.loc[entry, "reg"]
    if reg not in (1, -1):
        return []
    typ, sgn = ("PE", -1) if reg == 1 else ("CE", 1)
    day = rf.opts.loc[(entry, e)]
    spot = day["UndrlygPric"].iloc[0]
    s = day.xs(typ, level="OptnTp")
    s = s[s.SttlmPric > 0]
    k = s.index.to_numpy()
    tgt = spot * (1 + sgn * short_pct / 100)
    ks_c = k[k <= tgt] if sgn < 0 else k[k >= tgt]
    if len(ks_c) == 0: return []
    ks = ks_c.max() if sgn < 0 else ks_c.min()
    if s.loc[ks].OpnIntrst <= 0: return []
    tgt_h = ks * (1 + sgn * hedge_pct / 100)
    kh_c = k[k <= tgt_h] if sgn < 0 else k[k >= tgt_h]
    if len(kh_c) == 0: return []
    kh = kh_c.max() if sgn < 0 else kh_c.min()
    ps, ph = s.loc[ks].SttlmPric, s.loc[kh].SttlmPric
    credit, width = ps - ph, abs(kh - ks)
    st = df.loc[e, "Close"]
    pnl, how = credit - min(max(sgn * (st - ks), 0.0), width) - 2 * slip, "expiry"
    if exit_mode == "regime":
        for d in [x for x in rf.dayset if entry < x < e]:
            if d not in df.index: continue
            j = df.index.get_loc(d); prev, cur = df["reg"].iloc[j - 1], df["reg"].iloc[j]
            hit = (cur == 1 and prev in (0, -1)) if typ == "CE" else (cur == -1 and prev in (0, 1))
            hit = hit or (cur == 9 and prev != 9)
            if hit:
                a, b = (d, e, typ, float(ks)), (d, e, typ, float(kh))
                if a in rf.opts.index and b in rf.opts.index:
                    pnl, how = credit - (rf.opts.loc[a, "SttlmPric"] - rf.opts.loc[b, "SttlmPric"]) - 4 * slip, "regime"
                    break
    return [dict(entry=entry, typ=typ, credit=credit, width=width, pnl=pnl, how=how, dist=abs(ks / spot - 1) * 100)]


def run(df, short_pct, hedge_pct, slip, exit_mode):
    rows = [r for e in rf.expiries for r in strike_legs(df, e, short_pct, hedge_pct, slip, exit_mode)]
    return pd.DataFrame(rows)


def line(label, t, lots=1):
    if t.empty:
        return f"{label}: no trades"
    rs = t.pnl * UNITS * lots
    eq = rs.sort_index().cumsum()
    yrs = (rf.dayset[-1] - start).days / 365.25
    return (f"{label:44s} {len(t):4d} {(t.pnl>0).mean()*100:4.0f}% {t.credit.mean():6.1f} {t.width.mean():5.0f} "
            f"{rs.sum():10,.0f} {rs.sum()/yrs:9,.0f} {rs.min():9,.0f} {(eq-eq.cummax()).min():10,.0f} {((t.width-t.credit).max())*UNITS*lots:10,.0f} {(t.how=='regime').mean()*100:5.0f}%")


def main():
    for confirm in (2, 1):
        p = bt.make_parser().parse_args([]); p.confirm = confirm
        df = bt.build(rf.nifty, rf.vixd, p)
        print(f"\n===== confirmation {confirm} close(s). 1 lot = {UNITS} units. Rs, 2019-02-11 to 2026-11-13 (7.8 yrs) =====")
        print(f"{'setup':44s} {'legs':>4s} {'win':>5s} {'cred':>6s} {'width':>5s} {'total Rs':>10s} {'per year':>9s} {'worst':>9s} {'maxDD':>10s} {'max loss':>10s} {'exit%':>6s}")
        for slip in (0.5, 1.0):
            for hedge in (1.5, 2.0):
                for exit_mode, en in (("expiry", "hold to expiry"), ("regime", "regime exit")):
                    t = run(df, 1.0, hedge, slip, exit_mode)
                    for side, name in (("PE", "bullish puts"), ("CE", "bearish calls"), (None, "both")):
                        u = t if side is None else t[t.typ == side]
                        print(line(f"slip {slip} hedge {hedge}% {en} | {name}", u))
                print()
        if confirm == 2:
            t = run(df, 1.0, 2.0, 0.5, "regime")
            t["year"] = t.entry.dt.year
            t["rs"] = t.pnl * UNITS
            print("By year, 1 lot, hedge 2%, regime exit, 0.5pt slippage, Rs:")
            print(t.groupby(["year", "typ"]).rs.sum().unstack().round(0).to_string())
            print("\nWorst 6 legs:")
            print(t.nsmallest(6, "rs")[["entry", "typ", "credit", "width", "pnl", "rs", "how"]].round(1).to_string(index=False))



if __name__ == "__main__":
    main()
