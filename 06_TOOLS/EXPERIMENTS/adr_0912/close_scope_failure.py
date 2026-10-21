from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0912-answer-first-user-followup';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
runs={p.parent.name:read(p) for p in (O/'baseline').glob('*/result.json')}
result={'status':'invalid','reason':'Runner selected risk_team while CM001 source belongs to financial_team. Paired model performance comparison invalid; candidate was never sent to model.','baseline':runs,'contracts':read(A/'artifacts/contract-disposition.json'),'scope_stop':read(A/'artifacts/scope-stop.json'),'candidate_model_calls':0,'working_code_integrated':False,'main_changed':False}
put(O/'result.json',result)
put(A/'artifacts/contracts-result.json',{'status':'complete','candidate_passed':115,'candidate_failed':7,'baseline_same_failures':7,'candidate_model_calls':0,'finite_only':True,'candidate_binding':read(D/'answer-first-binding.json')})
m=read(A/'실험/manifest.json');m['runs'][0].update(status='invalid',sha256=sha(O/'result.json'))
m['runs'].append({**m['runs'][0],'id':'contracts','status':'complete','selection_rule':'Finite software/API checks; no external model. Seven legacy failures reproduced on baseline.','artifact_path':str((A/'artifacts/contracts-result.json').relative_to(R)),'sha256':sha(A/'artifacts/contracts-result.json')})
m['results'].update(status='complete',by_arm={'baseline':{'status':'invalid','reason':'wrong team scope; first failed, second interrupted'},'answer-first':{'status':'complete','scope':'115 passed finite checks; seven existing failures; external model run not executed'}},comparisons=[],judge_disagreements=None,usage={'product_model_calls':sum(v.get('model_calls_total',v.get('model_calls',0)) for v in runs.values()),'offline_evaluator_calls':0},latency={'comparable':False},error_taxonomy=['RUNNER_WRONG_TEAM_SCOPE'])
why='The model comparison is invalid: wrong team scope excludes requested CM001 original. No candidate live run. Only finite technical/API checks are complete; no retrieval quality claim.'
m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',summary_run_id=None,artifact_path=None,sha256=None,not_applicable_reason=why)
# Incomplete model runs are preserved, not counted as measured search-quality stages.
m['design']['retrieval_stage_plan']['stages_by_arm']={}
put(A/'실험/manifest.json',m)
meta=(A/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Proposed',meta)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=['확인된 원문 우선 ASSESS 및 근거 있는 답변 우선 정책을 격리 구현했다. 소프트웨어 검사를 완료했으나 외부 모델 비교는 실행기 팀 범위 오류로 invalid다.','기존 선택기가 가정적 예외를 계속 조사하고 ASSESS도 답변을 미뤘다.',json.dumps(read(D/'criteria.json'),ensure_ascii=False,indent=2),'동일 working baseline과 answer-first, CM001 후속과 CM033. 단일 프로세스 순차 실행.','고정 714개 코드 파일, Qwen3.8/Parasail FP8/reasoning none/no fallback. 공유 데이터. 정확한 freeze 및 preflight 변경 기록 보존.',json.dumps(result,ensure_ascii=False,indent=2),'실행기의 risk_team 공개 28문서 범위에는 financial_team의 코스닥시장 상장규정이 없다. CM001은4회 후422, CM033은 중단. 후보는 미실행.','모델·사용량은 baseline 시나리오별 result.json, RAM receipt. 원시 wire/canonical/runtime 보존. 비교 속도 미측정.','자료 부재는 저장소 데이터 부재가 아니라 실행 요청의 잘못된 팀 선택 때문이다. ACL은 올바르게 차단했다.','115개 검사 통과. 기존7개 실패 동일 재현. 의미 성능 검증 전이므로 MAIN 승격 불가.','작업 코드·MAIN87·GENOS 미변경. 후속 ADR에서 financial_team 범위를 사전 동결하고 동일 후보를 다시 검증한다.','setup/implement/seal/run_tests/live와 design/freeze.json. 실패 경로를 덮어쓰지 않는다.']
(A/'README.md').write_text('---'+meta+'---\n\n# 확인된 근거 우선 답변과 사용자 후속 조사\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{p}' for i,(h,p) in enumerate(zip(heads,parts),1))+'\n')
qheads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
questions={t['id']:t['question'] for s in read(D/'cases.json') for t in s['turns']}
for q in m['questions']:
 cid=q.get('id',q.get('case_id'));cid=cid if cid in questions else next((x for x in sorted(questions,key=len,reverse=True) if x in q['file']),None)
 parts=['run-001 invalid; contracts complete',questions.get(cid,str(q)),'정답 미주입, 승인 gold와 모델 judge 없음.','design/cases.json, freeze.json 및 request.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n잘못된 팀 범위로 모델 비교 invalid. 원시 자료 보존, 회수 품질 집계 없음.','artifacts/run-001/baseline 및 preflight-admission의 gzip wire/canonical, raw와 runtime.','실제 calls.json. 후보 외부 호출0회.','115 finite API/contract pass, seven legacy failures reproduced on baseline.','실행기 팀 선택 오류. 후속 ADR 필요.']
 (A/'실험'/q['file']).write_text('# 실행과 실패 기록\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{p}' for i,(h,p) in enumerate(zip(qheads,parts),1))+'\n')
(A/'실험/README.md').write_text('# 질문 인덱스\n\n'+'\n'.join(f"- [{q.get('id',q['file'])}]({q['file']})" for q in m['questions'])+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Failed-scope probe, frozen code and finite contract audit','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm'))]})
(A/'RESULT.txt').write_text('격리 구현 및 소프트웨어115개 통과. 기존7개 실패 동일 재현.\nCM001financial_team 자료를 risk_team 세션에서 조회하여 모델 비교 invalid. 후보 외부 모델 호출0회.\n작업 코드·MAIN87·GENOS 미변경. 정확한 금융팀 범위로 후속 검증 필요.\n')
