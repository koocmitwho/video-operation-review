"""Read-only, bounded prioritization of existing pending native-image requests."""
import json
import math

from vor_store import asset_path, get_meta, ranges


def question_queue(conn, work, start=None, end=None, batch_size=8):
    """Return the next batch; recording actual views advances a later call.

    A time range changes ordering only. Its bounds are inclusive original
    timestamps of represented requests, including exact-run requests whose
    representative image precedes the range. No selection or view is authored.
    """
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError('batch_size must be a positive integer.')
    if (start is None) != (end is None):
        raise ValueError('Provide both start and end, or neither.')
    scoped = start is not None
    if scoped and (any(type(value) not in (int, float) or not math.isfinite(value)
                       for value in (start, end)) or start > end):
        raise ValueError('start and end must be finite ordered original timestamps.')

    # Match the existing candidate/status full-native-view rule. A crop,
    # overview, or nonconsecutive return to the same pixels cannot clear it.
    sql = (
        'SELECT c.*,f.time_s,f.pts,f.pts_time,f.time_source,a.id AS asset_id,a.path '
        'FROM candidates c JOIN frames f USING(frame_no) '
        'LEFT JOIN assets a ON a.id=(SELECT id FROM assets '
        'WHERE frame_no=c.frame_no AND kind="full" ORDER BY id LIMIT 1) '
        'WHERE NOT EXISTS (SELECT 1 FROM views v JOIN assets seen ON seen.id=v.asset_id '
        'WHERE v.frame_no=c.frame_no AND seen.kind="full" AND v.presentation="native") '
        'ORDER BY c.frame_no')
    pending = []
    requested_frames = set()
    for row in conn.execute(sql):
        entry = dict(row)
        entry['reasons'] = json.loads(entry['reasons'])
        entry['represented_requests'] = json.loads(entry['represented_requests'])
        requested_frames.update(entry['represented_requests'])
        pending.append(entry)

    original_times = {}
    if scoped:
        ordered = sorted(requested_frames)
        for offset in range(0, len(ordered), 900):
            chunk = ordered[offset:offset + 900]
            query = 'SELECT frame_no,time_s FROM frames WHERE frame_no IN (' + ','.join('?' for _ in chunk) + ')'
            original_times.update((row['frame_no'], row['time_s']) for row in conn.execute(query, chunk))

    for entry in pending:
        matched = sorted(n for n in entry['represented_requests']
                         if scoped and original_times.get(n) is not None
                         and start <= original_times[n] <= end)
        entry['in_requested_range'] = bool(matched)
        entry['matched_request_ranges'] = [
            dict(start_frame=first, end_frame=last,
                 start_time_s=original_times[first], end_time_s=original_times[last])
            for first, last in ranges(matched)]
    pending.sort(key=lambda entry: (not entry['in_requested_range'], entry['frame_no']))
    batch = pending[:batch_size]
    for entry in batch:
        entry['absolute_path'] = str(asset_path(work, entry['path'])) if entry['path'] else None

    return dict(
        source=get_meta(conn, 'source'), source_reverified=False,
        requested_range=dict(start=start, end=end) if scoped else None,
        total_pending=len(pending),
        range_pending=sum(entry['in_requested_range'] for entry in pending) if scoped else None,
        batch_size=batch_size, batch=batch, remaining_after_batch=len(pending) - len(batch),
        range_scope_is_not_full_review=True,
        candidate_pixel_equivalence='exact_consecutive_RGB_only',
        next_batch='Record actual full-native-image views, then request this queue again; no offset.')
