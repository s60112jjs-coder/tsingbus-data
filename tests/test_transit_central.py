"""Synthetic central-line safety fixtures, never real published schedules."""
import copy
import unittest
from test_sync_transit import CALENDAR, m
from test_transit_south import south_fixture


def central_fixture():
    raw = south_fixture()
    for rid, (uid, _, number, _) in m.CENTRAL_ROUTES.items():
        ops = m.CENTRAL_OPERATORS[rid]
        route = {'RouteUID': uid, 'RouteName': {'Zh_tw': number},
                 'Operators': [{'OperatorID': op, 'OperatorCode': code,
                                'OperatorName': {'Zh_tw': code, 'En': code}} for op, code in ops.items()],
                 'SubRoutes': []}
        rows, schedules = [], []
        subs = ['THB186601', 'THB186602', 'THB1866B1', 'THB1866B2', 'THB1866C2'] if rid == '1866' else ['THB901001', 'THB901002']
        for sub in subs:
            if rid == '1866':
                direction = 0 if sub.endswith('1') else 1
                names = ['新竹轉運站', '清華大學', '中清交流道', '水湳轉運中心', '國光客運臺中車站']
                if direction:
                    names.reverse()
                if sub == 'THB1866C2':
                    names = ['水湳轉運中心', '清華大學', '新竹轉運站']
            elif sub.endswith('1'):
                direction = 0
                names = ['臺中車站(大智北路)', '朝馬站', '清華大學', '新竹轉運站']
            else:
                direction = 1
                names = ['新竹轉運站', '清華大學', '水湳轉運中心', '朝馬(臺灣大道)', '臺中車站(民族路口)']
            route['SubRoutes'].append({'SubRouteUID': sub, 'Direction': direction, 'OperatorIDs': list(ops)})
            for j, op in enumerate(ops):
                stops = [{'StopSequence': i, 'StopUID': f'{sub}_{op}_{i}',
                          'StopName': {'Zh_tw': n, 'En': n},
                          'LocationCityCode': 'TXG' if n in m.CENTRAL_STOP_IDS else 'HSZ',
                          'StopPosition': {'PositionLat': 24.2 - i / 1000}}
                         for i, n in enumerate(names, 1)]
                rows.append({'SubRouteUID': sub, 'Direction': direction, 'Operators': [{'OperatorID': op}], 'Stops': stops})
                trip = {'ServiceDay': dict(zip(m.DAY_KEYS, [1] * 7)),
                        'StopTimes': [dict(s, DepartureTime=m.clock(8 * 60 + j * 20 + i * 10)) for i, s in enumerate(stops)]}
                if sub in ('THB186601', 'THB186602'):
                    trip['StopTimes'] = trip['StopTimes'][:3]
                if sub == 'THB1866C2':
                    trip['SpecialDays'] = [{'Dates': ['2026-10-24'], 'ServiceStatus': 0}]
                schedules.append({'SubRouteUID': sub, 'Direction': direction, 'OperatorID': op, 'Timetables': [trip]})
        raw[uid] = {'route': route, 'scope': 'InterCity', 'stops': rows, 'schedules': schedules}
    return raw


def build(raw):
    return m.build(raw, CALENDAR, '2026-10-15', origin_frequency_ready=True)


