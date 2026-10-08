#!/usr/bin/env python3
"""TDX static data -> App schema v1. Credentials stay in process environment."""
import argparse
import copy
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DAY_KEYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
DAYS = ('MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN')
# Include only reviewed, direct services. Other discovered branches stay excluded.
ROUTES = {
    'BLUE1_LOCAL': ('HSZ0010', 'City/Hsinchu', '藍線1區', ('HSZ001001', 'HSZ0010A1', 'HSZ0010A2')),
    '2': ('HSZ0020', 'City/Hsinchu', '2', ('HSZ002001', 'HSZ002002')),
    '83': ('HSZ0008', 'City/Hsinchu', '83', ('HSZ000801', 'HSZ000802', 'HSZ0008B1', 'HSZ0008B2')),
    '182': ('HSZ0182', 'City/Hsinchu', '182', ('HSZ018201', 'HSZ018202')),
    'PIONEER': ('HSZ0185', 'City/Hsinchu', '先導公車', ('HSZ018501', 'HSZ018502', 'HSZ0185A1', 'HSZ0185A2')),
    '5608': ('THB5608', 'InterCity', '5608', ('THB560801', 'THB560802')),
    '2011': ('THB2011', 'InterCity', '2011', ('THB201101', 'THB201102')),
    '1822': ('THB1822', 'InterCity', '1822', ('THB182201', 'THB182202')),
    '9003': ('THB9003', 'InterCity', '9003', ('THB900301', 'THB900302')),
    '1728': ('THB1728', 'InterCity', '1728', ('THB172801', 'THB172802')),
}
# Reviewed Ho-Hsin branches whose official stop sequence includes Hsinchu.
# Optional branches may have no Schedule; F/B pairs are the required core service.
SOUTH_ROUTES = {
    '7500': ('THB7500', 'InterCity', '7500',
             ('THB750001', 'THB750002', 'THB7500D1', 'THB7500D2', 'THB7500F1', 'THB7500F2',
              'THB7500O1', 'THB7500O2', 'THB7500T1', 'THB7500T2')),
    '7513': ('THB7513', 'InterCity', '7513',
             ('THB751301', 'THB751302', 'THB7513B1', 'THB7513B2', 'THB7513D1', 'THB7513D2',
              'THB7513F1', 'THB7513F2', 'THB7513I1', 'THB7513I2')),
}
SOUTH_CORE = {'7500': {'THB7500F1', 'THB7500F2'}, '7513': {'THB7513B1', 'THB7513B2'}}
# IDs are permanent App selection keys; route-local mapping avoids conflating 5608's 新竹站.
SOUTH_STOPS = [
    ('HOHSIN_HSINCHU', '和欣客運新竹站', 'Ho-Hsin Hsinchu Station', 'CAMPUS'),
    ('XINYING', '新營站', 'Xinying Station', 'DESTINATION'),
    ('MADOU', '麻豆站轉運站', 'Madou Station', 'DESTINATION'),
    ('YONGKANG_HOHSIN', '永康轉運站', 'Yongkang Bus Station', 'DESTINATION'),
    ('LIUJIADING_HOHSIN', '六甲頂站', 'Liujiading Stop', 'DESTINATION'),
    ('TAINAN_HOHSIN', '臺南轉運站', 'Tainan Bus Station', 'DESTINATION'),
    ('NANZI', '楠梓站', 'Nanzi Station', 'DESTINATION'),
    ('JIURU_HOHSIN', '九如站', 'Jiuru Station', 'DESTINATION'),
    ('KAOHSIUNG_HOHSIN', '建國客運站', 'Kaohsiung Bus Terminal', 'DESTINATION'),
    ('ZHONGZHENG_HOHSIN', '中正站', 'Zhongzheng Station', 'DESTINATION'),
    ('LINGYA_SPORTS_PARK', '捷運苓雅運動園區站', 'MRT Lingya Sports Park Station', 'DESTINATION'),
]
SOUTH_ALIASES = {s[1]: s[0] for s in SOUTH_STOPS}
SOUTH_ALIASES['新竹站'] = 'HOHSIN_HSINCHU'
SOUTH_NON_DESTINATIONS = {'臺北轉運站', '三重站', '經國轉運站', '朝馬站'}
# Public IDs are owned by this project, never TDX StopUIDs.
STOP_DEFS = [
    ('NTHU_NORTH_GATE', '清華大學（光復路）', 'NTHU / Guangfu Road', 'CAMPUS'),
    ('NTHU_CAMPUS_NORTH_GATE', '清大北校門（校內83）', 'NTHU North Gate / Campus 83', 'CAMPUS'),
    ('NTHU_GENERAL_BUILDING_II', '第二綜合大樓', 'NTHU General Building II', 'CAMPUS'),
    ('NTHU_LIFE_SCIENCES', '生科館（人社院）', 'NTHU Life Sciences / Humanities', 'CAMPUS'),
    ('NTHU_TSMC_BUILDING', '台積館', 'NTHU TSMC Building', 'CAMPUS'),
    ('HSINCHU_TRA', '新竹火車站', 'Hsinchu Railway Station', 'DESTINATION'),
    ('HSINCHU_BUS_STATION', '新竹轉運站', 'Hsinchu Bus Station', 'DESTINATION'),
    ('HSINCHU_TRA_ZHONGZHENG', '新竹火車站（中正路）', 'Hsinchu Station / Zhongzheng Road', 'DESTINATION'),
    ('HSINCHU_BUS_DEPOT', '新竹站（5608）', 'Hsinchu Bus Depot / 5608', 'DESTINATION'),
    ('HSR_HSINCHU', '高鐵新竹站', 'THSR Hsinchu Station', 'DESTINATION'),
    ('TAIPEI_BUS_STATION', '台北轉運站', 'Taipei Bus Station', 'DESTINATION'),
    ('GONGGUAN', '捷運公館站', 'Gongguan MRT Station', 'DESTINATION'),
    ('NTU', '臺大', 'National Taiwan University', 'DESTINATION'),
    ('JINGMEI', '捷運景美站', 'Jingmei MRT Station', 'DESTINATION'),
    ('DAPINGLIN', '捷運大坪林站', 'Dapinglin MRT Station', 'DESTINATION'),
    ('XIAOBITAN', '中央新村（捷運小碧潭站）', 'Zhongyang New Village / Xiaobitan MRT', 'DESTINATION'),
    ('RENAI_DUNHUA', '仁愛敦化路口（圓環）', 'Renai / Dunhua Intersection', 'DESTINATION'),
]
ALIASES = {
    '清華大學': 'NTHU_NORTH_GATE', '火車站': 'HSINCHU_TRA',
    '新竹火車站(中正路)': 'HSINCHU_TRA_ZHONGZHENG', '中正路': 'HSINCHU_TRA_ZHONGZHENG',
    '新竹站': 'HSINCHU_BUS_DEPOT', '新竹轉運站': 'HSINCHU_BUS_STATION',
    '高鐵新竹站': 'HSR_HSINCHU', '臺北轉運站': 'TAIPEI_BUS_STATION',
    '捷運公館站': 'GONGGUAN', '臺大': 'NTU', '捷運景美站': 'JINGMEI',
    '捷運大坪林站': 'DAPINGLIN', '中央新村(捷運小碧潭站)': 'XIAOBITAN',
    '仁愛敦化路口(圓環)': 'RENAI_DUNHUA',
}
CAMPUS_83 = {'北校門': 'NTHU_CAMPUS_NORTH_GATE', '清大北校門': 'NTHU_CAMPUS_NORTH_GATE',
             '第二綜合大樓': 'NTHU_GENERAL_BUILDING_II', '生科館(人社院)': 'NTHU_LIFE_SCIENCES',
             '台積館': 'NTHU_TSMC_BUILDING'}


