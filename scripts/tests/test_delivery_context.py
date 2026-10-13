"""Persistent user handoff and evidence-bound replay; fixtures are not semantic acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from urllib.parse import unquote

from test_record_contract import RecordFixture, step
import vor_store as store


class DeliveryContextContract(RecordFixture, unittest.TestCase):
    def context(self, **changes):
        value = dict(question='仅核对替换后的两行文字', scope='0–2.66秒；不执行录像中的命令',
                     next_action='补看触发按钮前后画面', used_language_source_ids=[])
        return dict(value, **changes)

    def export(self):
        result = store.export_records(self.conn, self.work)
        return result, json.loads((self.work / 'review.json').read_text(encoding='utf-8'))

    def check(self):
        artifact = self.work / 'replay.txt'
        artifact.write_text('Synthetic replay fixture; not a real run.', encoding='utf-8')
        snapshot = store.status(self.conn).get('delivery_snapshot', 'missing-before-implementation')
        return dict(id='R1', reviewer='fixture-reviewer', scope='S1 only', environment='test fixture',
                    step_ids=['S1'], outcome='passed', result='Synthetic expected output matches.',
                    content_snapshot=snapshot,
                    artifacts=[dict(path='replay.txt', sha256=store.sha256(artifact))])

    def test_context_survives_reexport_and_fixed_handoff_is_in_generation(self):
        self.import_data({'delivery_context': self.context()})
        first, data = self.export()
        self.assertEqual(data.get('delivery_context'), self.context())
        handoff = self.work / 'handoff.md'
        self.assertTrue(handoff.is_file())
        text = handoff.read_text(encoding='utf-8')
        for expected in ['仅核对替换后的两行文字', '不执行录像中的命令', '补看触发按钮前后画面',
                         'report.md', 'source.mkv']:
            self.assertIn(expected, text)
        self.assertIn(self.work.as_posix(), [unquote(target) for target in re.findall(r'\]\(<([^>]+)>\)', text)])
        manifest = json.loads((self.work / 'export-manifest.json').read_text(encoding='utf-8'))
        self.assertIn('handoff.md', manifest['files'])
        self.assertEqual(manifest['files']['handoff.md']['sha256'], hashlib.sha256(handoff.read_bytes()).hexdigest())
        self.assertIn(first['generation'], text)
        self.export()
        self.assertIn('补看触发按钮前后画面', handoff.read_text(encoding='utf-8'))

    def test_invalid_context_is_rejected_without_partial_step_write(self):
        before = self.database_snapshot()
        for changes in [dict(scope=' '), dict(question=3), dict(used_language_source_ids=['missing'])]:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, 'delivery_context'):
                    self.import_data({'steps': [step()], 'delivery_context': self.context(**changes)})
                self.assertEqual(before, self.database_snapshot())

    def test_imported_transcript_is_not_automatically_claimed_as_used(self):
        from vor_language import import_transcript
        transcript = self.work / 'speech.json'
        transcript.write_text(json.dumps(dict(time_base='original', language='zh',
            segments=[dict(start=0, end=.5, text='合成讲解')])) , encoding='utf-8')
        import_transcript(self.conn, self.work, transcript)
        ident = self.conn.execute('SELECT id FROM language_sources').fetchone()[0]
        self.import_data({'delivery_context': self.context()})
        _, data = self.export()
        summary = '\n'.join(data.get('delivery_summary', []))
        self.assertIn('已导入', summary)
        self.assertIn('未声明使用', summary)
        self.import_data({'delivery_context': self.context(used_language_source_ids=[ident])})
        _, data = self.export()
        self.assertIn('已使用', '\n'.join(data['delivery_summary']))
        self.assertIn(ident, '\n'.join(data['delivery_summary']))

    def test_audio_probe_distinguishes_unchecked_from_no_audio(self):
        _, data = self.export()
        self.assertIn('音轨未检查', '\n'.join(data.get('delivery_summary', [])))
        from vor_language import tracks
        tracks(self.conn)
        _, data = self.export()
        self.assertIn('无音轨', '\n'.join(data.get('delivery_summary', [])))

    def test_audio_without_transcription_is_explicit_in_report(self):
        store.set_meta(self.conn, 'media_tracks', {'audio': [{'codec_type': 'audio'}], 'subtitles': []})
        self.conn.commit()
        self.export()
        report = (self.work / 'report.md').read_text(encoding='utf-8')
        self.assertIn('有音轨；旁白未转写', report)

    def test_context_text_is_escaped_once_in_rendered_report(self):
        self.import_data({'delivery_context': self.context(question='检查 A_B 和 <tag>')})
        self.export()
        report = (self.work / 'report.md').read_text(encoding='utf-8')
        self.assertIn('检查 A\\_B 和 &lt;tag&gt;', report)
        self.assertNotIn('&amp;lt;tag&amp;gt;', report)

    def test_replay_id_cannot_overwrite_frozen_history(self):
        self.import_data({'steps': [step()]})
        entry = self.check()
        self.import_data({'reproduction_checks': [entry]})
        before = self.database_snapshot()
        entry['result'] = 'Changed claim'
        with self.assertRaisesRegex(ValueError, 'already recorded'):
            self.import_data({'reproduction_checks': [entry]})
        self.assertEqual(before, self.database_snapshot())

    def test_replay_record_binds_content_and_loses_currency_after_step_change(self):
        self.import_data({'steps': [step()], 'delivery_context': self.context()})
        replay = self.check()
        self.import_data({'reproduction_checks': [replay]})
        _, data = self.export()
        checks = data.get('reproduction_checks', [])
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]['freshness'], 'current')
        self.assertIn('test fixture', '\n'.join(data['delivery_summary']))
        changed = step(); changed['visible_result'] = 'Changed result'
        self.import_data({'steps': [changed]})
        _, data = self.export()
        self.assertEqual(data['reproduction_checks'][0]['freshness'], 'stale')
        self.assertIn('已过期', '\n'.join(data['delivery_summary']))

    def test_replay_stays_bound_when_only_next_action_changes(self):
        self.import_data({'steps': [step()], 'delivery_context': self.context()})
        self.import_data({'reproduction_checks': [self.check()]})
        self.import_data({'delivery_context': self.context(next_action='交给独立审阅者')})
        _, data = self.export()
        self.assertEqual(data.get('reproduction_checks', [{}])[0].get('freshness'), 'current')

    def test_replay_rejects_stale_hash_unknown_step_and_escaping_file_atomically(self):
        self.import_data({'steps': [step()]})
        replay = self.check()
        before = self.database_snapshot()
        variants = []
        for key, value in [('content_snapshot', '0' * 64), ('step_ids', ['missing'])]:
            item = copy.deepcopy(replay); item[key] = value; variants.append(item)
        for path, digest in [('../outside.txt', '0' * 64), ('replay.txt', '0' * 64)]:
            item = copy.deepcopy(replay); item['artifacts'] = [dict(path=path, sha256=digest)]; variants.append(item)
        for item in variants:
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    self.import_data({'reproduction_checks': [item]})
                self.assertEqual(before, self.database_snapshot())

    def test_replay_evidence_change_is_reported_without_erasing_prior_record(self):
        self.import_data({'steps': [step()]})
        self.import_data({'reproduction_checks': [self.check()]})
        (self.work / 'replay.txt').write_text('Changed evidence', encoding='utf-8')
        _, data = self.export()
        self.assertEqual(len(data.get('reproduction_checks', [])), 1)
        self.assertEqual(data['reproduction_checks'][0]['freshness'], 'evidence_changed')
        self.assertIn('证据文件缺失或变化', '\n'.join(data['delivery_summary']))

    def test_generated_delivery_cannot_be_its_own_reproduction_evidence(self):
        self.import_data({'steps': [step()]})
        self.export()
        entry = self.check()
        for index, name in enumerate(['report.md', 'handoff.md', 'review.json', 'export-manifest.json', 'review.sqlite3']):
            entry['id'] = f'R-forbidden-{index}'
            entry['artifacts'] = [dict(path=name, sha256=store.sha256(self.work / name))]
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'artifacts'):
                    self.import_data({'reproduction_checks': [entry]})

    def test_preexisting_or_user_edited_handoff_is_never_overwritten(self):
        handoff = self.work / 'handoff.md'
        handoff.write_text('My preexisting handwritten instructions.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'handoff'):
            self.export()
        self.assertEqual(handoff.read_text(encoding='utf-8'), 'My preexisting handwritten instructions.')
        handoff.rename(self.work / 'manual-handoff.md')
        self.export()
        before = (self.work / 'report.md').read_bytes()
        handoff.write_text('Additional user notes.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'handoff'):
            self.export()
        self.assertEqual((self.work / 'report.md').read_bytes(), before)
        self.assertEqual(handoff.read_text(encoding='utf-8'), 'Additional user notes.')

    def test_original_video_and_registered_visual_evidence_cannot_prove_replay(self):
        self.import_data({'steps': [step()]})
        entry = self.check()
        for index, name in enumerate(['source.mkv', 'evidence.png']):
            entry['id'] = f'R-original-{index}'
            entry['artifacts'] = [dict(path=name, sha256=store.sha256(self.work / name))]
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'artifacts'):
                    self.import_data({'reproduction_checks': [entry]})

    def test_handoff_publish_failure_restores_entire_previous_export(self):
        self.import_data({'delivery_context': self.context()})
        self.export()
        names = ['review.json', 'report.md', 'handoff.md', 'frames.jsonl', 'omission-audit.json', 'export-manifest.json']
        self.assertTrue((self.work / 'handoff.md').is_file())
        before = {name: (self.work / name).read_bytes() for name in names}
        self.import_data({'delivery_context': self.context(next_action='Changed action')})
        original = Path.replace
        failed = False
        def fail_once(source, destination):
            nonlocal failed
            if Path(destination) == self.work / 'handoff.md' and not failed:
                failed = True
                raise OSError('injected handoff publish failure')
            return original(source, destination)
        with patch.object(Path, 'replace', fail_once):
            with self.assertRaisesRegex(OSError, 'handoff publish'):
                self.export()
        self.assertEqual(before, {name: (self.work / name).read_bytes() for name in names})
        self.assertFalse((self.work / 'export.pending.json').exists())
