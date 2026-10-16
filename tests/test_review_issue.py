"""The review issue: one status comment edited by every run, a new comment only when the owner must act; the monthly
AI cost ledger it shows; newly failing sources. gh is never called: a fake stands in for it."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ai_cost
import draft
import news
import refresh
import review_issue as R

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 16, 10, 30, tzinfo=timezone.utc)
BOT = 'github-actions[bot]'

class FakeGh:
    """Stands in for gh: open issues, the issue's comments, and every call made."""
    def __init__(self, issues=(2,), comments=()):
        self.issues, self.comments, self.calls, self.next_id = list(issues), [dict(c) for c in comments], [], 100

    def __call__(self, *args, data=None):
        self.calls.append((args, data))
        if args[:2] == ('issue', 'list'):
            return json.dumps([{'number': n} for n in self.issues[:1]])
        if args[:2] == ('label', 'create'):
            return ''
        if args[0] == 'api' and '--paginate' in args:
            return ''.join(json.dumps(c) + '\n' for c in self.comments)
        if args[0] == 'api':
            method, path = args[args.index('-X') + 1], args[args.index('-X') + 2]
            if method == 'POST' and path == 'repos/{owner}/{repo}/issues':
                self.issues.append(7)
                return json.dumps({'number': 7})
            if method == 'POST' and path.endswith('/comments'):
                self.next_id += 1
                self.comments.append({'id': self.next_id, 'user': BOT, 'body': data['body']})
                return json.dumps({'id': self.next_id})
            if method == 'PATCH':
                cid = int(path.rsplit('/', 1)[1])
                next(c for c in self.comments if c['id'] == cid)['body'] = data['body']
                return '{}'
        raise AssertionError(f'unexpected gh call {args}')

    def writes(self, method):
        return [(a[a.index('-X') + 2], d) for a, d in self.calls if a[0] == 'api' and '-X' in a and a[a.index('-X') + 1] == method]

    def new_comments(self):
        return [d['body'] for path, d in self.writes('POST') if path.endswith('/comments')]

    def alerts(self):
        """The alert comments posted (each an email); the status comment is not one."""
        return [b for b in self.new_comments() if b.startswith('**Needs you')]

class FailingAlertGh(FakeGh):
    """gh whose alert comment cannot be posted (a rate limit or a server error); everything else works."""
    def __call__(self, *args, data=None):
        if data and data.get('body', '').startswith('**Needs you'):
            self.failed = getattr(self, 'failed', 0) + 1  # not a write: GitHub refused it
            raise subprocess.CalledProcessError(1, ['gh', *args], stderr='HTTP 502')
        return super().__call__(*args, data=data)

def report(**kw):
    r = {'at': '2026-10-16T10:09:44+00:00', 'health': {'successful_sources': 257, 'failed_sources': 2, 'attempted_sources': 259},
         'changes': [], 'review': [{'url': 'https://blogs.nvidia.com/blog/a/', 'reason': 'Official page changed; inspect timeline', 'at': 'x'}],
         'errors': {'https://forums.developer.nvidia.com/t/1': 'HTTPError 403: Forbidden', 'https://www.nvidia.com/x': 'ValueError: Source incomplete or blocked'},
         'new_errors': []}
    r.update(kw)
    return r

def product(pid, checked):
    return {'id': pid, 'model': pid.upper(), 'price': {'usd_low': 1, 'checked': checked}}

class ReviewIssueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'data').mkdir()
        self.write('refresh-report.json', report())
        self.write('draft-report.json', {'created': [], 'waiting': [], 'in_pull_request': [], 'pull_requests': []})
        self.write('catalog.json', {'products': [product('fresh', '2026-10-08'), {'id': 'noprice', 'model': 'No price', 'price': None}]})
        self.write('news.json', {'ai': {'key_set': True, 'policy_version': 1, 'policy_checked': 3, 'regional': 2}, 'items': []})
        self.write('ai-cost.json', {'2026-09': {'usd': 9.8, 'runs': 58}, '2026-10': {'usd': 4.1234, 'runs': 20, 'last_run': '1-1'}})
        self.write('run-timing.json', [{'slot': 's', 'started_at': 't', 'delay_min': d} for d in (204.7, 30.0, 12.5)])
        patch = mock.patch.object(R, 'ROOT', self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, obj):
        (self.root / 'data' / name).write_text(json.dumps(obj), encoding='utf-8')

    def run_review(self, fake):
        with mock.patch('builtins.print'):
            self.assertEqual(R.main(run=fake, now=NOW), 0)
        return fake

    def status(self, fake):
        return R.find_status(fake.comments)

    def test_one_status_comment_edited_every_run_no_new_comment_when_nothing_needs_the_owner(self):
        # The first run on the existing issue adds the status comment once; later runs only edit it (no email).
        fake = self.run_review(FakeGh(comments=[{'id': 1, 'user': BOT, 'body': 'Source check at ... (an old run comment)'}]))
        self.assertEqual(len(fake.new_comments()), 1)
        body = self.status(fake)['body']
        self.assertTrue(body.startswith(R.MARKER))
        for text in ('257/259 reached', '2 failing', '**AI cost (estimate):** $4.12 in October 2026 over 20 runs (September: $9.80, 58 runs).',
                     'Content policy (UAE/GCC)', 'the last one started 12.5 min after its slot; median 30 min over the last 3',
                     '**AI drafts:** none open.', 'Official pages that changed', 'https://blogs.nvidia.com/blog/a/',
                     'Failing sources', 'HTTPError 403: Forbidden', 'no email'):
            self.assertIn(text, body)
        self.assertNotIn('Approximate prices', body)
        for run in range(3):
            fake = self.run_review(FakeGh(comments=fake.comments))
            self.assertEqual(fake.new_comments(), [], run)
            self.assertEqual([p for p, _ in fake.writes('PATCH')], [f"repos/{{owner}}/{{repo}}/issues/comments/{self.status(fake)['id']}"])

    def test_prices_are_flagged_at_30_days(self):
        from datetime import date
        self.assertEqual(R.STALE_PRICE_DAYS, 30)
        catalog = {'products': [product('d29', '2026-09-17'), product('d30', '2026-09-16'), product('d47', '2026-08-30'),
                                {'id': 'none', 'model': 'NONE', 'price': None}, {'id': 'nodate', 'model': 'X', 'price': {'usd_low': 1, 'checked': None}}]}
        stale = R.stale_prices(catalog, date(2026, 10, 16))
        self.assertEqual([(s['id'], s['days']) for s in stale], [('d47', 47), ('d30', 30)])
        self.write('catalog.json', catalog)
        fake = self.run_review(FakeGh())
        [alert] = fake.alerts()
        self.assertIn('Approximate price 30 days old: D30 (checked 2026-09-16)', alert)
        self.assertNotIn('D29', alert)
        self.assertIn('**Approximate prices 30 days old or more:** D47 (2026-08-30), D30 (2026-09-16)', self.status(fake)['body'])

    def test_a_price_reaching_the_limit_is_announced_once(self):
        self.write('catalog.json', {'products': [product('fresh', '2026-10-08'), product('old', '2026-08-30')]})
        fake = self.run_review(FakeGh())
        [alert] = fake.alerts()
        self.assertIn('**Needs you:**', alert)
        self.assertIn('Approximate price 47 days old: OLD (checked 2026-08-30)', alert)
        self.assertNotIn('FRESH', alert)
        self.assertIn('OLD (2026-08-30)', self.status(fake)['body'])
        self.assertEqual(R.read_alerted(self.status(fake)['body']), {'price:old:2026-08-30'})
        # The next runs: still old, already announced, so only the status comment is edited.
        fake = self.run_review(FakeGh(comments=fake.comments))
        self.assertEqual(fake.new_comments(), [])
        # Updated, then old again later: a new check date is announced again.
        self.write('catalog.json', {'products': [product('old', '2026-08-31')]})
        fake = self.run_review(FakeGh(comments=fake.comments))
        self.assertEqual(len(fake.new_comments()), 1)

    def test_spec_changes_newly_failing_sources_and_drafts_are_announced(self):
        self.write('refresh-report.json', report(changes=['H200: power_w changed from 600 to 700'],
                                                new_errors=['https://forums.developer.nvidia.com/t/1']))
        self.write('draft-report.json', {'created': ['Instinct MI999X'], 'waiting': ['Instinct MI999X'], 'in_pull_request': [],
                                         'pull_requests': [], 'pr_error': 'The pull request step failed, so 1 AI draft(s) are not in a pull request.'})
        fake = self.run_review(FakeGh())
        [alert] = fake.alerts()
        for text in ('Verified specification change (already applied): H200: power_w changed from 600 to 700',
                     f'Source failing in {refresh.FAILING_AFTER} checks in a row: https://forums.developer.nvidia.com/t/1 (HTTPError 403: Forbidden)',
                     'AI draft waiting for its pull request: Instinct MI999X', 'The pull request step failed'):
            self.assertIn(text, alert)
        self.assertIn('AI drafts waiting for a pull request', self.status(fake)['body'])
        # The same report again (a re-run): nothing new.
        fake = self.run_review(FakeGh(comments=fake.comments))
        self.assertEqual(fake.new_comments(), [])
        # The pull request was opened: the draft stays announced, the failure is settled; no comment.
        self.write('draft-report.json', {'created': [], 'waiting': [], 'in_pull_request': ['Instinct MI999X'], 'pull_requests': [12]})
        fake = self.run_review(FakeGh(comments=fake.comments))
        self.assertEqual(fake.new_comments(), [])
        self.assertIn('1 to check in pull request #12: Instinct MI999X', self.status(fake)['body'])
        # A second draft joins the pull request: announced.
        self.write('draft-report.json', {'created': ['Helios 2'], 'waiting': [], 'in_pull_request': ['Instinct MI999X', 'Helios 2'], 'pull_requests': [12]})
        fake = self.run_review(FakeGh(comments=fake.comments))
        self.assertEqual(len(fake.new_comments()), 1)
        self.assertIn('AI draft to check in pull request #12: Helios 2', fake.new_comments()[0])
        self.assertNotIn('MI999X', fake.new_comments()[0])

    def test_a_status_comment_by_anyone_else_is_never_trusted(self):
        # The issue is public: a forged comment cannot mark alerts as announced or take the status comment's place.
        self.write('catalog.json', {'products': [product('old', '2026-08-30')]})
        forged = R.MARKER + '\nfake\n<!-- alerted: ["price:old:2026-08-30"] -->'
        fake = self.run_review(FakeGh(comments=[{'id': 5, 'user': 'someone', 'body': forged}]))
        self.assertEqual(fake.writes('PATCH'), [])
        self.assertTrue(any('Approximate price 47 days old' in b for b in fake.new_comments()))
        self.assertEqual(self.status(fake)['user'], BOT)

    def test_an_alert_that_could_not_be_posted_is_posted_by_the_next_run(self):
        # The alert is posted before the status comment is written, and only what was posted counts as announced.
        self.write('refresh-report.json', report(changes=['H200: power_w changed from 600 to 700'],
                                                new_errors=['https://forums.developer.nvidia.com/t/1']))
        self.write('catalog.json', {'products': [product('old', '2026-08-30')]})
        fake = FailingAlertGh(comments=[])
        with mock.patch('builtins.print'):
            self.assertEqual(R.main(run=fake, now=NOW), 1)  # the step shows the failure (it is continue-on-error)
        self.assertEqual((fake.failed, fake.alerts()), (1, []))
        body = self.status(fake)['body']
        self.assertEqual(R.read_alerted(body), set())
        # A spec change and a newly failing source belong to this run only: they are carried until posted.
        self.assertEqual([k.split(':')[0] for k, _ in R.read_unsent(body)], ['change', 'fail'])
        # The next run (gh works again; this source check found nothing new) posts all three.
        self.write('refresh-report.json', report(at='2026-10-16T22:09:44+00:00'))
        fake = self.run_review(FakeGh(comments=fake.comments))
        [alert] = fake.alerts()
        for text in ('Verified specification change (already applied): H200: power_w changed from 600 to 700',
                     'Source failing in', 'https://forums.developer.nvidia.com/t/1', 'Approximate price 47 days old: OLD'):
            self.assertIn(text, alert)
        body = self.status(fake)['body']
        self.assertEqual((R.read_alerted(body), R.read_unsent(body)), ({'price:old:2026-08-30'}, []))
        # And never again.
        fake = self.run_review(FakeGh(comments=fake.comments))
        self.assertEqual(fake.new_comments(), [])

    def test_a_failed_post_of_a_lasting_alert_is_tried_again_without_being_carried(self):
        self.write('catalog.json', {'products': [product('old', '2026-08-30')]})
        fake = FailingAlertGh(comments=[])
        with mock.patch('builtins.print'):
            R.main(run=fake, now=NOW)
        self.assertEqual(R.read_unsent(self.status(fake)['body']), [])  # still in `current` next run: not carried
        fake = self.run_review(FakeGh(comments=fake.comments))
        self.assertIn('Approximate price 47 days old: OLD', fake.alerts()[0])

    def test_old_announcements_settled_without_a_draft_are_listed_once(self):
        urls = ['https://newsroom.amd.com/news/aai-2026-ryzen-ai-embedded-x100/', 'https://newsroom.amd.com/news/aai-2026-helios-update/']
        self.write('draft-report.json', {'at': '2026-10-16T22:20:00+00:00', 'created': [], 'waiting': [], 'in_pull_request': [],
                                         'pull_requests': [], 'settled_without_pull_request': urls})
        fake = self.run_review(FakeGh(comments=[]))
        [alert] = fake.alerts()
        for text in ('2 official announcement(s) were marked "drafted" before pull requests were tracked', 'no new Claude cost',
                     '`python scripts/draft.py --redraft URL`', *urls):
            self.assertIn(text, alert)
        self.assertIn('Old announcements settled without a draft', self.status(fake)['body'])
        # A run that reads the same report (no draft step): nothing new.
        fake = self.run_review(FakeGh(comments=fake.comments))
        self.assertEqual(fake.new_comments(), [])
        # The next draft run settles nothing: the line goes, no comment.
        self.write('draft-report.json', {'at': '2026-10-17T10:20:00+00:00', 'created': [], 'waiting': [], 'in_pull_request': [], 'pull_requests': []})
        fake = self.run_review(FakeGh(comments=fake.comments))
        self.assertEqual(fake.new_comments(), [])
        self.assertNotIn('Old announcements', self.status(fake)['body'])

    def test_no_open_issue(self):
        # Nothing needs the owner: no issue is opened.
        fake = self.run_review(FakeGh(issues=()))
        self.assertEqual(fake.writes('POST'), [])
        # Something does: the issue is opened with it (that is the alert), then the status comment; no second alert.
        self.write('catalog.json', {'products': [product('old', '2026-08-30')]})
        fake = self.run_review(FakeGh(issues=()))
        (path, issue), *comments = fake.writes('POST')
        self.assertEqual(path, 'repos/{owner}/{repo}/issues')
        self.assertEqual(issue['labels'], [R.LABEL])
        self.assertIn('Approximate price 47 days old', issue['body'])
        self.assertEqual(len(comments), 1)
        self.assertTrue(comments[0][1]['body'].startswith(R.MARKER))
        self.assertEqual(comments[0][0], 'repos/{owner}/{repo}/issues/7/comments')

    def test_status_text_fits_one_comment_and_keeps_its_hidden_list(self):
        many = [{'url': f'https://nvidianews.nvidia.com/news/{"x" * 300}{n}', 'reason': 'Official page changed', 'at': 'x'} for n in range(400)]
        keys = [f'price:p{n}:2026-08-30' for n in range(50)] + ['change:-->x:y']
        unsent = [('change:t:-->x', 'Verified specification change (already applied): -->x'), ('price:p:1', 'not one-shot: never carried')]
        text = R.status_text(report(review=many), {}, [], keys, NOW, self.root / 'data/news.json', self.root / 'data/ai-cost.json',
                             self.root / 'data/run-timing.json', unsent)
        self.assertLessEqual(len(text), 65536)
        self.assertIn(f'and {400 - R.LIST_MAX} more', text)
        self.assertEqual(R.read_alerted(text), set(keys))
        self.assertEqual(R.read_unsent(text), unsent[:1])
        self.assertEqual(text.count('-->'), text.count('<!--'))  # no key can end the hidden comment early
        self.assertNotIn('@', text.replace('github-actions[bot]', ''))  # no mention: an edit never notifies anyone

    def test_failure_reasons_and_manual_checks_are_shown(self):
        self.write('refresh-report.json', report(manual_checks=[{'url': 'https://marketplace.nvidia.com/en-us/products/rtx-spark/',
                                                                 'why': refresh.MANUAL_WHY}]))
        fake = self.run_review(FakeGh())
        body = self.status(fake)['body']
        for text in ('2 failing (below); 1 script-rendered pages to check by hand (below).', 'To check by hand (not fetched automatically) (1)',
                     'https://marketplace.nvidia.com/en-us/products/rtx-spark/: Script-rendered page',
                     'https://forums.developer.nvidia.com/t/1: HTTPError 403: Forbidden'):
            self.assertIn(text, body)
        self.assertEqual(fake.new_comments()[1:], [])  # nothing to act on: only the status comment

    def test_workflow_step(self):
        wf = (ROOT / '.github/workflows/publish.yml').read_text(encoding='utf-8')
        at = wf.index('run: python scripts/review_issue.py')
        step = wf[wf.rindex('- name:', 0, at):at]
        self.assertIn('GH_TOKEN: ${{ github.token }}', step)
        self.assertIn('continue-on-error: true', step)
        self.assertLess(wf.index('name: Save refreshed data'), at)
        self.assertIn('issues: write', wf)

class CostLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'ai-cost.json'

    def test_month_usd_and_runs(self):
        self.assertIsNone(ai_cost.add(0.5, 0, NOW, 'r1', self.path))  # no request: nothing written
        self.assertFalse(self.path.exists())
        ai_cost.add(0.2909, 11, NOW, '10-1', self.path)   # news.py
        ai_cost.add(0.031, 1, NOW, '10-1', self.path)     # draft.py in the same run
        ai_cost.add(0.1, 3, NOW, '11-1', self.path)       # the next run
        ai_cost.add(0.2, 3, datetime(2026, 11, 1, tzinfo=timezone.utc), '12-1', self.path)
        ledger = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual((ledger['2026-10']['usd'], ledger['2026-10']['runs']), (0.4219, 2))
        self.assertEqual((ledger['2026-11']['usd'], ledger['2026-11']['runs']), (0.2, 1))
        self.assertEqual(ai_cost.month_line(datetime(2026, 11, 2, tzinfo=timezone.utc), self.path),
                         '**AI cost (estimate):** $0.20 in November 2026 over 1 run (October: $0.42, 2 runs).')
        self.assertEqual(ai_cost.month_line(datetime(2027, 3, 1, tzinfo=timezone.utc), self.path), '')
        # The ledger began mid-month: that month says so.
        self.assertEqual(ai_cost.month_line(NOW, self.path), '**AI cost (estimate):** $0.42 in October 2026 (counted from 16 Oct) over 2 runs.')
        # Local runs (no GITHUB_RUN_ID) count each script run.
        with mock.patch.dict(os.environ, {'GITHUB_RUN_ID': ''}):
            ai_cost.add(0.1, 1, NOW, path=self.path)
            ai_cost.add(0.1, 1, NOW, path=self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['2026-10']['runs'], 4)

    def test_keeps_24_months_and_survives_a_broken_file(self):
        self.path.write_text(json.dumps({f'2024-{m:02d}': {'usd': 1, 'runs': 1} for m in range(1, 13)} |
                                        {f'2025-{m:02d}': {'usd': 1, 'runs': 1} for m in range(1, 13)}), encoding='utf-8')
        ai_cost.add(1, 1, NOW, 'r', self.path)
        ledger = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(len(ledger), ai_cost.KEEP_MONTHS)
        self.assertNotIn('2024-01', ledger)
        self.path.write_text('{broken', encoding='utf-8')
        self.assertEqual(ai_cost.add(1, 1, NOW, 'r', self.path), {'usd': 1.0, 'runs': 1, 'from': '2026-10-16', 'last_run': 'r'})

    def test_news_and_draft_add_their_usage_when_they_end(self):
        # Both use the same model and list prices; each records when its script ends (even after an error).
        self.assertEqual((draft.MODEL, draft.PRICE_IN, draft.PRICE_OUT), (news.MODEL, news.PRICE_IN, news.PRICE_OUT))
        for module in (news, draft):
            with mock.patch.object(module, 'usage_report', return_value={'requests': 4, 'estimated_usd': 0.25}), \
                 mock.patch.object(ai_cost, 'add') as add:
                module.record_cost()
            add.assert_called_once_with(0.25, 4)
            with mock.patch.object(ai_cost, 'add', side_effect=OSError('read-only')), mock.patch('builtins.print'):
                module.record_cost()  # never fails the run
            src = (ROOT / 'scripts' / f'{module.__name__}.py').read_text(encoding='utf-8')
            self.assertIn('    finally:\n        record_cost()', src.split("if __name__ == '__main__':")[1])
        usage = type('U', (), {'input_tokens': 1_000_000, 'output_tokens': 100_000})()
        response = type('R', (), {'usage': usage, 'stop_reason': 'refusal', 'parsed_output': None})()
        client = type('C', (), {})()
        client.messages = type('M', (), {'parse': staticmethod(lambda **kw: response)})()
        before = dict(draft.USAGE)
        draft.extract(client, 'https://newsroom.amd.com/news/x/', 't', 'text')
        self.assertEqual(draft.USAGE['requests'] - before['requests'], 1)
        self.assertEqual(draft.USAGE['input_tokens'] - before['input_tokens'], 1_000_000)

