"""Streaming FFmpeg media work. Ordinals stay in presentation order; no FPS-derived timestamps."""
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image

from vor_store import (asset_path, begin_attempt, dump, end_attempt, get_meta, log_history,
                       now, require_asset, set_meta, sha256, status)


def process_options():
    # Do not open visible console windows for helpers on Windows.
    return {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}


def finite_float(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def version(executable):
    p = subprocess.run([executable, '-version'], capture_output=True, **process_options())
    if p.returncode:
        raise RuntimeError(f'{executable} version check failed')
    return p.stdout.decode('utf-8', errors='replace').splitlines()[0]


def source_identity(video):
    video = Path(video).resolve(strict=True)
    if not video.is_file():
        raise ValueError('Video must be a local file.')
    stat = video.stat()
    return {'path': str(video), 'size': stat.st_size, 'sha256': sha256(video)}


def bind_source(conn, video):
    source = source_identity(video)
    old = get_meta(conn, 'source')
    if old and (old['sha256'] != source['sha256'] or old['size'] != source['size']):
        raise ValueError('Source content differs from cached review. Use a new --work directory.')
    with conn:
        set_meta(conn, 'source', source)
    return source


def index_video(conn, work, video, ffprobe='ffprobe', checkpoint=100):
    if get_meta(conn, 'index_complete_clean', False):
        return
    work = Path(work)
    (work / 'logs').mkdir(exist_ok=True)
    attempt = begin_attempt(conn, 'index', {'ffprobe': ffprobe})
    log_rel = f'logs/index-{attempt}.log'
    count = 0
    proc = None
    try:
        with (work / log_rel).open('wb') as log:
            meta = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_streams',
                                   '-show_format', '-of', 'json', str(video)],
                                  stdout=subprocess.PIPE, stderr=log, **process_options())
            if meta.returncode:
                raise RuntimeError('ffprobe metadata failed; see index log.')
            media = json.loads(meta.stdout)
            if not media.get('streams'):
                raise ValueError('No first video stream (v:0).')
            stream = media['streams'][0]
            with conn:
                set_meta(conn, 'media', media)
                declared = stream.get('nb_frames')
                set_meta(conn, 'declared_frames', int(declared) if declared and declared.isdigit() else None)
                set_meta(conn, 'ffprobe_version', version(ffprobe))
                set_meta(conn, 'index_complete_clean', False)
            entries = ('frame=pts,pts_time,best_effort_timestamp,best_effort_timestamp_time,'
                       'width,height,key_frame,duration_time')
            proc = subprocess.Popen([ffprobe, '-v', 'error', '-select_streams', 'v:0',
                                     '-show_frames', '-show_entries', entries, '-of', 'compact=p=0:nk=0', str(video)],
                                    stdout=subprocess.PIPE, stderr=log, **process_options())
            previous_time = None
            anomalies = {'missing_pts': 0, 'missing_all_time': 0, 'non_increasing_time': 0}
            for raw in proc.stdout:
                values = {}
                for part in raw.decode('utf-8', errors='replace').strip().split('|'):
                    if '=' in part:
                        k, v = part.split('=', 1)
                        values[k] = None if v in {'N/A', ''} else v
                if 'width' not in values or 'height' not in values:
                    continue  # ffprobe may emit separate side-data lines, not additional frames.
                pts_time = finite_float(values.get('pts_time'))
                best = finite_float(values.get('best_effort_timestamp_time'))
                t = pts_time if pts_time is not None else best
                source = 'pts' if pts_time is not None else ('best_effort' if best is not None else 'missing')
                if pts_time is None:
                    anomalies['missing_pts'] += 1
                if t is None:
                    anomalies['missing_all_time'] += 1
                elif previous_time is not None and t <= previous_time:
                    anomalies['non_increasing_time'] += 1
                if t is not None:
                    previous_time = t
                data = (count, values.get('pts'), values.get('pts_time'), values.get('best_effort_timestamp'),
                        values.get('best_effort_timestamp_time'), t, source, int(values['width']),
                        int(values['height']), int(values.get('key_frame') or 0), values.get('duration_time'))
                existing = conn.execute('SELECT frame_no,pts,pts_time,best_effort_timestamp,best_effort_time,'
                                        'time_s,time_source,width,height,key_frame,duration_time '
                                        'FROM frames WHERE frame_no=?', (count,)).fetchone()
                if existing and tuple(existing) != data:
                    raise ValueError(f'Index replay mismatch at frame {count}; use a fresh review directory.')
                conn.execute('INSERT OR IGNORE INTO frames(frame_no,pts,pts_time,best_effort_timestamp,'
                             'best_effort_time,time_s,time_source,width,height,key_frame,duration_time) '
                             'VALUES (?,?,?,?,?,?,?,?,?,?,?)', data)
                count += 1
                if count % checkpoint == 0:
                    conn.execute('UPDATE attempts SET decoded_frames=? WHERE id=?', (count, attempt))
                    conn.commit()
            code = proc.wait()
            log.flush()
            if code or (work / log_rel).stat().st_size:
                raise RuntimeError(f'ffprobe did not finish cleanly (exit {code}); see {log_rel}.')
            if count == 0:
                raise ValueError('No decodable video frames.')
            with conn:
                set_meta(conn, 'video_total_frames', count)
                set_meta(conn, 'index_complete_clean', True)
                set_meta(conn, 'timestamp_anomalies', anomalies)
            end_attempt(conn, attempt, 'complete', count, log_path=log_rel)
    except BaseException as exc:
        conn.commit()  # Retain only complete rows already parsed.
        end_attempt(conn, attempt, 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                    count, error=str(exc) or type(exc).__name__, log_path=log_rel)
        raise
    finally:
        if proc:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()


