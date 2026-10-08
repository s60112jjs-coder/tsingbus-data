"""Synthetic safety fixtures; never used as a real published timetable."""
import unittest

from test_sync_transit import CALENDAR, fixtures, m


def south_fixture():
    data = fixtures()
    paths = {
        '7500': ['臺北轉運站', '三重站', '新竹站', '麻豆站轉運站', '永康轉運站', '六甲頂站', '臺南轉運站'],
        '7513': ['臺北轉運站', '三重站', '新竹站', '新營站', '楠梓站', '捷運苓雅運動園區站', '建國客運站'],
    }
    for rid, (uid, scope, name, _) in m.SOUTH_ROUTES.items():
        core = sorted(m.SOUTH_CORE[rid])
        # Both a bypass branch and an optional origin-only branch are exercised.
        subs = core + [uid + 'X1', uid + '01', uid + '02']
        if rid == '7513':
            subs.append('THB7513F2')
        route = {'RouteUID': uid, 'RouteName': {'Zh_tw': name},
                 'Operators': [{'OperatorID': '25', 'OperatorCode': 'HoHsinBus',
                                'OperatorName': {'Zh_tw': '和欣客運', 'En': 'Ho-Hsin Bus'}}],
                 'SubRoutes': []}
        rows, schedules = [], []
        for sub in subs:
            direction = 0 if sub.endswith('1') else 1
            names = list(paths[rid])
            if direction == 1:
                names.reverse()
            if sub.endswith('X1'):
                names.remove('新竹站')
            stops = [{'StopSequence': i, 'StopUID': f'{sub}_STOP_{i}', 'StopName': {'Zh_tw': n, 'En': n}}
                     for i, n in enumerate(names, 1)]
            route['SubRoutes'].append({'SubRouteUID': sub, 'Direction': direction, 'OperatorIDs': ['25']})
            rows.append({'SubRouteUID': sub, 'Direction': direction, 'Operators': [{'OperatorID': '25'}], 'Stops': stops})
            trip = {'ServiceDay': dict(zip(m.DAY_KEYS, [1] * 7)),
                    'StopTimes': [dict(s, DepartureTime=m.clock(8 * 60 + i * 15)) for i, s in enumerate(stops)]}
            if sub.endswith('01'):
                trip['StopTimes'] = trip['StopTimes'][:1]
            if sub.endswith('02') and rid == '7500':
                trip['StopTimes'] = trip['StopTimes'][:2]  # Partial data cannot prove Hsinchu service.
            if sub == 'THB7513F2':
                trip['ServiceDay'] = dict(zip(m.DAY_KEYS, [0] * 6 + [1]))
                trip['SpecialDays'] = [
                    {'Dates': ['2026-10-09'], 'ServiceStatus': 0},
                    {'DatePeriod': {'StartDate': '2026-10-09', 'EndDate': '2026-10-11'}, 'ServiceStatus': 0}]
            schedules.append({'SubRouteUID': sub, 'Direction': direction, 'OperatorID': '25', 'Timetables': [trip]})
        data[uid] = {'route': route, 'scope': scope, 'stops': rows, 'schedules': schedules}
    return data


def build(data):
    return m.build(data, CALENDAR, '2026-10-09', origin_frequency_ready=True)


