"""Post-selection only, no model calls or changes to product inputs."""
from pathlib import Path
import gzip,hashlib,json,sqlite3,sys,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0889-scoped-reading-completion';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());ht=lambda s:hashlib.sha256(s.encode()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def db(p):
 d=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);d.row_factory=sqlite3.Row;return d
G=R/read(D/'baseline.json')['release']['data_path'];source=db(G/'store.sqlite');nav=db(G/'navigation/navigation.sqlite')
def origin(sid):
 row=nav.execute('select json from source where id=?',(sid,)).fetchone();return json.loads(row[0]) if row else None
def coord(v):
 if not v:return None
 a=v.get('article_coordinate') or {};did=a.get('doc_id',v.get('document_id'));node=a.get('node',v.get('unit_id'))
 return {'doc_id':did,'node':int(node)} if did and node is not None and str(node).isdigit() else None
def uniq(items):return [json.loads(v) for v in sorted({json.dumps(v,sort_keys=True) for v in items if v})]
for c in read(D/'cases.json'):
 cid=c['id'];P=O/cid
 if len(sys.argv)>1 and cid!=sys.argv[1]:continue
 if (P/'raw-runtime.tar.gz').exists() and (P/'audit.json').exists():
  print(cid,'existing audited archive preserved');continue
 if not (P/'result.json').exists():continue
 result=read(P/'result.json');body=read(P/'response.json').get('body',{}) if (P/'response.json').exists() else {};answer=body.get('answer',{})
 finalids=sorted({sid for claim in answer.get('claims',[]) for sid in claim.get('source_ids',[])}) if isinstance(answer,dict) else []
 summary={'case_id':cid,'result':{k:v for k,v in result.items() if k!='usage'},'final_source_ids':finalids,'final_coordinates':uniq(coord(origin(s)) for s in finalids),'final_sources':[{'source_id':s,'document':(origin(s) or {}).get('document_name'),'heading':(origin(s) or {}).get('heading')} for s in finalids],'unmapped_final':[s for s in finalids if not coord(origin(s))], 'read_evidence':[], 'read_coordinates':[], 'span_checks':[], 'events':[], 'decisions':[], 'state':[], 'original_availability':[]}
 (P/'answer.txt').write_text((answer.get('text','') if isinstance(answer,dict) else str(answer)) or body.get('message',''))
 for journal in (P/'runtime').rglob('journal.sqlite'):
  j=db(journal);summary['state'].append(dict(j.execute('select status,phase,state_revision,evidence_revision from run').fetchone()))
  summary['budget']=dict(j.execute('select * from budget').fetchone())
  for row in j.execute('select * from evidence_unit'):
   e=dict(row);spans=[dict(x) for x in j.execute('select * from evidence_span where evidence_id=? order by ordinal',(e['evidence_id'],))];v=origin(e['source_id']);valid=bool(spans)
   for span in spans:
    raw=source.execute('select text,source_artifact_sha256 from source_block where document_id=? and block_id=?',(e['document_id'],span['block_id'])).fetchone()
    valid=valid and bool(raw) and raw['source_artifact_sha256']==e['source_artifact_hash'] and ht(raw['text'])==span['block_hash'] and raw['text'][span['start_cp']:span['end_cp']]==span['text'] and ht(span['text'])==span['span_hash']
   valid=valid and ht('\n'.join(x['text'] for x in spans))==e['text_hash']
   summary['span_checks'].append({'evidence_id':e['evidence_id'],'span_count':len(spans),'exact_original_match':bool(valid)})
   summary['read_evidence'].append({'evidence_id':e['evidence_id'],'source_id':e['source_id'],'canonical':coord(v),'document':v.get('document_name') if v else None,'heading':v.get('heading') if v else None,'blocks':[x['block_id'] for x in spans],'ranges':[{'block_id':x['block_id'],'start_cp':x['start_cp'],'end_cp':x['end_cp']} for x in spans], 'chars':sum(len(x['text']) for x in spans)})
  for row in j.execute('select seq,kind,payload_json from event order by seq'):
   if any(s in row['kind'] for s in ('FAIL','REJECT','ERROR','REPAIR','PENDING_READING','ASSESSMENT_GAP','ASSESSMENT_VALIDATED','READ_CHOICE')):
    summary['events'].append({'seq':row['seq'],'kind':row['kind'],'payload':json.loads(row['payload_json'])})
  summary['navigation_handles']={row['kind']:row['n'] for row in j.execute('select kind,count(*) n from navigation_handle group by kind')};j.close()
 summary['read_coordinates']=uniq(e['canonical'] for e in summary['read_evidence'])
 for reqp in sorted((P/'raw').glob('*/request.json')):
  v=read(reqp);resp=reqp.with_name('response.json');out={}
  if resp.exists():
   try:out=json.loads(read(resp)['choices'][0]['message']['content'])
   except (ValueError,KeyError,IndexError,TypeError):pass
  view={}
  for msg in v.get('messages',[]):
   try:
    x=json.loads(msg.get('content',''));view=x.get('view',view) if isinstance(x,dict) else view
   except (ValueError,TypeError):pass
  actions=view.get('actions',{});rows=actions.get('table_rows',[]) if isinstance(actions,dict) else []
  mentioned=re.findall(r'read_action\((T[0-9]+)\)',str(out.get('reason',''))+' '+str(out.get('notes','')))
  read_options=[r for r in rows if len(r)>1 and r[0]=='READ_ARTICLES' and r[1] in mentioned]
  summary['decisions'].append({'mentioned_available_reads':read_options,'targets':out.get('targets'), 'exploration_targets':[e.get('target') for e in out.get('exploration',[]) if isinstance(e,dict)], 'call':reqp.parent.name,'stage':view.get('source_stage'),'reading_progress':view.get('reading_progress'),'action':out.get('next_action'), 'reason':out.get('reason'),'target_id':out.get('target_id'),'status':out.get('status'),'requested_action':out.get('action')})
 ref=next(x for x in read(D/'offline-reference.json') if x['id']==cid)
 for target in ref['targets']:
  found=nav.execute('select json from source where document_id=? and article=?',(target['doc_id'],target['article'])).fetchone()
  candidates=[]
  if found:candidates=[json.loads(found[0])]
  else:
   # Exact final document-name component only; never use candidate IDs in product.
   for row in nav.execute('select json from source where article=?',(target['article'],)):
    v=json.loads(row[0])
    if v.get('document_name','').split(' > ')[-1]==target['law']:candidates.append(v)
  available=[]
  for v in candidates:
   did=v['document_id'];d=source.execute('select json from document where document_id=?',(did,)).fetchone();metadata=json.loads(d[0]).get('document_metadata',{}) if d else {}
   ranges=[r for e in summary['read_evidence'] if e['source_id']==v['id'] for r in e['ranges']]
   full=[]
   for block in v.get('blocks',[]):
    intervals=sorted((r['start_cp'],r['end_cp']) for r in ranges if r['block_id']==block['block_id']);covered=0
    for start,end in intervals:
     if start>covered:break
     covered=max(covered,end)
    if covered>=len(block['text']):full.append(block['block_id'])
   available.append({'fully_read_block_ids':full,'original_block_count':len(v.get('blocks',[])),'unread_or_partial_block_ids':[b['block_id'] for b in v.get('blocks',[]) if b['block_id'] not in full], 'canonical':coord(v),'source_id':v['id'],'source_artifact_sha256':v.get('source_artifact_sha256'),'text_sha256':ht(v.get('text','')),'registered_text_sha256_matches':ht(v.get('text',''))==target.get('source_text_sha256'),'metadata':metadata,'read':coord(v) in summary['read_coordinates'],'cited':coord(v) in summary['final_coordinates'],'in_public_grant':did in read(P/'request.json').get('json',{}).get('document_ids',[])})
  summary['original_availability'].append({'law':target['law'],'article':target['article'],'registered_coordinate':{'doc_id':target['doc_id'],'node':int(target['node'])},'registered_revision':target.get('document_revision'),'registered_enforcement':target.get('document_enforcement'),'candidates':available})
 put(P/'audit.json',summary)
 print(json.dumps({'case':cid,'status':result.get('status'),'http':result.get('http_status'),'calls':result['model_calls'],'read_articles':len(summary['read_coordinates']),'cited_articles':len(summary['final_coordinates']),'span_mismatches':sum(not x['exact_original_match'] for x in summary['span_checks']),'answer':answer.get('text','') if isinstance(answer,dict) else str(answer)},ensure_ascii=False))
