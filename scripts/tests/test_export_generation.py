"""Faults must not leave a successful-looking mixed export; no semantic assertions."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from test_record_contract import RecordFixture, step
import vor_store as store

DELIVERY = ('review.json', 'omission-audit.json', 'frames.jsonl', 'report.md')


class ExportGenerationContract(RecordFixture, unittest.TestCase):
    def snapshot(self):
        return {name: (self.work / name).read_bytes() for name in (*DELIVERY, 'export-manifest.json')
                if (self.work / name).exists()}

    def test_successful_export_has_complete_manifest_matching_all_four_files(self):
        result = store.export_records(self.conn, self.work)
        self.assertTrue((self.work / 'export-manifest.json').is_file())
        manifest = json.loads((self.work / 'export-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['state'], 'complete')
        self.assertEqual(set(manifest['files']), set(DELIVERY))
        self.assertEqual(result['generation'], manifest['generation'])
        self.assertEqual(json.loads((self.work / 'review.json').read_text(encoding='utf-8'))['export_generation'], manifest['generation'])
        for name, data in manifest['files'].items():
            self.assertEqual(data['sha256'], hashlib.sha256((self.work / name).read_bytes()).hexdigest())
        self.assertIn(manifest['generation'], (self.work / 'report.md').read_text(encoding='utf-8'))
        self.assertFalse((self.work / 'export.pending.json').exists())

    def test_render_failure_keeps_all_previous_delivery_bytes(self):
        store.export_records(self.conn, self.work)
        before = self.snapshot()
        self.import_data({'steps': [step()]})
        with patch('vor_report.render_report', side_effect=RuntimeError('injected renderer failure')):
            with self.assertRaisesRegex(RuntimeError, 'renderer failure'):
                store.export_records(self.conn, self.work)
        self.assertEqual(before, self.snapshot())

    def test_partial_publish_failure_restores_previous_generation(self):
        store.export_records(self.conn, self.work)
        before = self.snapshot()
        self.import_data({'steps': [step()]})
        original = Path.replace
        failed = False
        def fail_once(source, destination):
            nonlocal failed
            if Path(destination) == self.work / 'report.md' and not failed:
                failed = True
                raise OSError('injected report publish failure')
            return original(source, destination)
        with patch.object(Path, 'replace', fail_once):
            with self.assertRaisesRegex(OSError, 'publish failure'):
                store.export_records(self.conn, self.work)
        self.assertTrue(failed)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.work / 'export.pending.json').exists())

    def test_unrecoverable_publish_keeps_pending_receipt_and_rejects_new_export(self):
        store.export_records(self.conn, self.work)
        self.import_data({'steps': [step()]})
        original = Path.replace
        failed_publish = False
        def fail_report(source, destination):
            nonlocal failed_publish
            if Path(destination) == self.work / 'report.md':
                failed_publish = True
                raise OSError('injected persistent lock')
            if failed_publish and Path(destination) == self.work / 'review.json':
                raise OSError('injected persistent lock')
            return original(source, destination)
        with patch.object(Path, 'replace', fail_report):
            with self.assertRaises(OSError):
                store.export_records(self.conn, self.work)
        self.assertTrue((self.work / 'export.pending.json').is_file())
        pending = json.loads((self.work / 'export.pending.json').read_text(encoding='utf-8'))
        self.assertIn(pending['state'], ('pending', 'recovery_required'))
        self.assertTrue((self.work / pending['staging_directory']).is_dir())
        with self.assertRaisesRegex(ValueError, 'export.pending.json'):
            store.export_records(self.conn, self.work)

    def test_interrupt_immediately_after_rename_cannot_escape_rollback_accounting(self):
        store.export_records(self.conn, self.work)
        before = self.snapshot()
        self.import_data({'steps': [step()]})
        original = Path.replace
        interrupted = False
        def replace_then_interrupt(source, destination):
            nonlocal interrupted
            result = original(source, destination)
            if Path(destination) == self.work / 'review.json' and not interrupted:
                interrupted = True
                raise KeyboardInterrupt('after successful rename')
            return result
        with patch.object(Path, 'replace', replace_then_interrupt):
            with self.assertRaises(KeyboardInterrupt):
                store.export_records(self.conn, self.work)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.work / 'export.pending.json').exists())


if __name__ == '__main__':
    unittest.main()
