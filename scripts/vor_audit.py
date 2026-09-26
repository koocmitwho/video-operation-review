"""Omission-risk checks on recorded evidence. Never a proof that every semantic action was recovered."""
import hashlib
import json
import re

from vor_store import dump, evidence_references, get_meta, log_history, rebuild_candidates, validate


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _strings(value):
    return isinstance(value, list) and all(_nonempty(item) for item in value)


def check_aux_records(conn, data):
    """Reject malformed additions; semantic/reference gaps remain inspectable by audit."""
    seen = set()
    for entry in data.get('coverage', []):
        if not isinstance(entry, dict) or type(entry.get('frame_no')) is not int:
            raise ValueError('Coverage needs an integer representative frame_no.')
        n = entry['frame_no']
        if n in seen:
            raise ValueError(f'Duplicate coverage frame in one import: {n}')
        seen.add(n)
        frame = conn.execute('SELECT exact_start,digest FROM frames WHERE frame_no=?', (n,)).fetchone()
        if frame is None or frame['digest'] is None or frame['exact_start'] != n:
            raise ValueError(f'Coverage frame {n} must be a computed exact-run representative.')
        if entry.get('classification') not in {'operation', 'context', 'uncertain'}:
            raise ValueError('Coverage classification must be operation, context or uncertain.')
        if not all(_nonempty(entry.get(k)) for k in ['reason', 'reviewer']):
            raise ValueError('Coverage requires a specific reason and reviewer.')
        if not all(_strings(entry.get(k)) for k in ['step_ids', 'issue_ids', 'evidence']):
            raise ValueError('Coverage step_ids, issue_ids and evidence must be string arrays.')
        if not entry['evidence']:
            raise ValueError('Coverage requires actual evidence references.')
        if entry['classification'] == 'operation' and not entry['step_ids']:
            raise ValueError('Operation coverage requires at least one step ID.')
        if entry['classification'] == 'uncertain' and not entry['issue_ids']:
            raise ValueError('Uncertain coverage requires an issue ID.')
    for entry in data.get('omission_reviews', []):
        if not isinstance(entry, dict) or not all(_nonempty(entry.get(k)) for k in ['id', 'reviewer', 'note']):
            raise ValueError('Omission reviews require id, reviewer and a substantive note.')
        if entry.get('independence') not in {'independent', 'self_review'}:
            raise ValueError('Review independence must be independent or self_review.')
        if not isinstance(entry.get('snapshot'), str) or not re.fullmatch('[0-9a-f]{64}', entry['snapshot']):
            raise ValueError('Review needs the current audit snapshot SHA-256.')
        checked = entry.get('checked_state_frames')
        if not isinstance(checked, list) or not all(type(n) is int and n >= 0 for n in checked) or len(checked) != len(set(checked)):
            raise ValueError('checked_state_frames must contain distinct non-negative representative ordinals.')
        if not all(_strings(entry.get(k)) for k in ['evidence', 'issue_ids', 'tool_trace_refs']):
            raise ValueError('Review evidence, issue_ids and tool_trace_refs must be string arrays.')
        if not entry['tool_trace_refs'] or not entry['evidence']:
            raise ValueError('Review must cite actual image-tool calls and evidence; strings alone are not proof.')
        if entry.get('conclusion') not in {'no_additional_omissions_found', 'gaps_found', 'incomplete'}:
            raise ValueError('Invalid omission-review conclusion.')


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def content_snapshot(conn):
    """Bind the review to source content and annotations, excluding review/view append events."""
    h = hashlib.sha256()
    def add(value):
        h.update(_canonical(value).encode('utf-8') + b'\n')
    add({'audit_contract': 1})
    source = get_meta(conn, 'source', {})
    add({'source_sha256': source.get('sha256'), 'size': source.get('size'),
         'scan_config': get_meta(conn, 'scan_config'), 'total': get_meta(conn, 'video_total_frames'),
         'index_clean': get_meta(conn, 'index_complete_clean'), 'scan_clean': get_meta(conn, 'scan_complete_clean')})
    for row in conn.execute('SELECT frame_no,pts,pts_time,time_s,time_source,width,height,digest,exact_start '
                            'FROM frames ORDER BY frame_no'):
        add(dict(row))
    for table, ordering in [('steps', 'id'), ('issues', 'id'), ('coverage', 'frame_no')]:
        add(table)
        for row in conn.execute(f'SELECT payload FROM {table} ORDER BY {ordering}'):
            add(json.loads(row[0]))
    # New crops or redundant images do not change the authored content. Only cited assets are pinned.
    refs = set()
    for table in ['steps', 'issues', 'coverage']:
        for row in conn.execute(f'SELECT payload FROM {table}'):
            refs.update(evidence_references(json.loads(row[0])))
    for ident in sorted(refs):
        row = conn.execute('SELECT id,frame_no,kind,sha256,parent_id,crop FROM assets WHERE id=?', (ident,)).fetchone()
        add(dict(row) if row else {'missing_asset': ident})
    return h.hexdigest()


