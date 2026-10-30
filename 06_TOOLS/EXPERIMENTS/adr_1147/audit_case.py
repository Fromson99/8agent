"""Bounded read-only audit of preserved candidate/native/model evidence."""
from pathlib import Path
import json,gzip,sys,sqlite3,hashlib
R=Path(__file__).resolve().parents[3];A=R/sys.argv[1];P=A/'artifacts/run-001/privacy-controller-source-001'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
f=read(A/'artifacts/design/freeze.json');C=R/f['code_root'];r=read(P/'result.json');allowed=set(read(P/'request.json')['json']['document_ids']);base=read(A/'artifacts/design/baseline.json');g=R/base['release']['data_path'];db=sqlite3.connect((g/'store.sqlite').as_uri()+'?mode=ro',uri=True);db.execute('PRAGMA cache_size=-4096')
summary={'new_model_calls':r['model_calls'],'http_status':r.get('http_status'),'status':r.get('status'),'source_spans':0,'source_mismatches':[],'scope_violations':[],'stable_id_changes':[],'calls':[],'output_cap_fields':[],'judgment_events':{},'quality_certified':False,'performance_claim':False,'elapsed_seconds':r['elapsed_seconds']};known={};docs={}
for p in sorted((P/'canonical').glob('*.json.gz')):
 if 'output' in p.name:continue
 v=json.load(gzip.open(p,'rt'))['view']
 reg=v.get('reference_registry',{})
 for ident,alias in reg.get('mapping',{}).items():
  if ident in known and known[ident]!=alias:summary['stable_id_changes'].append([p.name,ident,known[ident],alias])
  known[ident]=alias
 for d in reg.get('documents',[]):
  if d['document_id'] in docs and docs[d['document_id']]!=d['id']:summary['stable_id_changes'].append([p.name,d['document_id'],docs[d['document_id']],d['id']])
  docs[d['document_id']]=d['id']
 for s in v.get('sources',[]):
  if 'spans' not in s:continue
  if s['document_id'] not in allowed:summary['scope_violations'].append([p.name,s['document_id']])
  for span in s['spans']:
   row=db.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',(s['document_id'],str(span['block_id']))).fetchone();summary['source_spans']+=1
   if not row or row[0][span['start_cp']:span['end_cp']]!=span['text']:summary['source_mismatches'].append([p.name,s['id'],span['block_id']])
  if '\n'.join(x['text'] for x in s['spans'])!=s['text']:summary['source_mismatches'].append([p.name,s['id'],'joined'])
for call in read(P/'calls.json'):
 row={k:call.get(k) for k in ('call','phase','status','http_status','error_type')};op=P/'canonical'/f"{call['generation']:03d}-output.json.gz"
 if op.exists():
  d=json.load(gzip.open(op,'rt'));rv=d.get('read_review',{});row.update(choice=d.get('choice'),new_reviews=len(rv.get('new_reviews',{})),revisions=len(rv.get('revisions',{})))
 summary['calls'].append(row)
for p in (P/'raw').glob('call-*/request.json'):
 d=read(p)
 summary['output_cap_fields'] += [[p.parent.name,k] for k in ('max_tokens','max_output_tokens','max_completion_tokens') if k in d]
for jp in r['journal_paths']:
 j=sqlite3.connect((R/jp).as_uri()+'?mode=ro',uri=True)
 for kind,count in j.execute("SELECT kind,count(*) FROM event WHERE kind like 'READ_JUDGMENT%' OR kind='INDEPENDENT_READ_RECOVERY' OR kind='INVESTIGATION_BOUNDED_STOP' GROUP BY kind"):
  summary['judgment_events'][kind]=summary['judgment_events'].get(kind,0)+count
 j.close()
summary.update(candidate_files_unchanged=all(sha(C/n)==h for n,h in f['files'].items()),active_pointer_unchanged=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'],stable_canonical_ids=len(known),stable_documents=len(docs),usage=r['usage'])
summary.update(wire_source_checks=0,wire_source_mismatches=[])
for row in read(P/'calls.json'):
 cp=P/'canonical'/f"{row['generation']:03d}.json.gz"
 if not cp.exists():continue
 canonical=json.load(gzip.open(cp,'rt'))['view'];mapping=canonical.get('reference_registry',{}).get('mapping',{})
 paths=list((P/'raw').glob(f"call-{row['call']:03d}-*/request.json"))
 if not paths:continue
 actual=json.loads(read(paths[0])['messages'][1]['content'])['view']
 sources={s['id']:s for s in actual.get('sources',[]) if isinstance(s,dict) and 'id' in s}
 for source in canonical.get('sources',[]):
  if 'text' not in source:continue
  alias=mapping.get(source['id'],source['id']);offered=sources.get(alias);summary['wire_source_checks']+=1
  if offered is None or offered.get('text')!=source['text']:summary['wire_source_mismatches'].append([row['call'],alias,'source text differs or missing'])
 # Assessment options are a second source carrier after the full-page menu.
 offered={e['id']:e for e in actual.get('evidence_options',[]) if isinstance(e,dict) and 'id' in e}
 for option in canonical.get('evidence_options',[]):
  if 'text' not in option:continue
  alias=mapping.get(option['id'],option['id']);delivered=offered.get(alias)
  if delivered is not None:
   summary['wire_source_checks']+=1
   if delivered.get('text')!=option['text']:summary['wire_source_mismatches'].append([row['call'],alias,'assessment text differs'])
out=P/'audit.json';assert not out.exists();out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k not in ('calls','usage')},ensure_ascii=False))