class InvalidData(ValueError):
    pass


def zh(value):
    return value.get('Zh_tw', '') if isinstance(value, dict) else str(value or '')


def day_list(service):
    if not isinstance(service, dict) or any(service.get(k) not in (0, 1) for k in DAY_KEYS):
        raise InvalidData('Missing or invalid ServiceDay flags')
    days = [d for k, d in zip(DAY_KEYS, DAYS) if service[k] == 1]
    if not days:
        raise InvalidData('Empty ServiceDay')
    return days


def minute(value):
    try:
        h, m = map(int, value.split(':'))
    except (ValueError, AttributeError):
        raise InvalidData('Invalid timetable time') from None
    if not (0 <= h <= 30 and 0 <= m < 60):
        raise InvalidData('Timetable time outside App range')
    return h * 60 + m


def clock(value):
    if not 0 <= value < 31 * 60:
        raise InvalidData('Midnight rollover exceeds App range')
    return f'{value // 60:02d}:{value % 60:02d}'


def stop_id(route_id, stop):
    name = zh(stop['StopName'])
    if route_id == '83':
        return CAMPUS_83.get(name) or ({'新竹轉運站': 'HSINCHU_BUS_STATION'}.get(name))
    return ALIASES.get(name)


def normalized_stop_times(trip):
    """Unwrap official ordered times; never calculate travel times."""
    result = {}
    previous = -1
    rollover = 0
    for stop in sorted(trip.get('StopTimes', []), key=lambda x: x['StopSequence']):
        raw = stop.get('DepartureTime') or stop.get('ArrivalTime')
        if not raw:
            continue
        value = minute(raw)
        if value < 1440:
            value += rollover
            if value < previous:
                # Only a clock crossing midnight is valid, not arbitrary backwards data.
                if previous % 1440 < 18 * 60 or value % 1440 > 6 * 60:
                    raise InvalidData('Non-monotonic official StopTimes')
                rollover += 1440
                value += 1440
        if value < previous:
            raise InvalidData('Non-monotonic official StopTimes')
        previous = value
        key = stop['StopSequence']
        if key in result:
            raise InvalidData('Duplicate StopTime sequence')
        result[key] = (stop, clock(value))
    if not result:
        raise InvalidData('Trip has no official times')
    return result


