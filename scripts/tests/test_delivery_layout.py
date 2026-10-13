"""Readable delivery behavior; synthetic records do not prove visual accuracy."""
import json
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_report as record_fixture
from vor_report import render_report


class DeliveryLayoutContract(unittest.TestCase):
    def setUp(self):
        self.fixture = record_fixture.ReadableReportContract(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        first = self.fixture.step('S1', 0, 1)
        first['input_action'] = '输入 2，然后应用'
        second = self.fixture.step('S2', 2, 3, 'partial', '9')
        second['phase'] = '检查计算结果'
        second['input_action'] = '没有新增输入'
        self.fixture.add_records(steps=[second, first])
        self.fixture.export()
        self.report = json.loads((self.fixture.work / 'review.json').read_text(encoding='utf-8'))

    def render(self):
        def frame_details(n):
            row = self.fixture.conn.execute('SELECT * FROM frames WHERE frame_no=?', (n,)).fetchone()
            return dict(row) if row else None
        return render_report(self.report, self.fixture.work, frame_details)

    def test_every_action_is_readable_in_order_before_the_first_picture(self):
        md = self.render()
        self.assertIn('## 连续操作清单', md)
        overview = md.split('## 连续操作清单', 1)[1].split('## 参数与生效范围', 1)[0]
        self.assertLess(md.index('## 连续操作清单'), md.index('!['))
        self.assertLess(overview.index('[S1]'), overview.index('[S2]'))
        for fragment in ['设置步长', '检查计算结果', '已确认', '待核实', '设置 → 求解参数',
                         '对象 A', '对象 B', '输入 2，然后应用', '没有新增输入',
                         '点击应用', '参数栏显示新值', '00:00.250', '00:01.000']:
            self.assertIn(fragment, overview)
        for ident in ['5331', '5332']:
            self.assertIn(f'](#step-{ident})', overview)
            self.assertIn(f'<a id="step-{ident}"></a>', md)

    def test_all_evidence_remains_linked_and_images_are_folded_per_step(self):
        md = self.render()
        groups = re.findall(r'<details>\s*<summary>完整证据[^<]*</summary>(.*?)</details>', md, re.S)
        self.assertEqual(len(groups), 2)
        outside = re.sub(r'<details>.*?</details>', '', md, flags=re.S)
        self.assertNotIn('![', outside)
        for index in range(4):
            target = f'evidence/frame%20{index}%20%28full%29.png'
            ident = f'f{index:09d}'
            self.assertIn(f'[{ident}](<{target}>)', outside)
            self.assertEqual(md.count(f'![{ident}](<{target}>)'), 1)
        self.assertIn('操作前', groups[0])
        self.assertIn('确认动作', groups[1])

    def test_delivery_summary_is_durable_escaped_and_replaces_unknown_replay_default(self):
        self.report['delivery_summary'] = ['本轮范围：只核对 <参数> 与 [输出]',
                                           '旁白：已采用 source.srt',
                                           '复现验收：已记录独立操作结果，审阅完成度单列']
        md = self.render()
        front = md.split('## 连续操作清单', 1)[0]
        self.assertIn('本轮范围：只核对 &lt;参数&gt; 与 \\[输出\\]', front)
        self.assertIn('旁白：已采用 source.srt', front)
        self.assertIn('复现验收：已记录独立操作结果', front)
        self.assertNotIn('复现验收：未记录', front)

    def test_report_exposes_a_stable_handoff_entry_before_evidence(self):
        md = self.render()
        self.assertIn('[继续审阅与交接](handoff.md)', md.split('![', 1)[0])
        self.assertIn('复现验收：未记录', md)

    def test_legacy_resolved_without_structured_closure_remains_a_visible_risk(self):
        self.report['issues'] = [dict(payload=dict(id='Q-old', question='是否应用？', status='resolved',
            step_ids=['S1'], start_frame=0, end_frame=1, attempts=[], resolution='旧记录称已处理',
            next_action='补充确认画面'))]
        md = self.render()
        front = md.split('## 参数与生效范围', 1)[0]
        self.assertIn('未解决事项：1', front)
        self.assertIn('Q-old', front)
        self.assertIn('已标记解决，结案依据待补', md)
        self.assertIn('旧记录称已处理', md)
        self.assertIn('补充确认画面', md)
        self.assertNotIn('S1 完成后', md)
        self.assertNotIn('### 已解决事项', md)

    def test_legacy_no_action_instruction_is_history_not_the_current_next_step(self):
        issue = dict(id='Q-old', question='是否应用？', status='resolved', step_ids=['S1'],
                     start_frame=0, end_frame=1, next_action='不需操作，无须继续补图',
                     attempts=[dict(action='查看确认后画面', conclusion='已解决')])
        self.report['issues'] = [dict(payload=issue)]
        original = json.dumps(self.report, ensure_ascii=False, sort_keys=True)
        md = self.render()
        detail = md.split('#### Q-old', 1)[1].split('## 附录', 1)[0]
        current = [line for line in detail.splitlines() if line.startswith('下一步：')]
        self.assertEqual(current, ['下一步：核对已有补查与证据，补齐记录者、理由和来源。'])
        self.assertIn('原下一步（历史记录）：不需操作，无须继续补图', detail)
        self.assertIn('历史结案标记；当前缺少结构化结案依据，以下补查结论是历史原文', detail)
        self.assertIn('结论：已解决', detail)
        self.assertLess(detail.index('历史结案标记'), detail.index('结论：已解决'))
        self.assertEqual(json.dumps(self.report, ensure_ascii=False, sort_keys=True), original)

    def test_structured_resolution_has_readable_provenance_and_linked_evidence(self):
        self.report['issues'] = [dict(payload=dict(id='Q-new', question='是否应用？', status='resolved',
            step_ids=['S1'], start_frame=0, end_frame=1, attempts=[],
            resolution=dict(mode='evidence', reviewer='reviewer-A', reason='状态栏显示 Applied',
                            evidence=['f000000001'])))]
        md = self.render()
        self.assertIn('未解决事项：0', md)
        resolved = md.split('### 已解决事项', 1)[1].split('## 附录', 1)[0]
        for fragment in ['结案方式：证据确认', '记录者：reviewer-A', '理由：状态栏显示 Applied',
                         '[f000000001](<evidence/frame%201%20%28full%29.png>)']:
            self.assertIn(fragment, resolved)
        self.assertNotIn('mode：', resolved)
        self.assertNotIn('reviewer：', resolved)

    def test_withdrawn_issue_preserves_the_reason_and_checkable_basis(self):
        self.report['issues'] = [dict(payload=dict(id='Q-withdrawn', question='需要再次点击？',
            status='resolved', step_ids=['S1'], start_frame=0, end_frame=1, attempts=[],
            resolution=dict(mode='withdrawn', reviewer='reviewer-B', reason='原问题误设',
                            basis='S1 原记录与同一确认画面重复提出了问题')))]
        md = self.render()
        self.assertIn('结案方式：撤回误设问题', md)
        self.assertIn('核对依据：S1 原记录与同一确认画面重复提出了问题', md)
        self.assertIn('记录者：reviewer-B', md)

    def test_checklist_escapes_source_text_and_does_not_turn_final_values_into_inputs(self):
        step = self.report['steps'][0]['payload']
        step['id'] = 'S[1]\"<img>'
        step['phase'] = '查看 <script> | [参数]'
        step.pop('input_action')
        step['final_parameters']['步长']['value'] = '987654'
        md = self.render()
        self.assertIn('## 连续操作清单', md)
        overview = md.split('## 连续操作清单', 1)[1].split('## 参数与生效范围', 1)[0]
        self.assertIn('&lt;script&gt; \\| \\[参数\\]', overview)
        self.assertNotIn('<img>', md)
        self.assertNotIn('987654', overview)
        self.assertIn('输入过程未单独记录', overview)
        self.assertTrue(all(re.fullmatch(r'step-[0-9a-f]+', value)
                            for value in re.findall(r'<a id="([^"]+)"></a>', md)))


if __name__ == '__main__':
    unittest.main()
