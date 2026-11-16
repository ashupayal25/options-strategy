from datetime import date

import pytest

from otm_strategy.chain import ChainError, listed_expiry, parse_puts

PAYLOAD = {"records": {"underlyingValue": 25000.0, "data": [
    {"expiryDates": "24-Nov-2026", "strikePrice": 24000, "PE": {"buyPrice1": 8, "sellPrice1": 10, "lastPrice": 7, "openInterest": 500}},
    {"expiryDates": "24-Nov-2026", "strikePrice": 23500, "PE": {"buyPrice1": 0, "sellPrice1": 4, "lastPrice": 3, "openInterest": 90}},
    {"expiryDates": "24-Nov-2026", "strikePrice": 23000, "PE": {"buyPrice1": 1, "sellPrice1": 2, "lastPrice": 1, "openInterest": 0}},
    {"expiryDates": "01-Dec-2026", "strikePrice": 24000, "PE": {"buyPrice1": 20, "sellPrice1": 22, "lastPrice": 21, "openInterest": 10}}]}}


def test_parse_puts_uses_mid_else_last_and_drops_zero_open_interest():
    puts, spot = parse_puts(PAYLOAD, date(2026, 11, 24))
    assert puts == {24000.0: 9.0, 23500.0: 3.0} and spot == 25000.0


def test_parse_puts_raises_when_the_expiry_is_missing():
    with pytest.raises(ChainError):
        parse_puts(PAYLOAD, date(2026, 12, 8))


def test_listed_expiry_follows_a_holiday_shift():
    listed = ["17-Nov-2026", "23-Nov-2026", "01-Dec-2026"]
    assert listed_expiry(listed, date(2026, 11, 17)) == date(2026, 11, 17)
    assert listed_expiry(listed, date(2026, 11, 24)) == date(2026, 11, 23)
    assert listed_expiry(listed, date(2026, 12, 15)) is None
