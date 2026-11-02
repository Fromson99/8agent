from common import *
import re
b=read(DES/'baseline.json');f=read(DES/'freeze.json');C=ROOT/f['code_root']
tests={n:read(ART/('checks-final-'+n+'.json')) for n in ('records','api','existing','support')}
integration=read(ART/'working-integration.json')
checks={
 'records12':tests['records']['exit_code']==0 and tests['records']['passed']==12,
 'oracle_service2':tests['api']['exit_code']==0 and tests['api']['passed']==2,
 'support97':tests['support']['exit_code']==0 and tests['support']['passed']==97,
 'same_legacy14':tests['existing']['passed']==56 and tests['existing']['failed']==14,
 'no_new_regression':all(not row['new_failures'] for row in integration['comparisons']),
 'same_frozen_inventory':all(v['code_root']==f['code_root'] for v in tests.values()),
 'frozen494':len(f['files'])==494 and all(sha(C/n)==h for n,h in f['files'].items()),
 'working494':all(sha(ROOT/n)==h for n,h in f['files'].items()),
 'rebase_exact':read(DES/'release-rebase.json')['staged_files']==f['files'],
 'main125_before_selection':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],
 'gold_connector_settings_preserved':all(sha(ROOT/n)==h for n,h in read(DES/'gold-before-integration.json')['files'].items()),
 'models_profiles_and_data_preserved':all(f['files'][n]==h for n,h in b['manifest']['files'].items() if n.startswith('00_SYSTEM/') and n!='00_SYSTEM/PIPELINE.json'),
}
assert all(checks.values()),checks
put(RUN/'result.json',{'status':'complete','strict_success':True,'checks':checks,
 'technical_tests_passed':167,'same_existing_failures':14,'new_failures':0,
 'candidate':f['candidate_revision'],'serving_files':494,'changed_files':len(integration['products'])+len(integration['pins']),
 'external_model_calls':0,'field_deployed':False,'actual_nfs_history_migrated':False,
 'performance_certified':False,'quality_certified':False,
 'test_artifacts':{n:bind(ART/('checks-final-'+n+'.json')) for n in tests}})
