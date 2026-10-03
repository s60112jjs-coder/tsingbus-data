import datetime as dt
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('transit_alerts', Path(__file__).resolve().parents[1] / 'scripts/transit_alerts.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FakeAPI:
    repo = 's60112jjs-coder/tsingbus-data'

    def __init__(self, issues=()):
        self.existing = list(issues)
        self.writes = []

    def issues(self):
        return self.existing

    def request(self, method, path, body=None):
        self.writes.append((method, path, body))


class AlertTests(unittest.TestCase):
    def test_calendar_boundary_and_owner_assignment(self):
        self.assertEqual(m.due_date('2027-12-31'), dt.date(2027, 11, 1))
        api = FakeAPI()
        m.maintain(api, '2027-12-31', dt.date(2027, 10, 31), None)
        self.assertEqual(api.writes, [])
        m.maintain(api, '2027-12-31', dt.date(2027, 11, 1), None)
        self.assertEqual(len(api.writes), 1)
        self.assertEqual(api.writes[0][2]['assignees'], ['s60112jjs-coder'])

    def test_closed_calendar_reminder_is_not_repeated_and_new_year_is_independent(self):
        api = FakeAPI([{'body': m.calendar_key('2027-12-31'), 'state': 'closed', 'number': 1}])
        m.maintain(api, '2027-12-31', dt.date(2028, 1, 1), None)
        self.assertEqual(api.writes, [])
        m.maintain(api, '2028-12-31', dt.date(2028, 12, 1), None)
        self.assertEqual(len(api.writes), 1)

    def test_failure_deduplication_and_recovery(self):
        api = FakeAPI([{'body': m.FAILURE_KEY, 'state': 'open', 'number': 4}])
        m.maintain(api, '2027-12-31', dt.date(2026, 10, 3), {'conclusion': 'failure', 'html_url': 'https://github.com/example'})
        self.assertEqual(api.writes, [])
        m.maintain(api, '2027-12-31', dt.date(2026, 10, 3), {'conclusion': 'success'})
        self.assertEqual(api.writes, [('PATCH', 'issues/4', {'state': 'closed'})])

    def test_new_failure_episode_after_recovery(self):
        api = FakeAPI([{'body': m.FAILURE_KEY, 'state': 'closed', 'number': 4}])
        m.maintain(api, '2027-12-31', dt.date(2026, 10, 3), {'conclusion': 'failure', 'html_url': 'https://github.com/example'})
        self.assertEqual(len(api.writes), 1)

    def test_dry_run_has_no_writes_and_cancel_does_not_send_failure(self):
        api = FakeAPI()
        result = m.maintain(api, '2027-12-31', dt.date(2027, 12, 1), {'conclusion': 'failure', 'html_url': 'https://github.com/example'}, dry_run=True)
        self.assertEqual(len(result), 2)
        self.assertEqual(api.writes, [])
        m.maintain(api, '2027-12-31', dt.date(2026, 10, 3), {'conclusion': 'cancelled'})
        self.assertEqual(api.writes, [])


if __name__ == '__main__':
    unittest.main()
