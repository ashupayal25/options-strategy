"""Telegram notifications through the Bot API (plain text). The bot token is never logged."""
import logging
import time

import requests

from .credentials import get_secret

log = logging.getLogger("otm.notify")

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LEN = 4000  # Telegram's hard limit is 4096 characters per message


def split_message(text, limit=MAX_LEN):
    """Split on line boundaries; a single over-long line is cut at the limit."""
    chunks, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current or not chunks:
        chunks.append(current)
    return chunks


class Notifier:
    def __init__(self, token, chat_id, *, session=None, retries=3, timeout=10, sleep=time.sleep):
        self._token = token
        self.chat_id = str(chat_id)
        self.session = session or requests.Session()
        self.retries = retries
        self.timeout = timeout
        self._sleep = sleep

    @classmethod
    def from_env(cls, **kwargs):
        token = get_secret("TELEGRAM_BOT_TOKEN", "telegram/bot_token")
        chat_id = get_secret("TELEGRAM_CHAT_ID", "telegram/chat_id")
        if not token or not chat_id:
            return None
        return cls(token, chat_id, **kwargs)

    def send(self, text, urgent=False):
        """Send text (split if long). Returns True only if every part was delivered. Never raises."""
        ok = True
        for chunk in split_message(text):
            ok = self._post(chunk, urgent) and ok
        return ok

    def _post(self, chunk, urgent):
        url = API_URL.format(token=self._token)
        payload = {"chat_id": self.chat_id, "text": chunk, "disable_notification": not urgent,
                   "disable_web_page_preview": True}
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.post(url, json=payload, timeout=self.timeout)
            except requests.RequestException as e:
                # str(e) of a requests error contains the URL (and so the token); log only the type
                log.warning("telegram send failed (%s), attempt %d/%d", type(e).__name__, attempt, self.retries)
            else:
                if resp.status_code == 200:
                    return True
                if resp.status_code == 429:
                    wait = _retry_after(resp)
                    log.warning("telegram rate limited, waiting %ss", wait)
                    self._sleep(wait)
                    continue
                if 400 <= resp.status_code < 500:
                    log.error("telegram rejected the message (HTTP %d): %s", resp.status_code, _description(resp))
                    return False
                log.warning("telegram HTTP %d, attempt %d/%d", resp.status_code, attempt, self.retries)
            if attempt < self.retries:
                self._sleep(2 ** attempt)
        return False


def _retry_after(resp):
    try:
        return min(int(resp.json().get("parameters", {}).get("retry_after", 2)), 30)
    except Exception:
        return 2


def _description(resp):
    try:
        return str(resp.json().get("description", ""))[:200]
    except Exception:
        return ""
