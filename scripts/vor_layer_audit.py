"""Audit interval coverage, operation evidence, sampled merges and bounded omission reviews."""
import json
from vor_store import get_meta, log_history, rebuild_candidates, validate
from vor_audit import EvidenceAudit, content_snapshot
from vor_layers import (canonical_hash, coarse_ok, complement, covered_targets, coverage_counts,
                        fine_problems, interval_mapping, payloads, sample_requirements, viewed_frames)


def audit_layers(conn,work,queue=False,base_validation=None):
    base=validate(conn,work) if base_validation is None else base_validation
    audit=EvidenceAudit(conn); status=base['status']
    entries=sorted(payloads(conn,'intervals'),key=lambda e:(e['start_frame'],e['end_frame'],e['id']))
    checks=payloads(conn,'interval_checks'); entries_by_id={e['id']:e for e in entries}
    if not base['valid']: audit.finding('record_consistency_failed','记录或证据文件校验失败。',stage='records',validation_errors=base['errors'])
    if not status['full_compute_complete']:
        audit.finding('full_scan_incomplete','全帧索引/计算尚未完整；未处理尾部不能被区间声明覆盖。',stage='records',
                      unprocessed_ranges=status['unprocessed_ranges'],unindexed_tail=status['unindexed_tail'])
    end=max(audit.frames,default=-1)
    spans=[[e['start_frame'],e['end_frame']] for e in entries]
    for a,b in complement(spans,0,end):
        audit.finding('interval_gap',f'帧 {a}–{b} 尚无粗审区间归属。',[a,b],start_frame=a,end_frame=b)
    furthest=-1
    for entry in entries:
        if entry['start_frame']<=furthest:
            audit.finding('interval_overlap',f"区间 {entry['id']} 与已有区间重叠，需要拆分或退役旧区间。",[entry['start_frame']],interval_id=entry['id'])
        furthest=max(furthest,entry['end_frame'])
    requirements={}; valid_resolutions=set()
    check_by_id={c['id']:c for c in checks}
    for e in entries:
        ident=e['id']; bounds=[e['start_frame'],e['end_frame']]
        audit.evidence(e['evidence'],ident,bounds)
        if not coarse_ok(conn,e):
            audit.finding('interval_overview_missing',f'区间 {ident} 缺少本审阅者的首尾代表全画面（可概览）查看登记。',bounds,interval_id=ident)
        mapping=interval_mapping(conn,e)
        if e['merge']=='exact' and len(mapping)>1:
            audit.finding('false_exact_merge',f'区间 {ident} 含不同 RGB 状态，不能称为精确重复。',bounds,interval_id=ident)
        if e['merge']=='none' and len(mapping)>1 and e['disposition']!='operation':
            audit.finding('merge_reason_missing',f'区间 {ident} 合并多个非操作状态却未声明 approximate。',bounds,interval_id=ident)
        for issue in e['issue_ids']:
            if issue not in audit.issues: audit.finding('interval_issue_missing',f'{ident} 引用了不存在的疑点 {issue}。',bounds)
        if e['disposition']=='uncertain': audit.finding('interval_uncertain',f'区间 {ident} 的操作意图/内容仍不确定。',bounds)
        if e['disposition']=='operation':
            for code in fine_problems(conn,e,audit.steps):
                audit.finding(code,f'区间 {ident} 的操作精审仍有缺口：{code}。',bounds,stage='fine',interval_id=ident)
            # Every factual step reference needs author-native viewing, not just role thumbnails.
            for sid in e['step_ids']:
                step=audit.steps.get(sid)
                if not step: continue
                for ref in step['evidence']:
                    if not viewed_frames(conn,[ref],step.get('author'),native=True):
                        audit.finding('operation_native_view_missing',f'步骤 {sid} 的 {ref} 无作者本人原图/裁剪查看登记。',bounds,stage='fine')
                if (step['input_files'] or step['output_files']) and not any(
                    key.startswith('file:') for phase in ('before','after') for key in step.get('transition',{}).get(phase,{})):
                    audit.finding('file_handoff_state_missing',f'步骤 {sid} 需使用共享 file: 状态键记录输入输出交接。',bounds,stage='continuity')
        req=sample_requirements(conn,e); requirements[ident]=req
        relevant=[c for c in checks if c['interval_id']==ident]
        current=[c for c in relevant if c['scope_hash']==req['scope_hash']]
        valid=[]
        for c in current:
            targets=set(req['all_state_frames'] if c['method']=='exhaustive' else req['frames'])
            seen=viewed_frames(conn,c['evidence'],c['reviewer'],native=True,full=True)
            okay=targets<=covered_targets(conn,targets,seen)
            audit.evidence(c['evidence'],c['id'],req['frames'],stage='sampling')
            if not okay:
                audit.finding('sample_evidence_incomplete',f"抽查 {c['id']} 缺少本人的风险/随机样本原图查看；概览不能代替。",sorted(targets),stage='sampling')
            elif c['conclusion']=='clear':
                valid.append(c)
                for ref in c.get('resolves',[]):
                    old=check_by_id.get(ref)
                    prior=set(old.get('source_scope_frames',[])) if old else set()
                    if c['method']!='exhaustive' or not old or old['conclusion']!='expand' or not prior or not prior<=covered_targets(conn,prior,seen):
                        audit.finding('expansion_scope_incomplete',f"抽查 {c['id']} 未穷尽查看被引用异常 {ref} 的原范围。",sorted(prior),stage='sampling')
                    else: valid_resolutions.add(ref)
        if relevant and not current and any(c['scope_hash']!=req['scope_hash'] for c in relevant):
            audit.finding('interval_sample_stale',f'区间 {ident} 的旧抽查已过期；需当前范围复核。',req['frames'],stage='sampling')
        if req['required'] and not current:
            audit.finding('interval_sample_missing',f'合并/低优先级区间 {ident} 尚未完成风险与随机抽查。',req['frames'],stage='sampling')
        elif req['required'] and not valid and not any(c['conclusion']=='expand' for c in current):
            audit.finding('interval_sample_incomplete',f'区间 {ident} 抽查尚未完成。',req['frames'],stage='sampling')
        resolved=valid_resolutions
        for c in relevant:
            if c['conclusion']=='expand' and c['id'] not in resolved:
                audit.finding('sample_requires_expansion',f"抽查 {c['id']} 发现异常；展开区间 {ident} 并补充步骤/疑点，穷尽复查后才能关闭。",
                              [e['start_frame']-1,*req['all_state_frames'],e['end_frame']+1],stage='sampling',interval_id=ident)
    # Retiring an interval cannot silently discard an anomaly.
    retired_resolved=valid_resolutions
    for c in checks:
        if c['interval_id'] not in entries_by_id and c['conclusion']=='expand' and c['id'] not in retired_resolved:
            audit.finding('retired_interval_anomaly',f"被退役的区间仍有异常抽查 {c['id']} 未处理。",stage='sampling')
    linked={s for e in entries if e['disposition']=='operation' for s in e['step_ids']}
    audit.step_transitions(linked)
    for issue in status['unresolved_issues']:
        audit.finding('unresolved_issue',f"疑点 {issue['id']} 尚未解决：{issue['question']}",[issue.get('start_frame'),issue.get('end_frame')],stage='records')
    ready=not audit.findings
    snapshot=canonical_hash([content_snapshot(conn),entries,checks,payloads(conn,'language_sources')])
    review=_review(conn,audit,entries,requirements,snapshot)
    suggested=sorted({n for f in audit.findings for n in f['suggested_frames']})
    queued=0
    if queue and suggested:
        with conn:
            for f in audit.findings:
                for n in f['suggested_frames']:
                    before=conn.total_changes
                    conn.execute('INSERT OR IGNORE INTO requests VALUES (?,?,?)',(n,'layer_audit:'+f['code'],'audit'))
                    queued+=conn.total_changes-before
            rebuild_candidates(conn)
            log_history(conn,'layer_audit_queue',dict(snapshot=snapshot,frames=suggested))
    counts=coverage_counts(conn)
    return dict(audit_version=2,mode='layered',snapshot=snapshot,coverage=dict(counts,interval_count=len(entries)),
                interval_mapping=[dict(id=e['id'],state_ranges=interval_mapping(conn,e),sample_requirements=requirements[e['id']]) for e in entries],
                findings=audit.findings,summary=dict(intervals=len(entries),**counts,findings=len(audit.findings),suggested_frame_count=len(suggested),queued_requests=queued),
                suggested_frames=suggested,records_ready_for_omission_review=ready,omission_review=review,
                review_gate_passed_recorded=ready and review['status']=='current_independent_review_recorded',
                semantic_completeness_proven=False,assurance='Interval coverage and bounded sample/evidence consistency only; actual attention and semantic completeness are not proven.')


