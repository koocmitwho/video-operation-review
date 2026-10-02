"""Render an agent's persisted observations as a readable, evidence-linked handoff."""
import html
import math
from pathlib import Path
from urllib.parse import quote
from vor_store import issue_steps


def text(value):
    """Escape record text once, including text inside Markdown tables and image labels."""
    if value is None:
        return '未知'
    if isinstance(value, bool):
        return '是' if value else '否'
    result = html.escape(str(value), quote=False).replace('\\', '\\\\')
    for char in '`*_[]|#':
        result = result.replace(char, '\\' + char)
    return ' / '.join(result.splitlines())


def readable(value):
    if isinstance(value, dict):
        return '；'.join(f'{text(k)}：{readable(v)}' for k, v in value.items()) or '未记录'
    if isinstance(value, (list, tuple)):
        return '、'.join(readable(v) for v in value) or '无记录'
    return text(value) if value != '' else '未记录'


def link(label, path, work=None):
    path = str(path)
    if work is not None:
        candidate = Path(path)
        if candidate.is_absolute():
            try:
                path = candidate.relative_to(work).as_posix()
            except ValueError:
                pass
    target = quote(path.replace('\\', '/'), safe='/:')
    return f'[{text(label)}](<{target}>)'


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def clock(seconds):
    millis = round(abs(seconds) * 1000)
    minutes, rest = divmod(millis, 60000)
    hours, minutes = divmod(minutes, 60)
    prefix = '-' if seconds < 0 else ''
    return f'{prefix}{hours:02d}:{minutes:02d}:{rest / 1000:06.3f}' if hours else f'{prefix}{minutes:02d}:{rest / 1000:06.3f}'


def timestamp(frame_no, frames):
    frame, origin = frames(frame_no) or {}, frames(0) or {}
    pts = number(frame.get('pts_time'))
    raw = f'原始 PTS：{pts:.3f} s' if pts is not None else '原始 PTS：未知'
    if pts is None and frame.get('time_source') == 'best_effort':
        best = number(frame.get('best_effort_time'))
        raw += f'；best-effort：{best:.3f} s' if best is not None else '；best-effort：未知'
    current, zero = number(frame.get('time_s')), number(origin.get('time_s'))
    relative = clock(current - zero) if current is not None and zero is not None else '未知'
    return f'源帧 {text(frame_no)}；{raw}；相对视频首帧：{relative}'


def step_label(step, issues=(), findings=()):
    if step.get('status') == 'confirmed' and (findings or any(
            i.get('status') != 'resolved' and step['id'] in issue_steps(i, [step]) for i in issues)):
        return '部分确认，待核实（步骤登记为已确认）'
    return {'confirmed': '已确认（步骤登记）', 'partial': '部分确认，待核实',
            'unresolved': '待核实'}.get(step.get('status'), '状态未记录')


def unknown(value):
    if value is None or value == '':
        return True
    if isinstance(value, str):
        return value.strip().lower() in {'unknown', 'n/a', 'null', '未知', '未展示', '待核实', '待辨认', '未记录'}
    if isinstance(value, dict):
        return not value or any(unknown(v) for k, v in value.items() if k != 'evidence')
    if isinstance(value, list):
        return not value or any(unknown(v) for v in value)
    return False


def parameter_value(value):
    if not isinstance(value, dict):
        return readable(value), value
    if value.get('visible') is False and 'value' not in value:
        return '控件不可见', False
    actual = value.get('value')
    result = readable(actual)
    if value.get('unit'):
        result += f" {text(value['unit'])}"
    return result, actual


def parameter_scope(step, actual, issues, record_valid, findings=()):
    if not record_valid:
        return '生效未核实（记录完整性待修复）'
    if findings:
        return '生效未核实（审计发现冲突或证据缺口）'
    blocked = any(issue.get('status') != 'resolved' and step['id'] in issue_steps(issue, [step]) for issue in issues)
    if step.get('status') != 'confirmed' or step.get('uncertainties') or unknown(actual) or blocked:
        return '生效未核实'
    transition = step.get('transition') or {}
    for name in ('confirmation', 'result'):
        item = transition.get(name) or {}
        if item.get('status') != 'observed' and not (item.get('status') == 'not_applicable' and item.get('note')):
            return '生效未核实（确认或结果依据未记录）'
    return f"{text(step['id'])} 完成后（按该步骤记录）"


