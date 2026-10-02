"""Publish a complete export generation, retaining recovery data on uncertain failure."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile


DELIVERY_FILES = ('review.json', 'omission-audit.json', 'frames.jsonl', 'report.md')
MANIFEST = 'export-manifest.json'
PENDING = 'export.pending.json'


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def require_no_pending_export(work):
    if (Path(work) / PENDING).exists():
        raise ValueError(f'{PENDING} exists: export is incomplete. Preserve the staging/previous files; '
                         'restore or inspect that generation before exporting again.')


def publish_generation(work, generation, populate):
    """Render everything before publishing; a pending receipt fences interrupted groups.

    The four legacy filenames remain available. Their replacements are not a filesystem
    transaction: consumers must reject a pending receipt and verify the final manifest.
    Ordinary exceptions roll back; crash/power-loss recovery remains explicit.
    """
    work = Path(work).resolve()
    require_no_pending_export(work)
    stage = Path(tempfile.mkdtemp(prefix='.export-', dir=work))
    pending_path = work / PENDING
    pending_owned = False
    replaced = []
    previous = {}
    retain_stage = False
    receipt = dict(version=1, state='pending', generation=generation, staging_directory=stage.name)
    try:
        populate(stage)
        manifest = dict(version=1, state='complete', generation=generation,
                        files={name: dict(sha256=_hash(stage / name), size=(stage / name).stat().st_size)
                               for name in DELIVERY_FILES})
        (stage / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        # Exclusive creation also prevents two publishers from replacing the same files.
        with pending_path.open('x', encoding='utf-8') as stream:
            pending_owned = True
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
        backup = stage / 'previous'
        backup.mkdir()
        for name in (*DELIVERY_FILES, MANIFEST):
            target = work / name
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise ValueError(f'Export target must be a regular file: {name}')
            previous[name] = target.exists()
            if previous[name]:
                shutil.copyfile(target, backup / name)
        receipt['previous_files'] = {name: dict(present=present, sha256=_hash(backup / name) if present else None)
                                     for name, present in previous.items()}
        _json(pending_path, receipt)
        for name in (*DELIVERY_FILES, MANIFEST):
            # The OS rename may succeed just before an interrupt reaches Python.
            # Include its target in recovery BEFORE invoking it, not after it returns.
            replaced.append(name)
            (stage / name).replace(work / name)
        pending_path.unlink()
        pending_owned = False
        return dict(generation=generation, export_manifest=str(work / MANIFEST))
    except BaseException as exc:
        if pending_owned:
            retain_stage = True  # A second interruption must not discard recovery files.
            if not pending_path.exists():
                # This also covers an interrupt immediately after removing the final marker.
                _json(pending_path, receipt)
            rollback_errors = []
            for name in reversed(replaced):
                try:
                    if previous[name]:
                        # Copy so a failed replacement still leaves the backup intact.
                        restore = stage / (name + '.restore')
                        shutil.copyfile(stage / 'previous' / name, restore)
                        restore.replace(work / name)
                    else:
                        (work / name).unlink()
                except BaseException as failure:
                    rollback_errors.append(f'{name}: {failure}')
            if rollback_errors:
                retain_stage = True
                receipt.update(state='recovery_required', error=str(exc), rollback_errors=rollback_errors)
                try:
                    _json(pending_path, receipt)
                except OSError:
                    pass  # The preexisting pending marker must remain a fail-closed signal.
            else:
                try:
                    pending_path.unlink()
                    retain_stage = False
                except OSError:
                    retain_stage = True
            if retain_stage:
                raise OSError(f'Export failed; recovery required. Keep {pending_path} and {stage}. {exc}') from exc
        raise
    finally:
        if not retain_stage:
            # Only delete the private directory created by this call, never a user input.
            if stage.parent.resolve() != work or not stage.name.startswith('.export-'):
                raise ValueError('Unsafe export staging directory.')
            shutil.rmtree(stage)
