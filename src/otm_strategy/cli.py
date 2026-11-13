"""Command line: otm report [--notify] | record | close | list | notify-test.  Places no orders."""
import argparse
import json
import logging
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import positions
from .config import Settings
from .data import DataError, load_market
from .notify import Notifier
from .report import build_report
from .storage import make_store

log = logging.getLogger("otm")
IST = ZoneInfo("Asia/Kolkata")


def detect_phase(now=None):
    """Morning runs (before noon IST) are the entry run, later runs are the 3:20 PM exit run."""
    now = now or datetime.now(IST)
    return "entry" if now.hour < 12 else "exit"


def select_events(report, phase, cfg):
    """Which Telegram messages to send: exit alerts always; the entry ticket on the entry run; a summary on the exit run."""
    out = []
    for e in report.events:
        if e.kind == "exit":
            out.append(e)
        elif e.kind == "entry" and phase == "entry":
            out.append(e)
        elif e.kind == "summary" and phase == "exit" and cfg.notify_daily_summary and report.live_today:
            out.append(e)
    return out


def _notifier_or_warn():
    n = Notifier.from_env()
    if n is None:
        log.warning("Telegram is not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID or SSM); no messages sent")
    return n


def cmd_report(args, cfg, store):
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    phase = detect_phase() if args.phase == "auto" else args.phase
    notifier = _notifier_or_warn() if args.notify else None
    try:
        nifty, vix, notes = load_market(store)
        rep = build_report(today, cfg, nifty, vix, positions.load(store), entry_day=args.entry_day,
                           spot=args.spot, expiry=args.expiry, notes=notes)
    except Exception as e:
        log.error("report failed: %s: %s", type(e).__name__, str(e)[:300])
        if notifier:
            notifier.send(f"NIFTY OTM - ERROR {today}\nThe {phase} run failed: {type(e).__name__}: {str(e)[:300]}\nNo signal was produced. Check the instance logs.", urgent=True)
        return 1
    print(rep.text)
    key = f"reports/signal_{today}_{datetime.now().strftime('%H%M')}.txt"
    try:
        store.write_text(key, rep.text + "\n")
        print(f"\n(saved to {store.describe(key)})")
    except Exception as e:
        log.warning("could not save the report (%s)", type(e).__name__)
    if notifier:
        for event in select_events(rep, phase, cfg):
            ok = notifier.send(event.text, urgent=event.urgent)
            log.info("telegram %s message %s", event.kind, "sent" if ok else "FAILED")
    return 0


def cmd_record(args, cfg, store):
    pid = positions.record(store, args.side, args.short, args.hedge, args.expiry, args.lots, args.entry_date)
    print(f"recorded position #{pid}")
    return 0


def cmd_close(args, cfg, store):
    left = positions.close(store, args.id)
    print(f"closed position #{args.id}; {left} open")
    return 0


def cmd_list(args, cfg, store):
    rows = positions.load(store)
    print(json.dumps(rows, indent=2) if rows else "no positions recorded")
    return 0


def cmd_notify_test(args, cfg, store):
    n = Notifier.from_env()
    if n is None:
        print("Telegram is not configured: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, or OTM_SSM_PREFIX for SSM.")
        return 2
    ok = n.send("NIFTY OTM - Telegram test OK. The signal app can reach you.", urgent=True)
    print("test message sent" if ok else "test message FAILED (see the log lines above)")
    return 0 if ok else 1


def build_parser():
    ap = argparse.ArgumentParser(prog="otm", description=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("report", help="daily report: entry ticket on entry days, exit checks for recorded positions")
    r.add_argument("--entry-day", choices=["auto", "yes", "no"], default="auto", help="override entry-day detection (holiday weeks)")
    r.add_argument("--spot", type=float, help="live Nifty price to compute strikes from (default: prior close)")
    r.add_argument("--expiry", help="contract expiry YYYY-MM-DD (default: next weekly expiry day)")
    r.add_argument("--today", help="YYYY-MM-DD, for testing")
    r.add_argument("--notify", action="store_true", help="send Telegram messages")
    r.add_argument("--phase", choices=["auto", "entry", "exit"], default="auto", help="which run this is (auto: before noon IST = entry)")
    rec = sub.add_parser("record", help="record a position you traded")
    rec.add_argument("--side", choices=["PE", "CE"], required=True)
    rec.add_argument("--short", type=int, required=True)
    rec.add_argument("--hedge", type=int, required=True)
    rec.add_argument("--expiry", required=True)
    rec.add_argument("--lots", type=int, default=Settings.from_env().lots)
    rec.add_argument("--entry-date")
    c = sub.add_parser("close", help="remove a closed or expired position")
    c.add_argument("--id", type=int, required=True)
    sub.add_parser("list", help="show recorded positions")
    sub.add_parser("notify-test", help="send a test Telegram message")
    return ap


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    args = build_parser().parse_args(argv)
    if args.cmd is None:
        args = build_parser().parse_args(["report"] + (argv or []))
    cfg, store = Settings.from_env(), make_store()
    handler = {"report": cmd_report, "record": cmd_record, "close": cmd_close, "list": cmd_list,
               "notify-test": cmd_notify_test}[args.cmd]
    return handler(args, cfg, store)


if __name__ == "__main__":
    sys.exit(main())
