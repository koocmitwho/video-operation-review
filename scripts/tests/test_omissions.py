"""Omission-gate contracts. View records here are synthetic bookkeeping fixtures, not actual views."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from PIL import Image
from make_fixtures import make_fixtures

CLI = Path(__file__).resolve().parents[1] / 'review_video.py'


class OmissionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='vor omissions 中文 ')
        cls.root = Path(cls.temp.name)
        cls.video, _ = make_fixtures(cls.root / '素材')
        frames = [Image.new('RGB', (160, 90), (30, 30, 30)) for _ in range(4)]
        frames[1].putpixel((40, 40), (31, 30, 30))
        cls.low = cls.root / 'one-pixel.mkv'
        p = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pixel_format', 'rgb24',
                            '-video_size', '160x90', '-framerate', '8', '-i', 'pipe:0', '-c:v', 'ffv1',
                            str(cls.low)], input=b''.join(f.tobytes() for f in frames), capture_output=True)
        if p.returncode:
            raise RuntimeError(p.stderr.decode('utf-8', errors='replace'))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.work = self.root / self._testMethodName

    def cli(self, *args, ok=True):
        if args[0] == 'select' and '--mode' not in args:
            args = (*args, '--mode', 'coverage')
        if args[0] in ('audit','validate') and '--mode' not in args:
            args = (*args, '--mode', 'strict')
        p = subprocess.run([sys.executable, '-X', 'utf8', str(CLI), *map(str, args), '--work', str(self.work)],
                           capture_output=True, text=True, encoding='utf-8')
        if ok:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        else:
            self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(p.stdout.lstrip().startswith('{'), p.stdout + p.stderr)
        return json.loads(p.stdout)

    def rows(self, query):
        with closing(sqlite3.connect(self.work / 'review.sqlite3')) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(query)]

    def import_data(self, data, ok=True):
        path = self.work / 'annotations.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        return self.cli('import-records', path, ok=ok)

    def record_views(self, numbers, actor='test-author'):
        self.cli('extract', '--frames', ','.join(map(str, numbers)))
        for n in numbers:
            self.cli('record-view', '--asset', f'f{n:09d}', '--actor', actor, '--tool', 'view_image',
                     '--trace', 'synthetic-test://not-an-actual-view', '--observation', 'Synthetic fixture only.')

    def prepare(self):
        self.cli('scan', self.video)
        self.cli('select')
        self.record_views([0, 3, 4, 6])

    @staticmethod
    def step(ident, start, end, before, after, before_frame, after_frame):
        before_asset, after_asset = f'f{before_frame:09d}', f'f{after_frame:09d}'
        return {
            'id': ident, 'phase': ident, 'author': 'test-author', 'start_frame': start, 'end_frame': end,
            'software': 'Synthetic', 'module': 'Test', 'menu_path': ['Options'], 'selected_objects': ['A'],
            'final_parameters': {'A.rate': after}, 'confirmation_action': 'Apply result observed',
            'visible_result': 'Applied', 'input_files': [], 'output_files': [],
            'evidence': [before_asset, after_asset], 'uncertainties': [], 'status': 'confirmed',
            'transition': {
                'before': {'A.rate': {'value': before, 'evidence': [before_asset]}},
                'after': {'A.rate': {'value': after, 'evidence': [after_asset]}},
                'confirmation': {'status': 'observed', 'evidence': [after_asset], 'note': 'Synthetic confirmation'},
                'result': {'status': 'observed', 'evidence': [after_asset], 'note': 'Synthetic result'}
            }
        }

    def good_records(self):
        steps = [self.step('S1', 0, 3, '1', '2', 0, 3), self.step('S2', 4, 7, '2', '3', 4, 6)]
        coverage = [dict(frame_no=n, classification='operation', step_ids=['S1' if n < 4 else 'S2'],
                         issue_ids=[], reason='This state supports the linked operation.',
                         evidence=[f'f{n:09d}'], reviewer='test-author') for n in [0, 3, 4, 6]]
        return {'steps': steps, 'coverage': coverage}

    def review_record(self, audit):
        self.record_views([0, 3, 4, 6], actor='test-reviewer')
        return {'id': 'R1', 'reviewer': 'test-reviewer', 'independence': 'independent',
                'snapshot': audit['snapshot'], 'checked_state_frames': [0, 3, 4, 6],
                'evidence': [f'f{n:09d}' for n in [0, 3, 4, 6]],
                'tool_trace_refs': ['synthetic-test://not-an-actual-view'],
                'issue_ids': [], 'conclusion': 'no_additional_omissions_found',
                'note': 'Synthetic unit fixture, not proof of independent model inspection.'}

    def codes(self, audit):
        return {f['code'] for f in audit['findings']}

    def test_explicit_strict_selection_keeps_subthreshold_state(self):
        self.cli('scan', self.low)
        self.cli('select')
        self.assertEqual([r['frame_no'] for r in self.rows('SELECT frame_no FROM candidates ORDER BY frame_no')],
                         [0, 1, 2])

    def test_audit_finds_unselected_state_and_queues_without_new_views(self):
        self.cli('scan', self.low)
        self.cli('select', '--mode', 'changes', '--context-frames', '0')
        self.assertNotIn(1, [r['frame_no'] for r in self.rows('SELECT frame_no FROM candidates')])
        audit = self.cli('audit', '--queue')
        self.assertEqual(audit['coverage']['state_count'], 3)
        self.assertTrue(any(f['code'] == 'unaccounted_state' and f['frame_no'] == 1 for f in audit['findings']))
        self.assertIn(1, [r['frame_no'] for r in self.rows('SELECT frame_no FROM candidates')])
        self.assertEqual(self.cli('status')['recorded_visual_unique_frames'], 0)
        self.assertEqual(self.cli('status')['computed_frames'], 4)

    def test_broad_step_interval_does_not_hide_unaccounted_states(self):
        self.prepare()
        self.import_data({'steps': [self.step('whole-video', 0, 7, '1', '3', 0, 6)]})
        audit = self.cli('audit')
        self.assertEqual(audit['coverage']['unaccounted_state_frames'], [0, 3, 4, 6])
        self.assertFalse(audit['records_ready_for_omission_review'])

    def test_crop_only_cannot_close_state_accounting(self):
        self.cli('scan', self.video)
        self.cli('extract', '--frames', '3')
        cropped = self.cli('crop', '--asset', 'f000000003', '--box', '0,0,20,20')['asset_id']
        self.cli('record-view', '--asset', cropped, '--actor', 'test-author', '--tool', 'view_image',
                 '--trace', 'synthetic-test://crop', '--observation', 'Synthetic crop view fixture')
        self.import_data({'coverage': [{'frame_no': 3, 'classification': 'context', 'step_ids': [], 'issue_ids': [],
                        'reason': 'Purportedly irrelevant', 'evidence': [cropped], 'reviewer': 'test-author'}]})
        audit = self.cli('audit')
        self.assertIn('state_full_view_missing', self.codes(audit))
        self.assertNotIn(3, audit['coverage']['accounted_state_frames'])

    def test_operation_coverage_requires_linked_step(self):
        self.prepare()
        data = self.good_records()
        data['coverage'][1]['step_ids'] = ['unknown-step']
        self.import_data(data)
        self.assertIn('coverage_step_missing', self.codes(self.cli('audit')))

    def test_coverage_reviewer_must_have_their_own_full_view_record(self):
        self.prepare()
        data = self.good_records()
        data['coverage'][1]['reviewer'] = 'someone-who-never-opened-it'
        self.import_data(data)
        audit = self.cli('audit')
        self.assertNotIn(3, audit['coverage']['accounted_state_frames'])

    def test_reviewer_trace_string_alone_does_not_pass_gate(self):
        self.prepare()
        self.import_data(self.good_records())
        review = self.review_record(self.cli('audit'))
        review['reviewer'] = 'different-agent-with-no-view-records'
        self.import_data({'omission_reviews': [review]})
        audit = self.cli('audit')
        self.assertIn('reviewer_view_missing', self.codes(audit))
        self.assertFalse(audit['review_gate_passed_recorded'])

    def test_review_tool_trace_must_match_reviewer_evidence(self):
        self.prepare()
        self.import_data(self.good_records())
        review=self.review_record(self.cli('audit'))
        self.import_data({'omission_reviews':[review]})
        self.assertTrue(self.cli('audit')['review_gate_passed_recorded'])
        review['tool_trace_refs']=['synthetic-test://no-such-call']
        self.import_data({'omission_reviews':[review]})
        audit=self.cli('audit')
        self.assertFalse(audit['review_gate_passed_recorded'])
        self.assertIn('review_trace_unlinked',self.codes(audit))

    def test_state_discontinuity_detects_missing_intermediate_change(self):
        self.prepare()
        data = self.good_records()
        data['steps'][1]['transition']['before']['A.rate']['value'] = '99'
        self.import_data(data)
        gaps = [f for f in self.cli('audit')['findings'] if f['code'] == 'state_discontinuity']
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]['state_key'], 'A.rate')
        self.assertEqual(gaps[0]['previous_value'], '2')
        self.assertEqual(gaps[0]['next_value'], '99')

    def test_absent_visible_control_is_distinct_from_unknown_business_value(self):
        self.prepare()
        data = self.good_records()
        first, second = data['steps']
        first['transition']['before']['dialog.rate_field'] = {
            'value': {'visible': True, 'text': '20'}, 'evidence': ['f000000000']}
        first['transition']['after']['dialog.rate_field'] = {
            'value': {'visible': False}, 'evidence': ['f000000003']}
        second['transition']['before']['dialog.rate_field'] = {
            'value': {'visible': False}, 'evidence': ['f000000004']}
        second['transition']['after']['dialog.rate_field'] = {
            'value': {'visible': True, 'text': '5'}, 'evidence': ['f000000006']}
        self.import_data(data)
        audit = self.cli('audit')
        self.assertTrue(audit['records_ready_for_omission_review'], audit['findings'])
        self.assertNotIn('state_value_unknown', self.codes(audit))
        self.assertNotIn('state_discontinuity', self.codes(audit))

    def test_missing_confirmation_remains_gap_even_with_resolved_issue(self):
        self.prepare()
        data = self.good_records()
        data['steps'][0]['transition']['confirmation'] = {'status': 'not_shown', 'evidence': [], 'note': 'Not visible'}
        data['issues'] = [{'id': 'Q1', 'question': 'Was it applied?', 'status': 'resolved', 'attempts': []}]
        self.import_data(data)
        audit = self.cli('audit')
        self.assertIn('confirmation_gap', self.codes(audit))
        self.assertFalse(audit['records_ready_for_omission_review'])

    def test_consistent_records_require_separate_omission_review(self):
        self.prepare()
        self.import_data(self.good_records())
        audit = self.cli('audit')
        self.assertTrue(audit['records_ready_for_omission_review'], audit['findings'])
        self.assertEqual(audit['coverage']['accounted_state_frames'], [0, 3, 4, 6])
        self.assertEqual(audit['omission_review']['status'], 'missing')
        self.assertFalse(audit['review_gate_passed_recorded'])
        self.assertFalse(audit['semantic_completeness_proven'])
        self.cli('validate', '--require-coverage', ok=False)

    def test_review_snapshot_becomes_stale_after_step_edit(self):
        self.prepare()
        data = self.good_records()
        self.import_data(data)
        audit = self.cli('audit')
        self.import_data({'omission_reviews': [self.review_record(audit)]})
        reviewed = self.cli('audit')
        self.assertTrue(reviewed['review_gate_passed_recorded'], reviewed['findings'])
        self.assertFalse(reviewed['semantic_completeness_proven'])
        self.cli('validate', '--require-coverage')
        data['steps'][0]['visible_result'] = 'Changed annotation after review'
        self.import_data({'steps': [data['steps'][0]]})
        stale = self.cli('audit')
        self.assertEqual(stale['omission_review']['status'], 'stale')
        self.assertFalse(stale['review_gate_passed_recorded'])

    def test_same_author_cannot_claim_independent_review(self):
        self.prepare()
        self.import_data(self.good_records())
        review = self.review_record(self.cli('audit'))
        review['reviewer'] = 'test-author'
        self.import_data({'omission_reviews': [review]})
        audit = self.cli('audit')
        self.assertIn('reviewer_not_independent', self.codes(audit))
        self.assertFalse(audit['review_gate_passed_recorded'])

    def test_review_cannot_skip_a_distinct_state(self):
        self.prepare()
        self.import_data(self.good_records())
        review = self.review_record(self.cli('audit'))
        review['checked_state_frames'] = [0, 3, 6]
        self.import_data({'omission_reviews': [review]})
        audit = self.cli('audit')
        self.assertIn('review_scope_incomplete', self.codes(audit))
        self.assertFalse(audit['review_gate_passed_recorded'])

    def test_schema_one_migrates_without_losing_old_records(self):
        self.prepare()
        self.import_data({'steps': [self.step('legacy', 0, 7, '1', '3', 0, 6)]})
        with closing(sqlite3.connect(self.work / 'review.sqlite3')) as conn:
            conn.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
            conn.execute('DROP TABLE IF EXISTS coverage')
            conn.execute('DROP TABLE IF EXISTS omission_reviews')
            conn.commit()
        self.cli('status')
        self.assertEqual(len(self.rows('SELECT * FROM steps')), 1)
        self.assertEqual(len(self.rows('SELECT * FROM views')), 4)
        audit = self.cli('audit')
        self.assertEqual(audit['coverage']['state_count'], 4)
        self.assertFalse(audit['review_gate_passed_recorded'])

    def test_export_includes_audit_and_does_not_claim_semantic_completeness(self):
        self.prepare()
        self.import_data(self.good_records())
        self.cli('export')
        data = json.loads((self.work / 'review.json').read_text(encoding='utf-8'))
        self.assertIn('coverage_audit', data)
        self.assertFalse(data['coverage_audit']['semantic_completeness_proven'])
        self.assertTrue((self.work / 'omission-audit.json').is_file())


if __name__ == '__main__':
    unittest.main()