def _review(conn,audit,entries,requirements,snapshot):
    row=conn.execute('SELECT payload FROM layer_reviews ORDER BY recorded_at DESC,id DESC LIMIT 1').fetchone()
    if row is None:
        audit.finding('omission_review_missing','尚无当前分层记录的遗漏复核。',stage='review')
        return dict(status='missing',id=None)
    r=json.loads(row[0]); info={k:r[k] for k in ('id','reviewer','independence')}
    if r['snapshot']!=snapshot:
        audit.finding('omission_review_stale','区间/操作/抽查/语言线索已变化，复核快照过期。',stage='review')
        return dict(info,status='stale')
    before=len(audit.findings)
    authors={s.get('author') for s in audit.steps.values()}|{e['reviewer'] for e in entries}
    if r['independence']!='independent' or r['reviewer'] in authors:
        audit.finding('reviewer_not_independent','这是自审或与作者同名；不能算独立遗漏复核。',stage='review')
    if set(r['checked_interval_ids'])!={e['id'] for e in entries}:
        audit.finding('review_scope_incomplete','复核未覆盖所有粗审区间。',stage='review')
    audit.evidence(r['evidence'],r['id'],stage='review')
    seen=viewed_frames(conn,r['evidence'],r['reviewer'],full=True)
    native=viewed_frames(conn,r['evidence'],r['reviewer'],native=True,full=True)
    for e in entries:
        bounds={e['start_frame'],e['end_frame']}
        targets=set(requirements[e['id']]['frames']) if requirements[e['id']]['required'] else set()
        # Review final/before/critical role evidence natively, not every RGB state.
        role_targets=set(); role_assets=set()
        for sid in e['step_ids']:
            step=audit.steps.get(sid,{})
            for refs in step.get('role_evidence',{}).values():
                for ref in refs:
                    asset=audit.assets.get(ref)
                    if asset:
                        role_targets.add(asset['frame_no'])
                        role_assets.add(ref)
        if bounds-covered_targets(conn,bounds,seen) or targets-covered_targets(conn,targets,native):
            audit.finding('reviewer_view_missing',f"复核者尚缺区间 {e['id']} 的代表画面或抽查原图。",bounds|targets,stage='review')
        if any(not audit.native_asset_covered(ref,r['evidence'],r['reviewer']) for ref in role_assets):
            audit.finding('reviewer_fine_view_missing',f"复核者尚缺 {e['id']} 的操作角色精审证据。",role_targets,stage='review')
    audit.review_trace_links(r)
    for issue in r['issue_ids']:
        if issue not in audit.issues or audit.issues[issue]['status']!='resolved':
            audit.finding('review_issue_unresolved','复核仍有缺失/未解决疑点 '+issue,stage='review')
    if r['conclusion']!='no_additional_omissions_found': audit.finding('review_not_complete','复核仍未完成。',stage='review')
    return dict(info,status='current_independent_review_recorded' if len(audit.findings)==before else 'needs_followup')
