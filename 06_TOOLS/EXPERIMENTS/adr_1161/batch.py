"""One heavy worker at a time; record every CM case, never replay a dispatched case."""
from common import *
import subprocess,time,os,signal,sqlite3,gzip,tarfile,shutil,hashlib
cases=read(DES/'cases.json');f=read(DES/'freeze.json');S=Path(__file__).parent
assert len(cases)==3
assert read(ART/'preflight/cm-001/preflight-transport-reached.json')['native_transport_boundary_reached']
RUN.mkdir(parents=True,exist_ok=True);put(ART/'batch-process.json',{'pid':os.getpid(),'started_at':time.time(),'cases':3})

def audit(P):
 r=read(P/'result.json');body=(read(P/'response.json').get('body') or {}) if (P/'response.json').exists() else {};answer=body.get('answer') or {};answer=answer if isinstance(answer,dict) else {};ta=(body.get('assembly') or {}).get('term_agent') or {};scope=set(read(P/'request.json')['json']['document_ids']) if (P/'request.json').exists() else set()
 observed={'case_id':P.name,'http_status':r.get('http_status'),'status':r.get('status'),'error':r.get('error'),'error_type':r.get('error_type'),'model_calls':r.get('model_calls',0),'elapsed_seconds':r.get('elapsed_seconds'),'model_seconds':r.get('model_transport_seconds'),'application_prepare_seconds':r.get('application_prepare_seconds'),'claim_count':len(answer.get('claims',[])),'answer_chars':len(answer.get('text','')),'accepted_outcome':ta.get('accepted_outcome'),'usage':r.get('usage',[]),'read_evidence':0,'span_checks':0,'source_mismatches':0,'acl_violations':0,'events':{},'final_claim_links':[],'legal_correctness':'not_scored','runtime_archive':None}
 db=sqlite3.connect((ROOT/read(DES/'baseline.json')['release']['data_path']/'store.sqlite').as_uri()+'?mode=ro',uri=True)
 for path in r.get('journal_paths',[]):
  jp=ROOT/path
  if not jp.exists():continue
  j=sqlite3.connect(jp.as_uri()+'?mode=ro',uri=True);j.row_factory=sqlite3.Row
  for e in j.execute('SELECT * FROM evidence_unit'):
   observed['read_evidence']+=1
   if e['document_id'] not in scope:observed['acl_violations']+=1
   for span in j.execute('SELECT * FROM evidence_span WHERE evidence_id=?',(e['evidence_id'],)):
    raw=db.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',(e['document_id'],span['block_id'])).fetchone();observed['span_checks']+=1
    if not raw or raw[0][span['start_cp']:span['end_cp']]!=span['text']:observed['source_mismatches']+=1
  for row in j.execute("SELECT kind,count(*) n FROM event WHERE kind like '%REPAIR%' OR kind like '%REJECT%' OR kind like '%INDEPENDENT%' GROUP BY kind"):observed['events'][row['kind']]=observed['events'].get(row['kind'],0)+row['n']
  row=j.execute("SELECT payload_json FROM entity_version WHERE kind='case_stage' AND entity_id='case:ASSESS' ORDER BY version DESC LIMIT 1").fetchone()
  if row:
   assess=json.loads(row[0]);ids={c['claim_id'] for c in assess.get('claims',[])}
   for rv in ((assess.get('read_judgment_review') or {}).get('review') or {}).get('judgments',[]):observed['final_claim_links'].append({'id':rv['id'],'disposition':rv['disposition'],'valid_refs':set(rv['claim_refs'])<=ids,'claim_refs':rv['claim_refs']})
  j.close()
 db.close()
 observed['output_cap_fields']=[]
 for p in (P/'raw').glob('call-*/request.json'):
  raw=read(p)
  for k in ('max_tokens','max_output_tokens','max_completion_tokens'):
   if k in raw:observed['output_cap_fields'].append([p.parent.name,k])
 observed['original_integrity_checked']=observed['span_checks']>0
 observed['integrity_fault']=bool(observed['source_mismatches'] or observed['acl_violations'] or observed['output_cap_fields'] or any(not x['valid_refs'] for x in observed['final_claim_links']))
 observed['response_with_claims']=observed['http_status']==200 and observed['claim_count']>0 and observed['answer_chars']>0
 rt=P/'runtime'
 if rt.exists():
  files={str(x.relative_to(P)):sha(x) for x in rt.rglob('*') if x.is_file()};arc=P/'runtime.tar.gz'
  with tarfile.open(arc,'w:gz',compresslevel=4,dereference=False) as t:t.add(rt,arcname='runtime')
  with tarfile.open(arc,'r:gz') as t:
   ms={x.name:x for x in t if x.isfile()};assert set(ms)==set(files)
   for n,m in ms.items():
    with t.extractfile(m) as q:assert hashlib.file_digest(q,'sha256').hexdigest()==files[n]
  put(P/'runtime-archive.json',{'archive':str(arc.relative_to(ROOT)),'sha256':sha(arc),'files':files,'verified_lossless':True,'restore':'tar -xzf runtime.tar.gz -C '+str(P)});shutil.rmtree(rt);observed['runtime_archive']=str(arc.relative_to(ROOT))
 put(P/'audit.json',observed);return observed

