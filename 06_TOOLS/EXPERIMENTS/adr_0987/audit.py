"""Offline original-span/usage checks. No model, no product-context changes."""
from common import *
import sqlite3,gzip,collections,html
def db(path):
    value=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True);value.row_factory=sqlite3.Row;return value
selected=read(DES/'selected.json');G=ROOT/selected['release']['data_path'];source=db(G/'store.sqlite');nav=db(G/'navigation/navigation.sqlite')
def origin(sid):
    r=nav.execute('select json from source where id=?',(sid,)).fetchone();return json.loads(r[0]) if r else None
def coord(v):
    if not v:return None
    a=v.get('article_coordinate') or {};did=a.get('doc_id',v.get('document_id'));node=a.get('node',v.get('unit_id'))
    return {'doc_id':did,'node':int(node)} if did and str(node).isdigit() else None
def unique(values):return [json.loads(x) for x in sorted({json.dumps(v,sort_keys=True) for v in values if v})]
def ht(value):return hashlib.sha256(value.encode()).hexdigest()
def citations(value):
    out=set()
    if isinstance(value,dict):
        if isinstance(value.get('source_ids'),list):out.update(x for x in value['source_ids'] if isinstance(x,str))
        for v in value.values():out.update(citations(v))
    elif isinstance(value,list):
        for v in value:out.update(citations(v))
    return out
timings={}
for line in (ART/'console-run-001.txt').open():
    if not line.startswith('{'):continue
    try:v=json.loads(line)
    except ValueError:continue
    if v.get('event')=='session.prepare.timings':timings[v['run_id']]=v
