# Deploy with GitHub Actions (free) — step by step

Your repo: https://github.com/ashupayal25/options-strategy

Goal: GitHub sends you Telegram signals at **09:40** and **15:20 IST** on weekdays. No AWS.

Do the steps in order. Stop if a step fails and fix that first.

---

## Step 0 — Push this code to GitHub

On your PC, in `C:\workspace\options-strategy`:

```powershell
git add .github/workflows/otm-signal.yml state/.gitkeep deploy/github-actions.md README.md .env.example .gitignore
git status
git commit -m "Add free GitHub Actions signal runner"
git push origin main
```

Open https://github.com/ashupayal25/options-strategy and confirm you can see the folder `.github/workflows/`.

---

## Step 1 — Create a Telegram bot (if you do not have one)

1. Open Telegram and search for **@BotFather**
2. Send: `/newbot`
3. Follow the prompts (name + username)
4. BotFather replies with a **token** that looks like `123456:ABC-DEF...`
5. **Copy and save that token** (this is `TELEGRAM_BOT_TOKEN`)
6. Click the link to open **your** new bot, then send it any message (e.g. `hi`)

---

## Step 2 — Get your Telegram chat id

1. In a browser, open this URL (paste your real token in place of `TOKEN`):

   `https://api.telegram.org/botTOKEN/getUpdates`

   Example: `https://api.telegram.org/bot123456:ABC-DEF/getUpdates`

2. In the page text, find `"chat":{"id":` — the number after it is your chat id  
   Example: `"chat":{"id":987654321` → chat id is `987654321`
3. **Copy and save that number** (this is `TELEGRAM_CHAT_ID`)

If the page shows `"result":[]`, go back to your bot chat, send another message, refresh the URL.

---

## Step 3 — Put the two secrets in GitHub

1. Open: https://github.com/ashupayal25/options-strategy/settings/secrets/actions  
   (Repo → **Settings** → left sidebar **Secrets and variables** → **Actions**)
2. Click **New repository secret**
3. Name: `TELEGRAM_BOT_TOKEN`  
   Secret: paste the bot token → **Add secret**
4. Click **New repository secret** again
5. Name: `TELEGRAM_CHAT_ID`  
   Secret: paste the chat id number → **Add secret**

You should now see both names listed (values stay hidden).

---

## Step 4 — Allow Actions to save state

1. Open: https://github.com/ashupayal25/options-strategy/settings/actions  
   (Repo → **Settings** → left sidebar **Actions** → **General**)
2. Scroll to **Workflow permissions**
3. Select **Read and write permissions**
4. Click **Save**

---

## Step 5 — Run a test

1. Open: https://github.com/ashupayal25/options-strategy/actions  
   (Repo → **Actions** tab)
2. If GitHub asks to enable Actions, click **I understand my workflows, go ahead and enable them**
3. In the left list, click **OTM signal**
4. Click **Run workflow** (right side)
5. Leave branch as `main`
6. Under **Which run to execute**, choose **`notify-test`**
7. Click the green **Run workflow**
8. Wait ~1 minute, then click the new run in the list and open the **signal** job to watch the log

**Pass:** you get a Telegram message saying the test is OK.  
**Fail:** open the red step in the log — usually a wrong secret name/value.

---

## Step 6 — Optional second test

Same as Step 5, but choose phase **`exit`** (or **`entry`**).  
You should get today’s report on Telegram (even on a holiday it may say there is nothing to do).

---

## Done — automatic schedule

After Steps 0–5 work, you do not need to click anything on normal days:

| When (IST, Mon–Fri) | What |
|---|---|
| 09:40 | Entry report → Telegram |
| 15:20 | Exit report → Telegram |

GitHub can be a few minutes late. That is normal.

---

## Later: tell the bot about positions you traded

Exit alerts only work if positions are in `state/positions.json`.

On your PC:

```powershell
cd C:\workspace\options-strategy
.\.venv\Scripts\activate
$env:OTM_STORE = "state"
otm record --side PE --short 24750 --hedge 24250 --expiry 2026-11-24 --lots 2
git add state/positions.json
git commit -m "Record PE position"
git push origin main
```

To close one: `otm close --id 1` then commit and push again.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No **OTM signal** workflow | Step 0 — push was missing; refresh Actions |
| Secret errors in the log | Step 3 — names must be exact: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Cannot commit state | Step 4 — Read and write permissions + Save |
| No Telegram message | Step 1–2 — message the bot first; check chat id |
| Yahoo / data warnings | App retries then uses `state/cache/`; open the Actions log |
