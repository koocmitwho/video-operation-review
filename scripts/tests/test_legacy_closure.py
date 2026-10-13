"""Legacy issue closures must not imply completion. All view rows are synthetic."""
import json
import unittest

from test_record_contract import RecordFixture, step
import vor_store as store
from vor_audit import audit_omissions
from vor_layers import sample_requirements
from vor_record_contract import check_issue


class LegacyClosureContract(RecordFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.conn.execute("UPDATE frames SET digest='fixture',exact_start=0")
        for key, value in [('video_total_frames', 2), ('index_complete_clean', True),
                           ('scan_complete_clean', True), ('selection_performed', True)]:
            store.set_meta(self.conn, key, value)
        self.conn.execute('INSERT INTO candidates VALUES (?,?,?)', (0, '[]', '[0]'))
        self.conn.commit()
        store.record_view(self.conn, self.work, 'f0', 'independent-fixture', 'image_tool',
                          'synthetic-test://legacy-closure', 'Synthetic bookkeeping, not actual inspection.')

    def legacy_issue(self, **extra):
        issue = dict(id='Q-legacy', question='Was this outcome established?', status='resolved',
                     attempts=[dict(note='Historical check had no recorded conclusion', evidence=['f0'])], **extra)
        self.conn.execute('INSERT INTO issues VALUES (?,?)', (issue['id'], store.dump(issue)))
        self.conn.commit()  # Simulate an existing ledger; new imports correctly reject this shape.
        return issue

    def context(self):
        return dict(id='I1', start_frame=0, end_frame=1, phase='Synthetic context',
                    disposition='context', reason='Synthetic single-state fixture', reviewer='synthetic',
                    merge='exact', fine_status='not_reviewed', evidence=['f0'], step_ids=[], issue_ids=[])

    def setup_current_review(self, mode, issue_ids):
        if mode == 'layered':
            interval = self.context()
            self.import_data({'intervals': [interval]})
            sample = sample_requirements(self.conn, interval)
            self.import_data({'interval_checks': [dict(
                id='C1', interval_id='I1', reviewer='synthetic', scope_hash=sample['scope_hash'],
                method='risk_and_random', evidence=['f0'], reason='Synthetic state sample',
                conclusion='clear', resolves=[])]})
            table, scope = 'layer_reviews', dict(checked_interval_ids=['I1'])
        else:
            self.import_data({'coverage': [dict(frame_no=0, classification='context', step_ids=[], issue_ids=[],
                                               reason='Synthetic static context', evidence=['f0'], reviewer='synthetic')]})
            table, scope = 'omission_reviews', dict(checked_state_frames=[0])
        snapshot = audit_omissions(self.conn, self.work, mode=mode)['snapshot']
        review = dict(id='R1', reviewer='independent-fixture', independence='independent', snapshot=snapshot,
                      evidence=['f0'], tool_trace_refs=['synthetic-test://legacy-closure'], issue_ids=issue_ids,
                      conclusion='no_additional_omissions_found', note='Synthetic bookkeeping only', **scope)
        self.import_data({table: [review]})

    def check_legacy_review(self, mode):
        self.setup_current_review(mode, [])
        self.assertTrue(store.validate(self.conn, self.work, mode=mode)['review_complete'])
        issue = self.legacy_issue()
        self.assertEqual(check_issue(issue), [])
        self.setup_current_review(mode, [issue['id']])
        audit = audit_omissions(self.conn, self.work, mode=mode)
        self.assertIn('review_issue_unresolved', {f['code'] for f in audit['findings']})
        self.assertEqual(audit['omission_review']['status'], 'needs_followup')
        self.assertFalse(audit['review_gate_passed_recorded'])
        result = store.validate(self.conn, self.work, require_coverage=True, mode=mode)
        self.assertTrue(result['valid'], result['errors'])
        self.assertFalse(result['review_complete'])
        self.assertEqual(result['status']['unresolved_issues'], [issue])
        self.assertEqual(json.loads(self.conn.execute('SELECT payload FROM issues').fetchone()[0]), issue)

    def test_legacy_closure_keeps_strict_review_valid_but_incomplete(self):
        self.check_legacy_review('strict')

    def test_legacy_closure_keeps_layered_review_valid_but_incomplete(self):
        self.check_legacy_review('layered')

    def test_legacy_closure_keeps_examined_operation_out_of_completed_count(self):
        operation = dict(step(), status='confirmed', uncertainties=[], author='synthetic',
                         role_evidence={role: ['f0'] for role in ('before', 'during', 'after')})
        interval = dict(self.context(), disposition='operation', fine_status='reviewed', step_ids=['S1'])
        self.import_data({'steps': [operation], 'intervals': [interval]})
        self.assertEqual(store.status(self.conn)['fine_reviewed_frames_recorded'], 2)
        issue = self.legacy_issue(step_ids=['S1'])
        result = store.validate(self.conn, self.work)
        self.assertTrue(result['valid'], result['errors'])
        self.assertEqual(result['status']['fine_examined_frames_recorded'], 2)
        self.assertEqual(result['status']['fine_reviewed_frames_recorded'], 0)
        self.assertEqual(result['status']['unresolved_issues'], [issue])

    def test_retirement_cannot_discard_legacy_closure_with_no_recorded_basis(self):
        original = dict(step('S0'), status='confirmed', uncertainties=[])
        self.import_data({'steps': [original]})
        self.legacy_issue(start_frame=0, end_frame=1)
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'unresolved issue'):
            self.import_data({'retire_steps': [dict(id='S0', reviewer='synthetic',
                reason='Static input is not an action', replacement_step_ids=[])]})
        self.assertEqual(self.database_snapshot(), before)


if __name__ == '__main__':
    unittest.main()
