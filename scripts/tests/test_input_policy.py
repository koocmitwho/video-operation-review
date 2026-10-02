"""Offline input boundaries: no manifest dependencies enter evidence/cache identity."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vor_language as language
import vor_media as media
import vor_store as store
from make_fixtures import make_fixtures


class InputPolicyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='vor input policy ')
        cls.root = Path(cls.temp.name)
        cls.cfr, cls.vfr = make_fixtures(cls.root / 'input')
        cls.avi = cls.root / 'input' / 'ordinary.avi'
        cls.mp4 = cls.root / 'input' / 'ordinary.mp4'
        for target, codec in ((cls.avi, 'ffv1'), (cls.mp4, 'mpeg4')):
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(cls.cfr), '-c:v', codec,
                            str(target)], check=True, capture_output=True, timeout=20)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.work = self.root / self._testMethodName
        self.conn = store.connect(self.work, create=True)
        self.addCleanup(self.conn.close)

    def manifest(self, name='disguised.mkv'):
        path = self.work / name
        shutil.copy2(self.cfr, self.work / 'segment.mkv')
        path.write_text("ffconcat version 1.0\nfile 'segment.mkv'\n", encoding='utf-8')
        return path

    def test_scan_rejects_a_local_manifest_disguised_as_video(self):
        with self.assertRaisesRegex(ValueError, 'unsupported_media_input'):
            media.scan(self.conn, self.work, self.manifest())
        self.assertIsNone(store.get_meta(self.conn, 'source'))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM frames').fetchone()[0], 0)

    def test_mov_external_dref_is_rejected_even_with_real_video_bytes(self):
        data = bytearray(self.mp4.read_bytes())
        entry = data.index(b'url ')
        self.assertEqual(data[entry + 4:entry + 8], b'\x00\x00\x00\x01')
        data[entry + 4:entry + 8] = b'\x00\x00\x00\x00'
        reference_movie = self.work / 'external-reference.mp4'
        reference_movie.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'unsupported_media_input'):
            media.scan(self.conn, self.work, reference_movie)

    def test_network_playlist_is_rejected_before_any_helper_can_run(self):
        playlist = self.work / 'renamed.mp4'
        playlist.write_text('#EXTM3U\n#EXTINF:1,\nhttp://127.0.0.1:9/private.ts\n', encoding='utf-8')
        def forbid_helper(*args, **kwargs):
            self.fail('Input policy must reject this manifest before launching any helper.')
        with patch.object(subprocess, 'Popen', side_effect=forbid_helper):
            with self.assertRaisesRegex(ValueError, 'unsupported_media_input'):
                media.scan(self.conn, self.work, playlist)

    def test_old_manifest_source_is_invalid_even_when_forced_hash_matches(self):
        source, cache, _ = store.source_file_identity(self.manifest('source.ffconcat'))
        with self.conn:
            store.set_meta(self.conn, 'source', source)
            store.set_meta(self.conn, 'source_hash_cache', cache)
        result = store.verify_source(self.conn, force_hash=True)
        self.assertFalse(result['valid'], result)
        self.assertIn('unsupported', result['code'])

    def test_all_media_input_processes_limit_protocol_and_demuxer_before_path(self):
        calls = []
        real_popen = subprocess.Popen
        def observe(args, **kwargs):
            calls.append(list(args))
            return real_popen(args, **kwargs)
        subtitle = self.work / 'words.srt'
        subtitle.write_text('1\n00:00:00,000 --> 00:00:00,500\nLocal text\n', encoding='utf-8')
        with patch.object(subprocess, 'Popen', side_effect=observe):
            media.scan(self.conn, self.work, self.cfr)
            media.extract(self.conn, self.work, [0])
            language.tracks(self.conn)
            language.import_subtitles(self.conn, self.work, subtitle)
            with store.database(self.work / 'mov', create=True) as movie_conn:
                media.scan(movie_conn, self.work / 'mov', self.mp4)
        inputs = tuple(map(str, (self.cfr, self.mp4, subtitle)))
        readers = [args for args in calls if any(path in args for path in inputs)]
        self.assertGreaterEqual(len(readers), 6)
        for args in readers:
            with self.subTest(args=args):
                path_index = min(args.index(p) for p in inputs if p in args)
                self.assertIn('-protocol_whitelist', args[:path_index])
                self.assertEqual(args[args.index('-protocol_whitelist') + 1], 'file')
                self.assertIn('-format_whitelist', args[:path_index])
                allowed = args[args.index('-format_whitelist') + 1].split(',')
                self.assertNotIn('concat', allowed)
                self.assertNotIn('hls', allowed)
                if str(self.mp4) in args:
                    for flag in ('-enable_drefs', '-use_absolute_path'):
                        self.assertIn(flag, args[:path_index])
                        self.assertEqual(args[args.index(flag) + 1], '0')

    def test_ordinary_cfr_vfr_avi_and_mp4_still_scan_and_extract(self):
        for i, video in enumerate((self.cfr, self.vfr, self.avi, self.mp4)):
            with self.subTest(video=video.name), store.database(self.work / str(i), create=True) as conn:
                work = self.work / str(i)
                result = media.scan(conn, work, video)
                self.assertTrue(result['full_compute_complete'])
                self.assertEqual(result['video_total_frames'], 4 if video == self.vfr else 8)
                self.assertEqual(media.extract(conn, work, [0])['extracted_new'], 1)


if __name__ == '__main__':
    unittest.main()
