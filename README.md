# OTM Nifty signal app

A signal-only app for a weekly Nifty option-selling strategy. It reads daily Nifty and India VIX bars, works out the market regime
(bullish, bearish, sideways, no trade), and tells you what to do: an entry ticket on the day after weekly expiry and exit alerts for
the positions you have recorded. Messages go to Telegram. **It places no orders and needs no broker login.**

> Not financial advice. The rules were backtested on settlement prices, not live fills. Paper trade first and compare.

## The rules (defaults)

| | Puts (bullish regime) | Calls (bearish regime) |
|---|---|---|
| Entry | day after weekly expiry, about 30 minutes after the open, decided from the prior close | same |
| Short strike | 2% below the prior close | 3% above the prior close |
| Hedge (margin relief only) | 2% beyond the short | 2% beyond the short |
| Skip rule | skip when the prior-close RSI is above 70 | none |
| Exit | hold to expiry (no stop) | exit both legs when the regime turns bullish or no-trade |

Sideways and no-trade regimes: stay out. Two daily closes confirm a regime change. Details and the evidence are in `docs/STRATEGY_SPEC.md`.

## Layout

```
src/otm_strategy/   the app (regime engine, strategy rules, report, Telegram, storage, CLI)
research/           backtests and experiments (they import the same regime engine; run them from this folder)
pine/               TradingView script (regime_system.pine) and older versions
docs/               strategy spec
tests/              pytest suite
deploy/             AWS CloudFormation, systemd timers, bootstrap/update scripts (see deploy/README.md)
data/ outputs/ reports/   local data, generated results and reports (git-ignored)
```

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"
pytest                            # 48 tests, no network needed
```

## Commands

```bash
otm report                                   # today's report (entry ticket if today is an entry day, exit checks)
otm report --notify --phase entry            # same, and send the Telegram messages for the entry run
otm report --today 2026-11-13 --entry-day yes --expiry 2026-11-24    # replay a date / force an entry day (holiday weeks)
otm report --spot 25200                      # compute strikes from a live price instead of the prior close
otm record --side PE --short 24750 --hedge 24250 --expiry 2026-11-24 --lots 2   # log a position you traded
otm list
otm close --id 1                             # remove a closed or expired position
otm notify-test                              # send a test Telegram message
```

`python -m otm_strategy ...` works too. Run the entry report at about 09:40 IST on the day after expiry and the exit report at about 15:20 IST every trading day.

## Telegram

Messages: the entry ticket (entry run), exit alerts (always, with sound), a short daily summary (3:20 PM run, skipped on market holidays),
and an error alert if a run fails. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the environment, or store them in AWS SSM
(`OTM_SSM_PREFIX`, see `deploy/README.md`). The token is never logged. Test with `otm notify-test`.

## Settings

All settings have the locked defaults and can be overridden with `OTM_*` variables. See `.env.example` (lots, lot size, strike distances,
RSI limit, confirmation closes, expiry weekday, storage location).

State: `positions.json`, saved reports and cached bars live in the local project folder by default, or in S3 when `OTM_STORE=s3://bucket/otm/`.

## Research data (not in git)

The backtests need about 1 GB of NSE option history in `data/` (git-ignored). The app itself does not need it.

```bash
python research/fetch_bhav.py       # NSE daily F&O files from July 2024 onward -> data/bhav/nifty_options.csv
# download the 2019-2024 zips into data/bhav_old/ (see docs/), then:
python research/build_old.py        # -> data/bhav/nifty_options_old.csv
python research/final_rules.py      # example backtest; results are written to outputs/
```

## Deploying

See `deploy/README.md`: one small EC2 instance with an Elastic IP, a private S3 bucket for state, secrets in SSM Parameter Store,
and two systemd timers in IST.
