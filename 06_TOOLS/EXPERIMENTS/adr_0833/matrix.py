from pathlib import Path
from copy import deepcopy
import hashlib,json,resource,sys,time
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0833-compact-delivery-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'freeze.json');arm=sys.argv[1];assert arm in ('baseline','connected')
assert all(sha(R/n)==h for n,h in f['files'].items())
base=read(D/'baseline.json')['manifest'];code=R/(base['code_root'] if arm=='baseline' else f['code_root'])
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.legal_agent import bounded_source_session as bounded
from semantic_runtime.legal_agent.source_tools import canonical_evidence
from semantic_runtime.legal_agent.repository import text_hash
from semantic_runtime.legal_agent.completion_contracts import evidence_options
from semantic_runtime.legal_agent.gateway import compact_wire_view
from semantic_runtime.legal_agent.errors import ContractError
started=time.monotonic();rows=[]
for c in read(D/'cases.json'):
    unit=('😀' if c['unicode'] else '한')*c['length']
    text='\n\n'.join([unit]*c['lines']);start=19
    span={'block_id':'exact:block','start_cp':start,'end_cp':start+len(text),'text':text,'span_hash':text_hash(text),'block_hash':text_hash('P'*start+text)}
    origin={'source_id':'source:own','document_id':'doc:own','unit_id':'17','generation_id':'fixed-g','source_artifact_hash':'a'*64,'role':'reference','temporal_status':'unknown','metadata':{}}
    acquired=canonical_evidence(origin,[span]);source={**acquired,'text':text,'adopted_spans':[{**span,'evidence_id':acquired['evidence_id']}]}
    opts=evidence_options([source]);view={'source_stage':'memory-assess','sources':[{'source_id':origin['source_id'],'document_id':origin['document_id'],'evidence_refs':[o['id'] for o in opts]}],'evidence_options':opts}
    if c['rebound']:acquired['evidence_id']='Enew-current-request'
    if c['scope']=='foreign_document':acquired['document_id']='doc:other'
    if c['scope']=='foreign_source':acquired['source_id']='source:other'
    offered=[] if c['scope']=='unread' else [acquired]
    before=deepcopy((view,offered));rejected=False
    try:out=bounded.compact_assessment_evidence(view,offered) if hasattr(bounded,'compact_assessment_evidence') else []
    except ContractError:out=[];rejected=True
    assert (view,offered)==before
    expected={(o['source_id'],o['document_id'],o['block_id'],o['start_cp'],o['end_cp'],o['text']) for o in opts}
    actual={(e['source_id'],e['document_id'],s['block_id'],s['start_cp'],s['end_cp'],s['text']) for e in out for s in e['spans']}
    if c['scope']=='same':
        valid=not rejected and actual==expected and all(len(e['spans'])==1 for e in out)
        if out:
            durable={**view,'exact_evidence':[{'source_id':e['source_id'],'document_id':e['document_id'],'text':'\n'.join(s['text'] for s in e['spans']),'spans':e['spans']} for e in out]}
            wire=compact_wire_view(durable,'compose')
            valid=valid and 'exact_evidence' not in wire and wire['evidence_options']==opts
    else:valid=not out
    rows.append({'case_id':c['case_id'],'passed':bool(valid),'exact_spans':len(out),'rejected':rejected,'false_positive':c['scope']!='same' and bool(out)})
result={'arm':arm,'passed':sum(r['passed'] for r in rows),'total':len(rows),'false_positives':sum(r['false_positive'] for r in rows),'cases':rows,'elapsed_seconds':time.monotonic()-started,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'model_calls':0}
(A/'artifacts'/('matrix-'+arm+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='cases'}))
