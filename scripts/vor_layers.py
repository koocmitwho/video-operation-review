"""Layered review planning and records; machine proposals never attest to human review."""
import hashlib
import json
import math
from pathlib import Path

from vor_store import (atomic_text, dump, evidence_references, get_meta, log_history, now,
                       rebuild_candidates, set_meta)


def payloads(conn, table):
    return [json.loads(r[0]) for r in conn.execute(f'SELECT payload FROM {table} ORDER BY id')]


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def state_rows(conn, start=0, end=None):
    # Group inside the requested range; retain original exact_start even when it precedes start.
    end = end if end is not None else 9223372036854775807
    return conn.execute('SELECT exact_start,MIN(frame_no) AS start_frame,MAX(frame_no) AS end_frame,'
                        'MIN(time_s) AS start_time,MAX(time_s) AS end_time,MAX(global_delta) AS global_delta,'
                        'MAX(max_local_delta) AS local_delta,MAX(changed_fraction) AS fraction,digest '
                        'FROM frames WHERE digest IS NOT NULL AND frame_no BETWEEN ? AND ? '
                        'GROUP BY exact_start ORDER BY MIN(frame_no)', (start,end))


def interval_mapping(conn, entry):
    return [dict(r) for r in state_rows(conn, entry['start_frame'], entry['end_frame'])]


def index_fingerprint(conn):
    h=hashlib.sha256()
    h.update(dump(get_meta(conn,'source',{})).encode('utf-8'))
    for row in conn.execute('SELECT frame_no,time_s,digest FROM frames ORDER BY frame_no'):
        h.update(dump(tuple(row)).encode('utf-8'))
    return h.hexdigest()


def prepare(conn, work=None, max_span=15.0, layout_fraction=0.12, stable_seconds=0.75):
    """Partition every computed frame. Limits bound local context, never total completion."""
    if not all(math.isfinite(x) and x > 0 for x in (max_span,layout_fraction,stable_seconds)):
        raise ValueError('Segmentation controls must be finite and positive.')
    config=dict(contract=1,max_span=max_span,layout_fraction=layout_fraction,stable_seconds=stable_seconds)
    key=canonical_hash([config,index_fingerprint(conn)])
    cached=get_meta(conn,'layer_plan_key')==key
    if not cached:
        proposals=[]; bucket=[]
        def flush():
            if not bucket: return
            first,last=bucket[0],bucket[-1]
            reps={first['start_frame'],last['end_frame']}
            changes=[s for s in bucket if (s['local_delta'] or 0)>0]
            if changes:
                reps.add(max(changes,key=lambda s:s['local_delta'])['start_frame'])
                reps.add(min(changes,key=lambda s:s['local_delta'])['start_frame'])
            # Returning to an earlier exact image is a retrace clue, not proof of cancellation.
            seen={}; retraces=[]
            for s in bucket:
                if s['digest'] in seen: retraces.append(s['start_frame'])
                seen[s['digest']]=s['start_frame']
            if retraces: reps.add(retraces[0])
            proposals.append(dict(id=f"P{first['start_frame']:09d}",start_frame=first['start_frame'],
                end_frame=last['end_frame'],start_time=first['start_time'],end_time=last['end_time'],
                state_ranges=[[s['start_frame'],s['end_frame'],s['exact_start']] for s in bucket],
                representative_frames=sorted(reps),status='proposed_unreviewed',
                reason='Contiguous change cluster; layout/dwell/context boundaries; weakest and strongest local changes retained.',
                boundary_clue=first.get('boundary_clue','start'),
                risk_clues={'distinct_states':len(bucket),'small_change_frames':[s['start_frame'] for s in changes if (s['fraction'] or 0)<0.01],
                            'retrace_frames':retraces,'one_frame_states':[s['start_frame'] for s in bucket if s['start_frame']==s['end_frame']]},
                merge='exact' if len(bucket)==1 else 'approximate_proposal',
                precision='overview only; native evidence is needed for operations and small text'))
            bucket.clear()
        previous=None
        for row in state_rows(conn):
            s=dict(row); reason=None
            if bucket:
                if s['start_frame']!=previous['end_frame']+1: reason='uncomputed gap'
                elif (s['fraction'] or 0)>=layout_fraction or (s['global_delta'] or 0)>=5.0: reason='layout/control surface change'
                elif previous['start_time'] is not None and previous['end_time']-previous['start_time']>=stable_seconds: reason='stable dwell exit'
                elif s['start_time'] is not None and bucket[0]['start_time'] is not None and s['start_time']-bucket[0]['start_time']>=max_span: reason='context duration bound'
                elif s['start_time'] is None and s['start_frame']-bucket[0]['start_frame']>=1200: reason='unknown-time ordinal context bound'
            if reason: flush()
            s['boundary_clue']=reason or 'start/continuation'
            bucket.append(s); previous=s
        flush()
        if not proposals: raise ValueError('No computed frames; scan first.')
        with conn:
            # Authored intervals/checks never overwritten by planning.
            log_history(conn,'layer_plan_previous',payloads(conn,'segments'))
            conn.execute('DELETE FROM segments')
            for p in proposals: conn.execute('INSERT INTO segments VALUES (?,?)',(p['id'],dump(p)))
            set_meta(conn,'layer_plan_key',key)
            set_meta(conn,'layer_plan_config',config)
    proposals=payloads(conn,'segments')
    with conn:
        conn.execute("DELETE FROM requests WHERE origin='automatic'")
        for p in proposals:
            for n in p['representative_frames']:
                conn.execute('INSERT OR IGNORE INTO requests VALUES (?,?,?)',(n,'layer_overview:'+p['id'],'automatic'))
        rebuild_candidates(conn)
        set_meta(conn,'review_mode','layered')
        set_meta(conn,'selection_config',dict(mode='layered',**config))
    plan=dict(version=1,segments=proposals,cache_reused=cached,config=config,index_fingerprint=key,
              machine_only=True,true_operation_count=None,
              uncomputed_ranges=_missing_computed(conn),
              unindexed_tail=None if get_meta(conn,'index_complete_clean') else 'unknown')
    if work: atomic_text(Path(work)/'layer-plan.json',json.dumps(plan,ensure_ascii=False,indent=2))
    return plan


