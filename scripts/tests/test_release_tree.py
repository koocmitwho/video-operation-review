"""Release parity uses isolated trees, never writes a real publication checkout."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


CLI = Path(__file__).resolve().parents[1] / 'check_release.py'
sys.path.insert(0, str(CLI.parent))
import check_release


class ReleaseTreeContract(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='vor release 中文 ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'source'
        self.target = self.root / 'target'
        for directory in (self.source, self.target):
            self.put(directory, 'SKILL.md', 'skill\n')
            self.put(directory, 'scripts/review_video.py', 'print("fixture")\n')

    @staticmethod
    def put(root, relative, content):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def compare(self, expected):
        process = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(CLI),
                                  '--source', str(self.source), '--target', str(self.target)],
                                 capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(process.returncode, expected, process.stdout + process.stderr)
        self.assertTrue(process.stdout.lstrip().startswith('{'), process.stdout + process.stderr)
        return json.loads(process.stdout)

    def test_equal_trees_ignore_git_and_python_caches(self):
        self.put(self.target, '.git/config', 'private local metadata')
        self.put(self.source, 'scripts/__pycache__/generated.pyc', 'cache')
        result = self.compare(0)
        self.assertTrue(result['identical'])
        self.assertEqual(result['compared_files'], 2)

    def test_drift_reports_changes_missing_files_and_unmanaged_extras(self):
        self.put(self.source, 'references/中文.md', 'new reference')
        self.put(self.target, 'scripts/obsolete.py', 'old file')
        self.put(self.target, 'SKILL.md', 'stale skill')
        result = self.compare(1)
        self.assertFalse(result['identical'])
        self.assertEqual(result['changed'], ['SKILL.md'])
        self.assertEqual(result['missing_in_target'], ['references/中文.md'])
        self.assertEqual(result['extra_in_target'], ['scripts/obsolete.py'])

    def test_comparison_does_not_overwrite_conflicting_target(self):
        self.put(self.target, 'SKILL.md', 'unsaved local work')
        before = (self.target / 'SKILL.md').read_bytes()
        self.compare(1)
        self.assertEqual((self.target / 'SKILL.md').read_bytes(), before)
        self.assertEqual((self.source / 'SKILL.md').read_text(encoding='utf-8'), 'skill\n')

    def test_incomplete_project_is_not_an_equal_release(self):
        (self.target / 'SKILL.md').unlink()
        result = self.compare(1)
        self.assertFalse(result['identical'])
        self.assertEqual(result['missing_in_target'], ['SKILL.md'])

    def test_two_empty_folders_do_not_pass(self):
        self.source = self.root / 'empty-source'
        self.target = self.root / 'empty-target'
        self.source.mkdir()
        self.target.mkdir()
        result = self.compare(2)
        self.assertIn('SKILL.md', result['error'])

    def test_directory_enumeration_failure_never_reports_identical(self):
        self.put(self.target, 'unreadable/extra.py', 'unmanaged target content')
        self.assertFalse(check_release.compare(self.source, self.target)['identical'])
        # A deliberately noncanonical spelling exercises the same mismatch as
        # Windows TEMP paths using an 8.3 alias before inventory resolves them.
        denied = self.target / '..' / self.target.name / 'unreadable'
        original = os.scandir
        injected = []

        def unreadable(path):
            if Path(path).resolve() == denied.resolve():
                injected.append(path)
                raise PermissionError('Synthetic directory enumeration failure')
            return original(path)

        # Inject the filesystem failure, keeping real os.walk and inventory logic.
        with patch('os.scandir', side_effect=unreadable):
            for source in (self.source, self.target):
                with self.subTest(same_root=source == self.target):
                    before = len(injected)
                    with self.assertRaisesRegex(PermissionError, 'Synthetic directory enumeration failure'):
                        check_release.compare(source, self.target)
                    self.assertEqual(len(injected), before + 1, 'The intended scandir failure was not injected')

    def test_nonignored_directory_link_is_rejected(self):
        destination = self.target / 'real-directory'
        destination.mkdir()
        self.put(destination, 'extra.py', 'linked content must not silently disappear')
        self.put(self.source, 'real-directory/extra.py', 'linked content must not silently disappear')
        link = self.target / 'linked-directory'
        try:
            link.symlink_to(destination, target_is_directory=True)
        except OSError as exc:
            if os.name != 'nt':
                self.skipTest(f'Directory symlinks unavailable: {exc}')
            # Windows junctions exercise the same incomplete-enumeration risk
            # without enabling privileges or changing access controls.
            literal = lambda value: "'" + str(value).replace("'", "''") + "'"
            command = ('New-Item -ItemType Junction -Path ' + literal(link) +
                       ' -Target ' + literal(destination) + ' -ErrorAction Stop | Out-Null')
            process = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
            if process.returncode:
                self.skipTest('Directory symlink/junction unavailable: ' + process.stderr.decode(errors='replace'))
        self.assertTrue(link.is_dir())
        result = self.compare(2)
        self.assertFalse(result['identical'])
        self.assertIn('linked-directory', result['error'])

    def test_git_worktree_metadata_file_is_ignored(self):
        self.put(self.target, '.git', 'gitdir: ../local-worktree-metadata\n')
        result = self.compare(0)
        self.assertTrue(result['identical'])
        self.assertEqual(result['compared_files'], 2)


if __name__ == '__main__':
    unittest.main()
