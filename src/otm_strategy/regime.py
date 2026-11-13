"""Regime engine shared by the app and the research scripts (moved from research/backtest.py unchanged)."""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class RegimeParams:
    adx_len: int = 14
    adx_side: float = 20
    adx_trend: float = 20
    dist: float = 3.0
    slope_flat: float = 0.7
    bbw_side: float = 70
    squeeze: float = 5
    confirm: int = 2


def rma(s, n):
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def pct_rank(s, n):
    a = s.to_numpy()
    out = np.full(len(a), np.nan)
    for i in range(n, len(a)):
        if not np.isnan(a[i]):
            out[i] = (a[i - n:i] <= a[i]).sum() / n * 100
    return pd.Series(out, index=s.index)


def build(nifty, vix, p):
    """Return the daily frame with indicators and the confirmed regime in column `reg`.

    reg: 1 bullish, -1 bearish, 0 sideways, 9 no trade.
    """
    df = nifty[["Open", "High", "Low", "Close"]].dropna().copy()
    h, l, c = df["High"], df["Low"], df["Close"]
    up, down = h.diff(), -l.diff()
    plus = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    trr = rma(tr, p.adx_len)
    dip, dim = 100 * rma(plus, p.adx_len) / trr, 100 * rma(minus, p.adx_len) / trr
    df["adx"] = 100 * rma((dip - dim).abs() / (dip + dim).replace(0, 1), p.adx_len)
    df["sma20"], df["sma50"], df["sma200"] = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    df["slope"] = (df["sma50"] - df["sma50"].shift(5)) / df["sma50"].shift(5) * 100
    dev = 2 * c.rolling(20).std(ddof=0)
    df["bbu"], df["bbl"] = df["sma20"] + dev, df["sma20"] - dev
    df["bbrank"] = pct_rank((df["bbu"] - df["bbl"]) / df["sma20"], 126)
    delta = c.diff()
    df["rsi"] = 100 - 100 / (1 + rma(delta.clip(lower=0), 14) / rma((-delta).clip(lower=0), 14))
    v = vix["Close"].dropna()
    df["vix"] = v.reindex(df.index, method="ffill")
    df["vixavg"] = v.rolling(50).mean().reindex(df.index, method="ffill")

    squeeze = df["bbrank"] < p.squeeze
    bull = (c > df["sma50"]) & (c > df["sma200"]) & (df["slope"] > 0) & (df["adx"] > p.adx_trend)
    bear = (c < df["sma50"]) & (c < df["sma200"]) & (df["slope"] < 0) & (df["adx"] > p.adx_trend)
    side = ((df["adx"] < p.adx_side) & ((c / df["sma50"] - 1).abs() * 100 <= p.dist)
            & (df["slope"].abs() <= p.slope_flat) & (df["bbrank"] <= p.bbw_side))
    raw = np.where(squeeze, 9, np.where(bull, 1, np.where(bear, -1, np.where(side, 0, 9))))

    reg = np.full(len(df), 9)
    cand, cnt, cur = 9, 0, 9
    for i, r in enumerate(raw):
        if r == cand:
            cnt += 1
        else:
            cand, cnt = r, 1
        if cnt >= p.confirm and cand != cur:
            cur = cand
        reg[i] = cur
    df["reg"] = reg

    over = (c > df["bbu"]) | (c < df["bbl"]) | (df["rsi"] > 70) | (df["rsi"] < 30)
    rp = df["rsi"].shift(1)
    df["S"] = (df["reg"] == 0) & ~over & (df["rsi"] >= 40) & (df["rsi"] <= 60)
    df["B"] = ((df["reg"] == 1) & ~over & ((df["Low"] <= df["sma20"]) | (df["Low"] <= df["bbl"]))
               & (rp <= 50) & (df["rsi"] > rp))
    df["E"] = ((df["reg"] == -1) & ~over & ((df["High"] >= df["sma20"]) | (df["High"] >= df["bbu"]))
               & (rp >= 50) & (df["rsi"] < rp))
    return df.dropna(subset=["sma200", "bbrank", "vix", "vixavg", "rsi"])
