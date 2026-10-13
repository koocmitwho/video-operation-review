"""Immutable, portable supplementary evidence; never primary-video coverage.

An explicit import reads one authorized export directory. Later validation reads
only its in-work snapshot. Recorded views are attributed observations, not proof
that the depicted operation succeeded or that a tool really displayed an image.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import sqlite3
import stat
import tempfile

from vor_export import DELIVERY_FILES, MANIFEST, PENDING
from vor_store import dump, get_meta, log_history, now, set_meta, sha256


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _identifier(value):
    if (not isinstance(value, str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value)
            or re.fullmatch('CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]', value, re.IGNORECASE)):
        raise ValueError('Supplement ID must be a safe non-device directory name, 1..64 ASCII characters.')
    return value


def _no_links(path):
    for item in (path, *path.parents):
        try:
            details = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(details.st_mode) or getattr(details, 'st_file_attributes', 0) & 1024:
            raise ValueError(f'Supplement path cannot contain a symlink or junction: {item}')


def _root(path):
    path = Path(path).absolute()
    _no_links(path)
    return path.resolve()


def _relative(root, value):
    if not _text(value) or ':' in value or PureWindowsPath(value).drive:
        raise ValueError('Supplement file path must be relative.')
    parts = value.replace('\\', '/').split('/')
    if PurePosixPath(value.replace('\\', '/')).is_absolute() or any(
            p in ('', '.', '..') or p != p.rstrip(' .') or p != p.lstrip(' ') for p in parts):
        raise ValueError('Supplement file path must be relative and cannot escape its directory.')
    root = _root(root)
    path = root.joinpath(*parts)
    _no_links(path)
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError('Supplement file path escapes its directory.')
    return resolved


def _json(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Supplement JSON must be an object: {path.name}')
    return value


def _match(path, expected):
    if not _digest(expected) or not path.is_file() or sha256(path) != expected:
        raise ValueError(f'Missing or changed snapshot file hash: {path.name}')


def _view_matches(view, asset):
    return (isinstance(view, dict) and view.get('asset_id') == asset['id']
            and type(view.get('frame_no')) is int and view['frame_no'] == asset['frame_no']
            and view.get('asset_sha256') == asset['sha256'] and view.get('presentation', 'native') == 'native'
            and view.get('tool') in ('view_image', 'read_image', 'image_tool', 'visible_attachment')
            and all(_text(view.get(key)) for key in ('actor', 'trace_ref', 'observation', 'created')))


def _source_export(root, asset_ids):
    if _relative(root, PENDING).exists():
        raise ValueError('Source export is incomplete: export.pending.json exists.')
    manifest_bytes = _relative(root, MANIFEST).read_bytes()
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes)
    if (not isinstance(manifest, dict) or manifest.get('state') != 'complete' or not _text(manifest.get('generation'))
            or not isinstance(manifest.get('files'), dict) or set(manifest['files']) != set(DELIVERY_FILES)):
        raise ValueError('Source export requires a complete manifest of the fixed delivery files.')
    for name in DELIVERY_FILES:
        info = manifest['files'][name]
        if not isinstance(info, dict):
            raise ValueError('Invalid source manifest file entry.')
        path = _relative(root, name)
        _match(path, info.get('sha256'))
        if type(info.get('size')) is not int or info['size'] != path.stat().st_size:
            raise ValueError('Source manifest file size changed.')
    report = _json(_relative(root, 'review.json'))
    if report.get('export_generation') != manifest['generation']:
        raise ValueError('Source review and manifest export generation differ.')
    source = report.get('source')
    if not isinstance(source, dict) or not _digest(source.get('sha256')):
        raise ValueError('Source review must retain its video SHA-256 identity.')
    validation = report.get('validation', {})
    verification = validation.get('source_verification', {}) if isinstance(validation, dict) else {}
    if (not isinstance(validation, dict) or not isinstance(verification, dict)
            or validation.get('valid') is not True or verification.get('valid') is not True
            or verification.get('sha256') != source['sha256']
            or verification.get('expected_sha256') != source['sha256']):
        raise ValueError('Source export records invalid source or evidence integrity; repair and export again.')
    assets, views = report.get('assets'), report.get('views')
    if not isinstance(assets, list) or not isinstance(views, list):
        raise ValueError('Source assets and native view records are required.')
    selected = []
    for ident in asset_ids:
        matches = [asset for asset in assets if isinstance(asset, dict) and asset.get('id') == ident]
        if len(matches) != 1:
            raise ValueError(f'Unknown or duplicate source asset ID: {ident}')
        asset = matches[0]
        if (asset.get('kind') != 'full' or type(asset.get('frame_no')) is not int or asset['frame_no'] < 0
                or asset.get('parent_id') is not None or not _digest(asset.get('sha256'))):
            raise ValueError('Supplement import requires an original full image with frame/hash identity.')
        path = _relative(root, asset.get('path'))
        _match(path, asset['sha256'])
        if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'):
            raise ValueError('Source asset must be an image file.')
        source_views = [view for view in views if _view_matches(view, asset)]
        if not source_views:
            raise ValueError(f'Source asset requires a matching native view: {ident}')
        selected.append(dict(asset=asset, source_views=source_views, source_path=path))
    frames = {}
    wanted = {item['asset']['frame_no'] for item in selected}
    with _relative(root, 'frames.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            frame = json.loads(line)
            if isinstance(frame, dict) and type(frame.get('frame_no')) is int and frame['frame_no'] in wanted:
                if frame['frame_no'] in frames:
                    raise ValueError('Duplicate source frame identity in export.')
                frames[frame['frame_no']] = frame
    if set(frames) != wanted:
        raise ValueError('Source asset frame is absent from the exported frame ledger.')
    for item in selected:
        item['source_frame'] = frames[item['asset']['frame_no']]
    _match(_relative(root, 'frames.jsonl'), manifest['files']['frames.jsonl']['sha256'])
    _match(_relative(root, MANIFEST), manifest_digest)
    return report, manifest, selected, manifest_digest


def _entries(conn):
    saved = get_meta(conn, 'supplements', [])
    if not isinstance(saved, list) or any(not isinstance(entry, dict) for entry in saved):
        raise ValueError('Stored supplements metadata is invalid.')
    ids = [entry.get('id') for entry in saved]
    for ident in ids:
        _identifier(ident)
    if len(set(ident.casefold() for ident in ids)) != len(ids):
        raise ValueError('Duplicate stored supplement ID.')
    return saved


def _save(conn, entries, kind, receipt):
    set_meta(conn, 'supplements', entries)
    log_history(conn, kind, receipt)


def import_supplement(conn, work, source_review, ident, asset_ids, actor, note):
    """Copy an explicitly chosen export; imported source views are not local views."""
    ident = _identifier(ident)
    if not all(_text(value) for value in (actor, note)):
        raise ValueError('Supplement importer and note are required.')
    if (not isinstance(asset_ids, list) or not asset_ids or not all(_text(value) for value in asset_ids)
            or len(set(asset_ids)) != len(asset_ids)):
        raise ValueError('Distinct nonempty source asset IDs are required.')
    work, source_review = _root(work), _root(source_review)
    if work == source_review:
        raise ValueError('A supplement must come from an independent review, not self-reference.')
    saved = _entries(conn)
    if ident.casefold() in {entry['id'].casefold() for entry in saved}:
        raise ValueError('Supplement ID already exists; snapshots cannot be replaced.')
    report, source_manifest, selected, manifest_digest = _source_export(source_review, asset_ids)
    if report['source']['sha256'] == (get_meta(conn, 'source') or {}).get('sha256'):
        raise ValueError('Supplement source must be independent of the primary video.')
    storage = _relative(work, 'supplements')
    storage.mkdir(exist_ok=True)
    destination = _relative(storage, ident)
    if destination.exists():
        raise ValueError('Supplement destination already exists; preserve it and choose another ID.')
    stage = Path(tempfile.mkdtemp(prefix='.supplement-', dir=storage))
    created_destination = False
    committed = False
    try:
        files = {}
        for source_name, name, digest in (
                ('review.json', 'source-review.json', source_manifest['files']['review.json']['sha256']),
                (MANIFEST, 'source-export-manifest.json', manifest_digest)):
            shutil.copyfile(_relative(source_review, source_name), stage / name)
            _match(stage / name, digest)
            files[name] = digest
        copied = []
        for index, item in enumerate(selected):
            asset = item['asset']
            name = f'asset-{index + 1:04d}{item["source_path"].suffix.lower()}'
            shutil.copyfile(item['source_path'], stage / name)
            _match(stage / name, asset['sha256'])
            files[name] = asset['sha256']
            copied.append(dict(id=asset['id'], frame_no=asset['frame_no'], kind='full', sha256=asset['sha256'],
                               path=name, source_asset=asset, source_frame=item['source_frame'],
                               source_views=item['source_views']))
        # An export may have been replaced between validation and copying.
        _match(_relative(source_review, MANIFEST), manifest_digest)
        if _relative(source_review, PENDING).exists():
            raise ValueError('Source export became pending during supplement import.')
        package = dict(version=1, id=ident, source=report['source'],
                       source_export_generation=source_manifest['generation'], archive_non_live=True,
                       imported_by=actor, import_note=note, imported_at=now(), files=files, assets=copied,
                       assurance='archived_export_integrity_and_attributed_views_only')
        (stage / 'package.json').write_text(dump(package), encoding='utf-8')
        entry = dict(id=ident, manifest=dict(path=f'supplements/{ident}/package.json',
                                            sha256=sha256(stage / 'package.json')), views=[])
        with conn:
            if not conn.in_transaction:
                conn.execute('BEGIN IMMEDIATE')
            if _entries(conn) != saved:
                raise ValueError('Supplement metadata changed concurrently; retry without replacing its history.')
            # mkdir is exclusive on all supported hosts; do not rename over any existing directory.
            destination.mkdir()
            created_destination = True
            for child in stage.iterdir():
                child.replace(destination / child.name)
            _save(conn, [*saved, entry], 'import_supplement', dict(id=ident, manifest=entry['manifest']))
        committed = True
        return next(item for item in supplement_status(conn, work) if item['id'] == ident)
    finally:
        remove_destination = created_destination and not committed
        if remove_destination:
            try:
                # A commit can finish just before Python delivers an interrupt.
                # Never remove files that the durable ledger already registered.
                remove_destination = not any(row == entry for row in _entries(conn))
            except (sqlite3.Error, ValueError, TypeError):
                remove_destination = False  # Keep recovery data when commit state is uncertain.
        for owned in ([destination] if remove_destination else []) + [stage]:
            # Only these two newly created directories belong to this call.
            checked = _relative(storage, owned.name)
            if checked.exists():
                shutil.rmtree(checked)


def _snapshot(work, entry):
    ident = _identifier(entry.get('id'))
    manifest = entry.get('manifest')
    if not isinstance(manifest, dict) or manifest.get('path') != f'supplements/{ident}/package.json':
        raise ValueError('Supplement package must stay inside its own named directory.')
    path = _relative(work, manifest['path'])
    _match(path, manifest.get('sha256'))
    package = _json(path)
    if package.get('id') != ident or package.get('archive_non_live') is not True:
        raise ValueError('Supplement package identity differs from its registered snapshot.')
    files = package.get('files')
    if not isinstance(files, dict):
        raise ValueError('Supplement snapshot files are invalid.')
    for name, digest in files.items():
        _match(_relative(path.parent, name), digest)
    report = _json(_relative(path.parent, 'source-review.json'))
    source_manifest = _json(_relative(path.parent, 'source-export-manifest.json'))
    if (report.get('source') != package.get('source') or source_manifest.get('state') != 'complete'
            or report.get('export_generation') != package.get('source_export_generation')
            or source_manifest.get('generation') != package.get('source_export_generation')
            or source_manifest['files']['review.json']['sha256'] != files.get('source-review.json')):
        raise ValueError('Supplement source identity or export generation differs from its snapshot.')
    return package, path.parent


def supplement_status(conn, work):
    """Read only local archive files; original source directories are never followed."""
    try:
        entries = _entries(conn)
    except (ValueError, TypeError) as exc:
        return [dict(id=None, valid=False, assets=[], archive_non_live=True,
                     errors=[dict(code='invalid_supplement', reference='supplements', message=str(exc))])]
    result = []
    for entry in entries:
        item = dict(id=entry['id'], valid=False, assets=[], archive_non_live=True, errors=[])
        try:
            package, folder = _snapshot(work, entry)
            item.update({key: package[key] for key in ('source', 'source_export_generation', 'imported_by',
                                                     'import_note', 'imported_at', 'assurance')})
            if not isinstance(entry.get('views'), list):
                raise ValueError('Supplement local view records must be an array.')
            for asset in package['assets']:
                local_views = [view for view in entry['views'] if _view_matches(view, asset)
                               and view.get('package_sha256') == entry['manifest']['sha256']]
                item['assets'].append(dict(asset, relative_path=(folder / asset['path']).relative_to(_root(work)).as_posix(),
                                           view_records=local_views, viewed_recorded=bool(local_views)))
            known = {asset['id']: asset for asset in package['assets']}
            if any(not isinstance(view, dict) or view.get('asset_id') not in known
                   or not _view_matches(view, known[view['asset_id']])
                   or view.get('package_sha256') != entry['manifest']['sha256'] for view in entry['views']):
                raise ValueError('Supplement local view identity or package hash differs.')
            item['valid'] = True
        except (OSError, ValueError, TypeError, KeyError) as exc:
            item['errors'].append(dict(code='invalid_supplement', reference=entry['id'], message=str(exc)))
        result.append(item)
    return result


def record_supplement_view(conn, work, ident, asset_id, actor, tool, trace, observation):
    """Record the caller's actual local image display, separately from imported views."""
    if tool not in ('view_image', 'read_image', 'image_tool', 'visible_attachment') or not all(
            _text(value) for value in (actor, trace, observation)):
        raise ValueError('An actual image tool, actor, trace and observation are required.')
    if (trace.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'))
            or trace == asset_id or not any(marker in trace for marker in ('://', '#', ':'))):
        raise ValueError('Record an actual image tool-call or message reference, not an image filename.')
    saved = _entries(conn)
    snapshot = next((item for item in supplement_status(conn, work) if item['id'] == ident), None)
    if not snapshot or not snapshot['valid']:
        raise ValueError('Unknown or invalid supplementary snapshot.')
    asset = next((asset for asset in snapshot['assets'] if asset['id'] == asset_id), None)
    if not asset:
        raise ValueError('Unknown supplementary asset ID.')
    previous = dump(saved)
    entry = next(entry for entry in saved if entry['id'] == ident)
    view = dict(asset_id=asset_id, frame_no=asset['frame_no'], asset_sha256=asset['sha256'], actor=actor,
                tool=tool, trace_ref=trace, observation=observation, created=now(), presentation='native',
                package_sha256=entry['manifest']['sha256'])
    entry['views'].append(view)
    with conn:
        if not conn.in_transaction:
            conn.execute('BEGIN IMMEDIATE')
        if dump(_entries(conn)) != previous:
            raise ValueError('Supplement metadata changed concurrently; retry without replacing its history.')
        _save(conn, saved, 'supplement_view', dict(supplement_id=ident, view=view))
    return next(item for item in supplement_status(conn, work) if item['id'] == ident)


