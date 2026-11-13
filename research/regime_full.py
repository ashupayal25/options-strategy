import math
import os
import sys

import numpy as np
import pandas as pd

import backtest as bt

from otm_strategy.paths import ROOT as HERE, OUTPUTS
OUTPUTS.mkdir(parents=True, exist_ok=True)
CAPITAL = 1600000
STEP = 50
PUT_OTM = 4.0
CALL_OTM = 3.0
HEDGE_EXTRA = 2.0
nifty, vixd = bt.load("^NSEI", "nifty", "2007-09-17", False), bt.load("^INDIAVIX", "vix", "2007-09-17", False)


def lot_for(d):
    return 75 if d < pd.Timestamp("2021-07-01") else 50 if d < pd.Timestamp("2024-04-26") else 25


def load_all():
    new = pd.read_csv(os.path.join(HERE, "data", "bhav", "nifty_options.csv"), parse_dates=["TradDt", "XpryDt"])
    old = pd.read_csv(os.path.join(HERE, "data", "bhav", "nifty_options_old.csv"), parse_dates=["TradDt", "XpryDt"])
    close = nifty["Close"]
    close.index = pd.to_datetime(close.index)
    old["UndrlygPric"] = old.TradDt.map(close)
    old["NewBrdLotQty"] = old.TradDt.map(lot_for)
    old = old.dropna(subset=["UndrlygPric"])
    new = new[new.TradDt > old.TradDt.max()]
    both = pd.concat([old, new]).drop_duplicates(["TradDt", "XpryDt", "OptnTp", "StrkPric"])
    both = both.set_index(["TradDt", "XpryDt", "OptnTp", "StrkPric"]).sort_index()
    return both, sorted(both.index.get_level_values("TradDt").unique())


opts, days = load_all()
expiries = sorted(opts.index.get_level_values("XpryDt").unique())
listed = set(zip(opts.index.get_level_values("TradDt"), opts.index.get_level_values("XpryDt")))
dayset = [pd.Timestamp(x) for x in days]


def nearest_listed(cand, target, prefer_otm_side):
    """Pick listed strike closest to target; never closer to ATM than target."""
    if cand.empty:
        return None
    if prefer_otm_side > 0:
        far = cand[cand.index >= target]
    else:
        far = cand[cand.index <= target]
    if far.empty:
        return None
    return (far.index.to_series() - target).abs().idxmin()


def pick(day, typ, spot, put_otm, call_otm, hedge_extra, step=STEP):
    s = day.xs(typ, level="OptnTp")
    s = s[s.OpnIntrst > 0]
    s = s[s.index > spot] if typ == "CE" else s[s.index < spot]
    cand = s[s.SttlmPric > 0]
    if cand.empty:
        return None

    if typ == "CE":
        short_tgt = spot * (1 + call_otm / 100)
        short_tgt = math.ceil(short_tgt / step) * step
        hedge_tgt = spot * (1 + (call_otm + hedge_extra) / 100)
        hedge_tgt = math.ceil(hedge_tgt / step) * step
        ks = nearest_listed(cand, short_tgt, +1)
        if ks is None:
            return None
        far = cand[cand.index > ks]
        kh = nearest_listed(far, max(hedge_tgt, ks + step), +1)
    else:
        short_tgt = spot * (1 - put_otm / 100)
        short_tgt = math.floor(short_tgt / step) * step
        hedge_tgt = spot * (1 - (put_otm + hedge_extra) / 100)
        hedge_tgt = math.floor(hedge_tgt / step) * step
        ks = nearest_listed(cand, short_tgt, -1)
        if ks is None:
            return None
        far = cand[cand.index < ks]
        kh = nearest_listed(far, min(hedge_tgt, ks - step), -1)

    if kh is None:
        return None
    return float(ks), float(kh), float(cand.loc[ks].SttlmPric), float(far.loc[kh].SttlmPric)


def settle(d, e, typ, ks, kh):
    a, b = (d, e, typ, float(ks)), (d, e, typ, float(kh))
    if a not in opts.index or b not in opts.index:
        return None
    return opts.loc[a, "SttlmPric"] - opts.loc[b, "SttlmPric"]


