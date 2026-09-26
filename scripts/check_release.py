"""Compare a canonical skill tree with a release copy; never modifies either tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


IGNORED_DIRECTORIES = {'.git', '__pycache__', '.venv', 'venv', '.pytest_cache'}


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f'Not a directory: {root}')
    result = {}
    def enumeration_failed(error):
        raise error

    for directory, folders, files in os.walk(root, onerror=enumeration_failed):
        folders[:] = sorted(name for name in folders if name not in IGNORED_DIRECTORIES)
        for name in folders:
            path = Path(directory) / name
            attributes = getattr(path.lstat(), 'st_file_attributes', 0)
            if path.is_symlink() or attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
                raise ValueError(f'Release directory links are not supported: {path}')
        for name in sorted(files):
            path = Path(directory) / name
            if name == '.git' or path.suffix in {'.pyc', '.pyo'}:
                continue
            if not path.resolve().is_relative_to(root):
                raise ValueError(f'Release file resolves outside its tree: {path}')
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def compare(source, target):
    expected = inventory(source)
    for required in ('SKILL.md', 'scripts/review_video.py'):
        if required not in expected:
            raise ValueError(f'Canonical source is missing {required}.')
    actual = inventory(target)
    changed = sorted(name for name in expected.keys() & actual.keys()
                     if expected[name] != actual[name])
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    return dict(identical=not (changed or missing or extra),
                compared_files=len(expected.keys() & actual.keys()),
                changed=changed, missing_in_target=missing, extra_in_target=extra)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--target', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compare(args.source, args.target)
    except (OSError, ValueError) as exc:
        print(json.dumps(dict(identical=False, error=str(exc)), ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['identical'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
