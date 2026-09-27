"""真实挂起子进程与合成失败注入，检查退出与 attempt 收尾。"""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vor_language as language
import vor_media as media
import vor_store as store
from make_fixtures import make_fixtures


class HelperTimeoutContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='vor timeout ')
        cls.root = Path(cls.temp.name)
        cls.video, _ = make_fixtures(cls.root / 'input')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.work = self.root / self._testMethodName
        self.conn = store.connect(self.work, create=True)
        self.addCleanup(self.conn.close)

    @contextmanager
    def hanging_helpers(self, flag):
        real_popen = subprocess.Popen
        children, emergency = [], []
        def launch(args, **kwargs):
            if flag in args:
                args = [sys.executable, '-c', 'import time; time.sleep(600)']
                process = real_popen(args, **kwargs)
                children.append(process)
                timer = threading.Timer(2, lambda: process.kill() if process.poll() is None else None)
                timer.daemon = True
                timer.start()
                emergency.append(timer)
                return process
            return real_popen(args, **kwargs)
        try:
            with patch.object(subprocess, 'Popen', side_effect=launch), \
                 patch.object(media, 'PROBE_TIMEOUT', 0.15, create=True), \
                 patch.object(media, 'INDEX_TIMEOUT', 0.15, create=True), \
                 patch.object(media, 'MEDIA_TIMEOUT', 0.15, create=True):
                yield children
        finally:
            for timer in emergency:
                timer.cancel()
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=5)

    def assert_timeout(self, operation, flag):
        start = time.monotonic()
        caught = None
        with self.hanging_helpers(flag) as children:
            try:
                operation()
            except Exception as exc:
                caught = exc
            self.assertEqual(getattr(caught, 'code', None), 'helper_timeout', repr(caught))
            self.assertTrue(children)
            self.assertTrue(all(child.poll() is not None for child in children))
        self.assertLess(time.monotonic() - start, 1.8)
        attempts = store.status(self.conn)['attempts']
        self.assertTrue(attempts)
        self.assertEqual(attempts[-1]['status'], 'failed')
        self.assertIn('helper_timeout', attempts[-1]['error'])
        self.assertFalse(any(a['status'] == 'running_or_unfinalized' for a in attempts))

    def test_metadata_probe_timeout_ends_attempt(self):
        self.assert_timeout(lambda: media.scan(self.conn, self.work, self.video), '-show_format')

    def test_index_stdout_hang_timeout_ends_attempt(self):
        self.assert_timeout(lambda: media.scan(self.conn, self.work, self.video), '-show_frames')

    def test_version_timeout_ends_attempt(self):
        self.assert_timeout(lambda: media.scan(self.conn, self.work, self.video), '-version')

    def test_decoder_stdout_hang_timeout_ends_attempt(self):
        self.assert_timeout(lambda: media.scan(self.conn, self.work, self.video), 'image2pipe')

    def test_extract_stdout_hang_timeout_ends_attempt(self):
        media.scan(self.conn, self.work, self.video)
        self.assert_timeout(lambda: media.extract(self.conn, self.work, [0]), 'image2pipe')

    def test_tracks_timeout_ends_attempt(self):
        media.scan(self.conn, self.work, self.video)
        self.assert_timeout(lambda: language.tracks(self.conn), '-show_streams')

    def test_subtitle_timeout_ends_attempt(self):
        media.scan(self.conn, self.work, self.video)
        sub = self.work / 'input.srt'
        sub.write_text('1\n00:00:00,000 --> 00:00:00,500\n测试字幕\n', encoding='utf-8')
        self.assert_timeout(lambda: language.import_subtitles(self.conn, self.work, sub), '-c:s')

    def test_process_options_apply_timeout_and_allow_popen_options(self):
        self.assertGreater(media.process_options().get('timeout', 0), 0)
        self.assertEqual(media.process_options(timeout=120)['timeout'], 120)
        self.assertNotIn('timeout', media.process_options(timeout=None))

    def test_index_progress_renews_timeout_for_longer_total_run(self):
        real_popen = subprocess.Popen
        script = ("import time; "
                  "[(print(f'pts={n}|pts_time={n/8}|width=160|height=90|key_frame=0', flush=True), "
                  "time.sleep(.1)) for n in range(8)]")
        def launch(args, **kwargs):
            if '-show_frames' in args:
                return real_popen([sys.executable, '-c', script], **kwargs)
            return real_popen(args, **kwargs)
        start = time.monotonic()
        with patch.object(subprocess, 'Popen', side_effect=launch), patch.object(media, 'INDEX_TIMEOUT', .3):
            result = media.scan(self.conn, self.work, self.video)
        self.assertTrue(result['full_compute_complete'])
        self.assertEqual(result['computed_frames'], 8)
        self.assertGreater(time.monotonic() - start, .6)


if __name__ == '__main__':
    unittest.main()
