"""Start-delay log of scheduled runs (scripts/run_timing.py) and its workflow step."""
import json
import re
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_timing

ROOT = Path(__file__).resolve().parents[1]
CRON = '7 22,10 * * *'

def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)

class SlotTests(unittest.TestCase):
    def test_latest_slot_at_or_before_the_start(self):
        for started, slot in ((utc(2026, 10, 16, 10, 7), utc(2026, 10, 16, 10, 7)),          # on time
                              (utc(2026, 10, 16, 13, 31, 40), utc(2026, 10, 16, 10, 7)),     # 3.4 hours late
                              (utc(2026, 10, 16, 22, 6), utc(2026, 10, 16, 10, 7)),          # a minute before the next
                              (utc(2026, 10, 17, 5, 37), utc(2026, 10, 16, 22, 7)),          # past midnight UTC
                              (utc(2026, 10, 17, 10, 6, 59), utc(2026, 10, 16, 22, 7))):
            self.assertEqual(run_timing.last_slot(CRON, started), slot, started)

    def test_cron_fields(self):
        self.assertEqual(run_timing.last_slot('15 3,15 * * *', utc(2026, 10, 16, 8, 9)), utc(2026, 10, 16, 3, 15))
        self.assertEqual(run_timing.last_slot('*/30 * * * *', utc(2026, 10, 16, 8, 59)), utc(2026, 10, 16, 8, 30))
        for bad in ('7 22,10 * * 1', '7 22,10 1 * *', '61 1 * * *', '7 24 * * *', 'nonsense'):
            with self.assertRaises(ValueError, msg=bad):
                run_timing.last_slot(bad, utc(2026, 10, 16, 8, 9))

class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'run-timing.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_appends_slot_start_and_delay(self):
        entry = run_timing.record(CRON, utc(2026, 10, 16, 13, 31, 40, 123456), self.path)
        self.assertEqual(entry, {'slot': '2026-10-16T10:07:00+00:00', 'started_at': '2026-10-16T13:31:40+00:00', 'delay_min': 204.7})
        run_timing.record(CRON, utc(2026, 10, 16, 22, 19), self.path)
        log = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual([e['delay_min'] for e in log], [204.7, 12.0])
        self.assertEqual(set(log[1]), {'slot', 'started_at', 'delay_min'})

    def test_keeps_the_newest_60(self):
        self.path.write_text(json.dumps([{'slot': str(n), 'started_at': str(n), 'delay_min': n} for n in range(60)]), encoding='utf-8')
        run_timing.record(CRON, utc(2026, 10, 16, 10, 9), self.path)
        log = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(len(log), run_timing.KEEP)
        self.assertEqual(run_timing.KEEP, 60)
        self.assertEqual((log[0]['delay_min'], log[-1]['delay_min']), (1, 2.0))

    def test_a_missing_or_broken_log_starts_again(self):
        for text in (None, '{not json', '{"a": 1}'):
            if text is not None:
                self.path.write_text(text, encoding='utf-8')
            run_timing.record(CRON, utc(2026, 10, 16, 10, 9), self.path)
            self.assertEqual(len(json.loads(self.path.read_text(encoding='utf-8'))), 1, text)
            self.path.unlink()

    def test_not_a_scheduled_run_writes_nothing(self):
        with mock.patch.object(run_timing, 'LOG', self.path):
            self.assertEqual(run_timing.main(['']), 0)
        self.assertFalse(self.path.exists())

class WorkflowStepTests(unittest.TestCase):
    def test_first_step_on_a_schedule_and_saved_with_the_data(self):
        wf = (ROOT / '.github/workflows/publish.yml').read_text(encoding='utf-8')
        at = wf.index('run: python scripts/run_timing.py "$SCHEDULE"')
        step = wf[wf.rindex('- name:', 0, at):at]
        self.assertIn("if: github.event_name == 'schedule'", step)
        self.assertIn('SCHEDULE: ${{ github.event.schedule }}', step)
        self.assertIn('continue-on-error: true', step)  # a logging problem never stops the run
        self.assertLess(wf.index('uses: actions/setup-python@'), at)
        for later in ('run: pip install -r requirements.txt', 'run: python scripts/refresh.py', 'run: python scripts/news.py',
                      'name: Save refreshed data'):
            self.assertLess(at, wf.index(later), later)
        save = wf[wf.index('name: Save refreshed data'):]
        self.assertIn("git add data ':!data/drafts'", save)  # data/run-timing.json goes with the refreshed data
        # The workflow's own cron line parses.
        cron = re.search(r"cron: '([^']+)'", wf).group(1)
        self.assertEqual(run_timing.last_slot(cron, utc(2026, 10, 16, 11, 0)), utc(2026, 10, 16, 10, 7))

if __name__ == '__main__':
    unittest.main()
