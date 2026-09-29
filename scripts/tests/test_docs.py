"""安装命令、文档拓扑、验证产物与发布配置契约；使用标准库。"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]


def project_files():
    excluded = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache',
                'input', 'work', 'output', 'outputs', 'evidence'}
    for folder, directories, filenames in os.walk(ROOT):
        directories[:] = [name for name in directories if name not in excluded]
        for name in filenames:
            yield Path(folder) / name


def prose(text):
    return re.sub(r'(?ms)^```[^\n]*\n.*?^```\s*$', '', text)


def links(path):
    text = prose(path.read_text(encoding='utf-8'))
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
        target = target.strip().strip('<>')
        if urlsplit(target).scheme or target.startswith('#'):
            continue
        yield (path.parent / unquote(target.split('#')[0])).resolve()


class DocumentationContract(unittest.TestCase):
    def test_command_examples_have_no_invalid_control_characters(self):
        blocks = re.compile(r'(?ms)^```(?:powershell|bash|sh|shell|cmd|text)[ \t]*\n(.*?)^```[ \t]*$')
        offenders = []
        for doc in (p for p in project_files() if p.suffix == '.md'):
            text = doc.read_text(encoding='utf-8')
            for block in blocks.finditer(text):
                for offset, char in enumerate(block.group(1)):
                    if (ord(char) < 32 and char not in '\t\r\n') or ord(char) == 127:
                        line = text.count('\n', 0, block.start(1) + offset) + 1
                        offenders.append(f'{doc.relative_to(ROOT)}:{line}: U+{ord(char):04X}')
        self.assertEqual(offenders, [], 'Command arguments contain non-copyable control characters.')

    def test_relative_markdown_links_resolve(self):
        for doc in (p for p in project_files() if p.suffix == '.md'):
            for target in links(doc):
                with self.subTest(doc=str(doc.relative_to(ROOT)), target=str(target)):
                    self.assertTrue(target.exists())

    def test_all_references_are_reachable_from_skill(self):
        reached, queue = set(), [ROOT / 'SKILL.md']
        while queue:
            doc = queue.pop().resolve()
            if doc in reached or doc.suffix != '.md' or not doc.is_file():
                continue
            reached.add(doc)
            queue.extend(links(doc))
        self.assertEqual({p.resolve() for p in (ROOT / 'references').glob('*.md')} - reached, set())

    def test_readme_language_link_and_structure_match(self):
        cn, en = [(ROOT / p).read_text(encoding='utf-8') for p in ('README.md', 'README.en.md')]
        self.assertIn(ROOT / 'README.en.md', set(links(ROOT / 'README.md')))
        headings = lambda text: [len(s) for s in re.findall(r'(?m)^(#{1,6}) ', text)]
        self.assertEqual(headings(cn), headings(en))
        self.assertEqual(len(re.findall(r'(?m)^```', cn)), len(re.findall(r'(?m)^```', en)))

    def test_skill_frontmatter_matches_install_directory(self):
        text = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
        name = re.search(r'(?m)^name: (\S+)$', text).group(1)
        self.assertRegex(name, r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
        # 安装目录名取自 README 记录的安装路径，与检出目录名无关。
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        installed = re.search(r'skills[/\\]([a-z0-9-]+)', readme).group(1)
        self.assertEqual(name, installed)
        self.assertRegex(text, r'(?m)^description: >-\n  \S')

    def test_reference_commands_resolve_from_skill_root(self):
        for name in ('examples.md', 'layered-review.md', 'models.md', 'models.en.md'):
            text = (ROOT / 'references' / name).read_text(encoding='utf-8')
            with self.subTest(name=name):
                self.assertNotRegex(text, r"Resolve-Path ['\"]\./scripts/")
                self.assertNotIn('python scripts/review_video.py', text)
                self.assertIn('$skillRoot', text)
                self.assertIn('Join-Path $skillRoot', text)
                self.assertIn('& $pythonExe', text)

    def test_documented_parameter_literals_match_parser(self):
        for file, options in [('method.md', ['--tile-size', '--checkpoint-frames']),
                              ('layered-review.md', ['--max-span']), ('examples.md', ['--stride'])]:
            text = (ROOT / 'references' / file).read_text(encoding='utf-8')
            for option in options:
                with self.subTest(file=file, option=option):
                    self.assertIn(option, text)

    def test_visible_key_states_have_frames_expectations_and_rules(self):
        path = ROOT / 'validation/layered-trial-truth.json'
        self.assertTrue(path.is_file())
        truth = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual([s['frame_no'] for s in truth['key_states']], list(range(16, 25)))
        self.assertTrue(all(s['expected_visible'] for s in truth['key_states']))
        self.assertTrue(truth['judgement_rule'])
        summary = json.loads((ROOT / 'validation/verification.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['synthetic_visual_trial']['visible_key_states'], [9, 9])
        self.assertIn(path, set(links(ROOT / 'references/validation.md')))

    def test_baseline_and_dated_historical_test_logs_are_linked(self):
        baseline = ROOT / 'validation/tests-98.log'
        self.assertRegex(baseline.read_text(encoding='utf-8'), r'Ran 98 tests in [\d.]+s\s+OK\s*$')
        for name in ('README.md', 'references/validation.md'):
            self.assertIn(baseline, set(links(ROOT / name)))
        historical = ROOT / 'validation/script-tests-20260924.log'
        self.assertTrue(historical.is_file())
        self.assertFalse((ROOT / 'validation/script-tests.log').exists())

    def test_dependency_ranges_bound_existing_packages(self):
        text = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
        self.assertRegex(text, r'(?mi)^numpy>=2,<3$')
        self.assertRegex(text, r'(?mi)^Pillow>=10\.1,<13$')

    def test_ci_records_helper_versions_and_pins_installations(self):
        text = (ROOT / '.github/workflows/tests.yml').read_text(encoding='utf-8')
        self.assertIn('ffmpeg -version', text)
        self.assertIn('ffprobe -version', text)
        self.assertRegex(text, r'choco install ffmpeg[^\n]*--version[= ]\d')
        self.assertIn('ubuntu-24.04', text)
        self.assertRegex(text, r'ffmpeg=[^\s]+')

    def test_codex_skill_has_explicit_invocation_and_prompt(self):
        text = (ROOT / 'agents/openai.yaml').read_text(encoding='utf-8')
        self.assertRegex(text, r'(?m)^  default_prompt: .*\$video-operation-review')
        self.assertRegex(text, r'(?m)^policy:\n  allow_implicit_invocation: false\s*$')

    def test_text_line_endings_follow_gitattributes(self):
        attrs = ROOT / '.gitattributes'
        self.assertTrue(attrs.is_file())
        self.assertIn('* text=auto', attrs.read_text(encoding='utf-8'))
        if not (ROOT / '.git').exists():
            self.skipTest('Not a git checkout; line endings are normalized by git on clone.')
        # 检查提交内容（索引侧），不依赖检出时的换行转换或编辑器设置。
        result = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '--eol'],
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        suffixes = {'.py', '.md', '.yaml', '.yml', '.json', '.txt', '.log'}
        offenders = []
        for line in result.stdout.splitlines():
            index, _, path = line.partition('\t')
            if Path(path.strip()).suffix in suffixes and index.split()[0] in {'i/crlf', 'i/mixed'}:
                offenders.append(path.strip())
        self.assertEqual(offenders, [])

    def test_review_outputs_are_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(['git', 'init', '--quiet', folder], check=True, capture_output=True, timeout=10)
            shutil.copyfile(ROOT / '.gitignore', Path(folder) / '.gitignore')
            outputs = ['layer-plan.json', 'review.json', 'frames.jsonl', 'omission-audit.json', 'report.md', 'evidence/frame.png']
            result = subprocess.run(['git', '-C', folder, 'check-ignore', '-z', '--stdin'],
                                    input=('\0'.join(outputs)+'\0').encode(), capture_output=True, timeout=10)
            self.assertEqual(set(result.stdout.decode().rstrip('\0').split('\0')), set(outputs))

    def test_mit_license_is_shipped(self):
        file = ROOT / 'LICENSE'
        self.assertTrue(file.is_file())
        text = file.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('MIT License\n'))
        self.assertIn('Permission is hereby granted, free of charge', text)


if __name__ == '__main__':
    unittest.main()