class NewlyFailingTests(unittest.TestCase):
    def test_failing_after_two_checks_in_a_row(self):
        state = {'https://a.nvidia.com/': {'digest': 'd', 'checked_at': 't'}}
        errors = {'https://a.nvidia.com/': 'HTTPError: 503', 'https://old.nvidia.com/': 'ValueError: blocked'}
        # Already failing in the previous report (before this count existed): not new.
        self.assertEqual(refresh.mark_failures(state, errors, {'https://old.nvidia.com/': 'ValueError'}), [])
        self.assertEqual(state['https://a.nvidia.com/']['failures'], 1)
        self.assertEqual(refresh.mark_failures(state, errors, errors), ['https://a.nvidia.com/'])  # second in a row
        self.assertEqual(refresh.mark_failures(state, errors, errors), [])                          # announced once
        self.assertEqual(state['https://old.nvidia.com/']['failures'], refresh.FAILING_AFTER + 3)

class TimingStatusTests(unittest.TestCase):
    def test_start_delays_and_a_damaged_log(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run-timing.json'
            self.assertEqual(R.timing_status(path), '')
            path.write_text(json.dumps([{'delay_min': 'late'}, 'x', {'slot': 's'}, {'delay_min': 7}, {'delay_min': 3.5}]), encoding='utf-8')
            self.assertEqual(R.timing_status(path), '**Scheduled runs:** the last one started 3.5 min after its slot; median 5.25 min over the last 2.')

if __name__ == '__main__':
    unittest.main()
