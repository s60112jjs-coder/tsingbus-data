"""Sync reliability: carry-forward, retries, conflict re-apply, Pages re-check. Synthetic data only."""
import argparse
import datetime as dt
import importlib.util
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from test_sync_transit import CALENDAR, m
from test_transit_central import central_fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_pages', ROOT / 'scripts/verify_pages.py')
vp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vp)
NOW = dt.datetime(2026, 10, 25, 21, 50, tzinfo=ZoneInfo('Asia/Taipei'))


def full():
    return m.build(central_fixture(), CALENDAR, '2026-10-24', origin_frequency_ready=True)


def workspace(previous=None):
    directory = tempfile.TemporaryDirectory()
    root = Path(directory.name)
    (root / 'docs/v1').mkdir(parents=True)
    (root / 'scripts').mkdir()
    (root / 'scripts/transit-holidays.json').write_text(json.dumps(CALENDAR))
    previous = previous or full()
    (root / 'docs/v1/transit.json').write_text(json.dumps(previous, ensure_ascii=False))
    (root / 'docs/v1/manifest.json').write_text(json.dumps({'schemaVersion': 2, 'files': {
        'campus': {'path': 'campus.json', 'updatedAt': 'keep'},
        'transit': {'path': 'transit.json', 'updatedAt': '2026-10-24T07:54:42+08:00'}}}))
    return directory, root


def args(root, fixture=None, **extra):
    values = dict(input=None, root=root, preview=None, origin_frequency_ready=True, skip_2011=False, rounds=2,
                  retry_wait=300, accept_trip_drop='', result=None, save_candidate=None, apply_candidate=None,
                  record_failure=None, last_success=None)
    if fixture is not None:
        path = root / 'fixture.json'
        path.write_text(json.dumps(fixture, ensure_ascii=False))
        values['input'] = path
    values.update(extra)
    return argparse.Namespace(**values)


class FakeClient:
    """Serves collect()/diagnose_absent() from a raw fixture; can fail the first N rounds."""
    def __init__(self, raw, fail_rounds=0, rename=None):
        self.raw, self.fail_rounds, self.rename, self.requests = raw, fail_rounds, rename, 0

    def get(self, endpoint, query=None, allow_empty=False):
        self.requests += 1
        kind, scope = endpoint.split('/', 1)
        if FakeClient.round_no <= self.fail_rounds:
            raise m.TransientSourceError(f'TDX {endpoint} HTTP 503')
        bundles = [v for v in self.raw.values() if v.get('scope', 'City/Hsinchu' if v['route']['RouteUID'].startswith('HSZ') else 'InterCity') == scope]
        if kind == 'Route':
            if query and 'RouteName' in query:
                return [dict(self.rename, RouteName={'Zh_tw': '1728'})] if self.rename else []
            return [v['route'] for v in bundles]
        field = 'stops' if kind == 'StopOfRoute' else 'schedules'
        return [dict(s, RouteUID=v['route']['RouteUID']) for v in bundles for s in v[field]]


def factory(client):
    def make():
        FakeClient.round_no += 1
        return client
    FakeClient.round_no = 0
    return make


