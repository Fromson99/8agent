"""Post-run source and execution audit. Never changes product input or calls a model."""
from common import *
import sqlite3, sys, collections
sys.path.insert(0, str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import (StageLedgerRecorder, identity_canonicalizer,
    grade_capture, build_run_artifact, build_experiment_artifact)

s=read(ART/'stage.json'); G=ROOT/s['base_release']['data_path']
def ro(p):
    db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro', uri=True)
    db.row_factory=sqlite3.Row
    return db
nav=ro(G/'navigation/navigation.sqlite'); source=ro(G/'store.sqlite')
def origin(sid):
    row=nav.execute('select json from source where id=?',(sid,)).fetchone()
    return json.loads(row[0]) if row else {}
def coord(v):
    a=v.get('article_coordinate') or {}; did=a.get('doc_id',v.get('document_id')); node=a.get('node',v.get('unit_id'))
    return {'doc_id':did,'node':int(node)} if did and str(node).isdigit() else None
def uniq(rows):
    return [json.loads(x) for x in sorted({json.dumps(x,sort_keys=True) for x in rows if x})]
def h(t): return hashlib.sha256(t.encode()).hexdigest()
def cited(v):
    if isinstance(v,list): return set().union(*(cited(x) for x in v))
    if isinstance(v,dict): return set(v.get('source_ids',[])).union(*(cited(x) for k,x in v.items() if k!='source_ids'))
    return set()
C=ROOT/s['roots']['candidate']
import importlib.util
# Load only the frozen reversible projection; no model or product context mutation.
spec=importlib.util.spec_from_file_location('semantic_runtime.legal_agent.audit_navigation_projection',C/'02_BACKEND/semantic_runtime/legal_agent/navigation_input.py')
projection=importlib.util.module_from_spec(spec);spec.loader.exec_module(projection)
expand=projection.expand_cards
def members_key(rows):
    return {(m['source_id'],str(p['block_id']),p['start_cp'],p['end_cp']) for m in rows for p in m['spans']}

observations={}; graded=[]; plans={}
for arm in s['arm_order']:
    P=ART/'known-query'/arm
    if not (P/'result.json').exists():
        if (ART/'stop.json').exists():
            rec=StageLedgerRecorder('known-query',arm,identity_canonicalizer)
            why='Not executed: preregistered provider/transport stop in preceding arm.'
            rec.record_stage('original_read','source',[],executed=False,skip_reason=why)
            rec.record_stage('final_cited','present',[],parent_stage_ids=['original_read'],executed=False,skip_reason=why)
            graded.append(grade_capture(rec.capture(),[]));plans[arm]=['original_read','final_cited']
        continue
    result=read(P/'result.json'); response=read(P/'response.json') if (P/'response.json').exists() else {}
    body=response.get('body',{}); allowed=read(P/'request.json')['json']['document_ids']
    events=[]; checks=[]; read_rows=[]
    for p in (P/'runtime').rglob('journal.sqlite'):
        db=ro(p)
        for row in db.execute('select seq,kind,payload_json from event order by seq'):
            events.append({'seq':row['seq'],'kind':row['kind'],'payload':json.loads(row['payload_json'])})
        for row in db.execute('select * from evidence_unit'):
            e=dict(row); spans=[dict(x) for x in db.execute('select * from evidence_span where evidence_id=? order by ordinal',(e['evidence_id'],))]
            valid=bool(spans)
            for span in spans:
                raw=source.execute('select text,source_artifact_sha256 from source_block where document_id=? and block_id=?',(e['document_id'],span['block_id'])).fetchone()
                valid=valid and bool(raw) and raw['source_artifact_sha256']==e['source_artifact_hash'] and h(raw['text'])==span['block_hash'] and raw['text'][span['start_cp']:span['end_cp']]==span['text'] and h(span['text'])==span['span_hash']
            valid=valid and h('\n'.join(x['text'] for x in spans))==e['text_hash']
            checks.append({'evidence_id':e['evidence_id'],'span_count':len(spans),'exact_original_match':bool(valid),'within_scope':e['document_id'] in allowed})
            o=origin(e['source_id'])
            read_rows.append({'evidence_id':e['evidence_id'],'source_id':e['source_id'],'canonical':coord(o),
                'document_name':o.get('document_name'),'heading':o.get('heading'),
                'spans':[{k:x[k] for k in ('block_id','start_cp','end_cp','span_hash')} for x in spans]})
        db.close()
    trace=[]
    for p in sorted((P/'model').glob('call-*/request.json')):
        raw=read(p); user=json.loads(next(x['content'] for x in raw['messages'] if x['role']=='user')); v=expand(user.get('view',{}))
        reply=read(p.with_name('response.json')) if p.with_name('response.json').exists() else {}
        try: proposal=json.loads(reply['choices'][0]['message']['content'])
        except (ValueError,KeyError,IndexError): proposal={'unavailable_or_invalid_output':True}
        refs=v.get('references',{})
        trace.append({'call':p.parent.name,'source_stage':v.get('source_stage',v.get('phase')),
            'source_count':len(v.get('sources',[])),'references':refs,
            'scope_choices':v.get('connection_scope_choices',[]),'selected_scope':v.get('selected_connection_scope'),
            'relation_groups':v.get('groups',[]),'proposal':proposal,
            'request_sha256':sha(p),'response_sha256':sha(p.with_name('response.json')) if p.with_name('response.json').exists() else None})
    catalogs=[]; selections=[]; selected=None
    scope_path=P/'scope-trace.jsonl'
    if scope_path.exists():
        for line in scope_path.open():
            event=json.loads(line); value=event['data']
            if event['kind']=='scope_selected':
                selected=value; selections.append(value)
            elif event['kind']=='catalog':
                keys=members_key(value['scope'] or [])
                expected=members_key(selected['members']) if selected else set()
                catalog_sources={g['anchor']['source_id'] for g in value['groups']}
                matches=any(keys==members_key(v['members']) and set(value['anchors']) <= {x[0] for x in members_key(v['members'])} for v in selections) and catalog_sources<=set(value['anchors'])
                catalogs.append({'seq':event['seq'],'selected_scope_id':selected['id'] if selected else None,
                    'exact_selected_scope':matches,'before_explicit_selection':selected is None,
                    'group_count':len(value['groups']),'anchors':value['anchors'],'scope':value['scope']})
    finalids=sorted(cited(body.get('answer',{}))); reads=uniq(x['canonical'] for x in read_rows); finals=uniq(coord(origin(x)) for x in finalids)
    rec=StageLedgerRecorder('known-query',arm,identity_canonicalizer)
    rec.record_stage('original_read','source',reads)
    rec.record_stage('final_cited','present',finals,parent_stage_ids=['original_read'],discard_reasons=[{'identity':x,'reason':'Read evidence not selected for final citation; this does not establish irrelevance or source absence.'} for x in reads if x not in finals])
    graded.append(grade_capture(rec.capture(),[])); plans[arm]=['original_read','final_cited']
    corpus=nav.execute('select count(*) from source where document_id in ('+','.join('?' for _ in allowed)+')',allowed).fetchone()[0]
    usage=result.get('usage',[])
    report={'native_result':result,'service_status':response.get('status'),'read_coordinates':reads,'final_coordinates':finals,'corpus_total':corpus,
        'source_checks':{'count':len(checks),'mismatches':sum(not x['exact_original_match'] for x in checks),'scope_violations':sum(not x['within_scope'] for x in checks)},
        'scope_selection_count':len(selections),'catalog_count':len(catalogs),'catalog_scope_violations':sum(not x['exact_selected_scope'] for x in catalogs),
        'preselection_catalog_count':sum(x['before_explicit_selection'] for x in catalogs),
        'model_seconds':sum(x.get('seconds',0) for x in usage),
        'usage':{k:sum(x.get(k,0) or 0 for x in usage) for k in ('input_tokens','output_tokens','cost_usd')},
        'outcome':body.get('assembly',{}).get('term_agent',{}).get('accepted_outcome',{'answer_status':body.get('answer_status'),'failure_reason':body.get('failure_reason')}),
        'answer':body.get('answer',{}).get('text',body.get('message','')),
        'observed_targets':{law: [x for x in read_rows if (x['document_name'] or '').split(' > ')[-1]==law and (x['heading'] or ' ').split('(')[0].strip().split(' ')[0]==article] for law,article in [('소득세법','제97조'),('소득세법 시행령','제163조')]}}
    save(P/'events-audit.json',events); save(P/'source-audit.json',{'checks':checks,'read_evidence':read_rows,'final_source_ids':finalids})
    save(P/'calls-audit.json',trace); save(P/'scope-audit.json',{'selections':selections,'catalogs':catalogs})
    (P/'answer.txt').write_text(report['answer']+'\n'); observations[arm]=report
ledger=build_experiment_artifact('ADR-1023','ADR-1023-experiment-v1',[build_run_artifact('run-001',graded,plans)])
save(ART/'retrieval-ledger.json',ledger)
save(ART/'observations.json',{'by_arm':observations,'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']})
print(json.dumps({arm:{k:v[k] for k in ('service_status','source_checks','scope_selection_count','catalog_count','catalog_scope_violations','preselection_catalog_count','usage','outcome')} for arm,v in observations.items()},ensure_ascii=False,indent=2))
nav.close(); source.close()
