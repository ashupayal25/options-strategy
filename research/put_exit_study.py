import pandas as pd
import backtest as bt
import regime_full as rf
from delta_strikes import leg
UNITS, LOTS, CAP = 65, 25, 1600000
p = bt.make_parser().parse_args([]); p.confirm = 2
df = bt.build(rf.nifty, rf.vixd, p)
for slip in (0.5, 1.0):
    print(f"\n=== 15-delta puts (chain IV), 25 lots, slip {slip} ===")
    print(f"{'put exit':34s} {'legs':>4s} {'win':>5s} {'total':>10s} {'2019-22':>9s} {'2023-26':>9s} {'worst':>9s} {'maxDD':>9s} {'exit%':>6s}")
    for name, ex in (("hold to expiry (current)", "none"), ("exit on regime change", "regime"), ("exit on close <= short strike", "hard")):
        t = pd.DataFrame([r for e in rf.expiries if (r := leg(df, e, "PE", "chain", 15, 2.0, slip, "sma50", ex))])
        rs = t.pnl * UNITS * LOTS; eq = rs.cumsum()
        print(f"{name:34s} {len(t):4d} {(t.pnl>0).mean()*100:4.0f}% {rs.sum():10,.0f} {rs[t.entry<'2023-01-01'].sum():9,.0f} {rs[t.entry>='2023-01-01'].sum():9,.0f} {rs.min():9,.0f} {(eq-eq.cummax()).min():9,.0f} {(t.how!='expiry').mean()*100:5.0f}%")
