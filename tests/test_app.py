from datetime import date

import pytest

from otm_strategy import cli, positions
from otm_strategy.config import Settings
from otm_strategy.data import DataError, load_market
from otm_strategy.report import Event, Report, build_report
from otm_strategy.storage import LocalStore
from otm_strategy.strategy import _bs_put
from conftest import FakeNotifier, make_frames

TODAY = date(2026, 11, 16)  # the business day after the last synthetic bar (13 Nov)


def test_bullish_with_high_rsi_skips_the_put(uptrend):
    rep = build_report(TODAY, Settings(rsi_skip=1.0), *uptrend, [], entry_day="yes")
    assert "SKIP the put trade" in rep.text and "PUT spread" not in rep.text
    assert [e.kind for e in rep.events] == ["entry", "summary"]


def test_bullish_without_rsi_skip_gives_a_put_ticket(uptrend):
    rep = build_report(TODAY, Settings(rsi_skip=200.0), *uptrend, [], entry_day="yes", expiry="2026-11-24")
    assert "PUT spread (bull put), 2 lots x 65 = 130 units" in rep.text
    assert "1) BUY  130" in rep.text and "2) SELL 130" in rep.text and rep.text.index("1) BUY") < rep.text.index("2) SELL")
    assert "HOLD TO EXPIRY" in rep.text and "otm record --side PE" in rep.text and "fixed 2% fallback" in rep.text


