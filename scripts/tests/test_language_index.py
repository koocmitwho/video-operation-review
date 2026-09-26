"""Synthetic timestamp alignment tests; no visual inspection or ASR is performed."""
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vor_language as language
import vor_store as store


class CountedSpans:
    """Observe source-span visits without changing the real alignment values."""

    def __init__(self, spans):
        self.spans = spans
        self.visits = 0

    def __len__(self):
        return len(self.spans)

    def __iter__(self):
        for span in self.spans:
            self.visits += 1
            yield span

    def __getitem__(self, key):
        value = self.spans[key]
        self.visits += len(value) if isinstance(key, slice) else 1
        return value


class LanguageIndexContract(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='vor language index synthetic ')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.conn = store.connect(self.work, create=True)
        self.addCleanup(self.conn.close)

    def frames(self, times_and_durations):
        self.conn.executemany(
            'INSERT INTO frames(frame_no,time_s,duration_time,time_source) VALUES (?,?,?,?)',
            ((n, time, duration, 'pts') for n, (time, duration) in enumerate(times_and_durations)))
        self.conn.commit()

    def align(self, bounds, key='synthetic', offset=0):
        segments = [dict(start=start, end=end, text=f'原文 cue {i}',
                         translation='translation', speaker='synthetic')
                    for i, (start, end) in enumerate(bounds)]
        return language._store(self.conn, {'kind': 'synthetic'}, segments,
                               offset, 'zh-en', 'original', key)

    def test_duplicate_and_backward_pts_do_not_rescan_every_frame_per_cue(self):
        frame_count = 4096
        cue_count = 128
        for backward in (False, True):
            with self.subTest(backward=backward):
                self.conn.execute('DELETE FROM frames')
                times = [(n / 30, '0.033333333') for n in range(frame_count)]
                times[2000] = ((1990 if backward else 1999) / 30, '0.033333333')
                self.frames(times)
                spans, warnings = language._alignment(self.conn)
                counted = CountedSpans(spans)
                bounds = [(i + 0.01, i + 0.02) for i in range(cue_count)]
                # Only the read-only span container is instrumented. All queries,
                # warnings, cue records and database writes use production code.
                with patch.object(language, '_alignment', return_value=(counted, warnings)):
                    result = self.align(bounds, key=f'complexity-{backward}')
                self.assertEqual(len(result['cues']), cue_count)
                self.assertIn('non_increasing_frame_time', result['warnings'])
                self.assertLess(
                    counted.visits, frame_count * 8 + cue_count * 32,
                    f'{counted.visits} span visits indicate per-cue full-frame rescans')

    def test_overlap_points_unknown_times_and_half_open_boundaries(self):
        self.frames([(5, None), (5, '.5'), (4, '4'), (None, None),
                     (6, '0'), (6, None), (7, '0')])
        # These display intervals are [5,5], [5,5.5), [4,8), unknown,
        # [6,6], [6,7), [7,7]. Point states count at cue start, never at end.
        bounds = [(5, 5.25), (5.5, 6), (6, 7), (7, 7.25), (8, 9), (4, 5)]
        result = self.align(bounds)
        self.assertEqual([cue['frame_ranges'] for cue in result['cues']],
                         [[[0, 2]], [[2, 2]], [[2, 2], [4, 5]],
                          [[2, 2], [6, 6]], [], [[2, 2]]])
        self.assertEqual(result['warnings'], ['non_increasing_frame_time', 'outside_index',
                                             'overlap', 'unknown_display_duration',
                                             'unknown_frame_time'])
        self.assertEqual([cue['original_start'] for cue in result['cues']],
                         [a for a, _ in bounds])
        self.assertTrue(all(cue['evidence_role'] == 'language_clue_only' for cue in result['cues']))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM views').fetchone()[0], 0)

    def test_arbitrary_cue_order_and_offsets_match_exhaustive_overlap_reference(self):
        rng = random.Random(20260926)
        rows = [(5 + n * .25, '.25') for n in range(160)]
        for n in range(7, 160, 13):
            rows[n] = (rows[n - 1][0], '3.5')
        for n in range(10, 160, 17):
            rows[n] = (None, None)
        for n in range(19, 160, 23):
            rows[n] = (5 + n * .25 - 2, '0')
        self.frames(rows)
        bounds = [(rng.uniform(-2, 45), rng.uniform(.01, 5)) for _ in range(150)]
        bounds = [(start, start + length) for start, length in bounds]
        offset = 2.5
        result = self.align(bounds, offset=offset)
        for cue, (start, end) in zip(result['cues'], bounds):
            members = []
            for n, (time, duration) in enumerate(rows):
                if time is None:
                    continue
                following = rows[n + 1][0] if n + 1 < len(rows) else None
                stop = following if following is not None and following > time else time + float(duration or 0)
                point_inside = stop == time and start + offset <= time < end + offset
                interval_overlaps = time < end + offset and stop > start + offset
                if point_inside or interval_overlaps:
                    members.append(n)
            actual = [n for a, b in cue['frame_ranges'] for n in range(a, b + 1)]
            self.assertEqual(actual, members, (start, end))
            self.assertEqual(cue['start_time'], start + offset)
            self.assertEqual(cue['end_time'], end + offset)
            self.assertEqual(cue['translation'], 'translation')
        stored = json.loads(self.conn.execute('SELECT payload FROM language_sources').fetchone()[0])
        self.assertEqual(stored, result)

    def test_empty_and_unknown_only_indexes_keep_cues_unaligned(self):
        for unknown_only in (False, True):
            with self.subTest(unknown_only=unknown_only):
                if unknown_only:
                    self.frames([(None, None)])
                result = self.align([(0, 1)], key=f'empty-{unknown_only}')
                self.assertEqual(result['cues'][0]['frame_ranges'], [])
                self.assertEqual(result['cues'][0]['alignment'], 'unaligned')
                self.assertIn('outside_index', result['warnings'])

    def test_legacy_cached_alignment_cannot_hide_a_long_overlapping_display(self):
        self.frames([(0, '10'), (None, None), (1, '1'), (2, '1'), (3, '1')])
        path = self.work / 'transcript.json'
        data = dict(time_base='original', segments=[dict(start=2.2, end=2.4, text='synthetic')])
        path.write_text(json.dumps(data), encoding='utf-8')
        source = dict(path=str(path.resolve()), sha256=store.sha256(path), kind='asr_interchange',
                      engine='user_supplied', model=None, glossary=[], provenance=None)
        # Reproduce the historical cache key, before an overlap-capable index.
        historical_index = language.canonical_hash([tuple(row) for row in self.conn.execute(
            'SELECT frame_no,time_s,duration_time FROM frames ORDER BY frame_no')])
        legacy_key = 'lang-' + language.canonical_hash([source, 0.0, historical_index])[:24]
        legacy = language._store(self.conn, source, data['segments'], 0, 'und', 'original', legacy_key)
        # Old predecessor-only lookup omitted frame 0, whose known duration is 10s.
        legacy['cues'][0]['frame_ranges'] = [[3, 3]]
        with self.conn:
            self.conn.execute('UPDATE language_sources SET payload=? WHERE id=?',
                              (store.dump(legacy), legacy_key))
        result = language.import_transcript(self.conn, self.work, path)
        self.assertEqual(result['cues'][0]['frame_ranges'], [[0, 0], [3, 3]])
        self.assertFalse(result['cache_reused'])
        self.assertNotEqual(result['id'], legacy_key)
        cached = language.import_transcript(self.conn, self.work, path)
        self.assertTrue(cached['cache_reused'])
        self.assertEqual(cached['id'], result['id'])
        old = json.loads(self.conn.execute(
            'SELECT payload FROM language_sources WHERE id=?', (legacy_key,)).fetchone()[0])
        self.assertEqual(old['cues'][0]['frame_ranges'], [[3, 3]])


if __name__ == '__main__':
    unittest.main()