m=read(ADR/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['design']['release_rebase']=bind(DES/'release-rebase.json')
m['runs'][0].update(status='complete',artifact_path=str((RUN/'result.json').relative_to(ROOT)),sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={
 'baseline':{'status':'complete','passed':153,'existing_failures':14},
 'oracle-records':{'status':'complete','passed':167,'existing_failures':14,'new_failures':0}},
 comparisons=integration['comparisons'],judge_disagreements=[],
 usage={'external_model_calls':0,'embedding_calls':0,'original_gold_writes':0,'synthetic_local_oracle_records':'isolated namespaces, cleaned'},
 latency={'performance_claim':False,'final_test_suite_seconds':{n:v['seconds'] for n,v in tests.items()}},
 error_taxonomy=['Legacy 14 failures reproduced with no new failing tests',
 'Hydration authorization ordering and test identity fixture corrected',
 'Repeated constructor DDL was batched without delaying application write durability',
 'Mapped Oracle predicates and JSON_TABLE clauses corrected at source query boundary',
 'SQLite REPLACE implicit deletion reconciled using touched table keys',
 'Stored journal version selected for source history reads',
 'Wiki projection atomic I/O routed to Oracle',
 'Fixture schema/compact decoder/old-v4-source-bundle assumptions corrected with raw failures retained',
 'Official release preview rejected the service entry in engine-only pins; fixed before cutover'],
 main_wiring='promotion-candidate',quality_certified=False)
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
values=['run-001 / baseline·oracle-records. 실제 로컬 Oracle와 기존 계약 검사.',
 '지금 DP=oracle로 하면 전체 우리 오라클 디비만 쓰게 해주게 코드를 수정해줘 메인꺼',
 '법률 정답 평가는 없다. 원문·권한·기록·CAS·원본 바이트·중복/재개의 기술 계약만 확인한다.',
 '[사전 기준](../artifacts/design/criteria.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색 정책·회수 품질 비교 해당 없음. 합성 원문 범위와 입력을 고정했다.',
 '실제 모델 호출0. ScriptedTransport로 요청 경계만 모의했다.',
 '실제 Oracle SQL, Python/SQLite 검증기 및 기존 기술 계약. 새 모델/임베딩0.',
 '167통과·기존14동일·새실패0. 전체 저장소 통과·법률 정확성·대용량 성능 인증이 아니다.',
 'Oracle 기록 저장 분기 채택. NFS 기본값 유지, 실제 현장 NFS 전량 이관/GENOS 반입은 별도다.']
q=ADR/'실험/질문-001-contract.md';q.write_text('# Oracle 전체 기록 저장 기술 계약\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
m['questions']=[{'number':1,'case_id':'contract','file':q.name,'sha256':sha(q)}];put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[
 ('결정 요약','DP=oracle의 영구 원문·검색·Agent 기록 저장을 Oracle로 연결하는 기술 변경을 채택한다. 기본 NFS 모드 유지. 494파일, 제품/워크플로우 명세60+엔진 pin31=91변경. 신규 표는 앞서 준비한 Agent3표21컬럼이며 기존 STATE 포함4표26컬럼. Gold 추가/변경0.'),
 ('문제와 변경 전 구조','MAIN125는 지식 조회는 Oracle지만 외부 NFS/CIFS 기록 경로를 요구했다. journal·대화·조사·게시·진행·보고서의 실제 소비자를 전환해야 했다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json). NFS/디스크 SQLite 없는 요청, 원문/권한/본문 해시, durable row delta·CAS·fence·중복 영수증, 기존 기본 경로 회귀, 원본 불변 이관과 정확한 MAIN 재결속을 검증한다.'),
 ('실험 설계','선택 MAIN125를 기준으로 격리 후보를 만들고 최종 rev-010을 동결했다. 로컬 실제 Oracle SIDDA에 고유 테스트 namespace만 사용했고 원문은 별도의 임시 NO AUTHENTICATION owner를 생성/정리했다. 모델/호스트 인증만 모의했다. Oracle SQL/실제 원문·기록 포트는 모의하지 않았다.'),
 ('데이터·모델·재현성','기존 법률 프로필·모델·원문 및 Gold13표/60컬럼·매핑·온톨로지 설정 유지. Oracle가 영구 정본이며 기존 SQL/트리거는 요청 메모리 SQLite에서 실행하고 변경 행만 REC/BODY에 보관한다. 온디스크 DB 복제/지식 미러는 없다. 기존 Dataiku/S3 배치 기록 책임은 유지한다.'),
 ('결과','[최종 결과](artifacts/run-001/result.json). Oracle 저장/이관/동시성/소유권/복원12, 실제 서빙 진입을 통한 v3/v4 원문→모의답변→저장→중복 무호출→새 연결 재조회2 통과. 기존 본체56통과/기존14실패 동일, 압축·위키·AD·출처 보조97통과. 새 실패0. 검사는 전체 저장소/실제 LLM/현장 Oracle19 인증이 아니다.'),
 ('사례별 오류 분석','개발·기동·SQL·재조회·release preview 실패는 모두 artifacts에 보존했다. REPLACE의 UNIQUE 암묵 삭제, Oracle 논리→물리 predicate, JSON_TABLE 재해석, 저장판본 reader와 위키 원자 쓰기를 수정했다. 잘못된 fixture와 압축 참조 직접 해석 오류도 구분했다. 공식 preview가 service.py 엔진 pin을 거절하여 메인 선택 전 올바른 릴리스 목록으로 고쳤다.'),
 ('비용·지연·회수 규모','실제 모델/임베딩0. 테스트 지연은 환경/합성 데이터 한정이며 성능 비교 근거가 아니다. Oracle 기록 I/O와 namespace 메모리 복원 비용이 추가된다. 1초/NFS 대비 가속/다중 인스턴스 처리량을 보장하지 않는다. 기본 복원 크기256MiB 제한, 초과 시 잘라 성공시키지 않는다.'),
 ('해석','DP를 추가 플래그 없이 저장 소비자까지 연결했다. Oracle 장애나 불완전 이관에서 NFS/로컬 저장으로 우회하지 않는다. 기존 ACL/원문·코드 결속·게시 승인·모델 무중복 계약을 유지한다. 모든 기록 SQL을 Oracle 문법으로 재작성한 구조는 아니며 요청 메모리 호환 실행기를 사용한다.'),
 ('한계와 일반화 가능 범위','현장 Oracle19/ORDS 권한·GENOS 실제 리비전·실제 LLM·대용량/장기 사용·부하 성능 미검증. 14개 기존 실패는 남아 있다. 실제 현장 NFS 전량 이관은 수행하지 않았다. 제공 이관기는 writer 정지 후 정확한 기존 절대 경로/namespace를 유지해야 한다. 롤백 시 Oracle 신규 이력이 NFS에 자동 역반영되지 않는다.'),
 ('운영 결정·롤백 조건','사용자 메인 수정 지시에 따라 공식 prepare/apply로 선택한다. 이전 MAIN125/원본 NFS/Gold 연결기와 수정 전 작업 파일을 보존한다. 소유권/해시/권한 불일치·저장 장애 시 중단한다. 활성 영수증은 별도 감사 파일에 기록하며 완료 ADR을 사후 promoted로 바꾸지 않는다.'),
 ('재현 명령','prepare → explicit consumer edits → register/freeze → check.py baseline/candidate → integrate → qualify → adr_structure hash/status/validate → 공식 rag_main_promotion prepare/apply → 실제 root entry 및 활성 포인터 확인. [산출물 목록](artifacts/manifest.json).')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# Oracle 전체 기록 저장 메인 연결\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 검증 기록\n\n[최종 결과](../artifacts/run-001/result.json) · [전체 실패/검증 산출물](../artifacts/manifest.json).\n')
print('Qualified167 technical tests; legacy14 unchanged; actual field deployment/migration still separate')
