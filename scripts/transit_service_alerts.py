#!/usr/bin/env python3
"""Official service-disruption monitor -> docs/v1/transit-alerts.json.

Sources, in order of authority:
  1. TDX Bus Alert (營運通阻) for InterCity and Hsinchu City: the only source that can
     mark a route SUSPENDED / PARTIAL_SUSPENSION / SERVICE_ALERT / NORMAL.
  2. DGPA nationwide work/school closure page: risk hint only (UNCONFIRMED). A city
     closure never cancels a bus by itself.
Absence of alerts means "no disruption found", never "officially normal". A failed
source keeps its previous unexpired entries and is reported as UNAVAILABLE.
"""
import argparse
import copy
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_transit as st  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ALERTS_PATH = 'docs/v1/transit-alerts.json'
TAIPEI = ZoneInfo('Asia/Taipei')
TDX_SOURCES = {
    'TDX_BUS_ALERT_INTERCITY': ('Alert/InterCity', 'THB',
                                'https://tdx.transportdata.tw/api/basic/v2/Bus/Alert/InterCity'),
    'TDX_BUS_ALERT_HSINCHU': ('Alert/City/Hsinchu', 'HSZ',
                              'https://tdx.transportdata.tw/api/basic/v2/Bus/Alert/City/Hsinchu'),
}
DGPA_ID = 'DGPA_CLOSURES'
DGPA_URL = 'https://www.dgpa.gov.tw/typh/daily/nds.html'
# #城市 //每條路線會經過哪些縣市：所有路線都從新竹市（清大）出發；目的地分頁再加上終點那一端。
GROUP_CITIES = {'TRA': {'新竹市'}, 'HSR': {'新竹市', '新竹縣'}, 'TAIPEI': {'新竹市', '臺北市', '新北市'},
                'SOUTH': {'新竹市', '臺南市', '高雄市'}, 'CENTRAL': {'新竹市', '臺中市'}}
CITY_EN = {'新竹市': 'Hsinchu City', '新竹縣': 'Hsinchu County', '臺北市': 'Taipei City', '新北市': 'New Taipei City',
           '臺南市': 'Tainan City', '高雄市': 'Kaohsiung City', '臺中市': 'Taichung City'}
# An alert without EndTime may not keep a route "suspended" beyond this.
OPEN_ENDED_HOURS = 24
VALID_HOURS = 30          # App treats the file as stale after validUntil.
HEARTBEAT_HOURS = 12      # Rewrite (and redeploy) at most this often when nothing changed.
STATE_RANK = {'SUSPENDED': 5, 'PARTIAL_SUSPENSION': 4, 'SERVICE_ALERT': 3, 'NORMAL': 2, 'UNCONFIRMED': 1}
WHOLE_DIRECTIONS = {None, 2, 10, 255}


def zh(value):
    return st.zh(value)


def parse_time(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=TAIPEI)


def iso(value):
    return value.astimezone(TAIPEI).isoformat(timespec='seconds') if value else None


# #路線清單 //從目前發布的 transit.json 取路線、業者、分頁；TDX 代號沿用同步程式的白名單。
def route_catalog(transit):
    defs = st.all_route_defs()
    groups = {}
    for group in transit.get('groups', []):
        for section in group.get('sections', []):
            for rid in section.get('routes', []):
                groups.setdefault(rid, set()).add(group['id'])
    catalog = {}
    for route in transit.get('routes', []):
        rid = route['id']
        if rid not in defs:
            continue
        uid, _, number, subs = defs[rid]
        cities = set().union(*(GROUP_CITIES.get(g, {'新竹市'}) for g in groups.get(rid, {'TRA'})))
        catalog[rid] = {'uid': uid, 'prefix': uid[:3], 'number': number, 'subs': set(subs),
                        'operators': {x for x in route.get('operatorZh', '').split('／') if x},
                        'cities': cities}
    return catalog


def route_id_matches(info, route_id, name):
    short = info['uid'][3:]
    return (route_id in (info['uid'], short, short.lstrip('0'))) or (name and name == info['number'])