def segments(route_id, stops):
    stops = sorted(stops, key=lambda x: x['StopSequence'])
    if route_id == 'BLUE1_LOCAL' and zh(stops[0]['StopName']) == zh(stops[-1]['StopName']):
        turns = [i for i, s in enumerate(stops) if zh(s['StopName']) == '竹中']
        if len(turns) != 1:
            raise InvalidData('Unrecognized blue-line loop turnaround')
        i = turns[0]
        return [('OUT', stops[:i + 1]), ('BACK', stops[i:])]
    return [('DIRECT', stops)]


def build_base(raw, calendar, today, origin_frequency_ready=False, skip_2011=False):
    if not (calendar['coverageStart'] <= today <= calendar['coverageEnd']):
        raise InvalidData('Official holiday calendar needs renewal')
    output_routes = []
    for route_id, (uid, scope, expected_name, allowed_subs) in ROUTES.items():
        if route_id == '2011' and skip_2011:
            continue
        bundle = raw.get(uid)
        if not bundle or not bundle.get('stops') or not bundle.get('schedules'):
            raise InvalidData(f'Missing required route {route_id}')
        route = bundle['route']
        if route.get('RouteUID') != uid or zh(route.get('RouteName')) != expected_name:
            raise InvalidData(f'Route identity changed: {route_id}')
        stop_rows = {}
        for row in bundle['stops']:
            operator_ids = [str(o['OperatorID']) for o in row.get('Operators', [])] or [str(row.get('OperatorID', ''))]
            for operator_id in operator_ids:
                key = (row['SubRouteUID'], row['Direction'], operator_id)
                if key in stop_rows and stop_rows[key]['Stops'] != row['Stops']:
                    raise InvalidData('Conflicting stop sequences for one operator')
                stop_rows[key] = row
        directions = []
        seen_subs = set()
        seen_services = set()
        for schedule in sorted(bundle['schedules'], key=lambda x: (x['SubRouteUID'], str(x.get('OperatorID', '')))):
            sub = schedule['SubRouteUID']
            if sub not in allowed_subs:
                continue
            op = str(schedule.get('OperatorID', ''))
            row = stop_rows.get((sub, schedule['Direction'], op))
            if row is None:
                matches = [v for (s, d, _), v in stop_rows.items() if s == sub and d == schedule['Direction']]
                if len(matches) != 1:
                    raise InvalidData(f'Missing or ambiguous stop sequence: {sub}')
                row = matches[0]
            full_stops = sorted(row['Stops'], key=lambda x: x['StopSequence'])
            if not full_stops or len({x['StopSequence'] for x in full_stops}) != len(full_stops):
                raise InvalidData(f'Invalid stops: {sub}')
            trips = schedule.get('Timetables', [])
            frequencies = schedule.get('Frequencys', [])
            if not trips and not frequencies:
                raise InvalidData(f'Empty schedule: {sub}')
            if route_id == '2011' and not frequencies:
                raise InvalidData('2011 daytime frequency data is missing; review before changing service kind')
            seen_subs.add(sub)
            seen_services.add((sub, op))
            for segment, subset in segments(route_id, full_stops):
                selected = [(s['StopSequence'], stop_id(route_id, s)) for s in subset if stop_id(route_id, s)]
                ids = [sid for _, sid in selected]
                if len(ids) != len(set(ids)):
                    raise InvalidData(f'Ambiguous repeated public stop: {sub}')
                if not any(s.startswith('NTHU_') for s in ids) or not any(not s.startswith('NTHU_') for s in ids):
                    raise InvalidData(f'Required branch no longer serves campus and destination: {sub}')
                prefix = f'{route_id}_{allowed_subs.index(sub)}_{op}_{segment}'
                times_trips, origin_trips = [], []
                for trip in trips:
                    days = day_list(trip.get('ServiceDay'))
                    official = normalized_stop_times(trip)
                    mapped = {sid: official[seq][1] for seq, sid in selected if seq in official}
                    for seq, sid in selected:
                        if seq in official and official[seq][0].get('StopUID') != next(s['StopUID'] for s in subset if s['StopSequence'] == seq):
                            raise InvalidData(f'StopTime identity mismatch: {sub}')
                    if any(s.startswith('NTHU_') for s in mapped):
                        times_trips.append({'days': days, 'times': mapped})
                    elif len(official) == 1 and min(official) == full_stops[0]['StopSequence']:
                        origin_trips.append({'days': days, 'origin': next(iter(official.values()))[1]})
                    else:
                        raise InvalidData(f'Trip missing campus time without origin-only semantics: {sub}')
                origin_name = zh(full_stops[0]['StopName'])
                origin_en = full_stops[0]['StopName'].get('En', origin_name)
                if times_trips:
                    directions.append({'id': prefix + '_TIMES', 'stops': ids, 'timeKind': 'STOP_TIME',
                                       'trips': sorted_unique(times_trips)})
                if origin_trips:
                    directions.append({'id': prefix + '_ORIGIN', 'stops': ids, 'timeKind': 'ORIGIN_DEPARTURE_ONLY',
                                       'originZh': origin_name, 'originEn': origin_en, 'trips': sorted_unique(origin_trips)})
                if frequencies:
                    if segment != 'DIRECT':
                        raise InvalidData('Cannot attach origin frequencies to a loop segment')
                    if not origin_frequency_ready:
                        raise InvalidData('2011 origin frequency needs App origin label; use preview or explicitly skip 2011')
                    values = []
                    for f in frequencies:
                        start, end = minute(f['StartTime']), minute(f['EndTime'])
                        if end < start:
                            end += 1440
                        low, high = f['MinHeadwayMins'], f['MaxHeadwayMins']
                        if not isinstance(low, int) or not isinstance(high, int) or not 0 < low <= high:
                            raise InvalidData('Invalid headway')
                        values.append({'days': day_list(f.get('ServiceDay')), 'start': clock(start), 'end': clock(end),
                                       'minHeadway': low, 'maxHeadway': high})
                    directions.append({'id': prefix + '_FREQUENCY', 'stops': ids, 'timeKind': 'FREQUENCY',
                                       'originZh': origin_name, 'originEn': origin_en, 'frequencies': sorted_unique(values)})
        if seen_subs != set(allowed_subs):
            raise InvalidData(f'Missing required branch: {route_id}')
        expected_services = {(s['SubRouteUID'], str(o)) for s in route.get('SubRoutes', [])
                             if s['SubRouteUID'] in allowed_subs for o in s.get('OperatorIDs', [])}
        if not expected_services or seen_services != expected_services:
            raise InvalidData(f'Missing operator service: {route_id}')
        operators = route.get('Operators', [])
        if not operators:
            raise InvalidData(f'Missing operator: {route_id}')
        output_routes.append({'id': route_id, 'number': expected_name, 'zh': expected_name,
                              'en': route.get('RouteName', {}).get('En', expected_name),
                              'operatorZh': '／'.join(sorted({zh(o['OperatorName']) for o in operators})),
                              'operatorEn': ' / '.join(sorted({o['OperatorName'].get('En', zh(o['OperatorName'])) for o in operators})),
                              'directions': sorted(directions, key=lambda d: d['id'])})
    taipei_routes = ['2011', '1822', '9003'] if not skip_2011 else ['1822', '9003']
    result = {'schemaVersion': 1, 'updatedAt': today, 'holidays': sorted(set(calendar['holidays'])),
              'holidayServiceAs': 'SUNDAY',
              'stops': [dict(zip(('id', 'zh', 'en', 'side'), s)) for s in STOP_DEFS],
              'groups': [
                  {'id': 'TRA', 'zh': '台鐵', 'en': 'TRA', 'sections': [
                      {'id': 'TRA', 'zh': '新竹火車站／轉運站', 'en': 'Hsinchu Station Area',
                       'destinationStops': ['HSINCHU_TRA', 'HSINCHU_BUS_STATION', 'HSINCHU_TRA_ZHONGZHENG', 'HSINCHU_BUS_DEPOT'],
                       'routes': ['BLUE1_LOCAL', '2', '83', '182', '5608', 'PIONEER']}]},
                  {'id': 'HSR', 'zh': '高鐵', 'en': 'THSR', 'sections': [
                      {'id': 'HSR', 'zh': '高鐵新竹站', 'en': 'THSR Hsinchu', 'destinationStops': ['HSR_HSINCHU'], 'routes': ['182', 'PIONEER']}]},
                  {'id': 'TAIPEI', 'zh': '台北', 'en': 'Taipei', 'sections': [
                      {'id': 'TAIPEI_TERMINAL', 'zh': '台北轉運站', 'en': 'Taipei Bus Station', 'destinationStops': ['TAIPEI_BUS_STATION'], 'routes': taipei_routes},
                      {'id': 'TAIPEI_SOUTH', 'zh': '公館／臺大／景美／新店／東區', 'en': 'Gongguan / NTU / Xindian',
                       'destinationStops': ['GONGGUAN', 'NTU', 'JINGMEI', 'DAPINGLIN', 'XIAOBITAN', 'RENAI_DUNHUA'], 'routes': ['1728']}]}],
              'routes': sorted(output_routes, key=lambda r: r['id'])}
    return result


