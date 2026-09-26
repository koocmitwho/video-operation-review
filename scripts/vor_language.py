"""FFmpeg-normalized subtitles and explicit-time-base ASR interchange. No model/API calls."""
from bisect import bisect_left
import json
import math
from pathlib import Path
import re
import subprocess

from vor_store import dump, get_meta, log_history, now, ranges, sha256
from vor_media import bind_source, finite_float, process_options, version
from vor_layers import canonical_hash


def tracks(conn,ffprobe='ffprobe'):
    source=get_meta(conn,'source')
    bind_source(conn,source['path'])
    p=subprocess.run([ffprobe,'-v','error','-show_streams','-of','json',source['path']],capture_output=True,**process_options())
    if p.returncode: raise ValueError(p.stderr.decode('utf-8',errors='replace'))
    streams=json.loads(p.stdout)['streams']
    simplify=lambda s:{k:s.get(k) for k in ('index','codec_name','codec_type','start_time','duration','tags')}
    return dict(audio=[simplify(s) for s in streams if s['codec_type']=='audio'],
                subtitles=[simplify(s) for s in streams if s['codec_type']=='subtitle'],asr_started=False,
                policy='Existing captions first. No automatic transcription, translation, model download or external upload.')


def _number(value):
    if type(value) not in (int,float) or not math.isfinite(value): raise ValueError('Timestamps/offsets must be finite numbers.')
    return float(value)


def _clock(text):
    h,m,s=text.replace(',','.').split(':')
    return int(h)*3600+int(m)*60+float(s)


def _normalized_srt(text):
    # This is a decoder of FFmpeg's canonical output, not a replacement SRT/VTT parser.
    result=[]
    for block in re.split(r'\n\s*\n',text.replace('\r\n','\n').strip()):
        lines=block.splitlines()
        if len(lines)<3 or not lines[0].isdigit(): raise ValueError('Unexpected FFmpeg-normalized SRT block.')
        match=re.fullmatch(r'(\d+:\d{2}:\d{2},\d{3}) --> (\d+:\d{2}:\d{2},\d{3})',lines[1])
        if not match: raise ValueError('Unexpected FFmpeg-normalized subtitle timestamp.')
        result.append(dict(start=_clock(match[1]),end=_clock(match[2]),text='\n'.join(lines[2:])))
    if not result: raise ValueError('No text subtitles available.')
    return result


def _alignment(conn):
    rows=list(conn.execute('SELECT frame_no,time_s,duration_time FROM frames ORDER BY frame_no'))
    warnings=[]; spans=[]; previous=None
    for i,r in enumerate(rows):
        t=r['time_s']
        if t is None: warnings.append('unknown_frame_time'); continue
        if previous is not None and t<=previous: warnings.append('non_increasing_frame_time')
        previous=t
        following=rows[i+1]['time_s'] if i+1<len(rows) else None
        duration=finite_float(r['duration_time'])
        end=following if following is not None and following>t else t+duration if duration and duration>0 else t
        if end==t: warnings.append('unknown_display_duration')
        spans.append((t,end,r['frame_no']))
    return sorted(spans),warnings


class _DisplayIntervalIndex:
    """Query sorted display spans, including overlaps caused by irregular PTS.

    Subtree maximum endpoints let a cue skip frames whose display has ended.
    A zero-duration state is a point: include it at cue start but not cue end.
    The endpoint's boolean distinguishes that inclusive point from a normal
    display interval's exclusive end, without inventing a frame duration.
    """

    def __init__(self, spans):
        self.spans = spans
        self.starts = []
        self.size = 1 << max(0, len(spans) - 1).bit_length()
        self.max_ends = [(-math.inf, False)] * (2 * self.size)
        for i, (start, stop, _) in enumerate(spans):
            self.starts.append(start)
            self.max_ends[self.size + i] = (stop, stop == start)
        for node in range(self.size - 1, 0, -1):
            self.max_ends[node] = max(self.max_ends[2 * node], self.max_ends[2 * node + 1])

    def frames(self, begin, end):
        limit = bisect_left(self.starts, end)
        boundary = (begin, False)
        members = []
        pending = [(1, 0, self.size)]
        while pending:
            node, left, right = pending.pop()
            if left >= limit or self.max_ends[node] <= boundary:
                continue
            if right - left == 1:
                members.append(self.spans[left][2])
                continue
            middle = (left + right) // 2
            pending.append((2 * node + 1, middle, right))
            pending.append((2 * node, left, middle))
        return sorted(set(members))


