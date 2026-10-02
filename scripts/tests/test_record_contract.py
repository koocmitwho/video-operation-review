"""Negative record-contract regressions; all view rows are synthetic bookkeeping."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vor_store as store

ROOT = Path(__file__).resolve().parents[2]


def step(ident='S1'):
    return dict(id=ident, phase='fixture', start_frame=0, end_frame=1, software='fixture',
                module='fixture', menu_path=[], selected_objects=[], final_parameters={},
                confirmation_action='not shown', visible_result='unknown', input_files=[],
                output_files=[], evidence=['f0'], uncertainties=['fixture only'], status='partial')


class RecordFixture:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='vor record contract ')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.conn = store.connect(self.work, create=True)
        self.addCleanup(self.conn.close)
        source = self.work / 'source.mkv'
        shutil.copyfile(ROOT / 'examples/tutorial/tutorial.mkv', source)
        store.set_meta(self.conn, 'source', store.source_file_identity(source)[0])
        self.conn.executemany('INSERT INTO frames(frame_no,time_s,pts_time,time_source,width,height) '
                              'VALUES (?,?,?,?,?,?)', [(0, 0, '0', 'pts', 800, 450), (1, .5, '.5', 'pts', 800, 450)])
        asset = self.work / 'evidence.png'
        shutil.copyfile(ROOT / 'examples/tutorial/evidence/f000000004.png', asset)
        self.conn.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?,?)',
                          ('f0', 0, 'full', asset.name, store.sha256(asset), None, None, store.now()))
        self.conn.commit()
        store.record_view(self.conn, self.work, 'f0', 'synthetic', 'image_tool',
                          'synthetic-test://record-contract', 'Synthetic bookkeeping; not a real image view.')

    def import_data(self, data):
        file = self.work / 'records.json'
        file.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return store.import_records(self.conn, file)

    def database_snapshot(self):
        return '\n'.join(self.conn.iterdump())


class RecordContract(RecordFixture, unittest.TestCase):
    def test_known_extensions_reject_wrong_shapes_without_mutating_database(self):
        cases = [('role_evidence', []), ('role_evidence', {'before': 'f0'}),
                 ('transition', []), ('transition', {'after': []}),
                 ('transition', {'before': {'rate': []}}),
                 ('transition', {'confirmation': []}), ('transition', {'result': {'status': []}})]
        self.import_data({'steps': [step('existing')]})
        before = self.database_snapshot()
        for field, value in cases:
            with self.subTest(field=field, value=value):
                entry = step(); entry[field] = value
                with self.assertRaisesRegex(ValueError, r'steps\[0\]\.' + field):
                    self.import_data({'steps': [entry]})
                self.assertEqual(before, self.database_snapshot())

    def test_same_batch_duplicate_steps_or_issues_rejected_before_any_write(self):
        for table, record in [('steps', step()), ('issues', dict(id='Q1', question='Unknown?', status='open', attempts=[]))]:
            with self.subTest(table=table):
                before = self.database_snapshot()
                with self.assertRaisesRegex(ValueError, r'duplicate.*id|Duplicate.*ID'):
                    self.import_data({table: [record, copy.deepcopy(record)]})
                self.assertEqual(before, self.database_snapshot())

    def test_issue_id_and_question_need_nonempty_strings(self):
        for field in ('id', 'question'):
            for value in (None, '', ' ', 3, ['x']):
                with self.subTest(field=field, value=value):
                    record = dict(id='Q1', question='Unknown?', status='open', attempts=[])
                    record[field] = value
                    before = self.database_snapshot()
                    with self.assertRaisesRegex(ValueError, r'issues\[0\]\.' + field):
                        self.import_data({'issues': [record]})
                    self.assertEqual(before, self.database_snapshot())

    def test_later_valid_record_update_and_unknown_extensions_are_preserved(self):
        entry = step(); entry['future_extension'] = {'opaque': [1, {'new': True}]}
        self.import_data({'steps': [entry]})
        entry['visible_result'] = 'Changed observation, still not a success claim'
        self.import_data({'steps': [entry]})
        self.import_data({'steps': [entry]})
        rows = list(self.conn.execute('SELECT payload FROM steps'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0][0]), entry)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM history').fetchone()[0], 3)

    def test_non_object_step_and_nonfinite_json_fail_with_record_path(self):
        for entry in (None, [], 'not a record'):
            with self.subTest(entry=entry):
                with self.assertRaisesRegex(ValueError, r'steps\[0\]'):
                    self.import_data({'steps': [entry]})
        entry = step(); entry['final_parameters'] = {'rate': float('nan')}
        with self.assertRaisesRegex(ValueError, r'finite|NaN|JSON'):
            self.import_data({'steps': [entry]})

    def test_legacy_malformed_step_validate_returns_diagnostic_and_export_preserves_files(self):
        store.export_records(self.conn, self.work)
        old_report = (self.work / 'report.md').read_bytes()
        entry = step(); entry['role_evidence'] = ['wrong']
        self.conn.execute('INSERT INTO steps VALUES (?,?)', ('S1', store.dump(entry)))
        self.conn.commit()
        result = store.validate(self.conn, self.work, require_coverage=True)
        self.assertFalse(result['valid'])
        self.assertFalse(result['review_complete'])
        self.assertTrue(any(e['code'] == 'invalid_step' and 'role_evidence' in e['message'] for e in result['errors']))
        with self.assertRaisesRegex(ValueError, 'role_evidence'):
            store.export_records(self.conn, self.work)
        self.assertEqual((self.work / 'report.md').read_bytes(), old_report)
        self.assertEqual(json.loads(self.conn.execute('SELECT payload FROM steps').fetchone()[0]), entry)

    def test_legacy_null_issue_and_non_object_payload_remain_inspectable(self):
        self.conn.execute('INSERT INTO issues VALUES (?,?)', (None, store.dump(dict(id=None, question='Unknown?', status='open', attempts=[]))))
        self.conn.execute('INSERT INTO steps VALUES (?,?)', ('broken', '[]'))
        self.conn.commit()
        result = store.validate(self.conn, self.work, require_coverage=True)
        self.assertFalse(result['valid'])
        self.assertTrue({'invalid_step', 'invalid_issue'} <= {e['code'] for e in result['errors']})
        state = store.status(self.conn)
        self.assertTrue(state['record_contract_errors'])
        self.assertFalse(state['annotation_counts_available'])

    def test_frame_ordinals_outside_sqlite_range_are_rejected_before_commit(self):
        for field in ('start_frame', 'end_frame'):
            with self.subTest(field=field):
                entry = step(); entry[field] = 2 ** 63
                if field == 'start_frame':
                    entry['end_frame'] = 2 ** 63
                before = self.database_snapshot()
                with self.assertRaisesRegex(ValueError, r'frame'):
                    self.import_data({'steps': [entry]})
                self.assertEqual(before, self.database_snapshot())
        entry = step(); entry.update(start_frame=2 ** 63, end_frame=2 ** 63)
        self.conn.execute('INSERT INTO steps VALUES (?,?)', ('S1', store.dump(entry)))
        self.conn.commit()
        result = store.validate(self.conn, self.work, require_coverage=True)
        self.assertFalse(result['valid'])
        self.assertIn('invalid_step', {e['code'] for e in result['errors']})

    def test_large_parameter_numbers_are_not_confused_with_sqlite_frame_ordinals(self):
        entry = step(); entry['final_parameters'] = {'arbitrary_integer': {'value': 10 ** 30, 'evidence': ['f0']}}
        self.import_data({'steps': [entry]})
        saved = json.loads(self.conn.execute('SELECT payload FROM steps').fetchone()[0])
        self.assertEqual(saved['final_parameters']['arbitrary_integer']['value'], 10 ** 30)


if __name__ == '__main__':
    unittest.main()