def affected_steps(steps, audit):
    """Use explicit audit links; global coverage/review gaps do not negate every step."""
    codes = {'final_parameter_mismatch', 'state_discontinuity', 'confirmation_gap', 'result_gap',
             'step_transition_missing', 'step_state_missing', 'state_fact_invalid', 'state_value_unknown',
             'step_ranges_overlap', 'audit_evidence_missing', 'audit_evidence_unreviewed'}
    result = {step['id']: [] for step in steps}
    for finding in audit.get('findings', []):
        if finding.get('code') not in codes:
            continue
        owner_fields = ('step_id', 'previous_step', 'next_step')
        explicit_owner = any(key in finding for key in owner_fields)
        ids = {finding[key] for key in owner_fields if isinstance(finding.get(key), str)}
        reference = finding.get('reference')
        linked_finding = finding
        if not explicit_owner and isinstance(reference, str):
            # Older findings encoded owner/role/key into a dotted string. Legal IDs
            # can contain those same separators, so an ambiguous match is not fact.
            matching = [ident for ident in result if reference == ident or reference.startswith(ident + '.')]
            ids.update(matching)
            if len(matching) > 1:
                linked_finding = dict(finding, _report_ambiguous_step_ids=sorted(matching))
        for ident in ids:
            if ident in result:
                result[ident].append(linked_finding)
    return result


def parameter_findings(findings, name):
    """Old conflicts without a parameter key conservatively affect the whole step."""
    return [finding for finding in findings if finding['code'] != 'final_parameter_mismatch'
            or not finding.get('parameter_key') or finding['parameter_key'] == name]


def finding_reason(finding):
    # Called only for the fixed, known codes selected by affected_steps.
    reason = f"`{finding['code']}`：{text(finding.get('message', '需核实记录和证据'))}"
    if finding.get('_report_ambiguous_step_ids'):
        reason += '（旧发现的步骤引用存在歧义，候选：' + readable(finding['_report_ambiguous_step_ids']) + '；归属待核实）'
    return reason


def references(ids, assets):
    return '、'.join(link(ident, assets[ident]['path']) if ident in assets else f'{text(ident)}（证据缺失）'
                    for ident in ids) or '未记录'


def file_text(item):
    if not isinstance(item, dict):
        return readable(item)
    labels = {'visible_name': '可见名称', 'full_path': '完整路径', 'role': '用途', 'version': '版本',
              'path': '路径', 'evidence': '证据', 'note': '说明'}
    return '；'.join(f'{labels.get(k, text(k))}：{readable(v)}' for k, v in item.items()) or '未记录'


def range_text(value):
    if value is None:
        return '未知'
    return '；'.join(f'{text(start)}–{text(end)}' for start, end in value) or '无'


def evidence_roles(step, ident):
    labels = {'before': '操作前', 'during': '操作中', 'after': '操作后'}
    roles = [label for name, label in labels.items() if ident in (step.get('role_evidence') or {}).get(name, [])]
    for name, label in [('confirmation', '确认动作'), ('result', '结果')]:
        if ident in ((step.get('transition') or {}).get(name) or {}).get('evidence', []):
            roles.append(label)
    for name, value in (step.get('final_parameters') or {}).items():
        if isinstance(value, dict) and ident in value.get('evidence', []):
            roles.append(f'参数：{text(name)}')
    return '、'.join(roles) or '角色未记录'


