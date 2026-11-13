"""Entry-day detection, strike selection, symbols and the call exit rule (pure functions, no I/O)."""
import math
from datetime import timedelta

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


def call_exit_hit(prev, cur):
    """Call legs exit when the regime turns bullish (from sideways or bearish) or to no-trade."""
    return (cur == 1 and prev in (0, -1)) or (cur == 9 and prev != 9)


def first_call_exit(regs, entered):
    """Date of the first regime change after `entered` that triggers the call exit, or None. regs: Series indexed by date."""
    for d in regs.index[regs.index.date > entered]:
        j = regs.index.get_loc(d)
        if call_exit_hit(int(regs.iloc[j - 1]), int(regs.iloc[j])):
            return d
    return None
