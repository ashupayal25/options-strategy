import numpy as np
import pandas as pd

from otm_strategy.regime import RegimeParams, build, pct_rank, rma
from conftest import make_frames


def test_steady_uptrend_is_bullish(uptrend):
    df = build(*uptrend, RegimeParams())
    assert int(df.reg.iloc[-1]) == 1


def test_steady_downtrend_is_bearish(downtrend):
    df = build(*downtrend, RegimeParams())
    assert int(df.reg.iloc[-1]) == -1


def test_regime_values_are_valid(uptrend):
    df = build(*uptrend, RegimeParams())
    assert set(df.reg.unique()) <= {1, -1, 0, 9}


def test_every_confirmed_regime_lasts_at_least_the_confirmation_length():
    nifty, vix = make_frames(segments=[(300, 0.002), (60, -0.003), (60, 0.003)])
    reg = build(nifty, vix, RegimeParams(confirm=3)).reg
    runs = reg.groupby((reg != reg.shift()).cumsum()).size().iloc[1:-1]  # ignore the first and the still-open last run
    assert len(runs) > 0 and (runs >= 3).all()


def test_helpers():
    s = rma(pd.Series([1.0, 2.0, 3.0, 4.0]), 2)
    assert len(s) == 4 and s.iloc[-1] > s.iloc[0]
    r = pct_rank(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
    assert np.isnan(r.iloc[0]) and r.iloc[-1] == 100.0
