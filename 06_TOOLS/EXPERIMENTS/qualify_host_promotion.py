"""Prospective release-binding census; no product edits or model reruns."""
from pathlib import Path
import hashlib,json,re,sys
R=Path(__file__).resolve().parents[2]
A=R/'04_EXPERIMENTS/ADR/ADR-0872-host-assembly-promotion-contract'
P=R/'04_EXPERIMENTS/ADR/ADR-0870-host-owned-enum-contract'
L=R/'04_EXPERIMENTS/ADR/ADR-0871-host-owned-fulltext-live'
D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):
 assert not p.exists(),p
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');f=read(P/'artifacts/design/freeze.json');C=R/f['code_root']
mode=sys.argv[1]
if mode=='freeze':
 inputs=[P/'실험/manifest.json',P/'README.md',P/'artifacts/run-001/result.json',
 P/'artifacts/working-api.log',P/'artifacts/working-consumer.json',P/'artifacts/design/release-rebase.json',
 P/'artifacts/design/integration.json',P/'artifacts/design/freeze.json',P/'artifacts/design/baseline.json',
 P/'artifacts/main-prepare.log',P/'artifacts/working-resource-stop-001/RECEIPT.json',
 L/'실험/manifest.json',L/'artifacts/summary.json',Path(__file__).resolve()]
 criteria={'scope':'New promotion artifact integrity census over completed exact parent code; no implementation, model, prompt, parser or legal-quality re-evaluation.',
 'success':['Frozen evidence bytes unchanged','711 working/candidate files and370 staged serving files match','415 working tests and10 actual consumer checks recorded','16 actual external calls with0 schema errors,1 answer and1 incomplete retained honestly','MAIN82 baseline pointer unchanged','New promotion metadata has explicit true checks and no waiver'],
 'failure':['Any code/data/evidence drift','Hidden incomplete query or resource interruption','Changed historical experiment','Quality waiver'],
 'legal_holdout':False,'finite_integrity_census':True,'new_model_calls':0,'max_heavy_workers':1,
 'qualification_note':'Out-of-sample label applies to prospective release-binding conditions only; prior regressions and live questions remain observed/in-sample evidence, not new legal quality holdout.'}
 put(D/'criteria.json',criteria);put(D/'freeze.json',{'inputs':{str(p.relative_to(R)):sha(p) for p in inputs},'candidate':f['candidate'],'code_root':f['code_root'],'pointer':bound(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
 m.update(decision_eligible=True,in_sample=False)
 m['lineage']['hypothesis_delta']=criteria['scope']
 m['design'].update(hypothesis=criteria['scope'],primary_metric='Exact release identity, consumer evidence and qualification contract',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,release_rebase=bound(P/'artifacts/design/release-rebase.json'))
 m['design']['code_isolation']['reason']='No new product candidate. Read-only verification of immutable ADR0870 candidate bytes and completed evidence; share its code snapshot rather than duplicate data/code.'
 for arm in m['design']['arms']:
  arm.update(changes='Completed0870 evidence' if arm['id']=='baseline' else 'Promotion metadata and identity verification only; same0870 bytes',controls=['No product edits','No model calls','No historical results changed'])
 m['runs'][0].update(arm_ids=['qualified'],selection_rule=criteria['qualification_note'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
 m['llm_policy']['llm_calls']=[]
 m['dataset'].update(name='release-binding-finite-census',version='20261018-r1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
 reason='No retrieval/model effect comparison; exact immutable code and evidence integrity census.'
 m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
 (A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 print('Frozen new promotion identity census; no duplicated candidate or data')
elif mode=='run':
 frozen=read(D/'freeze.json');cm=read(R/f['candidate']['manifest_path']);rebase=read(P/'artifacts/design/release-rebase.json')
 live=read(L/'artifacts/summary.json');working=read(P/'artifacts/working-consumer.json')
 checks={'frozen_evidence':all(sha(R/n)==h for n,h in frozen['inputs'].items()),
 'candidate711_working_identical':len(cm['files'])==711 and all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files']),
 'serving370_staged_exact':len(rebase['staged_files'])==370 and all(sha(C/n)==h for n,h in rebase['staged_files'].items()),
 'working415_recorded':'Sequential aggregate: 415 passed' in (P/'artifacts/working-api.log').read_text(),
 'actual_consumer10':working['status']=='PASS' and len(working['checks'])==10 and all(working['checks'].values()),
 'actual_model_outcomes_retained':live['model_calls']==16 and live['schema_error_count']==0 and live['answer_count']==1 and len(live['cases'])==2,
 'no_schema_rejections':all(not x['generation_rejections'] for x in live['cases']),
 'MAIN82_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(P/'artifacts/design/baseline.json')['pointer_sha256'],
 'resource_interruption_preserved':(P/'artifacts/working-resource-stop-001/RECEIPT.json').is_file(),
 'parent_completed':read(P/'실험/manifest.json')['reservation']['status']=='completed'}
 assert all(checks.values()),checks
 result={'status':'complete','strict_success':True,'checks':checks,'candidate':f['candidate'],'real_model_calls':0,'quality_certified':False,'limitations':['Integrity census only, no new legal holdout or model rerun.','0871 one query review_incomplete retained; no claim of all-answer success.','GENOS internal grammar/model/deployment unverified.','Working resource stop and prepare metadata rejection preserved.']}
 put(A/'artifacts/run-001/result.json',result)
 m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
 m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','basis':'Completed0870 preserved'},'qualified':{'status':'complete','strict_success':True,'checks':len(checks)}},comparisons=[],usage={'product_model_calls':0,'offline_evaluator_calls':0},error_taxonomy=[])
 (A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 meta=(A/'README.md').read_text().split('---',2)[1]
 for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('decision_eligible','true'),('in_sample','false')]:meta=re.sub(r'(?m)^'+k+r':.*$',k+': '+v,meta)
 heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
 texts=['Accepted promotion-candidate. Exact completed0870 bytes; no product changes.', '0870 completion omitted promotion-candidate metadata and explicit result checks. Stable prepare correctly rejected before MAIN mutation. Preserve completed record.',json.dumps(read(D/'criteria.json'),ensure_ascii=False),'Prospective finite release-binding census. Prior technical/model observations retained, not relabeled legal holdout.','Shared immutable0870 snapshot711files and current data. No new model calls.',json.dumps(result,ensure_ascii=False),'Historical prepare rejection and resource stop remain in0870 artifacts. This run passes all10 integrity checks.','No fulltext reload, data copy or model call. Hash small code/evidence only.','Qualification links the actual verified code and consumers without weakening release checks.', '\n'.join(result['limitations']),'Use stable prepare/check/apply with user-authorized confirm-main; verify active service. Rollback to prior release while retaining original state/history.','qualify_host_promotion.py freeze; run; stable status/hash/validate --final/graph; prepare/apply; active consumer.']
 (A/'README.md').write_text('---'+meta+'---\n\n# 시스템 조립 승격 결속\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
 (A/'실험/README.md').write_text('# 승격 결속 검사\n\n제품 코드는 완료0870 그대로. 새로운10개 결속 검사를 실행하며 모델/법률 평가를 재실행하지 않는다.\n')
 paths=[p for p in (A/'artifacts').rglob('*') if p.is_file()]
 put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen release binding census','contains_raw_prompts_and_outputs':False} for p in paths]})
 print(checks)
else:raise ValueError(mode)
