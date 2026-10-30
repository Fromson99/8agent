"""Native RAG capture uses actual co-cited receipts; never adds a model call."""
from copy import deepcopy
import sqlite3
from .contracts import BasisUnavailable
from .contracts import digest
from .integration import selection,save_proposal,present


def has_approvals(pipeline,who):
    factory=getattr(pipeline,'basis_factory',None)
    if not factory:return False
    try:
        with factory() as service:
            return any(r['link']['status']=='APPROVED' and r['link']['kind']!='RELATED' for r in service.list(who)['items'])
    except (sqlite3.OperationalError,OSError,BasisUnavailable):
        # Source research may continue, but a failed authority lookup cannot
        # certify a cached route as having current approval dependencies.
        return True


def finish(pipeline,cases,result,who,body,envelope,work):
    factory=getattr(pipeline,'basis_factory',None)
    if not factory:return envelope
    parts=cases.parts(result['goal_id']) if result.get('goal_id') else {}
    claims=parts.get('COMPOSE',{}).get('payload',{}).get('claims',[])
    if not claims:claims=(result.get('answer') or {}).get('claims',[])
    from ..legal_agent.investigation_contracts import claim_evidence
    ids=[]
    try:
        with factory() as service:
            evidence=work.evidence()
            by={}
            for e in evidence:
                if e['document_id'] not in who['document_ids']:continue
                role=service.sources.catalogue[e['document_id']]['category']
                if role in ('internal','external'):by[e['evidence_id']]={**e,'side':role}
            for index,claim in enumerate(claims):
                cited=claim_evidence(claim);selected=[]
                for e in by.values():
                    if any(c['source_id']==e['source_id'] and c.get('quote') and any(c['quote'] in p['text'] for p in e['spans']) for c in cited):
                        selected.append(e)
                internal=[e for e in selected if e['side']=='internal'];external={}
                for e in selected:
                    if e['side']=='external':external.setdefault(e['document_id'],[]).append(e)
                if not internal:continue
                for did,ends in external.items():
                    payload={'request_id':'rag:'+envelope['run_id']+':'+digest([index,did]),
                        'internal':[selection(e) for e in internal],'external':[selection(e) for e in ends],
                        'kind':'BASIS','reason':'같은 답변 주장에 실제 인용된 내규·외규입니다. 법적 근거 관계 여부는 원문 검토와 사용자 승인이 필요합니다. 의견: '+claim['text'],
                        'provenance':{'type':'MODEL_OBSERVATION','method':'COCITED_CANDIDATE','run_id':envelope['run_id'],
                            'internal_refs':[e['evidence_id'] for e in internal],'external_refs':[e['evidence_id'] for e in ends]}}
                    saved=save_proposal(service,who,payload,by);ids.append(saved['link']['link_id'])
            # Include dependencies actually used, even without a co-cited claim.
            selection_state=parts.get('SELECT',{}).get('payload',{}).get('investigation_state',{})
            basis=selection_state.get('basis_links',{})
            ids.extend(row['link']['link_id'] for row in (basis.get('snapshot') or {}).get('items',[]))
    except (sqlite3.OperationalError,OSError,BasisUnavailable) as exc:
        return {**envelope,'basis_capture_status':'pending','basis_capture_error':type(exc).__name__}
    value={**envelope,'basis_link_ids':sorted(set(ids))}
    request={'workflow_id':'native_rag','principal':who,'document_ids':who['document_ids'],'as_of':body.get('as_of')}
    return present(pipeline,request,value)
