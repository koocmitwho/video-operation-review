"""Conservative local inputs whose bytes can define the entire media identity.

No subprocess or URL is opened here. Apply input_options before the input path
at every FFmpeg/ffprobe entry, including their first metadata probe.
"""
from pathlib import Path
import re


class InputPolicyError(ValueError):
    code = 'unsupported_media_input'

    def __init__(self, reason):
        super().__init__('unsupported_media_input: ' + reason)


def _reject(reason):
    raise InputPolicyError(reason)


def _check_mov(stream, file_size):
    """Walk bounded box headers, never read sample data or follow references.

    Common self-contained MOV/MP4 is accepted. Compressed/reference movies and
    image-item metadata are outside this policy; do not silently skip their
    potentially different dependency model. External drefs are rejected even
    though enable_drefs=0 also protects the FFmpeg boundary.
    """
    remaining = 100000
    found_moov = False

    def read_at(offset, size):
        stream.seek(offset)
        data = stream.read(size)
        if len(data) != size:
            _reject('Incomplete MOV/MP4 box metadata.')
        return data

    def boxes(start, end):
        nonlocal remaining
        while start < end:
            remaining -= 1
            if remaining < 0 or end - start < 8:
                _reject('MOV/MP4 box metadata exceeds policy limits or is malformed.')
            header = read_at(start, 8)
            size, kind = int.from_bytes(header[:4], 'big'), header[4:]
            header_size = 8
            if size == 1:
                if end - start < 16:
                    _reject('Incomplete extended MOV/MP4 box.')
                size = int.from_bytes(read_at(start + 8, 8), 'big')
                header_size = 16
            elif size == 0:
                size = end - start
            if size < header_size or size > end - start:
                _reject('MOV/MP4 box extent is outside its parent.')
            yield kind, start + header_size, start + size
            start += size

    def data_references(start, end):
        if end - start < 8:
            _reject('Incomplete MOV/MP4 dref.')
        header = read_at(start, 8)
        count = int.from_bytes(header[4:], 'big')
        if header[:4] != b'\0\0\0\0' or not 1 <= count <= 4096:
            _reject('Unsupported MOV/MP4 data-reference table.')
        entries = 0
        for kind, payload, stop in boxes(start + 8, end):
            entries += 1
            if kind != b'url ' or stop - payload != 4 or read_at(payload, 4) != b'\0\0\0\1':
                _reject('External or unsupported MOV/MP4 data reference; use a self-contained file.')
        if entries != count:
            _reject('MOV/MP4 data-reference count does not match its entries.')

    containers = {b'moov', b'trak', b'mdia', b'minf', b'dinf', b'stbl', b'udta'}
    def walk(start, end, depth=0):
        nonlocal found_moov
        if depth > 16:
            _reject('MOV/MP4 box nesting exceeds input policy limits.')
        for kind, payload, stop in boxes(start, end):
            if kind in {b'cmov', b'rmra', b'rmda', b'rdrf', b'iloc'}:
                _reject('Compressed/reference MOV or image-item dependencies are not supported.')
            if kind == b'moov':
                found_moov = True
            if kind == b'dref':
                data_references(payload, stop)
            elif kind in containers:
                walk(payload, stop, depth + 1)
            elif kind == b'meta':
                if stop - payload < 4 or read_at(payload, 4) != b'\0\0\0\0':
                    _reject('Unsupported MOV/MP4 metadata box layout.')
                walk(payload + 4, stop, depth + 1)
    walk(0, file_size)
    if not found_moov:
        _reject('MOV/MP4 must include its own movie metadata; standalone fragments are unsupported.')


def _identify(path, allow_subtitles=False):
    with Path(path).open('rb') as stream:
        prefix = stream.read(4096)
        if prefix.startswith(b'\x1a\x45\xdf\xa3'):
            return 'matroska'
        if prefix[:4] == b'RIFF' and prefix[8:12] == b'AVI ':
            return 'avi'
        if prefix[4:8] in {b'ftyp', b'moov', b'mdat', b'wide', b'free', b'skip'}:
            stream.seek(0, 2)
            _check_mov(stream, stream.tell())
            return 'mov'
        if allow_subtitles:
            text = prefix.removeprefix(b'\xef\xbb\xbf').lstrip(b'\r\n \t')
            if re.match(rb'WEBVTT(?:[ \t]|\r?\n|$)', text):
                return 'webvtt'
            if re.match(rb'\d+\r?\n\d+:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d+:\d{2}:\d{2}[,.]\d{3}', text):
                return 'srt'
    _reject('Use a self-contained Matroska/WebM, AVI or MOV/MP4 file'
            + (' or UTF-8 SRT/WebVTT subtitles.' if allow_subtitles else '.')
            + ' Playlists, manifests, image sequences and other input formats are unsupported.')


def require_self_contained(path):
    """Return the accepted container name or raise InputPolicyError, without helpers."""
    return _identify(path)


def input_options(path, allow_subtitles=False):
    """Restrict both auto/nested demuxing and protocols before the input is parsed."""
    kind = _identify(path, allow_subtitles)
    whitelist = {'matroska': 'matroska,webm', 'mov': 'mov,mp4,m4a,3gp,3g2,mj2'}.get(kind, kind)
    options = ['-protocol_whitelist', 'file', '-format_whitelist', whitelist, '-f', kind]
    if kind == 'mov':
        options += ['-enable_drefs', '0', '-use_absolute_path', '0']
    return options
