"""Read-only stored009 decision-fragment replay; not a fresh legal answer run."""
from common import *
import sqlite3,os,resource
from copy import deepcopy
from types import SimpleNamespace as NS
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
f=read(sorted(DES.glob('freeze-*.json'))[-1]);C=ROOT/f['code_root']
for n,h in f['files'].items():assert sha(C/n)==h,n
sys.path[:0]=[str(C),str(C/'02_BACKEND')]
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import reference_bundles as rb,read_judgment_final as final,requirement_coverage as rc,investigation_supervisor as su
from semantic_runtime.legal_agent.errors import ProposalError
from lawrag.core.legal_coordinate import find_coordinates
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1201-final-original-coverage-review/artifacts/live/cm-009'
b=read(DES/'baseline.json');data=ROOT/b['release']['data_path'];view=read(P/'canonical/006.json.gz')['view'];value=read(P/'canonical/006-output.json.gz');state=read(P/'states/013.json.gz')
did=value['source_targets'][0]['document_ref']
db=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True)
nav=sqlite3.connect((data/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
units={};coords={}
for uid,parent,raw in db.execute('select unit_id,parent_id,json from source_unit where document_id=?',(did,)):
 node=json.loads(raw);node['parent']=parent;units[(did,str(uid))]=node
 surface=node.get('legal_coordinate',{}).get('surface','');found=find_coordinates(surface)
 if len(found)==1:coords[(did,str(uid))]=found[0].coordinate
sources={r['id']:r for (raw,) in nav.execute('select json from source where document_id=?',(did,)) for r in [json.loads(raw)]}
def members(doc,uid):
 seen=set()
 while uid is not None:
  uid=str(uid)
  if uid in seen:raise AssertionError('cycle')
  seen.add(uid)
  found=[sid for sid,s in sources.items() if str(s.get('unit_id'))==uid]
  if found:return found
  uid=units[(doc,uid)]['parent']
 return []
def source(doc,bid):
 row=db.execute('select text from source_block where document_id=? and block_id=?',(doc,str(bid))).fetchone();assert row
 return {'text':row[0]}
matcher=NS(units=units,stored_coordinates=coords,_unit_sources=members)
inv=NS(policy={'reference_bundle_review':True},p=state,s=NS(scope={x['document_id'] for x in view['sources']},store=NS(source=source),matcher=matcher))
goals=deepcopy(view['source_goal_context']['goals']);before=len(goals)
for row in value['source_targets']:
 coordinate=row['coordinate'];identity=digest([row['issue_id'],did,coordinate,row['coordinate_scope']])
 if not any(g['identity']==identity for g in goals):goals.append({'goal_id':'SG'+str(len(goals)+1),'identity':identity,'document_id':did,'document_name':'저장 대상 문서','coordinate':coordinate,'coordinate_scope':row['coordinate_scope'],'issue_id':row['issue_id'],'reason':row['reason'],'status':'REQUIRED','routes':[],'arrivals':[]})
added=rb.expand(inv,view,goals)
expected_members={'제31조제1항제3호마목','제31조제1항제3호바목'}
assert expected_members<={r['coordinate'] for r in goals},goals
assert any(r['coordinate'].endswith('바목') for r in added)
assert rb.expand(inv,view,goals)==[]
# Check actual stored final originals against each exact stored node subtree.
fv=read(P/'canonical/011.json.gz')['view'];opts=fv['evidence_options'];checks={}
for coordinate in expected_members:
 uid=next(uid for (doc,uid),c in coords.items() if c.canonical_surface()==coordinate)
 lo,hi=units[(did,uid)]['span'];expected=[]
 for bid,text in db.execute('select block_id,text from source_block where document_id=? and cast(block_id as integer)>=? and cast(block_id as integer)<? order by cast(block_id as integer)',(did,lo,hi)):
  expected.append({'document_id':did,'block_id':str(bid),'start_cp':0,'end_cp':len(text),'text_hash':digest(text)})
 checked=rb.coverage(expected,opts);checks[coordinate]={'complete':checked['complete'],'expected_blocks':[s['block_id'] for s in expected],'missing_blocks':[s['block_id'] for s in checked['missing']]}
 goal=next(g for g in goals if g['coordinate']==coordinate)
 goal['expected']=expected;goal['status']='ACQUIRED' if checked['complete'] else 'REQUIRED'
assert checks['제31조제1항제3호마목']['complete']
assert not checks['제31조제1항제3호바목']['complete']
# Copy final journal state only in memory, adding bound origins from the replay.
fs=read(P/'states/013.json.gz');st=next(iter(fs['investigation_supervisor'].values()));st['source_goals']=goals;st['state_hash']=su.seal(st)
ctx=final.context(fs,fv['current_request'],fv['issues'],opts,{o['document_id'] for o in opts},review_changes=True)
proposal=read(P/'canonical/012-output.json.gz');assert proposal['gaps']
try:final.validate_review(proposal,ctx,opts)
except ProposalError as exc:
 codes=sorted({e['code'] for e in exc.issues});assert 'FINAL_REVIEW_PURPOSE_CHANGE' in codes,codes
else:raise AssertionError('old ungrounded exclusion accepted')
reconciled,receipt=rc.reconcile_material_gaps(proposal,fv['requirement_context'],opts)
assert receipt and reconciled['claims']==proposal['claims'] and reconciled['gaps']==proposal['gaps']
rc.validate_review(reconciled,fv['requirement_context'],opts)
assert any(r['status']=='UNRESOLVED' and r['gap_indices'] for r in reconciled[rc.FIELD])
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
result={'passed':True,'candidate_revision':f['candidate_revision'],'scope':'Saved006 explicit target expansion and saved012 final review/gap reconciliation only; native API tested separately; no new009 model answer',
 'declared':[r['coordinate'] for r in value['source_targets']],'expanded':sorted(expected_members),'exact_coverage':checks,
 'change_rejection_codes':codes,'gap_indices_preserved':receipt['gap_indices'],'claims_unchanged':receipt['claims_unchanged'],'gaps_unchanged':receipt['gaps_unchanged'],
 'new_model_calls':0,'external_requests':0,'completed1201_unchanged':True,'main117_unchanged':True,
 'sources':[{'path':str((P/n).relative_to(ROOT)),'sha256':sha(P/n)} for n in ('canonical/006.json.gz','canonical/006-output.json.gz','canonical/011.json.gz','canonical/012-output.json.gz','states/013.json.gz')]}
put(ART/('saved009-'+f['candidate_revision']['revision_id']+'.json'),result)
print(json.dumps(result,ensure_ascii=False))
db.close();nav.close()