def match_scope(alert, prefix, catalog):
    """Map one TDX alert scope onto our routes: rid -> {'whole': bool, 'directions', 'trips'}."""
    scope = alert.get('Scope') or {}
    routes = {rid: info for rid, info in catalog.items() if info['prefix'] == prefix}
    hits = {}

    def hit(rid, whole, direction=None, trip=None):
        entry = hits.setdefault(rid, {'whole': False, 'directions': set(), 'trips': []})
        if whole and direction in WHOLE_DIRECTIONS:
            entry['whole'] = True
        elif direction not in WHOLE_DIRECTIONS:
            entry['directions'].add(direction)
        if trip:
            entry['trips'].append(trip)

    for r in scope.get('Routes') or []:
        for rid, info in routes.items():
            if route_id_matches(info, str(r.get('RouteID') or ''), zh(r.get('RouteName'))):
                hit(rid, True, r.get('Direction'))
    for r in scope.get('SubRoutes') or []:
        sub_id = str(r.get('SubRouteID') or '')
        for rid, info in routes.items():
            if (sub_id in info['subs'] or info['prefix'] + sub_id in info['subs']
                    or zh(r.get('SubRouteName')) == info['number']):
                hit(rid, False, r.get('Direction'))
    for r in scope.get('Trips') or []:
        for rid, info in routes.items():
            if route_id_matches(info, str(r.get('RouteID') or ''), None):
                hit(rid, False, r.get('Direction'),
                    {'direction': r.get('Direction'), 'departure': r.get('TripDepTime')})
    if not hits and not any(scope.get(k) for k in ('Routes', 'SubRoutes', 'Trips', 'Stops', 'Stations')):
        named = {zh(o.get('OperatorName')) for o in scope.get('Operators') or []}
        for rid, info in routes.items():
            if info['operators'] & named:
                # Joint routes stay partial when only one of their operators is named.
                hit(rid, info['operators'] <= named)
    return hits


def alert_state(alert, scope_hit):
    status, effect = alert.get('Status'), alert.get('Effect')
    conflict = (status == 0 and effect == 2) or (status == 1 and effect in (3, 4))
    if conflict:
        return 'SERVICE_ALERT', True
    whole = scope_hit['whole'] and not scope_hit['trips']
    if status == 0 or effect == 4:
        return ('SUSPENDED' if whole else 'PARTIAL_SUSPENSION'), False
    if status == 1 and effect in (None, 254, 255):
        return 'NORMAL', False
    return 'SERVICE_ALERT', False


def convert_alerts(source_id, prefix, rows, catalog, now, first_seen):
    result = []
    for row in rows:
        alert_id = str(row.get('AlertID') or '')
        if not alert_id:
            continue
        publish, start, end = (parse_time(row.get(k)) for k in ('PublishTime', 'StartTime', 'EndTime'))
        if end and end < now:
            continue  # Officially ended.
        begin = start or publish or now
        expires = end or begin + dt.timedelta(hours=OPEN_ENDED_HOURS)
        hits = match_scope(row, prefix, catalog)
        if not hits:
            continue
        key = f'{source_id}:{alert_id}'
        routes, conflict = {}, False
        for rid, h in sorted(hits.items()):
            state, bad = alert_state(row, h)
            conflict = conflict or bad
            if state == 'SUSPENDED' and not end and now > expires:
                state = 'SERVICE_ALERT'  # Open-ended suspension may not stay in force indefinitely.
            entry = {'state': state}
            if h['directions']:
                entry['directions'] = sorted(h['directions'])
            if h['trips']:
                entry['trips'] = sorted(h['trips'], key=lambda t: (t['direction'] or 0, t['departure'] or ''))
            routes[rid] = entry
        alert = {'id': key, 'sourceId': source_id, 'alertId': alert_id,
                 'title': row.get('Title') or '', 'description': row.get('Description') or '',
                 'department': row.get('Department') or '', 'status': row.get('Status'),
                 'cause': row.get('Cause'), 'effect': row.get('Effect'),
                 'url': row.get('AlertURL') or TDX_SOURCES[source_id][2],
                 'publishTime': iso(publish), 'startTime': iso(begin), 'endTime': iso(end),
                 'expiresAt': iso(expires), 'firstSeenAt': first_seen.get(key) or iso(now),
                 'sourceUpdateTime': row.get('SrcUpdateTime') or row.get('UpdateTime'),
                 'routes': routes}
        if conflict:
            alert['conflict'] = True
        result.append(alert)
    return result


