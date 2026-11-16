"""Settings for the signal app. Defaults are the locked rules; every value can be overridden by an OTM_* variable."""
import os
from dataclasses import dataclass


def _env(name, default, cast):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    if cast is bool:
        return raw.strip().lower() in ("1", "true", "yes", "y", "on")
    return cast(raw)


@dataclass(frozen=True)
class Settings:
    lots: int = 2
    lot_size: int = 65
    step: int = 50
    put_delta: float = 15.0
    put_otm: float = 2.0  # fallback when no option chain is given
    call_otm: float = 3.0
    hedge_extra: float = 2.0
    rsi_skip: float = 70.0
    confirm: int = 2
    sell_sideways: bool = False
    expiry_weekday: int = 1  # Monday=0, Tuesday=1 ...; the weekly expiry day (verify on NSE)
    notify_daily_summary: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            lots=_env("OTM_LOTS", d.lots, int),
            lot_size=_env("OTM_LOT_SIZE", d.lot_size, int),
            step=_env("OTM_STEP", d.step, int),
            put_delta=_env("OTM_PUT_DELTA", d.put_delta, float),
            put_otm=_env("OTM_PUT_OTM", d.put_otm, float),
            call_otm=_env("OTM_CALL_OTM", d.call_otm, float),
            hedge_extra=_env("OTM_HEDGE_EXTRA", d.hedge_extra, float),
            rsi_skip=_env("OTM_RSI_SKIP", d.rsi_skip, float),
            confirm=_env("OTM_CONFIRM", d.confirm, int),
            sell_sideways=_env("OTM_SELL_SIDEWAYS", d.sell_sideways, bool),
            expiry_weekday=_env("OTM_EXPIRY_WEEKDAY", d.expiry_weekday, int),
            notify_daily_summary=_env("OTM_NOTIFY_DAILY_SUMMARY", d.notify_daily_summary, bool),
        )
