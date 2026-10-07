"""Step correction preserves provenance; fixture views are synthetic bookkeeping."""
import copy
import json
import unittest

from test_record_contract import RecordFixture, step
import vor_store as store
from vor_audit import audit_omissions, content_snapshot


class StepRetirementContract(RecordFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.conn.execute("UPDATE frames SET digest='fixture',exact_start=0")
        self.conn.commit()
        self.original = step('S0')
        self.original.update(uncertainties=[], status='confirmed', phase='Mistaken static precondition')
        self.import_data({'steps': [self.original]})

    def correction(self, replacements=None):
        return dict(id='S0', reason='Static initial state belongs to the real operation precondition.',
                    reviewer='corrector', replacement_step_ids=replacements or [])

    def interval(self):
        return dict(id='I0', start_frame=0, end_frame=1, phase='Initial state',
                    disposition='context', reason='No action is shown here.', reviewer='synthetic',
                    merge='exact', fine_status='not_reviewed', evidence=['f0'], step_ids=['S0'], issue_ids=[])

    def test_retirement_archives_original_and_leaves_source_assets_views_unchanged(self):
        pinned = {t: list(self.conn.execute(f'SELECT * FROM {t}')) for t in ('frames', 'assets', 'views', 'meta')}
        before = content_snapshot(self.conn)
        self.import_data({'retire_steps': [self.correction()]})
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM steps').fetchone()[0], 0)
        archived = json.loads(self.conn.execute('SELECT payload FROM step_retirements WHERE id="S0"').fetchone()[0])
        self.assertEqual(archived['original_step'], self.original)
        self.assertEqual(archived['reason'], self.correction()['reason'])
        self.assertEqual(archived['reviewer'], 'corrector')
        self.assertTrue(archived['recorded_at'])
        self.assertNotEqual(before, content_snapshot(self.conn))
        for table, rows in pinned.items():
            self.assertEqual(rows, list(self.conn.execute(f'SELECT * FROM {table}')))
        history = [json.loads(r[0]) for r in self.conn.execute("SELECT payload FROM history WHERE kind='retired_step'")]
        self.assertEqual(history, [archived])

    def test_retirement_requires_complete_reasoned_request_and_existing_id(self):
        for changes in ({'reason': ''}, {'reviewer': ' '}, {'replacement_step_ids': 'S1'},
                        {'id': 'missing'}, {'replacement_step_ids': ['missing']},
                        {'replacement_step_ids': ['S0']}, {'replacement_step_ids': ['S1', 'S1']}):
            with self.subTest(changes=changes):
                request = self.correction(); request.update(changes)
                before = self.database_snapshot()
                with self.assertRaisesRegex(ValueError, 'retire_steps|retirement|replacement'):
                    self.import_data({'retire_steps': [request]})
                self.assertEqual(before, self.database_snapshot())
        for request in (None, [], {}, {'id': 'S0', 'reason': 'x', 'reviewer': 'x'}):
            with self.subTest(request=request):
                with self.assertRaisesRegex(ValueError, 'retire_steps'):
                    self.import_data({'retire_steps': [request]})
        with self.assertRaisesRegex(ValueError, 'retire_steps'):
            self.import_data({'retire_steps': 'S0'})

    def test_all_active_links_require_explicit_handling_and_archive_before_after(self):
        interval = self.interval()
        issue = dict(id='Q0', status='resolved', question='Was the field readable?',
                     step_ids=['S0'], attempts=[])
        coverage = dict(frame_no=0, classification='context', reason='Initial state',
                        reviewer='synthetic', evidence=['f0'], step_ids=['S0'], issue_ids=[])
        self.import_data({'intervals': [interval], 'issues': [issue], 'coverage': [coverage]})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'reference|link'):
            self.import_data({'retire_steps': [self.correction()]})
        self.assertEqual(before, self.database_snapshot())
        changed = {key: copy.deepcopy(value) for key, value in
                   [('intervals', interval), ('issues', issue), ('coverage', coverage)]}
        for record in changed.values():
            record['step_ids'] = []
        self.import_data(dict(retire_steps=[self.correction()], **{k: [v] for k, v in changed.items()}))
        archived = json.loads(self.conn.execute('SELECT payload FROM step_retirements').fetchone()[0])
        self.assertEqual(archived['references_before']['intervals'], [interval])
        self.assertEqual(archived['references_before']['issues'], [issue])
        self.assertEqual(archived['references_before']['coverage'], [coverage])
        self.assertEqual(archived['references_after']['intervals'], [changed['intervals']])

    def test_replacement_and_link_updates_are_atomic_even_after_late_failure(self):
        replacement = step('S1')
        bad_check = dict(id='C0', interval_id='missing', scope_hash='bad', reviewer='synthetic',
                         method='exhaustive', evidence=['f0'], reason='Synthetic', conclusion='clear')
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'unknown interval'):
            self.import_data(dict(steps=[replacement], retire_steps=[self.correction(['S1'])],
                                  interval_checks=[bad_check]))
        self.assertEqual(before, self.database_snapshot())
        self.import_data(dict(steps=[replacement], retire_steps=[self.correction(['S1'])]))
        self.assertEqual([r[0] for r in self.conn.execute('SELECT id FROM steps')], ['S1'])

    def test_retired_id_cannot_be_reimported_or_re_retired(self):
        self.import_data({'retire_steps': [self.correction()]})
        before = self.database_snapshot()
        for data in ({'steps': [self.original]}, {'retire_steps': [self.correction()]}):
            with self.subTest(data=data):
                with self.assertRaisesRegex(ValueError, 'retired|retirement'):
                    self.import_data(data)
                self.assertEqual(before, self.database_snapshot())

    def test_conflicting_duplicate_and_cyclic_retirement_batch_is_rejected(self):
        other = step('S1'); other.update(uncertainties=[], status='confirmed')
        self.import_data({'steps': [other]})
        second = self.correction(['S0']); second['id'] = 'S1'
        for data in ({'retire_steps': [self.correction(), self.correction()]},
                     {'steps': [self.original], 'retire_steps': [self.correction()]},
                     {'retire_steps': [self.correction(['S1']), second]}):
            with self.subTest(data=data):
                before = self.database_snapshot()
                with self.assertRaisesRegex(ValueError, 'retire_steps|retirement|replacement'):
                    self.import_data(data)
                self.assertEqual(before, self.database_snapshot())

    def test_unresolved_issue_cannot_be_closed_hidden_or_detached_by_retirement(self):
        issue = dict(id='Q0', status='open', question='Was the value actually applied?',
                     start_frame=0, end_frame=1, step_ids=['S0'], attempts=[{'conclusion': 'Still unknown'}])
        replacement = step('S1')
        self.import_data({'issues': [issue]})
        before = self.database_snapshot()
        for changes in ({'status': 'resolved', 'step_ids': ['S1']}, {'step_ids': []},
                        {'step_ids': ['S1'], 'attempts': []}, {'step_ids': ['S1'], 'question': 'Changed'}):
            with self.subTest(changes=changes):
                changed = dict(issue, **changes)
                with self.assertRaisesRegex(ValueError, 'unresolved|issue'):
                    self.import_data(dict(steps=[replacement], issues=[changed], retire_steps=[self.correction(['S1'])]))
                self.assertEqual(before, self.database_snapshot())
        changed = dict(issue, step_ids=['S1'])
        self.import_data(dict(steps=[replacement], issues=[changed], retire_steps=[self.correction(['S1'])]))
        self.assertEqual(store.status(self.conn)['unresolved_issues'], [changed])

    def test_range_linked_issue_and_inline_uncertainty_must_survive(self):
        issue = dict(id='Q0', status='blocked', question='Result missing', start_frame=0, end_frame=1, attempts=[])
        self.import_data({'issues': [issue]})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'unresolved|issue'):
            self.import_data({'retire_steps': [self.correction()]})
        self.assertEqual(before, self.database_snapshot())
        self.import_data({'issues': [dict(issue, status='resolved')]})
        self.import_data({'steps': [dict(self.original, uncertainties=['Unconfirmed action'], status='partial')]})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'uncertaint'):
            self.import_data({'retire_steps': [self.correction()]})
        self.assertEqual(before, self.database_snapshot())
        replacement = dict(step('S1'), uncertainties=['Unconfirmed action'])
        self.import_data(dict(steps=[replacement], retire_steps=[self.correction(['S1'])]))

    def test_retirement_and_interval_removal_do_not_erase_expansion_anomaly(self):
        from vor_layers import sample_requirements
        interval = self.interval()
        self.import_data({'intervals': [interval]})
        check = dict(id='C0', interval_id='I0', scope_hash=sample_requirements(self.conn, interval)['scope_hash'],
                     reviewer='synthetic', method='risk_and_random', reason='Unexpected state',
                     evidence=['f0'], conclusion='expand')
        self.import_data({'interval_checks': [check]})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'anomal|expand'):
            self.import_data({'retire_steps': [self.correction()], 'retire_intervals': ['I0']})
        self.assertEqual(before, self.database_snapshot())
        replacement = step('S1')
        self.import_data(dict(steps=[replacement], retire_steps=[self.correction(['S1'])], retire_intervals=['I0']))
        codes = {f['code'] for f in audit_omissions(self.conn, self.work)['findings']}
        self.assertIn('retired_interval_anomaly', codes)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM interval_checks').fetchone()[0], 1)

    def test_export_has_only_current_steps_and_traceable_retirement(self):
        replacement = step('S1')
        self.import_data(dict(steps=[replacement], retire_steps=[self.correction(['S1'])]))
        store.export_records(self.conn, self.work)
        report = json.loads((self.work / 'review.json').read_text(encoding='utf-8'))
        self.assertEqual([r['id'] for r in report['steps']], ['S1'])
        self.assertEqual(report['step_retirements'][0]['payload']['original_step'], self.original)
        text = (self.work / 'report.md').read_text(encoding='utf-8')
        self.assertIn('步骤纠错历史', text)
        self.assertIn(self.correction()['reason'], text)
        self.assertNotIn('Mistaken static precondition', text.split('## 附录')[0])

    def test_existing_review_becomes_stale_in_both_review_modes(self):
        for mode, table in [('layered', 'layer_reviews'), ('strict', 'omission_reviews')]:
            snapshot = audit_omissions(self.conn, self.work, mode=mode)['snapshot']
            review = dict(id='R0', reviewer='independent-fixture', independence='independent',
                          snapshot=snapshot, note='Synthetic previous review', evidence=['f0'],
                          tool_trace_refs=['synthetic-test://record-contract'], issue_ids=[],
                          checked_interval_ids=[], checked_state_frames=[0], conclusion='no_additional_omissions_found')
            self.import_data({table: [review]})
        self.import_data({'retire_steps': [self.correction()]})
        for mode in ('layered', 'strict'):
            with self.subTest(mode=mode):
                audit = audit_omissions(self.conn, self.work, mode=mode)
                self.assertEqual(audit['omission_review']['status'], 'stale')
                self.assertFalse(audit['review_gate_passed_recorded'])

    def test_retirement_cannot_remove_unresolved_step_status(self):
        original = dict(self.original, status='unresolved')
        self.import_data({'steps': [original]})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            self.import_data({'retire_steps': [self.correction()]})
        self.assertEqual(before, self.database_snapshot())
        confirmed = dict(step('S1'), status='confirmed', uncertainties=[])
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            self.import_data(dict(steps=[confirmed], retire_steps=[self.correction(['S1'])]))
        self.assertEqual(before, self.database_snapshot())
        self.import_data(dict(steps=[step('S1')], retire_steps=[self.correction(['S1'])]))

    def test_retired_original_evidence_integrity_still_participates_in_validation(self):
        broken = dict(self.original, evidence=['missing-asset'])
        self.import_data({'steps': [broken]})
        self.assertFalse(store.validate(self.conn, self.work)['valid'])
        self.import_data({'retire_steps': [self.correction()]})
        result = store.validate(self.conn, self.work)
        self.assertFalse(result['valid'])
        self.assertIn('unknown_evidence', {e['code'] for e in result['errors']})

    def test_unresolved_issue_keeps_unaffected_links_when_retired_link_is_replaced(self):
        issue = dict(id='Q0', status='open', question='Shared question', step_ids=['S0', 'S9'], attempts=[])
        self.import_data({'issues': [issue], 'steps': [step('S9')]})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'unresolved|issue'):
            self.import_data(dict(steps=[step('S1')], issues=[dict(issue, step_ids=['S1'])],
                                  retire_steps=[self.correction(['S1'])]))
        self.assertEqual(before, self.database_snapshot())

    def test_malformed_archived_original_remains_diagnostic_without_exporting(self):
        self.import_data({'retire_steps': [self.correction()]})
        store.export_records(self.conn, self.work)
        previous = (self.work / 'review.json').read_bytes()
        self.conn.execute("UPDATE step_retirements SET payload='{}'")
        self.conn.commit()
        try:
            result = store.validate(self.conn, self.work)
        except Exception as exc:
            self.fail(f'Invalid archive must return diagnostics, not raise {exc!r}')
        self.assertFalse(result['valid'])
        self.assertIn('invalid_retired_step', {e['code'] for e in result['errors']})
        with self.assertRaises(ValueError):
            store.export_records(self.conn, self.work)
        self.assertEqual(previous, (self.work / 'review.json').read_bytes())

    def test_retirement_envelope_corruption_is_invalid_before_export(self):
        self.import_data({'retire_steps': [self.correction()]})
        store.export_records(self.conn, self.work)
        previous = (self.work / 'review.json').read_bytes()
        original = json.loads(self.conn.execute('SELECT payload FROM step_retirements').fetchone()[0])
        cases = [('reason', None), ('reviewer', ''), ('recorded_at', None),
                 ('replacement_step_ids', 'S1'), ('replacement_step_ids', ['S1', 'S1']),
                 ('references_before', []), ('references_after', {}),
                 ('references_before', dict(intervals=[None], coverage=[], issues=[]))]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                changed = dict(original, **{field: value})
                self.conn.execute('UPDATE step_retirements SET payload=?', (store.dump(changed),))
                self.conn.commit()
                result = store.validate(self.conn, self.work)
                self.assertFalse(result['valid'])
                self.assertIn('invalid_retired_step', {e['code'] for e in result['errors']})
                with self.assertRaises(ValueError):
                    store.export_records(self.conn, self.work)
                self.assertEqual(previous, (self.work / 'review.json').read_bytes())

    def test_nested_retired_parameter_and_transition_evidence_cannot_hide_missing_asset(self):
        original = dict(self.original, evidence=['f0', 'missing-asset'],
                        final_parameters={'rate': {'value': None, 'evidence': ['missing-asset']}},
                        transition={'before': {'rate': {'value': None, 'evidence': ['missing-asset']}}})
        self.import_data({'steps': [original]})
        self.import_data({'retire_steps': [self.correction()]})
        result = store.validate(self.conn, self.work)
        self.assertFalse(result['valid'])
        self.assertIn('unknown_evidence', {e['code'] for e in result['errors']})
        # Removing a nested reference from the original top-level list is invalid too.
        archived = json.loads(self.conn.execute('SELECT payload FROM step_retirements').fetchone()[0])
        archived['original_step']['evidence'] = ['f0']
        self.conn.execute('UPDATE step_retirements SET payload=?', (store.dump(archived),))
        self.conn.commit()
        result = store.validate(self.conn, self.work)
        self.assertFalse(result['valid'])
        self.assertIn('invalid_retired_step', {e['code'] for e in result['errors']})

    def test_range_question_keeps_effective_unaffected_step_links(self):
        issue = dict(id='Q0', status='open', question='Shared unknown', start_frame=0, end_frame=1, attempts=[])
        self.import_data({'issues': [issue], 'steps': [step('S9')]})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'unresolved|issue'):
            self.import_data(dict(steps=[step('S1')], issues=[dict(issue, step_ids=['S1'])],
                                  retire_steps=[self.correction(['S1'])]))
        self.assertEqual(before, self.database_snapshot())
        updated = dict(issue, step_ids=['S1', 'S9'])
        self.import_data(dict(steps=[step('S1')], issues=[updated], retire_steps=[self.correction(['S1'])]))

    def test_add_then_retire_step_cannot_revive_older_review_snapshot(self):
        snapshots = {}
        for mode, table in [('layered', 'layer_reviews'), ('strict', 'omission_reviews')]:
            snapshots[mode] = audit_omissions(self.conn, self.work, mode=mode)['snapshot']
            review = dict(id='R0', reviewer='synthetic', independence='independent',
                          snapshot=snapshots[mode], note='Earlier synthetic review', evidence=['f0'],
                          tool_trace_refs=['synthetic-test://record-contract'], issue_ids=[],
                          checked_interval_ids=[], checked_state_frames=[0], conclusion='no_additional_omissions_found')
            self.import_data({table: [review]})
        temporary = dict(self.original, id='temporary')
        self.import_data({'steps': [temporary]})
        self.import_data({'retire_steps': [dict(self.correction(), id='temporary')]})
        for mode in snapshots:
            with self.subTest(mode=mode):
                audit = audit_omissions(self.conn, self.work, mode=mode)
                self.assertNotEqual(audit['snapshot'], snapshots[mode])
                self.assertEqual(audit['omission_review']['status'], 'stale')

    def test_existing_replacement_keeps_its_own_unknowns_and_status(self):
        original = dict(step('S0'), uncertainties=['Unknown A'])
        replacement = dict(step('S1'), uncertainties=['Unknown B'])
        self.import_data({'steps': [original, replacement]})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'uncertaint|unresolved'):
            self.import_data(dict(steps=[dict(replacement, uncertainties=['Unknown A'])],
                                  retire_steps=[self.correction(['S1'])]))
        self.assertEqual(before, self.database_snapshot())
        self.import_data(dict(steps=[dict(replacement, uncertainties=['Unknown A', 'Unknown B'])],
                              retire_steps=[self.correction(['S1'])]))

    def test_previously_retired_interval_expansion_still_requires_replacement(self):
        from vor_layers import sample_requirements
        interval = self.interval()
        self.import_data({'intervals': [interval]})
        check = dict(id='C0', interval_id='I0', scope_hash=sample_requirements(self.conn, interval)['scope_hash'],
                     reviewer='synthetic', method='risk_and_random', reason='Unexpected state',
                     evidence=['f0'], conclusion='expand')
        self.import_data({'interval_checks': [check]})
        self.import_data({'retire_intervals': ['I0']})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'anomal|expand'):
            self.import_data({'retire_steps': [self.correction()]})
        self.assertEqual(before, self.database_snapshot())
        self.import_data(dict(steps=[step('S1')], retire_steps=[self.correction(['S1'])]))
        archive = json.loads(self.conn.execute('SELECT payload FROM step_retirements').fetchone()[0])
        self.assertIn(interval, archive['references_before']['intervals'])

    def test_archived_reference_evidence_and_record_shape_remain_validated(self):
        issue = dict(id='Q0', status='resolved', question='Historic evidence', step_ids=['S0'],
                     attempts=[{'evidence': ['missing-asset']}])
        self.import_data({'issues': [issue]})
        self.import_data(dict(issues=[dict(issue, step_ids=[], attempts=[])], retire_steps=[self.correction()]))
        result = store.validate(self.conn, self.work)
        self.assertFalse(result['valid'])
        self.assertIn('unknown_evidence', {e['code'] for e in result['errors']})
        archive = json.loads(self.conn.execute('SELECT payload FROM step_retirements').fetchone()[0])
        for table in ('issues', 'intervals', 'coverage'):
            with self.subTest(table=table):
                broken = copy.deepcopy(archive)
                broken['references_before'][table] = [{}]
                self.conn.execute('UPDATE step_retirements SET payload=?', (store.dump(broken),))
                self.conn.commit()
                result = store.validate(self.conn, self.work)
                self.assertIn('invalid_retired_step', {e['code'] for e in result['errors']})

    def indirect_replacement_issue_case(self, table, historical=False):
        replacement = dict(self.original, id='S1')
        issue = dict(id='Q1', status='open', question='Indirect replacement unknown', attempts=[])
        if table == 'intervals':
            association = dict(self.interval(), id='I1', step_ids=['S1'], issue_ids=['Q1'])
        else:
            association = dict(frame_no=0, classification='context', reason='Existing replacement context',
                               reviewer='synthetic', evidence=['f0'], step_ids=['S1'], issue_ids=['Q1'])
        self.import_data(dict(steps=[replacement], issues=[issue], **{table: [association]}))
        if historical:
            self.import_data({'retire_intervals': ['I1']})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'unresolved|issue'):
            self.import_data(dict(issues=[dict(issue, status='resolved')], retire_steps=[self.correction(['S1'])]))
        self.assertEqual(before, self.database_snapshot())
        linked = dict(issue, step_ids=['S1'])
        self.import_data(dict(issues=[linked], retire_steps=[self.correction(['S1'])]))
        self.assertEqual(store.status(self.conn)['unresolved_issues'], [linked])
        archive = json.loads(self.conn.execute('SELECT payload FROM step_retirements').fetchone()[0])
        self.assertIn(association, archive['references_before'][table])
        self.assertIn(issue, archive['references_before']['issues'])

    def test_existing_replacement_interval_issue_cannot_close_during_retirement(self):
        self.indirect_replacement_issue_case('intervals')

    def test_existing_replacement_coverage_issue_cannot_close_during_retirement(self):
        self.indirect_replacement_issue_case('coverage')

    def test_existing_replacement_retired_interval_issue_cannot_close_during_retirement(self):
        self.indirect_replacement_issue_case('intervals', historical=True)

    def test_reused_interval_id_cannot_shadow_historical_unresolved_issue(self):
        issue = dict(id='Q1', status='open', question='Historical unresolved question', attempts=[])
        old = dict(self.interval(), id='I1', step_ids=['S1'], issue_ids=['Q1'])
        current = dict(old, issue_ids=[], reason='Later reused ID')
        self.import_data(dict(steps=[dict(self.original, id='S1')], issues=[issue], intervals=[old]))
        self.import_data({'retire_intervals': ['I1']})
        self.import_data({'intervals': [current]})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, 'unresolved|issue'):
            self.import_data(dict(issues=[dict(issue, status='resolved')], retire_steps=[self.correction(['S1'])]))
        self.assertEqual(before, self.database_snapshot())
        self.import_data(dict(issues=[dict(issue, step_ids=['S1'])], retire_steps=[self.correction(['S1'])]))
        archive = json.loads(self.conn.execute('SELECT payload FROM step_retirements').fetchone()[0])
        self.assertEqual(archive['references_before']['intervals'], [current, old])
        self.assertEqual(archive['references_after']['intervals'], [current])
        self.assertTrue(store.validate(self.conn, self.work)['valid'])

    def test_multiple_retired_versions_retain_each_issue_and_evidence_payload(self):
        issues = [dict(id=f'Q{i}', status='resolved', question=f'Historical question {i}', attempts=[]) for i in (1, 2)]
        self.import_data(dict(steps=[dict(self.original, id='S1')], issues=issues))
        old1 = dict(self.interval(), id='I1', step_ids=['S1'], issue_ids=['Q1'], reason='First retired version')
        old2 = dict(old1, issue_ids=['Q2'], evidence=['missing-historical-asset'], reason='Second retired version')
        current = dict(old1, issue_ids=[], reason='Current third version')
        for version in (old1, old2):
            self.import_data({'intervals': [version]})
            self.import_data({'retire_intervals': ['I1']})
        self.import_data({'intervals': [current]})
        self.import_data({'retire_steps': [self.correction(['S1'])]})
        archive = json.loads(self.conn.execute('SELECT payload FROM step_retirements').fetchone()[0])
        self.assertEqual(archive['references_before']['intervals'], [current, old1, old2])
        self.assertEqual({i['id'] for i in archive['references_before']['issues']}, {'Q1', 'Q2'})
        self.assertEqual(archive['references_after']['intervals'], [current])
        result = store.validate(self.conn, self.work)
        self.assertFalse(result['valid'])
        self.assertIn('unknown_evidence', {e['code'] for e in result['errors']})
        self.assertNotIn('invalid_retired_step', {e['code'] for e in result['errors']})


    def test_every_retired_record_checks_nested_history_not_only_first(self):
        second = copy.deepcopy(self.original)
        second['id'] = 'S1'
        self.import_data({'steps': [second]})
        self.import_data({'retire_steps': [self.correction(), dict(self.correction(), id='S1')]})
        baseline = json.loads(self.conn.execute('SELECT payload FROM step_retirements WHERE id="S1"').fetchone()[0])
        self.assertTrue(store.validate(self.conn, self.work)['valid'])
        for table in ('intervals', 'coverage', 'issues'):
            with self.subTest(table=table):
                corrupt = copy.deepcopy(baseline)
                corrupt['references_before'][table] = [{}]
                self.conn.execute('UPDATE step_retirements SET payload=? WHERE id="S1"', (store.dump(corrupt),))
                self.conn.commit()
                result = store.validate(self.conn, self.work)
                self.assertFalse(result['valid'], 'Every archive row must validate its historical references')
                errors = [e for e in result['errors'] if e['code'] == 'invalid_retired_step']
                self.assertTrue(any(e['reference'] == 'S1' and table in e['message'] for e in errors))


if __name__ == '__main__':
    unittest.main()
