import io
import os
import zipfile

import pandas as pd

from otm_strategy.paths import ROOT as HERE, OUTPUTS
OUTPUTS.mkdir(parents=True, exist_ok=True)
SRC = os.path.join(HERE, "data", "bhav_old")
OUT = os.path.join(HERE, "data", "bhav", "nifty_options_old.csv")
frames, bad = [], []
for name in sorted(os.listdir(SRC)):
    if not name.endswith(".zip"):
        continue
    try:
        z = zipfile.ZipFile(os.path.join(SRC, name))
        raw = pd.read_csv(z.open(z.namelist()[0]), usecols=lambda c: not c.startswith("Unnamed"))
    except Exception as e:
        bad.append((name, str(e)[:60]))
        continue
    n = raw[(raw.INSTRUMENT == "OPTIDX") & (raw.SYMBOL == "NIFTY")]
    if n.empty:
        bad.append((name, "no NIFTY rows"))
        continue
    frames.append(pd.DataFrame({
        "TradDt": pd.to_datetime(n.TIMESTAMP, format="%d-%b-%Y"),
        "XpryDt": pd.to_datetime(n.EXPIRY_DT, format="%d-%b-%Y"),
        "StrkPric": n.STRIKE_PR.astype(float), "OptnTp": n.OPTION_TYP,
        "ClsPric": n.CLOSE, "SttlmPric": n.SETTLE_PR, "OpnIntrst": n.OPEN_INT, "TtlTradgVol": n.CONTRACTS}))
out = pd.concat(frames)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
out.to_csv(OUT, index=False)
print("files read:", len(frames), "| skipped:", len(bad), bad[:5])
print("rows:", len(out), "| days:", out.TradDt.nunique(), "|", out.TradDt.min().date(), "to", out.TradDt.max().date())
print("expiries per day (median):", int(out.groupby("TradDt").XpryDt.nunique().median()))
w = out[out.TradDt == out.TradDt.min()]
print(sorted(w.XpryDt.unique())[:4], w.OptnTp.unique())
