"""Recorded effective intervals are evidence, never inferred from filename/latest."""
from datetime import date
from .contracts import as_of,require


def applicability(repo,binding,day=None):
    day=as_of(day) or date.today().isoformat();rows=[]
    for end in binding['internal']+binding['external']:
        lineage=repo.lineage(end['document_id']) or {}
        # Unit-specific dates override document dates. Missing / transitional
        # provisions remain explicit and do not block ordinary source research.
        temporal=lineage.get('unit_effectivity',{}).get(str(end['unit_id']),lineage)
        start=temporal.get('effective_from');stop=temporal.get('effective_until')
        for v in (start,stop):as_of(v)
        status='UNKNOWN'
        if start:status='FUTURE' if day<start else 'IN_RECORDED_INTERVAL'
        if stop and day>=stop:status='EXPIRED'
        if temporal.get('transitional') and status=='IN_RECORDED_INTERVAL':status='TRANSITION_REVIEW'
        rows.append({'document_id':end['document_id'],'unit_id':end['unit_id'],'status':status,
            'effective_from':start,'effective_until':stop,'transitional':temporal.get('transitional')})
    return {'as_of':day,'items':rows,'priority_eligible':not any(r['status'] in ('FUTURE','EXPIRED') for r in rows),
            'legal_applicability_certified':False}


def validate_lineage(value):
    require(isinstance(value,dict) and all(isinstance(value.get(k),str) and value[k] for k in
        ('version_id','family_id','source_artifact_hash')),'BASIS_LINEAGE','판본·계열·원문 해시가 필요합니다.')
    for interval in [value,*value.get('unit_effectivity',{}).values()]:
        for k in ('effective_from','effective_until'):as_of(interval.get(k))
        if interval.get('effective_from') and interval.get('effective_until'):
            require(interval['effective_from']<interval['effective_until'],'BASIS_DATE','시행 기간이 역전되었습니다.')