def _missing_computed(conn):
    from vor_store import ranges
    return ranges(r[0] for r in conn.execute('SELECT frame_no FROM frames WHERE digest IS NULL ORDER BY frame_no'))


def _text(value): return isinstance(value,str) and bool(value.strip())
def _strings(value): return isinstance(value,list) and all(_text(x) for x in value)


def check_layer_records(conn,data):
    for key in ('intervals','interval_checks','layer_reviews','retire_intervals'):
        if key in data and not isinstance(data[key],list): raise ValueError(key+' must be an array.')
    for table in ('intervals','interval_checks','layer_reviews'):
        seen=set()
        for entry in data.get(table,[]):
            if not isinstance(entry,dict) or not _text(entry.get('id')) or entry['id'] in seen:
                raise ValueError('Records need unique nonempty IDs within each import.')
            seen.add(entry['id'])
            evidence_references(entry)
    for e in data.get('intervals',[]):
        if not all(type(e.get(k)) is int for k in ('start_frame','end_frame')) or not 0<=e['start_frame']<=e['end_frame']:
            raise ValueError('Interval bounds must be ordered source-frame ordinals.')
        count=conn.execute('SELECT COUNT(*) FROM frames WHERE digest IS NOT NULL AND frame_no BETWEEN ? AND ?',
                           (e['start_frame'],e['end_frame'])).fetchone()[0]
        if count!=e['end_frame']-e['start_frame']+1: raise ValueError('Interval includes uncomputed/unknown frames.')
        if not all(_text(e.get(k)) for k in ('phase','reason','reviewer')): raise ValueError('Interval needs phase, reason and reviewer.')
        if e.get('disposition') not in ('operation','context','uncertain'): raise ValueError('Invalid interval disposition.')
        if e.get('merge') not in ('none','exact','approximate'): raise ValueError('Invalid merge type.')
        if e.get('fine_status') not in ('not_reviewed','partial','reviewed'): raise ValueError('Invalid fine status.')
        if not all(_strings(e.get(k)) for k in ('evidence','step_ids','issue_ids')): raise ValueError('Interval references must be string arrays.')
        if e['disposition']=='operation' and not e['step_ids']: raise ValueError('Operation interval needs step IDs.')
        if e['disposition']=='uncertain' and not e['issue_ids']: raise ValueError('Uncertain interval needs issue IDs.')
    for e in data.get('interval_checks',[]):
        if not all(_text(e.get(k)) for k in ('interval_id','reviewer','scope_hash','reason')): raise ValueError('Check needs scope hash, interval, reviewer and reason.')
        if e.get('method') not in ('risk_and_random','exhaustive'): raise ValueError('Invalid sampling method.')
        if e.get('conclusion') not in ('clear','expand','incomplete'): raise ValueError('Invalid check conclusion.')
        if not _strings(e.get('evidence')) or not _strings(e.get('resolves',[])): raise ValueError('Check evidence/resolves must be arrays.')
    for e in data.get('layer_reviews',[]):
        if not all(_text(e.get(k)) for k in ('reviewer','snapshot','note')): raise ValueError('Review needs reviewer, snapshot and note.')
        if e.get('independence') not in ('independent','self_review'): raise ValueError('Invalid reviewer independence.')
        if not all(_strings(e.get(k)) for k in ('checked_interval_ids','evidence','tool_trace_refs','issue_ids')): raise ValueError('Review references must be arrays.')
        if not e['tool_trace_refs'] or not e['evidence']: raise ValueError('Review must cite actual viewed evidence and calls.')
        if e.get('conclusion') not in ('no_additional_omissions_found','gaps_found','incomplete'): raise ValueError('Invalid review conclusion.')
    if not _strings(data.get('retire_intervals',[])): raise ValueError('Retire intervals by ID.')
    if set(data.get('retire_intervals',[])) & {e['id'] for e in data.get('intervals',[])}:
        raise ValueError('Cannot retire and update same interval in one import.')


