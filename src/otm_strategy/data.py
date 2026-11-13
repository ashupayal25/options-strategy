"""Daily Nifty and India VIX bars from Yahoo, with retries and a cached fallback."""
import io
import logging
import time

import pandas as pd
import yfinance as yf

log = logging.getLogger("otm.data")

SYMBOLS = {"nifty": "^NSEI", "vix": "^INDIAVIX"}


class DataError(RuntimeError):
    pass


def fetch(symbol, start="2014-01-01", retries=3, sleep=time.sleep):
    last = None
    for attempt in range(1, retries + 1):
        try:
            d = yf.download(symbol, start=start, interval="1d", auto_adjust=False, progress=False)
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            d.index = pd.to_datetime(d.index).tz_localize(None).normalize()
            d = d.dropna(subset=["Close"])
            if d.empty:
                raise DataError(f"no rows returned for {symbol}")
            return d
        except Exception as e:
            last = e
            log.warning("fetch %s failed (%s), attempt %d/%d", symbol, type(e).__name__, attempt, retries)
            if attempt < retries:
                sleep(2 * attempt)
    raise DataError(f"could not fetch {symbol}: {type(last).__name__}")


def _cache_key(name):
    return f"cache/{name}.csv"


def _read_cache(store, name):
    text = store.read_text(_cache_key(name))
    if not text:
        return None
    return pd.read_csv(io.StringIO(text), index_col=0, parse_dates=True)


def load_market(store, fetcher=fetch):
    """Return (nifty, vix, notes). Live data is cached in the store; if Yahoo fails the cache is used and a note is added."""
    frames, notes = {}, []
    for name, symbol in SYMBOLS.items():
        try:
            frames[name] = fetcher(symbol)
            store.write_text(_cache_key(name), frames[name].to_csv())
        except DataError as e:
            cached = _read_cache(store, name)
            if cached is None:
                raise
            frames[name] = cached
            notes.append(f"DATA WARNING: {symbol} live fetch failed ({e}); using cached bars up to {cached.index[-1].date()}.")
    return frames["nifty"], frames["vix"], notes
