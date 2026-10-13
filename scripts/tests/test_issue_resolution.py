"""Issue closure provenance; record fixtures are not semantic review evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vor_record_contract as contract
import vor_store as store
from test_record_contract import RecordFixture, step


def issue(ident='Q1', status='resolved', resolution=None):
    record = dict(id=ident, question='Did the setting apply?', status=status, attempts=[])
    if resolution is not None:
        record['resolution'] = copy.deepcopy(resolution)
    return record


EVIDENCE_RESOLUTION = dict(mode='evidence', reviewer='reviewer-1',
                           reason='The visible applied state answers Q1.', evidence=['f0'])
WITHDRAWN_RESOLUTION = dict(mode='withdrawn', reviewer='reviewer-1',
                            reason='Q1 incorrectly assumed a newly executed action.',
                            basis='Original Q1 question and S1 input_action describe an existing value.')


class IssueResolutionContract(RecordFixture, unittest.TestCase):
    def closure_helpers(self):
        self.assertTrue(callable(getattr(contract, 'resolution_errors', None)),
                        'Closure deficiencies must be inspectable for legacy records.')
        self.assertTrue(callable(getattr(contract, 'issue_is_resolved', None)),
                        'Consumers need evidence-aware closure status.')
        return contract.resolution_errors, contract.issue_is_resolved

    def test_new_resolved_issue_without_justification_rejects_whole_import(self):
        self.import_data({'issues': [issue(status='open')]})
        before = self.database_snapshot()
        with self.assertRaisesRegex(ValueError, r'issues\[0\]\.resolution'):
            self.import_data({'steps': [step('new-step')], 'issues': [issue()]})
        self.assertEqual(before, self.database_snapshot())

    def test_evidence_and_withdrawn_closures_preserve_distinct_justifications(self):
        records = [issue('Q-evidence', resolution=EVIDENCE_RESOLUTION),
                   issue('Q-withdrawn', resolution=WITHDRAWN_RESOLUTION)]
        self.import_data({'issues': records})
        stored = {r['id']: json.loads(r['payload']) for r in self.conn.execute('SELECT * FROM issues')}
        self.assertEqual(stored, {r['id']: r for r in records})
        errors, resolved = self.closure_helpers()
        for record in stored.values():
            with self.subTest(mode=record['resolution']['mode']):
                self.assertEqual(errors(record), [])
                self.assertTrue(resolved(record))
        self.assertTrue(store.validate(self.conn, self.work)['valid'])

    def test_missing_wrong_or_blank_resolution_fields_reject_atomically(self):
        bad = [('resolution', value) for value in ('Old free-text closure', '', [], 1, True)]
        for key in ('mode', 'reviewer', 'reason', 'evidence'):
            resolution = copy.deepcopy(EVIDENCE_RESOLUTION)
            resolution.pop(key)
            bad.append((key, resolution))
        for key in ('reviewer', 'reason'):
            for value in (None, '', '   ', 7, [], {}):
                bad.append((key, dict(EVIDENCE_RESOLUTION, **{key: value})))
        for value in (None, '', 'other', [], {}):
            bad.append(('mode', dict(EVIDENCE_RESOLUTION, mode=value)))
        for value in (None, [], 'f0', [''], [' '], [4]):
            bad.append(('evidence', dict(EVIDENCE_RESOLUTION, evidence=value)))
        for value in (None, '', '   ', [], {}):
            bad.append(('basis', dict(WITHDRAWN_RESOLUTION, basis=value)))
        missing_basis = copy.deepcopy(WITHDRAWN_RESOLUTION)
        missing_basis.pop('basis')
        bad.append(('basis', missing_basis))
        before = self.database_snapshot()
        for field, resolution in bad:
            with self.subTest(field=field, resolution=resolution):
                record = issue(resolution=resolution)
                with self.assertRaisesRegex(ValueError, 'resolution'):
                    self.import_data({'issues': [issue('new-open', 'open'), record]})
                self.assertEqual(before, self.database_snapshot())

    def test_legacy_resolved_records_remain_readable_without_becoming_verified_closures(self):
        records = [issue('legacy-missing'), issue('legacy-text', resolution='Previously accepted manually.')]
        for record in records:
            self.conn.execute('INSERT INTO issues VALUES (?,?)', (record['id'], store.dump(record)))
        self.conn.commit()
        before = self.database_snapshot()
        errors, resolved = self.closure_helpers()
        for record in records:
            with self.subTest(ident=record['id']):
                self.assertEqual(contract.check_issue(record), [])
                self.assertTrue(errors(record))
                self.assertFalse(resolved(record))
        self.assertEqual(contract.record_contract_errors(self.conn), [])
        self.assertEqual(before, self.database_snapshot())

    def test_open_and_blocked_issues_do_not_require_or_inherit_closure(self):
        errors, resolved = self.closure_helpers()
        for status in ('open', 'blocked'):
            for resolution in (None, EVIDENCE_RESOLUTION):
                with self.subTest(status=status, resolution=resolution):
                    record = issue(status=status, resolution=resolution)
                    self.import_data({'issues': [record]})
                    self.assertEqual(errors(record), [])
                    self.assertFalse(resolved(record))

    def test_closure_helper_returns_field_diagnostics_for_malformed_legacy_resolution(self):
        errors, resolved = self.closure_helpers()
        for value in (None, '', [], {'mode': []}, {'mode': 'evidence'}, {'mode': 'withdrawn'}):
            with self.subTest(resolution=value):
                record = issue(resolution=value)
                before = copy.deepcopy(record)
                self.assertTrue(errors(record))
                self.assertTrue(all('resolution' in error for error in errors(record)))
                self.assertFalse(resolved(record))
                self.assertEqual(before, record)

    def test_closure_evidence_still_uses_existing_asset_reference_validation(self):
        record = issue(resolution=dict(EVIDENCE_RESOLUTION, evidence=['not-in-this-ledger']))
        self.import_data({'issues': [record]})
        validation = store.validate(self.conn, self.work)
        self.assertFalse(validation['valid'])
        self.assertTrue(any(e['code'] == 'unknown_evidence' and e['reference'] == 'Q1'
                            for e in validation['errors']))


if __name__ == '__main__':
    unittest.main()
