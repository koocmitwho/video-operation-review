"""Opt-in regression for the private RC consolidation script, not CLI inference.

Set VOR_RC_FIXTURE, VOR_FINALIZER, VOR_WORKTREE and VOR_ORIGINAL_TRIALS.
The licensed/local fixture stays outside the distributable project.
"""
import copy
import ast
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class ConsolidationRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(os.environ['VOR_FINALIZER']).read_text(encoding='utf-8')
        assignments = {node.targets[0].id: node.value for node in ast.parse(source).body
                       if isinstance(node, ast.Assign) and len(node.targets) == 1
                       and isinstance(node.targets[0], ast.Name)}
        for key, variable in [('ROOT', 'VOR_WORKTREE'), ('BASE', 'VOR_VALIDATION_BASE'),
                              ('old', 'VOR_ORIGINAL_TRIALS')]:
            expected = ast.parse(f"Path(os.environ['{variable}'])", mode='eval').body
            if key not in assignments or ast.dump(assignments[key]) != ast.dump(expected):
                raise ValueError('Use the isolated explicit-environment replay copy; original scripts are not executed.')
        cls.temp = tempfile.TemporaryDirectory(prefix='vor rc replay ')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.base = Path(cls.temp.name)
        fixture = Path(os.environ['VOR_RC_FIXTURE'])
        for name in ('rechecks', 'visual'):
            shutil.copytree(fixture / name, cls.base / name)
        cls.observed = {'Part-1.Approximate global size': '0.4', 'Part-1.Curvature control': True,
                        'Part-1.Maximum deviation factor': '0.1',
                        'Part-1.Minimum size control': 'By fraction of global size',
                        'Part-1.Minimum size fraction': '0.1'}
        # The literal observations are freshly rechecked pixels, never effective values.
        with closing(sqlite3.connect(cls.base / 'rechecks/parameters/review.sqlite3')) as conn:
            step = json.loads(conn.execute("SELECT payload FROM steps WHERE id='S02'").fetchone()[0])
            for name, value in cls.observed.items():
                step['final_parameters'][name]['observed_value'] = value
                step['final_parameters'][name]['value'] = None
            conn.execute("UPDATE steps SET payload=? WHERE id='S02'", (json.dumps(step),))
            conn.commit()
        cls.attempts_before = cls.attempts()
        cls.runs = []
        env = dict(os.environ, VOR_VALIDATION_BASE=str(cls.base), PYTHONDONTWRITEBYTECODE='1')
        for _ in range(2):
            result = subprocess.run([sys.executable, '-X', 'utf8', os.environ['VOR_FINALIZER']],
                                    env=env, capture_output=True, encoding='utf-8', timeout=120)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            cls.runs.append({case: json.loads((cls.base / 'rechecks' / case / 'review.json').read_text(encoding='utf-8'))
                             for case in ('parameters', 'file-handoff', 'replacement')})

    @classmethod
    def attempts(cls):
        result = {}
        for case in ('parameters', 'file-handoff', 'replacement'):
            with closing(sqlite3.connect(cls.base / 'rechecks' / case / 'review.sqlite3')) as conn:
                for ident, payload in conn.execute('SELECT id,payload FROM issues'):
                    result[case, ident] = json.loads(payload)['attempts']
        return copy.deepcopy(result)

    def test_repeat_preserves_observations_without_promoting_effective_values(self):
        for run in self.runs:
            step = next(s['payload'] for s in run['parameters']['steps'] if s['id'] == 'S02')
            for name, expected in self.observed.items():
                with self.subTest(parameter=name):
                    self.assertEqual(step['final_parameters'][name]['observed_value'], expected)
                    self.assertIsNone(step['final_parameters'][name]['value'])

    def test_replayed_attempts_preserve_existing_history_without_appending_duplicates(self):
        after = self.attempts()
        for key in [('parameters', 'Q01'), ('parameters', 'Q02'), ('file-handoff', 'Q01'),
                    ('file-handoff', 'Q02'), ('file-handoff', 'Q03'), ('replacement', 'Q01')]:
            with self.subTest(issue=key):
                self.assertEqual(after[key], self.attempts_before[key])

    def test_unknown_count_remains_unknown_in_action_and_result_prose(self):
        step = next(s['payload'] for s in self.runs[-1]['file-handoff']['steps'] if s['id'] == 'S01')
        self.assertIsNone(step['final_parameters']['已加载行数']['value'])
        for prose in (step['confirmation_action'], step['visible_result'],
                      step['transition']['confirmation']['note'], step['transition']['result']['note']):
            with self.subTest(prose=prose):
                self.assertNotIn('9,296', prose)
                self.assertNotIn('2,958', prose)
        self.assertFalse(self.runs[-1]['file-handoff']['validation']['review_complete'])

    def test_unconfirmed_submission_has_no_confirmed_interval_title(self):
        interval = next(i['payload'] for i in self.runs[-1]['parameters']['intervals'] if i['id'] == 'I03')
        self.assertEqual(interval['fine_status'], 'partial')
        self.assertNotIn('并确认', interval['phase'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
