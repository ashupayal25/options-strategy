"""Nifty put prices for one expiry from the NSE option-chain feed."""
import logging
import time
from datetime import datetime, timedelta

import requests

log = logging.getLogger("otm.chain")

INFO_URL = "https://www.nseindia.com/api/option-chain-contract-info?symbol=NIFTY"
URL = "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY&expiry={expiry}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/option-chain"}


class ChainError(RuntimeError):
    pass


def parse_puts(payload, expiry):
    """({strike: price}, spot) for the expiry. Price is the bid-ask mid, else the last price; strikes without open interest are dropped."""
    key = expiry.strftime("%d-%b-%Y")
    rows = [r for r in payload.get("records", {}).get("data", []) if r.get("expiryDates") == key and r.get("PE")]
    puts = {}
    for r in rows:
        pe = r["PE"]
        bid, ask = pe.get("buyPrice1") or 0, pe.get("sellPrice1") or 0
        price = (bid + ask) / 2 if bid > 0 and ask > 0 else pe.get("lastPrice") or 0
        if price > 0 and (pe.get("openInterest") or 0) > 0:
            puts[float(r["strikePrice"])] = float(price)
    spot = payload.get("records", {}).get("underlyingValue")
    if not puts or not spot:
        raise ChainError(f"no usable put prices for expiry {key}")
    return puts, float(spot)


def listed_expiry(listed, nominal):
    """The nominal expiry if NSE lists it, else the latest listed one up to 4 days earlier (holiday shift), else None."""
    dates = sorted(datetime.strptime(x, "%d-%b-%Y").date() for x in listed)
    if nominal in dates:
        return nominal
    earlier = [d for d in dates if nominal - timedelta(days=4) <= d < nominal]
    return earlier[-1] if earlier else None


def fetch_put_chain(expiry, retries=3, sleep=time.sleep):
    """(puts, spot, expiry actually used). The weekly expiry moves earlier when its day is a holiday."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            s = requests.Session()
            s.headers.update(HEADERS)
            s.get("https://www.nseindia.com/option-chain", timeout=15)
            info = s.get(INFO_URL, timeout=15)
            info.raise_for_status()
            used = listed_expiry(info.json()["expiryDates"], expiry)
            if used is None:
                raise ChainError(f"NSE does not list an expiry near {expiry}")
            r = s.get(URL.format(expiry=used.strftime("%d-%b-%Y")), timeout=15)
            r.raise_for_status()
            return (*parse_puts(r.json(), used), used)
        except ChainError:
            raise
        except Exception as e:
            last = e
            log.warning("NSE chain fetch failed (%s), attempt %d/%d", type(e).__name__, attempt, retries)
            if attempt < retries:
                sleep(3 * attempt)
    raise ChainError(f"NSE option chain unavailable ({type(last).__name__})")