def render_report(report, work, frames):
    """Only presentation changes here; machine data and completion gates stay in vor_store."""
    steps = sorted((r['payload'] for r in report.get('steps', [])),
                   key=lambda s: (s.get('start_frame', 0), s.get('end_frame', 0), s.get('id', '')))
    issues = [r['payload'] for r in report.get('issues', [])]
    open_issues = [i for i in issues if i.get('status') != 'resolved']
    assets = {a['id']: a for a in report.get('assets', [])}
    result = report['validation']
    findings_by_step = affected_steps(steps, report.get('coverage_audit') or {})
    confirmed = [s for s in steps if s.get('status') == 'confirmed' and not s.get('uncertainties')
                 and not findings_by_step[s['id']]
                 and not any(s['id'] in issue_steps(i, steps) for i in open_issues)]
    pending = [s for s in steps if s not in confirmed]
    if not result['valid']:
        delivery = '证据或记录待修复；当前内容用于继续核对'
    elif result['review_complete']:
        delivery = '当前范围的审阅记录已完成'
    else:
        delivery = '阶段性交付，审阅待完成'
    lines = ['# 软件操作录屏审阅', '', f'**当前交付状态：{delivery}。**', '',
             f"- 已确认步骤：{'、'.join(text(s['id']) for s in confirmed) or '无'}（按步骤记录）。",
             f"- 待核实步骤：{'、'.join(text(s['id']) for s in pending) or '无已登记项'}。",
             f"- 未解决事项：{len(open_issues)} 项。", '- 复现验收：未记录。审阅完成度与实际照做成功分别验收。', '']
    if not steps:
        lines += ['尚无操作步骤；需继续查看画面并记录操作。', '']
    for issue in open_issues:
        lines.append(f"- {text(issue.get('id'))}：{text(issue.get('question'))}")
    source = (report.get('source') or {}).get('path')
    lines += ['', f"源视频：{link(Path(source).name, source, work) if source else '未记录'}。", '',
              '时间定位：原始 PTS 保留媒体时间戳；相对视频首帧时间按索引首帧换算。'
              '播放器实际起点未核实，起点一致时可按相对时间定位；未知时间不换算。', '',
              '## 参数与生效范围', '',
              '每行保留对应步骤、对象与阶段；同名参数在后续步骤出现时另列，不跨步骤覆盖。', '',
              '| 步骤 / 阶段 | 对象 | 参数 | 记录值 | 生效范围 | 依据 |', '|---|---|---|---|---|---|']
    parameter_count = 0
    for step in steps:
        for name, value in (step.get('final_parameters') or {}).items():
            parameter_count += 1
            shown, actual = parameter_value(value)
            detail = value if isinstance(value, dict) else {}
            basis = text(detail['basis']) + '；' if detail.get('basis') else ''
            refs = references(detail.get('evidence', []), assets)
            findings = parameter_findings(findings_by_step[step['id']], name)
            diagnostics = '；' + '；'.join(finding_reason(f) for f in findings) if findings else ''
            lines.append(f"| {text(step['id'])} / {text(step.get('phase'))} | {readable(step.get('selected_objects', []))} | "
                         f"{text(name)} | {shown} | {parameter_scope(step, actual, issues, result['valid'], findings)} | {basis}{refs}{diagnostics} |")
    if not parameter_count:
        lines += ['| — | — | 尚无参数记录 | 未知 | 生效未核实 | — |']
    lines += ['', '## 操作步骤', '']
    if not steps:
        lines += ['尚无操作步骤。', '']
    for step in steps:
        step_findings = findings_by_step[step['id']]
        input_action = step.get('input_action')
        input_text = (text(input_action) if isinstance(input_action, str) and input_action.strip() else
                      '输入过程未单独记录；请结合确认动作与前后画面核对，阶段参数不代表输入动作。')
        lines += [f"### {text(step['id'])} · {text(step.get('phase'))} · {step_label(step, issues, step_findings)}", '',
                  f"起点：{timestamp(step.get('start_frame'), frames)}。", '',
                  f"终点：{timestamp(step.get('end_frame'), frames)}。", '',
                  f"软件 / 模块：{text(step.get('software'))} / {text(step.get('module'))}。", '']
        if step_findings:
            lines += ['当前审计发现冲突或证据缺口；下方保留原操作记录，需核实后使用。', '']
            for finding in step_findings:
                suggested = set(finding.get('suggested_frames', []))
                refs = [ident for ident in step.get('evidence', []) if ident in assets and assets[ident]['frame_no'] in suggested]
                refs = refs or step.get('evidence', [])
                lines.append(f"- {finding_reason(finding)}；该步骤证据：{references(refs, assets)}。")
            lines += ['']
        lines += [f"1. **点击哪里**：{' → '.join(readable(v) for v in step.get('menu_path', [])) or '入口未记录'}。",
                  f"2. **选择什么**：{readable(step.get('selected_objects', []))}。",
                  f'3. **填写什么**：{input_text}']
        params = step.get('final_parameters') or {}
        lines += [f"4. **如何确认**：{text(step.get('confirmation_action'))}",
                  f"5. **应看到什么**：{text(step.get('visible_result'))}", '']
        if params:
            lines += ['阶段参数记录：' + '；'.join(f'{text(k)} = {parameter_value(v)[0]}' for k, v in params.items()) + '。']
            if any('生效未核实' in parameter_scope(step, parameter_value(value)[1], issues, result['valid'],
                    parameter_findings(step_findings, name)) for name, value in params.items()):
                lines += ['此处包含待核实值，生效范围见上表。']
            lines += ['']
        for key, label in [('input_files', '输入文件'), ('output_files', '输出文件')]:
            lines += [f"- {label}：{'；'.join(file_text(v) for v in step.get(key, [])) or '无记录'}。"]
        if step.get('uncertainties'):
            lines += [f"- 待核实：{readable(step['uncertainties'])}。"]
        lines += ['', '画面证据：', '']
        for ident in step.get('evidence', []):
            asset = assets.get(ident)
            if not asset:
                lines += [f'- {text(ident)}：证据缺失。', '']
                continue
            role = evidence_roles(step, ident)
            lines += [f"{text(ident)} · {role} · {timestamp(asset['frame_no'], frames)}。", '',
                      '!' + link(ident, asset['path']), '']
    lines += ['## 待核对事项', '']
    if not open_issues:
        lines += ['无已登记的未解决事项。', '']
    for group, entries in [(None, open_issues), ('### 已解决事项', [i for i in issues if i.get('status') == 'resolved'])]:
        if group and entries:
            lines += [group, '']
        for issue in entries:
            state = {'open': '待补查', 'blocked': '等待补充材料', 'resolved': '已解决'}.get(issue.get('status'), '状态未知')
            lines += [f"#### {text(issue.get('id'))} · {state}", '', text(issue.get('question')), '',
                      f"关联步骤：{'、'.join(text(i) for i in issue_steps(issue, steps)) or '未记录'}。", '']
            if issue.get('start_frame') is not None:
                lines += [f"范围起点：{timestamp(issue['start_frame'], frames)}。", '',
                          f"范围终点：{timestamp(issue.get('end_frame'), frames)}。", '']
            else:
                lines += ['视频范围：未记录。', '']
            if issue.get('impact'):
                lines += [f"影响：{readable(issue['impact'])}", '']
            lines += ['已尝试补查：', '']
            attempts = issue.get('attempts') or []
            if not attempts:
                lines += ['- 尚无补查记录。']
            for attempt in attempts:
                if not isinstance(attempt, dict):
                    lines += [f'- {readable(attempt)}']
                    continue
                labels = {'action': '动作', 'new_information': '新信息', 'conclusion': '结论',
                          'original_time_range': '原始时间范围（秒）'}
                for key, value in attempt.items():
                    shown = references(value, assets) if key == 'evidence' and isinstance(value, list) else readable(value)
                    lines += [f"- {labels.get(key, text(key))}：{shown}"]
            if issue.get('status') != 'resolved':
                lines += ['', f"下一步：{readable(issue.get('next_action')) if issue.get('next_action') else '未记录具体动作；需围绕本项问题补充证据。'}"]
                if issue.get('needed_information'):
                    lines += [f"所需信息：{readable(issue['needed_information'])}"]
            elif issue.get('resolution'):
                lines += ['', f"解决依据：{readable(issue['resolution'])}"]
            if issue.get('evidence'):
                lines += ['', f"相关证据：{references(issue['evidence'], assets)}"]
            lines += ['']
    lines += audit_appendix(report)
    return '\n'.join(lines) + '\n'


