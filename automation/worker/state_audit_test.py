from __future__ import annotations

import json
from detail_enrichment_test import build_d1


def main() -> int:
    d1 = build_d1()

    settings = d1.query("SELECT key,value FROM settings WHERE key IN ('event_creation_enabled','scheduler_enabled','production_status','next_event_id','event_id_counter_status') ORDER BY key").rows
    events = d1.query("SELECT event_id,title,publish,editorial_state,review_state,origin_ref,created_at,created_by,note FROM events ORDER BY event_id").rows
    terms = d1.query("SELECT term_id,event_id,date_from,date_to,term_state,is_active FROM terms ORDER BY event_id,date_from,term_id").rows
    findings = d1.query("SELECT finding_id,status,event_id,resolution,resolved_at,resolved_by FROM findings WHERE event_id IS NOT NULL OR status='RESOLVED' ORDER BY event_id,finding_id").rows
    requests = d1.query("SELECT request_id,operation,entity_type,entity_id,status,started_at,finished_at,actor,error FROM requests ORDER BY started_at,request_id").rows
    runs = d1.query("SELECT run_id,run_type,status,started_at,finished_at,created_events,error_count,actor,note FROM runs ORDER BY started_at,run_id").rows
    autos = d1.query("SELECT event_id,title,run_id,auto_updated_at FROM event_auto ORDER BY event_id").rows

    details = []
    for event in events:
        eid = int(event['event_id'])
        origin_ref = event.get('origin_ref')
        details.append({
            'event': event,
            'terms': [t for t in terms if int(t['event_id']) == eid],
            'event_auto': next((a for a in autos if int(a['event_id']) == eid), None),
            'origin_finding': next((f for f in findings if f.get('finding_id') == origin_ref), None),
            'requests_for_event': [r for r in requests if str(r.get('entity_id') or '') == str(eid)],
            'runs_for_event': [r for r in runs if str(eid).zfill(6) in str(r.get('run_id') or '')],
        })

    anomalies = []
    for d in details:
        event = d['event']
        eid = event['event_id']
        if not d['terms']:
            anomalies.append({'event_id': eid, 'type': 'NO_TERMS'})
        if not d['event_auto']:
            anomalies.append({'event_id': eid, 'type': 'NO_EVENT_AUTO'})
        if event.get('origin_ref') and not d['origin_finding']:
            anomalies.append({'event_id': eid, 'type': 'ORIGIN_FINDING_MISSING', 'origin_ref': event.get('origin_ref')})
        for req in d['requests_for_event']:
            if req.get('status') != 'SUCCESS':
                anomalies.append({'event_id': eid, 'type': 'NON_SUCCESS_REQUEST', 'request': req})
        for run in d['runs_for_event']:
            if run.get('status') != 'SUCCESS':
                anomalies.append({'event_id': eid, 'type': 'NON_SUCCESS_RUN', 'run': run})

    print(json.dumps({
        'ok': True,
        'mode': 'STATE_AUDIT_READ_ONLY',
        'read_only': True,
        'settings': settings,
        'counts': {
            'events': len(events),
            'terms': len(terms),
            'event_auto': len(autos),
            'linked_findings': len(findings),
            'requests': len(requests),
            'runs': len(runs),
            'anomalies': len(anomalies),
        },
        'event_details': details,
        'anomalies': anomalies,
        'writes_performed': False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