def test_put_ticket_uses_the_chain_delta_when_given(uptrend):
    spot = float(uptrend[0].Close.iloc[-1])
    chain = {k: _bs_put(spot, k, 8 / 365, 0.14) for k in range(int(spot * 0.9) // 50 * 50, int(spot), 50)}
    rep = build_report(TODAY, Settings(rsi_skip=200.0), *uptrend, [], entry_day="yes", expiry="2026-11-24", put_chain=chain)
    assert "Put short chosen from the option chain: delta" in rep.text and "fallback" not in rep.text


def test_put_ticket_fetches_the_chain_and_uses_its_spot(uptrend):
    spot = float(uptrend[0].Close.iloc[-1]) * 1.01
    chain = {k: _bs_put(spot, k, 8 / 365, 0.14) for k in range(int(spot * 0.9) // 50 * 50, int(spot), 50)}
    rep = build_report(TODAY, Settings(rsi_skip=200.0), *uptrend, [], entry_day="yes", expiry="2026-11-24", chain_fetcher=lambda exp: (chain, spot, exp))
    assert f"live spot {spot:,.1f} from the NSE option chain" in rep.text and "chosen from the option chain" in rep.text


def test_put_ticket_follows_a_holiday_shifted_expiry(uptrend):
    spot = float(uptrend[0].Close.iloc[-1])
    chain = {k: _bs_put(spot, k, 8 / 365, 0.14) for k in range(int(spot * 0.9) // 50 * 50, int(spot), 50)}
    rep = build_report(TODAY, Settings(rsi_skip=200.0), *uptrend, [], entry_day="yes", expiry="2026-11-24", chain_fetcher=lambda exp: (chain, spot, date(2026, 11, 23)))
    assert "NSE lists the weekly expiry as 2026-11-23" in rep.text and "NIFTY26N23" in rep.text


def test_put_ticket_falls_back_with_the_reason_when_the_fetch_fails(uptrend):
    from otm_strategy.chain import ChainError

    def broken(exp):
        raise ChainError("NSE option chain unavailable (HTTPError)")
    rep = build_report(TODAY, Settings(rsi_skip=200.0), *uptrend, [], entry_day="yes", expiry="2026-11-24", chain_fetcher=broken)
    assert "fixed 2% fallback" in rep.text and "NSE option chain unavailable (HTTPError)" in rep.text


def test_bearish_gives_a_call_ticket(downtrend):
    rep = build_report(TODAY, Settings(), *downtrend, [], entry_day="yes", expiry="2026-11-24")
    assert "CALL spread (bear call)" in rep.text and "exit BOTH legs if Nifty closes above its SMA50" in rep.text


def test_not_an_entry_day_has_no_ticket(uptrend):
    rep = build_report(TODAY, Settings(), *uptrend, [], entry_day="no")
    assert "ENTRY TODAY? == no" in rep.text and all(e.kind != "entry" for e in rep.events)


def test_call_exit_alert_after_regime_flip():
    nifty, vix = make_frames(segments=[(330, -0.002), (60, 0.004)])
    entered = nifty.index[-65].date().isoformat()  # entered while the downtrend was still running
    pos = [dict(id=1, side="CE", short=9000, hedge=9500, expiry="2026-11-24", lots=2, entry_date=entered)]
    rep = build_report(TODAY, Settings(), nifty, vix, pos, entry_day="no")
    assert "EXIT NOW" in rep.text
    exits = [e for e in rep.events if e.kind == "exit"]
    assert len(exits) == 1 and exits[0].urgent and "BUY BACK 130" in exits[0].text


def test_puts_never_trigger_an_exit(uptrend):
    pos = [dict(id=2, side="PE", short=9000, hedge=8500, expiry="2026-11-24", lots=2, entry_date="2026-10-01")]
    rep = build_report(TODAY, Settings(), *uptrend, pos, entry_day="no")
    assert "HOLD (puts are held to expiry" in rep.text and all(e.kind != "exit" for e in rep.events)


def test_expired_position_is_flagged(uptrend):
    pos = [dict(id=3, side="PE", short=9000, hedge=8500, expiry="2026-11-10", lots=2, entry_date="2026-11-03")]
    rep = build_report(TODAY, Settings(), *uptrend, pos, entry_day="no")
    assert "EXPIRED" in rep.text and "otm close --id 3" in rep.text


def test_message_selection_policy():
    rep = Report("x", [Event("entry", "e"), Event("exit", "x", True), Event("summary", "s")], live_today=True)
    cfg = Settings()
    assert [e.kind for e in cli.select_events(rep, "entry", cfg)] == ["entry", "exit"]
    assert [e.kind for e in cli.select_events(rep, "exit", cfg)] == ["exit", "summary"]
    assert [e.kind for e in cli.select_events(rep, "exit", Settings(notify_daily_summary=False))] == ["exit"]
    holiday = Report("x", rep.events, live_today=False)
    assert [e.kind for e in cli.select_events(holiday, "exit", cfg)] == ["exit"]


def test_phase_detection():
    from datetime import datetime
    ist = cli.IST
    assert cli.detect_phase(datetime(2026, 11, 18, 9, 40, tzinfo=ist)) == "entry"
    assert cli.detect_phase(datetime(2026, 11, 18, 15, 20, tzinfo=ist)) == "exit"


@pytest.fixture
def app(monkeypatch, tmp_path, uptrend):
    monkeypatch.setenv("OTM_STORE", str(tmp_path))
    monkeypatch.setenv("OTM_RSI_SKIP", "200")
    fake = FakeNotifier()
    monkeypatch.setattr(cli.Notifier, "from_env", classmethod(lambda cls, **kw: fake))
    monkeypatch.setattr(cli, "load_market", lambda store: (*uptrend, []))
    return fake, tmp_path


def test_report_command_sends_entry_ticket_and_saves(app, capsys):
    fake, tmp = app
    assert cli.main(["report", "--today", "2026-11-16", "--entry-day", "yes", "--notify", "--phase", "entry"]) == 0
    assert len(fake.sent) == 1 and "ENTRY DAY 2026-11-16" in fake.sent[0][0] and "PUT spread" in fake.sent[0][0]
    assert list((tmp / "reports").glob("signal_2026-11-16_*.txt"))
    assert "SIGNAL REPORT" in capsys.readouterr().out


def test_report_without_notify_sends_nothing(app):
    fake, _ = app
    assert cli.main(["report", "--today", "2026-11-16", "--entry-day", "yes"]) == 0
    assert fake.sent == []


def test_exit_run_sends_summary(app):
    fake, _ = app
    assert cli.main(["report", "--today", "2026-11-13", "--notify", "--phase", "exit"]) == 0
    assert len(fake.sent) == 1 and "daily check 2026-11-13" in fake.sent[0][0]


def test_failure_sends_an_error_alert_and_returns_1(app, monkeypatch):
    fake, _ = app

    def boom(store):
        raise DataError("could not fetch ^NSEI: ConnectionError")

    monkeypatch.setattr(cli, "load_market", boom)
    assert cli.main(["report", "--today", "2026-11-16", "--notify", "--phase", "entry"]) == 1
    assert len(fake.sent) == 1 and fake.sent[0][1] is True and "ERROR 2026-11-16" in fake.sent[0][0]


def test_record_list_close_commands(app, capsys):
    cli.main(["record", "--side", "PE", "--short", "24750", "--hedge", "24250", "--expiry", "2026-11-24", "--entry-date", "2026-11-18"])
    cli.main(["list"])
    assert "24750" in capsys.readouterr().out
    cli.main(["close", "--id", "1"])
    cli.main(["list"])
    assert "no positions recorded" in capsys.readouterr().out


def test_market_data_falls_back_to_cache_with_a_warning(tmp_path, uptrend):
    store = LocalStore(tmp_path)
    nifty, vix = uptrend
    ok = load_market(store, fetcher=lambda sym: nifty if sym == "^NSEI" else vix)
    assert ok[2] == []

    def failing(sym):
        raise DataError("blocked")

    n2, v2, notes = load_market(store, fetcher=failing)
    assert len(n2) == len(nifty) and len(notes) == 2 and "DATA WARNING" in notes[0]
    with pytest.raises(DataError):
        load_market(LocalStore(tmp_path / "empty"), fetcher=failing)
