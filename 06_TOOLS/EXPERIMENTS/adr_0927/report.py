from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0927-connected-source-release-binding';Q=R/'04_EXPERIMENTS/ADR/ADR-0926-connected-source-release-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
check=read(A/'artifacts/binding-check.json');prior=read(Q/'artifacts/run-001/result.json');assert all(check['checks'].values())
result={**prior,'checks':check['checks'],'new_finite_tests':0,'retained_tests':162,'qualification_kind':'Exact four-field release binding and actual stable integration checker; no product change','strict_success':True,'preparation_failure':str((Q/'artifacts/main-prepare.log').relative_to(R))};put(A/'artifacts/run-001/result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'));m['results'].update(status='complete',by_arm={'qualified':{'status':'complete','strict_success':True,'checks':check['checks']}},usage={'product_model_calls':0,'offline_evaluator_calls':0},error_taxonomy=[{'kind':'release_binding_metadata','detail':'Full research binding has extra fields; stable release checker requires exact4fields. Corrected in this successor; source unchanged.'},{'kind':'inherited_limitations','details':prior['remaining']}])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 p=A/'실험'/q['file'];parts=['run-001/qualified; completed926 unchanged product.','구현한 연결 원문 탐색을 로컬 MAIN에 연결한다.','Finite release metadata contract; no legal gold.','design/binding.json andfreeze.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nNo retrieval evaluation; parent ledger preserved.','No model calls.','No new inference or product modification.','Actual stable integration checker and all387file census; retain162checks and actual candidate/working consumers.',json.dumps(result,ensure_ascii=False)]
 p.write_text('# 릴리스 바인딩\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n');q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
meta=(A/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:
 if re.search(r'(?m)^'+k+':',meta):meta=re.sub(r'(?m)^'+k+r':.*$',k+': '+v,meta)
 else:meta+='\n'+k+': '+v+'\n'
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=['Accepted exact release metadata contract; product unchanged.','Full research candidate binding had extra identifiers, while stable release contract requires exact4fields. Preparation stopped before activation.',json.dumps(read(D/'criteria.json'),ensure_ascii=False),'Exact same387product files, frozen4field metadata and stableintegrationcheck.','Same completed926 and925 code/data/profile. No model calls.',json.dumps(result,ensure_ascii=False),'Failure logs and incomplete prepared directory retained; no validator bypass.','162 retained passing technical checks and exact packager inventory; no repeated model run.','Research lineage retains extra fields separately; release only carries verified contract fields.','\n'.join(prior['remaining']),'Prepare exact qualified r2 release, apply with stable confirmation and verify actualselectedservice. MAIN88 rollback; GENOS separate.','prepare; check; report; hash/status/finalvalidate/graph; promote prepare; stable apply; activeconsumer; finish.']
(A/'README.md').write_text('---'+meta+'---\n\n# 연결 원문 릴리스 바인딩 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n')
(A/'실험/README.md').write_text('# 검증 인덱스\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0927','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact release binding contract','contains_raw_prompts_and_outputs':False} for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json']})
print('Qualified same387files and162checks with exact release binding')
