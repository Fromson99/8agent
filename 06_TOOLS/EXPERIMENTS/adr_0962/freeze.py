from pathlib import Path
import json,hashlib,shutil,sys,copy
R=Path(__file__).resolve().parents[3];sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
D=R/'04_EXPERIMENTS/ADR/ADR-0962-scoped-clear-boundary';A=D/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0962/guarded-current';stage=A/'code'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
new='02_BACKEND/semantic_runtime/legal_agent/query_scope.py';shutil.copyfile(C/'snapshot'/new,stage/new)
for p in (stage/'02_BACKEND/ENGINES').rglob('*.json'):
 m=json.loads(p.read_text())
 if 'files' in m:
  for n in m['files']:m['files'][n]=sha(stage/n)
  save(p,m)
p=stage/'00_SYSTEM/PIPELINE.json';conf=json.loads(p.read_text())
def pins(v):
 if isinstance(v,dict):
  if v.get('manifest') and 'sha256' in v and (stage/v['manifest']).is_file():v['sha256']=sha(stage/v['manifest'])
  for c in v.values():pins(c)
 elif isinstance(v,list):
  for c in v:pins(c)
pins(conf);save(p,conf)
c=json.loads((C/'candidate.json').read_text())
for row in c['files']:shutil.copyfile(stage/row['target_path'],C/'snapshot'/row['target_path'])
ac.freeze(C);c=json.loads((C/'candidate.json').read_text());rev=c['revisions'][-1]
seal=json.loads((A/'stage.json').read_text());seal['files']={n:sha(stage/n) for n in seal['files']};save(A/'stage.json',seal)
for file in ('probe.py','consumer.py'):
 txt=(R/'06_TOOLS/EXPERIMENTS/adr_0961'/file).read_text().replace('ADR-0961-scoped-consumer-qualification','ADR-0962-scoped-clear-boundary').replace('ADR-0957-multiturn-structured-scope','ADR-0962-scoped-clear-boundary')
 if file=='probe.py':txt=txt.replace('max_calls=20','max_calls=24')
 else:
  txt=txt.replace("node=next((u for (d,u),n in qs.units(matcher,did) if (did,u) in matcher.stored_coordinates and n.get('family')=='kr_article' and n.get('coordinate_binding',{}).get('mode')!='unresolved'),None)","from collections import Counter\n counts=Counter(matcher.stored_coordinates[d,u].canonical_surface() for (d,u),n in qs.units(matcher,did) if (d,u) in matcher.stored_coordinates)\n node=next((u for (d,u),n in qs.units(matcher,did) if (did,u) in matcher.stored_coordinates and counts[matcher.stored_coordinates[d,u].canonical_surface()]==1 and n.get('family')=='kr_article' and n.get('coordinate_binding',{}).get('mode')!='unresolved'),None)")
 (R/'06_TOOLS/EXPERIMENTS/adr_0962'/file).write_text(txt)
txt=(R/'06_TOOLS/EXPERIMENTS/adr_0957/run_contracts.py').read_text().replace('ADR-0957-multiturn-structured-scope','ADR-0962-scoped-clear-boundary');(R/'06_TOOLS/EXPERIMENTS/adr_0962/run_contracts.py').write_text(txt)
old=R/'04_EXPERIMENTS/ADR/ADR-0961-scoped-consumer-qualification';cases=json.loads((old/'artifacts/command-cases.json').read_text());reg=copy.deepcopy(cases[2]);reg['id']='regression-q3';reg['split']='in_sample_regression'
utterances=['방금 못 찾은 내용을 접수 기한으로 수정해서 조사해 줘. 지정한 장과 문서는 계속 유지해.', '이번에는 가상개정규정 제4절만 대상으로 삼아서 같은 내용을 찾아 줘.', '제7장 제한은 풀어 줘. 모의등록규정 전체의 접수 요건을 조사해.', '지금 조사에 가상운영세칙도 추가해서 확인해 줘.', '법령과 목차 조건을 지우고 권한 내 모든 문서를 대상으로 다시 조사해 줘.']
for i,x in enumerate(cases):
 x['id']=f'u{i+1}';x['split']='out_of_sample';x['context']['utterance']=utterances[i];x['expected']['document']=[None,'가상개정규정','모의등록규정','가상운영세칙',None][i];x['expected']['structure']=[None,'제4절',None,None,None][i]
cases.append(reg);save(A/'command-cases.json',cases)
m=json.loads((D/'실험/manifest.json').read_text());om=json.loads((old/'실험/manifest.json').read_text());m['design']=copy.deepcopy(om['design']);m['decision_eligible']=True
m['design']['hypothesis']='Explicit document versus structure removal plus named-document CLEAR rejection prevents accidental widening while preserving multi-turn correction.'
m['design']['primary_metric']='Five unseen command contracts plus one prior failed regression; all critical deterministic source/scope/API/service assertions pass.'
m['design']['success_criteria']='All5 out-of-sample commands and1 in-sample regression pass;98 deterministic contracts and real data scoped read/service/hash checks pass; post-activation exact active binding or rollback. No waiver.'
m['design']['arms'][0].update(derived_from=['ADR-0961-experiment-v1/qualified'],changes='Completed rejected parent; raw error preserved, no model rerun');m['design']['arms'][1].update(id='guarded',changes='Explicit scope-removal prompt and host rejection when a CLEAR utterance names an authorized document')
m['design']['test_bindings']={n:sha(R/n) for n in ['05_TESTS/CONTRACTS/test_unattempted_gap_finish.py','05_TESTS/CONTRACTS/test_scoped_multiturn_api.py','05_TESTS/CONTRACTS/test_multiturn_structured_scope.py','06_TOOLS/EXPERIMENTS/adr_0962/run_contracts.py','06_TOOLS/EXPERIMENTS/adr_0962/consumer.py']}
b={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
runner=R/'06_TOOLS/EXPERIMENTS/adr_0962/probe.py';m['design']['code_isolation']['candidates']=[{**b,'candidate_id':'guarded-current','arm_id':'guarded','experiment_id':m['experiment_id'],'run_ids':['run-001'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}]
m['design'].pop('release_rebase',None)
m['dataset']={**om['dataset'],'frozen_source':str((A/'command-cases.json').relative_to(R)),'sha256':sha(A/'command-cases.json'),'name':'Five new scope utterances and separately labeled prior failed regression'};m['llm_policy']=om['llm_policy'];m['llm_policy']['llm_calls'][0]['max_calls']=24;m['retrieval_accounting']=om['retrieval_accounting'];m['runs'][0].update(status='planned',purpose='primary',selection_rule='Five unseen cases plus labeled in-sample q3 regression; max24calls and600sec. Exact source/ACL/state required.',artifact_path=str((A/'result.json').relative_to(R)),sha256='PENDING');save(D/'실험/manifest.json',m)
save(A/'preview-auth.json',{'purpose':'integration_preview'});save(A/'preview-validation.json',{'structural_checks_passed':True})
print('Frozen guarded candidate',len(c['files']))
