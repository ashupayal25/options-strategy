from datetime import date, timedelta

import pandas as pd

from otm_strategy.config import Settings
from otm_strategy.strategy import (call_exit_hit, first_call_exit, is_entry_day, next_expiry, strikes, symbol)

CFG = Settings()


def weekdays(start, end, holidays=()):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5 and d not in holidays:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_put_strikes_round_down_and_hedge_is_beyond():
    short, hedge = strikes(25299.3, "PE", CFG)
    assert short == 24750 and hedge == 24250
    assert short < 25299.3 * 0.99 and hedge < short


def test_call_strikes_round_up_and_hedge_is_beyond():
    short, hedge = strikes(25299.3, "CE", CFG)
    assert short == 26100 and hedge == 26650
    assert short > 25299.3 * 1.03 - 1 and hedge > short


def test_symbol_format():
    assert symbol(date(2025, 11, 18), 24650, "PE") == "NIFTY25N1824650PE"
    assert symbol(date(2025, 10, 7), 24000, "CE") == "NIFTY25O0724000CE"
    assert symbol(date(2026, 12, 1), 25000, "PE") == "NIFTY26D0125000PE"
    assert symbol(date(2026, 6, 9), 25000, "PE") == "NIFTY2660925000PE"


def test_entry_day_is_the_day_after_the_tuesday_expiry():
    days = weekdays(date(2026, 11, 2), date(2026, 11, 17))
    done = [d for d in days if d < date(2026, 11, 11)]
    assert is_entry_day(date(2026, 11, 11), done, 1) is True          # Wednesday after Tuesday 10 Nov
    done = [d for d in days if d < date(2026, 11, 12)]
    assert is_entry_day(date(2026, 11, 12), done, 1) is False         # Thursday
    done = [d for d in days if d < date(2026, 11, 9)]
    assert is_entry_day(date(2026, 11, 9), done, 1) is False          # Monday


def test_entry_day_when_the_expiry_tuesday_is_a_holiday():
    # Tuesday 10 Nov is a holiday: expiry moves to Monday 9 Nov, so Wednesday is the entry day
    days = weekdays(date(2026, 11, 2), date(2026, 11, 13), holidays={date(2026, 11, 10)})
    done = [d for d in days if d < date(2026, 11, 11)]
    assert is_entry_day(date(2026, 11, 11), done, 1) is True


def test_entry_day_when_monday_and_tuesday_are_holidays():
    days = weekdays(date(2026, 11, 2), date(2026, 11, 13), holidays={date(2026, 11, 9), date(2026, 11, 10)})
    done = [d for d in days if d < date(2026, 11, 11)]
    assert done[-1] == date(2026, 11, 6)                              # last trading day before today
    assert is_entry_day(date(2026, 11, 11), done, 1) is True


def test_next_expiry():
    assert next_expiry(date(2026, 11, 11), 1) == date(2026, 11, 17)
    assert next_expiry(date(2026, 11, 16), 1) == date(2026, 11, 17)


def test_call_exit_rule():
    assert call_exit_hit(prev=-1, cur=1) and call_exit_hit(prev=0, cur=1)
    assert call_exit_hit(prev=-1, cur=9) and call_exit_hit(prev=0, cur=9)
    assert not call_exit_hit(prev=-1, cur=-1) and not call_exit_hit(prev=-1, cur=0)
    assert not call_exit_hit(prev=9, cur=9) and not call_exit_hit(prev=1, cur=1)


def test_first_call_exit_finds_the_flip_after_entry():
    idx = pd.to_datetime(["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-11-02", "2026-11-03", "2026-11-04"])
    regs = pd.Series([-1, -1, -1, -1, -1, 9, 9], index=idx)
    assert first_call_exit(regs, date(2026, 10, 28)) == pd.Timestamp("2026-11-03")
    assert first_call_exit(regs, date(2026, 11, 3)) is None
