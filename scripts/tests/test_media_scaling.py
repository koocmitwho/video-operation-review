"""Synthetic regressions for sparse extraction and decoder completion boundaries."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vor_media as media
import vor_store as store


class MediaScalingContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='vor media scaling ')
        cls.root = Path(cls.temp.name)
        for name, count in [('small', 8), ('large', 1200)]:
            raw = b''.join(bytes((n % 256, n // 256, 13)) * 256 for n in range(count))
            result = subprocess.run(
                ['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24',
                 '-video_size', '16x16', '-framerate', '100', '-i', 'pipe:0',
                 '-c:v', 'ffv1', str(cls.root / (name + '.mkv'))],
                input=raw, capture_output=True, **media.process_options())
            if result.returncode:
                raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
        cls.small = cls.root / 'small.mkv'
        cls.large = cls.root / 'large.mkv'
        cls.ppm = cls.root / 'small.ppm'
        cls.ppm.write_bytes(b''.join(b'P6\n16 16\n255\n' + bytes((n, 0, 13)) * 256
                                     for n in range(8)))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.work = self.root / self._testMethodName
        self.conn = store.connect(self.work, create=True)
        self.addCleanup(self.conn.close)

    def test_six_hundred_sparse_frames_keep_identity_and_contiguous_spans(self):
        media.scan(self.conn, self.work, self.large)
        numbers = [0, 1, 2, 6, 7] + list(range(10, 1200, 2))
        try:
            result = media.extract(self.conn, self.work, numbers)
        except Exception as exc:
            self.fail(f'600 requested sparse frames must extract successfully: {exc}')
        self.assertEqual(result['extracted_new'], 600)
        self.assertEqual(len(result['assets']), 600)
        for n in numbers:
            with Image.open(self.work / 'evidence' / f'f{n:09d}.png') as image:
                self.assertEqual(image.getpixel((0, 0)), (n % 256, n // 256, 13))
        self.assertEqual(store.status(self.conn)['recorded_visual_unique_frames'], 0)

    def test_decoder_filter_failure_reports_process_error_and_log(self):
        media.scan(self.conn, self.work, self.small)
        invalid_filter = self.work / 'invalid.filter'
        invalid_filter.write_text('select=not_a_function(n)', encoding='utf-8')
        real_decoder = media.decoder
        def broken_filter(video, ffmpeg, log, filter_file=None, count=None):
            return real_decoder(video, ffmpeg, log, invalid_filter, count)
        with patch.object(media, 'decoder', side_effect=broken_filter):
            with self.assertRaises(Exception) as caught:
                media.extract(self.conn, self.work, [0])
        self.assertIsInstance(caught.exception, RuntimeError)
        self.assertRegex(str(caught.exception), r'Extraction failed/degraded.*logs/extract')
        attempt = self.conn.execute("SELECT * FROM attempts WHERE kind='extract'").fetchone()
        self.assertEqual(attempt['status'], 'failed')
        self.assertIn('not_a_function', (self.work / attempt['log_path']).read_text())
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 0)

    def test_clean_early_extraction_eof_reports_missing_frame_and_retains_prefix(self):
        media.scan(self.conn, self.work, self.small)
        real_decoder = media.decoder
        def truncated(video, ffmpeg, log, filter_file=None, count=None):
            return real_decoder(video, ffmpeg, log, filter_file, count=1)
        with patch.object(media, 'decoder', side_effect=truncated):
            with self.assertRaisesRegex(ValueError, 'ended before requested frame 2'):
                media.extract(self.conn, self.work, [0, 2])
        self.assertEqual([r[0] for r in self.conn.execute('SELECT frame_no FROM assets')], [0])
        self.assertEqual(self.conn.execute(
            "SELECT status FROM attempts WHERE kind='extract'").fetchone()[0], 'failed')

    def test_real_pixel_mismatch_keeps_its_own_error(self):
        media.scan(self.conn, self.work, self.small)
        with self.conn:
            self.conn.execute("UPDATE frames SET digest='wrong-pixels' WHERE frame_no=0")
        with self.assertRaisesRegex(ValueError, 'does not match.*pixel digest'):
            media.extract(self.conn, self.work, [0])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 0)

    def test_budget_exactly_at_tail_finishes_without_an_extra_decode(self):
        result = media.scan(self.conn, self.work, self.small, max_new_frames=8)
        self.assertTrue(result['full_compute_complete'])
        self.assertEqual(result['attempts'][-1]['status'], 'complete')
        with patch.object(media, 'decoder', side_effect=AssertionError('Unexpected replay')):
            self.assertTrue(media.scan(self.conn, self.work, self.small)['full_compute_complete'])

    def test_budget_at_tail_still_checks_decoder_failure_after_last_frame(self):
        def failed_tail(video, ffmpeg, log, filter_file=None, count=None):
            script = ('import pathlib,sys; sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes()); '
                      'sys.stdout.flush(); sys.stderr.write("synthetic decoder tail failure\\n"); sys.exit(7)')
            return subprocess.Popen([sys.executable, '-B', '-c', script, str(self.ppm)],
                                    stdout=subprocess.PIPE, stderr=log, **media.process_options())
        with patch.object(media, 'decoder', side_effect=failed_tail):
            with self.assertRaisesRegex(RuntimeError, 'FFmpeg decode failed/degraded'):
                media.scan(self.conn, self.work, self.small, max_new_frames=8)
        result = store.status(self.conn)
        self.assertEqual(result['computed_frames'], 8)
        self.assertFalse(result['full_compute_complete'])
        self.assertEqual(result['attempts'][-1]['status'], 'failed')

    def test_budget_does_not_hide_genuinely_early_decoder_eof(self):
        real_decoder = media.decoder
        def truncated(video, ffmpeg, log, filter_file=None, count=None):
            return real_decoder(video, ffmpeg, log, filter_file, count=2)
        with patch.object(media, 'decoder', side_effect=truncated):
            with self.assertRaisesRegex(ValueError, 'count does not match'):
                media.scan(self.conn, self.work, self.small, max_new_frames=8)
        result = store.status(self.conn)
        self.assertEqual(result['computed_frames'], 2)
        self.assertFalse(result['full_compute_complete'])


if __name__ == '__main__':
    unittest.main()
