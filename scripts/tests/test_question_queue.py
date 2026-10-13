"""Read-only question priority; all view events are synthetic bookkeeping."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vor_store as store


class QuestionQueueContract(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='vor queue 中文 ')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.conn = store.connect(self.work, create=True)
        self.addCleanup(self.conn.close)
        self.source = {'path': str(self.work / 'source.mkv'), 'size': 123, 'sha256': 'a' * 64}
        times = [5.0, 5.04, 5.20, 5.48, 5.8, 6.2, 6.8, 7.1]
        starts = [0, 0, 2, 3, 3, 5, 6, 7]
        for n, (timestamp, start) in enumerate(zip(times, starts)):
            self.conn.execute(
                'INSERT INTO frames(frame_no,pts,pts_time,time_s,time_source,width,height,digest,exact_start) '
                'VALUES (?,?,?,?,?,?,?,?,?)',
                (n, str(int(timestamp * 1000)), str(timestamp), timestamp, 'pts', 16, 16,
                 f'exact-state-{start}', start))
            self.conn.execute('INSERT INTO requests VALUES (?,?,?)', (n, f'fixture-{n}', 'test'))
        store.set_meta(self.conn, 'source', self.source)
        store.rebuild_candidates(self.conn)
        self.conn.commit()

    def queue(self, **kwargs):
        self.assertIsNotNone(importlib.util.find_spec('vor_queue'),
                             'The read-only bounded question queue is not implemented')
        from vor_queue import question_queue
        return question_queue(self.conn, self.work, **kwargs)

    def asset(self, frame, kind='full'):
        ident = f'{kind}-{frame}'
        path = self.work / 'evidence' / (ident + '.png')
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b'Synthetic bookkeeping fixture, not an image inspection.')
        self.conn.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?,?)',
                          (ident, frame, kind, path.relative_to(self.work).as_posix(),
                           store.sha256(path), None, None, store.now()))
        self.conn.commit()
        return ident

    def view(self, frame, kind='full', presentation='native'):
        ident = self.asset(frame, kind)
        self.conn.execute(
            'INSERT INTO views(asset_id,frame_no,actor,tool,trace_ref,observation,asset_sha256,created,presentation) '
            'SELECT id,frame_no,?,?,?,?,sha256,?,? FROM assets WHERE id=?',
            ('test-only', 'image_tool', 'synthetic-test://question-queue',
             'Synthetic bookkeeping only, not an actual view.', store.now(), presentation, ident))
        self.conn.commit()

    def test_window_prioritizes_without_removing_other_pending_candidates(self):
        result = self.queue(start=6.0, end=6.9, batch_size=3)
        self.assertEqual(result['total_pending'], 6)
        self.assertEqual(result['range_pending'], 2)
        self.assertEqual([item['frame_no'] for item in result['batch']], [5, 6, 0])
        self.assertEqual(result['remaining_after_batch'], 3)
        self.assertTrue(result['range_scope_is_not_full_review'])

    def test_original_request_pts_matches_when_exact_representative_precedes_window(self):
        result = self.queue(start=5.03, end=5.05, batch_size=1)
        entry = result['batch'][0]
        self.assertEqual(result['range_pending'], 1)
        self.assertEqual(entry['frame_no'], 0)
        self.assertEqual(entry['time_s'], 5.0)
        self.assertEqual(entry['matched_request_ranges'], [
            {'start_frame': 1, 'end_frame': 1, 'start_time_s': 5.04, 'end_time_s': 5.04}])
        self.assertEqual(entry['represented_requests'], [0, 1])
        self.assertTrue(entry['in_requested_range'])
        self.assertEqual(entry['reasons'], ['fixture-0@0', 'fixture-1@1'])

    def test_decimal_original_pts_inclusive_bounds_do_not_assume_zero_origin_or_fps(self):
        result = self.queue(start=5.20, end=5.48, batch_size=2)
        self.assertEqual(result['requested_range'], {'start': 5.20, 'end': 5.48})
        self.assertEqual(result['range_pending'], 2)
        self.assertEqual([item['frame_no'] for item in result['batch']], [2, 3])
        self.assertEqual(result['batch'][1]['matched_request_ranges'], [
            {'start_frame': 3, 'end_frame': 3, 'start_time_s': 5.48, 'end_time_s': 5.48}])

    def test_empty_window_still_returns_global_pending_in_frame_order(self):
        result = self.queue(start=20.0, end=21.0, batch_size=2)
        self.assertEqual(result['range_pending'], 0)
        self.assertEqual([item['frame_no'] for item in result['batch']], [0, 2])
        self.assertTrue(all(not item['in_requested_range'] for item in result['batch']))

    def test_default_batch_and_source_identity_do_not_imply_source_reverification(self):
        result = self.queue()
        self.assertEqual([item['frame_no'] for item in result['batch']], [0, 2, 3, 5, 6, 7])
        self.assertEqual(result['batch_size'], 8)
        self.assertIsNone(result['requested_range'])
        self.assertIsNone(result['range_pending'])
        self.assertEqual(result['source'], self.source)
        self.assertFalse(result['source_reverified'])
        self.assertTrue(all(item['absolute_path'] is None for item in result['batch']))

    def test_only_full_native_candidate_views_leave_queue(self):
        self.view(0)
        self.view(2, presentation='overview')
        self.view(3, kind='crop')
        result = self.queue(batch_size=20)
        self.assertEqual(result['total_pending'], 5)
        self.assertEqual([item['frame_no'] for item in result['batch']], [2, 3, 5, 6, 7])
        self.assertEqual(result['total_pending'], store.status(self.conn)['candidates_pending'])

    def test_return_to_same_pixels_is_a_distinct_candidate(self):
        self.conn.execute("UPDATE frames SET digest='exact-state-0' WHERE frame_no=7")
        self.conn.commit()
        self.view(0)
        self.assertIn(7, [item['frame_no'] for item in self.queue()['batch']])

    def test_unviewed_extracted_asset_has_safe_absolute_path(self):
        ident = self.asset(2)
        entry = self.queue(start=5.20, end=5.20, batch_size=1)['batch'][0]
        self.assertEqual(entry['asset_id'], ident)
        self.assertEqual(entry['absolute_path'], str(self.work / 'evidence' / 'full-2.png'))

    def test_repeated_batches_use_current_views_and_never_skip_remaining_candidates(self):
        delivered = []
        for _ in range(3):
            result = self.queue(start=6.0, end=6.9, batch_size=2)
            frames = [entry['frame_no'] for entry in result['batch']]
            delivered.extend(frames)
            for frame in frames:
                self.view(frame)
        self.assertEqual(delivered, [5, 6, 0, 2, 3, 7])
        result = self.queue(start=6.0, end=6.9, batch_size=2)
        self.assertEqual(result['batch'], [])
        self.assertEqual(result['total_pending'], 0)

    def test_queue_is_read_only_for_sql_rows_and_database_bytes(self):
        self.asset(2)
        self.conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        before_rows = list(self.conn.iterdump())
        files = [path for path in self.work.iterdir() if path.name.startswith('review.sqlite3')]
        before_bytes = {path.name: path.read_bytes() for path in files}
        total_changes = self.conn.total_changes
        self.conn.execute('PRAGMA query_only=ON')
        self.queue(start=5.03, end=5.8, batch_size=1)
        self.assertEqual(list(self.conn.iterdump()), before_rows)
        self.assertEqual(self.conn.total_changes, total_changes)
        self.assertEqual({path.name: path.read_bytes() for path in files}, before_bytes)

    def test_partial_invalid_nonfinite_and_boolean_ranges_are_rejected(self):
        for args in ({'start': 5}, {'end': 6}, {'start': 6, 'end': 5},
                     {'start': float('nan'), 'end': 6}, {'start': 5, 'end': float('inf')},
                     {'start': float('-inf'), 'end': 6}, {'start': True, 'end': 6},
                     {'start': '5', 'end': 6}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.queue(**args)

    def test_batch_size_requires_a_positive_integer(self):
        for batch_size in (0, -1, 1.5, True, '2', None):
            with self.subTest(batch_size=batch_size), self.assertRaises(ValueError):
                self.queue(batch_size=batch_size)


if __name__ == '__main__':
    unittest.main()
