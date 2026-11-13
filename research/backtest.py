import argparse
import math
import os

import numpy as np  # noqa: F401
import pandas as pd
import yfinance as yf

from otm_strategy.paths import DATA, OUTPUTS
OUTPUTS.mkdir(parents=True, exist_ok=True)
KINDS = {"all": "SBE", "sideways": "S", "bullish": "B", "bearish": "E"}


def load(symbol, name, start, refresh):
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, f"{name}.csv")
    if os.path.exists(path) and not refresh:
        return pd.read_csv(path, index_col=0, parse_dates=True)
    d = yf.download(symbol, start=start, auto_adjust=False, progress=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    d.to_csv(path)
    return d


# regime engine lives in the package (shared with the signal app)
from otm_strategy.regime import build, pct_rank, rma  # noqa: E402,F401


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(s, k, t, vol, r, call):
    d1 = (math.log(s / k) + (r + vol * vol / 2) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if call:
        return s * ncdf(d1) - k * math.exp(-r * t) * ncdf(d2)
    return k * math.exp(-r * t) * ncdf(-d2) - s * ncdf(-d1)


def spread_pnl(s, em, mult, call, iv, st, dte, p):
    t, vol = dte / 365.0, iv / 100.0
    sign = 1 if call else -1
    ks = sign * math.ceil(sign * (s + sign * em * mult) / p.step) * p.step
    kh = sign * math.ceil(sign * (s + sign * em * (mult + p.hedge)) / p.step) * p.step
    if kh == ks:
        kh = ks + sign * p.step
    credit = bs(s, ks, t, vol, p.rate, call) - bs(s, kh, t, vol, p.rate, call)
    loss = min(max(sign * (st - ks), 0.0), abs(kh - ks))
    return credit - loss - 2 * p.cost_pts, credit, abs(kh - ks)


def backtest(df, kinds, variant, hold, dte, mult, p):
    c, hi, lo = df["Close"].to_numpy(), df["High"].to_numpy(), df["Low"].to_numpy()
    vix, vavg = df["vix"].to_numpy(), df["vixavg"].to_numpy()
    sig = {k: df[k].to_numpy() for k in "SBE"}
    dates = df.index
    last, trades = -10**9, []
    for i in range(len(df) - hold):
        kind = next((k for k in kinds if sig[k][i]), None)
        if kind is None:
            continue
        if variant == "B" and not vix[i] > vavg[i]:
            continue
        if variant == "C" and not vix[i] > p.vix_floor:
            continue
        if i - last < hold:
            continue
        last = i
        em = c[i] * vix[i] / 100 * math.sqrt(dte / 365.0)
        call_l, put_l = c[i] + em * mult, c[i] - em * mult
        need_c, need_p = kind in "SE", kind in "SB"
        h, l, st = hi[i + 1:i + hold + 1].max(), lo[i + 1:i + hold + 1].min(), c[i + hold]
        touched = (need_c and h >= call_l) or (need_p and l <= put_l)
        closed_out = (need_c and st >= call_l) or (need_p and st <= put_l)
        breach = max((h - call_l) / c[i] * 100 if need_c else 0.0, (put_l - l) / c[i] * 100 if need_p else 0.0, 0.0)
        pnl, credit, width = 0.0, 0.0, 0.0
        for call, need in ((True, need_c), (False, need_p)):
            if need:
                a, b, w = spread_pnl(c[i], em, mult, call, vix[i], st, dte, p)
                pnl, credit, width = pnl + a, credit + b, max(width, w)
        trades.append(dict(date=dates[i], kind=kind, spot=c[i], vix=vix[i], touched=touched,
                           closed_out=closed_out, breach=breach if touched else 0.0, pnl=pnl, credit=credit,
                           max_loss=width - credit + 2 * p.cost_pts))
    return pd.DataFrame(trades)


def summarize(t):
    if t.empty:
        return dict(n=0)
    wins, losses = t.loc[t.pnl > 0, "pnl"], t.loc[t.pnl <= 0, "pnl"]
    tb = t[t.touched]
    return dict(n=len(t), never_touched=round((~t.touched).mean() * 100, 1),
                closed_inside=round((~t.closed_out).mean() * 100, 1),
                avg_breach=round(tb.breach.mean(), 2) if len(tb) else 0.0,
                max_breach=round(tb.breach.max(), 2) if len(tb) else 0.0,
                avg_credit=round(t.credit.mean(), 1), avg_pnl=round(t.pnl.mean(), 1),
                win_pct=round((t.pnl > 0).mean() * 100, 1), worst=round(t.pnl.min(), 1),
                pf=round(wins.sum() / -losses.sum(), 2) if losses.sum() < 0 else float("inf"),
                total_pnl=round(t.pnl.sum(), 0))


def make_parser():
    a = argparse.ArgumentParser()
    a.add_argument("--start", default="2007-09-17")
    a.add_argument("--refresh", action="store_true")
    a.add_argument("--adx-len", type=int, default=14)
    a.add_argument("--adx-side", type=float, default=20)
    a.add_argument("--adx-trend", type=float, default=20)
    a.add_argument("--dist", type=float, default=3.0)
    a.add_argument("--slope-flat", type=float, default=0.7)
    a.add_argument("--bbw-side", type=float, default=70)
    a.add_argument("--squeeze", type=float, default=5)
    a.add_argument("--confirm", type=int, default=2)
    a.add_argument("--vix-floor", type=float, default=13)
    a.add_argument("--step", type=int, default=50)
    a.add_argument("--hedge", type=float, default=0.6)
    a.add_argument("--cost-pts", type=float, default=1.0)
    a.add_argument("--rate", type=float, default=0.065)
    a.add_argument("--mults", default="1.0,1.2,1.5,1.8,2.0")
    return a


def main():
    p = make_parser().parse_args()

    df = build(load("^NSEI", "nifty", p.start, p.refresh), load("^INDIAVIX", "vix", p.start, p.refresh), p)
    print(f"Data: {df.index[0].date()} to {df.index[-1].date()}, {len(df)} daily bars")
    print("Regime days:", {k: int((df.reg == v).sum()) for k, v in (("bull", 1), ("bear", -1), ("side", 0), ("none", 9))})

    rows = []
    for hold, dte, label in ((5, 7, "weekly"), (25, 35, "monthly")):
        for kname, kinds in KINDS.items():
            for variant in "ABC":
                for m in [float(x) for x in p.mults.split(",")]:
                    t = backtest(df, kinds, variant, hold, dte, m, p)
                    rows.append(dict(horizon=label, kinds=kname, variant=variant, mult=m, **summarize(t)))
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(OUTPUTS, "results.csv"), index=False)

    pd.set_option("display.width", 200)
    cols = ["kinds", "variant", "mult", "n", "never_touched", "closed_inside", "avg_breach", "max_breach",
            "avg_credit", "avg_pnl", "win_pct", "worst", "pf", "total_pnl"]
    for label in ("weekly", "monthly"):
        print(f"\n=== {label}, variant A (no VIX filter) ===")
        print(res[(res.horizon == label) & (res.variant == "A")][cols].drop(columns="variant").to_string(index=False))
        print(f"\n=== {label}, variant comparison at 1.5x ===")
        print(res[(res.horizon == label) & (res.mult == 1.5)][cols].to_string(index=False))

    t = backtest(df, "SBE", "A", 5, 7, 1.5, p)
    t.to_csv(os.path.join(OUTPUTS, "trades_weekly_1.5x.csv"), index=False)
    t["year"] = pd.to_datetime(t.date).dt.year
    y = t.groupby("year").agg(n=("pnl", "size"), never_touched=("touched", lambda x: round((~x).mean() * 100, 1)),
                              pnl=("pnl", "sum")).round(1)
    print("\n=== weekly, variant A, 1.5x, all kinds: by year ===")
    print(y.to_string())


if __name__ == "__main__":
    main()