class CentralTests(unittest.TestCase):
    def test_fourteen_routes_five_groups_preserve_existing_data(self):
        raw = central_fixture()
        baseline = m.build_without_central(raw, CALENDAR, '2026-10-15', origin_frequency_ready=True)
        result = build(raw)
        self.assertEqual(len(result['routes']), 14)
        self.assertEqual([g['id'] for g in result['groups']], ['TRA', 'HSR', 'TAIPEI', 'SOUTH', 'CENTRAL'])
        self.assertEqual(result['groups'][:4], baseline['groups'])
        self.assertEqual([r for r in result['routes'] if r['id'] not in m.CENTRAL_ROUTES], baseline['routes'])
        self.assertEqual(result['stops'][:len(baseline['stops'])], baseline['stops'])
        central = result['groups'][-1]['sections'][0]
        self.assertEqual(central['routes'], ['1866', '9010'])
        self.assertNotIn('HSINCHU_BUS_STATION', central['destinationStops'])

    def test_partial_outbound_only_advertises_confirmed_timed_leg(self):
        result = build(central_fixture())
        direction = next(d for r in result['routes'] if r['id'] == '1866' for d in r['directions'] if 'THB186601' in d['id'])
        self.assertEqual(direction['stops'], ['HSINCHU_BUS_STATION', 'NTHU_NORTH_GATE', 'ZHONGQING_INTERCHANGE'])
        self.assertNotIn('TAICHUNG_KUOKUANG', direction['trips'][0]['times'])
        self.assertEqual(direction['timeKind'], 'STOP_TIME')

    def test_partial_inbound_without_campus_is_not_origin_only(self):
        route = next(r for r in build(central_fixture())['routes'] if r['id'] == '1866')
        self.assertFalse(any('THB186602' in d['id'] for d in route['directions']))
        self.assertTrue(any('THB1866B2' in d['id'] for d in route['directions']))

    def test_9010_operators_and_opposite_terminal_locations_stay_distinct(self):
        route = next(r for r in build(central_fixture())['routes'] if r['id'] == '9010')
        self.assertEqual(len(route['directions']), 4)
        for d in route['directions']:
            if 'THB901001' in d['id']:
                self.assertEqual(d['stops'][0], 'TAICHUNG_STATION_DAZHI')
                self.assertIn('CHAOMA', d['stops'])
                self.assertNotIn('TAICHUNG_STATION_MINZU', d['stops'])
            else:
                self.assertEqual(d['stops'][-1], 'TAICHUNG_STATION_MINZU')
                self.assertIn('CHAOMA_TAIWAN_BLVD', d['stops'])
        trips = [d['trips'][0]['times']['NTHU_NORTH_GATE'] for d in route['directions'] if 'THB901001' in d['id']]
        self.assertEqual(set(trips), {'08:20', '08:40'})

    def test_true_origin_only_retains_real_origin_name(self):
        raw = central_fixture()
        schedule = raw['THB9010']['schedules'][0]
        schedule['Timetables'][0]['StopTimes'] = schedule['Timetables'][0]['StopTimes'][:1]
        d = next(d for r in build(raw)['routes'] if r['id'] == '9010' for d in r['directions'] if d['timeKind'] == 'ORIGIN_DEPARTURE_ONLY')
        self.assertEqual(d['originZh'], '臺中車站(大智北路)')
        self.assertEqual(d['trips'][0]['origin'], '08:00')

    def test_dates_midnight_and_fetch_order_are_stable(self):
        raw = central_fixture()
        trip = raw['THB1866']['schedules'][-1]['Timetables'][0]
        for i, t in enumerate(trip['StopTimes']):
            t['DepartureTime'] = m.clock((23 * 60 + 50 + i * 20) % 1440)
        first = build(raw)
        d = next(d for r in first['routes'] if r['id'] == '1866' for d in r['directions'] if 'THB1866C2' in d['id'])
        self.assertEqual(d['trips'][0]['times']['NTHU_NORTH_GATE'], '24:10')
        self.assertEqual(d['trips'][0]['serviceExceptions'], [{'startDate': '2026-10-24', 'endDate': '2026-10-24', 'runs': False}])
        for uid in ('THB1866', 'THB9010'):
            raw[uid]['schedules'].reverse()
            raw[uid]['stops'].reverse()
            for row in raw[uid]['stops']:
                for stop in row['Stops']:
                    stop['StopPosition']['PositionLat'] += 0.00001
        self.assertEqual(first, build(raw))

    def test_missing_route_operator_core_or_taichung_mapping_fails(self):
        modifications = [
            lambda d: d.pop('THB1866'),
            lambda d: d['THB9010']['route']['Operators'].pop(),
            lambda d: d['THB9010'].update(schedules=[s for s in d['THB9010']['schedules'] if not (s['SubRouteUID'] == 'THB901001' and s['OperatorID'] == '56')]),
            lambda d: d['THB1866']['stops'][0]['Stops'][-1]['StopName'].update(Zh_tw='Unknown Taichung stop'),
            lambda d: d['THB1866']['stops'][0]['Stops'][-1].pop('LocationCityCode'),
        ]
        for mutate in modifications:
            raw = central_fixture()
            mutate(raw)
            with self.assertRaises(m.InvalidData):
                build(raw)

    def test_partial_skips_still_validate_identity_and_exceptions(self):
        for kind in ('identity', 'dates'):
            raw = central_fixture()
            trip = raw['THB1866']['schedules'][1]['Timetables'][0]
            if kind == 'identity':
                trip['StopTimes'][0]['StopUID'] = 'WRONG'
            else:
                trip['SpecialDays'] = [{'Dates': ['2026-02-30'], 'ServiceStatus': 0}]
            with self.assertRaises(m.InvalidData):
                build(raw)

    def test_no_cross_operator_fallback_or_unreviewed_campus_branches(self):
        raw = central_fixture()
        raw['THB9010']['stops'] = [r for r in raw['THB9010']['stops'] if not (r['SubRouteUID'] == 'THB901001' and r['Operators'][0]['OperatorID'] == '56')]
        with self.assertRaises(m.InvalidData):
            build(raw)
        raw = central_fixture()
        row = copy.deepcopy(raw['THB1866']['stops'][0]);row['SubRouteUID'] = 'THB1866X1'
        schedule = copy.deepcopy(raw['THB1866']['schedules'][0]);schedule['SubRouteUID'] = 'THB1866X1'
        raw['THB1866']['stops'].append(row);raw['THB1866']['schedules'].append(schedule)
        with self.assertRaises(m.InvalidData):
            build(raw)

    def test_collect_stays_six_whitelist_calls_for_fourteen_routes(self):
        raw = central_fixture()
        class Client:
            def __init__(self): self.calls = []
            def get(self, endpoint, query):
                self.calls.append((endpoint, query))
                kind, scope = endpoint.split('/', 1)
                bundles = [v for v in raw.values() if v.get('scope', 'City/Hsinchu' if v['route']['RouteUID'].startswith('HSZ') else 'InterCity') == scope]
                if kind == 'Route': return [v['route'] for v in bundles]
                field = 'stops' if kind == 'StopOfRoute' else 'schedules'
                return [dict(s, RouteUID=v['route']['RouteUID']) for v in bundles for s in v[field]]
        client = Client();data = m.collect(client)
        self.assertEqual(len(data), 14)
        self.assertEqual(len(client.calls), 6)
        self.assertTrue(all('THB1866' in q and 'THB9010' in q for e, q in client.calls if e.endswith('InterCity')))


if __name__ == '__main__': unittest.main()
