import logging

import requests

from otm_strategy.credentials import get_secret
from otm_strategy.notify import MAX_LEN, Notifier, split_message

TOKEN = "123456:SECRET-TOKEN-VALUE"


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def make(session, **kw):
    return Notifier(TOKEN, 999, session=session, sleep=lambda s: None, **kw)


def test_split_short_text_is_one_chunk():
    assert split_message("hello\nworld") == ["hello\nworld"]


def test_split_long_text_respects_limit_and_keeps_every_line():
    lines = [f"line {i} " + "x" * 90 for i in range(200)]
    chunks = split_message("\n".join(lines))
    assert all(len(c) <= MAX_LEN for c in chunks) and len(chunks) > 1
    assert "\n".join(chunks).split("\n") == lines


def test_split_single_overlong_line():
    chunks = split_message("a" * (MAX_LEN * 2 + 5))
    assert [len(c) for c in chunks] == [MAX_LEN, MAX_LEN, 5]


def test_send_success_payload():
    s = FakeSession(Resp(200))
    assert make(s).send("hi") is True
    url, payload = s.calls[0]
    assert url.endswith("/sendMessage") and payload["chat_id"] == "999" and payload["text"] == "hi"
    assert payload["disable_notification"] is True and "parse_mode" not in payload


def test_urgent_messages_notify_with_sound():
    s = FakeSession(Resp(200))
    make(s).send("alert", urgent=True)
    assert s.calls[0][1]["disable_notification"] is False


def test_retries_on_server_error_then_succeeds():
    s = FakeSession(Resp(500), Resp(502), Resp(200))
    assert make(s).send("hi") is True and len(s.calls) == 3


def test_gives_up_after_retries():
    s = FakeSession(Resp(500), Resp(500), Resp(500))
    assert make(s).send("hi") is False and len(s.calls) == 3


def test_client_errors_are_not_retried():
    s = FakeSession(Resp(400, {"description": "chat not found"}))
    assert make(s).send("hi") is False and len(s.calls) == 1


def test_rate_limit_waits_and_retries():
    waited = []
    s = FakeSession(Resp(429, {"parameters": {"retry_after": 3}}), Resp(200))
    n = Notifier(TOKEN, 1, session=s, sleep=waited.append)
    assert n.send("hi") is True and waited == [3]


def test_network_error_never_raises_and_token_never_logged(caplog):
    err = requests.ConnectionError(f"HTTPSConnectionPool: Max retries exceeded with url: /bot{TOKEN}/sendMessage")
    s = FakeSession(err, err, err)
    with caplog.at_level(logging.DEBUG):
        assert make(s).send("hi") is False
    assert TOKEN not in caplog.text and "SECRET-TOKEN" not in caplog.text


def test_from_env_requires_both_values(monkeypatch):
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "OTM_SSM_PREFIX"):
        monkeypatch.delenv(k, raising=False)
    assert Notifier.from_env() is None
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    assert Notifier.from_env() is None
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    assert Notifier.from_env() is not None


def test_secret_comes_from_env_before_ssm():
    class Boom:
        def get_parameter(self, **kw):
            raise AssertionError("SSM must not be called when the env var is set")

    assert get_secret("X", "a/b", env={"X": " val "}, ssm_client=Boom()) == "val"


def test_secret_falls_back_to_ssm_when_prefix_is_set():
    class Ssm:
        def get_parameter(self, Name, WithDecryption):
            assert Name == "/otm-strategy/telegram/bot_token" and WithDecryption is True
            return {"Parameter": {"Value": "from-ssm"}}

    env = {"OTM_SSM_PREFIX": "/otm-strategy/"}
    assert get_secret("TELEGRAM_BOT_TOKEN", "telegram/bot_token", env=env, ssm_client=Ssm()) == "from-ssm"
    assert get_secret("TELEGRAM_BOT_TOKEN", "telegram/bot_token", env={}, ssm_client=Ssm()) is None


def test_ssm_failure_returns_none_without_raising():
    class Ssm:
        def get_parameter(self, **kw):
            raise RuntimeError("AccessDenied")

    assert get_secret("X", "a", env={"OTM_SSM_PREFIX": "/p"}, ssm_client=Ssm()) is None
