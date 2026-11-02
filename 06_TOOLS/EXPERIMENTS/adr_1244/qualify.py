from common import *
import re
b=read(DES/'baseline.json');f=read(DES/'freeze.json');integration=read(ART/'working-integration.json')
checks={'records18':read(ART/'checks-qualified-records.json')['passed']==18 and read(ART/'checks-qualified-records.json')['exit_code']==0,
 'oracle_and_nfs_failure_api2':read(ART/'checks-qualified-api.json')['passed']==2 and read(ART/'checks-qualified-api.json')['exit_code']==0,
 'same_legacy_tests':all(not v['new_failures'] for v in integration['comparisons']),
 'same495':len(f['files'])==495 and all(sha(ROOT/n)==h for n,h in f['files'].items()),
 'exact_rebase':read(DES/'release-rebase.json')['staged_files']==f['files'],
 'main127_before_cutover':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],
 'usage_within90':read(ART/'capacity-before.json')['within_limit']}
assert all(checks.values())
put(RUN/'result.json',{'status':'complete','strict_success':True,'checks':checks,'technical_tests_passed':173,'new_failures':0,
 'split_storage_cases':18,'oracle_nfs_available_and_unavailable_api_cases':2,'default_existing_passed':153,'same_existing_failures':14,
 'candidate':f['candidate_revision'],'external_model_calls':0,'new_ddl':0,'field_nfs_mount_certified':False,'field_deployed':False})
m=read(ADR/'실험/manifest.json');m['design']['release_rebase']=bind(DES/'release-rebase.json')
m['runs'][0].update(status='complete',artifact_path=str((RUN/'result.json').relative_to(ROOT)),sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','passed':153,'same_existing_failures':14},
 'oracle-records':{'status':'complete','passed':173,'same_existing_failures':14,'new_failures':0}},comparisons=integration['comparisons'],
 judge_disagreements=[],usage={'external_model_calls':0,'embedding_calls':0,'new_ddl':0,'local_usage':read(ART/'capacity-before.json')},
 latency={'performance_claim':False},error_taxonomy=['Full raw requests/responses/SSE and traceback previously stored in Oracle bodies',
 'Diagnostic poll concurrent-hydration StateConflict is deferred to the next read pulse without write/model retry'],main_wiring='promotion-candidate',quality_certified=False)
q=ADR/'실험/질문-001-contract.md';heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
values=['run-001 baseline/oracle-records, MAIN127 부모.','온톨로지에 필요한 구조화 내용 Oracle, 상세 로그 NFS에 두기.',
 '법률 정답 평가 없음. 기록 목적지·원본·권한·재개·무재전송만 검사.',
 '[사전 기준](../artifacts/design/criteria.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색 정책/회수 비교 없음.',
 '실제 모델0. 실제 로컬 Oracle와 ScriptedTransport.',
 'NFS mount 검사는 합성 경로 어댑터를 사용, 실제 현장 mount 인증이 아니다.',
 '저장/경계/이관18·서비스2·기존153통과/14기존실패동일·새0.',
 '구조화 판단·근거·상태는 Oracle, 원시 프롬프트/응답·SSE/trace/보고서는 NFS. NFS 실패로 모델 재전송하지 않는다.']