# #停班停課 //只認「整個縣市」的宣布；某鄉某校的局部停課（前面帶「XX：」）不算。
def dgpa_closures(page):
    text = page
    ymd = re.search(r'Header_YMD">\s*(\d+)年\s*(\d+)月\s*(\d+)日', text)
    if not ymd:
        raise ValueError('DGPA page date not found')
    page_date = dt.date(int(ymd.group(1)) + 1911, int(ymd.group(2)), int(ymd.group(3)))
    updated = re.search(r'更新時間：\s*(\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}):(\d{2})', text)
    updated_at = (dt.datetime(*map(int, updated.groups()), tzinfo=TAIPEI) if updated else None)
    closures = {}
    if '無停班停課訊息' in text:
        return page_date, updated_at, closures
    rows = re.findall(r'headers="city_Name[^"]*">\s*<FONT>([^<]+)</FONT>\s*</TD>\s*<TD[^>]*>(.*?)</TD>',
                      text, flags=re.S | re.I)
    if not rows:
        raise ValueError('DGPA table layout not recognized')
    for city, cell in rows:
        city = city.strip()
        for segment in re.split(r'<br\s*/?>', cell, flags=re.I):
            words = html.unescape(re.sub(r'<[^>]+>', '', segment)).strip()
            if not words or re.match(r'^[^：:]{1,40}[：:]', words):
                continue  # Empty, or a named district/school only.
            if '停止上班' not in words and '停止上課' not in words:
                continue
            for word, offset in (('今天', 0), ('今日', 0), ('明天', 1), ('明日', 1)):
                if words.startswith(word):
                    closures.setdefault(city, set()).add(page_date + dt.timedelta(days=offset))
    return page_date, updated_at, closures


def covers(entry, day):
    start = parse_time(entry['startTime']).astimezone(TAIPEI).date()
    end = parse_time(entry.get('endTime') or entry['expiresAt']).astimezone(TAIPEI).date()
    return start <= day <= end


def summarize(alerts, hints, catalog):
    routes = {}
    for alert in alerts:
        for rid, entry in alert['routes'].items():
            item = {'state': entry['state'], 'startTime': alert['startTime'], 'endTime': alert['endTime'],
                    'expiresAt': alert['expiresAt'], 'alertIds': [alert['id']]}
            for k in ('directions', 'trips'):
                if k in entry:
                    item[k] = entry[k]
            routes.setdefault(rid, []).append(item)
    for hint in hints:
        day = dt.date.fromisoformat(hint['date'])
        for rid, info in sorted(catalog.items()):
            cities = sorted(info['cities'] & set(hint['cities']))
            if not cities:
                continue
            if any(covers(e, day) for e in routes.get(rid, []) if e['state'] != 'UNCONFIRMED'):
                continue  # An official alert for that day takes precedence over a closure hint.
            routes.setdefault(rid, []).append({
                'state': 'UNCONFIRMED', 'date': hint['date'], 'cities': cities,
                'noteZh': '、'.join(cities) + '已宣布停止上班或上課，客運業者尚未公告是否停駛；以下為原定班表，搭車前請向業者確認。',
                'noteEn': 'Work/school closure announced in ' + ', '.join(CITY_EN.get(c, c) for c in cities) +
                          '; the operator has not announced suspensions. Scheduled times shown; confirm before travelling.',
                'sourceUrl': DGPA_URL})
    for rid in routes:
        routes[rid].sort(key=lambda e: (-STATE_RANK[e['state']], e.get('startTime') or e.get('date')))
    return dict(sorted(routes.items()))


def content(doc):
    value = copy.deepcopy(doc)
    for k in ('updatedAt', 'lastCheckedAt', 'validUntil'):
        value.pop(k, None)
    for source in value.get('sources', []):
        source.pop('lastSuccessAt', None)
    return value


def build_document(previous, fetched, dgpa_page, catalog, now):
    """fetched: source id -> list of TDX rows, or None when that request failed."""
    previous = previous or {}
    old_sources = {s['id']: s for s in previous.get('sources', [])}
    first_seen = {a['id']: a['firstSeenAt'] for a in previous.get('alerts', [])}
    alerts, sources = [], []
    for source_id, (_, prefix, url) in TDX_SOURCES.items():
        rows = fetched.get(source_id)
        old = old_sources.get(source_id, {})
        if rows is None:
            keep = [a for a in previous.get('alerts', []) if a['sourceId'] == source_id
                    and parse_time(a['expiresAt']) > now]
            alerts.extend(keep)
            sources.append({'id': source_id, 'url': url, 'state': 'UNAVAILABLE', 'lastSuccessAt': old.get('lastSuccessAt')})
        else:
            alerts.extend(convert_alerts(source_id, prefix, rows, catalog, now, first_seen))
            sources.append({'id': source_id, 'url': url, 'state': 'OK', 'lastSuccessAt': iso(now)})
    today = now.astimezone(TAIPEI).date()
    hints = []
    old_dgpa = old_sources.get(DGPA_ID, {})
    try:
        if dgpa_page is None:
            raise ValueError('DGPA unavailable')
        _, page_updated, closures = dgpa_closures(dgpa_page)
        by_day = {}
        for city, days in closures.items():
            for day in days:
                if day >= today:
                    by_day.setdefault(day, set()).add(city)
        hints = [{'date': d.isoformat(), 'cities': sorted(c), 'pageUpdatedAt': iso(page_updated)}
                 for d, c in sorted(by_day.items())]
        sources.append({'id': DGPA_ID, 'url': DGPA_URL, 'state': 'OK', 'lastSuccessAt': iso(now)})
    except ValueError:
        hints = [h for h in previous.get('closureHints', []) if dt.date.fromisoformat(h['date']) >= today]
        sources.append({'id': DGPA_ID, 'url': DGPA_URL, 'state': 'UNAVAILABLE', 'lastSuccessAt': old_dgpa.get('lastSuccessAt')})
    alerts.sort(key=lambda a: a['id'])
    tdx_success = [parse_time(s['lastSuccessAt']) for s in sources if s['id'] in TDX_SOURCES and s['lastSuccessAt']]
    valid_until = min(tdx_success) + dt.timedelta(hours=VALID_HOURS) if len(tdx_success) == len(TDX_SOURCES) else None
    return {'schemaVersion': 1, 'updatedAt': previous.get('updatedAt'), 'lastCheckedAt': iso(now),
            'validUntil': iso(valid_until), 'sources': sources, 'alerts': alerts,
            'closureHints': hints, 'routes': summarize(alerts, hints, catalog)}


