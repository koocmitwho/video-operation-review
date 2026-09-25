"""Durable review bookkeeping. Consistency checks are not proof of visual attention."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

SCHEMA_VERSION = 3


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


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


def status(conn):
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
    attempts = [dict(r) for r in conn.execute('SELECT * FROM attempts ORDER BY id')]
    open_issues = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM issues')
                   if json.loads(r[0]).get('status') != 'resolved']
    result = {
        'video_total_frames': total, 'container_declared_frames': get_meta(conn, 'declared_frames'),
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
        'visual_assurance': 'Attested records with tool references; actual image tool calls must be audited separately.',
        'candidate_pending_ranges': ranges(r[0] for r in conn.execute(
            'SELECT frame_no FROM candidates c WHERE NOT EXISTS '
            '(SELECT 1 FROM views v JOIN assets a ON a.id=v.asset_id '
            'WHERE v.frame_no=c.frame_no AND a.kind="full" AND v.presentation="native") ORDER BY frame_no')),
        'unresolved_issues': open_issues, 'attempts': attempts,
        'timestamp_anomalies': get_meta(conn, 'timestamp_anomalies', {}),
        'near_duplicate_merging': False,
        'risk': 'Change thresholds can miss small or low-contrast actions. Exact-run coverage is not per-frame visual review.'
    }
    from vor_layers import coverage_counts
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
        raise ValueError('Only actual image viewing qualifies; OCR, diff, export and file listing do not.')
    if not all(s.strip() for s in [actor, trace, observation]):
        raise ValueError('Actor, actual tool-call reference and visual observation are required.')
    asset, _ = require_asset(conn, work, asset_id)
    with conn:
        conn.execute('INSERT INTO views(asset_id,frame_no,actor,tool,trace_ref,observation,asset_sha256,created) '
                     'VALUES (?,?,?,?,?,?,?,?)',
                     (asset_id, asset['frame_no'], actor, tool, trace, observation, asset['sha256'], now()))
    return status(conn)


STEP_FIELDS = {'id': str, 'phase': str, 'start_frame': int, 'end_frame': int, 'software': str,
               'module': str, 'menu_path': list, 'selected_objects': list, 'final_parameters': dict,
               'confirmation_action': str, 'visible_result': str, 'input_files': list,
               'output_files': list, 'evidence': list, 'uncertainties': list, 'status': str}


def evidence_references(value):
    """Collect explicit evidence fields at every depth; reject malformed reference lists."""
    refs = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'evidence':
                if not isinstance(item, list) or not all(isinstance(ref, str) for ref in item):
                    raise ValueError('Every evidence field must be a list of asset IDs.')
                refs.update(item)
            else:
                refs.update(evidence_references(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(evidence_references(item))
    return refs


def check_step(step):
    errors = [f'{key} must be {typ.__name__}' for key, typ in STEP_FIELDS.items()
              if key not in step or type(step[key]) is not typ]
    if errors:
        return errors
    if not step['id'].strip() or step['start_frame'] < 0 or step['start_frame'] > step['end_frame']:
        errors.append('Invalid id or frame interval')
    if step['status'] not in {'confirmed', 'partial', 'unresolved'}:
        errors.append('status must be confirmed, partial or unresolved')
    if not all(isinstance(x, str) for x in step['evidence']):
        errors.append('Evidence must contain asset IDs')
    else:
        try:
            if evidence_references(step) - set(step['evidence']):
                errors.append('Nested evidence must also be listed in the step top-level evidence field.')
        except ValueError as exc:
            errors.append(str(exc))
    if step['status'] == 'confirmed' and step['uncertainties']:
        errors.append('A confirmed step cannot retain uncertainties; use partial')
    return errors


def import_records(conn, path):
    from vor_audit import check_aux_records
    from vor_layers import check_layer_records, import_layer_records
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('Records must be an object containing steps and/or issues arrays.')
    for key in ['steps', 'issues', 'coverage', 'omission_reviews']:
        if key in data and not isinstance(data[key], list):
            raise ValueError(f'{key} must be an array.')
    for step in data.get('steps', []):
        errors = check_step(step)
        if errors:
            raise ValueError('; '.join(errors))
    for issue in data.get('issues', []):
        if not isinstance(issue, dict) or not all(k in issue for k in ['id', 'question', 'status', 'attempts']):
            raise ValueError('Issues need id, question, status and attempts.')
        if issue['status'] not in {'open', 'blocked', 'resolved'} or not isinstance(issue['attempts'], list):
            raise ValueError('Invalid issue status or attempts.')
        evidence_references(issue)
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


def validate(conn, work, require_coverage=False, mode=None):
    errors, warnings = [], []
    def err(code, ref, message):
        errors.append({'code': code, 'reference': ref, 'message': message})
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
        step = json.loads(row['payload'])
        for message in check_step(step):
            err('invalid_step', row['id'], message)
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
        issue = json.loads(row['payload'])
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
    s = status(conn)
    if not s['full_compute_complete']:
        warnings.append('Full-frame computation is not complete/clean; inspect attempts and missing ranges.')
    if s['candidates_pending']:
        warnings.append(f"{s['candidates_pending']} candidate source frames have no view record.")
    warnings.append('Internal consistency only: self-reported tool references do not independently prove visual review.')
    result = {'valid': not errors, 'errors': errors, 'warnings': warnings,
              'assurance': 'record_consistency_only', 'status': s}
    if require_coverage:
        from vor_audit import audit_omissions
        audit = audit_omissions(conn, work, base_validation=result, mode=mode)
        result['coverage_audit'] = audit
        if not audit['review_gate_passed_recorded']:
            result['errors'].append({'code': 'omission_gate_incomplete', 'reference': 'coverage_audit',
                                     'message': 'State accounting, continuity or current independent review is incomplete.'})
            result['valid'] = False
    return result


def export_records(conn, work):
    from vor_audit import audit_omissions
    work = Path(work).resolve()
    report = {'schema_version': SCHEMA_VERSION,
              'source': get_meta(conn, 'source'), 'media': get_meta(conn, 'media'),
              'scan_config': get_meta(conn, 'scan_config'), 'selection_config': get_meta(conn, 'selection_config'),
              'status': status(conn), 'validation': validate(conn, work)}
    report['coverage_audit'] = audit_omissions(conn, work, base_validation=report['validation'])
    for table in ['candidates', 'assets', 'views', 'steps', 'issues', 'coverage', 'omission_reviews', 'history',
                  'segments', 'intervals', 'interval_checks', 'layer_reviews', 'sheets', 'language_sources']:
        report[table] = [dict(r) for r in conn.execute(f'SELECT * FROM {table}')]
        for row in report[table]:
            for key in ['payload', 'reasons', 'represented_requests', 'crop']:
                if key in row and row[key] is not None:
                    row[key] = json.loads(row[key])
    atomic_text(work / 'review.json', json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    atomic_text(work / 'omission-audit.json', json.dumps(report['coverage_audit'], ensure_ascii=False, indent=2, allow_nan=False))
    temp = work / 'frames.jsonl.tmp'
    with temp.open('w', encoding='utf-8', newline='\n') as f:
        for row in conn.execute('SELECT * FROM frames ORDER BY frame_no'):
            entry = dict(row)
            if entry['tiles']:
                entry['tiles'] = json.loads(entry['tiles'])
            f.write(dump(entry) + '\n')
    temp.replace(work / 'frames.jsonl')
    s = report['status']
    lines = ['# 软件操作录屏审阅', '', '此文档由已有记录生成；语义正确性和实际图片工具调用需要另行核实。', '',
             '| 统计 | 当前记录 |', '|---|---|',
             f"| 视频总帧数 | {s['video_total_frames']}（未知时为 null/None） |",
             f"| 程序计算检查 | {s['computed_frames']} |",
             f"| 粗审覆盖 / 精审覆盖（登记源帧范围长度） | {s['coarse_reviewed_frames_recorded']} / {s['fine_reviewed_frames_recorded']} |",
             f"| 已进行精审 / 已完成精审（区间帧数，非看图计数） | {s['fine_examined_frames_recorded']} / {s['fine_reviewed_frames_recorded']} |",
             f"| 候选操作单元（不是实际操作总数） | {s['candidate_operation_units']} |",
             f"| 概览粒度去重源帧 | {s['recorded_overview_unique_frames']} |",
             f"| 候选帧 / 已登记查看 / 待查看 | {s['candidate_frames']} / {s['candidates_reviewed_recorded']} / {s['candidates_pending']} |",
             f"| 模型视觉查看去重源帧（按查看登记，非独立证明） | {s['recorded_visual_unique_frames']} |",
             f"| 全帧计算完成 | {s['full_compute_complete']} |",
             f"| 选定候选审阅完成（登记口径） | {s['selected_candidates_review_complete_recorded']} |",
             '| 全部帧逐张视觉审阅完成（独立核实） | 未核实 |', '',
             f"未计算范围：{dump(s['unprocessed_ranges'])}；未索引尾部：{dump(s['unindexed_tail'])}。", '',
             f"尚无全图查看登记的源帧：{dump(s['source_frames_without_full_view_record_ranges'])}。精确重复段由代表图覆盖也不计为逐张查看。", '',
             '## 操作步骤', '']
    for item in report['steps']:
        step = item['payload']
        bounds = [conn.execute('SELECT time_s FROM frames WHERE frame_no=?', (step[k],)).fetchone()[0]
                  if conn.execute('SELECT 1 FROM frames WHERE frame_no=?', (step[k],)).fetchone() else None
                  for k in ['start_frame', 'end_frame']]
        lines.extend([f"### {step['id']} · {step['phase']} · {step['status']}", '',
                      f"原始时间 {bounds[0]}–{bounds[1]} s；源帧 {step['start_frame']}–{step['end_frame']}。", ''])
        for label, key in [('软件', 'software'), ('模块', 'module'), ('菜单入口', 'menu_path'),
                           ('选择对象', 'selected_objects'), ('最终参数', 'final_parameters'),
                           ('确认动作', 'confirmation_action'), ('可见结果', 'visible_result'),
                           ('输入文件', 'input_files'), ('输出文件', 'output_files'), ('不确定项', 'uncertainties')]:
            value = step[key]
            lines.append(f'- {label}：{dump(value) if isinstance(value, (dict, list)) else value}')
        lines.append('')
        for ident in step['evidence']:
            asset = next((a for a in report['assets'] if a['id'] == ident), None)
            if asset:
                lines.extend([f"![{ident}]({asset['path']})", ''])
    lines += ['## 待核对事项', '']
    for issue in s['unresolved_issues']:
        lines += [f"- {issue['id']}：{issue['question']}（{issue['status']}）"]
    audit = report['coverage_audit']
    if audit.get('mode') == 'layered':
        lines += ['', '## 分层覆盖', '',
                  f"尚未粗审范围：{dump(s['not_coarse_reviewed_ranges'])}；尚未进行精审：{dump(s['not_fine_examined_ranges'])}；尚未完成精审：{dump(s['not_fine_reviewed_ranges'])}。", '',
                  f"复核状态：{audit['omission_review']['status']}；记录层检查通过：{audit['review_gate_passed_recorded']}。", '',
                  '区间、原始帧/状态映射、合并理由、抽查与字幕线索保存在 review.json；均不自动增加实际看图数。', '']
        for item in report['intervals']:
            entry = item['payload']
            lines.append(f"- {entry['id']} 帧 {entry['start_frame']}–{entry['end_frame']}：{entry['phase']}；{entry['disposition']}；{entry['merge']}；精审 {entry['fine_status']}；{entry['reason']}")
    else:
        lines += ['', '## 操作遗漏检查', '',
              f"不同连续画面状态：{audit['coverage']['state_count']}；有依据的状态说明：{len(audit['coverage']['accounted_state_frames'])}。", '',
              f"可进入遗漏复核：{audit['records_ready_for_omission_review']}；复核状态：{audit['omission_review']['status']}。", '',
              f"记录层遗漏检查通过：{audit['review_gate_passed_recorded']}。程序不能据此证明操作语义完整。", '',
                  f"未说明状态的代表帧：{dump(audit['coverage']['unaccounted_state_frames'])}。", '']
    lines += [f"- {f['code']}：{f['message']}（建议复查帧 {dump(f['suggested_frames'])}）" for f in audit['findings']] or ['- 没有发现记录层缺口；仍须保留证据边界。']
    result = report['validation']
    lines += ['', '## 记录校验', '',
              f"记录一致性校验：{'通过' if result['valid'] else '未通过'}。此项不独立证明实际视觉查看或步骤语义正确。", '',
              '错误：', '']
    lines += [f"- {e['code']} · {e['reference']}：{e['message']}" for e in result['errors']] or ['- 无。']
    lines += ['', '警告：', '']
    lines += [f'- {warning}' for warning in result['warnings']] or ['- 无。']
    lines += ['', '差分可能漏掉操作。相同画面合并代表的帧没有逐张被视觉查看。生成图片、OCR、差分和文件列表均不增加查看计数。']
    atomic_text(work / 'report.md', '\n'.join(lines) + '\n')
    return {'review_json': str(work / 'review.json'), 'frames_jsonl': str(work / 'frames.jsonl'),
            'report': str(work / 'report.md'), 'omission_audit': str(work / 'omission-audit.json'),
            'validation_passed': report['validation']['valid'],
            'omission_gate_passed_recorded': audit['review_gate_passed_recorded']}


def atomic_text(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(value, encoding='utf-8')
    temp.replace(path)
