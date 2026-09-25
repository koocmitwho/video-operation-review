"""Read-only dependency checks that work without NumPy or Pillow installed."""
import importlib
from pathlib import Path
import re
import shutil
import subprocess
import sys


def module_check(name, minimum=None):
    try:
        module = importlib.import_module(name)
        version = getattr(module, '__version__', 'unknown')
        if minimum is not None:
            parts = re.match(r'^(\d+)\.(\d+)', version)
            if not parts or tuple(map(int, parts.groups())) < minimum:
                return {'ok': False, 'version': version, 'error': 'Requires Pillow >= 10.1.'}
        return {'ok': True, 'version': version}
    except Exception as exc:
        return {'ok': False, 'error': str(exc), 'type': type(exc).__name__}


def executable_check(command, name):
    result = {'ok': False, 'command': command}
    try:
        path = shutil.which(command)
        if path is None:
            raise FileNotFoundError(f'{name} was not found; supply an executable path or update PATH.')
        result['path'] = str(Path(path).resolve())
        options = {'capture_output': True, 'text': True, 'encoding': 'utf-8',
                   'errors': 'replace', 'timeout': 5,
                   'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}
        process = subprocess.run([path, '-version'], **options)
        lines = process.stdout.splitlines()
        if process.returncode or not lines or not lines[0].startswith(f'{name} version '):
            raise RuntimeError(f'The executable did not return a valid {name} version (exit {process.returncode}).')
        result['version'] = lines[0]
        if name == 'ffmpeg':
            help_result = subprocess.run([path, '-h', 'full'], **options)
            supported = help_result.returncode == 0 and '-fps_mode' in help_result.stdout
            result['fps_mode_passthrough'] = supported
            if not supported:
                raise RuntimeError('FFmpeg must support -fps_mode passthrough.')
        result['ok'] = True
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result.update(error=str(exc), type=type(exc).__name__)
    return result


def diagnose(ffmpeg='ffmpeg', ffprobe='ffprobe'):
    """Report local processing readiness; host vision is outside this process."""
    checks = {
        'python': {'ok': sys.version_info >= (3, 10), 'version': sys.version.split()[0],
                   'executable': sys.executable},
        'numpy': module_check('numpy'),
        'pillow': module_check('PIL', minimum=(10, 1)),
        'ffmpeg': executable_check(ffmpeg, 'ffmpeg'),
        'ffprobe': executable_check(ffprobe, 'ffprobe'),
    }
    return {
        'ready': all(item['ok'] for item in checks.values()),
        'checks': checks,
        'visual_review': {
            'status': 'unverified',
            'reason': 'The host must actually display evidence with an image-capable model before recording a view.',
        },
        'hint': 'Use this Python executable with -m pip install -r <skill-root>/requirements.txt for missing packages. '
                'For FFmpeg use --ffmpeg/--ffprobe or VOR_FFMPEG/VOR_FFPROBE. No software or config was changed.',
    }
