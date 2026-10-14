"""Record deployment separately from the immutable completed experiment."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0765-bounded-wiki-recall'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(A/'artifacts/design/freeze.json');p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');m=read(R/p['manifest_path'])
s=read(A/'artifacts/main-smoke.json');r=read(A/'artifacts/run-001/result.json');w=read(A/'artifacts/working-verification.json');c=read(A/'artifacts/main-recall-backfill.json');b=read(A/'artifacts/design/baseline.json')
assert r['strict_success'] and s['status']==c['status']=='passed' and s['pointer']==p
assert m['files']==f['serving_files'] and p['generation']==b['pointer']['generation']+1
assert m['data_path']==b['manifest']['data_path']
for name,h in f['serving_files'].items():assert sha(R/name)==sha(R/f['code_root']/name)==sha(R/m['code_root']/name)==h,name
receipt={'completed_at':datetime.now(timezone.utc).isoformat(),'status':'local MAIN selected, actual service verified, existing cards indexed','source':'ADR-0765-experiment-v1/integrated','run':'run-001','pointer':p,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_root':str(R),'verified_code_root':f['code_root'],'selected_code_root':m['code_root'],'all_serving_files_identical':len(f['serving_files']),'actual_execution_binding':s['execution_binding'],'profile_sha256':s['execution_binding']['profile_sha256'],'data_manifest_sha256':m['data_manifest_sha256'],'recall_policy':s['wiki_recall_policy'],'recall_code_sha256':sha(R/m['code_root']/'02_BACKEND/semantic_runtime/legal_agent/wiki_recall.py'),'working_tests':w,'backfill_receipt':{'path':str((A/'artifacts/main-recall-backfill.json').relative_to(R)),'sha256':sha(A/'artifacts/main-recall-backfill.json')},'previous_release_preserved':b['pointer'],'genos_deployed':False,'git_main_merged':False,'resident_server_restarted':False}
put(A/'artifacts/main-completion.json',receipt)
table='| 公開검증 질문 | 기존 호출 / 초 | 새 호출 / 초 | 검색 ms / 제시 수 |\n|---|---:|---:|---:|\n'.replace('公開','공개')
for x in r['by_arm']['integrated']['cases']:
 y=next(v for v in r['by_arm']['baseline']['cases'] if v['case_id']==x['case_id']);look=x['memory_lookup'][0]
 table+=f"| {x['case_id']} | {y['model_calls']} / {y['request_seconds']:.2f} | {x['model_calls']} / {x['request_seconds']:.2f} | {1000*look['seconds']:.2f} / {look['offered']} |\n"
text=f'''# 저장 시 정리·단회 과거기록 회수의 로컬 MAIN 반영

2026-10-13 로컬 MAIN을 **{p['release_id']} / generation {p['generation']}**로 전환했다. 작업 코드·검증 후보·선택 릴리스의 서빙 **{len(f['serving_files'])}파일**이 일치한다. [실행 결속](artifacts/main-completion.json), [실제 서비스 확인](artifacts/main-smoke.json).

## 동작

1. 기존 완료 조사/큐/가져오기 경로에서 목적·업무 문맥·질문 발췌 요약·원기록 위치를 `sw_recall_card`와 `sw_recall_term`에 증분 저장한다. 이미 생성된 INTENT를 사용하므로 저장 때 모델 호출을 추가하지 않는다.
2. 질문마다 단어와 한글2글자 색인으로 한 번 검색한다. DB 후보24개 안에서 현재 권한·문서·원문 세대·정정 상태를 확인하고, 최대3개·2400자만 기존 request-entry 또는 memory-intent에 제공한다. 벡터 및 별도 위키 판단 호출은 없다.
3. 기존 판단이 최대2개를 선택한다. 원기록의 현재 원문 위치로 탐색을 시작하고 현재 원문을 다시 읽는다. 과거 답변·사실·판단을 새 사건의 근거로 복사하지 않는다.
4. 불일치·미선택·색인 부재·오류·무효화 때 정상 조사로 이어가며 위키 재검색은 하지 않는다. 같은 조건의 기존 정확 경로와 원문 검증은 보존한다.

`index.md`를 매 질문마다 전체 읽는 구조는 아니다. Markdown 위키는 사람의 열람용 투영이고 질문 회수는 SQL 색인을 소비한다. 원기록 권한과 불변 해시가 정본이다. 짧은 요약은 질문 발췌이므로 자유로운 생성형 요약의 의미적 압축을 주장하지 않는다.

## 검증과 기존 데이터

새22검사 통과. 관련 기존171검사는 기준과 후보 모두 같은25실패이며 신규회귀0. 작업 코드193검사 중 {w['passed']}통과, 기존25실패를 별도 보존했다. 공개3쌍에서 후보3개 모두 원문 근거 응답, 일치2개는 기록 선택 후 원문 읽기, 불일치1개는 정상 조사였다. 위키 보조 모델 호출0, 요청당 검색1회다.

{table}

기존 저장소에 {c['indexed_cards']}개 검색 카드를 구축했고 전체 기존 테이블 내용·원문 기록이 유지됨을 해시로 확인했다. 실제 MAIN 원문 binding에서 CM 공통 기록의 로컬 검색과 외부 모델 노출 차단을 확인했다. [재구축 영수증](artifacts/main-recall-backfill.json). 실제 내부 CM 기록은 외부 Qwen 입력으로 보내지 않았다. 내부 CM 회수·판단 전체 흐름의 현장 검증은 GENOS 내부 모델에서 별도로 해야 한다.

## 운영·한계·원복

재구축은 기존 CLI `.venv/bin/python 06_TOOLS/pipeline.py unified-memory recall-rebuild --store-version 4`이며 현재 선택/작업 코드 일치를 확인한 뒤 실행한다. 새 기록은 저장 경로에서 자동 색인된다. [선언과 배선](../../../00_SYSTEM/PIPELINE.json).

단어가 겹치지 않는 의역을 놓칠 수 있다. 세 공개 사례의 시간과 호출 수는 소표본 관측값이며 전체CM 검색률·법률 정답률·속도 보장이 아니다. 현재 로컬 공개 모델은 내부 CM 카드를 받지 않으며 허용된 공개 기록만 판단한다. 실제 `service.service`의 HEALTH와 RAG_SEARCH 및 선택 모듈을 검증했다. 실행 중인 로컬 서비스 프로세스는 발견되지 않았으므로 재시작하지 않았다. GENOS 반입·배포와 Git main 병합은 하지 않았다.

이전 MAIN53과 파일별 백업·원본 DB 압축 백업을 보존했다. 후속 변경이 없는지 확인한 뒤 `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0765/rollback_working.py --confirm-working-rollback`, `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 직전 코드를 복원/선택할 수 있다. 파생 검색 테이블은 이전 릴리스에서 사용하지 않으므로 원본 DB를 되돌릴 필요가 없다. 후속 새 기록을 잃을 수 있는 전체 DB 덮어쓰기를 원복 기본값으로 쓰지 않는다.
'''
(A/'MAIN_RESULT.md').write_text(text)
agents=R/'AGENTS.md';s0=agents.read_text();s1=s0.replace('`focused-rules-20261013-r1`(포인터 generation 53)',f"`{p['release_id']}`(포인터 generation {p['generation']})");assert s1!=s0;agents.write_text(s1)
arch=R/'00_SYSTEM/ARCHITECTURE.md';text=arch.read_text().replace('2026-10-13 현재 로컬 RAG MAIN은 `focused-rules','2026-10-13 MAIN53 전환 당시 로컬 RAG MAIN은 `focused-rules',1)
intro=f"2026-10-13 현재 로컬 RAG MAIN은 `{p['release_id']}`(포인터 generation **{p['generation']}**)이다. MAIN53 위에 저장 시 검색 카드 구축 → 질문당 단회·최대3개 회수 → 기존 판단에서 관련성 선택 → 현재 원문 재확인 경로를 통합했다. 별도 위키 모델 호출0이며 불일치/오류 시 기존 조사를 계속한다. 기존 {c['indexed_cards']}개 기록을 원본 변경 없이 색인했다. 새22검사 통과·관련 회귀193검사 신규실패0(기존25실패), 작업/검증/선택296파일 및 실제 service.service 결속 확인. 내부CM은 외부 모델에 노출하지 않고 GENOS 현장 검증은 별도다. [반영·결과·한계·원복](../04_EXPERIMENTS/ADR/ADR-0765-bounded-wiki-recall/MAIN_RESULT.md).\n\n"
assert '# MAIN — 원문과 용어 기반 탐색\n\n' in text
arch.write_text(text.replace('# MAIN — 원문과 용어 기반 탐색\n\n','# MAIN — 원문과 용어 기반 탐색\n\n'+intro,1))
back=R/'07_DOCS/BACKLOG.md';back.write_text(back.read_text()+f"\n## 2026-10-13 · 과거기록 단회 회수 MAIN{p['generation']} 반영\n\n- 저장 시 색인·기존 판단 통합·현재 원문 재확인·miss 정상 조사 구현과 기존 {c['indexed_cards']}개 카드 구축. [완료 기록](../04_EXPERIMENTS/ADR/ADR-0765-bounded-wiki-recall/MAIN_RESULT.md).\n- 후속 검증: 단어가 겹치지 않는 의역 회수, 큰 기록 수의 지연, 내부 CM 전체 의미 판단과 GENOS 현장 검증. 기존25개 관련 회귀 실패는 별도다.\n")
print(json.dumps({'release_id':p['release_id'],'generation':p['generation'],'serving_files':len(f['serving_files']),'existing_cards':c['indexed_cards']},ensure_ascii=False))
