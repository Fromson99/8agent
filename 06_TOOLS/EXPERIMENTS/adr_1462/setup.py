"""Freeze both arms (selected MAIN178 release code / staged candidate MAIN178 + declared names),
six public-document questions, grading targets and limits before any model call.

Questions use a law abbreviation the corpus declares (「…」(이하 "…"라 한다)) and that MAIN178's
document-name matching cannot resolve (checked offline before freezing), plus one control asked
with the full title. Targets (law + article) go only to the grading file.
"""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==178 and ptr['release_id']=='unread-labels-20261108-r1'
rel=read(ROOT/ptr['manifest_path']);B=ROOT/rel['code_root'];base_files=rel['files']
assert len(base_files)==544 and all(sha(B/n)==h for n,h in base_files.items())
audit=ROOT/'09_ARTIFACTS/AUDITS/20261108-declared-names';mr=read(audit/'main-release.json')
stage=mr['stage'];assert stage['name']=='staged-r4' and stage['status']=='PASSED' and stage['base_release_id']==ptr['release_id']
assert mr['test']['status']=='PASSED' and not mr['test']['new_failures'] and mr['test']['inventory_sha256']==stage['inventory_sha256']
S=ROOT/stage['code_root'];cand_files=stage['files'];assert all(sha(S/n)==h for n,h in cand_files.items())
product=sorted(n for n in cand_files if n.endswith('.py') and cand_files[n]!=base_files.get(n))
assert product==['02_BACKEND/semantic_runtime/legal_agent/declared_names.py','02_BACKEND/semantic_runtime/legal_agent/law_candidates.py','02_BACKEND/semantic_runtime/legal_agent/query_scope.py'],product
assert '판정: 통과' in (audit/'pytest-guard-r4/보고서.txt').read_text()
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
public=read(B/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
assert read(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']==public
LAW={'audit':'주식회사 등의 외부감사에 관한 법률','audit-r':'주식회사 등의 외부감사에 관한 법률 시행령','fair':'독점규제 및 공정거래에 관한 법률',
     'esec':'주식·사채 등의 전자등록에 관한 법률','issue':'증권의 발행 및 공시 등에 관한 규정'}
CASES=[('d1-audit-10','외부감사법상 회사는 감사인을 언제까지 선임해야 하나요?','외부감사법','audit','제10조'),
       ('d2-audit-r-5','외부감사법 시행령에서 외부감사를 받아야 하는 회사의 자산총액 기준은 얼마인가요?','외부감사법 시행령','audit-r','제5조'),
       ('d3-fair-31','공정거래법상 상호출자제한기업집단은 어떤 기준으로 지정되나요?','공정거래법','fair','제31조'),
       ('d4-esec-35','전자증권법에 따라 전자등록계좌부에 전자등록된 자는 어떤 권리를 가진 것으로 추정되나요?','전자증권법','esec','제35조'),
       ('d5-issue-2-3','발행·공시규정에서 증권신고서 효력발생시기의 특례는 어떻게 되나요?','발행·공시규정','issue','제2-3조'),
       ('c1-audit-10-full','주식회사 등의 외부감사에 관한 법률상 회사는 감사인을 언제까지 선임해야 하나요?',None,'audit','제10조')]
# Offline evidence, before freezing: MAIN178 name matching does not resolve the abbreviation; the
# candidate's declaration lookup finds a 「title」 in the public financial scope that is the target law.
import sqlite3
data=ROOT/rel['data_path'];store=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True)
names={d:n for d,n in store.execute('SELECT document_id,name FROM document')}
fin=sorted(d for d in public if 'financial_team' in names.get(d,''));title={d:names[d].split(' > ')[-1] for d in fin}
target_doc={k:next(d for d,t in title.items() if t==v) for k,v in LAW.items()}
sys.path[:0]=[str(S/'02_BACKEND')]
from semantic_runtime.legal_agent import declared_names as dn,query_scope as qs
from semantic_runtime.navigation_match import norm
from semantic_runtime.unit_fulltext import UnitFulltextIndex
index=UnitFulltextIndex(data/'fulltext',read(data/'navigation/manifest.json'));db=index.connect()
offline=[]
for cid,q,abbr,law,art in CASES:
 row={'case_id':cid,'abbreviation':abbr,'target_document':LAW[law]}
 if abbr:
  row['main178_name_match']=[title[d] for d in fin if norm(abbr)==norm(title[d]) or qs.abbreviates(abbr,title[d])]
  queries,report=dn.expand(type('S',(),{'matcher':type('M',(),{'unit_fulltext':index,'unit_fulltext_db':db})()})(),[q],None)
  row['candidate_added_queries']=report['added_queries'];row['declarations']=[(r['name'],r['long_form'],r['document_name'].split(' > ')[-1]) for r in report['declarations'] if r['kind']=='TITLE']
  assert not row['main178_name_match'] and row['candidate_added_queries'],row
 offline.append(row)
db.close()
put(DES/'offline-lookup.json',offline)
criteria={'authorization':'실함ㄱㄱ (구현한 이하 약칭 검색을 실제 모델로 실험)',
 'scope':'Six questions in 외규 mode over the public grant intersected with the financial team (44 public financial documents), local SQLite generation of MAIN178. Each question once per arm, independent requests, baseline before candidate. baseline = selected MAIN178 release code (unchanged); candidate = staged-r4 (MAIN178 + declared_names.py, law_candidates.py, query_scope.py; tests and Oracle scale guard passed). Both through the arm code tree\'s own service.py local-release path with the same data, profile, model and transport. No MAIN change.',
 'required':['Arm code bytes unchanged during the run; every loaded semantic_runtime module from the arm tree',
   'Primary: target article acquired (read) per question — the law the abbreviation names, at the frozen article; secondary: any original of the target law acquired',
   'Mechanism: candidate records DECLARED_NAME_QUERIES with the 「title」 query on the abbreviation questions; control question unchanged between arms',
   'Answer correctness checked by hand against the stored original of the target article; source-only, questions back or partial replies are not full answers',
   'Source/ACL/wire integrity, physical calls recorded, duplicate request adds 0 calls'],
 'limits':{'physical_total':200,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':1.5,'time_box_minutes':45,'ram_start_gib':5,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':128,'global_swap_growth_mib':512,'workers':1},
 'stop':'UNKNOWN ends that request without retry; next independent request allowed. Three consecutive UNKNOWN requests, source/ACL/code/resource violation, total budget or the 45-minute time box (checked before each next request) stop the batch. No other tests or model work in this session while the batch runs.',
 'quality_certified':False,'in_sample':True,'order':[c[0] for c in CASES],
 'note':'Questions were written for this experiment from declarations found in the corpus; one run per arm; a difference is an observation, not a rate. The model may know an abbreviation by itself (외부감사법) — that is part of what is measured.'}
cases=[{'id':cid,'arms':['baseline','candidate'],'document_ids':public,'steps':[{'number':1,'question':q,'mode':'외규'}]} for cid,q,*_ in CASES]
grades=[{'id':cid,'abbreviation':abbr,'target':{'law':LAW[law],'document_id':target_doc[law],'article':art}} for cid,q,abbr,law,art in CASES]
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades);put(DES/'live-cases.json',cases)
put(DES/'provider-policy.json',read(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
assert read(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==read(DES/'provider-policy.json')==read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')
put(DES/'authorization.json',{'request':criteria['authorization'],'documents':public,'scope':'Experiment-authored questions about public law documents only (local-gemma-public grant); originals are public law texts'})
transport=ART/'transport';transport.mkdir()
pins=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
 target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
put(transport/'transport-pins.json',pins)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis='Reading the corpus\'s own name declarations at request time lets an abbreviation question reach the law it names (search query with the 「title」, scope resolution).',primary_metric='Target article acquired per question, baseline vs candidate',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':stages,'candidate':stages}
for arm in m['design']['arms']:
 if arm['id']=='baseline':arm.update(changes='Selected MAIN178 release code unchanged (544 files)',controls='Same questions, data generation, grant, profile, model and transport')
 else:arm.update(changes='MAIN178 + declared_names.py/law_candidates.py/query_scope.py (staged-r4, derived pins refreshed)',controls='Same as baseline')
m['dataset'].update(name='declared-name abbreviation questions (experiment-authored)',version='adr1462-v1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'candidate',list(cand_files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
for n,h in cand_files.items():
 if not (can/'snapshot'/n).exists() or sha(can/'snapshot'/n)!=h:
  (can/'snapshot'/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(S/n,can/'snapshot'/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
snapshot=can/'revisions'/rev['revision_id']/'snapshot';assert all(sha(snapshot/n)==h for n,h in cand_files.items())
arms={'baseline':{'code_root':rel['code_root'],'files':base_files,'label':ptr['release_id']},
      'candidate':{'code_root':str(snapshot.relative_to(ROOT)),'files':cand_files,'label':'declared-names-staged-r4','pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}}
put(DES/'arms.json',arms)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(arms['candidate']['pin'],candidate_id='candidate',experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'],runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py')))])
put(ADR/'실험/manifest.json',m)
put(ART/'preparation-issues.json',[
 {'step':'setup attempt 1','model_calls':0,'issue':'Freeze check read the test record new_failures as an int; the tool stores a list. Check corrected, no design written.'},
 {'step':'setup attempt 2','model_calls':0,'issue':'Offline lookup before freezing found no expansion for 공정거래법상 (staged-r3): the tagger reads 상 as a noun suffix, so the noun part became 공정거래법상. Product fix (readings may end up to 2 characters before the noun end), new unit case, and reverse-direction names no longer added as queries (noise seen on the frozen questions: 감사인→회계감사인). Restaged as staged-r4 and re-verified (tests, Oracle scale guard, Oracle declared check) before this freeze.'}])
paths=[*Path(__file__).parent.glob('*.py'),*(DES/x for x in ('criteria.json','live-cases.json','authorization.json','provider-policy.json','arms.json','grading-only.json','offline-lookup.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('Frozen MAIN178 baseline + staged-r4 candidate, 6 questions x 2 arms, budget 200 calls/$1.5/45min; model 0')
