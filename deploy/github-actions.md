# Deploy with GitHub Actions (free)

Runs the signal app on GitHub’s runners — no AWS, no VPS. Two weekday schedules in IST, plus a manual “Run workflow” button for tests. Telegram gets the messages; `state/` in the repo holds positions and the Yahoo cache.

## 1. Put the repo on GitHub

If it is not there yet:

```bash
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

## 2. Add Telegram secrets

In the GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `TELEGRAM_CHAT_ID` | your chat id |

How to get the chat id: message your bot once, then open  
`https://api.telegram.org/bot<TOKEN>/getUpdates` and read `"chat":{"id": ...}`.

## 3. Allow Actions to write state (usually already on)

**Settings → Actions → General → Workflow permissions → Read and write permissions**  
(needed so the job can commit updates under `state/`).

## 4. Smoke test

1. **Actions → OTM signal → Run workflow**
2. Choose phase **`notify-test`** → Run
3. You should get a Telegram message within about a minute

Then try **`entry`** or **`exit`** the same way. Check the job log if anything fails.

## 5. What runs automatically

| IST (Mon–Fri) | Phase | Cron (UTC) |
|---|---|---|
| 09:40 | entry | `10 4 * * 1-5` |
| 15:20 | exit | `50 9 * * 1-5` |

India has no DST, so these stay aligned year-round. Scheduled workflows can be a few minutes late; that is normal for GitHub.

## 6. Recording positions

The exit run only knows positions in `state/positions.json`.

**From your laptop** (with the repo checked out and Telegram secrets in the environment if you also want notify):

```bash
pip install -e .
set OTM_STORE=state          # Windows PowerShell: $env:OTM_STORE="state"
otm record --side PE --short 24750 --hedge 24250 --expiry 2026-11-24 --lots 2
otm list
otm close --id 1
git add state/positions.json
git commit -m "record position"
git push
```

Or edit `state/positions.json` by hand and push. After each Actions run, cache/report files under `state/` may be auto-committed by the workflow.

## 7. Changing lots / settings

Defaults live in `src/otm_strategy/config.py`. To override in Actions, add `env:` keys under the “Run report” step in `.github/workflows/otm-signal.yml` (for example `OTM_LOTS: "3"`), commit, and push.

## 8. Things to know

- **Yahoo from cloud IPs:** same risk as AWS. The app retries, then falls back to `state/cache/`. If fetches fail often, we can switch data source later.
- **Holidays:** the app skips empty exit summaries when the market is closed; still verify entry weeks around NSE holidays.
- **Private repo:** Actions minutes are free within GitHub’s private-repo quota; two short jobs a day is negligible.
- **AWS path:** still documented in `deploy/README.md` if you want an Elastic IP later for broker APIs.
