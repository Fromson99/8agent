"""Document completed local MAIN only after actual selected service verification."""
from pathlib import Path
import json,hashlib,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');s=read(A/'artifacts/main-smoke.json');m=read(R/p['manifest_path']);result=read(A/'artifacts/run-001/result.json');assert s['status']=='passed' and s['pointer']==p and result['strict_success']
assert p['deployment_basis']=='VALIDATED_ADR_PROMOTION' and m['qualification']['source']['sha256']==sha(A/'실험/manifest.json')
for f,h in m['files'].items():assert sha(R/f)==sha(R/m['code_root']/f)==h,f
rebase=read(A/'artifacts/design/release-rebase.json');assert rebase['staged_files']==m['files']
profile_resolution=s['profile_resolution'];assert sha(R/profile_resolution['path'])==profile_resolution['sha256']
assert s['effective_frozen_service_equals_actual_runtime_profile'] and s['native_binding']==s['effective_frozen_service_binding']
receipts=[]
for f in (R/'01_DATA/ACTIVE/local/receipts').glob('semantic-apply-*.json'):
 v=read(f)
 if v.get('after',{}).get('release_id')==p['release_id'] and v['after'].get('release_manifest_sha256')==p['release_manifest_sha256']:receipts.append({'path':str(f.relative_to(R)),'sha256':sha(f),'action':v['action'],'quality_gate_override':v['quality_gate_override']})
assert len(receipts)==1 and receipts[0]['quality_gate_override'] is False
row=result['by_arm']['integrated'];counts={k:len(v) for k,v in result['semantic_outcomes'].items()}
record={'status':'complete','environment':'WSL local MAIN','selected_release':p,'code_root':m['code_root'],'data_generation':m['data_path'],'serving_files':len(m['files']),'exact_working_candidate_release_match':True,'source_result_sha256':sha(A/'artifacts/run-001/result.json'),'source_manifest_sha256':sha(A/'실험/manifest.json'),'apply_receipt':receipts[0],'real_entrypoint':s['entrypoint'],'service_execution_binding':s['execution_binding'],'native_execution_binding':s['native_binding'],'main_smoke_sha256':sha(A/'artifacts/main-smoke.json'),'semantic_outcomes':counts,'regression_successes':sum(x['http_status']==200 for x in result['regressions']),'contract_tests_passed':146,'genos_deployed':False,'git_main_merged':False,'resident_server_restarted':False}
record.update({'profile_resolution':profile_resolution,'evaluation_binding':s['evaluation_binding'],'effective_frozen_service_binding':s['effective_frozen_service_binding'],'nominal_evaluation_equals_actual_runtime_profile':s['nominal_evaluation_equals_actual_runtime_profile'],'effective_frozen_service_equals_actual_runtime_profile':True})
observation=A/'artifacts/main-response-observation.json';assert observation.exists()
record['main_response_observation']={'path':str(observation.relative_to(R)),'sha256':sha(observation)}
put(A/'artifacts/main-completion.json',record)
(A/'MAIN_RESULT.md').write_text(f"""# 조사 제어 통합의 로컬 MAIN 완료

로컬 MAIN은 `{p['release_id']}` / 포인터 generation **{p['generation']}**다. 통합 작업 코드·동결 검증 후보·선택 릴리스의 서빙 파일 {len(m['files'])}개가 같은 해시임을 확인했다. 기존 작업 코드의 다른 수정은 보존했다.

계약·회귀 검사 **146개** 통과, 별도 서빙 패키지·엔진 의존성·접근권한 검사 통과. 사전 동결한 독립 질문32개와 알려진 회귀8개를 각각1회 실행했다. 독립 질문의 정상 응답은 {row['request_success_count']}/32, 원문 기반 단일 judge의 세부 정답은 {row['correct_count']}/32다. 의미 정답·판단 실수·미답변의 분류는 `{counts}`이며 세부 정답 전부를 승격 조건으로 삼지 않았다. 회귀 정상 응답은 {record['regression_successes']}/8이다. 안전하게 거절된 모델 선택·인용과 예산 초과는 실제 응답 그대로 기록했다. 게시된 근거·권한·상태·실행 지문의 무결성 기준은 유지했다.

실제 새 프로세스의 **service.service**에서 HEALTH / RAG_SEARCH / RAG_ASK가 모두 성공했다. 질의는 `{s['question']}`이며 코드·원문 세대·검색 정책·스키마·native READ binding을 동결 후보 및 동결 서비스 팩터리와 대조했다. 평가 실행의 프로필 지문은 `{s['evaluation_binding']['profile']}`, 실제 서비스의 프로필 지문은 `{s['native_binding']['profile']}`다. 동결 서비스 팩터리가 공개 모델의 전송 재시도 횟수를 **1회 → 0회**로 보정하며 이 한 항목만 다르다. 원래 평가 지문은 보존했고, 모델 추가 호출 없이 동결 팩터리로 계산한 실행 프로필이 실제 서비스 지문과 같음을 확인했다. 두 프로필이 동일하다고 주장하지 않으며 추가 평가·재채점·품질 기준 완화는 하지 않았다. 공개 승인 145문서와 Qwen3.8 / Parasail FP8 / reasoning none 정책을 유지한다. 선택된 서비스의 실제 모델 호출은 공통 ExperimentClient로 감사 기록했다. 상주 서버의 재시작을 주장하지 않는다.

- [실험 결정과 실제 결과](README.md)
- [일반화 진단](artifacts/GENERALIZATION_REVIEW.md)
- [판단 오류·미답변 전수 기록](artifacts/run-001/GENERALIZATION_ERRORS.json)
- [실제 MAIN 실행 영수증](artifacts/main-completion.json)
- [서비스 질의와 지문](artifacts/main-smoke.json)
- [선언 프로필과 서비스 실행 프로필의 차이](artifacts/service-profile-resolution.json)
- [실제 MAIN 답변의 추가 설명 오류](artifacts/MAIN_RESPONSE_REVIEW.md)
- [적용 영수증](../../../../{receipts[0]['path']})

원문 세대는 `{m['data_path']}`를 그대로 선택하며 새 데이터 복사본을 만들지 않았다. 동일한 캐시의 hardlink 공유와 종료된 실행 DB의 무손실 압축으로 WSL의 파일 할당량 약18GiB를 줄였다. Windows C:의 가상 디스크 물리 용량 회수는 완료한 것으로 보고하지 않는다. 새 SQLite 기록은 DB뿐 아니라 남은 WAL/SHM까지 원래 바이트와 해시를 보존한다. 복원 시 원래 파일 이름으로 모두 복원해 SQLite를 열어야 한다.

## 재현·롤백

WSL `/home/jin/8-AGENT`에서 기존 진입점을 실행하면 선택 포인터를 읽는다. 추가 실험·후보 변경·재실행·재채점은 새 ADR에서 수행한다. 로컬 MAIN 롤백은 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`, 이어 작업 파일 복원은 `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0677/rollback_working.py --confirm-working-rollback`이다. 변경 코드·설정 67개와 활성 MAIN 안내 문서 2개를 백업·복원 대상으로 삼으며 다른 수정과 원문 세대·기존 runtime은 보존한다. 이후 다른 변경이 있으면 자동 복원을 중단해 그 변경을 보존한다.

Git main 병합·GENOS 현장 반입·리비전 배포·내부 모델 검증은 실행하지 않았다. `quality_certified=false`를 유지하며 내부 법률 데이터의 품질 인증으로 확대하지 않는다.
""")
docdir=A/'artifacts/main-documentation-backup';docdir.mkdir(exist_ok=False);docplan=[]
for name,path in [('AGENTS.md',R/'AGENTS.md'),('ARCHITECTURE.md',R/'00_SYSTEM/ARCHITECTURE.md')]:
 saved=docdir/name;shutil.copy2(path,saved);docplan.append({'path':str(path.relative_to(R)),'before':sha(path),'backup':str(saved.relative_to(R))})