def supplement_reference_errors(conn, work, refs, reviewer=None):
    """Diagnose explicit followup references; never resolve an original issue."""
    errors = []
    def error(code, reference, message):
        errors.append(dict(code=code, reference=reference, message=message))
    if not isinstance(refs, list) or not refs:
        return [dict(code='invalid_supplement_reference', reference='supplement_refs',
                     message='Nonempty explicit supplementary references required.')]
    snapshots = {item['id']: item for item in supplement_status(conn, work)}
    for ref in refs:
        if not isinstance(ref, dict) or not all(_text(ref.get(k)) for k in ('supplement_id', 'asset_id')):
            error('invalid_supplement_reference', 'supplement_refs', 'Supplement and asset IDs required.')
            continue
        snapshot = snapshots.get(ref['supplement_id'])
        if not snapshot:
            error('unknown_supplement', ref['supplement_id'], 'Supplement snapshot is not imported.')
        elif not snapshot['valid']:
            errors.extend(snapshot['errors'])
        else:
            asset = next((asset for asset in snapshot['assets'] if asset['id'] == ref['asset_id']), None)
            if not asset:
                error('unknown_supplement_evidence', ref['asset_id'], 'Asset is absent from this supplement.')
            elif not any(reviewer is None or view['actor'] == reviewer for view in asset['view_records']):
                error('unreviewed_supplement_evidence', ref['asset_id'],
                      'The followup reviewer must record an actual local native image view.')
    return errors