def token(stream):
    result = bytearray()
    while True:
        char = stream.read(1)
        if not char:
            return bytes(result) if result else None
        if char == b'#' and not result:
            stream.readline()
        elif char.isspace():
            if result:
                return bytes(result)
        else:
            result.extend(char)


def read_ppm(stream):
    magic = token(stream)
    if magic is None:
        return None
    if magic != b'P6':
        raise ValueError(f'Unexpected decoder frame header: {magic!r}')
    width, height, maximum = int(token(stream)), int(token(stream)), int(token(stream))
    if width <= 0 or height <= 0 or maximum != 255:
        raise ValueError('Expected positive RGB24 PPM dimensions and maxval 255.')
    length = width * height * 3
    raw = bytearray()
    while len(raw) < length:
        chunk = stream.read(length - len(raw))
        if not chunk:
            raise ValueError(f'Truncated RGB frame: received {len(raw)} of {length} bytes.')
        raw.extend(chunk)
    return np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)


@lru_cache(maxsize=16)
def _filter_file_option(ffmpeg):
    """Keep large graphs in files across legacy and current FFmpeg interfaces."""
    probe = subprocess.run([ffmpeg, '-hide_banner', '-h', 'full'],
                           capture_output=True, timeout=10, **process_options())
    if probe.returncode:
        raise RuntimeError(f'Cannot inspect FFmpeg filter-file options (exit {probe.returncode}).')
    # Older FFmpeg lacks generic file-backed options; newer versions removed
    # filter_script. Detect the installed interface instead of parsing versions.
    legacy = any(line.startswith(b'-filter_script') for line in probe.stdout.splitlines())
    return '-filter_script:v' if legacy else '-/filter:v'


def decoder(video, ffmpeg, log, filter_file=None, count=None):
    args = [ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-noautorotate', '-copyts',
            '-i', str(video), '-map', '0:v:0', '-an', '-sn', '-dn']
    if filter_file:
        args += [_filter_file_option(ffmpeg), str(filter_file)]
    args += ['-fps_mode', 'passthrough', '-c:v', 'ppm', '-pix_fmt', 'rgb24']
    if count is not None:
        args += ['-frames:v', str(count)]
    args += ['-f', 'image2pipe', 'pipe:1']
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=log, **process_options())


def pixel_digest(array):
    h = hashlib.sha256(f'{array.shape[1]}x{array.shape[0]}:rgb24:'.encode('ascii'))
    h.update(array.tobytes())
    return h.hexdigest()


def metrics(previous, current, tile_size, pixel_threshold):
    if previous is None or previous.shape != current.shape:
        return None, None, None, None, []
    # Full-resolution, all RGB channels. No resizing before exact comparison/diff.
    delta = np.abs(current.astype(np.int16) - previous.astype(np.int16)).max(axis=2)
    changed = int(np.count_nonzero(delta >= pixel_threshold))
    height, width = delta.shape
    ys, xs = np.arange(0, height, tile_size), np.arange(0, width, tile_size)
    sums = np.add.reduceat(np.add.reduceat(delta, ys, axis=0, dtype=np.int64), xs, axis=1)
    area = np.minimum(tile_size, height - ys)[:, None] * np.minimum(tile_size, width - xs)[None, :]
    means = sums / area
    y, x = np.unravel_index(np.argmax(means), means.shape)
    # Save strongest local region compactly; every tile participates in the maximum.
    local = [{'box': [int(xs[x]), int(ys[y]), min(width, int(xs[x]) + tile_size),
                      min(height, int(ys[y]) + tile_size)], 'mean_delta': float(means[y, x])}]
    return float(delta.mean()), float(means[y, x]), changed, changed / delta.size, local


