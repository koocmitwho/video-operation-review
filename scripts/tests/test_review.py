"""Behavior tests against real FFmpeg and the public CLI; synthetic view events only."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from make_fixtures import make_fixtures

CLI = Path(__file__).resolve().parents[1] / 'review_video.py'
sys.path.insert(0, str(CLI.parent))


class ReviewContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='vor tests 中文 ')
        cls.root = Path(cls.temp.name)
        cls.cfr, cls.vfr = make_fixtures(cls.root / '输入 视频')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.work = self.root / self._testMethodName

    def cli(self, *args, ok=True):
        if args[0] == 'select' and '--mode' not in args:
            args = (*args, '--mode', 'coverage')  # Preserve the original strict regression contract.
        p = subprocess.run([sys.executable, '-X', 'utf8', str(CLI), *map(str, args),
                            '--work', str(self.work)], capture_output=True, text=True, encoding='utf-8')
        if ok:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        else:
            self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout) if p.stdout.strip().startswith('{') else p

    def rows(self, query):
        with closing(sqlite3.connect(self.work / 'review.sqlite3')) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(query)]

    def scan(self, *args):
        self.cli('scan', self.cfr, '--checkpoint-frames', '1', *args)

    def extract(self):
        self.cli('select', '--anchor-seconds', '0.1', '--pixel-threshold', '8',
                 '--min-changed-pixels', '4')
        self.cli('extract', '--candidates')
        return self.rows('SELECT * FROM assets ORDER BY frame_no')[0]['id']

    def record(self, asset):
        return self.cli('record-view', '--asset', asset, '--actor', 'test-only',
                        '--tool', 'view_image', '--trace', 'synthetic-test://not-a-real-view',
                        '--observation', 'Synthetic test of bookkeeping; not an actual image view.')

    def test_exact_runs_and_small_single_frame_change(self):
        self.scan()
        status = self.cli('status')
        self.assertEqual(status['video_total_frames'], 8)
        self.assertEqual(status['computed_frames'], 8)
        self.assertTrue(status['full_compute_complete'])
        self.assertEqual([r['exact_start'] for r in self.rows('SELECT exact_start FROM frames ORDER BY frame_no')],
                         [0, 0, 0, 3, 4, 4, 6, 6])
        self.cli('select', '--min-changed-pixels', '4', '--pixel-threshold', '8')
        candidates = self.rows('SELECT frame_no,reasons FROM candidates ORDER BY frame_no')
        self.assertEqual([r['frame_no'] for r in candidates], [0, 3, 4, 6])
        self.assertIn('pixel_change', candidates[1]['reasons'])
        self.assertFalse(list(self.work.rglob('*.png')))

    def test_vfr_original_pts_and_other_dimensions(self):
        self.cli('scan', self.vfr)
        rows = self.rows('SELECT time_s,width,height,time_source FROM frames ORDER BY frame_no')
        self.assertEqual(len(rows), 4)
        for row, want in zip(rows, [5.0, 5.04, 5.2, 5.48]):
            self.assertAlmostEqual(row['time_s'], want, places=5)
            self.assertEqual((row['width'], row['height']), (426, 240))
            self.assertEqual(row['time_source'], 'pts')
        self.cli('focus', '--start', '5.03', '--end', '5.21', '--reason', 'check final setting')
        self.assertEqual([r['frame_no'] for r in self.rows('SELECT frame_no FROM candidates ORDER BY frame_no')], [1, 2])

    def test_pause_and_resume_preserve_ranges(self):
        self.scan('--max-new-frames', '3')
        s = self.cli('status')
        self.assertEqual(s['computed_frames'], 3)
        self.assertEqual(s['unprocessed_ranges'], [[3, 7]])
        self.assertFalse(s['full_compute_complete'])
        before = self.rows('SELECT frame_no,digest FROM frames WHERE digest IS NOT NULL')
        self.scan()
        self.assertEqual(self.cli('status')['computed_frames'], 8)
        self.assertEqual(before, self.rows('SELECT frame_no,digest FROM frames WHERE frame_no < 3'))
        self.assertEqual(self.rows('SELECT new_frames FROM attempts WHERE kind="scan" ORDER BY id')[-1]['new_frames'], 5)

    def test_failure_keeps_machine_readable_state(self):
        self.cli('scan', self.cfr.parent / '损坏.mkv', ok=False)
        s = self.cli('status')
        self.assertIsNone(s['video_total_frames'])
        self.assertEqual(s['computed_frames'], 0)
        self.assertFalse(s['full_compute_complete'])
        self.assertTrue(s['attempts'])
        self.assertTrue(any(a['status'] == 'failed' for a in s['attempts']))
        self.assertTrue(list((self.work / 'logs').glob('*')))

    def test_images_and_crops_do_not_mark_viewed_and_views_dedupe(self):
        self.scan()
        asset = self.extract()
        self.assertEqual(self.cli('status')['recorded_visual_unique_frames'], 0)
        crop = self.cli('crop', '--asset', asset, '--box', '0,0,40,25')['asset_id']
        self.record(asset)
        self.record(asset)
        self.record(crop)
        s = self.cli('status')
        self.assertEqual(s['view_events'], 3)
        self.assertEqual(s['recorded_visual_unique_frames'], 1)
        self.assertIsNone(s['independently_verified_visual_frames'])
        self.assertEqual(s['candidates_reviewed_recorded'], 1)
        self.assertFalse(s['all_frames_visual_review_complete_verified'])

    def test_unreviewed_missing_and_tampered_evidence_detected(self):
        self.scan()
        asset = self.extract()
        record = {'steps': [{
            'id': 'step-1', 'phase': 'dialog', 'start_frame': 0, 'end_frame': 3,
            'software': 'synthetic', 'module': 'demo', 'menu_path': ['File'],
            'selected_objects': [], 'final_parameters': {}, 'confirmation_action': 'unknown',
            'visible_result': 'unknown', 'input_files': [], 'output_files': [],
            'evidence': [asset], 'uncertainties': ['Synthetic test'], 'status': 'partial'
        }], 'issues': [{'id': 'q1', 'status': 'open', 'question': 'Was Apply pressed?',
                        'start_frame': 0, 'end_frame': 3, 'attempts': []}]}
        file = self.work / 'records.json'
        file.write_text(json.dumps(record), encoding='utf-8')
        self.cli('import-records', file)
        result = self.cli('validate', ok=False)
        self.assertTrue(any(e['code'] == 'unreviewed_evidence' for e in result['errors']))
        self.record(asset)
        self.cli('validate')
        p = self.work / self.rows('SELECT path FROM assets ORDER BY frame_no')[0]['path']
        original = p.read_bytes()
        p.write_bytes(b'tampered')
        self.assertTrue(any(e['code'] == 'asset_hash_mismatch' for e in self.cli('validate', ok=False)['errors']))
        p.write_bytes(original)
        p.unlink()
        self.assertTrue(any(e['code'] == 'missing_asset' for e in self.cli('validate', ok=False)['errors']))
        record['steps'][0]['evidence'] = ['missing-evidence-id']
        file.write_text(json.dumps(record), encoding='utf-8')
        self.cli('import-records', file)
        self.assertTrue(any(e['code'] == 'unknown_evidence' for e in self.cli('validate', ok=False)['errors']))

    def test_cache_identity_refuses_different_source(self):
        self.scan()
        self.cli('scan', self.vfr, ok=False)
        self.assertEqual(self.cli('status')['video_total_frames'], 8)

    def test_crop_alone_does_not_complete_full_candidate(self):
        self.scan()
        asset = self.extract()
        crop = self.cli('crop', '--asset', asset, '--box', '0,0,10,10')['asset_id']
        self.record(crop)
        s = self.cli('status')
        self.assertEqual(s['recorded_visual_unique_frames'], 1)
        self.assertEqual(s['candidates_reviewed_recorded'], 0)
        self.assertEqual(s.get('source_frames_without_full_view_record_ranges'), [[0, 7]])

    def test_hard_termination_retains_committed_prefix_and_recovers(self):
        long_video = self.root / 'hard-stop-long.mkv'
        p = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'color=c=black:s=1280x720:r=120', '-t', '1', '-c:v', 'ffv1',
                            str(long_video)], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        proc = subprocess.Popen([sys.executable, '-X', 'utf8', str(CLI), 'scan', str(long_video),
                                 '--work', str(self.work), '--checkpoint-frames', '2'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        committed = 0
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline and proc.poll() is None:
                if (self.work / 'review.sqlite3').exists():
                    try:
                        committed = self.rows('SELECT COUNT(*) AS n FROM frames WHERE digest IS NOT NULL')[0]['n']
                    except sqlite3.OperationalError:
                        committed = 0
                    if committed >= 2:
                        proc.kill()
                        break
                time.sleep(0.02)
            proc.communicate(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate(timeout=5)
        self.assertGreaterEqual(committed, 2)
        interrupted = self.cli('status')
        self.assertGreater(interrupted['computed_frames'], 0)
        self.assertLess(interrupted['computed_frames'], 120)
        self.assertFalse(interrupted['full_compute_complete'])
        self.assertTrue(any(a['status'] == 'running_or_unfinalized' for a in interrupted['attempts']))
        self.cli('scan', long_video)
        recovered = self.cli('status')
        self.assertEqual(recovered['computed_frames'], 120)
        self.assertTrue(recovered['full_compute_complete'])

    def test_export_reuses_records_and_reports_gaps(self):
        self.scan()
        self.extract()
        self.cli('export')
        data = json.loads((self.work / 'review.json').read_text(encoding='utf-8'))
        self.assertEqual(data['status']['computed_frames'], 8)
        self.assertEqual(data['status']['recorded_visual_unique_frames'], 0)
        self.assertGreater(data['status']['candidates_pending'], 0)
        self.assertEqual(len((self.work / 'frames.jsonl').read_text(encoding='utf-8').splitlines()), 8)
        self.assertTrue((self.work / 'report.md').is_file())

    def test_candidate_manifest_exposes_time_reasons_and_pending_assets(self):
        self.scan()
        first = self.extract()
        result = self.cli('candidates', '--pending')
        self.assertEqual(result['candidates'][0]['time_s'], 0.0)
        self.assertEqual(result['candidates'][0]['asset_id'], first)
        self.assertTrue(result['candidates'][0]['reasons'])
        self.record(first)
        result = self.cli('candidates', '--pending')
        self.assertNotIn(0, [c['frame_no'] for c in result['candidates']])

    def test_nested_parameter_evidence_cannot_bypass_reference_checks(self):
        self.scan()
        asset = self.extract()
        record = {'steps': [{
            'id': 'nested', 'phase': 'parameters', 'start_frame': 0, 'end_frame': 3,
            'software': 'synthetic', 'module': 'demo', 'menu_path': [], 'selected_objects': [],
            'final_parameters': {'Rate': {'value': '5', 'evidence': ['unlisted-asset']}},
            'confirmation_action': 'not shown', 'visible_result': 'not shown',
            'input_files': [], 'output_files': [], 'evidence': [asset],
            'uncertainties': ['Synthetic test'], 'status': 'partial'}]}
        file = self.work / 'bad-nested.json'
        file.write_text(json.dumps(record), encoding='utf-8')
        self.cli('import-records', file, ok=False)
        self.assertEqual(len(self.rows('SELECT * FROM steps')), 0)

    def test_early_decoder_eof_preserves_computed_prefix(self):
        from vor_store import database, status
        import vor_media
        real_decoder = vor_media.decoder
        # Fault injection at the external decoder boundary, still running actual FFmpeg.
        def limited_decoder(video, ffmpeg, log, filter_file=None, count=None):
            return real_decoder(video, ffmpeg, log, filter_file, count=2)
        with database(self.work, create=True) as conn:
            with patch.object(vor_media, 'decoder', side_effect=limited_decoder):
                with self.assertRaisesRegex(ValueError, 'count does not match'):
                    vor_media.scan(conn, self.work, self.cfr)
            s = status(conn)
            self.assertEqual(s['computed_frames'], 2)
            self.assertEqual(s['unprocessed_ranges'], [[2, 7]])
            self.assertFalse(s['full_compute_complete'])
            self.assertEqual(s['attempts'][-1]['status'], 'failed')

    def test_issue_evidence_references_are_checked(self):
        self.scan()
        file = self.work / 'issue-bad-reference.json'
        file.write_text(json.dumps({'issues': [{'id': 'q', 'question': 'Need confirmation', 'status': 'open',
                       'attempts': [{'evidence': ['missing-asset'], 'new_information': 'none'}]}]}), encoding='utf-8')
        self.cli('import-records', file)
        result = self.cli('validate', ok=False)
        self.assertTrue(any(e['code'] == 'unknown_evidence' for e in result['errors']))

    def test_h264_b_frames_keep_presentation_order_and_extract_identity(self):
        video = self.root / 'H264 B帧.mp4'
        p = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(self.cfr), '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p', '-bf', '2', '-g', '8', str(video)], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.cli('scan', video)
        rows = self.rows('SELECT time_s FROM frames ORDER BY frame_no')
        self.assertEqual([r['time_s'] for r in rows], [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875])
        self.cli('select')
        self.cli('extract', '--candidates')
        self.cli('validate')


if __name__ == '__main__':
    unittest.main()
