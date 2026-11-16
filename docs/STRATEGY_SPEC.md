# OTM Option Selling Strategy - Spec v4 (DRAFT)

Status: working draft. Regime logic validated on real NSE Nifty option settlement prices from 11 Feb 2019 to 13 Nov 2026. Strike selection is now **% OTM from spot** (not a fixed rupee premium). Re-run `research/regime_full.py` after any rule change. Not financial advice, not a promise of returns.

Supersedes v1–v3. Removed since v1: price-based stops (tight spot % / credit multiples), VIX premium filter, RSI/Bollinger pullback entries, monthly stock selling, Black-Scholes pricing, fixed ₹10/₹16 short premium targeting.

## 1. Scope

| Item | Value |
|---|---|
| Instrument | Nifty index options, weekly expiry (use the NSE index `NSE:NIFTY`, not GIFT Nifty futures) |
| Signal timeframe | Daily candle, checked at about 3:20 PM |
| Style | Sell far-OTM options only (no ATM/ITM) |
| Short strikes | **Puts ≈ 4% OTM; Calls ≥ 3% OTM** from spot (rounded to strike step 50) |
| Hedge | Further OTM long leg (~2% beyond the short) for margin relief only. It does not cap a crash. Regime exit + hard kill are the protection. |
| Capital | Rs 16L |

## 2. Regime (daily, Nifty)

Indicators: ADX(14), SMA 20/50/200, Bollinger Bands (20, 2) and width percentile (126 bars).

| Regime | Conditions |
|---|---|
| Bullish | Close > SMA50 and > SMA200, SMA50 5-day slope > 0, ADX > 20 |
| Bearish | Close < SMA50 and < SMA200, SMA50 5-day slope < 0, ADX > 20 |
| Sideways | ADX < 20, within 3% of SMA50, abs(SMA50 slope) <= 0.7%, BB width percentile <= 70 |
| No trade | Anything else, or BB width percentile < 5 (squeeze) |

A new regime counts only after N consecutive daily closes (`confirmBars`, default 2).

SMA vs EMA (50/200): tested under v3; SMA is as good or better. Keep SMA.

## 3. Entry

- One entry per weekly cycle, on the day after the weekly expiry (default Wednesday for the current Tuesday expiry; verify on NSE).
- Bullish: sell the put side. Bearish: sell the call side.
- **Sideways: stay out by default** (`sellSideways = false`). Optional both-sides only if explicitly enabled.
- No trade: nothing.
- Entry is based on the regime at the entry day's close. No RSI, Bollinger, or VIX filters.

**Known mismatch (entry timing).** The backtests in `research/regime_full.py` and the earlier research scripts enter on the first trading day with 5-9 calendar days to expiry. In practice that is 8-9 days before expiry (for example the Tuesday before a Thursday expiry, or the Monday before a Tuesday expiry), one week earlier than "the day after expiry" described above and used as the default in `regime_system.pine`. Results depend heavily on this choice:
- Premium strategy (sell about Rs 16 / hedge about Rs 3, regime exit), total per lot, 0.5 pt slippage: entry 8-9 days out +59,366 (2 closes, sideways sold); entry the day after expiry -14,857 (same settings), or +22,538 for 1 close, directional only.
- 1% OTM put / 2% hedge, hold to expiry, per lot, 0.5 pt slippage: entry 8-9 days out +66,579 (second half 2023-26 only +2,506); the day after expiry +46,485 (second half -8,700); the day before expiry +31,388 (both halves positive, worst leg -10,345).
Decide one entry timing, make the backtest and the Pine script match, and re-run before relying on any number in this spec.

**Loser-reduction tests (puts only, 1% OTM / 2% hedge, hold to expiry, day-after-expiry entry, per lot, 0.5 pt slippage; also checked with 1 close):**
- Skip entries when RSI > 70: +67,223 (vs +46,485), worst leg -16,452 (vs -34,128). The benefit did not carry over to the 8-9 day entry (+41,236 vs +66,579), so treat it as fragile.
- Short strike 2% instead of 1% with the RSI skip: win rate 96%, +44,876, worst leg and drawdown -13,172, both halves positive.
- Enter the day before expiry: win rate 96%, +31,388, worst leg and drawdown -10,345, but only about 8 points of credit, so it is sensitive to slippage.
- Did not help: VIX filters, ADX filter, distance above SMA20 filter, volatility-adaptive strikes, exiting on any move away from bullish, exiting on regime change (it cut profit).
- About 15 variants were tried, so any single winner may be luck. Confirm on a walk-forward split.

