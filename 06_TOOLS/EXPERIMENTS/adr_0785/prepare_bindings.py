"""Bind new document membership without changing original data or export grants."""
from pathlib import Path
import hashlib,json,sqlite3,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0785/integrated/snapshot'
G=R/'01_DATA/TERM_RELEASES/risk-compare-docx-20261015-r1-index/serving/baseline/generation'
staged='--building' in sys.argv
selected=G.parent.parent/'.baseline.building/generation' if staged else G
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(selected/'manifest.json');old='term-source-8729f978a28924cb8c5b';did='deb0727589aad3cc'
with sqlite3.connect('file:'+str(selected/'store.sqlite')+'?mode=ro',uri=True) as db:
 rows={x[0]:x[1] for x in db.execute('SELECT document_id,source_artifact_sha256 FROM document')}
 assert len(rows)==1547
 added=rows[did];assert added=='deb0727589aad3cc1587ffd39e8fb66ad9603b4d716f757a90c96d098a394770'
paths={}
for kind in ('document-origins','document-aliases'):
 value=read(R/'01_DATA/PROJECTIONS'/kind/(old+'.json'))
 value.update(generation_id=m['generation_id'],store_sha256=m['store_sha256'])
 if kind=='document-origins':
  assert all(rows[d]==v['source_artifact_sha256'] for d,v in value['documents'].items())
  value['documents'][did]={'document_id':did,'status':'verified','source_artifact_sha256':added,
    'raw_relative_path':'internal/risk_team/상위규정/그룹위험관리기준시행세칙/그룹 위험관리세칙_최종.docx',
    'basis':'native DOCX hash; registered SourceSet risk-compare-input-20261015-r1; photo transcription; current validity unknown'}
  value['team_memberships'][did]=['risk_team']
 else:value['origin_projection_store_sha256']=m['store_sha256']
 name='01_DATA/PROJECTIONS/'+kind+'/'+m['generation_id']+'.json';put(C/name,value)
 paths[kind]={'generation_id':m['generation_id'],'path':name,'sha256':sha(C/name)}
p=C/'00_SYSTEM/PIPELINE.json';v=read(p)
def walk(x):
 if isinstance(x,dict):
  for key,kind in [('origin_projections','document-origins'),('alias_projections','document-aliases')]:
   if key in x:
    prior=[y for y in x[key] if y['generation_id']==m['generation_id']]
    if prior:assert prior==[paths[kind]]
    else:x[key].append(paths[kind])
  for y in x.values():walk(y)
 elif isinstance(x,list):
  for y in x:walk(y)
walk(v);put(p,v)
put(A/('artifacts/data-staged-binding.json' if staged else 'artifacts/data-binding.json'),{'generation_path':str(selected.relative_to(R)),
 'manifest_sha256':sha(selected/'manifest.json'),'generation_id':m['generation_id'],
 'store_sha256':m['store_sha256'],'document_count':len(rows),'new_document_id':did,
 'source_sha256':added,'projections':paths,'export_allowed':m['export_allowed'],
 'old_documents_unchanged':True,'current_validity':'unknown','model_calls':0,'selected':False})
print('Data binding ready:',m['generation_id'],len(rows),'documents; no active pointer changed')
