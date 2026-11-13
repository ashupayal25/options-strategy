"""Open-position records (what you actually traded). The app never places orders; you record fills."""
import json
from datetime import date

KEY = "positions.json"


def load(store):
    text = store.read_text(KEY)
    return json.loads(text) if text else []


def save(store, rows):
    store.write_text(KEY, json.dumps(rows, indent=2))


def record(store, side, short, hedge, expiry, lots, entry_date=None):
    rows = load(store)
    pid = max([r["id"] for r in rows], default=0) + 1
    rows.append(dict(id=pid, side=side, short=short, hedge=hedge, expiry=expiry, lots=lots,
                     entry_date=entry_date or date.today().isoformat()))
    save(store, rows)
    return pid


def close(store, pid):
    rows = [r for r in load(store) if r["id"] != pid]
    save(store, rows)
    return len(rows)
