import pandas as pd
import regime_full as rf


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


def entry_for(e, entry_dte):
    if entry_dte:
        c = [d for d in rf.dayset if 1 <= (e - d).days <= entry_dte and (d, e) in rf.listed]
        return max(c, key=lambda d: (e - d).days) if c else None
    return next((d for d in rf.dayset if 5 <= (e - d).days <= 9 and (d, e) in rf.listed), None)


def run(df, sideways, short_px, hedge_px, slip, start, entry_dte=0):
    rows = []
    for e in rf.expiries:
        entry = entry_for(e, entry_dte)
        if entry is None or e not in df.index or entry < start or entry not in df.index: continue
        reg = df.loc[entry, "reg"]
        types = {1: ["PE"], -1: ["CE"], 0: ["PE", "CE"] if sideways else []}.get(reg, [])
        day = rf.opts.loc[(entry, e)]
        spot, lot = float(day["UndrlygPric"].iloc[0]), int(day["NewBrdLotQty"].iloc[0])
        for typ in types:
            pk = pick(day, typ, spot, short_px, hedge_px)
            if pk is None: continue
            ks, kh, ps, ph = pk
            sgn = 1 if typ == "CE" else -1
            credit, width = ps - ph, abs(kh - ks)
            st = df.loc[e, "Close"]
            pnl, how = credit - min(max(sgn * (st - ks), 0.0), width) - 2 * slip, "expiry"
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
            rows.append(dict(entry=entry, typ=typ, lot=lot, credit=credit, width=width, pnl=pnl, how=how))
    t = pd.DataFrame(rows)
    t["rs"] = t.pnl * t.lot
    return t
