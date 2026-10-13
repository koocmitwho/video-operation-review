"""Persist task context and content-bound, attributed reproduction observations."""
import hashlib
import json
from pathlib import Path
import re


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _ids(value):
    return isinstance(value, list) and all(_text(v) for v in value) and len(set(value)) == len(value)


def _plain(value):
    """Summary values are plain text; each Markdown renderer escapes them once."""
    return '未知' if value is None else str(value)


def content_snapshot(conn):
    from vor_store import get_meta
    context = get_meta(conn, 'delivery_context', {})
    state = {'source': (get_meta(conn, 'source') or {}).get('sha256'),
             'context': {k: context.get(k) for k in ('question', 'scope', 'used_language_source_ids')}}
    for table in ('steps', 'issues', 'intervals', 'step_retirements', 'language_sources'):
        state[table] = [dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY id')]
    supplements = get_meta(conn, 'supplements', [])
    if supplements:
        state['supplements'] = supplements
    return hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def check_context(conn, context):
    if not isinstance(context, dict):
        raise ValueError('delivery_context: must be an object.')
    for key in ('question', 'scope', 'next_action'):
        if not _text(context.get(key)):
            raise ValueError(f'delivery_context.{key}: must be a nonempty string.')
    ids = context.get('used_language_source_ids')
    available = {r[0] for r in conn.execute('SELECT id FROM language_sources')}
    if not _ids(ids) or set(ids) - available:
        raise ValueError('delivery_context.used_language_source_ids: distinct imported source IDs required.')


def _artifact_valid(conn, work, artifact):
    from vor_store import asset_path, sha256, get_meta
    from vor_export import DELIVERY_FILES, MANIFEST, PENDING
    if not isinstance(artifact, dict) or not _text(artifact.get('path')):
        return False
    if not isinstance(artifact.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', artifact['sha256']):
        return False
    try:
        path = asset_path(work, artifact['path'])
        reserved = {(Path(work) / name).resolve() for name in
                    (*DELIVERY_FILES, MANIFEST, PENDING, 'review.sqlite3', 'review.sqlite3-wal', 'review.sqlite3-shm')}
        reserved.update(asset_path(work, row[0]) for row in conn.execute('SELECT path FROM assets'))
        source = get_meta(conn, 'source') or {}
        if source.get('path'):
            reserved.add(Path(source['path']).resolve())
        if path in reserved or any(part.startswith('.export-') for part in path.relative_to(Path(work).resolve()).parts):
            return False
        return path.is_file() and sha256(path) == artifact['sha256']
    except (ValueError, OSError):
        return False


def import_delivery(conn, data, work):
    """Called inside the existing import transaction; do not commit independently."""
    from vor_store import get_meta, set_meta, now
    if 'delivery_context' in data:
        check_context(conn, data['delivery_context'])
        set_meta(conn, 'delivery_context', data['delivery_context'])
    if 'reproduction_checks' not in data:
        return
    entries = data['reproduction_checks']
    if not isinstance(entries, list):
        raise ValueError('reproduction_checks: must be an array.')
    saved = get_meta(conn, 'reproduction_checks', [])
    seen = {entry['id'] for entry in saved}
    step_ids = {row[0] for row in conn.execute('SELECT id FROM steps')}
    snapshot = content_snapshot(conn)
    for index, entry in enumerate(entries):
        field = f'reproduction_checks[{index}]'
        if not isinstance(entry, dict):
            raise ValueError(f'{field}: must be an object.')
        for key in ('id', 'reviewer', 'scope', 'environment', 'result', 'content_snapshot'):
            if not _text(entry.get(key)):
                raise ValueError(f'{field}.{key}: must be a nonempty string.')
        if entry['id'] in seen:
            raise ValueError(f'{field}.id: already recorded; preserve history and use a new ID.')
        if entry.get('outcome') not in ('passed', 'failed', 'partial'):
            raise ValueError(f'{field}.outcome: must be passed, failed or partial.')
        if not _ids(entry.get('step_ids')) or not entry['step_ids'] or set(entry['step_ids']) - step_ids:
            raise ValueError(f'{field}.step_ids: nonempty current step IDs required.')
        if entry['content_snapshot'] != snapshot:
            raise ValueError(f'{field}.content_snapshot: stale; inspect status and review the current delivery.')
        artifacts = entry.get('artifacts')
        if not isinstance(artifacts, list) or not artifacts or not all(_artifact_valid(conn, work, a) for a in artifacts):
            raise ValueError(f'{field}.artifacts: existing in-work files with matching SHA-256 required.')
        # Generated fields cannot be supplied as an authority by the caller.
        accepted = {k: entry[k] for k in ('id', 'reviewer', 'scope', 'environment', 'result',
                    'content_snapshot', 'outcome', 'step_ids', 'artifacts')}
        saved.append(dict(accepted, recorded_at=now()))
        seen.add(entry['id'])
    set_meta(conn, 'reproduction_checks', saved)


def attach_delivery(conn, report, work):
    from vor_store import get_meta
    context = get_meta(conn, 'delivery_context', {})
    snapshot = content_snapshot(conn)
    report['delivery_context'] = context
    report['delivery_snapshot'] = snapshot
    report['media_tracks'] = get_meta(conn, 'media_tracks')
    checks = []
    for item in get_meta(conn, 'reproduction_checks', []):
        freshness = ('evidence_changed' if not all(_artifact_valid(conn, work, a) for a in item['artifacts'])
                     else 'stale' if item['content_snapshot'] != snapshot
                     else 'record_invalid' if not report['validation']['valid'] else 'current')
        checks.append(dict(item, freshness=freshness))
    report['reproduction_checks'] = checks
    report['delivery_summary'] = summary_lines(report)


def narration_summary(report):
    tracks = report.get('media_tracks')
    audio = ('音轨未检查' if tracks is None else '有音轨' if tracks.get('audio') else '无音轨')
    languages = {r['id']: r for r in report.get('language_sources', [])}
    context = report.get('delivery_context') or {}
    used = context.get('used_language_source_ids', [])
    if used:
        descriptions = []
        for ident in used:
            row = languages.get(ident)
            source = (row or {}).get('payload', {}).get('source', {})
            kind = '外部转写' if source.get('kind') == 'asr_interchange' else '字幕'
            descriptions.append(f'{kind} {_plain(ident)}（{_plain(source.get("path", "来源待核对"))}）')
        return f'旁白与语言：{audio}；按审阅者记录已使用' + '、'.join(descriptions) + '；导入文本不表示实际听取音频。'
    if languages:
        return f'旁白与语言：{audio}；已导入 {len(languages)} 份文本，未声明使用；本报告不声称已利用旁白。'
    return f'旁白与语言：{audio}；' + ('旁白未转写，本次无已使用的语言来源。' if tracks and tracks.get('audio')
                                    else '无已使用的字幕或转写记录。')


def summary_lines(report):
    context = report.get('delivery_context') or {}
    lines = [f'本轮问题：{_plain(context.get("question", "未记录"))}。',
             f'本轮范围：{_plain(context.get("scope", "未记录；继续前先确认原问题"))}。', narration_summary(report)]
    checks = report.get('reproduction_checks', [])
    if not checks:
        lines.append('复现验收：未记录。审阅完成度与实际照做成功分别验收。')
    labels = {'current': '当前内容', 'stale': '已过期，需按当前内容重验',
              'evidence_changed': '证据文件缺失或变化，结果待核对', 'record_invalid': '审阅记录完整性待修复'}
    outcomes = {'passed': '通过', 'failed': '失败', 'partial': '部分完成'}
    for item in checks:
        lines.append(f'复现验收 {_plain(item["id"])}：{labels[item["freshness"]]}；'
                     f'记录结果：{outcomes[item["outcome"]]}；范围：{_plain(item["scope"])}；'
                     f'环境：{_plain(item["environment"])}；记录者：{_plain(item["reviewer"])}；{_plain(item["result"])}。')
    if checks:
        lines.append('以上为带来源的照做记录；审阅门禁、照做结果与真人验收分别解释。')
    return lines


def render_handoff(report, work):
    from vor_report import text, link
    work = Path(work).resolve()
    context = report.get('delivery_context') or {}
    source = report.get('source') or {}
    status = report['status']
    next_action = context.get('next_action', '本轮问题和下一步未记录；先核对现有报告与疑点并确认范围。')
    lines = ['# 继续审阅', '', f'审阅目录：{link(work.as_posix(), work.as_posix())}',
             f'素材：{link(source.get("path", "未知"), source.get("path", ""))}',
             f'源 SHA-256：{text(source.get("sha256"))}', '', '[报告入口](report.md) · [结构化记录](review.json)', '']
    lines.extend('- ' + text(line) for line in report['delivery_summary'])
    lines += ['', f'已计算帧：{status["computed_frames"]}；全帧计算完成：{text(status["full_compute_complete"])}。',
              f'待查看候选：{status["candidates_pending"]}；登记查看源帧：{status["recorded_visual_unique_frames"]}。',
              '未完成审阅范围及原始帧范围见 report.md 审计附录和 review.json；索引不等于看过画面。',
              '', '## 下一步', '', text(next_action), '', '## 继续回执', '',
              f'继续审阅 {text(source.get("path"))}，沿用 {text(work.as_posix())}。'
              f'本轮问题：{text(context.get("question", "待确认"))}；范围：{text(context.get("scope", "待确认"))}。'
              f'先检查源身份、活动写入者、已有 status / intervals / 疑点，再处理：{text(next_action)}。'
              '已完成的索引不重建；重新打开当前步骤关键证据后再判断。', '',
              f'<!-- export_generation: {report["export_generation"]}; verify export-manifest.json and absence of export.pending.json -->', '']
    return '\n'.join(lines)
