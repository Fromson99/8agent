"""Read-only post-run audit; no model calls and no product input changes."""
from pathlib import Path
import hashlib, json, sqlite3, sys
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0925-source-lead-exact-observation';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());hashtext=lambda s:hashlib.sha256(s.encode()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def connect(p):
    db=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
release=read(D/'baseline.json')['manifest'];G=R/release['data_path']
source=connect(G/'store.sqlite');navigation=connect(G/'navigation/navigation.sqlite')
for case in read(D/'cases.json'):
    if len(sys.argv)>2 and case['id']!=sys.argv[2]:continue
    O=A/'artifacts/run-001'/sys.argv[1]/case['id']
    if not (O/'result.json').exists():continue
    run=read(O/'result.json');body=read(O/'response.json').get('body',{}) if (O/'response.json').exists() else {}
    summary={'case_id':case['id'],'result':{k:v for k,v in run.items() if k!='usage'},
             'rows':len(body.get('report',{}).get('rows',[])), 'unreviewed_sources':body.get('unreviewed_sources',[]), 'field_rows':body.get('comparison_items',{}).get('items',[]), 'attempts':body.get('research_attempts',{}),'evidence_summary':body.get('evidence_summary'),
             'evidence_refs':body.get('evidence_refs',[]),'error_code':body.get('error_code'),
             'resume_available':body.get('resume_available'),'unresolved':body.get('unresolved'),
             'children':{},'calls':[],'errors':[],'evidence_span_checks':[]}
    answer=body.get('answer',{});text=answer.get('text','') if isinstance(answer,dict) else str(answer)
    (O/'answer.txt').write_text(text+'\n')
    maps={};journals=[]
    for path in sorted((O/'runtime').rglob('journal.sqlite')):
        side=next((s for s in ('internal','external') if s in path.parts),'parent')
        db=connect(path);evidence={};checks=[];spans_by_id={}
        for row in db.execute('select * from evidence_unit'):
            e=dict(row);meta=json.loads(e.pop('metadata_json'));sid=e['source_id']
            nav=navigation.execute('select json from source where id=?',(sid,)).fetchone()
            origin=json.loads(nav[0]) if nav else None
            canonical={'doc_id':origin['document_id'],'node':int(origin['unit_id'])} if origin and origin.get('unit_id') is not None else None
            e.update(metadata=meta,canonical=canonical)
            spans=[dict(s) for s in db.execute('select * from evidence_span where evidence_id=? order by ordinal',(e['evidence_id'],))]
            spans_by_id[e['evidence_id']]=spans
            valid=bool(spans)
            for s in spans:
                raw=source.execute('select text,source_artifact_sha256 from source_block where document_id=? and block_id=?',(e['document_id'],s['block_id'])).fetchone()
                valid=valid and bool(raw) and raw['source_artifact_sha256']==e['source_artifact_hash'] and hashtext(raw['text'])==s['block_hash'] and raw['text'][s['start_cp']:s['end_cp']]==s['text'] and hashtext(s['text'])==s['span_hash']
            valid=valid and hashtext('\n'.join(s['text'] for s in spans))==e['text_hash']
            checks.append({'evidence_id':e['evidence_id'],'spans':len(spans),'exact_original_match':bool(valid)})
            evidence[e['evidence_id']]=e
        maps.setdefault(side,{}).update(evidence)
        observed=[];read_count=0
        for row in db.execute("select status,result_json from observation where tool in ('read','read_node')"):
            if row['status']!='OK':continue
            value=json.loads(row['result_json']);read_count+=1;observed.extend(value.get('evidence_ids',[]))
        events=[]
        for row in db.execute('select seq,kind,payload_json from event order by seq'):
            v=json.loads(row['payload_json']);kind=row['kind']
            if any(t in kind for t in ('REJECT','FAIL','ERROR','RECOVER','REPAIR')):
                diag=v.get('diagnostics',{});contract=diag.get('output_contract',v.get('validation',{}))
                event={'seq':row['seq'],'kind':kind,'code':v.get('code',diag.get('error_code')),
                       'error':diag.get('error_message',v.get('message',v.get('cause'))),'category':contract.get('category'),
                       'issues':[{'code':x.get('code'),'path':x.get('path')} for x in contract.get('issues',[])],
                       'journal':str(path.relative_to(R))}
                events.append(event)
        state=dict(db.execute('select status,phase,state_revision,evidence_revision from run').fetchone())
        if side!='parent':
            returned=body.get('rag_results',{}).get(side,{})
            child=summary['children'].setdefault(side,{'runs':[],'read_observations':0,'read_evidence_ids':[],
                 'canonical_read':[],'all_read_evidence':[],'returned_status':returned.get('status'),
                 'returned_evidence_ids':returned.get('evidence_ids',[]),'events':[]})
            child['runs'].append({'state':state,'journal':str(path.relative_to(R)),'read_observations':read_count})
            child['read_observations']+=read_count
            child['read_evidence_ids'].extend(observed)
            child['canonical_read'].extend(evidence[i]['canonical'] for i in observed if i in evidence and evidence[i]['canonical'])
            child['all_read_evidence'].extend(evidence.values())
            child['events'].extend(events)
        else:
            summary['errors']=events
            summary['child_return_history']=[]
            for call in db.execute("select call_id,status,result_json,error_json from workflow_call where kind='rag' order by rowid"):
                returned=json.loads(call['result_json'] or '{}')
                summary['child_return_history'].append({'call_id':call['call_id'],'receipt_status':call['status'],
                    'side':returned.get('side'),'status':returned.get('status'),'evidence_ids':returned.get('evidence_ids',[]),
                    'error_code':returned.get('error_code'),'child_run_ids':[r.get('run_id') for r in returned.get('records',[])]})
        summary['evidence_span_checks'].extend({'side':side,**c} for c in checks)
        journals.append({'side':side,'path':str(path.relative_to(R))});db.close()
    parent=maps.get('parent',{})
    for side,child in summary['children'].items():
        child['canonical_adopted']=[parent[i]['canonical'] for i in child['returned_evidence_ids'] if i in parent and parent[i]['canonical']]
        child['adoption_unmapped']=[i for i in child['returned_evidence_ids'] if i not in parent or not parent[i]['canonical']]
    summary['canonical_final']=[parent[i]['canonical'] for i in summary['evidence_refs'] if i in parent and parent[i]['canonical']]
    summary['final_unmapped']=[i for i in summary['evidence_refs'] if i not in parent or not parent[i]['canonical']]
    for p in sorted((O/'raw').glob('call-*')):
        request=read(p/'request.json');c={'call':p.name,'request_bytes':(p/'request.json').stat().st_size,
            'schema_chars':len(json.dumps(request.get('response_format',{}),ensure_ascii=False))}
        for message in request.get('messages',[]):
            try: view=json.loads(message.get('content','')).get('view',{})
            except (ValueError,TypeError,AttributeError): continue
            if isinstance(view,dict) and str(view.get('source_stage','')).startswith('workflow-'):
                packet=view.get('packet') or {};sources=view.get('sources',[])
                c['workflow_input']={'stage':view['source_stage'],
                    'source_cards':len(sources.get('table_rows',[])) if isinstance(sources,dict) else len(sources),
                    'packet':{k:packet.get(k) for k in ('index','count','dependency_closure_complete')},
                    'packet_evidence_count':len(packet.get('evidence_ids',[]))}
        if (p/'error.json').exists():c['error']=read(p/'error.json')
        if (p/'response.json').exists():
            raw=read(p/'response.json');choices=raw.get('choices') or [{}]
            c.update(model=raw.get('model'),provider=raw.get('provider'),finish=choices[0].get('finish_reason'),provider_error=raw.get('error'))
            try:v=json.loads(choices[0].get('message',{}).get('content',''))
            except (ValueError,TypeError):v={}
            c['decision']={k:v[k] for k in ('next_action','targets','issue_refs','disposition','status','verdict') if k in v}
        summary['calls'].append(c)
    summary['journals']=journals
    put(O/'audit.json',summary)
    print(json.dumps({'case':case['id'],'status':run.get('status'),'calls':run['model_calls'],'rows':summary['rows'],
        'children':{s:{'returned_status':c['returned_status'],'read_observations':c['read_observations'],
                       'returned_evidence_count':len(c['returned_evidence_ids'])} for s,c in summary['children'].items()},
        'span_mismatches':sum(not c['exact_original_match'] for c in summary['evidence_span_checks'])},ensure_ascii=False))