def audit_appendix(report):
    """Keep the existing audit facts, with the full machine records linked alongside."""
    s, audit, result = report['status'], report['coverage_audit'], report['validation']
    rows = [('容器声明帧数', s['container_declared_frames']),
            ('已索引的可解码呈现帧数', s['video_total_frames']),
            ('容器声明与解码计数不一致（container_frame_count_mismatch；未知表示尚不可比较）', s['container_frame_count_mismatch']),
            ('程序计算检查', s['computed_frames']),
            ('粗审覆盖 / 精审覆盖（登记源帧范围长度）', f"{s['coarse_reviewed_frames_recorded']} / {s['fine_reviewed_frames_recorded']}"),
            ('已进行精审 / 已完成精审（区间帧数）', f"{s['fine_examined_frames_recorded']} / {s['fine_reviewed_frames_recorded']}"),
            ('候选操作单元', s['candidate_operation_units']),
            ('概览粒度去重源帧', s['recorded_overview_unique_frames']),
            ('候选帧 / 已登记查看 / 待查看', f"{s['candidate_frames']} / {s['candidates_reviewed_recorded']} / {s['candidates_pending']}"),
            ('模型视觉查看去重源帧（登记口径）', s['recorded_visual_unique_frames']),
            ('全帧计算完成（可解码呈现帧口径）', s['full_compute_complete']),
            ('选定候选审阅完成（登记口径）', s['selected_candidates_review_complete_recorded']),
            ('全部帧逐张视觉审阅完成（独立核实）', '未核实')]
    lines = ['## 附录：统计与审计', '',
             '完整记录：[review.json](review.json)；逐帧索引：[frames.jsonl](frames.jsonl)；'
             '遗漏审计：[omission-audit.json](omission-audit.json)。', '',
             '| 统计 | 当前记录 |', '|---|---|']
    lines += [f'| {label} | {readable(value)} |' for label, value in rows]
    for key, label in [('unprocessed_ranges', '未计算范围'),
                       ('source_frames_without_full_view_record_ranges', '待补充全图查看登记的源帧')]:
        lines += ['', f'{label}：{range_text(s[key])}。']
    tail = s['unindexed_tail']
    tail_text = f"自源帧 {text(tail.get('from_frame'))} 起，结束未知" if tail else '无（索引已完成）'
    lines += ['', f'未索引尾部：{tail_text}。']
    if audit.get('mode') == 'layered':
        lines += ['', '### 分层覆盖', '']
        for key, label in [('not_coarse_reviewed_ranges', '尚未粗审范围'),
                           ('not_fine_examined_ranges', '尚未进行精审'), ('not_fine_reviewed_ranges', '尚未完成精审')]:
            lines += [f'- {label}：{range_text(s[key])}。']
        lines += ['', f"复核状态：{text(audit['omission_review']['status'])}；记录层检查通过：{text(audit['review_gate_passed_recorded'])}。", '',
                  '区间、原始帧/状态映射、合并理由、抽查与字幕线索保存在 review.json；查看数量来自图片调用登记。', '']
        for item in report.get('intervals', []):
            entry = item['payload']
            lines.append(f"- {text(entry['id'])} 帧 {entry['start_frame']}–{entry['end_frame']}：{text(entry['phase'])}；"
                         f"{text(entry['disposition'])}；{text(entry['merge'])}；精审 {text(entry['fine_status'])}；{text(entry['reason'])}")
    else:
        coverage = audit['coverage']
        lines += ['', '### 操作遗漏检查', '',
                  f"不同连续画面状态：{coverage['state_count']}；有依据的状态说明：{len(coverage['accounted_state_frames'])}。", '',
                  f"可进入遗漏复核：{text(audit['records_ready_for_omission_review'])}；复核状态：{text(audit['omission_review']['status'])}。", '',
                  f"记录层遗漏检查通过：{text(audit['review_gate_passed_recorded'])}。", '',
                  f"未说明状态的代表帧：{readable(coverage['unaccounted_state_frames'])}。", '']
    lines += ['', '检查发现：', '']
    lines += [f"- {text(f['code'])}：{text(f['message'])}（建议复查帧 {readable(f['suggested_frames'])}）"
              for f in audit['findings']] or ['- 当前记录检查就绪。']
    lines += ['', '### 记录校验与审阅完成度', '',
              f"记录完整性：{'通过' if result['valid'] else '待修复'}（源文件、证据哈希与引用）。", '',
              f"审阅完成度：{'已完成' if result['review_complete'] else '待完成'}（候选查看及当前模式复核门禁）。", '',
              f"源身份检查：{text(result['source_verification']['method'])}；本次重新哈希：{text(result['source_verification']['rehashed'])}。", '', '错误：', '']
    lines += [f"- {text(e['code'])} · {text(e['reference'])}：{text(e['message'])}" for e in result['errors']] or ['- 无。']
    lines += ['', '警告：', '']
    lines += [f'- {text(warning)}' for warning in result['warnings']] or ['- 无。']
    return lines
