#!/usr/bin/env python3
"""
Parses McCoy's EnTouch CSV export(s), stores them as dated snapshots in a
running state file, and bakes the accumulated history into a fresh copy of
the tracker.html template as seed data — no in-browser upload needed.

Usage:
  python3 build_report.py <csv_path> [<csv_path> ...]
  python3 build_report.py --mark '<facility>|<device>|<alertType>' '<note>' [--no-dispatch]
"""
import csv, json, re, sys, os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(SCRIPT_DIR, "mccoy_state.json")
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "tracker_template.html")
OUTPUT_DIR = SCRIPT_DIR

def norm(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()

def parse_alert_date(s):
    m = re.match(r'^(\d{2})-(\d{2})-(\d{4})\s+(\d{1,2}):(\d{2})\s*([ap]m)$', (s or '').strip(), re.I)
    if not m:
        return None
    mo, da, yr, hh, mi, ap = m.groups()
    hh = int(hh); mi = int(mi)
    if ap.lower() == 'pm' and hh != 12:
        hh += 12
    if ap.lower() == 'am' and hh == 12:
        hh = 0
    return datetime(int(yr), int(mo), int(da), hh, mi)

def date_key(dt):
    return dt.strftime("%Y-%m-%d")

def parse_csv(path):
    alerts = []
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a = {
                "facility": norm(row.get("Facility Name")),
                "device": norm(row.get("Device Name")),
                "alertType": norm(row.get("Alert Type")),
                "description": norm(row.get("Alert Description")),
                "dateStr": norm(row.get("Alert Assertion Date/Time")),
            }
            if a["facility"] and a["device"]:
                alerts.append(a)
    return alerts

def guess_report_date(alerts):
    max_dt = None
    for a in alerts:
        d = parse_alert_date(a["dateStr"])
        if d and (max_dt is None or d > max_dt):
            max_dt = d
    return date_key(max_dt) if max_dt else date_key(datetime.now())

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"dates": [], "snapshots": {}, "dispatched": {}, "reportedGhost": {}, "workOrderNotes": {}}

def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)

def normalize_device_base(device):
    return re.sub(r'\s*-\s*(zone temp|supply air|external\s*\d*)\s*$', '', norm(device), flags=re.I)

def alert_key(facility, device, alert_type):
    return f"{norm(facility)}|{norm(device).lower()}|{norm(alert_type).lower()}"

def mark_work_order(state, facility, device, alert_type, note, mark_dispatched=True):
    key = alert_key(facility, device, alert_type)
    state.setdefault("workOrderNotes", {})[key] = note
    if mark_dispatched:
        state.setdefault("dispatched", {})[key] = datetime.now().isoformat()
    return key

def write_output(state):
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    seed = {
        "dates": state["dates"],
        "snapshots": state["snapshots"],
        "dispatched": state.get("dispatched", {}),
        "reportedGhost": state.get("reportedGhost", {}),
        "workOrderNotes": state.get("workOrderNotes", {}),
    }
    seed_json = json.dumps(seed).replace("<", "\\u003c")

    placeholder = '<script type="application/json" id="mccoy-seed-data"></script>'
    replacement = f'<script type="application/json" id="mccoy-seed-data">{seed_json}</script>'
    out = template.replace(placeholder, replacement, 1)
    if out == template:
        print("WARNING: seed placeholder not found/replaced — check TEMPLATE_PATH markup")

    latest = state["dates"][-1] if state["dates"] else "export"
    # index.html is what GitHub Pages serves. Set MCCOY_DATED=1 to also write a dated copy.
    out_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Wrote {out_path} (latest report date {latest})")
    if os.environ.get("MCCOY_DATED") == "1":
        dated = os.path.join(OUTPUT_DIR, f"mccoy_alert_dashboard_{latest}.html")
        with open(dated, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Wrote {dated}")

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: build_report.py <csv_path> [<csv_path> ...]")
        print("   or: build_report.py --mark '<facility>|<device>|<alertType>' '<note>' [--no-dispatch]")
        sys.exit(1)

    state = load_state()

    if args[0] == "--mark":
        raw_key, note = args[1], args[2]
        mark_dispatched = "--no-dispatch" not in args
        facility, device, alert_type = raw_key.split("|")
        key = mark_work_order(state, facility, device, alert_type, note, mark_dispatched)
        save_state(state)
        print(f"Marked {key} -> {note!r} (dispatched={mark_dispatched})")
        write_output(state)
        return

    csv_paths = args
    loaded_dates = []

    for path in csv_paths:
        alerts = parse_csv(path)
        if not alerts:
            print(f"WARNING: no alert rows found in {path}, skipping")
            continue
        report_date = guess_report_date(alerts)
        state["snapshots"][report_date] = alerts
        if report_date not in state["dates"]:
            state["dates"].append(report_date)
        loaded_dates.append((report_date, len(alerts)))

    state["dates"] = sorted(state["dates"])
    save_state(state)

    for d, n in loaded_dates:
        print(f"Loaded {n} alerts for report date {d}")
    print(f"Known report dates now: {state['dates']}")
    write_output(state)

if __name__ == "__main__":
    main()
