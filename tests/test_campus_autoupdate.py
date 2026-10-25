"""Safety regression tests for official campus shuttle automatic updates."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from campus_autoupdate import (UnsafeNotice, apply_suspension, parse_date_span,
                               process, suspension_dates, validate_overrides)


class CampusUpdaterTests(unittest.TestCase):
    def setUp(self):
        self.today = dt.date(2026, 10, 26)

    def test_roc_dates_and_weekdays(self):
        dates = parse_date_span('115年10月24日(六)~10月26日(一)', self.today)
        self.assertEqual([d.isoformat() for d in dates],
                         ['2026-10-24', '2026-10-25', '2026-10-26'])

    def test_slash_dates(self):
        self.assertEqual(len(parse_date_span('10/24(六)~10/26(一)', self.today)), 3)

    def test_mismatched_weekday(self):
        with self.assertRaises(UnsafeNotice):
            parse_date_span('10/24(一)~10/26(六)', self.today)

    def test_multiple_ranges_blocked(self):
        with self.assertRaises(UnsafeNotice):
            parse_date_span('10/24~10/26及11/1~11/2', self.today)

    def test_overlong_range_blocked(self):
        with self.assertRaises(UnsafeNotice):
            parse_date_span('10/24~11/24', self.today)

    def test_not_both_systems(self):
        with self.assertRaises(UnsafeNotice):
            suspension_dates('10/24~10/26校園公車停駛', '', self.today)

    def test_reject_all_if_one_conflicted(self):
        o = {'overrides': [{'date': '2026-10-25', 'system': 'ALL', 'suspended': False,
                            'noteZh': 'x', 'noteEn': 'x'}]}
        with self.assertRaises(UnsafeNotice):
            apply_suspension(parse_date_span('10/24~10/26', self.today), o)
        self.assertEqual(len(o['overrides']), 1)

    def test_idempotence(self):
        o = {'overrides': []}
        days = parse_date_span('10/24~10/26', self.today)
        self.assertEqual(len(apply_suspension(days, o)), 3)
        self.assertEqual(len(apply_suspension(days, o)), 0)
        validate_overrides(o)

    def test_pdf_notice_never_guessed(self):
        period = {'validFrom': '2026-10-05', 'validTo': '2026-11-08',
                  'weekdayDepartures': [], 'saturdayDepartures': [], 'weekendDepartures': []}
        campus = {'system': 'CAMPUS', 'timetables': [period.copy()]}
        nanda = {'system': 'NANDA_SHUTTLE', 'timetables': [period.copy()]}
        notice = {'id': '99', 'title': '11/9~11/30校園公車時刻表', 'body': '請見附件',
                  'pdfs': ['table.pdf'], 'url': 'https://affairs.site.nthu.edu.tw/'}
        added, reviews, processed = process([notice], {'seen': {}}, campus, nanda,
                                            {'overrides': []}, self.today)
        self.assertFalse(added)
        self.assertEqual(processed[0]['status'], 'manual_review')
        self.assertIn('PDF', reviews[0]['reason'])


if __name__ == '__main__':
    unittest.main()