def _store(conn,source,segments,offset,language,time_base,key):
    spans,warnings=_alignment(conn); index=_DisplayIntervalIndex(spans)
    cues=[]; latest_end=None
    for i,s in enumerate(segments):
        begin=_number(s['start']); end=_number(s['end'])
        if end<=begin: raise ValueError('Every subtitle/transcript cue needs end > start.')
        if not isinstance(s.get('text'),str) or not s['text'].strip(): raise ValueError('Every cue needs original text.')
        if s.get('translation') is not None and not isinstance(s['translation'],str): raise ValueError('Translation must be text or null.')
        a,b=begin+offset,end+offset
        if latest_end is not None and a<latest_end: warnings.append('overlap')
        latest_end=max(latest_end or b,b)
        members=index.frames(a,b)
        if not members: warnings.append('outside_index')
        cues.append(dict(id=f'{key}:c{i+1}',original_start=begin,original_end=end,start_time=a,end_time=b,
                         text_original=s['text'],translation=s.get('translation'),language=s.get('language',language),
                         frame_ranges=ranges(members),alignment='display_interval_overlap' if members else 'unaligned',
                         speaker=s.get('speaker'),confidence=s.get('confidence'),evidence_role='language_clue_only'))
    record=dict(id=key,source=source,offset_seconds=offset,time_base=time_base,language=language,cues=cues,
                warnings=sorted(set(warnings)),created=now(),cache_reused=False,
                boundary='Speech/subtitles express intent; they do not prove clicks, UI values or execution success.')
    with conn:
        conn.execute('INSERT INTO language_sources VALUES (?,?)',(key,dump(record)))
        log_history(conn,'language_import',dict(id=key,source=source,cues=len(cues)))
    return record


def _cached(conn,key):
    row=conn.execute('SELECT payload FROM language_sources WHERE id=?',(key,)).fetchone()
    return dict(json.loads(row[0]),cache_reused=True) if row else None


def _index_key(conn):
    # Version 2 also covers long display intervals across unknown timestamps.
    # Keep historical language records, but do not reuse predecessor-only results.
    return canonical_hash({'alignment_version': 2, 'frames': [tuple(r) for r in conn.execute(
        'SELECT frame_no,time_s,duration_time FROM frames ORDER BY frame_no')]})


def import_subtitles(conn,work,path,offset=0.0,language='und',stream=0,ffmpeg='ffmpeg'):
    offset=_number(offset); path=Path(path).resolve(strict=True)
    if type(stream) is not int or stream<0: raise ValueError('Subtitle stream is a nonnegative s:N ordinal.')
    source=dict(path=str(path),sha256=sha256(path),kind='subtitle',stream=f's:{stream}',parser='FFmpeg',version=version(ffmpeg))
    key='lang-'+canonical_hash([source,offset,language,_index_key(conn)])[:24]
    cached=_cached(conn,key)
    if cached: return cached
    p=subprocess.run([ffmpeg,'-hide_banner','-nostdin','-v','error','-copyts','-i',str(path),'-map',f'0:s:{stream}',
                      '-c:s','srt','-f','srt','pipe:1'],capture_output=True,**process_options())
    logdir=Path(work)/'logs'; logdir.mkdir(exist_ok=True)
    (logdir/(key+'.log')).write_bytes(p.stderr)
    if p.returncode or p.stderr.strip():
        raise ValueError('Subtitle decoding unavailable/failed; inspect '+str(logdir/(key+'.log')))
    text=p.stdout.decode('utf-8-sig')
    if not text.strip(): raise ValueError('No text subtitle cues. Bitmap subtitles require a separately authorized OCR stage.')
    segments=_normalized_srt(text)
    return _store(conn,source,segments,offset,language,'source_pts_plus_offset',key)


def import_transcript(conn,work,path):
    path=Path(path).resolve(strict=True)
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data,dict) or data.get('time_base') not in ('original','video_relative'):
        raise ValueError('ASR interchange needs explicit time_base: original or video_relative.')
    segments=data.get('segments')
    if not isinstance(segments,list) or not segments: raise ValueError('ASR interchange needs nonempty segments.')
    if any(not isinstance(s,dict) or not all(k in s for k in ('start','end','text')) for s in segments):
        raise ValueError('Each ASR segment needs start, end, text.')
    offset=_number(data.get('offset_seconds',0.0))
    if data['time_base']=='video_relative':
        first=conn.execute('SELECT time_s FROM frames ORDER BY frame_no LIMIT 1').fetchone()
        if first is None or first[0] is None: raise ValueError('Cannot align relative ASR without the first original PTS.')
        offset+=first[0]
    source=dict(path=str(path),sha256=sha256(path),kind='asr_interchange',engine=data.get('engine','user_supplied'),
                model=data.get('model'),glossary=data.get('glossary',[]),provenance=data.get('provenance'))
    key='lang-'+canonical_hash([source,offset,_index_key(conn)])[:24]
    cached=_cached(conn,key)
    if cached: return cached
    return _store(conn,source,segments,offset,data.get('language','und'),data['time_base'],key)