def sorted_unique(values):
    return sorted({json.dumps(v, ensure_ascii=False, sort_keys=True): v for v in values}.values(),
                  key=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True))


def service_exceptions(trip):
    """Keep official date overrides, independent of service weekday and midnight."""
    source = trip.get('SpecialDays', [])
    if not isinstance(source, list):
        raise InvalidData('Invalid SpecialDays array')
    intervals = []

    def date(value):
        try:
            parsed = dt.date.fromisoformat(value)
        except (TypeError, ValueError):
            raise InvalidData('Invalid SpecialDays date') from None
        if parsed.isoformat() != value:
            raise InvalidData('SpecialDays date must be YYYY-MM-DD')
        return parsed

    for entry in source:
        if not isinstance(entry, dict):
            raise InvalidData('Invalid SpecialDays entry')
        # Live Ho-Hsin data has status 0 (not operating). Do not infer unreviewed
        # status meanings from Description or silently discard new statuses.
        if type(entry.get('ServiceStatus')) is not int or entry['ServiceStatus'] != 0:
            raise InvalidData('Unreviewed SpecialDays ServiceStatus; official mapping needs review')
        if not any(k in entry for k in ('Dates', 'DatePeriod')):
            raise InvalidData('SpecialDays has no dates')
        if 'Dates' in entry:
            if not isinstance(entry['Dates'], list) or not entry['Dates']:
                raise InvalidData('Invalid SpecialDays Dates')
            intervals.extend((date(d), date(d), False) for d in entry['Dates'])
        if 'DatePeriod' in entry:
            period = entry['DatePeriod']
            if not isinstance(period, dict):
                raise InvalidData('Invalid SpecialDays DatePeriod')
            start, end = date(period.get('StartDate')), date(period.get('EndDate'))
            if start > end:
                raise InvalidData('Reversed SpecialDays DatePeriod')
            intervals.append((start, end, False))
    merged = []
    for start, end, runs in sorted(set(intervals)):
        if merged and start <= merged[-1][1] + dt.timedelta(days=1):
            if runs != merged[-1][2]:
                raise InvalidData('Conflicting SpecialDays intervals')
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]), runs)
        else:
            merged.append((start, end, runs))
    return [{'startDate': start.isoformat(), 'endDate': end.isoformat(), 'runs': runs}
            for start, end, runs in merged]


