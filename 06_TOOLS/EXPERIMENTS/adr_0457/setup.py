from pathlib import Path
import json,shutil
R=Path.cwd();P=R/'04_EXPERIMENTS/ADR/ADR-0456-persistent-navigation-work-state';D=R/'04_EXPERIMENTS/ADR/ADR-0457-portable-synthesis-schema';A=D/'artifacts';T=R/'06_TOOLS/EXPERIMENTS/adr_0457';T.mkdir()
read=lambda p:json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
for f in ['dataset','grading']:shutil.copytree(P/'artifacts'/f,A/f)
for f in ['authorization.json','source-inventory.json']:shutil.copyfile(P/'artifacts'/f,A/f)
m=read(D/'실험/manifest.json');old=read(P/'artifacts/pre-call-manifest.json')
for k in ['design','dataset','llm_policy','retrieval_accounting']:m[k]=old[k]
h='Project minItems/maxItems out of synthesis/verification provider wire schema while retaining original local validation to remove observed400 without changing evidence, scopes, prompts or completion checks.'
m['lineage']['hypothesis_delta']=h;m['design'].update(hypothesis=h,success_criteria='portable18/18; no baseline-only regressions; no scope escapes/invalid quotes/provider errors; same14totalcalls/180s controller budget',implementation_scope='Only provider schema projection for navigation_synthesis/navigation_verify; unchanged original local JSON schema validation and receipts record both contracts',protocol_notes='Known18synthetic questions once per arm; no retries or adaptive changes. Parent456stateful complete failed synthesis schema; ADR0453 diagnostic observed array bound removal removes400. Semantic evaluation remains2blinded content judges.',controls='Same456fullworkstate, evidence, prompts, requirement/reference tasks, source corpus, metadata routing, mapping approvals, modelsettings, call/timebudget')
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-0456-experiment-v1/stateful'],'changes':'Frozen456stateful unchanged','controls':'same corpus/model/settings/budget'},{'id':'portable','role':'candidate','derived_from':['ADR-0456-experiment-v1/stateful'],'changes':m['design']['implementation_scope'],'controls':m['design']['controls']}];m['design']['code_isolation']['candidates']=[]
st=m['design']['retrieval_stage_plan']['stages_by_arm'];st['portable']=st.pop('stateful')
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['baseline','portable'],'selection_rule':'all18once, alternatingarms, fixedfollowup','status':'planned','artifact_path':str((A/'results.json').relative_to(R)),'sha256':'PENDING'}]
m['dataset'].update(version='portable457-v1',frozen_source=str((A/'dataset/product-cases.json').relative_to(R)));m['retrieval_accounting']['stage_ledger']['artifact_path']=str((A/'retrieval-ledger.json').relative_to(R))
write(D/'실험/manifest.json',m);write(A/'design-before-snapshot.json',m)
for f in ['fixtures.py','runtime.py','run_probe.py','score.py','finalize.py','test_routing.py','test_work_state.py']:
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0456'/f).read_text().replace('adr_0456','adr_0457').replace('ADR-0456','ADR-0457').replace('ADR456','ADR457').replace('persistent-navigation-work-state','portable-synthesis-schema').replace("'stateful'","'portable'")
 if f=='run_probe.py':s=s.replace('451,454,455]', '451,454,455,456]')
 if f=='runtime.py':
  s=s.replace('adr_0455/runtime.py','adr_0456/runtime.py').replace('ADR-0455-routing-validation-repair','ADR-0456-persistent-navigation-work-state').replace('parent455_runtime','parent456_runtime').replace('probe456binding','probe457binding').replace('stateful_navigation','portable_navigation').replace('adr_0457/stateful','adr_0457/portable')
  # Same dataset generation as parent, isolating transport projection.
 if f=='finalize.py':s=s.replace('ADR0454/run-001, baseline(ADR0451 mapped), routed(ADR0454).','ADR0457/run-001, baseline(ADR0456 stateful), portable(ADR0457).').replace('기존 mapped | 수정 routed','기존 stateful | 수정 portable').replace('위 structured_navigation 호출에 포함한다.','위 역할별 navigation 호출에 포함한다.')
 (T/f).write_text(s)
shutil.copyfile('/tmp/setup457.py',T/'setup.py')
