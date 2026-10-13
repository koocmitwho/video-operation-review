"""Portable supplementary snapshots; synthetic views never certify real semantics."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from test_record_contract import RecordFixture, ROOT
import vor_store as store


class SupplementSnapshots(RecordFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.source_work = self.work / 'other-review'
        self.source_conn = store.connect(self.source_work, create=True)
        self.addCleanup(self.source_conn.close)
        video = self.source_work / 'other.mkv'
        video.write_bytes((ROOT / 'examples/tutorial/tutorial.mkv').read_bytes() + b'\0')
        store.set_meta(self.source_conn, 'source', store.source_file_identity(video)[0])
        self.source_conn.execute('INSERT INTO frames(frame_no,time_s,pts_time,time_source,width,height) '
                                 'VALUES (0,0,"0","pts",800,450)')
        picture = self.source_work / 'other.png'
        shutil.copyfile(ROOT / 'examples/tutorial/evidence/f000000004.png', picture)
        self.source_conn.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?,?)',
                                 ('other-f0', 0, 'full', picture.name, store.sha256(picture), None, None, store.now()))
        self.source_conn.commit()
        store.record_view(self.source_conn, self.source_work, 'other-f0', 'source-reviewer',
                          'image_tool', 'synthetic-test://supplement-source', 'Synthetic source observation.')
        store.export_records(self.source_conn, self.source_work)

    def api(self):
        spec = importlib.util.find_spec('vor_supplements')
        self.assertIsNotNone(spec, 'Supplement snapshots must retain separate source identity and local views.')
        import vor_supplements
        return vor_supplements

    def add(self, ident='SUP1', asset_ids=None):
        return self.api().import_supplement(self.conn, self.work, self.source_work, ident,
                                           asset_ids or ['other-f0'], 'importer', 'Later recording of result.')

    def refs(self):
        return [{'supplement_id': 'SUP1', 'asset_id': 'other-f0'}]

    def view(self, reviewer='followup-reviewer'):
        return self.api().record_supplement_view(self.conn, self.work, 'SUP1', 'other-f0', reviewer,
                                                'image_tool', 'synthetic-test://supplement-local',
                                                'Synthetic local bookkeeping, not a real image view.')

    def rewrite_source_export(self, update):
        path = self.source_work / 'review.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        update(report)
        path.write_text(json.dumps(report), encoding='utf-8')
        manifest_path = self.source_work / 'export-manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['files']['review.json'] = {'sha256': store.sha256(path), 'size': path.stat().st_size}
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

    def test_import_keeps_source_identity_and_does_not_create_primary_views_or_frames(self):
        counts = [self.conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                  for table in ('frames', 'assets', 'views')]
        source_before = (self.source_work / 'review.json').read_bytes()
        result = self.add()
        self.assertTrue(result['archive_non_live'])
        self.assertEqual(result['source']['sha256'], store.get_meta(self.source_conn, 'source')['sha256'])
        self.assertNotEqual(result['source']['sha256'], store.get_meta(self.conn, 'source')['sha256'])
        self.assertEqual(counts, [self.conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                                  for table in ('frames', 'assets', 'views')])
        self.assertEqual((self.source_work / 'review.json').read_bytes(), source_before)
        self.assertFalse(result['assets'][0]['viewed_recorded'])
        self.assertTrue((self.work / result['assets'][0]['relative_path']).is_file())

    def test_reference_requires_same_followup_reviewer_to_view_local_snapshot(self):
        self.add()
        api = self.api()
        self.assertTrue(api.supplement_reference_errors(self.conn, self.work, self.refs(), reviewer='followup-reviewer'))
        self.view('someone-else')
        self.assertTrue(api.supplement_reference_errors(self.conn, self.work, self.refs(), reviewer='followup-reviewer'))
        self.view()
        self.assertEqual(api.supplement_reference_errors(self.conn, self.work, self.refs(), reviewer='followup-reviewer'), [])

    def test_changed_local_picture_source_report_and_manifest_fail_closed(self):
        result = self.add(); self.view()
        row = store.get_meta(self.conn, 'supplements')[0]
        package_path = self.work / row['manifest']['path']
        package = json.loads(package_path.read_text(encoding='utf-8'))
        targets = [self.work / result['assets'][0]['relative_path'], package_path,
                   package_path.parent / 'source-review.json', package_path.parent / 'source-export-manifest.json']
        for target in targets:
            with self.subTest(path=target.name):
                original = target.read_bytes()
                target.write_bytes(original + b' ')
                self.assertTrue(self.api().supplement_reference_errors(self.conn, self.work, self.refs()))
                target.write_bytes(original)
        self.assertEqual(self.api().supplement_reference_errors(self.conn, self.work, self.refs()), [])

    def test_target_snapshot_can_move_and_original_directory_can_disappear(self):
        result = self.add(); self.view()
        self.source_conn.close()
        shutil.rmtree(self.source_work)
        moved = self.work / 'moved-target'
        moved.mkdir()
        shutil.copytree(self.work / 'supplements', moved / 'supplements')
        relocated = store.connect(moved, create=True)
        self.addCleanup(relocated.close)
        store.set_meta(relocated, 'supplements', store.get_meta(self.conn, 'supplements'))
        relocated.commit()
        self.assertEqual(self.api().supplement_reference_errors(relocated, moved, self.refs(), reviewer='followup-reviewer'), [])
        self.assertTrue(self.api().supplement_status(relocated, moved)[0]['archive_non_live'])

    def test_source_updates_do_not_silently_refresh_archived_generation(self):
        result = self.add(); self.view()
        (self.source_work / 'other.png').write_bytes(b'new source content')
        (self.source_work / 'review.json').write_text('{}', encoding='utf-8')
        current = self.api().supplement_status(self.conn, self.work)[0]
        self.assertEqual(current['source_export_generation'], result['source_export_generation'])
        self.assertEqual(self.api().supplement_reference_errors(self.conn, self.work, self.refs()), [])

    def test_incomplete_or_mismatched_export_rejects_without_database_write(self):
        before = self.database_snapshot()
        (self.source_work / 'export.pending.json').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'pending|incomplete'):
            self.add()
        (self.source_work / 'export.pending.json').unlink()
        (self.source_work / 'report.md').write_text('modified', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'hash|changed|manifest'):
            self.add()
        self.assertEqual(self.database_snapshot(), before)
        self.assertFalse((self.work / 'supplements' / 'SUP1').exists())

    def test_mismatched_generation_and_missing_native_view_are_rejected(self):
        original = (self.source_work / 'review.json').read_bytes()
        original_manifest = (self.source_work / 'export-manifest.json').read_bytes()
        variants = [lambda r: r.update(export_generation='wrong-generation'),
                    lambda r: r.update(views=[]),
                    lambda r: r['views'][0].update(presentation='overview'),
                    lambda r: r['views'][0].update(asset_sha256='0' * 64),
                    lambda r: r['views'][0].update(frame_no=55)]
        for variant in variants:
            with self.subTest(update=variant):
                (self.source_work / 'review.json').write_bytes(original)
                (self.source_work / 'export-manifest.json').write_bytes(original_manifest)
                self.rewrite_source_export(variant)
                with self.assertRaises(ValueError):
                    self.add()
                self.assertIsNone(store.get_meta(self.conn, 'supplements'))

    def test_review_complete_alone_cannot_authorize_unviewed_source_evidence(self):
        self.rewrite_source_export(lambda r: (r.update(views=[]), r['validation'].update(review_complete=True)))
        with self.assertRaisesRegex(ValueError, 'view|native'):
            self.add()

    def test_paths_ids_self_reference_and_duplicate_ids_cannot_escape_or_overwrite(self):
        for ident in ('../escape', 'x/y', 'x\\y', 'C:\\outside', 'CON', '.', '', 'SUP1:stream'):
            with self.subTest(ident=ident):
                with self.assertRaises(ValueError):
                    self.add(ident)
        result = self.add()
        before = self.database_snapshot()
        picture = self.work / result['assets'][0]['relative_path']
        original = picture.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already|duplicate|exist'):
            self.add()
        self.assertEqual(self.database_snapshot(), before)
        self.assertEqual(picture.read_bytes(), original)
        store.export_records(self.conn, self.work)
        with self.assertRaisesRegex(ValueError, 'same|self|independent'):
            self.api().import_supplement(self.conn, self.work, self.work, 'SELF', ['f0'], 'a', 'n')

    def test_source_asset_paths_must_be_relative_and_contained(self):
        for unsafe in ('../evidence.png', str(self.work / 'evidence.png'), 'C:\\outside.png', 'a/../../other.png'):
            self.rewrite_source_export(lambda r: r['assets'][0].update(path=unsafe))
            with self.subTest(path=unsafe), self.assertRaisesRegex(ValueError, 'path|relative|escape'):
                self.add()

    def test_failed_copy_leaves_database_unchanged_and_only_removes_owned_stage(self):
        before = self.database_snapshot()
        storage = self.work / 'supplements'; storage.mkdir()
        unrelated = storage / 'keep.txt'; unrelated.write_text('keep', encoding='utf-8')
        api = self.api()
        with patch.object(api.shutil, 'copyfile', side_effect=OSError('injected copy failure')):
            with self.assertRaisesRegex(OSError, 'copy failure'):
                self.add()
        self.assertEqual(self.database_snapshot(), before)
        self.assertEqual(sorted(p.name for p in storage.iterdir()), ['keep.txt'])

    def test_failed_database_write_rolls_back_copied_package_and_database(self):
        api = self.api()
        before = self.database_snapshot()
        with patch.object(api, '_save', side_effect=OSError('injected persistence failure')):
            with self.assertRaisesRegex(OSError, 'persistence failure'):
                self.add()
        self.assertEqual(self.database_snapshot(), before)
        self.assertEqual(list((self.work / 'supplements').iterdir()), [])

    def test_source_manifest_change_during_read_rejects_instead_of_importing_invalid_snapshot(self):
        api = self.api()
        original = api._source_export
        def read_then_change(*args):
            result = original(*args)
            manifest = self.source_work / 'export-manifest.json'
            value = json.loads(manifest.read_text(encoding='utf-8'))
            value['generation'] = 'later-generation'
            manifest.write_text(json.dumps(value), encoding='utf-8')
            return result
        before = self.database_snapshot()
        with patch.object(api, '_source_export', side_effect=read_then_change):
            with self.assertRaises(ValueError):
                self.add()
        self.assertEqual(before, self.database_snapshot())

    def test_concurrent_metadata_change_cannot_be_overwritten_by_stale_import(self):
        api = self.api()
        original_copy = api.shutil.copyfile
        changed = False
        def copy_then_change(*args, **kwargs):
            nonlocal changed
            result = original_copy(*args, **kwargs)
            if not changed:
                changed = True
                store.set_meta(self.conn, 'supplements', [{'id': 'OTHER', 'manifest': {}, 'views': []}])
                self.conn.commit()
            return result
        with patch.object(api.shutil, 'copyfile', side_effect=copy_then_change):
            with self.assertRaisesRegex(ValueError, 'changed|concurrent|retry'):
                self.add()
        self.assertEqual(store.get_meta(self.conn, 'supplements')[0]['id'], 'OTHER')
        self.assertFalse((self.work / 'supplements' / 'SUP1').exists())

    def test_symbolic_or_junction_paths_are_rejected_without_following_external_content(self):
        external = self.work / 'external'; external.mkdir()
        link = self.source_work / 'linked'
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(external), str(link))
        else:
            link.symlink_to(external, target_is_directory=True)
        self.addCleanup(lambda: link.rmdir() if os.name == 'nt' else link.unlink())
        shutil.copyfile(self.source_work / 'other.png', external / 'other.png')
        self.rewrite_source_export(lambda r: r['assets'][0].update(path='linked/other.png'))
        with self.assertRaisesRegex(ValueError, 'symlink|junction'):
            self.add()
        self.assertIsNone(store.get_meta(self.conn, 'supplements'))

    def test_local_storage_junction_is_rejected_before_copy(self):
        external = self.work / 'external'; external.mkdir()
        link = self.work / 'supplements'
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(external), str(link))
        else:
            link.symlink_to(external, target_is_directory=True)
        self.addCleanup(lambda: link.rmdir() if os.name == 'nt' else link.unlink())
        with self.assertRaisesRegex(ValueError, 'symlink|junction'):
            self.add()
        self.assertEqual(list(external.iterdir()), [])

    def test_malformed_source_validation_gives_contract_diagnostic(self):
        self.rewrite_source_export(lambda r: r.update(validation=[]))
        with self.assertRaisesRegex(ValueError, 'validation|integrity'):
            self.add()

    def test_interrupt_after_commit_preserves_registered_snapshot_files(self):
        api = self.api()
        original = api._save
        def save_commit_interrupt(conn, *args):
            original(conn, *args)
            conn.commit()
            raise KeyboardInterrupt('after database commit')
        with patch.object(api, '_save', side_effect=save_commit_interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.add()
        self.assertEqual(store.get_meta(self.conn, 'supplements')[0]['id'], 'SUP1')
        self.assertTrue(api.supplement_status(self.conn, self.work)[0]['valid'])

    def test_invalid_view_registration_leaves_existing_views_intact(self):
        self.add(); self.view()
        before = self.database_snapshot()
        for actor, tool, trace in [('', 'image_tool', 'tool#1'), ('a', 'overview', 'tool#1'),
                                   ('a', 'image_tool', 'other-f0'), ('a', 'image_tool', 'other.png')]:
            with self.subTest(actor=actor, tool=tool, trace=trace), self.assertRaises(ValueError):
                self.api().record_supplement_view(self.conn, self.work, 'SUP1', 'other-f0', actor, tool, trace, 'obs')
        self.assertEqual(before, self.database_snapshot())

    def test_corrupted_local_view_hash_or_frame_is_not_trusted(self):
        self.add(); self.view()
        original = store.get_meta(self.conn, 'supplements')
        for field, value in [('asset_sha256', '0' * 64), ('frame_no', 5), ('presentation', 'overview'),
                             ('package_sha256', '0' * 64)]:
            modified = copy.deepcopy(original)
            modified[0]['views'][0][field] = value
            store.set_meta(self.conn, 'supplements', modified); self.conn.commit()
            with self.subTest(field=field):
                self.assertTrue(self.api().supplement_reference_errors(self.conn, self.work, self.refs()))


if __name__ == '__main__':
    unittest.main()