def scan(conn, work, video, ffmpeg='ffmpeg', ffprobe='ffprobe', tile_size=32,
         pixel_threshold=8, checkpoint=100, max_new_frames=None):
    if tile_size < 1 or not 1 <= pixel_threshold <= 255 or checkpoint < 1:
        raise ValueError('tile_size/checkpoint must be positive; pixel_threshold must be 1..255.')
    if max_new_frames is not None and max_new_frames < 1:
        raise ValueError('max_new_frames must be positive when given.')
    source = bind_source(conn, video)
    config = {'tile_size': tile_size, 'pixel_threshold': pixel_threshold,
              'pixel_format': 'rgb24', 'autorotate': False, 'video_stream': 'v:0',
              'ffmpeg_version': version(ffmpeg)}
    old_config = get_meta(conn, 'scan_config')
    if old_config and old_config != config:
        raise ValueError('Computation configuration/version differs. Use a new --work directory.')
    with conn:
        set_meta(conn, 'scan_config', config)
    index_video(conn, work, source['path'], ffprobe, checkpoint)
    if status(conn)['full_compute_complete']:
        return status(conn)
    work = Path(work)
    attempt = begin_attempt(conn, 'scan', {'max_new_frames': max_new_frames, 'checkpoint': checkpoint})
    log_rel = f'logs/scan-{attempt}.log'
    decoded = new = 0
    proc = None
    previous = previous_digest = None
    exact_start = 0
    state = 'complete'
    total_frames = get_meta(conn, 'video_total_frames')
    try:
        with (work / log_rel).open('wb') as log:
            proc = decoder(source['path'], ffmpeg, log)
            while True:
                array = read_ppm(proc.stdout)
                if array is None:
                    break
                n = decoded
                decoded += 1
                row = conn.execute('SELECT * FROM frames WHERE frame_no=?', (n,)).fetchone()
                if row is None or (row['height'], row['width']) != array.shape[:2]:
                    raise ValueError(f'Decode/index alignment failed at frame {n}.')
                digest = pixel_digest(array)
                if digest != previous_digest:
                    exact_start = n
                if row['digest'] is not None:
                    if row['digest'] != digest:
                        raise ValueError(f'Decoder replay pixel mismatch at frame {n}.')
                else:
                    overall, local, pixels, fraction, tiles = metrics(previous, array, tile_size, pixel_threshold)
                    conn.execute('UPDATE frames SET digest=?,exact_start=?,global_delta=?,max_local_delta=?,'
                                 'changed_pixels=?,changed_fraction=?,tiles=? WHERE frame_no=?',
                                 (digest, exact_start, overall, local, pixels, fraction, dump(tiles), n))
                    new += 1
                previous, previous_digest = array, digest
                if decoded % checkpoint == 0:
                    conn.execute('UPDATE attempts SET decoded_frames=?,new_frames=? WHERE id=?', (decoded, new, attempt))
                    conn.commit()
                # At the indexed tail, consume EOF and check the real exit/log instead
                # of killing a decoder that may still report a final error.
                if max_new_frames is not None and new >= max_new_frames and decoded < total_frames:
                    state = 'paused_budget'
                    break
            if state == 'paused_budget':
                proc.kill()
            code = proc.wait()
            log.flush()
            if state == 'complete' and (code or (work / log_rel).stat().st_size):
                raise RuntimeError(f'FFmpeg decode failed/degraded (exit {code}); see {log_rel}.')
            if state == 'complete' and decoded != get_meta(conn, 'video_total_frames'):
                raise ValueError('Decoded count does not match full frame index.')
            with conn:
                set_meta(conn, 'scan_complete_clean', state == 'complete')
            end_attempt(conn, attempt, state, decoded, new, log_path=log_rel)
    except BaseException as exc:
        with conn:
            set_meta(conn, 'scan_complete_clean', False)
        end_attempt(conn, attempt, 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed', decoded, new,
                    error=str(exc) or type(exc).__name__, log_path=log_rel)
        raise
    finally:
        if proc:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
    return status(conn)


