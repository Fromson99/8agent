"""Post-selection evidence timing and supervisor execution audit; no product mutation."""
from common import *
import sqlite3,gzip,tarfile,tempfile,shutil,datetime
def ts(s):return datetime.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
nav=sqlite3.connect((ROOT/read(DES/'baseline.json')['release']['data_path']/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
refs={r['id']:r for r in read(ART/'evaluation-only/cases.json')}
def coord(sid):
 row=nav.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()
 if not row:return None
 src=json.loads(row[0]);c=src.get('article_coordinate') or {};did=c.get('doc_id',src.get('document_id'));node=c.get('node',src.get('unit_id'))
 return (did,int(node)) if did and str(node).isdigit() else None
allrows=[]
for case in read(DES/'cases.json'):
 p=RUN/case['id']
 if not (p/'audit.json').exists():continue
 a=read(p/'audit.json');calls=read(p/'calls.json');start=None
 for line in (p/'worker.log').read_text().splitlines():
  if line.startswith('{'):
   try:l=json.loads(line)
   except ValueError:continue
   if l.get('event')=='ask.started':start=ts(l['ts']);break
 assert start is not None
 targets={(x['doc_id'],int(x['node'])) for x in refs[case['id']]['targets']};firstread={};firstdelivered={};events=[];assess=[];lastclaims=[]
 with tempfile.TemporaryDirectory(dir=ART,prefix='supervisor-post-') as tmp,tarfile.open(p/'runtime.tar.gz','r:gz') as tar:
  for i,m in enumerate(x for x in tar.getmembers() if x.name.endswith('/journal.sqlite')):
   folder=Path(tmp)/str(i);folder.mkdir();dbpath=folder/'journal.sqlite'
   with tar.extractfile(m) as src,dbpath.open('wb') as out:shutil.copyfileobj(src,out)
   for suffix in ('-wal','-shm'):
    try:side=tar.getmember(m.name+suffix)
    except KeyError:continue
    with tar.extractfile(side) as src,(folder/('journal.sqlite'+suffix)).open('wb') as out:shutil.copyfileobj(src,out)
   db=sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True)
   for sid,when in db.execute('SELECT u.source_id,e.created_at FROM evidence_unit u JOIN event e ON e.seq=u.created_seq'):
    c=coord(sid)
    if c in targets:firstread[c]=min(firstread.get(c,float('inf')),ts(when)-start)
   for seq,kind,raw,when in db.execute("SELECT seq,kind,payload_json,created_at FROM event WHERE kind LIKE 'SUPERVISOR%' OR kind IN ('COMPLETION_ASSESSMENT_REJECTED','FINAL_REVIEW_INDEPENDENT_RESEARCH','READ_CHOICE_SELECTED','INVESTIGATION_CHAIN_STEP') ORDER BY seq"):
    events.append({'seq':seq,'kind':kind,'seconds':ts(when)-start,'payload':json.loads(raw)})
   for raw in db.execute("SELECT payload_json FROM entity_version WHERE kind='case_stage' AND entity_id='case:ASSESS' ORDER BY version"):
    assess.append(json.loads(raw[0]))
   db.close()
 monitors=[]
 for call in calls:
  generation=call.get('generation')
  if not generation:continue
  f=p/'canonical'/f'{generation:03}.json.gz'
  if not f.exists():continue
  v=json.load(gzip.open(f,'rt'))['view']
  for source in v.get('sources',[]):
   c=coord(source.get('source_id',''))
   if c in targets:firstdelivered.setdefault(c,{'call':call['call'],'seconds':ts(call['started_at'])-start,'phase':call['phase']})
  if 'supervisor' in call['phase']:
   output=p/'canonical'/f'{generation:03}-output.json.gz'
   monitors.append({'call':call['call'],'seconds':ts(call['started_at'])-start,'trigger':v.get('trigger'),'proposed_action':v.get('proposed_action'),'result':json.load(gzip.open(output,'rt')) if output.exists() else None,'transport_status':call['status']})
 r={'case_id':case['id'],'http_status':a['http_status'],'model_calls':a['model_calls'],'supervisor_calls':len(monitors),'elapsed_seconds':a['elapsed_seconds'],'claim_count':a['claim_count'],'accepted_outcome':a['accepted_outcome'],'published_answer':a['http_status']==200 and a['answer_chars']>0,'has_actual_claims':a['claim_count']>0,'successful_answer_not_certified':True,'target_timing':[{'doc_id':d,'node':n,'server_first_acquired_seconds':firstread.get((d,n)),'model_first_delivery':firstdelivered.get((d,n))} for d,n in sorted(targets)],'monitors':monitors,'events':events,'assessments':assess,'source_mismatches':a['source_mismatches'],'acl_violations':a['acl_violations'],'claim_ref_violations':sum(not x['valid_refs'] for x in a['final_claim_links']),'output_cap_fields':a['output_cap_fields'],'supervisor_budget_ok':len(monitors)<=2,'no_supervisor_repair_or_retry':not any('supervisor' in c['phase'] and 'repair' in c['phase'] for c in calls)}
 put(p/'supervisor-audit.json',r);allrows.append({k:v for k,v in r.items() if k not in ('events','assessments','monitors')})
nav.close();put(RUN/'supervisor-summary.json',allrows);print(json.dumps(allrows,ensure_ascii=False))
