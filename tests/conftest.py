from datetime import date

import numpy as np
import pandas as pd
import pytest


def make_frames(n=420, drift=0.002, end=date(2026, 11, 13), segments=None, noise=0.002, seed=7):
    """Synthetic daily Nifty and VIX bars (seeded noise). segments: list of (days, daily_drift) to chain trends."""
    segments = segments or [(n, drift)]
    rets = np.concatenate([np.full(d, r) for d, r in segments])
    rets = rets + np.random.default_rng(seed).normal(0, noise, len(rets))
    idx = pd.bdate_range(end=end, periods=len(rets))
    close = 10000 * np.cumprod(1 + rets)
    prev = np.concatenate([[close[0]], close[:-1]])
    nifty = pd.DataFrame({"Open": prev, "High": np.maximum(prev, close) * 1.001,
                          "Low": np.minimum(prev, close) * 0.999, "Close": close}, index=idx)
    vix = pd.DataFrame({"Close": np.full(len(idx), 15.0)}, index=idx)
    return nifty, vix


@pytest.fixture
def uptrend():
    return make_frames(drift=0.002)


@pytest.fixture
def downtrend():
    return make_frames(drift=-0.002)


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, text, urgent=False):
        self.sent.append((text, urgent))
        return True