class ReliabilityTests(unittest.TestCase):
    def test_missing_1728_keeps_last_verified_copy_and_marks_it_stale(self):
        previous = full()
        directory, root = workspace(previous)
        with directory:
            raw = central_fixture()
            del raw['THB1728']
            # Another route really changed, so the rest of the feed must still update.
            raw['THB2011']['schedules'][0]['Frequencys'][0]['MaxHeadwayMins'] = 20
            client = FakeClient(raw)
            result = m.run(args(root), NOW, client_factory=factory(client), sleep=lambda s: None)
            self.assertEqual(result['held'], {'1728': 'SOURCE_MISSING'})
            data = json.loads((root / 'docs/v1/transit.json').read_text())
            routes = {r['id']: r for r in data['routes']}
            self.assertEqual(routes['1728'], {r['id']: r for r in previous['routes']}['1728'])
            self.assertIn(20, [f['maxHeadway'] for d in routes['2011']['directions'] for f in d.get('frequencies', [])])
            status = json.loads((root / 'docs/v1/transit-status.json').read_text())
            entry = status['routes']['1728']
            self.assertEqual((entry['state'], entry['reason'], entry['dataAsOf']),
                             ('STALE_DATA', 'SOURCE_MISSING', '2026-10-24T07:54:42+08:00'))
            self.assertEqual(entry['diagnosis']['diagnosis'], 'ROUTE_NOT_LISTED')
            manifest = json.loads((root / 'docs/v1/manifest.json').read_text())
            self.assertEqual(manifest['files']['transitStatus']['path'], 'transit-status.json')
            self.assertEqual(manifest['files']['campus']['updatedAt'], 'keep')
            # Next run, still missing: "since" must not move, so the 10-hour notice can fire.
            later = NOW + dt.timedelta(hours=12)
            m.run(args(root), later, client_factory=factory(FakeClient(raw)), sleep=lambda s: None)
            again = json.loads((root / 'docs/v1/transit-status.json').read_text())['routes']['1728']
            self.assertEqual(again['since'], entry['since'])
            # Recovery clears the status entry.
            m.run(args(root), later + dt.timedelta(hours=12), client_factory=factory(FakeClient(central_fixture())), sleep=lambda s: None)
            self.assertEqual(json.loads((root / 'docs/v1/transit-status.json').read_text())['routes'], {})

    def test_route_uid_change_is_diagnosed_not_guessed(self):
        directory, root = workspace()
        with directory:
            raw = central_fixture()
            del raw['THB1728']
            renamed = {'RouteUID': 'THB1728X', 'Operators': [{'OperatorName': {'Zh_tw': '新業者'}}]}
            m.run(args(root), NOW, client_factory=factory(FakeClient(raw, rename=renamed)), sleep=lambda s: None)
            diagnosis = json.loads((root / 'docs/v1/transit-status.json').read_text())['routes']['1728']['diagnosis']
            self.assertEqual(diagnosis['diagnosis'], 'ROUTE_UID_CHANGED')
            self.assertEqual(diagnosis['foundRouteUIDs'], ['THB1728X'])
            # The renamed route's data is never adopted automatically.
            data = json.loads((root / 'docs/v1/transit.json').read_text())
            self.assertNotIn('新業者', json.dumps(data, ensure_ascii=False))

    def test_missing_route_without_previous_copy_or_too_many_missing_rejects(self):
        raw = central_fixture()
        del raw['THB1728']
        previous = full()
        previous['routes'] = [r for r in previous['routes'] if r['id'] != '1728']
        with self.assertRaises(m.SourceIncomplete):
            m.build_resilient(raw, CALENDAR, '2026-10-25', previous, True)
        raw = central_fixture()
        for uid in ('THB1728', 'THB9003', 'THB1822'):
            del raw[uid]
        with self.assertRaises(m.SourceIncomplete):
            m.build_resilient(raw, CALENDAR, '2026-10-25', full(), True)

    def test_incomplete_stops_or_trips_still_reject_whole_feed(self):
        for mutate in (lambda d: d['THB1728']['stops'][0]['Stops'].pop(),
                       lambda d: d['THB9003']['schedules'].pop(),
                       lambda d: d['THB1822']['schedules'][0]['Timetables'][0]['StopTimes'][1].update(StopUID='WRONG')):
            raw = central_fixture()
            mutate(raw)
            with self.assertRaises(m.InvalidData):
                m.build_resilient(raw, CALENDAR, '2026-10-25', full(), True)

    def test_sudden_trip_drop_is_held_unless_a_human_accepts_it(self):
        previous = full()
        for route in previous['routes']:
            if route['id'] == '1728':
                for d in route['directions']:
                    d['trips'] = d['trips'] * 5
        candidate, held = m.build_resilient(central_fixture(), CALENDAR, '2026-10-25', previous, True)
        self.assertEqual(held, {'1728': 'SUDDEN_TRIP_DROP'})
        self.assertEqual({r['id']: r for r in candidate['routes']}['1728'], {r['id']: r for r in previous['routes']}['1728'])
        candidate, held = m.build_resilient(central_fixture(), CALENDAR, '2026-10-25', previous, True,
                                            accept_drops=frozenset({'1728'}))
        self.assertEqual(held, {})

    def test_weekday_that_loses_every_trip_is_held(self):
        previous = full()
        raw = central_fixture()
        for schedule in raw['THB1728']['schedules']:
            for trip in schedule['Timetables']:
                trip['ServiceDay'] = dict(zip(m.DAY_KEYS, [1, 0, 0, 0, 0, 0, 1]))  # Only Mon/Sun left.
        candidate, held = m.build_resilient(raw, CALENDAR, '2026-10-25', previous, True)
        self.assertEqual(held, {'1728': 'SERVICE_DAY_LOST'})
        self.assertEqual({r['id']: r for r in candidate['routes']}['1728'], {r['id']: r for r in previous['routes']}['1728'])
        _, held = m.build_resilient(raw, CALENDAR, '2026-10-25', previous, True, accept_drops=frozenset({'1728'}))
        self.assertEqual(held, {})

    def test_carried_south_route_keeps_its_stops_and_destinations(self):
        previous = full()
        raw = central_fixture()
        del raw['THB7513']
        candidate, held = m.build_resilient(raw, CALENDAR, '2026-10-25', previous, True)
        stop_ids = {s['id'] for s in candidate['stops']}
        route = {r['id']: r for r in candidate['routes']}['7513']
        self.assertTrue({sid for d in route['directions'] for sid in d['stops']} <= stop_ids)
        south = next(g for g in candidate['groups'] if g['id'] == 'SOUTH')['sections'][0]
        old_south = next(g for g in previous['groups'] if g['id'] == 'SOUTH')['sections'][0]
        self.assertEqual(south['destinationStops'], old_south['destinationStops'])

    def test_timeout_is_transient_and_gets_one_more_round(self):
        directory, root = workspace()
        with directory:
            client = FakeClient(central_fixture(), fail_rounds=1)
            waits = []
            result = m.run(args(root), NOW, client_factory=factory(client), sleep=waits.append)
            self.assertEqual(waits, [300])
            self.assertIn(result['category'], ('OK_CHANGED', 'OK_UNCHANGED'))

    def test_two_failed_rounds_raise_transient_and_publish_nothing(self):
        directory, root = workspace()
        with directory:
            before = {p.name: p.read_bytes() for p in (root / 'docs/v1').iterdir()}
            client = FakeClient(central_fixture(), fail_rounds=2)
            with self.assertRaises(m.TransientSourceError) as caught:
                m.run(args(root), NOW, client_factory=factory(client), sleep=lambda s: None)
            self.assertEqual(m.classify(caught.exception), 'TRANSIENT_SOURCE')
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'docs/v1').iterdir()})

    def test_data_errors_are_not_retried(self):
        directory, root = workspace()
        with directory:
            raw = central_fixture()
            raw['THB1728']['route']['RouteName'] = {'Zh_tw': '1728A'}
            waits = []
            with self.assertRaises(m.InvalidData) as caught:
                m.run(args(root), NOW, client_factory=factory(FakeClient(raw)), sleep=waits.append)
            self.assertEqual((waits, m.classify(caught.exception)), ([], 'SPEC_CHANGED'))

    def test_tdx_timeout_and_http_errors_are_classified(self):
        client = m.TDX.__new__(m.TDX)
        client.token, client.last_request, client.requests = 't', 0, 0
        with mock.patch.object(m.time, 'sleep'), mock.patch.object(m.urllib.request, 'urlopen', side_effect=TimeoutError()):
            with self.assertRaises(m.TransientSourceError):
                client.get('Route/InterCity', "RouteUID eq 'THB1728'")
        error = urllib.error.HTTPError('u', 404, 'nf', {}, None)
        with mock.patch.object(m.time, 'sleep'), mock.patch.object(m.urllib.request, 'urlopen', side_effect=error):
            with self.assertRaises(m.InvalidData) as caught:
                client.get('Route/InterCity', 'x')
            self.assertNotIsInstance(caught.exception, m.TransientSourceError)

    def test_conflict_retry_reapplies_saved_candidate_on_new_main(self):
        directory, root = workspace()
        with directory:
            saved = root / 'candidate.json'
            raw = central_fixture()
            raw['THB2011']['schedules'][0]['Frequencys'][0]['MaxHeadwayMins'] = 20
            m.run(args(root, save_candidate=saved), NOW, client_factory=factory(FakeClient(raw)), sleep=lambda s: None)
            published = (root / 'docs/v1/transit.json').read_bytes()
            # Simulate "git reset --hard origin/main" where someone else changed campus meanwhile.
            directory2, fresh = workspace()
            with directory2:
                manifest = json.loads((fresh / 'docs/v1/manifest.json').read_text())
                manifest['files']['campus']['updatedAt'] = 'someone-else'
                (fresh / 'docs/v1/manifest.json').write_text(json.dumps(manifest))
                m.run(args(fresh, apply_candidate=saved), NOW)
                self.assertEqual((fresh / 'docs/v1/transit.json').read_bytes(), published)
                self.assertEqual(json.loads((fresh / 'docs/v1/manifest.json').read_text())['files']['campus']['updatedAt'],
                                 'someone-else')

    def test_feed_marked_stale_only_after_30_hours_and_cleared_on_success(self):
        directory, root = workspace()
        with directory:
            fresh = (NOW - dt.timedelta(hours=10)).isoformat()
            result = m.run(args(root, record_failure='TRANSIENT_SOURCE', last_success=fresh), NOW)
            self.assertFalse(result['feedStale'])
            old = (NOW - dt.timedelta(hours=31)).isoformat()
            result = m.run(args(root, record_failure='TRANSIENT_SOURCE', last_success=old), NOW)
            self.assertTrue(result['feedStale'] and result['changed'])
            # Transit data itself must stay untouched while marking stale.
            self.assertEqual(json.loads((root / 'docs/v1/transit.json').read_text()), full())
            m.run(args(root), NOW, client_factory=factory(FakeClient(central_fixture())), sleep=lambda s: None)
            self.assertIsNone(json.loads((root / 'docs/v1/transit-status.json').read_text())['feed'])

    def test_manual_suspensions_survive_sync(self):
        previous = full()
        previous['suspensions'] = [{'date': '2026-10-23', 'routes': ['ALL'], 'noteZh': '颱風停駛'}]
        directory, root = workspace(previous)
        with directory:
            raw = central_fixture()
            raw['THB2011']['schedules'][0]['Frequencys'][0]['MaxHeadwayMins'] = 20
            m.run(args(root), NOW, client_factory=factory(FakeClient(raw)), sleep=lambda s: None)
            self.assertEqual(json.loads((root / 'docs/v1/transit.json').read_text())['suspensions'], previous['suspensions'])

    def test_old_app_schema_unchanged_by_carry_forward(self):
        raw = central_fixture()
        del raw['THB1728']
        candidate, _ = m.build_resilient(raw, CALENDAR, '2026-10-25', full(), True)
        self.assertEqual(set(candidate), set(full()))
        self.assertEqual(candidate['schemaVersion'], 1)
        for route in candidate['routes']:
            self.assertEqual(set(route), {'id', 'number', 'zh', 'en', 'operatorZh', 'operatorEn', 'directions'})

    def test_no_change_produces_no_write(self):
        directory, root = workspace()
        with directory:
            m.run(args(root), NOW, client_factory=factory(FakeClient(central_fixture())), sleep=lambda s: None)
            before = {p.name: p.read_bytes() for p in (root / 'docs/v1').iterdir()}
            result = m.run(args(root), NOW + dt.timedelta(hours=12), client_factory=factory(FakeClient(central_fixture())),
                           sleep=lambda s: None)
            self.assertEqual(result['category'], 'OK_UNCHANGED')
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'docs/v1').iterdir()})


class PagesVerifyTests(unittest.TestCase):
    def test_delayed_pages_eventually_match(self):
        expected = {'manifest.json': b'new', 'transit.json': b'T'}
        served = iter([b'old', b'old', b'new', b'T'])
        waits = []
        self.assertIsNone(vp.verify('https://x/v1/', expected, fetch=lambda url: next(served), sleep=waits.append, attempts=5))
        self.assertEqual(waits, [15, 15])

    def test_pages_never_updates_reports_failure(self):
        problem = vp.verify('https://x/v1/', {'manifest.json': b'new'}, fetch=lambda url: b'old',
                            sleep=lambda s: None, attempts=3)
        self.assertEqual(problem, 'manifest.json is not current')


if __name__ == '__main__':
    unittest.main()