def import_layer_records(conn,data):
    for ident in data.get('retire_intervals',[]):
        row=conn.execute('SELECT payload FROM intervals WHERE id=?',(ident,)).fetchone()
        if row: log_history(conn,'retired_interval',json.loads(row[0]))
        conn.execute('DELETE FROM intervals WHERE id=?',(ident,))
    for table in ('intervals','interval_checks'):
        for entry in data.get(table,[]):
            entry=dict(entry)
            if table=='interval_checks':
                scope=conn.execute('SELECT payload FROM intervals WHERE id=?',(entry['interval_id'],)).fetchone()
                if scope is None: raise ValueError('Check refers to an unknown interval.')
                req=sample_requirements(conn,json.loads(scope[0]))
                if entry['scope_hash']!=req['scope_hash']: raise ValueError('Check scope hash is not current.')
                entry['source_scope_frames']=req['all_state_frames']
            if table=='interval_checks' and conn.execute('SELECT 1 FROM interval_checks WHERE id=?',(entry['id'],)).fetchone():
                old=conn.execute('SELECT payload FROM interval_checks WHERE id=?',(entry['id'],)).fetchone()[0]
                if json.loads(old)!=entry: raise ValueError('Checks are immutable; add a new ID and resolves reference.')
            conn.execute(f'INSERT INTO {table} VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(entry['id'],dump(entry)))
    for entry in data.get('layer_reviews',[]):
        conn.execute('INSERT INTO layer_reviews VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,recorded_at=excluded.recorded_at',
                     (entry['id'],dump(entry),now()))


def viewed_frames(conn,refs,actor,native=False,full=False):
    result=set()
    for ident in refs:
        sql=('SELECT a.frame_no,f.exact_start,a.kind,v.presentation FROM assets a JOIN views v ON a.id=v.asset_id '
             'JOIN frames f ON f.frame_no=a.frame_no WHERE a.id=? AND v.actor=? AND a.sha256=v.asset_sha256 AND a.frame_no=v.frame_no')
        for r in conn.execute(sql,(ident,actor)):
            if native and r['presentation']!='native': continue
            if full and r['kind']!='full': continue
            result.add(r['frame_no'])
    return result


def covered_targets(conn, targets, viewed):
    """Exact-run equivalence only; approximate groups never create evidence equivalence."""
    wanted=sorted(set(targets)|set(viewed)); states={}
    for offset in range(0,len(wanted),800):
        chunk=wanted[offset:offset+800]
        sql='SELECT frame_no,exact_start FROM frames WHERE digest IS NOT NULL AND frame_no IN ('+','.join('?' for _ in chunk)+')'
        states.update((r[0],r[1]) for r in conn.execute(sql,chunk))
    seen={states[n] for n in viewed if n in states}
    return {n for n in targets if n in states and states[n] in seen}


def coarse_ok(conn,entry):
    views=viewed_frames(conn,entry['evidence'],entry['reviewer'],full=True)
    bounds={entry['start_frame'],entry['end_frame']}
    return covered_targets(conn,bounds,views)==bounds


def fine_problems(conn,entry,steps,require_complete=True):
    errors=[]
    if entry['disposition']!='operation' or entry['fine_status']=='not_reviewed': return ['operation_not_fine_reviewed']
    if require_complete and entry['fine_status']!='reviewed': errors.append('operation_not_fine_reviewed')
    for ident in entry['step_ids']:
        s=steps.get(ident)
        if s is None: errors.append('interval_step_missing'); continue
        if not entry['start_frame']<=s['start_frame']<=s['end_frame']<=entry['end_frame']: errors.append('step_outside_interval')
        roles=s.get('role_evidence')
        if not isinstance(roles,dict) or any(not _strings(roles.get(k)) or not roles[k] for k in ('before','during','after')):
            errors.append('operation_roles_missing'); continue
        positions=[]
        for role in ('before','during','after'):
            refs=roles[role]
            if not set(refs)<=set(s['evidence']): errors.append('role_evidence_not_declared')
            seen=viewed_frames(conn,refs,s.get('author'),native=True)
            actual={r[0] for ref in refs for r in conn.execute('SELECT frame_no FROM assets WHERE id=?',(ref,))}
            if not actual or not actual<=seen: errors.append('operation_native_view_missing')
            if any(not s['start_frame']<=n<=s['end_frame'] for n in actual): errors.append('role_evidence_outside_step')
            positions.append(sorted(actual))
        if all(positions) and not max(positions[0])<=min(positions[1])<=max(positions[1])<=min(positions[2]): errors.append('operation_role_order')
        if require_complete and (s['status']!='confirmed' or s['uncertainties']): errors.append('operation_unresolved')
    return sorted(set(errors))


def union_spans(spans):
    result=[]
    for a,b in sorted(spans):
        if result and a<=result[-1][1]+1: result[-1][1]=max(result[-1][1],b)
        else: result.append([a,b])
    return result


def complement(spans,start,end):
    result=[]; cursor=start
    for a,b in union_spans(spans):
        if a>cursor: result.append([cursor,min(a-1,end)])
        cursor=max(cursor,b+1)
    if cursor<=end: result.append([cursor,end])
    return [x for x in result if x[0]<=x[1]]


def coverage_counts(conn):
    entries=payloads(conn,'intervals'); steps={s['id']:s for s in payloads(conn,'steps')}
    bounds=conn.execute('SELECT MIN(frame_no),MAX(frame_no) FROM frames').fetchone()
    coarse=union_spans([[e['start_frame'],e['end_frame']] for e in entries if coarse_ok(conn,e)])
    fine=union_spans([[e['start_frame'],e['end_frame']] for e in entries if coarse_ok(conn,e) and not fine_problems(conn,e,steps)])
    examined=union_spans([[e['start_frame'],e['end_frame']] for e in entries if coarse_ok(conn,e) and not fine_problems(conn,e,steps,require_complete=False)])
    total=lambda spans:sum(b-a+1 for a,b in spans)
    return dict(coarse_reviewed_frames_recorded=total(coarse),fine_reviewed_frames_recorded=total(fine),
                fine_examined_frames_recorded=total(examined),fine_examined_ranges=examined,
                not_fine_examined_ranges=complement(examined,*bounds) if bounds[0] is not None else [],
                coarse_reviewed_ranges=coarse,fine_reviewed_ranges=fine,
                not_coarse_reviewed_ranges=complement(coarse,*bounds) if bounds[0] is not None else [],
                not_fine_reviewed_ranges=complement(fine,*bounds) if bounds[0] is not None else [],
                candidate_operation_units=len({s for e in entries for s in e['step_ids']}),true_operation_count=None,
                approximate_merge_intervals=sum(e['merge']=='approximate' for e in entries))


def sample_requirements(conn,entry):
    rows=interval_mapping(conn,entry)
    # Pin source frames AND interpretation; retries or extra view events alone don't stale checks.
    steps={s['id']:s for s in payloads(conn,'steps') if s['id'] in entry['step_ids']}
    scope_hash=canonical_hash([get_meta(conn,'source',{}).get('sha256'),entry,rows,steps,payloads(conn,'language_sources')])
    interior=[r for r in rows if entry['start_frame']<r['start_frame']<entry['end_frame']]
    frames=set()
    if interior:
        frames.add(max(interior,key=lambda r:r['local_delta'] or 0)['start_frame'])
        small=[r for r in interior if (r['local_delta'] or 0)>0]
        if small: frames.add(min(small,key=lambda r:r['local_delta'])['start_frame'])
        frames.add(interior[int(scope_hash[:16],16)%len(interior)]['start_frame'])
    required=entry['merge']=='approximate' or entry['disposition']=='context'
    if required and not frames: frames.add(entry['start_frame'])
    return dict(interval_id=entry['id'],scope_hash=scope_hash,required=required,frames=sorted(frames),
                strategy='strongest local change + weakest nonzero local change + deterministic content-seeded sample',
                all_state_frames=[r['start_frame'] for r in rows],
                warning='Sample checks are bounded; unsampled small edits can remain. Expand on anomalies.')


def manifest(conn):
    entries=payloads(conn,'intervals')
    return dict(segments=payloads(conn,'segments'),intervals=[dict(e,state_mapping=interval_mapping(conn,e),
                sampling=sample_requirements(conn,e)) for e in entries],coverage=coverage_counts(conn),
                language_sources=payloads(conn,'language_sources'))


# Exposed here for the CLI, keeping image composition mechanics out of interval logic.
from vor_sheets import make_sheet, record_sheet_view