class EvidenceAudit:
    def __init__(self, conn):
        self.conn = conn
        self.findings = []
        self.frames = {r['frame_no']: dict(r) for r in conn.execute(
            'SELECT frame_no,time_s,exact_start,digest,width,height FROM frames ORDER BY frame_no')}
        self.states = {r['frame_no']: dict(r) for r in conn.execute(
            'SELECT exact_start AS frame_no,MAX(frame_no) AS end_frame,MIN(time_s) AS start_time,'
            'MAX(time_s) AS end_time FROM frames WHERE digest IS NOT NULL GROUP BY exact_start ORDER BY exact_start')}
        self.assets = {r['id']: dict(r) for r in conn.execute('SELECT * FROM assets')}
        self.views = [dict(r) for r in conn.execute('SELECT * FROM views')]
        self.seen = {v['asset_id'] for v in self.views if v['asset_id'] in self.assets and
                     v['asset_sha256'] == self.assets[v['asset_id']]['sha256'] and
                     v['frame_no'] == self.assets[v['asset_id']]['frame_no']}
        self.viewers = {}
        self.native_viewers = {}
        for v in self.views:
            asset = self.assets.get(v['asset_id'])
            if asset and v['asset_sha256'] == asset['sha256'] and v['frame_no'] == asset['frame_no']:
                self.viewers.setdefault(v['asset_id'], set()).add(v['actor'])
                if v.get('presentation','native') == 'native':
                    self.native_viewers.setdefault(v['asset_id'], set()).add(v['actor'])
        self.steps = {r['id']: json.loads(r['payload']) for r in conn.execute('SELECT * FROM steps')}
        self.issues = {r['id']: json.loads(r['payload']) for r in conn.execute('SELECT * FROM issues')}
        self.coverage = {r['frame_no']: json.loads(r['payload']) for r in conn.execute('SELECT * FROM coverage')}

    def finding(self, code, message, frames=(), stage='coverage', **extra):
        suggested = sorted({n for n in frames if n in self.frames and self.frames[n]['digest'] is not None})
        times = [self.frames[n]['time_s'] for n in suggested if self.frames[n]['time_s'] is not None]
        self.findings.append(dict(code=code, stage=stage, message=message, suggested_frames=suggested,
                                  original_time_range=[min(times), max(times)] if times else None, **extra))

    def state_context(self, n):
        state = self.states[n]
        return [n - 1, n, min(n + 1, state['end_frame']), state['end_frame'], state['end_frame'] + 1]

    def evidence(self, refs, owner, frames=(), stage='coverage'):
        okay = True
        for ident in refs:
            if ident not in self.assets:
                self.finding('audit_evidence_missing', f'{owner} 引用了不存在的证据 {ident}。', frames, stage, reference=owner)
                okay = False
            elif ident not in self.seen:
                self.finding('audit_evidence_unreviewed', f'{owner} 的证据 {ident} 尚无有效查看登记。', frames, stage, reference=owner)
                okay = False
        return okay

    def full_state_evidence(self, refs, state_frame, actor=None):
        for ident in refs:
            asset = self.assets.get(ident)
            if not asset or asset['kind'] != 'full' or ident not in self.seen:
                continue
            frame = self.frames.get(asset['frame_no'])
            if frame is None or frame['exact_start'] != state_frame:
                continue
            if (actor is None and self.native_viewers.get(ident)) or actor in self.native_viewers.get(ident, set()):
                return True
        return False

    def _asset_region(self, ident, ancestors=()):
        """Resolve a crop chain into source-image coordinates; malformed chains fail closed."""
        asset = self.assets.get(ident)
        if not asset or ident in ancestors:
            return None
        frame = self.frames.get(asset['frame_no'])
        if not frame or frame['digest'] is None:
            return None
        if asset['kind'] == 'full':
            width, height = frame['width'], frame['height']
            if asset['parent_id'] or type(width) is not int or type(height) is not int or min(width, height) <= 0:
                return None
            return (0, 0, width, height)
        parent = self.assets.get(asset['parent_id'])
        if asset['kind'] != 'crop' or not parent or parent['frame_no'] != asset['frame_no']:
            return None
        region = self._asset_region(parent['id'], (*ancestors, ident))
        try:
            box = json.loads(asset['crop'])
        except (TypeError, ValueError):
            return None
        if region is None or not isinstance(box, list) or len(box) != 4 or any(type(n) is not int for n in box):
            return None
        x0, y0, x1, y1 = box
        left, top, right, bottom = region
        if not (0 <= x0 < x1 <= right-left and 0 <= y0 < y1 <= bottom-top):
            return None
        return (left+x0, top+y0, left+x1, top+y1)

    def native_asset_covered(self, ident, refs, actor):
        """Require the whole role region, allowing only exact consecutive source-state equivalents."""
        target = self.assets.get(ident)
        if not target:
            return False
        target_frame = self.frames.get(target['frame_no'])
        region = self._asset_region(ident)
        for ref in refs:
            if actor not in self.native_viewers.get(ref, set()):
                continue
            if ref == ident:
                return True
            candidate = self.assets[ref]
            frame = self.frames.get(candidate['frame_no'])
            if not region or not target_frame or not frame or frame['digest'] is None or frame['exact_start'] != target_frame['exact_start']:
                continue
            covering = self._asset_region(ref)
            if covering and covering[0] <= region[0] and covering[1] <= region[1] and covering[2] >= region[2] and covering[3] >= region[3]:
                return True
        return False

    def review_trace_links(self, review):
        """Check recorded actor/asset/hash/frame links, not the truth of tool-call attestations."""
        evidence = set(review['evidence'])
        actual_traces = set()
        for view in self.views:
            asset = self.assets.get(view['asset_id'])
            if (asset and view['actor'] == review['reviewer'] and view['asset_id'] in evidence and
                    view['asset_sha256'] == asset['sha256'] and view['frame_no'] == asset['frame_no'] and
                    _nonempty(view['trace_ref']) and _nonempty(view['observation'])):
                actual_traces.add(view['trace_ref'])
        if not set(review['tool_trace_refs']) <= actual_traces:
            self.finding('review_trace_unlinked', '复核调用引用未关联该复核者的有效证据查看登记。', stage='review')

    def account_states(self):
        accounted, missing, uncertain = [], [], []
        for n, state in self.states.items():
            entry = self.coverage.get(n)
            context = self.state_context(n)
            if entry is None:
                missing.append(n)
                self.finding('unaccounted_state', f'源帧 {n} 开始的不同画面状态尚未说明其操作归属或无关原因。',
                             context, frame_no=n, state_end_frame=state['end_frame'])
                continue
            okay = self.evidence(entry['evidence'], f'coverage:{n}', context)
            if not self.full_state_evidence(entry['evidence'], n, actor=entry['reviewer']):
                self.finding('state_full_view_missing', f'状态 {n} 缺少登记者本人对本精确重复段原图的查看记录，裁剪或其他人的登记不能代替。',
                             context, frame_no=n)
                okay = False
            for ident in entry['step_ids']:
                step = self.steps.get(ident)
                if step is None:
                    self.finding('coverage_step_missing', f'状态 {n} 引用了缺失步骤 {ident}。', context, frame_no=n)
                    okay = False
                elif step['start_frame'] > state['end_frame'] or step['end_frame'] < n:
                    self.finding('coverage_step_outside_state', f'状态 {n} 与步骤 {ident} 的时间范围不相交。', context, frame_no=n)
                    okay = False
            for ident in entry['issue_ids']:
                if ident not in self.issues:
                    self.finding('coverage_issue_missing', f'状态 {n} 引用了缺失疑点 {ident}。', context, frame_no=n)
                    okay = False
            if entry['classification'] == 'uncertain':
                uncertain.append(n)
                self.finding('state_unresolved', f'状态 {n} 仍标为不确定；解决 issue 后还需更新状态判断。', context, frame_no=n)
            if okay:
                accounted.append(n)
            else:
                missing.append(n)
        return dict(state_count=len(self.states), accounted_state_frames=accounted,
                    unaccounted_state_frames=missing, uncertain_state_frames=uncertain,
                    states=list(self.states.values()))

    def step_transitions(self, linked_steps=None):
        last_values = {}
        previous_step = None
        linked = linked_steps if linked_steps is not None else {
            ident for entry in self.coverage.values() if entry['classification'] == 'operation' for ident in entry['step_ids']}
        for step in sorted(self.steps.values(), key=lambda s: (s['start_frame'], s['end_frame'], s['id'])):
            ident = step['id']
            frames = [step['start_frame'] - 1, step['start_frame'], step['end_frame'], step['end_frame'] + 1]
            if ident not in linked:
                self.finding('step_without_state', f'步骤 {ident} 尚未绑定到任何操作画面状态。', frames, 'continuity', step_id=ident)
            if not _nonempty(step.get('author')):
                self.finding('step_author_missing', f'步骤 {ident} 缺少 author，不能检查复核者与作者是否相同。', frames, 'continuity', step_id=ident)
            if step['status'] != 'confirmed' or step['uncertainties']:
                self.finding('step_unresolved', f'步骤 {ident} 尚有未解决项或不是 confirmed。', frames, 'continuity', step_id=ident)
            if previous_step and step['start_frame'] < previous_step['end_frame']:
                self.finding('step_ranges_overlap', f"步骤 {previous_step['id']} 与 {ident} 重叠，需明确执行先后。",
                             frames, 'continuity', step_id=ident)
            previous_step = step
            transition = step.get('transition')
            if not isinstance(transition, dict) or not all(k in transition for k in ['before', 'after', 'confirmation', 'result']):
                self.finding('step_transition_missing', f'步骤 {ident} 缺少结构化前后状态、确认或结果检查。', frames, 'continuity', step_id=ident)
                continue
            for phase in ['before', 'after']:
                facts = transition[phase]
                if not isinstance(facts, dict) or not facts:
                    self.finding('step_state_missing', f'步骤 {ident} 的 {phase} 状态为空；需记录相关对象/参数/文件的可见状态。', frames, 'continuity', step_id=ident)
                    continue
                for key, fact in facts.items():
                    if not _nonempty(key) or not isinstance(fact, dict) or 'value' not in fact or not _strings(fact.get('evidence')) or not fact['evidence']:
                        self.finding('state_fact_invalid', f'步骤 {ident} 的 {phase}.{key} 需要 value 和非空 evidence。', frames, 'continuity', step_id=ident)
                        continue
                    self.evidence(fact['evidence'], f'{ident}.{phase}.{key}', frames, 'continuity')
                    value = fact['value']
                    if value is None:
                        self.finding('state_value_unknown', f'步骤 {ident} 的 {key} 仍未知，不能据此声称状态衔接完整。', frames, 'continuity', step_id=ident)
                        continue
                    if phase == 'before' and key in last_values and _canonical(last_values[key]['value']) != _canonical(value):
                        prior = last_values[key]
                        self.finding('state_discontinuity',
                                     f"{key} 从步骤 {prior['step_id']} 的 {dump(prior['value'])} 跳到 {ident} 前的 {dump(value)}；需补充中间操作或修正记录。",
                                     [prior['end_frame'], step['start_frame']], 'continuity',
                                     state_key=key, previous_step=prior['step_id'], next_step=ident,
                                     previous_value=prior['value'], next_value=value)
                    last_values[key] = {'value': value, 'step_id': ident, 'end_frame': step['end_frame']}
                    if phase == 'after' and key in step['final_parameters']:
                        final = step['final_parameters'][key]
                        final = final.get('value') if isinstance(final, dict) else final
                        if final is not None and _canonical(final) != _canonical(value):
                            self.finding('final_parameter_mismatch', f'步骤 {ident} 的最终参数 {key} 与 after 状态不一致。', frames, 'continuity', step_id=ident)
            for role in ['confirmation', 'result']:
                item = transition[role]
                if not isinstance(item, dict) or item.get('status') not in {'observed', 'not_applicable'}:
                    self.finding(f'{role}_gap', f'步骤 {ident} 的 {role} 尚未直接确认或明确说明不适用。', frames, 'continuity', step_id=ident)
                    continue
                if not _nonempty(item.get('note')) or not _strings(item.get('evidence')):
                    self.finding(f'{role}_gap', f'步骤 {ident} 的 {role} 缺少说明或证据列表。', frames, 'continuity', step_id=ident)
                elif item['status'] == 'observed' and not item['evidence']:
                    self.finding(f'{role}_gap', f'步骤 {ident} 的 {role} 标为 observed，但没有证据。', frames, 'continuity', step_id=ident)
                else:
                    self.evidence(item['evidence'], f'{ident}.{role}', frames, 'continuity')

    def omission_review(self, snapshot):
        row = self.conn.execute('SELECT payload FROM omission_reviews ORDER BY recorded_at DESC,id DESC LIMIT 1').fetchone()
        if row is None:
            self.finding('omission_review_missing', '尚无针对当前记录的独立遗漏复核。', stage='review')
            return {'status': 'missing', 'id': None}
        review = json.loads(row[0])
        info = {'id': review['id'], 'reviewer': review['reviewer'], 'independence': review['independence']}
        if review['snapshot'] != snapshot:
            self.finding('omission_review_stale', '源证据或操作记录已改变，原遗漏复核快照过期。', stage='review')
            return dict(info, status='stale')
        problems = len(self.findings)
        authors = {s.get('author') for s in self.steps.values()} | {e['reviewer'] for e in self.coverage.values()}
        if review['independence'] != 'independent' or review['reviewer'] in authors:
            self.finding('reviewer_not_independent', '复核声明为自审或与记录作者同名；不能算作独立遗漏复核。', stage='review')
        if set(review['checked_state_frames']) != set(self.states):
            unchecked = sorted(set(self.states) - set(review['checked_state_frames']))
            self.finding('review_scope_incomplete', '遗漏复核未明确覆盖全部不同连续画面状态。', unchecked, 'review')
        self.evidence(review['evidence'], review['id'], stage='review')
        self.review_trace_links(review)
        reviewer_states = set()
        for ident in review['evidence']:
            asset = self.assets.get(ident)
            if asset and asset['kind'] == 'full' and review['reviewer'] in self.native_viewers.get(ident, set()):
                reviewer_states.add(self.frames[asset['frame_no']]['exact_start'])
        for n in self.states:
            if n not in reviewer_states:
                self.finding('reviewer_view_missing', f'复核者 {review["reviewer"]} 没有状态 {n} 的原图查看登记。',
                             self.state_context(n), 'review', frame_no=n)
        for ident in review['issue_ids']:
            issue = self.issues.get(ident)
            if issue is None or issue['status'] != 'resolved':
                self.finding('review_issue_unresolved', f'遗漏复核中的疑点 {ident} 尚未解决或不存在。', stage='review')
        if review['conclusion'] != 'no_additional_omissions_found':
            self.finding('review_not_complete', '遗漏复核尚未得到“未发现新增遗漏”的有界结论。', stage='review')
        passed = len(self.findings) == problems
        return dict(info, status='current_independent_review_recorded' if passed else 'needs_followup')


