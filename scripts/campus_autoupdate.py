#!/usr/bin/env python3
"""Conservative, source-verified NTHU shuttle notice updater.

Only clear official BOTH-system suspensions are automatically applied.
PDF/image timetables must not be guessed from an unverified OCR output.
"""
import datetime as dt
import hashlib
import json
import re
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from crawl import LIST_URL, classify, fetch_detail, fetch_list

ROOT = Path(__file__).resolve().parents[1]
SPAN = re.compile(
    r'(?:(?P<year>20\d{2}|1\d{2})\s*年\s*)?'
    r'(?P<m1>\d{1,2})\s*[月/]\s*(?P<d1>\d{1,2})\s*日?\s*'
    r'(?:[（(](?P<w1>[一二三四五六日天])[）)])?\s*'
    r'(?:~|～|至|－|—|–|-)\s*'
    r'(?:(?P<m2>\d{1,2})\s*[月/])?\s*(?P<d2>\d{1,2})\s*日?\s*'
    r'(?:[（(](?P<w2>[一二三四五六日天])[）)])?'
)
WEEK = '一二三四五六日'
TIME = re.compile(r'^\d{2}:\d{2}$')


class UnsafeNotice(ValueError):
    pass


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def parse_date_span(text, today):
    matches = list(SPAN.finditer(text))
    if not matches:
        raise UnsafeNotice('公告未提供明確起迄日期')
    spans = []
    for match in matches:
        g = match.groupdict()
        first_month, first_day = int(g['m1']), int(g['d1'])
        last_month, last_day = int(g['m2'] or g['m1']), int(g['d2'])
        explicit = g['year']
        year = int(explicit) if explicit else None
        if year is not None and year < 1911:
            year += 1911
        possible = [year] if year else [today.year - 1, today.year, today.year + 1]
        candidates = []
        for y in possible:
            try:
                first = dt.date(y, first_month, first_day)
                last = dt.date(y + int((last_month, last_day) < (first_month, first_day)), last_month, last_day)
            except ValueError:
                continue
            if not (0 <= (last - first).days <= 13 and -14 <= (first - today).days <= 120):
                continue
            if g['w1'] and WEEK[first.weekday()] != g['w1'].replace('天', '日'):
                continue
            if g['w2'] and WEEK[last.weekday()] != g['w2'].replace('天', '日'):
                continue
            candidates.append((first, last))
        if len(candidates) != 1:
            raise UnsafeNotice('公告年份或星期與日期不能唯一對應')
        spans.append(candidates[0])
    if len(set(spans)) != 1:
        raise UnsafeNotice('公告中存在多個不同日期區間')
    start, end = spans[0]
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


def validate_timetables(data, system):
    if data.get('system') != system or not isinstance(data.get('timetables'), list) or not data['timetables']:
        raise ValueError('Invalid timetable schema')
    periods = data['timetables']
    for i, period in enumerate(periods):
        start = dt.date.fromisoformat(period['validFrom'])
        end = dt.date.fromisoformat(period['validTo'])
        if start > end or (i and start != dt.date.fromisoformat(periods[i-1]['validTo']) + dt.timedelta(days=1)):
            raise ValueError(f'Overlapping/missing periods: {system}')
        keys = ('weekdayDepartures', 'saturdayDepartures') if system == 'CAMPUS' else ('weekdayDepartures', 'weekendDepartures')
        for key in keys:
            departures = period.get(key)
            if not isinstance(departures, list):
                raise ValueError('Missing departure list')
            for trip in departures:
                clock = trip.get('time')
                if not isinstance(clock, str) or not TIME.fullmatch(clock):
                    raise ValueError('Malformed departure time')
                hh, mm = map(int, clock.split(':'))
                if hh > 23 or mm > 59 or not trip.get('routeId') or not trip.get('departureStopId'):
                    raise ValueError('Invalid shuttle departure')
                if type(trip.get('isPaidSubstitute')) is not bool:
                    raise ValueError('Missing substitution flag')
    return dt.date.fromisoformat(periods[-1]['validTo'])


def validate_overrides(data):
    seen = set()
    for item in data.get('overrides', []):
        date = item['date']
        if dt.date.fromisoformat(date).isoformat() != date:
            raise ValueError('Invalid override date')
        key = (date, item['system'])
        if key in seen or type(item.get('suspended')) is not bool:
            raise ValueError('Duplicated or invalid override')
        if not item.get('noteZh') or not item.get('noteEn'):
            raise ValueError('Missing bilingual notes')
        seen.add(key)