def legs(df, e, sideways, put_otm, call_otm, hedge_extra, slip, start, hard_kill=True, block=None):
    entry = next((d for d in dayset if 5 <= (e - d).days <= 9 and (d, e) in listed), None)
    if entry is None or e not in df.index or entry < start or entry not in df.index:
        return []
    reg = df.loc[entry, "reg"]
    types = {1: ["PE"], -1: ["CE"], 0: ["PE", "CE"] if sideways else []}.get(reg, [])
    if block is not None and block.loc[entry]:
        types = [t for t in types if t != "CE"]
    day = opts.loc[(entry, e)]
    spot, lot = float(day["UndrlygPric"].iloc[0]), int(day["NewBrdLotQty"].iloc[0])
    out = []
    for typ in types:
        pk = pick(day, typ, spot, put_otm, call_otm, hedge_extra)
        if pk is None:
            continue
        ks, kh, ps, ph = pk
        sgn = 1 if typ == "CE" else -1
        credit, width = ps - ph, abs(kh - ks)
        st = df.loc[e, "Close"]
        pnl, how = credit - min(max(sgn * (st - ks), 0.0), width) - 2 * slip, "expiry"
        for d in [x for x in dayset if entry < x < e]:
            if d not in df.index:
                continue
            j = df.index.get_loc(d)
            prev, cur = df["reg"].iloc[j - 1], df["reg"].iloc[j]
            spot_d = float(df.loc[d, "Close"])
            hit_regime = (cur == 1 and prev in (0, -1)) if typ == "CE" else (cur == -1 and prev in (0, 1))
            hit_regime = hit_regime or (cur == 9 and prev != 9)
            hit_hard = hard_kill and ((typ == "CE" and spot_d >= ks) or (typ == "PE" and spot_d <= ks))
            hit_block = block is not None and typ == "CE" and block.loc[d] and not block.loc[df.index[j - 1]]
            if hit_regime or hit_hard or hit_block:
                debit = settle(d, e, typ, ks, kh)
                if debit is None:
                    continue
                reason = "hard" if hit_hard and not hit_regime else ("block" if hit_block and not hit_regime else "regime")
                if hit_hard and hit_regime:
                    reason = "hard"
                pnl, how = credit - debit - 4 * slip, reason
                break
        otm_pct = abs(ks - spot) / spot * 100
        out.append(dict(
            entry=entry, typ=typ, reg=reg, lot=lot, ks=ks, kh=kh, credit=credit, width=width,
            otm_pct=otm_pct, pnl=pnl, how=how, spot=spot,
        ))
    return out


def run(df, sideways, put_otm, call_otm, hedge_extra, slip, start, hard_kill=True, block=None):
    rows = [
        r for e in expiries
        for r in legs(df, e, sideways, put_otm, call_otm, hedge_extra, slip, start, hard_kill, block)
    ]
    t = pd.DataFrame(rows)
    if not t.empty:
        t["rs"] = t.pnl * t.lot
    return t


if __name__ == "__main__":
    start = pd.Timestamp(sys.argv[1]) if len(sys.argv) > 1 else pd.Timestamp("2019-02-11")
    print(
        "Option data:", dayset[0].date(), "to", dayset[-1].date(),
        f"({len(dayset)} trading days). Lot size assumed 75 / 50 / 25 before 2024-07 (not in the old files).",
    )
    print(f"Strike rule: PE {PUT_OTM}% OTM, CE {CALL_OTM}% OTM, hedge +{HEDGE_EXTRA}% beyond short. Hard kill if spot closes beyond short.")
    for confirm in (2, 1):
        p = bt.make_parser().parse_args([])
        p.confirm = confirm
        df = bt.build(nifty, vixd, p)
        print(f"\n=== confirmation {confirm} close(s) ===")
        hdr = f"{'sideways':>8s} {'hard':>5s} {'slip':>4s} {'legs':>5s} {'win%':>5s} {'reg%':>5s} {'hard%':>5s} {'total/lot Rs':>12s} {'worst/lot Rs':>12s} {'avg OTM%':>8s} {'avg width':>9s}"
        print(hdr)
        for sw in (False, True):
            for hard in (True, False):
                for slip in (0.5, 1.0):
                    t = run(df, sw, PUT_OTM, CALL_OTM, HEDGE_EXTRA, slip, start, hard_kill=hard)
                    if t.empty:
                        continue
                    print(
                        f"{str(sw):>8s} {str(hard):>5s} {slip:4.1f} {len(t):5d} "
                        f"{(t.pnl > 0).mean() * 100:5.0f} {(t.how == 'regime').mean() * 100:5.0f} "
                        f"{(t.how == 'hard').mean() * 100:5.0f} {t.rs.sum():12,.0f} {t.rs.min():12,.0f} "
                        f"{t.otm_pct.mean():8.2f} {t.width.mean():9.0f}"
                    )
        if confirm == 2:
            t = run(df, False, PUT_OTM, CALL_OTM, HEDGE_EXTRA, 0.5, start, hard_kill=True)
            t["year"] = t.entry.dt.year
            y = t.groupby("year").agg(
                legs=("rs", "size"),
                win=("pnl", lambda x: round((x > 0).mean() * 100)),
                total_rs=("rs", "sum"),
                worst_rs=("rs", "min"),
                regime_exit=("how", lambda x: round((x == "regime").mean() * 100)),
                hard_exit=("how", lambda x: round((x == "hard").mean() * 100)),
            )
            print("\nBy year (confirm 2, PE 4% / CE 3%, sideways OFF, hard kill ON, 0.5pt slippage), Rs per lot:")
            print(y.round(0).to_string())
            print("\nWorst 8 legs (Rs per lot):")
            cols = ["entry", "typ", "reg", "spot", "ks", "otm_pct", "credit", "width", "pnl", "rs", "how"]
            print(t.nsmallest(8, "rs")[cols].round(1).to_string(index=False))
            t.to_csv(os.path.join(OUTPUTS, "full_trades_pct_otm.csv"), index=False)