def audit_omissions(conn, work, queue=False, base_validation=None, mode=None):
    mode = mode or get_meta(conn, 'review_mode', 'layered')
    if mode == 'layered':
        from vor_layer_audit import audit_layers
        return audit_layers(conn, work, queue, base_validation)
    if mode != 'strict':
        raise ValueError('Audit mode must be layered or strict.')
    base = validate(conn, work) if base_validation is None else base_validation
    audit = EvidenceAudit(conn)
    s = base['status']
    if not base['valid']:
        audit.finding('record_consistency_failed', '先修复记录、图片或引用校验错误；不能据此计算完成。',
                      stage='records', validation_errors=base['errors'])
    if not s['full_compute_complete']:
        audit.finding('full_scan_incomplete', '全帧索引或计算尚未完整、干净结束。', stage='records',
                      unprocessed_ranges=s['unprocessed_ranges'], unindexed_tail=s['unindexed_tail'])
    coverage = audit.account_states()
    audit.step_transitions()
    for issue in s['unresolved_issues']:
        audit.finding('unresolved_issue', f"疑点 {issue['id']} 尚未解决：{issue['question']}",
                      [issue.get('start_frame'), issue.get('end_frame')], 'records', issue_id=issue['id'])
    ready = not audit.findings
    snapshot = content_snapshot(conn)
    review = audit.omission_review(snapshot)
    passed = ready and review['status'] == 'current_independent_review_recorded'
    suggested = sorted({n for finding in audit.findings for n in finding['suggested_frames']})
    queued = 0
    if queue and suggested:
        with conn:
            for finding in audit.findings:
                for n in finding['suggested_frames']:
                    before = conn.total_changes
                    conn.execute('INSERT OR IGNORE INTO requests VALUES (?,?,?)', (n, 'audit:' + finding['code'], 'audit'))
                    queued += conn.total_changes - before
            rebuild_candidates(conn)
            log_history(conn, 'audit_queue', {'snapshot': snapshot, 'frames': suggested})
    return {
        'audit_version': 1, 'mode': 'strict', 'snapshot': snapshot,
        'coverage': coverage, 'findings': audit.findings,
        'summary': {'state_count': coverage['state_count'], 'accounted_states': len(coverage['accounted_state_frames']),
                    'unaccounted_states': len(coverage['unaccounted_state_frames']), 'findings': len(audit.findings),
                    'suggested_frame_count': len(suggested), 'queued_requests': queued},
        'suggested_frames': suggested, 'records_ready_for_omission_review': ready,
        'omission_review': review, 'review_gate_passed_recorded': passed,
        'semantic_completeness_proven': False,
        'assurance': 'Recorded state accounting, consistency and review attestations only. '
                     'Names, traces and hashes do not prove independent agents, actual attention or semantic completeness.'
    }
