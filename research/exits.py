import itertools
import math

import numpy as np
import pandas as pd

import backtest as bt


def leg_value(s, ks, kh, t, vol, call, p):
    if t <= 0:
        sign = 1 if call else -1
        return min(max(sign * (s - ks), 0.0), abs(kh - ks))
    return bt.bs(s, ks, t, vol, p.rate, call) - bt.bs(s, kh, t, vol, p.rate, call)


def make_leg(s, em, mult, call, vol, dte, p):
    sign = 1 if call else -1
    ks = sign * math.ceil(sign * (s + sign * em * mult) / p.step) * p.step
    kh = sign * math.ceil(sign * (s + sign * em * (mult + p.hedge)) / p.step) * p.step
    if kh == ks:
        kh = ks + sign * p.step
    credit = leg_value(s, ks, kh, dte / 365.0, vol, call, p)
    return dict(call=call, ks=ks, kh=kh, credit=credit, width=abs(kh - ks), open=True, pnl=None)


def regime_exit(prev, cur, call):
    if cur == 9 and prev != 9:
        return True
    if call:
        return cur == 1 and prev in (0, -1)
    return cur == -1 and prev in (0, 1)


def run(df, kinds, hold, dte, mult, p, stop=None, flip=False, take=None):
    o, h, l, c = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    vix, reg = df["vix"].to_numpy(), df["reg"].to_numpy()
    sig = {k: df[k].to_numpy() for k in "SBE"}
    dates = df.index
    last, out = -10**9, []
    for i in range(len(df) - hold):
        kind = next((k for k in kinds if sig[k][i]), None)
        if kind is None or i - last < hold:
            continue
        last = i
        em = c[i] * vix[i] / 100 * math.sqrt(dte / 365.0)
        legs = [make_leg(c[i], em, mult, call, vix[i] / 100, dte, p)
                for call, need in ((True, kind in "SE"), (False, kind in "SB")) if need]
        for j in range(1, hold + 1):
            t, vol, k = max(dte * (1 - j / hold), 0) / 365.0, vix[i + j] / 100, i + j
            for lg in legs:
                if not lg["open"]:
                    continue
                call, cr = lg["call"], lg["credit"]
                if j == hold:
                    lg["pnl"] = cr - leg_value(c[k], lg["ks"], lg["kh"], 0, vol, call, p)
                    lg["open"] = False
                    continue
                if stop is not None:
                    cap = cr * (1 + stop)
                    v_open = leg_value(o[k], lg["ks"], lg["kh"], t, vol, call, p)
                    v_ext = leg_value(h[k] if call else l[k], lg["ks"], lg["kh"], t, vol, call, p)
                    if v_open >= cap or v_ext >= cap:
                        lg["pnl"] = cr - (v_open if v_open >= cap else cap) - 2 * p.cost_pts
                        lg["open"] = False
                        continue
                v_close = leg_value(c[k], lg["ks"], lg["kh"], t, vol, call, p)
                if flip and regime_exit(reg[k - 1], reg[k], call):
                    lg["pnl"] = cr - v_close - 2 * p.cost_pts
                    lg["open"] = False
                elif take is not None and v_close <= cr * (1 - take):
                    lg["pnl"] = cr - v_close - 2 * p.cost_pts
                    lg["open"] = False
        pnl = sum(lg["pnl"] for lg in legs) - 2 * p.cost_pts * len(legs)
        credit = sum(lg["credit"] for lg in legs)
        width = max(lg["width"] for lg in legs)
        out.append(dict(date=dates[i], kind=kind, pnl=pnl, credit=credit, max_loss=width - credit + 2 * p.cost_pts))
    return pd.DataFrame(out)


def stats(t, split="2024-01-01"):
    if t.empty:
        return dict(n=0)
    d = pd.to_datetime(t.date)
    wins, losses = t.pnl[t.pnl > 0].sum(), -t.pnl[t.pnl <= 0].sum()
    return dict(n=len(t), win=round((t.pnl > 0).mean() * 100, 1), avg=round(t.pnl.mean(), 2),
                pf=round(wins / losses, 2) if losses > 0 else float("inf"), worst=round(t.pnl.min(), 1),
                total=round(t.pnl.sum()), early=round(t.pnl[d < split].sum()), recent=round(t.pnl[d >= split].sum()))


def main():
    p = bt.make_parser().parse_args([])
    df = bt.build(bt.load("^NSEI", "nifty", p.start, False), bt.load("^INDIAVIX", "vix", p.start, False), p)
    pd.set_option("display.width", 200)
    rows = []
    for mult in (1.2, 1.5):
        for stop, flip, take in itertools.product((None, 1.0, 1.5, 2.0), (False, True), (None, 0.5)):
            t = run(df, "SBE", 5, 7, mult, p, stop, flip, take)
            rows.append(dict(mult=mult, stop=stop, flip=flip, take=take, **stats(t)))
    res = pd.DataFrame(rows)
    import os
    from otm_strategy.paths import OUTPUTS
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    res.to_csv(os.path.join(OUTPUTS, "exits_results.csv"), index=False)
    for mult in (1.2, 1.5):
        print(f"\n=== weekly, all entries, strikes {mult}x (points; early = before 2024, recent = 2024 onward) ===")
        print(res[res.mult == mult].drop(columns="mult").to_string(index=False))


if __name__ == "__main__":
    main()
