import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta

import pandas as pd

from otm_strategy.paths import ROOT as HERE, OUTPUTS
OUTPUTS.mkdir(parents=True, exist_ok=True)
OUT_DIR = os.path.join(HERE, "data", "bhav")
OUT = os.path.join(OUT_DIR, "nifty_options.csv")
URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d}_F_0000.csv.zip"
KEEP = ["TradDt", "XpryDt", "StrkPric", "OptnTp", "OpnPric", "HghPric", "LwPric", "ClsPric",
        "SttlmPric", "UndrlygPric", "OpnIntrst", "TtlTradgVol", "NewBrdLotQty"]
START = date(2024, 7, 8)


def fetch(day):
    req = urllib.request.Request(URL.format(d=day.strftime("%Y%m%d")), headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            raw = urllib.request.urlopen(req, timeout=40).read()
            break
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    else:
        return None
    z = zipfile.ZipFile(io.BytesIO(raw))
    df = pd.read_csv(z.open(z.namelist()[0]))
    n = df[(df.FinInstrmTp == "IDO") & (df.TckrSymb == "NIFTY")]
    return n[KEEP]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    have = pd.read_csv(OUT) if os.path.exists(OUT) else pd.DataFrame(columns=KEEP)
    done = set(have.TradDt.unique())
    frames, missing = [have], []
    day, today = START, date.today()
    while day <= today:
        if day.weekday() < 5 and day.isoformat() not in done:
            d = fetch(day)
            if d is None or d.empty:
                missing.append(day.isoformat())
            else:
                frames.append(d)
                print("ok", day, len(d), flush=True)
            time.sleep(0.4)
        day += timedelta(days=1)
        if len(frames) % 25 == 0 and len(frames) > 1:
            pd.concat(frames).to_csv(OUT, index=False)
    pd.concat(frames).to_csv(OUT, index=False)
    print("done; no file for", len(missing), "weekdays (holidays or unavailable)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
