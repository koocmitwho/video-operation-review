"""User-facing export contracts; synthetic records are not a visual or reproduction test."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vor_store as store


class ReadableReportContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vor report 中文 ')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.conn = store.connect(self.work, create=True)
        self.addCleanup(self.conn.close)
        self.video = self.work / 'source clip (1).mkv'
        self.video.write_bytes(b'synthetic source identity; not decoded media')
        source, _, _ = store.source_file_identity(self.video)
        store.set_meta(self.conn, 'source', source)
        self.conn.executemany(
            'INSERT INTO frames(frame_no,pts,pts_time,time_s,time_source) VALUES (?,?,?,?,?)',
            [(0, '5000', '5.000', 5.0, 'pts'), (1, '5250', '5.250', 5.25, 'pts'),
             (2, '5500', '5.500', 5.5, 'pts'), (3, '6000', '6.000', 6.0, 'pts')])
        evidence = self.work / 'evidence'
        evidence.mkdir()
        for n in range(4):
            path = evidence / f'frame {n} (full).png'
            path.write_bytes(f'synthetic asset {n}; not visually inspected'.encode())
            ident = f'f{n:09d}'
            self.conn.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?,?)',
                              (ident, n, 'full', path.relative_to(self.work).as_posix(),
                               store.sha256(path), None, None, store.now()))
        self.conn.commit()
        for n in range(4):
            store.record_view(self.conn, self.work, f'f{n:09d}', 'test-author', 'view_image',
                              'synthetic-test://report-fixture', 'Synthetic bookkeeping only.')

    @staticmethod
    def step(ident, start, end, status='confirmed', value='2'):
        refs = [f'f{start:09d}', f'f{end:09d}']
        return dict(id=ident, phase='设置步长', start_frame=start, end_frame=end,
                    software='ExampleApp', module='分析', menu_path=['设置', '求解参数'],
                    selected_objects=['对象 A' if start == 0 else '对象 B'],
                    final_parameters={'步长': {'value': value, 'unit': 's', 'evidence': [refs[-1]],
                                               'basis': '确认后的参数栏'}},
                    confirmation_action='点击应用', visible_result='参数栏显示新值',
                    input_files=[{'visible_name': 'input.csv', 'full_path': '未展示', 'role': '输入'}],
                    output_files=[], evidence=refs, uncertainties=[] if status == 'confirmed' else ['未看清应用'],
                    status=status, author='test-author',
                    role_evidence={'before': [refs[0]], 'during': [refs[-1]], 'after': [refs[-1]]},
                    transition={'confirmation': {'status': 'observed', 'evidence': [refs[-1]]},
                                'result': {'status': 'observed', 'evidence': [refs[-1]]}})

    def add_records(self, **records):
        path = self.work / 'annotations.json'
        path.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
        store.import_records(self.conn, path)

    def export(self):
        result = store.export_records(self.conn, self.work)
        return result, (self.work / 'report.md').read_text(encoding='utf-8')

    def test_first_screen_exposes_usable_steps_and_blockers_before_statistics(self):
        self.add_records(steps=[self.step('S2', 2, 3, 'partial', '9'), self.step('S1', 0, 1)],
                         issues=[dict(id='Q1', question='是否应用了新值？', status='open', attempts=[],
                                      start_frame=2, end_frame=3)])
        result, md = self.export()
        front = md.split('## 操作步骤')[0]
        self.assertIn('当前交付状态', front)
        self.assertIn('已确认步骤：S1', front)
        self.assertIn('待核实步骤：S2', front)
        self.assertIn('Q1', front)
        self.assertNotIn('| 统计 |', front)
        self.assertIn('复现验收：未记录', front)
        self.assertLess(md.index('### S1'), md.index('### S2'))
        self.assertTrue(result['validation_passed'])
        self.assertFalse(result['review_complete'])

    def test_steps_and_files_render_as_instructions_instead_of_raw_objects(self):
        self.add_records(steps=[self.step('S1', 0, 1)])
        _, md = self.export()
        body = md.split('## 操作步骤')[1].split('## 待核对事项')[0]
        for phrase in ['点击哪里', '设置 → 求解参数', '选择什么', '对象 A', '填写什么',
                       '步长', '2 s', '如何确认', '点击应用', '应看到什么', '参数栏显示新值',
                       'input.csv', '完整路径：未展示']:
            self.assertIn(phrase, body)
        for json_fragment in ['"value":', '"visible_name":', '["设置"', '{"']:
            self.assertNotIn(json_fragment, body)

    def test_parameter_summary_preserves_object_and_step_scope_and_unknowns(self):
        a, b = self.step('S1', 0, 1), self.step('S2', 2, 3, 'partial', '9')
        b['final_parameters']['温度'] = {'value': None, 'unit': 'K'}
        self.add_records(steps=[a, b])
        _, md = self.export()
        self.assertIn('## 参数与生效范围', md)
        summary = md.split('## 参数与生效范围')[1].split('## 操作步骤')[0]
        rows = [line for line in summary.splitlines() if line.startswith('|')]
        self.assertTrue(any('S1' in row and '对象 A' in row and '2 s' in row and 'S1 完成后' in row for row in rows))
        self.assertTrue(any('S2' in row and '对象 B' in row and '9 s' in row and '生效未核实' in row for row in rows))
        self.assertTrue(any('温度' in row and '未知' in row and '生效未核实' in row for row in rows))
        self.assertNotIn('最终参数：', md)

    def test_nonzero_pts_and_evidence_roles_are_distinct_from_relative_time(self):
        self.add_records(steps=[self.step('S1', 0, 1)])
        _, md = self.export()
        self.assertIn('原始 PTS：5.250 s', md)
        self.assertIn('相对视频首帧：00:00.250', md)
        self.assertIn('播放器实际起点未核实', md)
        self.assertIn('操作前', md)
        self.assertIn('操作中', md)
        self.assertIn('操作后', md)
        self.assertIn('frame%201%20%28full%29.png', md)
        self.assertIn('source%20clip%20%281%29.mkv', md)
        self.assertIn('](<source%20clip%20%281%29.mkv>)', md)
        self.assertIn('f000000000', md)
        self.assertIn('f000000001', md)

    def test_missing_origin_and_best_effort_timestamps_are_not_invented_pts(self):
        self.conn.execute("UPDATE frames SET pts=NULL,pts_time=NULL,time_s=NULL,time_source='missing' WHERE frame_no=0")
        self.conn.execute("UPDATE frames SET pts=NULL,pts_time=NULL,best_effort_time='5.250',time_source='best_effort' WHERE frame_no=1")
        self.conn.commit()
        self.add_records(steps=[self.step('S1', 0, 1)])
        _, md = self.export()
        self.assertIn('原始 PTS：未知', md)
        self.assertIn('best-effort：5.250 s', md)
        self.assertIn('相对视频首帧：未知', md)
        self.assertNotIn('原始 PTS：5.250 s', md)
        self.assertNotIn('相对视频首帧：00:00.250', md)

    def test_issues_show_attempts_step_context_and_only_open_items_block_delivery(self):
        self.add_records(steps=[self.step('S1', 0, 1), self.step('S2', 2, 3, 'partial')], issues=[
            dict(id='Q1', question='是否确认执行？', status='blocked', start_frame=2, end_frame=3,
                 attempts=[dict(action='查看按钮裁剪', original_time_range=[5.5, 6.0],
                                evidence=['f000000003'], new_information='按钮被遮挡', conclusion='仍待核实')],
                 next_action='补看未遮挡的确认画面', impact='尚不能将新值作为后续计算输入'),
            dict(id='Q2', question='输入文件名？', status='resolved', start_frame=0, end_frame=1,
                 attempts=[dict(action='放大标题栏', new_information='已读到 input.csv', conclusion='已解决')])])
        _, md = self.export()
        front = md.split('## 参数与生效范围')[0]
        self.assertIn('Q1', front)
        self.assertNotIn('Q2', front)
        issues = md.split('## 待核对事项')[1].split('## 附录')[0]
        for phrase in ['Q1', '关联步骤：S2', '查看按钮裁剪', '按钮被遮挡', '补看未遮挡的确认画面',
                       '已解决事项', 'Q2', '已读到 input.csv', '5.500', '尚不能将新值作为后续计算输入']:
            self.assertIn(phrase, issues)

    def test_legacy_steps_and_empty_exports_remain_readable_without_changing_machine_contract(self):
        _, empty = self.export()
        self.assertIn('尚无操作步骤', empty)
        self.assertIn('复现验收：未记录', empty)
        old = self.step('S1', 0, 1)
        for key in ['author', 'transition', 'role_evidence']:
            old.pop(key)
        old['final_parameters'] = {'步长': 2}
        self.add_records(steps=[old])
        result, md = self.export()
        saved = json.loads((self.work / 'review.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['schema_version'], 3)
        self.assertEqual(saved['steps'][0]['payload'], old)
        self.assertEqual(result['validation_passed'], saved['validation']['valid'])
        self.assertEqual(result['review_complete'], saved['validation']['review_complete'])
        self.assertIn('角色未记录', md)
        self.assertIn('记录完整性', md)
        self.assertIn('审阅完成度', md)

    def test_text_metacharacters_cannot_break_markdown_tables_or_inject_html(self):
        step = self.step('S1', 0, 1)
        step['phase'] = '导入 *模型* | [v1] <img>'
        step['selected_objects'] = ['A|B']
        step['final_parameters']['文件'] = {'value': {'name': 'a[b].csv', 'path': 'D:\\input files\\x.csv'}}
        self.add_records(steps=[step])
        _, md = self.export()
        self.assertIn('导入 \\*模型\\* \\| \\[v1\\] &lt;img&gt;', md)
        self.assertIn('A\\|B', md)
        self.assertNotIn('<img>', md)
        self.assertNotIn('{"name":', md)

    def test_recorded_parameter_state_does_not_invent_an_input_action(self):
        cancelled = self.step('S1', 0, 1, value='1')
        cancelled['confirmation_action'] = '输入 20 后点击取消'
        cancelled['visible_result'] = '参数保留为 1'
        partial = self.step('S2', 2, 3, 'partial', '9')
        self.add_records(steps=[cancelled, partial])
        _, md = self.export()
        fill_lines = [line for line in md.splitlines() if '**填写什么**' in line]
        self.assertEqual(len(fill_lines), 2)
        for line in fill_lines:
            self.assertNotIn(' = ', line)
            self.assertIn('输入过程', line)
        self.assertIn('输入 20 后点击取消', md)
        self.assertIn('参数保留为 1', md)
        self.assertIn('阶段参数记录', md)

    def test_appendix_preserves_closed_range_boundaries(self):
        self.conn.execute("UPDATE frames SET digest='synthetic',exact_start=1 WHERE frame_no=1")
        self.conn.commit()
        _, md = self.export()
        self.assertIn('未计算范围：0–0；2–3', md)
        self.assertIn('未索引尾部：自源帧 4 起，结束未知', md)

    def test_changed_evidence_cannot_support_an_effective_parameter_claim(self):
        self.add_records(steps=[self.step('S1', 0, 1)])
        (self.work / 'evidence' / 'frame 1 (full).png').write_bytes(b'replaced evidence')
        result, md = self.export()
        self.assertFalse(result['validation_passed'])
        self.assertIn('证据或记录待修复', md)
        summary = md.split('## 参数与生效范围')[1].split('## 操作步骤')[0]
        self.assertNotIn('S1 完成后', summary)
        self.assertIn('记录完整性待修复', summary)

    def test_observed_input_action_is_separate_from_recorded_final_state(self):
        step = self.step('S1', 0, 1, value='1')
        step['input_action'] = '输入 20，然后取消'
        self.add_records(steps=[step])
        _, md = self.export()
        fill_line = next(line for line in md.splitlines() if '**填写什么**' in line)
        self.assertIn('输入 20，然后取消', fill_line)
        self.assertNotIn('1 s', fill_line)
        self.assertIn('阶段参数记录：步长 = 1 s', md)

    def test_linked_open_issue_downgrades_display_without_rewriting_step(self):
        step = self.step('S1', 0, 1)
        self.add_records(steps=[step], issues=[dict(
            id='Q1', question='保存后的交接还未确认', status='open', step_ids=['S1'], attempts=[])])
        result, md = self.export()
        heading = next(line for line in md.splitlines() if line.startswith('### S1'))
        self.assertIn('部分确认，待核实', heading)
        self.assertIn('步骤登记为已确认', heading)
        self.assertIn('待核实步骤：S1', md)
        self.assertNotIn('S1 完成后', md)
        saved = json.loads((self.work / 'review.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['steps'][0]['payload'], step)
        self.assertTrue(result['validation_passed'])
        self.assertFalse(result['review_complete'])


if __name__ == '__main__':
    unittest.main()
