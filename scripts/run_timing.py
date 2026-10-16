"""How late each scheduled run started: GitHub starts a scheduled workflow some time after its cron slot.

The publish workflow runs this as its first step on a schedule event:
    python scripts/run_timing.py "$SCHEDULE"     (SCHEDULE = github.event.schedule, the cron line that fired)
It works out the slot that fired (the latest time of that cron line at or before now, UTC), the minutes between the
slot and the actual start, and appends {slot, started_at, delay_min} to data/run-timing.json; the newest KEEP entries
are kept. The file is saved with the refreshed data and is not published.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / 'data/run-timing.json'
KEEP = 60

def _values(field, lo, hi):
    """The values of one cron field: '*', '*/n', a number or a comma list of numbers."""
    if field == '*':
        return list(range(lo, hi + 1))
    if field.startswith('*/'):
        return list(range(lo, hi + 1, int(field[2:])))
    values = sorted({int(v) for v in field.split(',')})
    if not values or values[0] < lo or values[-1] > hi:
        raise ValueError(f'cron field out of range: {field}')
    return values

def last_slot(cron, now):
    """The latest time at or before `now` at which a daily cron line ('M H * * *', UTC) fires."""
    minute, hour, *days = cron.split()
    if days != ['*', '*', '*']:
        raise ValueError(f'not a daily schedule: {cron}')
    minutes, hours = _values(minute, 0, 59), _values(hour, 0, 23)
    now = now.astimezone(timezone.utc)
    for back in (0, 1):
        day = (now - timedelta(days=back)).date()
        slots = [datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc) for h in hours for m in minutes]
        slots = [s for s in slots if s <= now]
        if slots:
            return max(slots)
    raise ValueError(f'no slot of {cron} in the last day')

def load(path=LOG):
    try:
        log = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return log if isinstance(log, list) else []

def record(cron, started, path=LOG, keep=KEEP):
    """Append this run's {slot, started_at, delay_min} to the log (the newest `keep` entries stay); return the entry."""
    started = started.astimezone(timezone.utc).replace(microsecond=0)
    slot = last_slot(cron, started)
    entry = {'slot': slot.isoformat(), 'started_at': started.isoformat(),
             'delay_min': round((started - slot).total_seconds() / 60, 1)}
    log = (load(path) + [entry])[-keep:]
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(log, indent=2) + '\n', encoding='utf-8', newline='\n')
    temp.replace(path)
    return entry

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cron = (argv[0] if argv else os.environ.get('SCHEDULE', '')).strip()
    if not cron:
        print('Not a scheduled run: no start delay to record.')
        return 0
    entry = record(cron, datetime.now(timezone.utc))
    print(f"Scheduled slot {entry['slot']} started {entry['delay_min']:g} min late.")
    return 0

if __name__ == '__main__':
    sys.exit(main())
