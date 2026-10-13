"""Cross-recording support cannot rewrite an original recording's missing event."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from test_record_contract import RecordFixture, ROOT, step
from vor_supplements import import_supplement, record_supplement_view
import vor_store as store


class FollowupIntegration(RecordFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.other = self.work / 'other'
        self.source = store.connect(self.other, create=True)
        self.addCleanup(self.source.close)
        video = self.other / 'source.mkv'
        video.write_bytes((ROOT / 'examples/tutorial/tutorial.mkv').read_bytes() + b'\0')
        store.set_meta(self.source, 'source', store.source_file_identity(video)[0])
        self.source.execute('INSERT INTO frames(frame_no,time_s,pts_time,time_source,width,height) VALUES(0,0,"0","pts",800,450)')
        asset = self.other / 'full.png'
        shutil.copyfile(ROOT / 'examples/tutorial/evidence/f000000004.png', asset)
        self.source.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?,?)',
                            ('later0',0,'full',asset.name,store.sha256(asset),None,None,store.now()))
        self.source.commit()
        store.record_view(self.source,self.other,'later0','source-author','image_tool','synthetic-test://source','Synthetic fixture.')
        store.export_records(self.source,self.other)

    def issue(self):
        return dict(id='Q1',status='blocked',question='Was the later result displayed?',attempts=[],
                    followup=dict(claim='A separate recording displays the later result.',
                                  original_record_limit='The original clip still omits that result.',
                                  reviewer='followup-author',
                                  supplement_refs=[dict(supplement_id='later',asset_id='later0')]))

    def prepare(self):
        import_supplement(self.conn,self.work,self.other,'later',['later0'],'importer','Separate source')
        record_supplement_view(self.conn,self.work,'later','later0','followup-author','image_tool',
                               'synthetic-test://local-supplement','Synthetic fixture, not actual visual acceptance.')

    def test_new_followup_requires_reasoned_shape_and_existing_viewed_reference(self):
        original=self.issue()
        cases=[dict(original,followup=[])]
        for key in ('claim','original_record_limit','reviewer','supplement_refs'):
            item=copy.deepcopy(original);item['followup'].pop(key);cases.append(item)
        cases.append(original)
        for item in cases:
            before=self.database_snapshot()
            with self.subTest(item=item):
                with self.assertRaisesRegex(ValueError,'followup|supplement'):
                    self.import_data({'issues':[item]})
                self.assertEqual(before,self.database_snapshot())

    def test_followup_cannot_borrow_another_reviewers_view(self):
        self.prepare();item=self.issue();item['followup']['reviewer']='someone-else'
        with self.assertRaisesRegex(ValueError,'supplement'):
            self.import_data({'issues':[item]})

    def test_valid_followup_is_exported_separately_without_resolving_original_gap(self):
        self.prepare();self.import_data({'issues':[self.issue()]})
        out=store.export_records(self.conn,self.work)
        data=json.loads((self.work/'review.json').read_text(encoding='utf-8'))
        self.assertEqual(len(data.get('supplements',[])),1)
        self.assertEqual(data['issues'][0]['payload']['status'],'blocked')
        self.assertEqual([i['id'] for i in data['status']['unresolved_issues']],['Q1'])
        self.assertTrue(out['validation_passed']);self.assertFalse(out['review_complete'])
        report=(self.work/'report.md').read_text(encoding='utf-8')
        for phrase in ['后续资料','原片','A separate recording displays','supplements/later/','later0']:
            self.assertIn(phrase,report)

    def test_archive_damage_invalidates_existing_followup_and_export(self):
        self.prepare();self.import_data({'issues':[self.issue()]})
        path=self.work/'supplements/later/source-review.json'
        path.write_text('{}',encoding='utf-8')
        result=store.validate(self.conn,self.work)
        self.assertFalse(result['valid'])
        self.assertTrue(any('supplement' in error['code'] for error in result['errors']))
        out=store.export_records(self.conn,self.work)
        self.assertFalse(out['validation_passed'])

    def test_supplement_identity_is_bound_to_both_review_and_replay_snapshots(self):
        from vor_audit import content_snapshot
        before=content_snapshot(self.conn)
        delivery=store.status(self.conn)['delivery_snapshot']
        self.prepare()
        self.assertNotEqual(before,content_snapshot(self.conn))
        self.assertNotEqual(delivery,store.status(self.conn)['delivery_snapshot'])

    def test_retirement_archive_keeps_supplement_references_in_integrity_checks(self):
        self.prepare();original=self.issue();original['step_ids']=['S0']
        self.import_data({'steps':[step('S0')],'issues':[original]})
        reassigned=copy.deepcopy(original);reassigned['step_ids']=['S1']
        self.import_data({'steps':[step('S1')],'issues':[reassigned],
                          'retire_steps':[dict(id='S0',reason='Correction fixture',reviewer='corrector',replacement_step_ids=['S1'])]})
        reassigned.pop('followup');self.import_data({'issues':[reassigned]})
        saved=store.get_meta(self.conn,'supplements');saved[0]['views']=[]
        store.set_meta(self.conn,'supplements',saved);self.conn.commit()
        result=store.validate(self.conn,self.work)
        self.assertFalse(result['valid'])
        self.assertTrue(any('S0.references_before' in error['reference'] for error in result['errors']))

    def test_cli_queue_and_supplement_operations_are_available(self):
        cli=ROOT/'scripts/review_video.py'
        p=subprocess.run([sys.executable,'-X','utf8','-B',str(cli),'queue','--work',str(self.work)],
                         capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(json.loads(p.stdout)['total_pending'],0)
        p=subprocess.run([sys.executable,'-X','utf8','-B',str(cli),'supplement-import','--work',str(self.work),
                          '--source-review',str(self.other),'--id','cli-later','--assets','later0',
                          '--actor','fixture','--note','Separate source fixture'],
                         capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertTrue(json.loads(p.stdout)['valid'])