def should_write(previous, doc, now):
    if not previous:
        return True, True
    changed = content(previous) != content(doc)
    valid = parse_time(previous.get('validUntil'))
    heartbeat = (doc.get('validUntil') is not None and
                 (valid is None or valid - now < dt.timedelta(hours=VALID_HOURS - HEARTBEAT_HOURS)))
    return changed or heartbeat, changed


def publish(root, doc, previous, now):
    write, changed = should_write(previous, doc, now)
    if not write:
        print('No alert change and heartbeat still fresh; files unchanged.')
        return False
    doc = copy.deepcopy(doc)
    doc['updatedAt'] = iso(now) if changed or not previous else previous.get('updatedAt')
    manifest_path = root / 'docs/v1/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest.get('files'), dict):
        raise SystemExit('Invalid existing manifest')
    # The entry stamp follows every write so App clients refresh validUntil too.
    manifest['files']['transitAlerts'] = {'path': 'transit-alerts.json', 'updatedAt': iso(now)}
    manifest['updatedAt'] = iso(now)
    st.write_json(root / ALERTS_PATH, doc)
    st.write_json(manifest_path, manifest)
    print(f'transit-alerts.json written (content changed={changed}).')
    return True


def fetch_dgpa():
    request = urllib.request.Request(DGPA_URL, headers={'User-Agent': 'tsingbus-data monitor'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode('utf-8', errors='replace')
    except Exception:
        return None


def fetch_live():
    fetched = {}
    try:
        client = st.TDX()
    except st.InvalidData as error:
        print(f'TDX unavailable: {error}')
        return {k: None for k in TDX_SOURCES}, 0
    for source_id, (endpoint, _, _) in TDX_SOURCES.items():
        try:
            fetched[source_id] = client.get(endpoint, allow_empty=True)
        except st.InvalidData as error:
            print(f'{source_id} unavailable: {error}')
            fetched[source_id] = None
    return fetched, client.requests


def emit(result_path, result):
    if result_path:
        Path(result_path).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--input', type=Path, help='Offline fixture: {"tdx": {source: rows|null}, "dgpaHtml": path|null}')
    parser.add_argument('--now', help='Override current time (tests/audits)')
    parser.add_argument('--result')
    args = parser.parse_args()
    now = parse_time(args.now) if args.now else dt.datetime.now(TAIPEI)
    transit = json.loads((args.root / 'docs/v1/transit.json').read_text(encoding='utf-8'))
    path = args.root / ALERTS_PATH
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    if args.input:
        fixture = json.loads(args.input.read_text(encoding='utf-8'))
        fetched = fixture['tdx']
        page = Path(fixture['dgpaHtml']).read_text(encoding='utf-8') if fixture.get('dgpaHtml') else None
        requests = 0
    else:
        fetched, requests = fetch_live()
        page = fetch_dgpa()
    doc = build_document(previous, fetched, page, route_catalog(transit), now)
    changed = publish(args.root, doc, previous, now)
    states = sorted({e['state'] for entries in doc['routes'].values() for e in entries})
    print(f'Sources: {[(s["id"], s["state"]) for s in doc["sources"]]}; route states: {states}; TDX requests: {requests}')
    emit(args.result, {'changed': changed, 'states': states})
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output, 'a', encoding='utf-8') as stream:
            stream.write(f"changed={'true' if changed else 'false'}\n")


if __name__ == '__main__':
    main()