class SouthTests(unittest.TestCase):
    def test_complete_build_keeps_existing_routes_groups_and_stop_ids(self):
        raw = south_fixture()
        base = m.build_base(raw, CALENDAR, '2026-10-09', origin_frequency_ready=True)
        result = build(raw)
        self.assertEqual(result['schemaVersion'], 1)
        self.assertEqual(result['groups'][:3], base['groups'])
        self.assertEqual(result['stops'][:len(base['stops'])], base['stops'])
        self.assertEqual([r for r in result['routes'] if r['id'] not in m.SOUTH_ROUTES], base['routes'])
        self.assertEqual(result['groups'][3]['sections'][0]['routes'], ['7500', '7513'])
        hsinchu = next(s for s in result['stops'] if s['id'] == 'HOHSIN_HSINCHU')
        self.assertEqual(hsinchu['side'], 'CAMPUS')
        self.assertEqual(m.stop_id('5608', {'StopName': {'Zh_tw': '新竹站'}}), 'HSINCHU_BUS_DEPOT')

    def test_both_directions_and_bypass_branches_are_filtered(self):
        result = build(south_fixture())
        for route in result['routes']:
            if route['id'] not in m.SOUTH_ROUTES:
                continue
            self.assertEqual({d['stops'][0] == 'HOHSIN_HSINCHU' for d in route['directions']}, {True, False})
            for direction in route['directions']:
                self.assertIn('HOHSIN_HSINCHU', direction['stops'])
                self.assertNotIn('TAIPEI_BUS_STATION', direction['stops'])
                self.assertNotIn('X1', direction['id'])

    def test_origin_only_keeps_real_origin_and_partial_trip_is_excluded(self):
        route = next(r for r in build(south_fixture())['routes'] if r['id'] == '7500')
        direction = next(d for d in route['directions'] if d['id'].endswith('_ORIGIN'))
        self.assertEqual(direction['originZh'], '臺北轉運站')
        self.assertEqual(direction['trips'][0]['origin'], '08:00')
        self.assertNotIn('THB750002', ' '.join(d['id'] for d in route['directions']))
        self.assertNotIn('HOHSIN_HSINCHU', direction['trips'][0].get('times', {}))

    def test_stop_times_and_service_exceptions_preserved(self):
        route = next(r for r in build(south_fixture())['routes'] if r['id'] == '7513')
        direction = next(d for d in route['directions'] if 'THB7513F2' in d['id'])
        trip = direction['trips'][0]
        self.assertEqual(trip['days'], ['SUN'])
        self.assertEqual(trip['serviceExceptions'], [
            {'startDate': '2026-10-09', 'endDate': '2026-10-11', 'runs': False}])
        self.assertEqual(trip['times']['HOHSIN_HSINCHU'], '09:00')

    def test_dates_periods_and_order_normalize_without_fake_update(self):
        first = {'SpecialDays': [{'Dates': ['2026-10-10', '2026-10-09', '2026-10-10'], 'ServiceStatus': 0},
                                 {'DatePeriod': {'StartDate': '2026-10-11', 'EndDate': '2026-10-11'}, 'ServiceStatus': 0}]}
        second = {'SpecialDays': [{'DatePeriod': {'StartDate': '2026-10-09', 'EndDate': '2026-10-11'},
                                  'ServiceStatus': 0, 'Description': 'different human text'}]}
        self.assertEqual(m.service_exceptions(first), m.service_exceptions(second))
        raw = south_fixture()
        before = build(raw)
        for uid in ('THB7500', 'THB7513'):
            raw[uid]['stops'].reverse()
            raw[uid]['schedules'].reverse()
        self.assertEqual(before, build(raw))

    def test_invalid_exceptions_and_unreviewed_status_fail(self):
        bad = [None, [{}], [{'Dates': ['2026-02-30'], 'ServiceStatus': 0}],
               [{'Dates': ['20261009'], 'ServiceStatus': 0}],
               [{'Dates': [], 'ServiceStatus': 0}],
               [{'Dates': ['2026-10-09'], 'ServiceStatus': True}],
               [{'Dates': ['2026-10-09'], 'ServiceStatus': 1}],
               [{'DatePeriod': {'StartDate': '2026-10-11', 'EndDate': '2026-10-09'}, 'ServiceStatus': 0}]]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(m.InvalidData):
                m.service_exceptions({'SpecialDays': value})

    def test_missing_route_core_direction_operator_or_new_stop_fails(self):
        modifications = [
            lambda d: d.pop('THB7513'),
            lambda d: d['THB7500'].update(schedules=[s for s in d['THB7500']['schedules'] if s['SubRouteUID'] != 'THB7500F2']),
            lambda d: d['THB7513']['route']['Operators'][0].update(OperatorID='26'),
            lambda d: d['THB7500']['stops'][0]['Stops'][3]['StopName'].update(Zh_tw='Unreviewed stop'),
        ]
        for modify in modifications:
            raw = south_fixture()
            modify(raw)
            with self.assertRaises(m.InvalidData):
                build(raw)

    def test_stop_identity_or_partial_core_hsinchu_time_fails(self):
        raw = south_fixture()
        raw['THB7513']['schedules'][0]['Timetables'][0]['StopTimes'][2]['StopUID'] = 'WRONG'
        with self.assertRaises(m.InvalidData):
            build(raw)
        raw = south_fixture()
        trip = raw['THB7513']['schedules'][0]['Timetables'][0]
        trip['StopTimes'] = [s for s in trip['StopTimes'] if s['StopName']['Zh_tw'] != '新竹站']
        with self.assertRaises(m.InvalidData):
            build(raw)

    def test_midnight_keeps_exceptions_on_original_service_day(self):
        raw = south_fixture()
        trip = raw['THB7513']['schedules'][0]['Timetables'][0]
        trip['SpecialDays'] = [{'Dates': ['2026-10-11'], 'ServiceStatus': 0}]
        for i, s in enumerate(trip['StopTimes']):
            s['DepartureTime'] = m.clock((23 * 60 + 30 + i * 20) % 1440)
        result = build(raw)
        d = next(d for r in result['routes'] if r['id'] == '7513' for d in r['directions'] if 'THB7513B1' in d['id'])
        self.assertEqual(d['trips'][0]['times']['HOHSIN_HSINCHU'], '24:10')
        self.assertEqual(d['trips'][0]['serviceExceptions'][0]['startDate'], '2026-10-11')

    def test_collect_uses_six_whitelist_requests_with_south_in_intercity_batch(self):
        raw = south_fixture()
        class Client:
            def __init__(self):
                self.calls = []
            def get(self, endpoint, query):
                self.calls.append((endpoint, query))
                kind, scope = endpoint.split('/', 1)
                bundles = [v for v in raw.values() if v.get('scope', 'City/Hsinchu' if v['route']['RouteUID'].startswith('HSZ') else 'InterCity') == scope]
                if kind == 'Route':
                    return [b['route'] for b in bundles]
                field = 'stops' if kind == 'StopOfRoute' else 'schedules'
                return [dict(s, RouteUID=b['route']['RouteUID']) for b in bundles for s in b[field]]
        client = Client()
        result = m.collect(client)
        self.assertEqual(len(client.calls), 6)
        self.assertIn('THB7500', result)
        self.assertIn('THB7513', result)
        self.assertTrue(all('THB7500' in q and 'THB7513' in q for e, q in client.calls if e.endswith('InterCity')))


if __name__ == '__main__':
    unittest.main()