def progress(rows,active=None,stopped=None):
 put(RUN/'progress.json',{'total':3,'completed':len(rows),'active':active,'stopped':stopped,'model_calls':sum(x.get('model_calls',0) for x in rows),'with_claims':sum(x.get('response_with_claims',False) for x in rows),'cases':rows,'updated_at':time.time()})
rows=[]
for case in cases:
 cid=case['id'];P=RUN/cid
 assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
 if (P/'audit.json').exists():rows.append(read(P/'audit.json'));continue
 if (P/'request.json').exists() and not (P/'result.json').exists():
  put(P/'result.json',{'case_id':cid,'status':'interrupted','error':'Previously dispatched without result; no same-case replay','model_calls':len(list((P/'raw').glob('call-*'))),'journal_paths':[str(p.relative_to(ROOT)) for p in (P/'runtime').rglob('journal.sqlite')],'elapsed_seconds':None})
 if not (P/'result.json').exists():
  avail=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
  if avail<3*1024**3 or shutil.disk_usage(ROOT).free<20*1024**3:progress(rows,stopped='resource guard before case');raise SystemExit(2)
  P.mkdir(parents=True,exist_ok=True);progress(rows,active=cid);started=time.monotonic()
  with (P/'worker.log').open('w') as log:
   process=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(S/'live.py'),cid],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   put(ART/'batch-process.json',{'pid':os.getpid(),'child_pid':process.pid,'active':cid,'started_at':time.time()})
   try:process.wait(timeout=1860)
   except (subprocess.TimeoutExpired,KeyboardInterrupt) as exc:
    os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
    if isinstance(exc,KeyboardInterrupt):raise
   if not (P/'result.json').exists():put(P/'result.json',{'case_id':cid,'status':'worker_failed','error':'Worker exited without result; see worker.log','returncode':process.returncode,'model_calls':len(list((P/'raw').glob('call-*'))),'usage':read(P/'raw/usage.json') if (P/'raw/usage.json').exists() else [],'journal_paths':[str(p.relative_to(ROOT)) for p in (P/'runtime').rglob('journal.sqlite')],'elapsed_seconds':time.monotonic()-started})
 row=audit(P);rows.append(row);progress(rows)
 print('CASE',cid,'completed',len(rows),'/3','HTTP',row['http_status'],'claims',row['claim_count'],'calls',row['model_calls'],flush=True)
 if row['integrity_fault']:progress(rows,stopped='integrity fault');raise SystemExit(3)
 if row['model_calls']==0 and row.get('error_type') in ('AssertionError','ContractError'):progress(rows,stopped='host or binding fault');raise SystemExit(4)
 time.sleep(2)
progress(rows);put(RUN/'execution-complete.json',{'cases':3,'completed':len(rows),'model_calls':sum(r['model_calls'] for r in rows),'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'],'quality_certified':False});print('ALL3 COMPLETE',flush=True)
