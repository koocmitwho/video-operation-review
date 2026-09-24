"""Subtitles/ASR are time-aligned clues, never visual evidence."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vor_store as store
import vor_media as media
from make_fixtures import make_fixtures


class LanguageContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='vor subtitle 中文 ')
        cls.root=Path(cls.temp.name)
        cls.cfr,cls.vfr=make_fixtures(cls.root/'input')
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def setUp(self):
        self.work=self.root/self._testMethodName
        self.conn=store.connect(self.work,create=True)
        self.addCleanup(self.conn.close)
        media.scan(self.conn,self.work,self.vfr)
    def lang(self):
        self.assertIsNotNone(importlib.util.find_spec('vor_language'),'Subtitle alignment interface missing')
        import vor_language
        return vor_language
    def write(self,name,text):
        p=self.work/name; p.write_text(text,encoding='utf-8'); return p
    def test_srt_offset_overlap_and_mixed_terms_preserve_original(self):
        p=self.write('mixed.srt','1\n00:00:00,000 --> 00:00:00,210\n设置 Rate 为 0.02\n\n2\n00:00:00,150 --> 00:00:00,400\nClick Apply 应用\n')
        result=self.lang().import_subtitles(self.conn,self.work,p,offset=5.0,language='zh-en')
        self.assertEqual(result['cues'][0]['frame_ranges'],[[0,2]])
        self.assertEqual(result['cues'][1]['frame_ranges'],[[1,2]])  # frame 1 is displayed until PTS 5.20
        self.assertEqual(result['cues'][0]['original_start'],0.0)
        self.assertEqual(result['cues'][0]['start_time'],5.0)
        self.assertIn('overlap',result['warnings'])
        self.assertIn('Rate',result['cues'][0]['text_original'])
        self.assertEqual(store.status(self.conn)['recorded_visual_unique_frames'],0)
    def test_vtt_is_parsed_by_ffmpeg(self):
        p=self.write('mixed.vtt','WEBVTT\n\nA\n00:00.040 --> 00:00.201\nMesh 网格\n\n')
        result=self.lang().import_subtitles(self.conn,self.work,p,offset=5)
        self.assertEqual(result['cues'][0]['frame_ranges'],[[1,2]])
        self.assertIn('Mesh',result['cues'][0]['text_original'])
    def test_asr_json_translation_keeps_source_and_explicit_time_base(self):
        p=self.write('speech.json',json.dumps({'time_base':'video_relative','language':'zh-en','segments':[{'start':0.04,'end':0.3,'text':'点击 Apply','translation':'Click Apply'}]}))
        result=self.lang().import_transcript(self.conn,self.work,p)
        cue=result['cues'][0]
        self.assertEqual(cue['start_time'],5.04)
        self.assertEqual(cue['text_original'],'点击 Apply')
        self.assertEqual(cue['translation'],'Click Apply')
        self.assertEqual(cue['frame_ranges'],[[1,2]])
    def test_unknown_time_base_and_nan_rejected(self):
        lang=self.lang()
        for data in [{'segments':[{'start':0,'end':1,'text':'x'}]}, {'time_base':'original','segments':[{'start':float('nan'),'end':1,'text':'x'}]}]:
            with self.assertRaises(ValueError): lang.import_transcript(self.conn,self.work,self.write('bad.json',json.dumps(data)))
    def test_missing_audio_and_subtitles_report_unavailable(self):
        result=self.lang().tracks(self.conn)
        self.assertEqual(result['audio'],[])
        self.assertEqual(result['subtitles'],[])
        self.assertFalse(result['asr_started'])
    def test_outside_video_cue_is_preserved_as_unaligned(self):
        p=self.write('outside.srt','1\n00:01:00,000 --> 00:01:01,000\noutside\n')
        result=self.lang().import_subtitles(self.conn,self.work,p)
        self.assertEqual(result['cues'][0]['frame_ranges'],[])
        self.assertIn('outside_index',result['warnings'])

    def test_cue_between_vfr_pts_overlaps_the_displayed_frame(self):
        p=self.write('between.srt','1\n00:00:05,050 --> 00:00:05,100\ncurrently displayed\n')
        result=self.lang().import_subtitles(self.conn,self.work,p)
        self.assertEqual(result['cues'][0]['frame_ranges'],[[1,1]])

    def test_embedded_text_track_retains_nonzero_original_pts(self):
        lang=self.lang()
        sub=self.write('embed.srt','1\n00:00:05,040 --> 00:00:05,300\nApply 应用\n')
        video=self.work/'with-subtitle.mkv'
        subprocess.run(['ffmpeg','-v','error','-y','-copyts','-i',str(self.vfr),'-i',str(sub),'-map','0:v:0','-map','1:s:0','-c','copy',str(video)],check=True,capture_output=True)
        result=lang.import_subtitles(self.conn,self.work,video,stream=0)
        self.assertEqual(result['cues'][0]['start_time'],5.04)
        self.assertEqual(result['cues'][0]['frame_ranges'],[[1,2]])

    def test_language_import_is_cached_and_does_not_overwrite_prior_alignment(self):
        lang=self.lang(); p=self.write('reuse.srt','1\n00:00:00,000 --> 00:00:00,400\nApply\n')
        first=lang.import_subtitles(self.conn,self.work,p,offset=5)
        second=lang.import_subtitles(self.conn,self.work,p,offset=5)
        self.assertTrue(second['cache_reused'])
        shifted=lang.import_subtitles(self.conn,self.work,p,offset=5.1)
        self.assertNotEqual(first['id'],shifted['id'])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM language_sources').fetchone()[0],2)

if __name__ == '__main__': unittest.main()