put(A/'artifacts/main-documentation-plan.json',{'status':'prepared','files':docplan})
agent=R/'AGENTS.md';text=agent.read_text();text=text.replace('`local-genos-unit-v6-20261006-r1`(포인터 generation 42)','`'+p['release_id']+'`(포인터 generation '+str(p['generation'])+')');agent.write_text(text)
architecture=R/'00_SYSTEM/ARCHITECTURE.md';text=architecture.read_text();marker='2026-10-07 **조사 제어 통합의 로컬 MAIN**'
assert marker not in text
intro=f"""{marker}을 `{p['release_id']}`(활성 포인터 generation **{p['generation']}**)로 전환했다. 기존 v6/AD/shortcut·wiki/SQL·NFS·서비스 변경 위에 법령별 탐색·요청 단위 우선 정렬, 정확한 확보·전달·채택 범위, 저장 원문 재열람, 쟁점별 충분성·gaps, 번호가 있는 행동·이유 체인, RETURN_TO와 제한된 재진입을 연결했다. 검토 파일67개를 작업 코드에 통합했고 검증 후보·작업 코드·선택 릴리스의 서빙265파일 해시가 같다. 계약146개와 동결 독립32질문·기존8회귀 및 실제 새 `service.service`의 HEALTH/RAG_SEARCH/RAG_ASK를 확인했다. 사용자 지시에 따라 세부 판단 실수는 개선 기록으로 분리하며 게시된 원문·권한·상태·실행 지문의 무결성 기준을 유지한다. 원문 세대·공개 승인145문서·Qwen3.8 정책을 유지하고 GENOS 현장 배포·Git main 병합·전문가 품질 인증은 별도다. [실제 배선·결과·원복](../04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization/MAIN_RESULT.md).

평가 프로필과 실제 서비스 프로필은 전송 재시도 1회→0회 보정 한 항목이 다르다. 이 보정은 동결된 서비스 팩터리에도 존재하며 실제 실행 지문과 일치함을 별도 기록했다. 실제 확인 답변에서 질문 밖의 회사 유형·조문 연결 오류도 발견해 원문 근거와 함께 남겼다. 실행 배선 완료와 모든 세부 설명의 정답 보증은 구분한다.

이하 날짜별 설명은 당시 구현·전환 이력이다.

"""
architecture.write_text(text.replace('# MAIN — 원문과 용어 기반 탐색\n\n','# MAIN — 원문과 용어 기반 탐색\n\n'+intro,1))
for item in docplan:item['after']=sha(R/item['path'])
put(A/'artifacts/main-documentation-plan.json',{'status':'applied','files':docplan})
print('Local MAIN completion documented',p['release_id'],p['generation'])
