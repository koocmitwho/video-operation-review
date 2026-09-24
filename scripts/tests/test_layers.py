"""Observable layered contracts. View events here are SYNTHETIC bookkeeping only."""
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vor_store as store
import vor_media as media
from vor_audit import audit_omissions
from make_layered_fixture import make_tutorial


class LayerContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='vor layered 中文 ')
        cls.root = Path(cls.temp.name)
        cls.video = make_tutorial(cls.root/'input')
        with store.database(cls.root/'base', create=True) as conn:
            media.scan(conn, cls.root/'base', cls.video)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.work = self.root/self._testMethodName
        self.work.mkdir()
        (self.work/'logs').mkdir()
        with store.database(self.root/'base') as source, closing(sqlite3.connect(self.work/'review.sqlite3')) as dest:
            source.backup(dest)
        self.conn = store.connect(self.work)
        self.addCleanup(self.conn.close)

    def layers(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('vor_layers'), 'Layered workflow is missing')
        import vor_layers
        return vor_layers

    def seen(self, frames, actor='fixture-author'):
        media.extract(self.conn, self.work, frames)
        for n in frames:
            store.record_view(self.conn, self.work, f'f{n:09d}', actor, 'view_image',
                              'synthetic-test://not-real-view', 'Synthetic record; NOT actual model inspection.')

    def import_data(self, data):
        path = self.work/'records.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        store.import_records(self.conn, path)

    def interval(self, ident='I1', start=0, end=31):
        return dict(id=ident, start_frame=start, end_frame=end, phase='fixture waiting',
                    disposition='context', reason='Fixture-only coarse decision, not semantic proof',
                    reviewer='fixture-author', merge='approximate', fine_status='not_reviewed',
                    evidence=[f'f{start:09d}', f'f{end:09d}'], step_ids=[], issue_ids=[])

    def setup_interval(self):
        layers = self.layers()
        layers.prepare(self.conn, self.work)
        self.seen([0,31])
        self.import_data({'intervals': [self.interval()]})
        return layers

    def test_default_selection_is_layered_and_does_not_fake_review(self):
        store.select_candidates(self.conn)
        self.assertEqual(store.get_meta(self.conn, 'review_mode'), 'layered')
        s = store.status(self.conn)
        self.assertLess(s['candidate_frames'], 32)
        self.assertEqual(s['recorded_visual_unique_frames'], 0)
        self.assertEqual(s['coarse_reviewed_frames_recorded'], 0)

    def test_every_source_frame_maps_to_a_proposal_and_original_state(self):
        plan = self.layers().prepare(self.conn, self.work)
        members = [n for p in plan['segments'] for n in range(p['start_frame'], p['end_frame']+1)]
        self.assertEqual(members, list(range(32)))
        self.assertTrue(all(p['state_ranges'] and p['reason'] for p in plan['segments']))
        self.assertTrue(any(16 in p['representative_frames'] for p in plan['segments']))
        self.assertEqual(store.status(self.conn)['recorded_visual_unique_frames'], 0)

    def test_reprepare_reuses_plan_and_does_not_erase_authored_intervals(self):
        layers = self.setup_interval()
        before = self.conn.execute('SELECT payload FROM intervals').fetchone()[0]
        layers.prepare(self.conn, self.work)
        self.assertEqual(before, self.conn.execute('SELECT payload FROM intervals').fetchone()[0])
        self.assertEqual(len(list(self.conn.execute("SELECT * FROM attempts WHERE kind='scan'"))), 1)

    def test_coarse_coverage_is_separate_from_fine_and_visual_counts(self):
        self.setup_interval()
        s = store.status(self.conn)
        self.assertEqual(s['coarse_reviewed_frames_recorded'], 32)
        self.assertEqual(s['fine_reviewed_frames_recorded'], 0)
        self.assertEqual(s['recorded_visual_unique_frames'], 2)
        self.assertTrue(s['near_duplicate_merging'])
        self.assertEqual(s['candidate_pixel_equivalence'],'exact_consecutive_RGB_only')
        a = audit_omissions(self.conn, self.work)
        self.assertNotIn('unaccounted_state', {f['code'] for f in a['findings']})
        self.assertIn('interval_sample_missing', {f['code'] for f in a['findings']})

    def test_holes_and_overlap_are_reported(self):
        layers = self.layers(); layers.prepare(self.conn, self.work)
        self.seen([0,10,12,20,19,31])
        self.import_data({'intervals': [self.interval('a',0,10), self.interval('b',12,20), self.interval('c',19,31)]})
        codes = {f['code'] for f in audit_omissions(self.conn,self.work)['findings']}
        self.assertTrue({'interval_gap','interval_overlap'} <= codes)

    def test_unviewed_interval_and_false_exact_merge_fail(self):
        self.layers().prepare(self.conn, self.work)
        item = self.interval(); item['merge'] = 'exact'
        self.import_data({'intervals': [item]})
        a = audit_omissions(self.conn,self.work)
        self.assertIn('false_exact_merge', {f['code'] for f in a['findings']})
        self.assertEqual(a['coverage']['coarse_reviewed_frames_recorded'], 0)

    def test_samples_bind_content_and_anomaly_expands_only_local_window(self):
        layers = self.setup_interval()
        req = layers.sample_requirements(self.conn, self.interval())
        self.seen(req['frames'])
        sample = dict(id='C1', interval_id='I1', reviewer='fixture-author', scope_hash=req['scope_hash'],
                      method='risk_and_random', evidence=[f'f{n:09d}' for n in req['frames']],
                      reason='Synthetic sampling', conclusion='expand', resolves=[])
        self.import_data({'interval_checks': [sample]})
        a = audit_omissions(self.conn,self.work,queue=True)
        self.assertIn('sample_requires_expansion',{f['code'] for f in a['findings']})
        self.assertEqual(a['suggested_frames'], list(range(32)))
        item = self.interval(); item['reason'] = 'Changed interpretation'
        self.import_data({'intervals':[item]})
        self.assertIn('interval_sample_stale',{f['code'] for f in audit_omissions(self.conn,self.work)['findings']})

    def test_blank_or_subtitle_only_review_cannot_increment_visual_or_pass(self):
        self.layers().prepare(self.conn,self.work)
        self.import_data({'intervals':[self.interval()]})
        self.assertEqual(store.status(self.conn)['recorded_visual_unique_frames'],0)
        self.assertFalse(audit_omissions(self.conn,self.work)['review_gate_passed_recorded'])

    def clear_sample(self, layers):
        item=json.loads(self.conn.execute('SELECT payload FROM intervals WHERE id="I1"').fetchone()[0])
        req=layers.sample_requirements(self.conn,item)
        self.seen(req['frames'])
        sample=dict(id='C1',interval_id='I1',reviewer='fixture-author',scope_hash=req['scope_hash'],
                    method='risk_and_random',evidence=[f'f{n:09d}' for n in req['frames']],
                    reason='Synthetic risk-targeted and deterministic random sample',conclusion='clear',resolves=[])
        self.import_data({'interval_checks':[sample]})
        return sample

    def step(self):
        from test_omissions import OmissionContract
        step=OmissionContract.step('S1',0,31,'1.00','0.02',0,31)
        step['author']='fixture-author'
        step['role_evidence']={'before':['f000000000'],'during':['f000000020'],'after':['f000000031']}
        step['evidence'].append('f000000020')
        return step

    def test_operations_require_native_before_during_after_evidence(self):
        layers=self.setup_interval(); self.seen([20])
        item=self.interval(); item.update(disposition='operation',step_ids=['S1'],fine_status='reviewed')
        step=self.step(); del step['role_evidence']
        self.import_data({'intervals':[item],'steps':[step]}); self.clear_sample(layers)
        audit=audit_omissions(self.conn,self.work)
        self.assertIn('operation_roles_missing',{f['code'] for f in audit['findings']})
        self.assertEqual(audit['coverage']['fine_reviewed_frames_recorded'],0)

    def test_final_parameters_and_file_handoff_discontinuity_remain_blocking(self):
        layers=self.setup_interval(); self.seen([20])
        item=self.interval(); item.update(disposition='operation',step_ids=['S1','S2'],fine_status='reviewed')
        first=self.step(); first['end_frame']=20
        first['transition']['after']['A.rate']['value']='0.20'
        first['transition']['after']['file:exchange']={'value':'wrong.csv','evidence':['f000000020']}
        second=copy.deepcopy(first); second.update(id='S2',start_frame=21,end_frame=31)
        second['transition']['before']['file:exchange']={'value':'result.csv','evidence':['f000000031']}
        self.import_data({'intervals':[item],'steps':[first,second]}); self.clear_sample(layers)
        codes={f['code'] for f in audit_omissions(self.conn,self.work)['findings']}
        self.assertTrue({'final_parameter_mismatch','state_discontinuity'} <= codes)

    def test_current_interval_review_does_not_demand_every_rgb_state(self):
        layers=self.setup_interval(); self.clear_sample(layers)
        a=audit_omissions(self.conn,self.work)
        self.assertTrue(a['records_ready_for_omission_review'],a['findings'])
        frames=sorted({0,31,*layers.sample_requirements(self.conn,self.interval())['frames']})
        self.seen(frames,actor='fixture-reviewer')
        review=dict(id='R1',reviewer='fixture-reviewer',independence='independent',snapshot=a['snapshot'],
                    checked_interval_ids=['I1'],evidence=[f'f{n:09d}' for n in frames],
                    tool_trace_refs=['synthetic-test://not-real-view'],issue_ids=[],
                    conclusion='no_additional_omissions_found',note='Synthetic accounting only')
        self.import_data({'layer_reviews':[review]})
        passed=audit_omissions(self.conn,self.work)
        self.assertTrue(passed['review_gate_passed_recorded'],passed['findings'])
        self.assertLess(store.status(self.conn)['recorded_visual_unique_frames'],32)
        self.assertFalse(passed['semantic_completeness_proven'])
        item=self.interval(); item['phase']='changed annotation'; self.import_data({'intervals':[item]})
        self.assertEqual(audit_omissions(self.conn,self.work)['omission_review']['status'],'stale')

    def test_sample_cannot_be_filled_with_unrelated_or_overview_only_assets(self):
        layers=self.setup_interval()
        req=layers.sample_requirements(self.conn,self.interval())
        self.import_data({'interval_checks':[dict(id='C1',interval_id='I1',reviewer='fixture-author',
                          scope_hash=req['scope_hash'],method='risk_and_random',evidence=['f000000000'],
                          reason='Only endpoint viewed',conclusion='clear',resolves=[])]})
        self.assertIn('sample_evidence_incomplete',{f['code'] for f in audit_omissions(self.conn,self.work)['findings']})

    def test_layered_export_includes_mapping_samples_and_pending_fine_ranges(self):
        self.setup_interval()
        store.export_records(self.conn,self.work)
        report=json.loads((self.work/'review.json').read_text(encoding='utf-8'))
        self.assertIn('intervals',report)
        self.assertIn('interval_checks',report)
        self.assertEqual(report['status']['not_fine_reviewed_ranges'],[[0,31]])
        self.assertEqual(report['coverage_audit']['mode'],'layered')

    def test_overview_sheet_is_not_native_fine_evidence_and_views_dedupe(self):
        layers = self.layers(); layers.prepare(self.conn,self.work)
        media.extract(self.conn,self.work,[0,1])
        self.assertTrue(hasattr(layers,'make_sheet'), 'Need explicit overview viewing granularity')
        sheet=layers.make_sheet(self.conn,self.work,[0,1],thumb_width=320)
        self.assertEqual(store.status(self.conn)['recorded_visual_unique_frames'],0)
        layers.record_sheet_view(self.conn,self.work,sheet['id'],'fixture-author','synthetic-test://sheet',
                                 {'f000000000':'Synthetic panel 0','f000000001':'Synthetic panel 1'})
        s=store.status(self.conn)
        self.assertEqual(s['recorded_visual_unique_frames'],2)
        self.assertEqual(s['recorded_full_image_unique_frames'],0)
        self.seen([0])
        self.assertEqual(store.status(self.conn)['recorded_visual_unique_frames'],2)
        self.assertEqual(store.status(self.conn)['recorded_full_image_unique_frames'],1)

    def test_legacy_migration_preserves_records_and_mode(self):
        self.conn.execute("UPDATE meta SET value='2' WHERE key='schema_version'")
        self.conn.execute("DELETE FROM meta WHERE key='review_mode'")
        self.conn.commit(); self.conn.close()
        self.conn=store.connect(self.work); self.addCleanup(self.conn.close)
        self.assertEqual(store.get_meta(self.conn,'schema_version'),3)
        self.assertEqual(store.get_meta(self.conn,'review_mode'),'strict')
        self.assertEqual(store.status(self.conn)['computed_frames'],32)

    def test_public_cli_exposes_layer_plan_mapping_and_language_tracks(self):
        cli=Path(__file__).resolve().parents[1]/'review_video.py'
        for args in [('plan',),('intervals',),('tracks',)]:
            p=subprocess.run([sys.executable,str(cli),*args,'--work',str(self.work)],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertIsInstance(json.loads(p.stdout),dict)
        self.assertTrue((self.work/'layer-plan.json').exists())

    def test_retiring_or_shrinking_interval_cannot_erase_sample_anomaly(self):
        layers=self.setup_interval(); sample=self.clear_sample(layers)
        sample.update(id='bad',conclusion='expand')
        self.import_data({'interval_checks':[sample]})
        self.seen([30])
        self.import_data({'retire_intervals':['I1'],'intervals':[self.interval('small',30,31)]})
        req=layers.sample_requirements(self.conn,self.interval('small',30,31))
        self.import_data({'interval_checks':[dict(id='fake-fix',interval_id='small',reviewer='fixture-author',
            scope_hash=req['scope_hash'],method='exhaustive',evidence=['f000000030','f000000031'],
            reason='Shrank interval without looking at original anomaly',conclusion='clear',resolves=['bad'])]})
        codes={f['code'] for f in audit_omissions(self.conn,self.work)['findings']}
        self.assertIn('expansion_scope_incomplete',codes)

    def test_tampered_sheet_and_overview_in_strict_mode_are_detected(self):
        layers=self.layers(); layers.prepare(self.conn,self.work)
        media.extract(self.conn,self.work,[0,1]); sheet=layers.make_sheet(self.conn,self.work,[0,1])
        layers.record_sheet_view(self.conn,self.work,sheet['id'],'fixture-author','synthetic-test://sheet',
                                 {'f000000000':'Synthetic panel 0','f000000001':'Synthetic panel 1'})
        self.import_data({'coverage':[dict(frame_no=0,classification='context',step_ids=[],issue_ids=[],
            reason='Synthetic',reviewer='fixture-author',evidence=['f000000000'])]})
        strict=audit_omissions(self.conn,self.work,mode='strict')
        with self.subTest('strict requires native'):
            self.assertIn('state_full_view_missing',{f['code'] for f in strict['findings']})
        Path(sheet['absolute_path']).write_bytes(b'changed')
        with self.subTest('sheet bytes pinned'):
            self.assertFalse(store.validate(self.conn,self.work)['valid'])

    def test_new_valid_sample_supersedes_stale_clear_sample(self):
        layers=self.setup_interval(); self.clear_sample(layers)
        item=self.interval(); item['reason']='Updated coarse interpretation'
        self.import_data({'intervals':[item]})
        req=layers.sample_requirements(self.conn,item); self.seen(req['frames'])
        self.import_data({'interval_checks':[dict(id='C2',interval_id='I1',reviewer='fixture-author',
            scope_hash=req['scope_hash'],method='risk_and_random',evidence=[f'f{n:09d}' for n in req['frames']],
            reason='Rechecked new content',conclusion='clear',resolves=[])]})
        self.assertTrue(audit_omissions(self.conn,self.work)['records_ready_for_omission_review'])

    def test_sparse_evidence_mapping_does_not_rescan_entire_long_index(self):
        layers=self.layers()
        with self.conn:
            self.conn.executemany('INSERT INTO frames(frame_no,time_source,digest,exact_start) VALUES (?,?,?,?)',
                                 [(n,'missing','synthetic-index-only',n) for n in range(32,20032)])
        # A bounded SQL VM budget exposes accidental full-index scans for two sparse frame IDs.
        self.conn.set_progress_handler(lambda: 1,1000)
        try:
            result=layers.covered_targets(self.conn,{0,20031},{0})
        except sqlite3.OperationalError as exc:
            self.fail('Sparse evidence mapping exhausted SQL work budget: '+str(exc))
        finally:
            self.conn.set_progress_handler(None,0)
        self.assertEqual(result,{0})

    def test_partial_operation_distinguishes_examined_from_completed_fine_review(self):
        self.setup_interval(); self.seen([20])
        item=self.interval(); item.update(disposition='operation',step_ids=['S1'],fine_status='partial')
        step=self.step(); step.update(status='partial',uncertainties=['Click is not visible'])
        self.import_data({'intervals':[item],'steps':[step]})
        stats=store.status(self.conn)
        self.assertEqual(stats.get('fine_examined_frames_recorded'),32)
        self.assertEqual(stats['fine_reviewed_frames_recorded'],0)
        self.assertEqual(stats['recorded_visual_unique_frames'],3)

if __name__ == '__main__': unittest.main()
