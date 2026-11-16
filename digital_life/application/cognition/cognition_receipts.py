"""Committed cognition receipts, separate from the model's public explanation."""
def for_request(store, activity, request):
    row = store.db.execute(
        "SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='cognition.output_recorded' AND source_event_id=? ORDER BY event_seq DESC LIMIT 1",
        (store.instance_id, activity, request)).fetchone()
    if not row:
        return None
    value = store.read_artifact(row[0])
    if value.get('receipt_version') != 1:
        return None  # Historical events do not distinguish created from reused.
    created, reused, recalled = (len(value.get(key, [])) for key in
                                ('created', 'reused', 'suppressed_recall'))
    if not (created or reused or recalled):
        return None
    parts = []
    if created:
        parts.append(f'已记录 {created} 条未核实认知候选')
    if reused:
        parts.append(f'复用 {reused} 条已有认知记录')
    if recalled:
        parts.append(f'{recalled} 条提案仅引用已有认知，未重复新增')
    return {'source': 'committed-cognition-event', 'created': created,
            'reused': reused, 'suppressed_recall': recalled,
            'text': '系统记录回执：' + '；'.join(parts) + '。这不表示事实已获确认。'}
