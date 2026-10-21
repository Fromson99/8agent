"""Record the selected local service only after actual binding verification."""
from common import *
import shutil
A=ROOT/'09_ARTIFACTS/AUDITS/20261021-structured-selection-main';s=read(ART/'stage.json');p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');m=read(ROOT/p['manifest_path']);c=read(ART/'consumer-active.json');a=read(ART/'analysis.json')
assert p['generation']==s['base_pointer']['generation']+1 and p['release_id']=='structured-selection-20261021-r1'
assert c['status']=='PASS' and not c['app_injected'] and all(c['checks'].values())
assert m['files']==s['files']['candidate'] and all(sha(ROOT/n)==h and sha(ROOT/m['code_root']/n)==h for n,h in m['files'].items())
search=c['health']['body']['search_selection'];before=read(ART/'consumer-candidate.json')['health']['body']['search_selection'];assert search==before
prior=read(ROOT/'09_ARTIFACTS/AUDITS/20261021-law-name-main/binding-check.json');assert search['sha256']==prior['search_selection_fingerprint']
shutil.copyfile(ART/'consumer-active.json',A/'consumer-active.json');save(A/'after-pointer.json',p)
save(A/'binding-check.json',{'all_working_candidate_selected_files_match':True,'file_count':len(m['files']),'actual_service_binding':c['binding'],'release_manifest_sha256':sha(ROOT/p['manifest_path']),'data_path':m['data_path'],'data_manifest_sha256':m['data_manifest_sha256'],'profile_sha256':c['profile_sha256'],'search_selection_fingerprint':search['sha256'],'workflow_version':c['workflow_version'],'quality_certified':False,'genos_verified':False})
counts={arm:sum(r['pass'] for r in ts) for arm,ts in a['by_arm'].items()};result=read(ART/'result.json')
block=f'''2026-10-21 사용자 “실제 LLM으로 다양한 범위·복수·제외 표현도 테스트해보고 문제없으면 메인에 반영하고 GENOS 반입용 ZIP도 만들어줘” 지시에 따라 **로컬 RAG MAIN{p['generation']} / workflow{c['workflow_version']}**을 선택했다. 릴리스는 `structured-selection-20261021-r1`, 정본은 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`이다. 자연어 분류를 LLM에 맡기는 기존 수정과 구조화 범위·복수·제외 선택을 통합했다. 초기·후속 범위 판단을 필수 출력하고 저장된 조·항·호·목 집합과 명시적 비교 연산을 실행한다. 적용 가정과 원문 제외를 구분하며 권한·원문·상태·해시 검사를 유지한다. ADR0972 후보16/32와 ADR0973 후보31/32는 거절 기록으로 보존했다. 최종 ADR0974 신규 합성32사례에서 기존{counts['baseline']}/32·후보{counts['candidate']}/32, 실제Qwen{a['physical_model_calls']}요청·{result['response_count']}응답(기준 HTTP429 1회 보존); 전체 답변 정확도·현장 성능 인증은 아니다. 최종199계약, 후보/작업/선택 서비스 HEALTH와419파일 결속을 확인했다. 데이터·모델 프로필·검색 선택 유지. 무거운 기존 임베딩 작업과 전체 원문 로딩을 병렬 실행하지 않았으며 실제 원문 읽기는 같은 코드의 합성 API와 모델 경계 검사로 확인했다. `VALIDATED_ADR_PROMOTION`, 품질 우회 없음, `quality_certified=false`. GENOS ZIP 설치 검사와 현장 반입·배포는 별도 상태이며 Git commit/push 미수행. 이전 전역 graph·의미 오류는 해결한 것으로 보지 않는다. 전환·복원: `09_ARTIFACTS/AUDITS/20261021-structured-selection-main/RESULT.txt`.'''
for n in ('AGENTS.md','00_SYSTEM/ARCHITECTURE.md'):
 path=ROOT/n;t=path.read_text();lo=t.index('<!-- CURRENT_LOCAL_RAG_RELEASE -->');hi=t.index('<!-- /CURRENT_LOCAL_RAG_RELEASE -->',lo)+len('<!-- /CURRENT_LOCAL_RAG_RELEASE -->')
 path.write_text(t[:lo]+'<!-- CURRENT_LOCAL_RAG_RELEASE -->\n'+block+'\n<!-- /CURRENT_LOCAL_RAG_RELEASE -->'+t[hi:])
priorcalls=sum(read(ROOT/f'04_EXPERIMENTS/ADR/{folder}/artifacts/result.json')['physical_model_calls'] for folder in ('ADR-0972-structured-selection-qualification','ADR-0973-required-structural-selection'))
(A/'RESULT.txt').write_text(f'''로컬 MAIN{p['generation']} 선택 및 실제 서비스 확인

릴리스: {p['release_id']}
workflow: {c['workflow_version']}
최종 검증: ADR0974 / 기준{counts['baseline']}/32, 후보{counts['candidate']}/32 / 실제Qwen{a['physical_model_calls']}요청·{result['response_count']}응답 / 199계약 통과.
이전 실패를 포함한 총 실제 호출: {priorcalls+a['physical_model_calls']}회. 1차16/32, 2차31/32 거절 기록 보존.
외부 Qwen3.8, Parasail FP8, reasoning none, fallback 없음. 법률 정답·GENOS 내부 모델 인증은 아니다.

범위·복수·제외·이상/초과/이하/미만·목·부모 여러 개·문서 여러 개를 구조화 모델 판단으로 처리한다.
문서 목록으로 분류하던 자연어 하드코딩 제거도 함께 반영했다. 읽기 제외와 미해당 가정을 분리한다.
선택은 실제 저장 노드로 실행하고 없는 범위는 미확인으로 남긴다. 원문·권한·상태·해시 검사를 우회하지 않는다.

작업/검증후보/선택릴리스419파일 일치. native service.service.application()이 선택한 local-release와 HEALTH200 확인.
후보·작업·활성 서비스의 데이터 manifest·모델 프로필·검색 선택 지문 동일. 실제 전체 원문 코퍼스 재로딩은 기존 임베딩 작업과 병렬로 하지 않았다.
실제 원문 READ·범위/권한·반복 실패/재개·중복 요청·응답 소비자는 같은 코드의 합성 API 계약과 실제 모델 선택→READ로 검증했다.
후보 바이트 통과를 현장 GENOS 배포로 설명하지 않는다. 현재 현장 반입·Git commit/push·서빙리비전·내부 모델은 미확인이다.

MAIN98 복원(필요할 때만):
.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
복원 후 선택한 실행 바인딩을 확인한다. 이전 포인터 previous-pointer.json과 릴리스 rollback/receipt를 보존했다.
GENOS ZIP 및 모의 설치 검사 결과는 handoffs/structured_selection_20261021_r1의 BUILD/DELIVERY_VALIDATION/SEALED에 별도로 기록한다.
''')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';t=index.read_text();note=f'\n- [ADR-0974 범위·적용 조건 분리](ADR-0974-read-scope-fact-separation/README.md) — 최종 후보{counts["candidate"]}/32,199계약,419파일 결속; 로컬 MAIN{p["generation"]}. ADR0972(16/32),0973(31/32)은 거절 이력.\n'
if 'ADR-0974 범위·적용 조건 분리' not in t:index.write_text(t.replace('# ADR workspace\n','# ADR workspace\n'+note,1))
print('Recorded actual MAIN',p['generation'],'419 files; search selection preserved')
