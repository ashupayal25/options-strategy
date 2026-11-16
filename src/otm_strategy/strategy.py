"""Entry-day detection, strike selection, symbols and the call exit rule (pure functions, no I/O)."""
import math
from datetime import timedelta

RATE = 0.065

NAMES = {1: "BULLISH", -1: "BEARISH", 0: "SIDEWAYS", 9: "NO TRADE"}
MONTH_CODE = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D"}


def actual_expiry(nominal, trading, today):
    """The weekly expiry date: the nominal weekday, or the last trading day before it if that day was a holiday."""
    if nominal in trading:
        return nominal
    if nominal < today:
        earlier = [d for d in trading if d <= nominal]
        return max(earlier) if earlier else None
    return None


def is_entry_day(today, completed, expiry_weekday):
    """True when the last completed trading day was a weekly expiry (so today is the day after)."""
    trading = set(completed)
    prev = completed[-1]
    for anchor in (prev, today):
        monday = anchor - timedelta(days=anchor.weekday())
        nominal = monday + timedelta(days=expiry_weekday)
        if actual_expiry(nominal, trading, today) == prev:
            return True
    return False


def next_expiry(today, expiry_weekday):
    monday = today - timedelta(days=today.weekday())
    for k in (0, 7):
        nominal = monday + timedelta(days=expiry_weekday + k)
        if nominal > today:
            return nominal


def symbol(expiry, strike, typ):
    """Likely Kite weekly symbol, e.g. NIFTY25N1824650PE. The last expiry of a month uses a different format: verify."""
    return f"NIFTY{expiry.year % 100:02d}{MONTH_CODE[expiry.month]}{expiry.day:02d}{int(strike)}{typ}"


def strikes(spot, side, cfg):
    """Short and hedge strikes from the reference spot. PE: below spot, CE: above spot; hedge is beyond the short."""
    step = cfg.step
    if side == "PE":
        short = math.floor(spot * (1 - cfg.put_otm / 100) / step) * step
        hedge = math.floor(short * (1 - cfg.hedge_extra / 100) / step) * step
    else:
        short = math.ceil(spot * (1 + cfg.call_otm / 100) / step) * step
        hedge = math.ceil(short * (1 + cfg.hedge_extra / 100) / step) * step
    return short, hedge


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _bs_put(spot, k, t, vol):
    d1 = (math.log(spot / k) + (RATE + vol * vol / 2) * t) / (vol * math.sqrt(t))
    return k * math.exp(-RATE * t) * _ncdf(-(d1 - vol * math.sqrt(t))) - spot * _ncdf(-d1)


def put_delta(spot, k, t, price):
    """Absolute delta of a put from its price (Black-Scholes implied vol), or None if the price has no implied vol."""
    if price <= max(k - spot, 0.0) * math.exp(-RATE * t) + 1e-6 or _bs_put(spot, k, t, 3.0) < price:
        return None
    lo, hi = 0.01, 3.0
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if _bs_put(spot, k, t, mid) > price else (mid, hi)
    vol = (lo + hi) / 2
    return 1 - _ncdf((math.log(spot / k) + (RATE + vol * vol / 2) * t) / (vol * math.sqrt(t)))


def delta_put_strikes(puts, spot, days, cfg):
    """Short = the OTM put with the largest delta not above cfg.put_delta; hedge = listed strike cfg.hedge_extra % beyond it.
    puts: {strike: price}. Returns (short, hedge, delta) or None when no strike qualifies."""
    t, best = days / 365.0, None
    for k, price in puts.items():
        d = put_delta(spot, k, t, price) if k < spot else None
        if d is not None and d <= cfg.put_delta / 100 and (best is None or d > best[0]):
            best = (d, k)
    if best is None:
        return None
    below = [k for k in puts if k <= best[1] * (1 - cfg.hedge_extra / 100)]
    return (best[1], max(below), best[0]) if below else None


def call_exit_hit(close, sma50):
    """Call legs exit when Nifty closes above its SMA50."""
    return bool(close > sma50)


def first_call_exit(df, entered):
    """Date of the first close above SMA50 after `entered`, or None. df: regime frame indexed by date."""
    for d in df.index[df.index.date > entered]:
        if call_exit_hit(df.Close.loc[d], df.sma50.loc[d]):
            return d
    return None