def compact_select(numbers):
    spans = []
    for n in sorted(set(numbers)):
        if spans and n == spans[-1][1] + 1:
            spans[-1][1] = n
        else:
            spans.append([n, n])
    terms = [f'eq(n\\,{a})' if a == b else f'between(n\\,{a}\\,{b})' for a, b in spans]
    # FFmpeg's expression parser cannot handle a long left-deep sum. Pair terms
    # into a balanced tree while keeping consecutive ranges compact.
    while len(terms) > 1:
        terms = [f'({terms[i]}+{terms[i + 1]})' if i + 1 < len(terms) else terms[i]
                 for i in range(0, len(terms), 2)]
    return 'select=' + (terms[0] if terms else '')


def extract(conn, work, frames, ffmpeg='ffmpeg'):
    work = Path(work)
    source = get_meta(conn, 'source')
    bind_source(conn, source['path'])
    numbers = sorted(set(frames))
    missing = []
    for n in numbers:
        row = conn.execute('SELECT * FROM frames WHERE frame_no=? AND digest IS NOT NULL', (n,)).fetchone()
        if row is None:
            raise ValueError(f'Frame {n} has not been computed.')
        ident = f'f{n:09d}'
        if conn.execute('SELECT 1 FROM assets WHERE id=?', (ident,)).fetchone():
            require_asset(conn, work, ident)
        else:
            missing.append(n)
    if not missing:
        return {'extracted_new': 0, 'assets': [f'f{n:09d}' for n in numbers]}
    (work / 'evidence').mkdir(exist_ok=True)
    attempt = begin_attempt(conn, 'extract', {'requested_frames': missing})
    log_rel = f'logs/extract-{attempt}.log'
    filter_file = work / 'logs' / f'extract-{attempt}.filter'
    filter_file.write_text(compact_select(missing), encoding='utf-8')
    proc = None
    done = 0
    try:
        with (work / log_rel).open('wb') as log:
            proc = decoder(source['path'], ffmpeg, log, filter_file, len(missing))
            for n in missing:
                array = read_ppm(proc.stdout)
                if array is None:
                    # stdout reached EOF, so waiting cannot block on an unread
                    # output pipe. Pixel mismatches take the kill/cleanup path.
                    code = proc.wait()
                    log.flush()
                    if code or (work / log_rel).stat().st_size:
                        raise RuntimeError(f'Extraction failed/degraded (exit {code}); see {log_rel}.')
                    raise ValueError(f'Extraction ended before requested frame {n}; see {log_rel}.')
                row = conn.execute('SELECT digest FROM frames WHERE frame_no=?', (n,)).fetchone()
                if pixel_digest(array) != row[0]:
                    raise ValueError(f'Extracted frame {n} does not match stored full-resolution pixel digest.')
                ident = f'f{n:09d}'
                relative = f'evidence/{ident}.png'
                path = asset_path(work, relative)
                temp = path.with_suffix('.png.tmp')
                Image.fromarray(array).save(temp, format='PNG')
                temp.replace(path)
                with conn:
                    conn.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?,?)',
                                 (ident, n, 'full', relative, sha256(path), None, None, now()))
                done += 1
            code = proc.wait()
            log.flush()
            if code or (work / log_rel).stat().st_size:
                raise RuntimeError(f'Extraction failed/degraded (exit {code}); see {log_rel}.')
        end_attempt(conn, attempt, 'complete', done, done, log_path=log_rel)
    except BaseException as exc:
        end_attempt(conn, attempt, 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed', done, done,
                    error=str(exc) or type(exc).__name__, log_path=log_rel)
        raise
    finally:
        if proc:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
    return {'extracted_new': done, 'assets': [f'f{n:09d}' for n in numbers]}


def crop(conn, work, asset_id, box):
    asset, path = require_asset(conn, work, asset_id)
    if asset['kind'] != 'full':
        raise ValueError('Crop a full evidence image; coordinates are original pixels.')
    with Image.open(path) as image:
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
            raise ValueError('Crop rectangle must be within original image bounds.')
        ident = asset_id + '-crop-' + '-'.join(map(str, box))
        rel = f'evidence/{ident}.png'
        target = asset_path(work, rel)
        if conn.execute('SELECT 1 FROM assets WHERE id=?', (ident,)).fetchone():
            require_asset(conn, work, ident)
        else:
            temp = target.with_suffix('.png.tmp')
            image.crop(box).save(temp, format='PNG')
            temp.replace(target)
            with conn:
                conn.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?,?)',
                             (ident, asset['frame_no'], 'crop', rel, sha256(target), asset_id, dump(box), now()))
    return {'asset_id': ident, 'path': str(target.resolve()), 'frame_no': asset['frame_no']}