def south_routes(raw):
    """Only reviewed Ho-Hsin Hsinchu branches/trips; no travel-time estimates."""
    output, used_stops = [], set()
    for rid, (uid, _, name, allowed) in SOUTH_ROUTES.items():
        bundle = raw.get(uid)
        if not bundle or not bundle.get('stops') or not bundle.get('schedules'):
            raise InvalidData(f'Missing required south route {rid}')
        route = bundle['route']
        operators = route.get('Operators', [])
        if (route.get('RouteUID') != uid or zh(route.get('RouteName')) != name or
                len(operators) != 1 or str(operators[0].get('OperatorID')) != '25' or
                operators[0].get('OperatorCode') != 'HoHsinBus' or
                zh(operators[0].get('OperatorName')) != '和欣客運'):
            raise InvalidData(f'South route/operator identity changed: {rid}')
        metadata = {(s['SubRouteUID'], s['Direction']): s for s in route.get('SubRoutes', [])}
        rows = {}
        for row in bundle['stops']:
            key = (row['SubRouteUID'], row['Direction'])
            if key in rows and rows[key]['Stops'] != row['Stops']:
                raise InvalidData(f'Conflicting south stop sequences: {rid}')
            rows[key] = row
        directions, seen_services, seen_core = [], set(), set()
        for schedule in sorted(bundle['schedules'], key=lambda s: (s['SubRouteUID'], s['Direction'])):
            sub, direction = schedule['SubRouteUID'], schedule['Direction']
            key = (sub, direction)
            row = rows.get(key)
            if row is None:
                raise InvalidData(f'Missing south stop sequence: {sub}')
            stops = sorted(row['Stops'], key=lambda s: s['StopSequence'])
            hsinchu = [s for s in stops if zh(s['StopName']) == '新竹站']
            if not hsinchu:
                continue  # Explicitly exclude all branches bypassing Hsinchu.
            if sub not in allowed:
                raise InvalidData(f'Unreviewed south Hsinchu branch: {sub}')
            if (str(schedule.get('OperatorID')) != '25' or key not in metadata or
                    {str(o) for o in metadata[key].get('OperatorIDs', [])} != {'25'} or
                    {str(o['OperatorID']) for o in row.get('Operators', [])} != {'25'}):
                raise InvalidData(f'South operator/branch mismatch: {sub}')
            if key in seen_services:
                raise InvalidData(f'Duplicate south schedule: {sub}')
            seen_services.add(key)
            if len(hsinchu) != 1 or len({s['StopSequence'] for s in stops}) != len(stops):
                raise InvalidData(f'Ambiguous south stop sequence: {sub}')
            if any(zh(s['StopName']) not in SOUTH_ALIASES and zh(s['StopName']) not in SOUTH_NON_DESTINATIONS for s in stops):
                raise InvalidData(f'Unreviewed south stop: {sub}')
            selected = [(s['StopSequence'], SOUTH_ALIASES[zh(s['StopName'])])
                        for s in stops if zh(s['StopName']) in SOUTH_ALIASES]
            ids = [sid for _, sid in selected]
            if len(ids) < 2 or len(set(ids)) != len(ids) or ids.index('HOHSIN_HSINCHU') not in (0, len(ids) - 1):
                raise InvalidData(f'Invalid south public stop order: {sub}')
            trips = schedule.get('Timetables', [])
            if not trips or schedule.get('Frequencys'):
                raise InvalidData(f'Missing or unreviewed south timetable: {sub}')
            times_trips, origin_trips = [], []
            lookup = {s['StopSequence']: s for s in stops}
            for trip in trips:
                days = day_list(trip.get('ServiceDay'))
                exceptions = service_exceptions(trip)
                official = normalized_stop_times(trip)
                for seq, (timed_stop, _) in official.items():
                    if seq not in lookup or timed_stop.get('StopUID') != lookup[seq].get('StopUID'):
                        raise InvalidData(f'South StopTime identity mismatch: {sub}')
                mapped = {sid: official[seq][1] for seq, sid in selected if seq in official}
                if 'HOHSIN_HSINCHU' in mapped:
                    # A partially timed destination cannot be advertised as served.
                    if set(mapped) != set(ids):
                        raise InvalidData(f'Partial south destination times need review: {sub}')
                    converted = {'days': days, 'times': mapped}
                    target = times_trips
                elif len(official) == 1 and min(official) == stops[0]['StopSequence']:
                    converted = {'days': days, 'origin': next(iter(official.values()))[1]}
                    target = origin_trips
                elif sub in ('THB750001', 'THB750002'):
                    # Audited partial trips terminate before Hsinchu; not proof of
                    # a boardable Hsinchu trip and not origin-only schedules.
                    continue
                else:
                    raise InvalidData(f'South trip lacks Hsinchu time or origin-only semantics: {sub}')
                if exceptions:
                    converted['serviceExceptions'] = exceptions
                target.append(converted)
            prefix = f'{rid}_{sub}_25'
            if times_trips:
                directions.append({'id': prefix + '_TIMES', 'stops': ids, 'timeKind': 'STOP_TIME',
                                   'trips': sorted_unique(times_trips)})
            if origin_trips:
                origin_name = stops[0]['StopName']
                directions.append({'id': prefix + '_ORIGIN', 'stops': ids, 'timeKind': 'ORIGIN_DEPARTURE_ONLY',
                                   'originZh': zh(origin_name), 'originEn': origin_name.get('En', zh(origin_name)),
                                   'trips': sorted_unique(origin_trips)})
            if times_trips or origin_trips:
                seen_core.add(sub)
                used_stops.update(ids)
        if not SOUTH_CORE[rid] <= seen_core:
            raise InvalidData(f'Missing required south core branch: {rid}')
        if {d['stops'][0] == 'HOHSIN_HSINCHU' for d in directions} != {True, False}:
            raise InvalidData(f'South route missing one travel direction: {rid}')
        output.append({'id': rid, 'number': name, 'zh': name, 'en': name,
                       'operatorZh': zh(operators[0]['OperatorName']),
                       'operatorEn': operators[0]['OperatorName'].get('En', zh(operators[0]['OperatorName'])),
                       'directions': sorted(directions, key=lambda d: d['id'])})
    return output, used_stops


