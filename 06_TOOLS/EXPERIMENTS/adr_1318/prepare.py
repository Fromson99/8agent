from pathlib import Path
import json,hashlib,sys,shutil,re,sqlite3
ROOT=Path('/home/jin/8-AGENT');T=Path(__file__).parent
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1318-integration-search-r2-answer-check';ART=ADR/'artifacts';DES=ART/'design'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path']);C=ROOT/release['code_root']
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
assert all(sha(C/n)==h for n,h in release['files'].items())
put(DES/'baseline.json',{'pointer':pointer,'release':release})
old=ROOT/'06_TOOLS/EXPERIMENTS/adr_1305'
for name in ('common.py','resource_guard.py','pinned_imports.py'):
 s=(old/name).read_text().replace('ADR-1305-main135-nearai-sqlite','ADR-1318-integration-search-r2-answer-check')
 (T/name).write_text(s)
grant=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
pub=set(grant['public_document_ids']);permitted=set(grant['workflow_authorization']['document_ids'])
db=sqlite3.connect('file:'+str(ROOT/release['data_path']/'store.sqlite')+'?mode=ro',uri=True)
names=dict(db.execute('select document_id,name from document'))
internal=sorted(k for k,v in names.items() if 'internal > risk_team >' in v and k in permitted)
assert internal
external=sorted(pub)
put(DES/'source-scope.json',{'public':external,'internal':internal,'names':{i:names[i] for i in external+internal},'authorization_path':str((C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json').relative_to(ROOT)),'authorization_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')})
source=ROOT/'09_ARTIFACTS/REPORTS/DOCUMENTS/20261104-integration-template-r2/작성데이터.json';book=read(source)
rows=[];groups=[]
manual={3:{1,2},5:{1,2,8,17,22,23,30}}
for a in (3,5):
 for n,item in enumerate(book[str(a)],1):
  ident=f'b{a:02}-{n:02}';quotes=re.findall('「([^」]+)」',item['action'])
  queries=[q for q in quotes if q not in ('외규','내규','전체 법령','대사','출처')]
  row={'id':ident,'agent':a,'number':n,**item,'classification':'question','queries':queries}
  if n in manual[a]:row['classification']='GENOS_UI_REQUIRED'
  elif a==5 and n in (27,29):row['classification']='CONCRETE_INPUT_REQUIRED'
  else:
   assert queries,(ident,item)
   mode='외규' if a==3 or n in (3,4,5,6,7,20) else '전체 법령' if n==18 else '대사' if n in (26,28) else '내규'
   if a==5 and n==21:
    queries=['위험관리위원회의 역할은?']*2;modes=['내규','외규']
   else:modes=[mode]*len(queries)
   if a==3 and n==27:queries=queries*2;modes=modes*2
   if a==3 and n==25:
    queries+=['상법상 정기주주총회는 언제 소집해야 하나요?','그럼 임시총회는 언제 소집하나요?'];modes+=['외규','외규']
   scope=external if a==3 or mode=='외규' else sorted(set(external+internal))
   steps=[{'number':i,'question':q,'mode':mo} for i,(q,mo) in enumerate(zip(queries,modes),1)]
   groups.append({'id':ident,'steps':steps,'document_ids':scope,'arms':['selected-main'],'original_test':item,'extra_multiturn_steps':a==3 and n==25})
  rows.append(row)
priority=['b03-25','b05-24','b05-21','b03-27','b03-28','b03-29','b05-25']
groups.sort(key=lambda g:(priority.index(g['id']) if g['id'] in priority else len(priority),g['id']))
put(DES/'cases.json',groups);put(DES/'workbook-cases.json',rows)
criteria={'hypothesis':'The exact R2 questions produce source-bound answers or appropriate clarification, and multi-turn transitions keep the intended subject while applying current scope and isolating new topics.',
 'primary_metric':'Per-turn final answer availability, expected content/source presence, effective question, command target, selected source category and reused evidence; UI-only cases separate.',
 'success':['Expected substantive answer and supporting original passages for answerable questions; a nonempty text alone is insufficient.','Follow-up role/convener refers to the prior subject; unrelated topic starts a separate goal; internal to external switch excludes old internal evidence.','No source/hash/ACL drift, no same-request extra physical call.'],
 'failure':['Save all HTTP/model/semantic failures separately. Unknown provider outcome or resource stop ends dispatch, never automatically resend a terminal request.','Stop after three consecutive technical errors; report remaining cells unexecuted, not failures.','Do not mark GENOS click/display cases passed from local API outcomes.'],
 'limits':{'per_request_physical':40,'global_physical':500,'per_request_seconds':1800,'sequential_workers':1},
 'selection':'All concrete question cases; multi-turn groups first in declared order. Each original query once except declared repeat and exact duplicate verification. Two unbound placeholder rows and GUI-only rows remain separately identified.',
 'user_steering':['지금만든 질문들 답이 나오는지','질문날리는것들 확인해줘 특히 멀티턴이런건 문제가 생길가능서잉 있어서 수정이나 실험해봐 내부에서'],
 'code_policy':'Freeze current selected release for baseline. No product or MAIN mutation. Any repair is a new frozen candidate after reproducible failure.',
 'source':{'input_path':str(source.relative_to(ROOT)),'input_sha256':sha(source),'source_store_sha256':read(ROOT/release['data_path']/'manifest.json')['store_sha256']}}
put(DES/'criteria.json',criteria)
put(DES/'authorization.json',{'user_request':criteria['user_steering'],'original_grant_path':str((C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json').relative_to(ROOT)),'original_grant_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'prior_explicit_authorization':grant['workflow_authorization']['authorization_text'],'scope_public':external,'scope_internal':internal,'cases_sha256':sha(DES/'cases.json'),'internal_source_is_public':False,'production_approval_unchanged':True})
oldart=ROOT/'04_EXPERIMENTS/ADR/ADR-1305-main135-nearai-sqlite/artifacts'
shutil.copyfile(oldart/'design/nearai-only.json',DES/'nearai-only.json')
# Existing external experiment transport; independent from serving code and model scope.
shutil.copytree(oldart/'transport',ART/'transport')
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']='New workbook-question probe with explicit user-requested multi-turn continuation, scope switch and topic transition checks.'
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Frozen selected release reference','controls':'No new baseline calls'}, {'id':'selected-main','role':'candidate','derived_from':['baseline'],'changes':'None: selected code on local SQLite with isolated journals','controls':'Question and mode exactly from R2; fixed model and provider; no answer key in product input'}]
m['dataset'].update(name='R2 B03 B05 integration questions',version='20261104-r2',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
oldm=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1305-main135-nearai-sqlite/실험/manifest.json')
m['llm_policy']=oldm['llm_policy'];m['llm_policy']['provider_override'].update(path=str((DES/'nearai-only.json').relative_to(ROOT)),sha256=sha(DES/'nearai-only.json'))
m['runs'][0].update(arm_ids=['selected-main'],selection_rule=criteria['selection'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
m['design']['retrieval_stage_plan']['stages_by_arm']={'selected-main':[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]}
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
paths=[str((C/n).relative_to(ROOT)) for n in release['files']]
can=ac.snapshot(ADR,'selected-main',paths,experiment_id=m['experiment_id'],arm_id='selected-main',run_ids=['run-001']);ac.freeze(can);assert not ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];snap=can/'revisions'/rev['revision_id']/'snapshot'
put(DES/'candidate.json',{'code_root':str((snap/release['code_root']).relative_to(ROOT)),'selected_files':release['files'],'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}})
print(json.dumps({'generation':pointer['generation'],'files':len(paths),'groups':len(groups),'turns':sum(len(g['steps']) for g in groups),'manual':sum(r['classification']=='GENOS_UI_REQUIRED' for r in rows),'unbound':sum(r['classification']=='CONCRETE_INPUT_REQUIRED' for r in rows),'internal_documents':[(i,names[i]) for i in internal]},ensure_ascii=False))
