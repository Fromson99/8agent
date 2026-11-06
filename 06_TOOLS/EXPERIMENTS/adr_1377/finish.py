from common import *
r=read(ART/'main-r2/activation.json')
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert r['active']==ptr and ptr['generation']==145
prev=read(ART/'previous-main-control/result.json')
fixed=read(ART/'prepared-current/result.json')
first=read(ART/'prepared-checks/result.json')
candidate=read(ART/'merged-checks-local/result.json')
summary={**r,'candidate_checks':candidate['passed'],'prepared_original_passed':first['passed'],'prepared_stale_provider_failed':first['failed'],
         'main142_legacy_control_passed':prev['passed'],'prepared_current_passed':fixed['passed'],'quality_certified':False,'model_calls':0,
         'native_executables':639,'source_set':read(DES/'source-set.json'),'engine':read(DES/'engine-preflight.json')}
put(ART/'result.json',summary)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'generation':142},'integrated':summary},judge_disagreements=0,usage={'physical_calls':0},error_taxonomy=['stale_synthetic_provider','restricted_local_test_interrupted'])
put(ADR/'실험/manifest.json',m)
headline='온톨로지 자동 구축·판단 누적과 답변 소비 경로를 로컬 MAIN145에 반영했다.'
bodies=[headline,'기존 MAIN142와 완료1376의 구축 경로, 완료1369의 답변 소비 경로를 세 파일 집합으로 대조했다.',
'엔진, 실행 SQL, 소스 바인딩과 설치·선택 단계 검사를 사전 고정했다.','판단·출처·문장에 따른 구축은 1376, 실제 명시 경로에 성공한 RAG 소비자는 1369에서 채택했다.',
'동결 528파일, 제품 27파일 변경 및 엔진·원생 SQL 메타데이터 갱신. 실행 SQL 639개 동일, 엔진30/500 일치.',
f"후보 47검사 통과. 준비본 첫 실행 12통과/3실패, 현행 모의 제공자로 바꾼 뒤 7통과. 선택 MAIN {r['main_checks']}검사, Gold 엔진 연결 {r['gold_checks']}검사 통과. 초기 세트와 재확인 수는 별도로 센다.",
'구형 제공자는 허용되지 않는 빈 source_goal_exclusions를 반환하여 원문 조사에서 거절됐다. MAIN142에서는 같은 세 경우가 통과했다. 모의 출력만 현행 제품 형식으로 맞춰 실제 전달, 응답 중 철회 및 재조회 시 철회를 원래 단언으로 확인했다. 첫 제한 환경 HEALTH 대기 후 원복(144세대), 병행 작업의 엔진 핀 복원·528개 대조, 동일 코드 r2 전달 API 1건을 거쳐 145세대로 전환했다.',
'외부 모델 호출 0회. 합성 입력의 API 왕복과 선택된 로컬 기본 서비스 HEALTH 200 확인.','법률 답변에서 자동 활용되는지는 후속 Qwen 실험으로 구분한다.',
'현장 배포·운영 지식 게시·독립 품질 인증은 별도다.',f"사용자 지시 전환. MAIN142 포인터와 Gold 원래 설정은 release rollback 및 {r['old_gold_binding']}에 보존했다.",
'adr_1377/setup → freeze → check → prepare_release → prepared-current → activate → finish. 상태는 ACTIVE_RELEASE.json에서 조회한다.']
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
p=ADR/'README.md';front=p.read_text().split('---',2)[1].replace('main_wiring: unchanged','main_wiring: user-directed-cutover')
p.write_text('---'+front+'---\n\n# 로컬 MAIN145 통합\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(zip(heads,bodies),1))+'\n')
q=m['questions'][0];qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
notes=['run-001/integrated','일단 메인에 반영하고 온톨로지는 이후에 추가 남은거 돌려봐봐','사전 기준은 design/criteria.json에 보존했다.','### 회수·탈락 단계 원장 — run·arm별\n\n릴리스 기술 검증. 실질 법률 질문 회수 없음.','외부 모델 호출 0회. 합성 제공자 계약 검사.','0회.','원본 SHA 대조, 선정 서비스와 Gold 연결기를 별도 새 프로세스에서 확인했다.',bodies[5]]
(ADR/'실험'/q['file']).write_text('# 로컬 MAIN 전환\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(zip(qh,notes),1))+'\n')
(ADR/'실험/README.md').write_text(f"# MAIN145 검증\n\n[검사 기록]({q['file']})\n")
report=ROOT/'09_ARTIFACTS/AUDITS/20261105-ontology-main143';report.mkdir(exist_ok=True)
(report/'메인반영_결과.txt').write_text('\n\n'.join(bodies)+'\n')
print(headline)