**Point-1 rules, tested as traded (`final_rules.py`):** entry the day after expiry (about 30 minutes after the open), decided from the PRIOR close regime and RSI, strikes from the prior close, entry priced at that day's settlement (a stand-in, no intraday data). Puts only, short 2% OTM, hedge 2% beyond the short, skip puts when prior-close RSI > 70. Per lot (65 units), 0.5 / 1.0 pt slippage, 2019-02 to 2026-11:
- Hold to expiry, 2 closes: 90 legs, 94% win, +51,945 / +46,095, worst leg -16,507, max drawdown -20,036, both halves positive. 1 close: +56,986 / +51,656.
- Regime exit: +17,501 / +10,416 (2 closes), +31,132 / +25,152 (1 close). Regime exit plus hard kill (close beyond the short strike): +19,159 (worst leg -11,180, drawdown -31,440). For the put side both exits cost more profit than they saved.
- Without the RSI skip the profit is about the same (+51,652) but the worst leg is -25,444.
- Puts 4% OTM (earlier setting): credit only about 6-7 points, win rate 49-56% at 1 pt slippage, total +12-18k. Too far out.
- Calls 3% OTM in a bearish regime: -51,243 / -55,078 (2 closes, hold); with 1 close and regime exit +24,576, but -38,038 with the hard kill. Unstable, treat as unproven.
- At 10 lots (hold, 2 closes, 0.5 pt): about +5.2L over 7.8 years (4.2% a year), worst leg about 1.65L (10%), drawdown about 2.0L (12.5%). At 22 lots: about +11.4L (9.2% a year), worst leg 3.6L (23%), drawdown 4.4L (28%).

**Decisions locked for the signal-only app (`otm`, package `src/otm_strategy`):** puts 2% OTM, hedge 2% beyond, skip puts when prior-close RSI > 70, hold puts to expiry (no stop); calls included at 3% OTM, hedge 2% beyond, exit calls on regime change (to bullish or no-trade); 2 closes to confirm a regime; sideways stays out; 2 lots at 65 units; signals from Yahoo (^NSEI, ^INDIAVIX); output to the console, Telegram and `reports/signal_<date>_<time>.txt` (S3 when deployed). The app places no orders. Run at about 9:40 AM on the day after expiry (entry ticket) and about 3:20 PM daily (exit check); record fills with `record`, remove with `close`. `regime_system.pine` defaults now match these decisions: puts hold to expiry (regime exit off), calls exit on regime change, hard kill off, call block off, sideways off, strikes from the prior close with the hedge 2% beyond the short. Open items: walk-forward test of these choices, paper trading, then broker automation.

**Update (delta puts, SMA50 call exit).** Backtested at 25 lots (1,625 units), Rs 16L, 0.5 pt slippage, 2019-02 to 2026-11 (`research/delta_strikes.py`, `delta_25lots.py`, `call_exit_study.py`):
- Puts: short strike = the put with delta closest to 15 without exceeding it, from implied vols on the option chain (Black-Scholes, r = 6.5%), hedge 2% beyond. Per lot over 90 legs it beat fixed 2% on worst leg and drawdown, and both halves were positive. A flat-VIX delta estimate did not reproduce this, so the app fetches the NSE option chain at the entry run (or reads `--chain`) and falls back to fixed 2% if that fails.
- Calls: 15-delta calls lost money (-3.2L at 25 lots) and fixed 3% did better. Keep calls at 3% OTM.
- Call exit: close above SMA50 only. It beat the regime exit and every faster exit tried (SMA20, rally %, distance to short). Adding the regime/no-trade exit on top cost about 14k per lot.
- 25 lots, 15-delta puts + fixed 3% calls + SMA50 exit: +21.1L (17.4% a year), worst leg -3.0L (19%), max drawdown -4.4L (28%). 59 call legs and about 17 exit variants were tried, so confirm on a walk-forward split. Margin is not modelled.

## 4. Strike and hedge selection

- **Put short:** floor(spot × (1 − 4%)) to the nearest listed strike step (50). Must be below spot.
- **Call short:** ceil(spot × (1 + 3%)) to the nearest listed strike step (50). Must be above spot (≥ 3% OTM).
- **Hedge:** ~2% further OTM beyond the short (put lower / call higher), bought only to reduce margin. Buy hedge first, then sell the short. Use limit orders.
- Do **not** target a fixed rupee premium (₹5 / ₹10 / ₹16). Premium is whatever the chain pays at that distance.

## 5. Exit

Primary: regime change (check daily candle ~3:20 PM).

- Put legs: exit when the regime turns bearish or no-trade.
- Call legs: exit when Nifty closes above its SMA50 (see the update in section 3).
- If the regime stays the same and spot has not breached the short, hold to expiry.
- Close the short and its hedge together.

**Hard kill (catastrophic circuit breaker):** if spot **closes at or beyond the short strike** (put: close ≤ short; call: close ≥ short), flatten that side immediately — even if the regime has not flipped. This is not a tight profit/loss stop; it is survival when the short is ITM.

## 6. Call block (advisory only — OFF by default)

- Pine option: after a rally of X% over N bars (default 8% over 10 bars), flag “do not sell new calls”.
- On the v3 premium-based sample it reduced profit and did not remove the worst losses. **Defaults: `blockOn = false`, `exitOnBlock = false`.** Keep as an advisory flag only.

## 7. Evidence notes

### v3 (premium ≈ ₹16 short / ₹3 hedge) — historical reference only