def suspension_dates(title, body, today):
    combined = title + '\n' + body
    if not ('停駛' in combined or '停止行駛' in combined):
        raise UnsafeNotice('沒有明確停駛措辭')
    if not ('校園公車' in combined and '南大校區區間車' in combined):
        raise UnsafeNotice('未明確同時指定校園公車與南大區間車')
    return parse_date_span(title, today)


def apply_suspension(dates, data):
    existing = data['overrides']
    # Validate ALL target dates first: one conflicted date must block the entire notice.
    for date in dates:
        matches = [x for x in existing if x['date'] == date.isoformat()]
        if any(x['system'] != 'ALL' or x['suspended'] is not True for x in matches):
            raise UnsafeNotice(f'{date}: 既有停駛設定存在衝突')
    added = []
    for date in dates:
        if any(x['date'] == date.isoformat() for x in existing):
            continue
        item = {
            'date': date.isoformat(), 'system': 'ALL', 'suspended': True,
            'noteZh': '清華大學官方公告：校園公車及南大校區區間車停駛',
            'noteEn': 'No service (official NTHU shuttle suspension notice)'
        }
        existing.append(item)
        added.append(item)
    existing.sort(key=lambda x: (x['date'], x['system']))
    return added


def digest(item):
    return hashlib.sha256((item['title'] + item['body'] + '|'.join(item['pdfs'])).encode('utf-8')).hexdigest()[:16]


def process(items, state, campus, nanda, overrides, today):
    validate_timetables(campus, 'CAMPUS')
    validate_timetables(nanda, 'NANDA_SHUTTLE')
    validate_overrides(overrides)
    added, reviews, processed = [], [], []
    for item in items:
        stamp = digest(item)
        previous = state.setdefault('seen', {}).get(item['id'])
        if previous and previous.get('digest') == stamp:
            continue
        title = item['title']
        if classify(title)[1] != '需更新資料':
            state['seen'][item['id']] = {'title': title, 'digest': stamp}
            continue
        try:
            if '時刻表' in title:
                raise UnsafeNotice('時刻表附件可能是圖片或PDF，尚無可信的完整班次機器解析結果')
            dates = suspension_dates(title, item['body'], today)
            added.extend(apply_suspension(dates, overrides))
            status = 'handled'
        except UnsafeNotice as err:
            reviews.append({'id': item['id'], 'digest': stamp, 'title': title, 'url': item['url'], 'reason': str(err)})
            status = 'manual_review'
        state['seen'][item['id']] = {'title': title, 'digest': stamp}
        processed.append({'id': item['id'], 'digest': stamp, 'status': status})
    validate_overrides(overrides)
    for system, data in (('CAMPUS', campus), ('NANDA_SHUTTLE', nanda)):
        end = validate_timetables(data, system)
        if (end - today).days <= 7:
            reviews.append({'id': 'coverage-' + system, 'digest': end.isoformat(),
                            'title': system + ' 班表即將到期', 'url': LIST_URL,
                            'reason': f'最新班表僅涵蓋到 {end}，尚無可靠的後續班表'})
    return added, reviews, processed


def main():
    today = dt.datetime.now(ZoneInfo('Asia/Taipei')).date()
    campus = read_json(ROOT / 'docs/v1/campus.json')
    nanda = read_json(ROOT / 'docs/v1/nanda.json')
    overrides = read_json(ROOT / 'docs/v1/overrides.json')
    state = read_json(ROOT / 'state.json')
    if not state.get('seen'):
        raise SystemExit('Cannot scan with an unseeded notice state')
    items = fetch_list()
    if not items:
        raise SystemExit('Official notice list empty; no automatic changes')
    for item in items:
        body, pdfs = fetch_detail(item['url'])
        if body.startswith('(擷取內文失敗'):
            raise SystemExit('Official notice detail unavailable; no changes')
        item['body'], item['pdfs'] = body, pdfs
        time.sleep(1)
    added, reviews, processed = process(items, state, campus, nanda, overrides, today)
    if added:
        (ROOT / 'docs/v1/overrides.json').write_text(json.dumps(overrides, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        path = ROOT / 'docs/v1/manifest.json'
        manifest = read_json(path)
        now = dt.datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
        manifest['updatedAt'] = now
        manifest['files']['overrides']['updatedAt'] = now
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'campus-review.json').write_text(json.dumps({'reviews': reviews, 'processed': processed}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Announcements: {len(items)}; new suspensions: {len(added)}; manual reviews: {len(reviews)}')


if __name__ == '__main__':
    main()
