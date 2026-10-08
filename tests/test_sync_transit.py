import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('sync_transit', Path(__file__).resolve().parents[1] / 'scripts/sync_transit.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixtures():
    data = {}
    for rid, (uid, scope, name, subs) in m.ROUTES.items():
        route = {'RouteUID': uid, 'RouteName': {'Zh_tw': name},
                 'Operators': [{'OperatorID': '1', 'OperatorName': {'Zh_tw': 'Official Operator'}}],
                 'SubRoutes': [{'SubRouteUID': sub, 'OperatorIDs': ['1']} for sub in subs]}
        stop_rows, schedules = [], []
        for sub in subs:
            names = ['北校門', '新竹轉運站'] if rid == '83' else ['清華大學', '火車站']
            if rid == '2011':
                names = ['新竹轉運站', '清華大學', '臺北轉運站']
            if rid == 'BLUE1_LOCAL' and sub == 'HSZ001001':
                names = ['火車站', '清華大學', '竹中', '清華大學', '火車站']
            stops = [{'StopSequence': i, 'StopUID': f'STOP_{i}', 'StopName': {'Zh_tw': n}} for i, n in enumerate(names, 1)]
            stop_rows.append({'SubRouteUID': sub, 'Direction': 0, 'Operators': [{'OperatorID': '1'}], 'Stops': stops})
            trip = {'ServiceDay': dict(zip(m.DAY_KEYS, [1] * 7)),
                    'StopTimes': [dict(s, DepartureTime=f'08:{i * 5:02d}') for i, s in enumerate(stops)]}
            schedule = {'SubRouteUID': sub, 'Direction': 0, 'OperatorID': '1', 'Timetables': [trip], 'Frequencys': []}
            if rid == '2011':
                schedule['Frequencys'] = [{'StartTime': '06:00', 'EndTime': '20:00', 'MinHeadwayMins': 10,
                                          'MaxHeadwayMins': 15, 'ServiceDay': dict(zip(m.DAY_KEYS, [1] * 7))}]
            schedules.append(schedule)
        data[uid] = {'route': route, 'stops': stop_rows, 'schedules': schedules}
    return data


CALENDAR = {'coverageStart': '2026-01-01', 'coverageEnd': '2027-12-31', 'holidays': ['2026-10-09', '2026-10-10']}


class TransitTests(unittest.TestCase):
    def test_midnight_preserves_service_day_and_official_minutes(self):
        trip = {'StopTimes': [{'StopSequence': 1, 'DepartureTime': '23:59'},
                              {'StopSequence': 2, 'DepartureTime': '00:05'},
                              {'StopSequence': 3, 'DepartureTime': '01:10'}]}
        self.assertEqual([v[1] for v in m.normalized_stop_times(trip).values()], ['23:59', '24:05', '25:10'])

    def test_backwards_non_midnight_times_fail(self):
        with self.assertRaises(m.InvalidData):
            m.normalized_stop_times({'StopTimes': [{'StopSequence': 1, 'DepartureTime': '08:30'},
                                                  {'StopSequence': 2, 'DepartureTime': '08:10'}]})

    def test_frequency_origin_gate_and_safe_defer(self):
        with self.assertRaises(m.InvalidData):
            m.build_base(fixtures(), CALENDAR, '2026-10-03')
        candidate = m.build_base(fixtures(), CALENDAR, '2026-10-03', skip_2011=True)
        self.assertEqual(len(candidate['routes']), 9)
        self.assertNotIn('2011', candidate['groups'][2]['sections'][0]['routes'])
        full = m.build_base(fixtures(), CALENDAR, '2026-10-03', origin_frequency_ready=True)
        f = next(d for r in full['routes'] if r['id'] == '2011' for d in r['directions'] if d['timeKind'] == 'FREQUENCY')
        self.assertEqual(f['originZh'], '新竹轉運站')
        self.assertEqual(f['frequencies'][0]['end'], '20:00')

    def test_loop_is_split_and_stops_are_not_conflated(self):
        candidate = m.build_base(fixtures(), CALENDAR, '2026-10-03', origin_frequency_ready=True)
        blue = next(r for r in candidate['routes'] if r['id'] == 'BLUE1_LOCAL')
        loop = [d for d in blue['directions'] if d['id'].startswith('BLUE1_LOCAL_0_')]
        self.assertEqual({tuple(d['stops']) for d in loop},
                         {('HSINCHU_TRA', 'NTHU_NORTH_GATE'), ('NTHU_NORTH_GATE', 'HSINCHU_TRA')})
        back = next(d for d in loop if d['stops'][0] == 'NTHU_NORTH_GATE')
        self.assertEqual(back['trips'][0]['times']['NTHU_NORTH_GATE'], '08:15')
        self.assertEqual(m.stop_id('83', {'StopName': {'Zh_tw': '北校門'}}), 'NTHU_CAMPUS_NORTH_GATE')
        self.assertIsNone(m.stop_id('83', {'StopName': {'Zh_tw': '清大南大校區'}}))

    def test_missing_route_or_operator_fails(self):
        data = fixtures()
        del data['THB1728']
        with self.assertRaises(m.InvalidData):
            m.build_base(data, CALENDAR, '2026-10-03', origin_frequency_ready=True)
        data = fixtures()
        data['THB9003']['route']['SubRoutes'][0]['OperatorIDs'].append('2')
        with self.assertRaises(m.InvalidData):
            m.build_base(data, CALENDAR, '2026-10-03', origin_frequency_ready=True)

    def test_metadata_and_fetch_order_do_not_create_content_changes(self):
        data = fixtures()
        first = m.build_base(data, CALENDAR, '2026-10-03', origin_frequency_ready=True)
        for bundle in data.values():
            bundle['route']['UpdateTime'] = '2099-01-01'
            bundle['schedules'].reverse()
            bundle['stops'].reverse()
        second = m.build_base(data, CALENDAR, '2026-10-04', origin_frequency_ready=True)
        self.assertEqual(m.semantic(first), m.semantic(second))

    def test_noop_and_two_real_updates_same_day(self):
        candidate = m.build_base(fixtures(), CALENDAR, '2026-10-03', origin_frequency_ready=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs/v1').mkdir(parents=True)
            manifest = root / 'docs/v1/manifest.json'
            manifest.write_text(json.dumps({'schemaVersion': 2, 'files': {'campus': {'path': 'campus.json', 'updatedAt': 'keep'}}}))
            self.assertTrue(m.publish(candidate, root, '2026-10-03T05:30:00+08:00'))
            before = {p.name: p.read_bytes() for p in (root / 'docs/v1').iterdir()}
            candidate['updatedAt'] = '2026-10-04'
            self.assertFalse(m.publish(candidate, root, '2026-10-04T05:30:00+08:00'))
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'docs/v1').iterdir()})
            changed = copy.deepcopy(candidate)
            changed['updatedAt'] = '2026-10-03'
            changed['routes'][0]['directions'][0]['trips'][0]['times']['NTHU_NORTH_GATE'] = '09:00'
            self.assertTrue(m.publish(changed, root, '2026-10-03T17:30:00+08:00'))
            self.assertEqual(json.loads(manifest.read_text())['files']['transit']['updatedAt'], '2026-10-03T17:30:00+08:00')
            self.assertEqual(json.loads(manifest.read_text())['files']['campus']['updatedAt'], 'keep')

    def test_calendar_expiration_rejects_future_publication(self):
        with self.assertRaises(m.InvalidData):
            m.build_base(fixtures(), CALENDAR, '2028-01-01', origin_frequency_ready=True)


if __name__ == '__main__':
    unittest.main()
