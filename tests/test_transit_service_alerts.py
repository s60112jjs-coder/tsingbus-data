"""Service-alert monitor: synthetic TDX alerts plus the archived 2026-10-22 DGPA closure page."""
import datetime as dt
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from test_transit_reliability import full

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('transit_service_alerts', ROOT / 'scripts/transit_service_alerts.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
TPE = ZoneInfo('Asia/Taipei')
EVENING = dt.datetime(2026, 10, 22, 20, 0, tzinfo=TPE)
TYPHOON_PAGE = (ROOT / 'tests/fixtures/dgpa_closures_2026-10-22.html').read_text(encoding='utf-8')
QUIET_PAGE = (ROOT / 'tests/fixtures/dgpa_no_closures.html').read_text(encoding='utf-8')
CATALOG = t.route_catalog(full())
# Synthetic fixtures use placeholder operators; use the real published names for operator scopes.
for rid, names in {'9003': {'三重客運', '新竹客運'}, '7500': {'和欣客運'}, '7513': {'和欣客運'}}.items():
    CATALOG[rid]['operators'] = names


def alert(alert_id, scope, status=0, effect=4, start='2026-10-23T00:00:00+08:00', end='2026-10-23T23:59:00+08:00', **extra):
    row = {'AlertID': alert_id, 'Title': f'測試 {alert_id}', 'Status': status, 'Effect': effect, 'Cause': 6,
           'PublishTime': '2026-10-22T19:00:00+08:00', 'StartTime': start, 'EndTime': end, 'Scope': scope}
    row.update(extra)
    return row


def route_scope(route_id, direction=255):
    return {'Routes': [{'RouteID': route_id, 'RouteName': {'Zh_tw': route_id}, 'Direction': direction}]}


def doc(intercity=(), hsinchu=(), page=QUIET_PAGE, previous=None, now=EVENING):
    fetched = {'TDX_BUS_ALERT_INTERCITY': None if intercity is None else list(intercity),
               'TDX_BUS_ALERT_HSINCHU': None if hsinchu is None else list(hsinchu)}
    return t.build_document(previous, fetched, page, CATALOG, now)


def states(document, rid):
    return [e['state'] for e in document['routes'].get(rid, [])]


class MonitorTests(unittest.TestCase):
    def test_operator_announces_full_day_suspension(self):
        d = doc([alert('A1', route_scope('7513'))])
        self.assertEqual(states(d, '7513'), ['SUSPENDED'])
        entry = d['alerts'][0]
        self.assertEqual((entry['startTime'], entry['endTime'], entry['cause']),
                         ('2026-10-23T00:00:00+08:00', '2026-10-23T23:59:00+08:00', 6))
        self.assertTrue(entry['url'].startswith('https://tdx.transportdata.tw/'))
        self.assertEqual(states(d, '7500'), [])  # Other routes of the same operator untouched.

    def test_single_direction_or_trip_is_partial_never_whole_route(self):
        d = doc([alert('A2', route_scope('THB1822', direction=0)),
                 alert('A3', {'Trips': [{'RouteID': '1728', 'Direction': 1, 'TripDepTime': '07:00'}]})])
        self.assertEqual(states(d, '1822'), ['PARTIAL_SUSPENSION'])
        self.assertEqual(d['routes']['1822'][0]['directions'], [0])
        self.assertEqual(d['routes']['1728'][0]['trips'], [{'direction': 1, 'departure': '07:00'}])

    def test_one_operator_of_a_joint_route_is_partial(self):
        d = doc([alert('A4', {'Operators': [{'OperatorName': {'Zh_tw': '三重客運'}}]})])
        self.assertEqual(states(d, '9003'), ['PARTIAL_SUSPENSION'])
        d = doc([alert('A5', {'Operators': [{'OperatorName': {'Zh_tw': '和欣客運'}}]})])
        self.assertEqual(states(d, '7500'), ['SUSPENDED'])
        self.assertEqual(states(d, '7513'), ['SUSPENDED'])

    def test_city_closure_without_operator_notice_is_only_unconfirmed(self):
        d = doc(page=TYPHOON_PAGE)
        self.assertEqual(d['closureHints'][0]['date'], '2026-10-23')
        for rid in CATALOG:
            self.assertEqual(states(d, rid), ['UNCONFIRMED'])
        self.assertNotIn('SUSPENDED', json.dumps(d['routes']))
        self.assertEqual(d['routes']['7513'][0]['cities'], ['新竹市', '臺南市', '高雄市'])
        self.assertEqual(d['routes']['1728'][0]['cities'], ['新竹市'])
        # District-only closures (Taoyuan's mountain schools) never flag a route.
        self.assertNotIn('桃園市', json.dumps(d['closureHints'], ensure_ascii=False))

    def test_official_alert_overrides_closure_hint_for_that_route_and_day(self):
        d = doc([alert('A1', route_scope('7513')),
                 alert('N1', route_scope('1728'), status=1, effect=None)], page=TYPHOON_PAGE)
        self.assertEqual(states(d, '7513'), ['SUSPENDED'])
        self.assertEqual(states(d, '1728'), ['NORMAL'])  # Officially confirmed normal.
        self.assertEqual(states(d, '182'), ['UNCONFIRMED'])

    def test_no_alerts_is_not_confirmed_normal(self):
        d = doc()
        self.assertEqual(d['routes'], {})
        self.assertEqual([s['state'] for s in d['sources']], ['OK', 'OK', 'OK'])

    def test_alert_modified_or_withdrawn_is_reflected_next_run(self):
        first = doc([alert('A1', route_scope('7513'))])
        modified = doc([alert('A1', route_scope('7513'), status=2, effect=3)], previous=first,
                       now=EVENING + dt.timedelta(hours=2))
        self.assertEqual(states(modified, '7513'), ['SERVICE_ALERT'])
        self.assertEqual(modified['alerts'][0]['firstSeenAt'], first['alerts'][0]['firstSeenAt'])
        withdrawn = doc([], previous=modified, now=EVENING + dt.timedelta(hours=4))
        self.assertEqual(withdrawn['alerts'], [])
        self.assertEqual(states(withdrawn, '7513'), [])

    def test_expired_and_open_ended_alerts_do_not_stay_forever(self):
        later = dt.datetime(2026, 10, 24, 1, 0, tzinfo=TPE)
        d = doc([alert('A1', route_scope('7513'))], now=later)
        self.assertEqual(d['alerts'], [])
        open_ended = alert('A6', route_scope('7513'), end=None, start='2026-10-23T06:00:00+08:00')
        fresh = doc([open_ended], now=dt.datetime(2026, 10, 23, 8, 0, tzinfo=TPE))
        self.assertEqual(states(fresh, '7513'), ['SUSPENDED'])
        self.assertEqual(fresh['alerts'][0]['expiresAt'], '2026-10-24T06:00:00+08:00')
        stale = doc([open_ended], now=dt.datetime(2026, 10, 24, 7, 0, tzinfo=TPE))
        self.assertEqual(states(stale, '7513'), ['SERVICE_ALERT'])

    def test_failed_source_keeps_unexpired_entries_and_reports_unavailable(self):
        first = doc([alert('A1', route_scope('7513'))], page=TYPHOON_PAGE)
        failed = doc(None, page=None, previous=first, now=EVENING + dt.timedelta(hours=2))
        self.assertEqual(states(failed, '7513'), ['SUSPENDED'])
        self.assertEqual({s['id']: s['state'] for s in failed['sources']},
                         {'TDX_BUS_ALERT_INTERCITY': 'UNAVAILABLE', 'TDX_BUS_ALERT_HSINCHU': 'OK', 'DGPA_CLOSURES': 'UNAVAILABLE'})
        self.assertEqual(failed['closureHints'], first['closureHints'])
        # validUntil only counts sources that actually answered; it never extends a dead feed.
        self.assertEqual(failed['validUntil'], first['validUntil'])

    def test_conflicting_fields_are_flagged_not_trusted(self):
        d = doc([alert('C1', route_scope('2011'), status=1, effect=4)])
        self.assertEqual(states(d, '2011'), ['SERVICE_ALERT'])
        self.assertTrue(d['alerts'][0]['conflict'])

    def test_city_feed_never_matches_intercity_routes_with_the_same_number(self):
        d = doc(hsinchu=[alert('H1', {'Routes': [{'RouteID': '1822', 'RouteName': {'Zh_tw': '1822'}}]})])
        self.assertEqual(states(d, '1822'), [])
        d = doc(hsinchu=[alert('H2', route_scope('182'))])
        self.assertEqual(states(d, '182'), ['SUSPENDED'])
        self.assertEqual(states(d, '1822'), [])

    def test_write_only_on_change_or_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs/v1').mkdir(parents=True)
            (root / 'docs/v1/manifest.json').write_text(json.dumps({'files': {'campus': {'path': 'campus.json'}}}))
            first = doc()
            self.assertTrue(t.publish(root, first, None, EVENING))
            stored = json.loads((root / t.ALERTS_PATH).read_text())
            again = doc(previous=stored, now=EVENING + dt.timedelta(hours=2))
            self.assertFalse(t.publish(root, again, stored, EVENING + dt.timedelta(hours=2)))
            beat = doc(previous=stored, now=EVENING + dt.timedelta(hours=13))
            self.assertTrue(t.publish(root, beat, stored, EVENING + dt.timedelta(hours=13)))
            refreshed = json.loads((root / t.ALERTS_PATH).read_text())
            self.assertEqual(refreshed['updatedAt'], stored['updatedAt'])  # Content unchanged.
            self.assertEqual(refreshed['validUntil'], '2026-10-24T15:00:00+08:00')
            manifest = json.loads((root / 'docs/v1/manifest.json').read_text())
            self.assertEqual(manifest['files']['transitAlerts']['path'], 'transit-alerts.json')
            self.assertEqual(manifest['files']['campus'], {'path': 'campus.json'})


if __name__ == '__main__':
    unittest.main()