Real prices, 2019-02-11 to 2026-11-13, regime-change exit only (no hard kill, sideways often ON). Useful for regime behaviour, not for current strike PnL.

| Confirmation | Sideways sold? | Legs | Total (0.5 / 1.0 pt) | Worst leg | Max drawdown (0.5 pt) |
|---|---|---|---|---|---|
| 2 closes | yes | 335 | 59,366 / 32,331 | -14,231 | -18,548 |
| 2 closes | no | 172 | 30,515 / 17,245 | -14,231 | -17,953 |
| 1 close | no | 180 | 55,710 / 41,570 | -7,868 | -8,586 |

March 2020 survived under that strike rule because far-OTM premiums widened with VIX and the regime flipped early. A one-day crash from a bullish regime was never covered.

### v4 (% OTM) — re-run required

Strike rule, sideways default OFF, and hard kill change expectancy. **Authoritative numbers come from `python research/regime_full.py`**, which writes `outputs/full_trades_pct_otm.csv`. Do not size live capital off the v3 ₹16 table.

Other v3 findings still relevant: ₹5 premium selling lost money; tight spot-% / premium-multiple stops reduced profits; Black-Scholes credits were too high vs real prices; EMA flipped more often than SMA without better results.

## 8. Realistic expectation and sizing

- Treat this as a **risk-managed premium harvest**, not a 1.5%/month income product.
- Size by what you can survive if a hard kill or regime exit fails (width × lot), not by margin alone. Check the broker margin calculator.
- Start **1–2 lots** on Rs 16L until live fills and slippage are known.
- All figures are before brokerage, STT, GST, exchange charges and tax (F&O profit is business income).

## 9. Known limits and open items

- Lot sizes in the 2019-mid-2024 files are assumed (75 → 50 → 25). Real lot sizes from July 2024 onward.
- Old files have no underlying price; Nifty daily close is used for spot.
- The 3:20 PM regime reading is provisional; the backtest uses the settlement price on the signal day.
- 1 vs 2 confirmation closes still open; prefer 2 for live until walk-forward says otherwise.
- A danger filter (VIX jumps, gaps, event weeks) is not built. Candidate for the next test.
- Stocks: not tested. Weekly entry marker does not apply to stock monthlies.
- Far-OTM liquidity and spreads: verify fills before scaling.
- Paper trade first.

## 10. TradingView script (`regime_system.pine`)

- Regime and weekly entry-day action on the daily chart. Background: green bullish, red bearish, cyan sideways, grey no trade.
- Markers: up = sell puts, down = sell calls, diamond = both (only if sideways ON), white X = regime exit, yellow X = hard kill, orange flag = call block (if enabled).
- Table: regime, action (from the prior close), status/exits, MTF context, indicators, **PE/CE short + hedge guides at 2% / 3% OTM**, call-block state.
- Defaults (match the app): put 2% OTM with the RSI > 70 skip, call 3% OTM, hedge 2% beyond the short, puts hold to expiry (regime exit off), calls exit on regime change, hard kill OFF, `sellSideways = false`, call block OFF.
- Use `NSE:NIFTY` on the 1D chart.

## 11. Files (repo root)

| Path | Purpose |
|---|---|
| `src/otm_strategy/` | The app: regime engine, strategy rules, report, Telegram (`notify.py`), storage (local/S3), CLI (`otm`) |
| `tests/` | pytest suite (`pytest`) |
| `pine/regime_system.pine` | Current TradingView script (older versions in `pine/archive/`) |
| `docs/STRATEGY_SPEC.md` | This document |
| `research/regime_full.py` | Full-period real-price backtest (% OTM, hard kill, sideways on/off) |
| `research/final_rules.py`, `reduce_losers.py`, `pct_strikes.py`, `premium_strategy.py` | Rule studies built on `regime_full` |
| `research/backtest.py` | Black-Scholes sweep and data loaders (regime engine now lives in `src/otm_strategy/regime.py`) |
| `research/fetch_bhav.py`, `build_old.py` | Download July 2024 onward / convert the 2019-2024 zips into `data/bhav/*.csv` |
| `research/regime_sl.py`, `hedge_10_2.py`, `sell5.py`, `directional_*.py`, `real_backtest.py`, `exits.py`, `last_years.py`, `hedged_lots.py` | Earlier experiments (premium / Black-Scholes era) |
| `deploy/` | AWS CloudFormation, systemd timers (IST), bootstrap/update scripts, `README.md` |
| `data/`, `outputs/`, `reports/` | Local data, generated results, saved reports (git-ignored) |

## 12. Next steps

1. Paste the latest Pine script on `NSE:NIFTY` 1D; confirm put ~4% / call ~3% guides and yellow hard-kill markers.
2. Run `python research/regime_full.py` and size from `outputs/full_trades_pct_otm.csv`, not from v3 ₹16 totals.
3. Walk-forward on confirm 1 vs 2.
4. Test a danger filter (VIX jump, gap, event weeks).
5. Paper trade 2–3 months at 1–2 lots; record real fills and slippage.
6. Scale only as far as the worst-case width allows.
