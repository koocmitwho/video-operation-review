"""The distributable demonstration must survive a normal Git checkout."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class PackagedExampleContract(unittest.TestCase):
    def test_example_report_video_and_evidence_are_not_ignored(self):
        paths = ['examples/tutorial/report.md', 'examples/tutorial/tutorial.mkv',
                 'examples/tutorial/evidence/f000000008.png']
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(['git', 'init', '--quiet', folder], check=True,
                           capture_output=True, timeout=10)
            shutil.copyfile(ROOT / '.gitignore', Path(folder) / '.gitignore')
            result = subprocess.run(['git', '-C', folder, 'check-ignore', '-z', '--stdin'],
                                    input=('\0'.join(paths) + '\0').encode(),
                                    capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stdout.decode(errors='replace'))
        self.assertEqual(result.stdout, b'')


if __name__ == '__main__':
    unittest.main()
