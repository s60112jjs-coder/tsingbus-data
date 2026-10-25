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


NOW = dt.datetime(2026, 10, 26, 8, 0, tzinfo=dt.timezone(dt.timedelta(hours=8)))


def stale(since, reason='SOURCE_MISSING', diagnosis='ROUTE_NOT_LISTED'):
    return {'feed': None, 'routes': {'1728': {'state': 'STALE_DATA', 'reason': reason, 'since': since,
                                              'dataAsOf': '2026-10-24T07:54:42+08:00',
                                              'diagnosis': {'diagnosis': diagnosis}}}}


class StatusIssueTests(unittest.TestCase):
    def episodes(self, issues=()):
        api = FakeAPI(issues)
        return api, m.Episodes(api, list(issues), False)

    def test_missing_route_waits_ten_hours_then_notifies_once(self):
        api, ep = self.episodes()
        m.maintain_status(ep, stale('2026-10-26T00:00:00+08:00'), None, NOW)
        self.assertEqual(api.writes, [])
        m.maintain_status(ep, stale('2026-10-25T21:50:00+08:00'), None, NOW)
        self.assertEqual(len(api.writes), 1)
        self.assertIn('1728', api.writes[0][2]['title'])
        m.maintain_status(ep, stale('2026-10-25T21:50:00+08:00'), None, NOW + dt.timedelta(days=1))
        self.assertEqual(len(api.writes), 1)  # Same episode, no daily repeat.

    def test_renamed_route_or_trip_drop_notifies_immediately(self):
        for status in (stale('2026-10-26T07:59:00+08:00', diagnosis='ROUTE_UID_CHANGED'),
                       stale('2026-10-26T07:59:00+08:00', reason='SUDDEN_TRIP_DROP')):
            api, ep = self.episodes()
            m.maintain_status(ep, status, None, NOW)
            self.assertEqual(len(api.writes), 1)

    def test_recovered_route_closes_its_issue(self):
        key = m.route_key('1728', '2026-10-25T21:50:00+08:00')
        api, ep = self.episodes([{'body': key, 'state': 'open', 'number': 13}])
        m.maintain_status(ep, {'feed': None, 'routes': {}}, None, NOW)
        self.assertEqual(api.writes, [('PATCH', 'issues/13', {'state': 'closed'})])

    def test_service_suspension_issue_is_deduplicated_and_closed_when_withdrawn(self):
        alerts = {'validUntil': '2026-10-27T00:00:00+08:00', 'alerts': [
            {'id': 'TDX_BUS_ALERT_INTERCITY:A1', 'title': '颱風停駛', 'department': '和欣客運', 'publishTime': None,
             'startTime': '2026-10-23T00:00:00+08:00', 'endTime': None, 'expiresAt': '2026-10-24T00:00:00+08:00',
             'url': 'https://example.invalid', 'routes': {'7513': {'state': 'SUSPENDED'}}},
            {'id': 'TDX_BUS_ALERT_INTERCITY:A2', 'title': '改道', 'routes': {'2011': {'state': 'SERVICE_ALERT'}}}]}
        api, ep = self.episodes()
        m.maintain_status(ep, None, alerts, NOW)
        m.maintain_status(ep, None, alerts, NOW)
        self.assertEqual(len(api.writes), 1)  # Only the suspension, only once.
        issues = [{'body': m.service_key('TDX_BUS_ALERT_INTERCITY:A1'), 'state': 'open', 'number': 20}]
        api, ep = self.episodes(issues)
        m.maintain_status(ep, None, {'validUntil': '2026-10-27T00:00:00+08:00', 'alerts': []}, NOW)
        self.assertEqual(api.writes, [('PATCH', 'issues/20', {'state': 'closed'})])

    def test_feed_and_monitor_staleness_can_recur_after_closing(self):
        closed = [{'body': m.FEED_STALE_KEY, 'state': 'closed', 'number': 5}]
        api, ep = self.episodes(closed)
        m.maintain_status(ep, {'feed': None, 'routes': {}}, None, NOW, last_success='2026-10-24T20:00:00+08:00')
        self.assertEqual(len(api.writes), 1)
        api, ep = self.episodes()
        m.maintain_status(ep, None, {'validUntil': '2026-10-25T00:00:00+08:00', 'alerts': []}, NOW)
        self.assertEqual(len(api.writes), 1)
        self.assertIn('監測', api.writes[0][2]['title'])

    def test_failed_step_name_is_explained(self):
        self.assertIn('人工確認', m.explain('失敗：官方資料規格變更（需人工檢查）'))
        api = FakeAPI()
        m.maintain(api, '2027-12-31', dt.date(2026, 10, 3),
                   {'conclusion': 'failure', 'html_url': 'https://github.com/example', 'failed_step': '發布後複檢（約 5 分鐘後）'})
        self.assertIn('發布後複檢', api.writes[0][2]['body'])


if __name__ == '__main__':
    unittest.main()
