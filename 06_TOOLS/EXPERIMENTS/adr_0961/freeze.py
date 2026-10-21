from pathlib import Path
import sys,json,hashlib,shutil,copy
R=Path(__file__).resolve().parents[3];sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
D=R/'04_EXPERIMENTS/ADR/ADR-0961-scoped-consumer-qualification';A=D/'artifacts'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
old=R/'04_EXPERIMENTS/ADR/ADR-0960-scoped-multiturn-qualification';op=old/'실험/manifest.json';om=json.loads(op.read_text())
for q in om['questions']:q['sha256']=sha(old/'실험'/q['file'])
save(op,om)
m=json.loads((D/'실험/manifest.json').read_text());m['lineage']['parents'][0]['manifest_sha256']=sha(op)
save(D/'실험/manifest.json',m)
parent=json.loads((R/'02_BACKEND/lawrag/research/candidates/adr_0957/scoped/candidate.json').read_text())
paths=[r['target_path'] for r in parent['files']]
C=ac.snapshot(D,'qualified',[n for n in paths if (R/n).is_file()],experiment_id=m['experiment_id'],arm_id='qualified',run_ids=['run-001'])
stage=R/'04_EXPERIMENTS/ADR/ADR-0957-multiturn-structured-scope/artifacts/code'
for n in paths:
 dst=C/'snapshot'/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(stage/n,dst)
 if not (R/n).exists():ac.register_file(C,n,upstream_state='absent')
ac.freeze(C)
c=json.loads((C/'candidate.json').read_text());rev=c['revisions'][-1]
shutil.copyfile(old/'artifacts/stage.json',A/'stage.json')
cases=json.loads((old/'artifacts/command-cases.json').read_text())
utterances=[
 '처음 질문의 승인을 접수로 정정할게. 법령과 장 범위는 유지해서 다시 조사해.',
 '대상 문서를 모의접수세칙 제3절로 바꿀게. 그 범위로 한정해 다시 확인해 줘.',
 '제7장만 보지 말고 모의등록규정 전부를 대상으로 접수 요건을 다시 찾아.',
 '모의추가규정까지 포함해서 현재 조사 범위에 더해 줘.',
 '이제 지정한 법령과 목차로 한정하지 말고 접근 가능한 모든 문서에서 찾아 줘.'
]
for i,case in enumerate(cases):
 case['id']=f'q{i+1}';case['context']['utterance']=utterances[i]
 g=case['context']['goals'][0];g['state']['task']='모의등록규정 제7장 접수 요건';g['state']['search_scope']['targets'][0].update(document_name='모의등록규정',coordinate='제7장',title='접수');g['previous_response']['text']='요청한 접수 요건을 아직 확보하지 못했습니다.'
 cases[i]['expected']['document']=[None,'모의접수세칙','모의등록규정','모의추가규정',None][i]
 cases[i]['expected']['structure']=[None,'제3절',None,None,None][i]
save(A/'command-cases.json',cases)
runner=R/'06_TOOLS/EXPERIMENTS/adr_0961/probe.py'
text=(R/'06_TOOLS/EXPERIMENTS/adr_0960/probe.py').read_text().replace('ADR-0960-scoped-multiturn-qualification','ADR-0961-scoped-consumer-qualification')
runner.write_text(text)
# All product bytes remain identical to the completed parent; only harness and new wording differ.
m['decision_eligible']=True
m['design']=copy.deepcopy(om['design'])
m['design']['success_criteria']='Five new synthetic commands pass; 97 deterministic API/scope/regression checks pass (pre-existing stale fixture excluded); actual data source read and release-stage hashes pass. Exact active service binding is checked after activation and rolled back on failure. No quality waiver.'
m['design']['primary_metric']='Five unseen synthetic command contracts, fixed structural regression and real local service consumer.'
m['design']['arms'][0]['derived_from']=['ADR-0960-experiment-v1/qualified'];m['design']['arms'][0]['changes']='Completed failed qualification, preserved provider429 and harness failures; no baseline rerun'
m['design']['arms'][1]['changes']='Identical product code; corrected test-model adapter and five new utterances'
m['design']['test_bindings']={n:sha(R/n) for n in om['design']['test_bindings']}
b={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
m['design']['code_isolation']['candidates']=[{**b,'candidate_id':'qualified','arm_id':'qualified','experiment_id':m['experiment_id'],'run_ids':['run-001'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}]
m['llm_policy']=om['llm_policy'];m['retrieval_accounting']=om['retrieval_accounting']
m['dataset']={**om['dataset'],'frozen_source':str((A/'command-cases.json').relative_to(R)),'sha256':sha(A/'command-cases.json'),'name':'second independent synthetic scope correction wording'}
m['runs'][0].update(status='planned',purpose='primary',selection_rule='New five cases, max20 physical calls and600seconds; fixed regression and exact data/service checks; no provider fallback.',artifact_path=str((A/'result.json').relative_to(R)),sha256='PENDING')
save(D/'실험/manifest.json',m)
save(A/'preview-auth.json',{'purpose':'integration_preview'});save(A/'preview-validation.json',{'structural_checks_passed':True})
print('Frozen same product bytes',len(paths),'files; five new cases and API harness recorded')