def build(raw, calendar, today, origin_frequency_ready=False, skip_2011=False):
    result = build_base(raw, calendar, today, origin_frequency_ready, skip_2011)
    routes, used = south_routes(raw)
    result['routes'] = sorted(result['routes'] + routes, key=lambda r: r['id'])
    result['stops'].extend(dict(zip(('id', 'zh', 'en', 'side'), s)) for s in SOUTH_STOPS if s[0] in used)
    result['groups'].append({'id': 'SOUTH', 'zh': '南部', 'en': 'South', 'sections': [
        {'id': 'SOUTH_HOHSIN', 'zh': '台南／高雄', 'en': 'Tainan / Kaohsiung',
         'destinationStops': [s[0] for s in SOUTH_STOPS if s[0] in used and s[3] == 'DESTINATION'],
         'routes': ['7500', '7513']}]})
    return result


class TDX:
    def __init__(self):
        self.last_request = 0
        client_id, secret = os.environ.get('TDX_CLIENT_ID'), os.environ.get('TDX_CLIENT_SECRET')
        if not client_id or not secret:
            raise InvalidData('TDX environment variables are missing')
        body = urllib.parse.urlencode({'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': secret}).encode()
        request = urllib.request.Request('https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token',
                                         data=body, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                self.token = json.load(response)['access_token']
        except Exception:
            raise InvalidData('TDX authentication failed; credentials were not logged') from None

    def get(self, endpoint, query):
        url = 'https://tdx.transportdata.tw/api/basic/v2/Bus/' + endpoint + '?' + urllib.parse.urlencode({'$filter': query, '$format': 'JSON'})
        for attempt in range(4):
            time.sleep(max(0, 15 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + self.token})
                with urllib.request.urlopen(request, timeout=45) as response:
                    result = json.load(response)
                if not isinstance(result, list) or not result:
                    raise InvalidData(f'TDX returned empty/invalid {endpoint}')
                return result
            except urllib.error.HTTPError as error:
                if error.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(45)
                    continue
                raise InvalidData(f'TDX {endpoint} HTTP {error.code}') from None
            except (OSError, ValueError):
                if attempt < 3:
                    time.sleep(15)
                    continue
                raise InvalidData(f'TDX {endpoint} failed') from None
        raise InvalidData('TDX retries exhausted')


def collect(client, skip_2011=False):
    bundles = {}
    for scope in ('City/Hsinchu', 'InterCity'):
        definitions = [v for k, v in {**ROUTES, **SOUTH_ROUTES}.items()
                       if v[1] == scope and not (skip_2011 and k == '2011')]
        route_filter = ' or '.join("RouteUID eq '" + v[0] + "'" for v in definitions)
        routes = client.get('Route/' + scope, route_filter)
        stops = client.get('StopOfRoute/' + scope, route_filter)
        schedules = client.get('Schedule/' + scope, route_filter)
        for route in routes:
            uid = route['RouteUID']
            bundles[uid] = {'route': route, 'scope': scope,
                            'stops': [s for s in stops if s['RouteUID'] == uid],
                            'schedules': [s for s in schedules if s['RouteUID'] == uid]}
    return bundles


def semantic(value):
    value = copy.deepcopy(value)
    value.pop('updatedAt', None)
    return value


def publish(candidate, root, stamp):
    transit_path = root / 'docs/v1/transit.json'
    manifest_path = root / 'docs/v1/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    files = manifest.get('files')
    if not isinstance(files, dict):
        raise InvalidData('Invalid existing manifest')
    old = json.loads(transit_path.read_text(encoding='utf-8')) if transit_path.exists() else None
    content_changed = old is None or semantic(old) != semantic(candidate)
    if not content_changed:
        candidate = old
    entry = {'path': 'transit.json', 'updatedAt': stamp if content_changed else candidate['updatedAt']}
    if (not content_changed and files.get('transit', {}).get('path') == 'transit.json'
            and files.get('transit', {}).get('updatedAt')):
        print('No substantive change; files and timestamps unchanged.')
        return False
    files['transit'] = entry
    manifest['updatedAt'] = stamp
    # Both payloads validated/serialized before either file is replaced. Git commit is atomic publication.
    transit_text = json.dumps(candidate, ensure_ascii=False, indent=2) + '\n'
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    if content_changed:
        staged = transit_path.with_suffix('.json.tmp')
        staged.write_text(transit_text, encoding='utf-8')
        staged.replace(transit_path)
    staged = manifest_path.with_suffix('.json.tmp')
    staged.write_text(manifest_text, encoding='utf-8')
    staged.replace(manifest_path)
    print('Validated transit and manifest updated locally.')
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, help='Offline, credential-free audit fixture')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--preview', type=Path, help='Review candidate only; does not publish')
    parser.add_argument('--origin-frequency-ready', action='store_true')
    parser.add_argument('--skip-2011', action='store_true')
    args = parser.parse_args()
    if not args.preview and not args.origin_frequency_ready and not args.skip_2011:
        raise InvalidData('Confirm App origin-frequency labeling or explicitly defer 2011 before publication')
    now = dt.datetime.now(ZoneInfo('Asia/Taipei'))
    calendar = json.loads((args.root / 'scripts/transit-holidays.json').read_text(encoding='utf-8'))
    raw = json.loads(args.input.read_text(encoding='utf-8')) if args.input else collect(TDX(), args.skip_2011)
    candidate = build(raw, calendar, now.date().isoformat(), args.origin_frequency_ready or bool(args.preview), args.skip_2011)
    if args.preview:
        args.preview.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Validated review candidate created; repository data files unchanged.')
    else:
        publish(candidate, args.root, now.isoformat(timespec='seconds'))


if __name__ == '__main__':
    try:
        main()
    except InvalidData as error:
        print('Sync rejected: ' + str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Sync failed; no source response or credentials were logged.', file=sys.stderr)
        sys.exit(1)