q.write_text('# Oracle 구조화·NFS 상세 기록\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
m['questions']=[{'number':1,'case_id':'contract','file':q.name,'sha256':sha(q)}];put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[('결정 요약','구조화 업무/온톨로지 기록은 Oracle, 상세 진단은 NFS로 분리하는 변경 채택. 제품11+pin31=42변경·495파일. DDL/Gold 변경0.'),
 ('문제와 변경 전 구조','MAIN127은 model_attempt의 전체 request/response/SSE와 report/trace 파일까지 Oracle BODY에 보관했다. 사용자 최신 요청으로 상세 로그의 영구 책임을 NFS로 정정했다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json). 원문/근거 좌표·판단/정정/gap/최종답변·권한·상태/예산/CAS·재개는 Oracle에서 NFS 없이 복원해야 한다. 원시 전송/traceback은 Oracle blob에도 없어야 한다.'),
 ('실험 설계','완료1243을 부모로495파일 후보 동결. 실제 로컬 Oracle 고유scope/임시원문owner와 모의모델, NFS는 로컬 파일 경로를 반환하는 검증 어댑터로 비교했다. 실제 NFS mount/19c/GENOS 인증이 아니다. NFS 정상/고장 두 서비스 조건과 상세보고서 실제파일을 검사했다.'),
 ('데이터·모델·재현성','Oracle 기록의 기존 SQLROW/JSON 본문 형식은 유지한다. 새 일반 정규화 테이블로 바꾼 것은 아니다. 전송 request는 NFS 위치/해시 참조로, response는 최소 structured-response와 별도 원시 참조로 보관한다. Oracle response_hash는 저장된 구조화 응답 해시이며 원본 응답 해시는 NFS 참조에 보존한다.'),
 ('결과','[결과](artifacts/run-001/result.json). 구조화/원시 분리·압축blob누출 차단·원본불변 이관/미사용blob제외·NFS없는복원·워크플로우 parser재사용·기본값/소유권18통과. 실제 Oracle 원문→모의답변→기록/중복무호출 API2, 기본경로 기존153통과·14실패동일/새0. 원래 모델입력/답변/승인 판단은 바꾸지 않았다.'),
 ('사례별 오류 분석','NFS 상세 독자가 원장 갱신과 동시에 hydrate하여 StateConflict로 heartbeat thread가 끝나던 경고를 보존하고 수정했다. 다음 읽기 pulse에서만 다시 읽으며 원장 쓰기나 모델을 재전송하지 않는다. 거절/실패/UNKNOWN 및 구조화 오류 계약은 유지한다.'),
 ('비용·지연·회수 규모','실모델/임베딩0. NFS 원시 로그는 제한된 메모리 큐로 전달하며 QUEUED는 영구저장 성공을 뜻하지 않는다. 실패/미설정은 참조 상태/로그로 남기고 Oracle·로컬 파일로 우회하지 않는다. 사용자 사용률90% 범위: 로컬 SIDDA 약9.312%, 디스크52.496%. 부하 성능 향상 인증 없음.'),
 ('해석','구조화 model_view·판단/근거·워크플로우 계약/반환값은 재개/검증 소비자에 필요해 Oracle에 유지한다. 원시 진단은 NFS, Oracle에 포인터/해시만 남긴다. 상세 독자만 NFS 원문을 펼치며 핵심 재개는 구조화 응답을 사용한다.'),
 ('한계와 일반화 가능 범위','현장 NFS/GENOS·Oracle19/ORDS·실LLM·대량 이관/성능 미검증. 실제 과거 기록 전량 이관/삭제0. 원래 NFS·이전 Oracle 기록은 임의 삭제하지 않았다. 명시 이관기는 raw attempt를 NFS에 내구저장한 뒤 구조화 부분만 옮기고 관련 없는 compact log blob을 제외한다. NFS 없으면 raw 포함 이관을 완료로 표시하지 않는다.'),
 ('운영 결정·롤백 조건','사용자 요청대로 MAIN128 후보 선택. 기본 NFS 모드 유지. 기존 GENOS_SHARED_LOG_DIR을 실제 NFS 상세 경로로 사용, Oracle data root를 포함하는 로그root는 거절한다. 필요하면 GENOS_DETAIL_LOG_DIR로 원시 로그 경로만 별도 지정. 이전 MAIN127/원본/Gold 연결기 보존, engine binding만 동일128로 결속.'),
 ('재현 명령','prepare→explicit edits/register/freeze→storage/API/baseline·candidate→integrate→qualify→공식hash/status/validate→prepare/apply→실제진입점. [산출물](artifacts/manifest.json).')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 구조화 Oracle·상세 NFS 기록\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검증\n\n[결과](../artifacts/run-001/result.json).\n')
print('Qualified173; same legacy14; NFS field mount/LLM/performance unverified')
