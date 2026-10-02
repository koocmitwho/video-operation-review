"""Shape checks for authored records; these do not judge video semantics."""
import json


STEP_FIELDS = {'id': str, 'phase': str, 'start_frame': int, 'end_frame': int, 'software': str,
               'module': str, 'menu_path': list, 'selected_objects': list, 'final_parameters': dict,
               'confirmation_action': str, 'visible_result': str, 'input_files': list,
               'output_files': list, 'evidence': list, 'uncertainties': list, 'status': str}
MAX_FRAME_ORDINAL = 2 ** 63 - 1  # Frame IDs are bound to SQLite INTEGER queries.


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _strings(value):
    return isinstance(value, list) and all(_text(item) for item in value)


def evidence_references(value, path='record'):
    """Reject malformed evidence at every depth and retain extension fields."""
    refs = set()
    if isinstance(value, dict):
        for key, item in value.items():
            child = f'{path}.{key}'
            if key == 'evidence':
                if not _strings(item):
                    raise ValueError(f'{child}: must be an array of nonempty asset IDs.')
                refs.update(item)
            else:
                refs.update(evidence_references(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            refs.update(evidence_references(item, f'{path}[{index}]'))
    return refs


def _common(record, path):
    errors = []
    if not isinstance(record, dict):
        return [f'{path}: must be an object.']
    try:
        json.dumps(record, allow_nan=False)
        evidence_references(record, path)
    except (ValueError, TypeError) as exc:
        errors.append(f'{path}: {exc}')
    return errors


def check_step(step, path='step'):
    errors = _common(step, path)
    if not isinstance(step, dict):
        return errors
    for key, typ in STEP_FIELDS.items():
        if key not in step or type(step[key]) is not typ:
            errors.append(f'{path}.{key}: must be {typ.__name__}.')
    if errors:
        return errors
    if not _text(step['id']):
        errors.append(f'{path}.id: must be a nonempty string.')
    if not 0 <= step['start_frame'] <= step['end_frame'] <= MAX_FRAME_ORDINAL:
        errors.append(f'{path}.start_frame/end_frame: must be ordered integers in 0..{MAX_FRAME_ORDINAL}.')
    if step['status'] not in {'confirmed', 'partial', 'unresolved'}:
        errors.append(f'{path}.status: must be confirmed, partial or unresolved.')
    if step['status'] == 'confirmed' and step['uncertainties']:
        errors.append(f'{path}.status: 含待核对项的步骤请使用 partial 状态。')
    try:
        if evidence_references(step, path) - set(step['evidence']):
            errors.append(f'{path}.evidence: nested evidence must also be listed at step level.')
    except ValueError as exc:
        errors.append(str(exc))
    for key in ('author', 'input_action'):
        if key in step and not isinstance(step[key], str):
            errors.append(f'{path}.{key}: must be a string when supplied.')
    if 'role_evidence' in step:
        roles = step['role_evidence']
        if not isinstance(roles, dict):
            errors.append(f'{path}.role_evidence: must be an object.')
        else:
            for role, refs in roles.items():
                if not _strings(refs):
                    errors.append(f'{path}.role_evidence.{role}: must be an array of asset IDs.')
    if 'transition' in step:
        transition = step['transition']
        if not isinstance(transition, dict):
            errors.append(f'{path}.transition: must be an object.')
        else:
            for phase in ('before', 'after'):
                if phase not in transition:
                    continue  # Missing evidence remains an audit gap, not invented data.
                facts = transition[phase]
                field = f'{path}.transition.{phase}'
                if not isinstance(facts, dict):
                    errors.append(f'{field}: must be an object.')
                else:
                    for key, fact in facts.items():
                        if not _text(key) or not isinstance(fact, dict):
                            errors.append(f'{field}.{key}: must be a state fact object.')
            for role in ('confirmation', 'result'):
                if role not in transition:
                    continue
                item = transition[role]
                field = f'{path}.transition.{role}'
                if not isinstance(item, dict):
                    errors.append(f'{field}: must be an object.')
                else:
                    for key in ('status', 'note'):
                        if key in item and not isinstance(item[key], str):
                            errors.append(f'{field}.{key}: must be a string.')
                    # Unknown/non-observed strings remain inspectable audit gaps.
    return errors


def check_issue(issue, path='issue'):
    errors = _common(issue, path)
    if not isinstance(issue, dict):
        return errors
    for key in ('id', 'question'):
        if not _text(issue.get(key)):
            errors.append(f'{path}.{key}: must be a nonempty string.')
    if issue.get('status') not in ('open', 'blocked', 'resolved'):
        errors.append(f'{path}.status: must be open, blocked or resolved.')
    if not isinstance(issue.get('attempts'), list):
        errors.append(f'{path}.attempts: must be an array.')
    for key in ('start_frame', 'end_frame'):
        if key in issue and issue[key] is not None and (type(issue[key]) is not int or not 0 <= issue[key] <= MAX_FRAME_ORDINAL):
            errors.append(f'{path}.{key}: must be an integer in 0..{MAX_FRAME_ORDINAL}, or null.')
    if all(type(issue.get(key)) is int for key in ('start_frame', 'end_frame')) and issue['start_frame'] > issue['end_frame']:
        errors.append(f'{path}.start_frame/end_frame: must be ordered.')
    if 'step_ids' in issue and not _strings(issue['step_ids']):
        errors.append(f'{path}.step_ids: must be an array of step IDs.')
    if 'step_id' in issue and issue['step_id'] is not None and not _text(issue['step_id']):
        errors.append(f'{path}.step_id: must be a nonempty string or null.')
    return errors


def check_import_records(data):
    """One batch may update an old ID, but must not overwrite itself."""
    json.dumps(data, allow_nan=False)
    for table, check in (('steps', check_step), ('issues', check_issue)):
        seen = set()
        for index, entry in enumerate(data.get(table, [])):
            path = f'{table}[{index}]'
            errors = check(entry, path)
            if errors:
                raise ValueError('; '.join(errors))
            if entry['id'] in seen:
                raise ValueError(f'{path}.id: duplicate id {entry["id"]!r} within one import.')
            seen.add(entry['id'])


def record_contract_errors(conn):
    """Diagnose legacy bad rows without rewriting or dropping them."""
    errors = []
    for table, check, code in (('steps', check_step, 'invalid_step'), ('issues', check_issue, 'invalid_issue')):
        for row in conn.execute(f'SELECT id,payload FROM {table}'):
            path = f'{table}[id={row[0]!r}]'
            try:
                payload = json.loads(row[1])
                messages = check(payload, path)
                if isinstance(payload, dict) and payload.get('id') != row[0]:
                    messages.append(f'{path}.id: payload and stored ID differ.')
            except (ValueError, TypeError) as exc:
                messages = [f'{path}: {exc}']
            errors.extend(dict(code=code, reference=row[0], message=message) for message in messages)
    return errors


def record_contract_audit(base, mode):
    """A malformed authored payload cannot safely enter semantic/coverage routines."""
    errors = base.get('record_contract_errors', [])
    findings = [dict(code='record_contract_invalid', stage='records', message=e['message'],
                     reference=e['reference'], suggested_frames=[], original_time_range=None) for e in errors]
    return dict(audit_version=2 if mode == 'layered' else 1, mode=mode, snapshot=None,
                coverage={}, findings=findings, summary=dict(findings=len(findings), suggested_frame_count=0, queued_requests=0),
                suggested_frames=[], records_ready_for_omission_review=False,
                omission_review=dict(status='blocked_invalid_records', id=None),
                review_gate_passed_recorded=False, semantic_completeness_proven=False,
                assurance='Record structure invalid; fix the named fields before continuing the audit.')
