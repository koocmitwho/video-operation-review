"""持久化审阅记录、证据完整性与完成度。"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from vor_record_contract import (STEP_FIELDS, check_import_records, check_issue, check_step,
                                 evidence_references, record_contract_audit, record_contract_errors)

SCHEMA_VERSION = 3


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def issue_steps(issue, steps):
    """Resolve explicit issue links first; use intersecting ranges only as a fallback."""
    explicit = issue.get('step_ids') or ([issue['step_id']] if issue.get('step_id') else [])
    if explicit:
        return list(explicit) if isinstance(explicit, list) else [explicit]
    start, end = issue.get('start_frame'), issue.get('end_frame')
    if type(start) is int and type(end) is int:
        return [step['id'] for step in steps if type(step.get('start_frame')) is int
                and type(step.get('end_frame')) is int
                and step['start_frame'] <= end and step['end_frame'] >= start]
    return []


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def file_signature(path):
    """文件属性用于复用已计算的内容哈希；Windows 另取文件变更时间。"""
    with Path(path).open('rb') as stream:
        stat = os.fstat(stream.fileno())
        signature = dict(size=stat.st_size, mtime_ns=stat.st_mtime_ns,
                         ctime_ns=stat.st_ctime_ns, device=stat.st_dev, inode=stat.st_ino)
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            import msvcrt
            class FileBasicInfo(ctypes.Structure):
                _fields_ = [(name, ctypes.c_longlong) for name in
                            ('creation', 'access', 'write', 'change')] + [('attributes', wintypes.DWORD)]
            info = FileBasicInfo()
            query = ctypes.WinDLL('kernel32', use_last_error=True).GetFileInformationByHandleEx
            query.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
            query.restype = wintypes.BOOL
            if not query(msvcrt.get_osfhandle(stream.fileno()), 0, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            signature['change_time'] = info.change
    return signature


def source_file_identity(video, cache=None, force_hash=False):
    path = Path(video).resolve(strict=True)
    signature = file_signature(path)
    reused = (not force_hash and cache and cache.get('path') == str(path)
              and cache.get('signature') == signature and cache.get('sha256'))
    digest = cache['sha256'] if reused else sha256(path)
    if not reused and file_signature(path) != signature:
        raise ValueError('源文件在校验过程中发生变化，请待文件写入结束后重试。')
    source = dict(path=str(path), size=signature['size'], sha256=digest)
    proof = dict(source, signature=signature)
    return source, proof, not bool(reused)


def verify_source(conn, force_hash=False):
    expected = get_meta(conn, 'source') or {}
    result = dict(path=expected.get('path'), expected_sha256=expected.get('sha256'),
                  sha256=None, rehashed=False, method='unavailable', valid=False)
    if not expected.get('path'):
        return dict(result, code='source_missing', message='源视频路径缺失，请检查 source 元数据。')
    try:
        source, cache, rehashed = source_file_identity(
            expected['path'], get_meta(conn, 'source_hash_cache'), force_hash)
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
        return dict(result, code='source_missing', message='源视频文件缺失，请恢复 source 中记录的路径。')
    except (OSError, ValueError) as exc:
        return dict(result, code='source_unreadable', message=str(exc))
    with conn:
        set_meta(conn, 'source_hash_cache', cache)
    result.update(sha256=source['sha256'], rehashed=rehashed,
                  method='sha256_recomputed' if rehashed else 'cached_sha256_stat_match')
    if source['sha256'] != expected.get('sha256'):
        return dict(result, code='source_hash_mismatch', message='源视频 SHA-256 与扫描时记录不一致。')
    from vor_input_policy import InputPolicyError, require_self_contained
    try:
        require_self_contained(source['path'])
    except InputPolicyError as exc:
        return dict(result, code='source_unsupported_media_input', message=str(exc))
    return dict(result, valid=True)


def connect(work, create=False):
    work = Path(work).resolve()
    if create:
        work.mkdir(parents=True, exist_ok=True)
    db = work / 'review.sqlite3'
    if not create and not db.is_file():
        raise ValueError('No review database; run scan first.')
    conn = sqlite3.connect(db, timeout=30)
    conn.row_factory = sqlite3.Row
    old = None
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone():
        old = get_meta(conn, 'schema_version')
        if old not in (None, 1, 2, SCHEMA_VERSION):
            conn.close()
            raise ValueError(f'Unsupported database schema: {old}')
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS frames(
      frame_no INTEGER PRIMARY KEY, pts TEXT, pts_time TEXT,
      best_effort_timestamp TEXT, best_effort_time TEXT,
      time_s REAL, time_source TEXT NOT NULL, width INTEGER, height INTEGER,
      key_frame INTEGER, duration_time TEXT, digest TEXT, exact_start INTEGER,
      global_delta REAL, max_local_delta REAL, changed_pixels INTEGER,
      changed_fraction REAL, tiles TEXT);
    CREATE TABLE IF NOT EXISTS attempts(
      id INTEGER PRIMARY KEY, kind TEXT NOT NULL, started TEXT NOT NULL, ended TEXT,
      status TEXT NOT NULL, decoded_frames INTEGER DEFAULT 0, new_frames INTEGER DEFAULT 0,
      error TEXT, log_path TEXT, details TEXT);
    CREATE TABLE IF NOT EXISTS requests(
      frame_no INTEGER NOT NULL REFERENCES frames(frame_no), reason TEXT NOT NULL,
      origin TEXT NOT NULL, PRIMARY KEY(frame_no,reason,origin));
    CREATE TABLE IF NOT EXISTS candidates(
      frame_no INTEGER PRIMARY KEY REFERENCES frames(frame_no), reasons TEXT NOT NULL,
      represented_requests TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS assets(
      id TEXT PRIMARY KEY, frame_no INTEGER NOT NULL REFERENCES frames(frame_no),
      kind TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL,
      parent_id TEXT REFERENCES assets(id), crop TEXT, created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS views(
      id INTEGER PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id),
      frame_no INTEGER NOT NULL REFERENCES frames(frame_no), actor TEXT NOT NULL,
      tool TEXT NOT NULL, trace_ref TEXT NOT NULL, observation TEXT NOT NULL,
      asset_sha256 TEXT NOT NULL, created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS steps(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS issues(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS coverage(frame_no INTEGER PRIMARY KEY REFERENCES frames(frame_no), payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS omission_reviews(id TEXT PRIMARY KEY, payload TEXT NOT NULL, recorded_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, kind TEXT, created TEXT, payload TEXT);
    CREATE TABLE IF NOT EXISTS segments(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS intervals(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS interval_checks(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS layer_reviews(id TEXT PRIMARY KEY, payload TEXT NOT NULL, recorded_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sheets(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS language_sources(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    ''')
    columns = {r[1] for r in conn.execute('PRAGMA table_info(views)')}
    if 'presentation' not in columns:
        conn.execute("ALTER TABLE views ADD COLUMN presentation TEXT NOT NULL DEFAULT 'native'")
    if 'sheet_id' not in columns:
        conn.execute('ALTER TABLE views ADD COLUMN sheet_id TEXT')
    if get_meta(conn, 'review_mode') is None:
        set_meta(conn, 'review_mode', 'strict' if old in (1, 2) else 'layered')
    set_meta(conn, 'schema_version', SCHEMA_VERSION)
    conn.commit()
    return conn


@contextmanager
def database(work, create=False):
    conn = connect(work, create)
    try:
        yield conn
    finally:
        conn.close()


def set_meta(conn, key, value):
    conn.execute('INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                 (key, dump(value)))


def get_meta(conn, key, default=None):
    row = conn.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def log_history(conn, kind, value):
    conn.execute('INSERT INTO history(kind,created,payload) VALUES (?,?,?)', (kind, now(), dump(value)))


def begin_attempt(conn, kind, details=None):
    cur = conn.execute('INSERT INTO attempts(kind,started,status,details) VALUES (?,?,?,?)',
                       (kind, now(), 'running_or_unfinalized', dump(details)))
    conn.commit()
    return cur.lastrowid


def end_attempt(conn, attempt, status, decoded=0, new=0, error=None, log_path=None):
    conn.execute('UPDATE attempts SET ended=?,status=?,decoded_frames=?,new_frames=?,error=?,log_path=? WHERE id=?',
                 (now(), status, decoded, new, error, log_path, attempt))
    conn.commit()


def ranges(values):
    result = []
    for n in values:
        if result and n == result[-1][1] + 1:
            result[-1][1] = n
        else:
            result.append([n, n])
    return result


def status(conn, _record_errors=None):
    total = get_meta(conn, 'video_total_frames')
    indexed = conn.execute('SELECT COUNT(*) FROM frames').fetchone()[0]
    computed = conn.execute('SELECT COUNT(*) FROM frames WHERE digest IS NOT NULL').fetchone()[0]
    candidates = conn.execute('SELECT COUNT(*) FROM candidates').fetchone()[0]
    viewed = conn.execute('SELECT COUNT(DISTINCT frame_no) FROM views').fetchone()[0]
    done = conn.execute('SELECT COUNT(*) FROM candidates c WHERE EXISTS '
                        '(SELECT 1 FROM views v JOIN assets a ON a.id=v.asset_id '
                        'WHERE v.frame_no=c.frame_no AND a.kind="full" AND v.presentation="native")').fetchone()[0]
    full_viewed = conn.execute('SELECT COUNT(DISTINCT v.frame_no) FROM views v '
                               'JOIN assets a ON a.id=v.asset_id WHERE a.kind="full" AND v.presentation="native"').fetchone()[0]
    index_clean = get_meta(conn, 'index_complete_clean', False)
    compute_clean = get_meta(conn, 'scan_complete_clean', False)
    declared = get_meta(conn, 'declared_frames')
    count_mismatch = (declared != total) if index_clean and total is not None and declared is not None else None
    attempts = [dict(r) for r in conn.execute('SELECT * FROM attempts ORDER BY id')]
    contract_errors = record_contract_errors(conn) if _record_errors is None else _record_errors
    open_issues = []
    for row in conn.execute('SELECT payload FROM issues'):
        try:
            issue = json.loads(row[0])
        except (ValueError, TypeError):
            continue  # The field diagnostic is retained in record_contract_errors.
        if not check_issue(issue) and issue['status'] != 'resolved':
            open_issues.append(issue)
    result = {
        'video_total_frames': total, 'container_declared_frames': declared,
        'frame_count_basis': 'decoded_presentation_frames',
        'container_frame_count_mismatch': count_mismatch,
        'indexed_frames': indexed, 'computed_frames': computed,
        'computed_ranges': ranges(r[0] for r in conn.execute('SELECT frame_no FROM frames WHERE digest IS NOT NULL ORDER BY frame_no')),
        'unprocessed_ranges': ranges(r[0] for r in conn.execute('SELECT frame_no FROM frames WHERE digest IS NULL ORDER BY frame_no')),
        'source_frames_without_full_view_record_ranges': ranges(r[0] for r in conn.execute(
            'SELECT frame_no FROM frames f WHERE NOT EXISTS '
            '(SELECT 1 FROM views v JOIN assets a ON a.id=v.asset_id '
            'WHERE v.frame_no=f.frame_no AND a.kind="full" AND v.presentation="native") ORDER BY frame_no')),
        'unindexed_tail': None if index_clean else {'from_frame': indexed, 'end_frame': 'unknown'},
        'full_compute_complete': bool(index_clean and compute_clean and total and computed == total),
        'candidate_requests': conn.execute('SELECT COUNT(DISTINCT frame_no) FROM requests').fetchone()[0],
        'candidate_frames': candidates, 'candidates_reviewed_recorded': done,
        'candidates_pending': candidates - done,
        'candidate_selection_performed': get_meta(conn, 'selection_performed', False),
        'selected_candidates_review_complete_recorded': bool(candidates and candidates == done),
        'recorded_visual_unique_frames': viewed,
        'recorded_full_image_unique_frames': full_viewed,
        'view_events': conn.execute('SELECT COUNT(*) FROM views').fetchone()[0],
        'state_accounting_records': conn.execute('SELECT COUNT(*) FROM coverage').fetchone()[0],
        'omission_review_records': conn.execute('SELECT COUNT(*) FROM omission_reviews').fetchone()[0],
        'independently_verified_visual_frames': None,
        'all_frames_visual_review_complete_recorded': bool(total and full_viewed == total),
        'all_frames_visual_review_complete_verified': False,
        'visual_assurance': '查看登记关联图片工具引用；交付时核对宿主工具结果。',
        'candidate_pending_ranges': ranges(r[0] for r in conn.execute(
            'SELECT frame_no FROM candidates c WHERE NOT EXISTS '
            '(SELECT 1 FROM views v JOIN assets a ON a.id=v.asset_id '
            'WHERE v.frame_no=c.frame_no AND a.kind="full" AND v.presentation="native") ORDER BY frame_no')),
        'unresolved_issues': open_issues, 'attempts': attempts,
        'record_contract_errors': contract_errors, 'annotation_counts_available': not contract_errors,
        'timestamp_anomalies': get_meta(conn, 'timestamp_anomalies', {}),
        'near_duplicate_merging': False,
        'risk': '变化指标提供候选线索，关键操作通过原图、局部裁剪与前后状态核对。'
    }
    from vor_layers import coverage_counts
    if contract_errors:
        result.update({key: None for key in (
            'coarse_reviewed_frames_recorded', 'fine_reviewed_frames_recorded', 'fine_examined_frames_recorded',
            'fine_examined_ranges', 'not_fine_examined_ranges', 'coarse_reviewed_ranges', 'fine_reviewed_ranges',
            'not_coarse_reviewed_ranges', 'not_fine_reviewed_ranges', 'candidate_operation_units',
            'true_operation_count', 'approximate_merge_intervals')})
        result['near_duplicate_merging'] = None
    else:
        result.update(coverage_counts(conn))
        result['near_duplicate_merging'] = bool(result['approximate_merge_intervals'])
    result['candidate_pixel_equivalence'] = 'exact_consecutive_RGB_only'
    result['review_mode'] = get_meta(conn, 'review_mode', 'layered')
    result['recorded_overview_unique_frames'] = conn.execute(
        'SELECT COUNT(DISTINCT frame_no) FROM views WHERE presentation="overview"').fetchone()[0]
    return result


def rebuild_candidates(conn):
    conn.execute('DELETE FROM candidates')
    groups = {}
    for row in conn.execute('SELECT r.frame_no,r.reason,f.exact_start FROM requests r '
                            'JOIN frames f USING(frame_no) WHERE f.digest IS NOT NULL ORDER BY r.frame_no'):
        rep = row['exact_start']
        group = groups.setdefault(rep, {'reasons': set(), 'requests': set()})
        group['reasons'].add(f"{row['reason']}@{row['frame_no']}")
        group['requests'].add(row['frame_no'])
    conn.executemany('INSERT INTO candidates VALUES (?,?,?)',
                     [(rep, dump(sorted(g['reasons'])), dump(sorted(g['requests']))) for rep, g in groups.items()])
    set_meta(conn, 'selection_performed', True)


def select_candidates(conn, anchor_seconds=5.0, global_threshold=2.0, local_threshold=0.8,
                      min_changed_pixels=8, context_frames=1, mode='layered'):
    if mode == 'layered':
        if (anchor_seconds, global_threshold, local_threshold, min_changed_pixels, context_frames) != (5.0, 2.0, 0.8, 8, 1):
            raise ValueError('分层模式使用 plan 的分段参数；这些阈值参数请用于 --mode coverage（穷尽逐状态）或 --mode changes。')
        from vor_layers import prepare
        prepare(conn)
        return status(conn)
    params = dict(anchor_seconds=anchor_seconds, global_threshold=global_threshold,
                  local_threshold=local_threshold, min_changed_pixels=min_changed_pixels,
                  context_frames=context_frames, mode=mode)
    if mode not in {'coverage', 'changes'}:
        raise ValueError('Selection mode must be coverage or changes.')
    if min(anchor_seconds, global_threshold, local_threshold, context_frames) < 0 or min_changed_pixels < 1:
        raise ValueError('Thresholds must be non-negative; min_changed_pixels must be positive.')
    with conn:
        conn.execute("DELETE FROM requests WHERE origin='automatic'")
        bounds = conn.execute('SELECT MIN(frame_no),MAX(frame_no) FROM frames WHERE digest IS NOT NULL').fetchone()
        if bounds[0] is None:
            raise ValueError('No computed frames to select.')
        def add(n, reason):
            conn.execute('INSERT OR IGNORE INTO requests SELECT frame_no,?,? FROM frames '
                         'WHERE frame_no=? AND digest IS NOT NULL', (reason, 'automatic', n))
        add(bounds[0], 'first')
        add(bounds[1], 'last_computed')
        next_anchor = None
        for f in conn.execute('SELECT * FROM frames WHERE digest IS NOT NULL ORDER BY frame_no'):
            n, t = f['frame_no'], f['time_s']
            if t is not None and anchor_seconds > 0 and (next_anchor is None or t >= next_anchor):
                add(n, 'time_anchor')
                next_anchor = t + anchor_seconds
            reasons = []
            if mode == 'coverage' and f['exact_start'] == n:
                reasons.append('distinct_state')
            if f['global_delta'] is None and n > 0:
                reasons.append('dimension_change')
            if f['global_delta'] is not None and f['global_delta'] > 0:
                if f['global_delta'] >= global_threshold:
                    reasons.append('global_change')
                if f['max_local_delta'] >= local_threshold:
                    reasons.append('local_change')
                if f['changed_pixels'] >= min_changed_pixels:
                    reasons.append('pixel_change')
            for reason in reasons:
                add(n, reason)
            if reasons:
                for other in range(max(0, n - context_frames), n + context_frames + 1):
                    if other != n:
                        add(other, f'context_of_{n}')
        rebuild_candidates(conn)
        set_meta(conn, 'selection_config', params)
        set_meta(conn, 'review_mode', 'strict')
        log_history(conn, 'select', params)
    return status(conn)


def focus(conn, start, end, reason, stride=1):
    if start > end or stride < 1 or not reason.strip():
        raise ValueError('Provide an ordered original-time interval, positive stride and specific reason.')
    rows = list(conn.execute('SELECT frame_no FROM frames WHERE digest IS NOT NULL '
                            'AND time_s>=? AND time_s<=? ORDER BY frame_no', (start, end)))
    if not rows:
        raise ValueError('No computed frames in interval; inspect original timestamps or finish scan.')
    with conn:
        conn.executemany('INSERT OR IGNORE INTO requests VALUES (?,?,?)',
                         [(r[0], reason, 'focus') for r in rows[::stride]])
        rebuild_candidates(conn)
        log_history(conn, 'focus', {'start': start, 'end': end, 'reason': reason, 'stride': stride})
    return status(conn)


def asset_path(work, relative):
    root = Path(work).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Asset path escapes review workspace.')
    return path


def candidate_manifest(conn, work, pending=False, start=None, end=None):
    result = []
    sql = ('SELECT c.*,f.time_s,f.width,f.height,a.id AS asset_id,a.path FROM candidates c '
           'JOIN frames f USING(frame_no) LEFT JOIN assets a ON a.frame_no=c.frame_no AND a.kind="full" '
           'ORDER BY c.frame_no')
    for row in conn.execute(sql):
        viewed = bool(conn.execute('SELECT 1 FROM views v JOIN assets a ON a.id=v.asset_id '
                                   'WHERE v.frame_no=? AND a.kind="full" AND v.presentation="native"', (row['frame_no'],)).fetchone())
        if pending and viewed:
            continue
        if start is not None and (row['time_s'] is None or row['time_s'] < start):
            continue
        if end is not None and (row['time_s'] is None or row['time_s'] > end):
            continue
        entry = dict(row)
        entry['reasons'] = json.loads(entry['reasons'])
        entry['represented_requests'] = json.loads(entry['represented_requests'])
        entry['view_record_exists_for_full_image'] = viewed
        entry['absolute_path'] = str(asset_path(work, entry['path'])) if entry['path'] else None
        result.append(entry)
    return {'candidates': result, 'count': len(result),
            'filter_uses': 'representative original timestamp; exact-run request ordinals are retained'}


def require_asset(conn, work, asset_id):
    row = conn.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone()
    if not row:
        raise ValueError(f'Unknown asset: {asset_id}')
    path = asset_path(work, row['path'])
    if not path.is_file() or sha256(path) != row['sha256']:
        raise ValueError(f'Missing or changed asset: {asset_id}')
    return row, path


def record_view(conn, work, asset_id, actor, tool, trace, observation):
    if tool not in {'view_image', 'read_image', 'image_tool', 'visible_attachment'}:
        raise ValueError('tool 请使用 view_image、read_image、image_tool 或 visible_attachment。')
    if not all(s.strip() for s in [actor, trace, observation]):
        raise ValueError('Actor, actual tool-call reference and visual observation are required.')
    asset, path = require_asset(conn, work, asset_id)
    reference = trace.strip()
    image_name = reference.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'))
    bare_name = len(reference) < 40 and not any(s in reference for s in ('://', '#', ':', '/', '\\', ' '))
    if image_name or bare_name or reference in {asset_id, asset['path'], str(path)}:
        raise ValueError('请填写图片调用或消息引用，例如 read_image#msg-42、session://abc/step-7。')
    with conn:
        conn.execute('INSERT INTO views(asset_id,frame_no,actor,tool,trace_ref,observation,asset_sha256,created) '
                     'VALUES (?,?,?,?,?,?,?,?)',
                     (asset_id, asset['frame_no'], actor, tool, trace, observation, asset['sha256'], now()))
    return status(conn)


def import_records(conn, path):
    from vor_audit import check_aux_records
    from vor_layers import check_layer_records, import_layer_records
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('Records must be an object containing steps and/or issues arrays.')
    for key in ['steps', 'issues', 'coverage', 'omission_reviews']:
        if key in data and not isinstance(data[key], list):
            raise ValueError(f'{key} must be an array.')
    check_import_records(data)
    check_aux_records(conn, data)
    check_layer_records(conn, data)
    with conn:
        for table in ['steps', 'issues']:
            for entry in data.get(table, []):
                conn.execute(f'INSERT INTO {table} VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                             (entry['id'], dump(entry)))
        for entry in data.get('coverage', []):
            conn.execute('INSERT INTO coverage VALUES (?,?) ON CONFLICT(frame_no) DO UPDATE SET payload=excluded.payload',
                         (entry['frame_no'], dump(entry)))
        for entry in data.get('omission_reviews', []):
            conn.execute('INSERT INTO omission_reviews VALUES (?,?,?) ON CONFLICT(id) '
                         'DO UPDATE SET payload=excluded.payload,recorded_at=excluded.recorded_at',
                         (entry['id'], dump(entry), now()))
        import_layer_records(conn, data)
        log_history(conn, 'import_records', data)
    return status(conn)


def validate(conn, work, require_coverage=False, mode=None, force_source_hash=False, *, _include_review=True):
    contract_errors = record_contract_errors(conn)
    errors, warnings = list(contract_errors), []
    def err(code, ref, message):
        errors.append({'code': code, 'reference': ref, 'message': message})
    source_verification = verify_source(conn, force_source_hash)
    if not source_verification['valid']:
        err(source_verification['code'], 'source', source_verification['message'])
    assets = {r['id']: dict(r) for r in conn.execute('SELECT * FROM assets')}
    for ident, asset in assets.items():
        try:
            path = asset_path(work, asset['path'])
            if not path.is_file():
                err('missing_asset', ident, asset['path'])
            elif sha256(path) != asset['sha256']:
                err('asset_hash_mismatch', ident, asset['path'])
        except ValueError as exc:
            err('unsafe_asset_path', ident, str(exc))
        if asset['parent_id'] and (asset['parent_id'] not in assets or
                assets[asset['parent_id']]['frame_no'] != asset['frame_no']):
            err('bad_crop_parent', ident, 'Crop must retain parent source frame identity.')
    seen_assets = set()
    sheets = {r['id']: json.loads(r['payload']) for r in conn.execute('SELECT * FROM sheets')}
    sheet_valid = {}
    for view in conn.execute('SELECT * FROM views'):
        asset = assets.get(view['asset_id'])
        if not asset or asset['frame_no'] != view['frame_no'] or asset['sha256'] != view['asset_sha256']:
            err('bad_view_reference', view['id'], 'Asset/frame/hash mismatch')
        elif not view['trace_ref'].strip() or not view['observation'].strip():
            err('missing_view_trace', view['id'], 'Missing tool call or observation')
        else:
            seen_assets.add(view['asset_id'])
        if view['presentation'] == 'overview':
            sheet = sheets.get(view['sheet_id'])
            if sheet and sheet['id'] not in sheet_valid:
                try:
                    path = asset_path(work,sheet['path'])
                    sheet_valid[sheet['id']] = path.is_file() and sha256(path)==sheet['sha256']
                except ValueError:
                    sheet_valid[sheet['id']] = False
            if not sheet or not sheet_valid.get(sheet['id']) or not any(
                    m['asset_id']==view['asset_id'] and m['source_sha256']==view['asset_sha256'] for m in sheet.get('members',[])):
                err('bad_sheet_view',view['id'],'Overview sheet or original member hash is missing/changed.')
    for row in conn.execute('SELECT * FROM steps'):
        try:
            step = json.loads(row['payload'])
        except (ValueError, TypeError):
            continue
        if check_step(step):
            continue  # Already diagnosed; do not dereference malformed legacy data.
        for n in [step.get('start_frame'), step.get('end_frame')]:
            if conn.execute('SELECT 1 FROM frames WHERE frame_no=?', (n,)).fetchone() is None:
                err('unknown_frame', row['id'], str(n))
        if not step.get('evidence'):
            err('missing_evidence', row['id'], 'No evidence for step; keep as an issue until evidence exists.')
        for ident in step.get('evidence', []):
            if ident not in assets:
                err('unknown_evidence', row['id'], ident)
            elif ident not in seen_assets:
                err('unreviewed_evidence', row['id'], ident)
    for row in conn.execute('SELECT * FROM issues'):
        try:
            issue = json.loads(row['payload'])
        except (ValueError, TypeError):
            continue
        if check_issue(issue):
            continue
        try:
            references = evidence_references(issue)
        except ValueError as exc:
            err('invalid_issue_evidence', row['id'], str(exc))
            continue
        for ident in references:
            if ident not in assets:
                err('unknown_evidence', row['id'], ident)
            elif ident not in seen_assets:
                err('unreviewed_evidence', row['id'], ident)
    s = status(conn, _record_errors=contract_errors)
    if not s['full_compute_complete']:
        warnings.append('全帧计算待完成；请查看 attempts 和后续范围。')
    if s['container_frame_count_mismatch']:
        warnings.append(f"container_frame_count_mismatch: 容器声明 {s['container_declared_frames']} 帧；"
                        f"完整索引包含 {s['video_total_frames']} 个可解码呈现帧。请核对源包、PTS 与日志。")
    if s['candidates_pending']:
        warnings.append(f"待查看候选源帧：{s['candidates_pending']}。")
    result = {'valid': not errors, 'errors': errors, 'warnings': warnings,
              'assurance': 'record_consistency_only', 'status': s,
              'record_contract_errors': contract_errors,
              'source_verification': source_verification}
    if _include_review or require_coverage:
        from vor_audit import audit_omissions
        audit = (record_contract_audit(result, mode or get_meta(conn, 'review_mode', 'layered'))
                 if contract_errors else audit_omissions(conn, work, base_validation=result, mode=mode))
        result['review_complete'] = bool(result['valid'] and s['full_compute_complete']
                                         and s['selected_candidates_review_complete_recorded']
                                         and audit['review_gate_passed_recorded'])
        if require_coverage:
            result['coverage_audit'] = audit
            result['coverage_errors'] = []
        if require_coverage and not result['review_complete']:
            result['coverage_errors'].append({'code': 'omission_gate_incomplete', 'reference': 'coverage_audit',
                                              'message': '请完成候选查看、状态衔接及当前内容的复核。'})
    return result


def export_records(conn, work, force_source_hash=False):
    from vor_audit import audit_omissions
    from vor_export import publish_generation, require_no_pending_export
    from uuid import uuid4
    work = Path(work).resolve()
    require_no_pending_export(work)
    contract_errors = record_contract_errors(conn)
    if contract_errors:
        raise ValueError('Cannot export invalid records: ' + '; '.join(e['message'] for e in contract_errors))
    generation = uuid4().hex
    report = {'schema_version': SCHEMA_VERSION,
              'export_generation': generation,
              'source': get_meta(conn, 'source'), 'media': get_meta(conn, 'media'),
              'scan_config': get_meta(conn, 'scan_config'), 'selection_config': get_meta(conn, 'selection_config'),
              'status': status(conn), 'validation': validate(conn, work, force_source_hash=force_source_hash,
                                                            _include_review=False)}
    report['coverage_audit'] = audit_omissions(conn, work, base_validation=report['validation'])
    s = report['status']
    report['validation']['review_complete'] = bool(report['validation']['valid'] and s['full_compute_complete']
        and s['selected_candidates_review_complete_recorded'] and report['coverage_audit']['review_gate_passed_recorded'])
    for table in ['candidates', 'assets', 'views', 'steps', 'issues', 'coverage', 'omission_reviews', 'history',
                  'segments', 'intervals', 'interval_checks', 'layer_reviews', 'sheets', 'language_sources']:
        report[table] = [dict(r) for r in conn.execute(f'SELECT * FROM {table}')]
        for row in report[table]:
            for key in ['payload', 'reasons', 'represented_requests', 'crop']:
                if key in row and row[key] is not None:
                    row[key] = json.loads(row[key])
    from functools import lru_cache
    from vor_report import render_report
    @lru_cache(maxsize=4096)
    def frame_details(frame_no):
        row = conn.execute('SELECT frame_no,pts_time,best_effort_time,time_s,time_source '
                           'FROM frames WHERE frame_no=?', (frame_no,)).fetchone()
        return dict(row) if row else None
    def populate(stage):
        # A renderer exception occurs before any previously delivered file changes.
        markdown = render_report(report, work, frame_details)
        markdown += f'\n<!-- export_generation: {generation}; verify export-manifest.json and absence of export.pending.json -->\n'
        (stage / 'report.md').write_text(markdown, encoding='utf-8')
        (stage / 'review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        audit_file = dict(report['coverage_audit'], export_generation=generation)
        (stage / 'omission-audit.json').write_text(json.dumps(audit_file, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        with (stage / 'frames.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
            for row in conn.execute('SELECT * FROM frames ORDER BY frame_no'):
                entry = dict(row)
                if entry['tiles']:
                    entry['tiles'] = json.loads(entry['tiles'])
                stream.write(dump(entry) + '\n')
    publication = publish_generation(work, generation, populate)
    audit = report['coverage_audit']
    return {'review_json': str(work / 'review.json'), 'frames_jsonl': str(work / 'frames.jsonl'),
            'report': str(work / 'report.md'), 'omission_audit': str(work / 'omission-audit.json'),
            'validation_passed': report['validation']['valid'],
            'review_complete': report['validation']['review_complete'],
            'omission_gate_passed_recorded': audit['review_gate_passed_recorded'], **publication}


def atomic_text(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(value, encoding='utf-8')
    temp.replace(path)
