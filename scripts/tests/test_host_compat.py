"""Host-facing contracts; real CLI/processes, isolated data, no model calls."""
import json
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from make_fixtures import make_fixtures

CLI = Path(__file__).resolve().parents[1] / 'review_video.py'


class HostCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = shutil.which('ffmpeg')
        cls.ffprobe = shutil.which('ffprobe')
        cls.temp = tempfile.TemporaryDirectory(prefix='vor hosts 中文 ')
        cls.root = Path(cls.temp.name)
        cls.video, _ = make_fixtures(cls.root / '素材 文件')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.cwd = self.root / self._testMethodName
        self.cwd.mkdir()

    def cli(self, *args, no_site=False, env=None):
        process_env = os.environ.copy()
        process_env.pop('VOR_FFMPEG', None)
        process_env.pop('VOR_FFPROBE', None)
        process_env.update(env or {})
        return subprocess.run(
            [sys.executable, '-X', 'utf8', *(['-S'] if no_site else []), str(CLI), *map(str, args)],
            cwd=self.cwd, env=process_env, capture_output=True, text=True, encoding='utf-8', timeout=30)

    def result(self, process, code):
        self.assertEqual(process.returncode, code, process.stdout + process.stderr)
        self.assertNotIn('Traceback', process.stderr)
        return json.loads(process.stdout)

    def test_help_works_without_third_party_dependencies_and_outside_skill_directory(self):
        process = self.cli('--help', no_site=True)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertIn('scan', process.stdout)
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_doctor_reports_all_missing_dependencies_without_creating_work(self):
        report = self.result(self.cli('doctor', no_site=True,
            env={'VOR_FFMPEG': str(self.cwd / 'absent-ffmpeg'),
                 'VOR_FFPROBE': str(self.cwd / 'absent-ffprobe')}), 1)
        self.assertFalse(report['ready'])
        for name in ('numpy', 'pillow', 'ffmpeg', 'ffprobe'):
            self.assertFalse(report['checks'][name]['ok'], name)
        self.assertEqual(report['visual_review']['status'], 'unverified')
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_doctor_checks_real_tools_without_claiming_host_vision(self):
        report = self.result(self.cli('doctor', '--ffmpeg', self.ffmpeg,
                                      '--ffprobe', self.ffprobe), 0)
        self.assertTrue(report['ready'])
        self.assertTrue(report['checks']['ffmpeg']['fps_mode_passthrough'])
        self.assertEqual(report['visual_review']['status'], 'unverified')
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_explicit_executables_override_environment_with_missing_path(self):
        report = self.result(self.cli('doctor', '--ffmpeg', self.ffmpeg,
            '--ffprobe', self.ffprobe, env={'PATH': '', 'VOR_FFMPEG': 'missing-ffmpeg',
                                           'VOR_FFPROBE': 'missing-ffprobe'}), 0)
        self.assertTrue(report['ready'])

    def test_unusable_executable_is_not_reported_as_ready(self):
        report = self.result(self.cli('doctor', '--ffmpeg', sys.executable,
                                      '--ffprobe', self.ffprobe), 1)
        self.assertFalse(report['checks']['ffmpeg']['ok'])

    def test_missing_runtime_dependencies_produce_actionable_json_without_database(self):
        work = self.cwd / 'review'
        report = self.result(self.cli('scan', self.video, '--work', work, no_site=True), 1)
        self.assertEqual(report['type'], 'ModuleNotFoundError')
        self.assertIn('doctor', report['hint'])
        self.assertFalse(work.exists())

    def test_environment_executables_work_for_scan_and_extract_in_unicode_paths(self):
        work = self.cwd / '审阅 数据'
        env = {'PATH': '', 'VOR_FFMPEG': self.ffmpeg, 'VOR_FFPROBE': self.ffprobe}
        self.result(self.cli('scan', self.video, '--work', work, env=env), 0)
        self.result(self.cli('extract', '--frames', '0', '--work', work, env=env), 0)
        self.assertTrue(list((work / 'evidence').glob('*.png')))

    def test_deepseek_read_image_trace_is_preserved_and_deduplicated(self):
        # Synthetic view attestations test bookkeeping only, never actual vision.
        work = self.cwd / 'review'
        self.result(self.cli('scan', self.video, '--work', work), 0)
        self.result(self.cli('extract', '--frames', '0', '--work', work), 0)
        with closing(sqlite3.connect(work / 'review.sqlite3')) as conn:
            asset = conn.execute('SELECT id FROM assets WHERE frame_no=0').fetchone()[0]
        for tool in ('read_image', 'view_image'):
            self.result(self.cli('record-view', '--work', work, '--asset', asset,
                '--actor', 'test-only', '--tool', tool, '--trace', f'synthetic-test-{tool}',
                '--observation', 'Synthetic test event; no actual visual review.'), 0)
        with closing(sqlite3.connect(work / 'review.sqlite3')) as conn:
            tools = conn.execute('SELECT tool, trace_ref FROM views ORDER BY rowid').fetchall()
            count = conn.execute('SELECT COUNT(DISTINCT frame_no) FROM views').fetchone()[0]
        self.assertEqual(tools, [('read_image', 'synthetic-test-read_image'),
                                 ('view_image', 'synthetic-test-view_image')])
        self.assertEqual(count, 1)


if __name__ == '__main__':
    unittest.main()