rows=[]
for case in read(DES/'cases.json'):
 for arm in ['baseline','knowledge']:
    P=RUN/'agent_layer'/arm/case['id']
    if not (P/'result.json').exists():continue
    result=read(P/'result.json');response=read(P/'response.json') if (P/'response.json').exists() else {};body=response.get('body',{});answer=body.get('answer',{});allowed=set(read(P/'request.json')['document_ids'])
    ids=sorted(citations(answer));reads=[];checks=[];events=[];states=[];read_blocks=set()
    # A bounded source-only response has no structured claims but does display
    # original quotations. Count those separately, then include them in present.
    rendered=html.unescape(answer.get('text',''));quote_ids=[]
    for item in body.get('selection',{}).get('selected',[]):
        title=' > '.join(x.get('title','') for x in item.get('ancestors',[]))
        header='**확인한 원문: '+item.get('document_name','')+' · '+title+'**'
        if header in rendered:
            section=rendered.split(header,1)[1].split('**확인한 원문:',1)[0]
            lines=[line[2:] for line in section.splitlines() if line.startswith('> ')]
            if lines and all(line in item.get('text','') for line in lines):quote_ids.append(item['id'])
    all_ids=sorted(set(ids)|set(quote_ids))
    for name in result['journal_paths']:
        journal=db(ROOT/name)
        for row in journal.execute('select status,phase,state_revision,evidence_revision from run'):states.append(dict(row))
        for row in journal.execute('select * from evidence_unit'):
            e=dict(row);spans=[dict(x) for x in journal.execute('select * from evidence_span where evidence_id=? order by ordinal',(e['evidence_id'],))];v=origin(e['source_id']);valid=bool(spans)
            for s in spans:
                read_blocks.add((e['document_id'],str(s['block_id'])))
                raw=source.execute('select text,source_artifact_sha256 from source_block where document_id=? and block_id=?',(e['document_id'],s['block_id'])).fetchone()
                valid=valid and bool(raw) and raw['source_artifact_sha256']==e['source_artifact_hash'] and ht(raw['text'])==s['block_hash'] and raw['text'][s['start_cp']:s['end_cp']]==s['text'] and ht(s['text'])==s['span_hash']
            valid=valid and ht('\n'.join(s['text'] for s in spans))==e['text_hash']
            checks.append({'evidence_id':e['evidence_id'],'span_count':len(spans),'exact_match':bool(valid),'authorized':e['document_id'] in allowed})
            reads.append({'source_id':e['source_id'],'coordinate':coord(v),'document':(v or {}).get('document_name')})
        for row in journal.execute('select seq,kind,payload_json from event order by seq'):
            if any(t in row['kind'] for t in ['KNOWLEDGE','CORE_EVIDENCE','RECALL','REPAIR','REJECT','FAIL','LAW_QUERY','ASSESS']):
                events.append({'seq':row['seq'],'kind':row['kind'],'payload':json.loads(row['payload_json'])})
        journal.close()
    model_views=[];exposures=[]
    important={'cm-051':[('e20b06b32087ace0','129')],'cm-008':[('eae25aa6e8a83c58','97')],
               'cm-010':[('7687ac5d901e9a4a','112')],'cm-007':[('eae25aa6e8a83c58','96'),('3521c3aaa5a735fd','195')]}
    critical=[]
    for did,bid in important[case['id']]:
        text=source.execute('select text from source_block where document_id=? and block_id=?',(did,bid)).fetchone()[0]
        critical.append({'document_id':did,'block_id':bid,'text':text,'read_in_journal':(did,bid) in read_blocks,'model_inputs_containing_full_block':[]})
    for path in sorted((P/'canonical').glob('*.json.gz')):
        if '-output' in path.name:continue
        with gzip.open(path,'rt') as f:v=json.load(f)
        raw=json.dumps(v,ensure_ascii=False)
        def strings(x):
            if isinstance(x,str):yield x
            elif isinstance(x,dict):
                for y in x.values():yield from strings(y)
            elif isinstance(x,list):
                for y in x:yield from strings(y)
        all_text=list(strings(v))
        for item in critical:
            if any(item['text'] in text for text in all_text):item['model_inputs_containing_full_block'].append(path.name)
        model_views.append({'file':str(path.relative_to(ROOT)),'guidance_in_actual_input':'legal_review_guidance' in raw,'bytes':len(raw.encode())})
    usage=body.get('assembly',{}).get('term_agent',{}).get('legal_knowledge') or {}
    stat=body.get('execution_stats') or {};prepare=timings.get(body.get('run_id'),{})
    audit={'case_id':case['id'],'arm':arm,'status':result.get('status'),'http_status':result.get('http_status'),'has_answer':result.get('has_answer'),
      'model_calls':result['model_calls'],'seconds':result['seconds'],'model_seconds':stat.get('llm_duration_ms',0)/1000,
      'prepare_seconds':prepare.get('elapsed_ms',0)/1000,'prepare_timing_recorded':bool(prepare),
      'seconds_excluding_prepare':result['seconds']-prepare.get('elapsed_ms',0)/1000,
      'read_coordinates':unique(x['coordinate'] for x in reads),'final_coordinates':unique(coord(origin(s)) for s in all_ids),
      'final_structured_claim_coordinates':unique(coord(origin(s)) for s in ids),
      'final_verbatim_quote_coordinates':unique(coord(origin(s)) for s in quote_ids),
      'citation_basis':'Union of structured claim source IDs and exact displayed original quotation blocks; quote-only response is not an answered conclusion',
      'unmapped_citations':[s for s in all_ids if origin(s) is None],'span_checks':checks,'states':states,'knowledge_usage':usage,
      'model_views':model_views,'knowledge_route_bound':sum(e['kind']=='KNOWLEDGE_SOURCE_ROUTE_BOUND' for e in events),
      'core_route_used':sum(e['kind']=='CORE_EVIDENCE_ROUTE_USED' for e in events),'events':events,'read_sources':reads,
      'critical_source_exposure':critical,'read_block_count':len(read_blocks),
      'answer_quality':'SEPARATE_MANUAL_REVIEW_REQUIRED','scope':'Offers, actual source route use and final citations are distinct; not a model internal reasoning explanation'}
    put(P/'audit.json',audit);rows.append({k:v for k,v in audit.items() if k not in ['events','read_sources','model_views','states','span_checks','knowledge_usage']})
    print(case['id'],arm,'read',len(audit['read_coordinates']),'cite',len(audit['final_coordinates']),'route',audit['core_route_used'],'model',result['model_calls'])
put(RUN/'audit-summary.json',rows);source.close();nav.close()
