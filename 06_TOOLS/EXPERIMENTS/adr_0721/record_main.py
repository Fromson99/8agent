from pathlib import Path
import json,hashlib,datetime
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0721-request-repair-final-qualification'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);smoke=read(A/'artifacts/main-smoke.json');base=read(A/'artifacts/design/baseline.json')
assert pointer['generation']==base['pointer']['generation']+1 and pointer['release_id']=='request-repair-20261009-r1'
assert smoke['status']=='passed' and smoke['pointer']==pointer
manifest=R/pointer['manifest_path'];release=read(manifest);assert release['files']==read(A/'artifacts/design/release-rebase.json')['staged_files']
for name,h in release['files'].items():assert sha(R/name)==sha(R/release['code_root']/name)==h,name
auth=read(A/'artifacts/main-authorization.json')
for ref in auth['qualification'].values():
 if isinstance(ref,dict) and 'path' in ref:assert sha(R/ref['path'])==ref['sha256']
v=read(A/'artifacts/working-verification.json');assert not v['new_failures'] and v['new23_pass']
receipts=[]
for q in (R/'01_DATA/ACTIVE/local/receipts').glob('*.json'):
 value=read(q)
 if value.get('action')=='VALIDATED_ADR_PROMOTION' and value.get('after')==pointer:receipts.append((q,value))
assert len(receipts)==1 and receipts[0][1]['before']==base['pointer']
r=read(A/'artifacts/run-001/result.json');assert r['strict_success'];install=read(A/'artifacts/working-install-receipt.json')
record={'status':'local-main-verified','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'active_pointer':bound(p),'release_manifest':bound(manifest),'pointer':pointer,'qualification':auth['qualification'],'working_install_receipt':bound(A/'artifacts/working-install-receipt.json'),'working_verification':bound(A/'artifacts/working-verification.json'),'service_verification':bound(A/'artifacts/main-smoke.json'),'execution_binding':smoke['execution_binding'],'exact_working_validated_release_inventory':True,'serving_file_count':len(release['files']),'apply_receipt':bound(receipts[0][0]),'rollback_files':[bound(q) for q in (manifest.parent/'rollback').iterdir() if q.is_file()],'git_main_merged':False,'genos_deployed':False,'resident_server_restarted':False,'external_model_calls_this_qualification':sum(a['calls'] for a in r['by_arm'].values()),'semantic_quality_certified':False}
(A/'artifacts/main-completion.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
table='| 신규 공개 질문 | MAIN50 호출 / 입력 / 시간 | MAIN51 호출 / 입력 / 시간 |\n|---|---:|---:|\n'
for old in r['by_arm']['baseline']['cases']:
 new=next(x for x in r['by_arm']['repaired']['cases'] if x['case_id']==old['case_id'])
 table+=f"| {old['case_id']} | {old['physical_model_attempts']}회 / {old['usage']['input_tokens']:,} / {old['request_seconds']:.1f}초 | {new['physical_model_attempts']}회 / {new['usage']['input_tokens']:,} / {new['request_seconds']:.1f}초 |\n"
b,c=r['primary_comparison']['baseline'],r['primary_comparison']['repaired'];repeat=[x for x in r['by_arm']['repaired']['cases'] if x['case_id'].startswith('S')]
text=f'''# 요청 상태·부족 근거·답변 내용 보존 — 로컬 MAIN51

`request-repair-20261009-r1`을 로컬 RAG MAIN generation {pointer['generation']}로 선택했다. 이번 범위는 전체 MAIN 중 RAG 서빙이다. 원문·용어집·색인 generation은 유지했다. Git main 병합 및 GENOS 현장 반입·배포는 수행하지 않았다.

## 반영한 동작

- 재조사 epoch와 동일 결정의 수정 시도를 분리했다. 수정 호출 중단 후에는 당시 입력·도구 메뉴를 복원한다. 알 수 없는 전송 결과를 세 번째 호출로 덮지 않으며 새 사용자 요청은 이전 gap 이력을 감사 기록으로 남긴 뒤 시작한다.
- 부족 근거를 세대·권한·문서·조문·span에 묶었다. 다른 조문을 읽은 기록으로 해결이나 부재를 승인하지 않는다. 모호한 대상은 미확인으로 남기고 정확히 해소된 대상은 기존 읽기 도구에 연결한다.
- 같은 부족을 표현만 바꿔 반복해도 요청의 무진행 횟수를 유지한다. 현재 입력에 이미 있는 원문은 재독 메뉴에서 빼고 채택·보류 선택은 유지한다. 읽음과 채택은 별개다.
- 질문 요구의 실제 인용과 업무 배경을 구분한다. 괄호를 일괄 삭제하지 않는다. 관련 조문을 직접 근거로 잘못 판단하는 의미 오류까지 코드로 해결했다고 보지 않는다.
- `investigation-completion-v5`는 결론·상세 설명·조건·의무·예외를 하나의 승인 내용으로 저장한다. 중첩 조건의 ID/root는 코드가 만들고 최종 조립은 내용을 그대로 보존한다. 예외가 비었다는 이유만으로 반복 안내를 붙이지 않는다. 기존 v4 이력 해석은 유지한다.
- 핵심 부족과 COVERED가 함께 게시되지 않도록 최종 coverage를 계산한다. 모델 제안과 승인 상태를 분리하고 ASSESS→COMPOSE→반환의 해시를 기록한다.
- 최종 판단 입력에서 본문 중복을 줄이고 원문 구절을 한곳에 제공한다. 요청 중 프로세스 RSS를 샘플링한다. 공유 캐시 포함 관측치이며 요청 단독 할당량이나 하위 프로세스 합산 peak는 아니다.

## 검증 결과

{table}
신규3문항의 원문 근거 응답은 {b['supported']}/3→{c['supported']}/3, 실제 호출 합계 {b['calls']}→{c['calls']}회, 입력 토큰 {b['input_tokens']:,}→{c['input_tokens']:,}, 요청 시간 {b['request_seconds']:.1f}→{c['request_seconds']:.1f}초다. 후보의 사전 고정 반복3건은 {sum(x['supported_response'] for x in repeat)}/3 응답했다. 실패·수정 호출도 포함한다. 3문항의 시간·토큰 관측을 일반 성능 향상으로 확대하지 않는다. 원문 문자열 일치는 법률 의미의 정답 판정과 다르며 [의미 검토](SEMANTIC_REVIEW.md)를 별도로 남겼다.

후보와 통합 작업 코드에서 신규23검사 통과, 기존271개 대비 신규 실패0. 전체294검사는279통과/15실패로, 그15개는 MAIN50에서도 동일하게 실패했다. 모두 통과했다고 보고하지 않는다. 이전 후보의 같은 결정 재개 결함은 ADR0719 승격을 막고 ADR0720에서 수정했다. 과거 실패 결과는 보존했다.

검증한 변경 {len(install['files'])}파일만 백업 후 통합했다. 작업 코드·동결 후보·선택 릴리스의 서빙 {len(release['files'])}파일이 일치한다. 새 WSL 로컬 프로세스에서 실제 `service.service` HEALTH/RAG_SEARCH의 포인터·코드·프로필·데이터·검색 정책·v5 모듈 선택을 확인했다. 이 선택 검사는 모델0회이고 모델 결과는 동일 코드의 위 공개 비교에 근거한다. 별도 상주 서비스 프로세스 재시작은 수행하지 않았다.

## 남은 범위

세부 법률 해석, 직접 근거/관련 근거의 의미 판별, 이유와 실제 행동의 의미 일치, 간접적인 법령 제목 추론은 추가 평가가 필요하다. 문장 의미가 같은 결론/상세의 표현 중복도 남을 수 있다. 범위 검색 도구는 계속 제공하지만 사용 빈도 개선을 인증하지 않는다. CM51 전수 재실행, 제안했던 넓은12문항 반복 매트릭스, 동시 요청과 하위 프로세스 peak, GENOS 성능은 미검증이다. 전역 graph의 과거8오류는 보존했으며 이번 직접 계보와 source final/rebase 검증은 통과했다. 품질 우회 승격은 사용하지 않았다.

## 롤백

직전 부모는 MAIN50 `compact-input-20261009-r1`이다. 현재 포인터와 apply receipt가 이번 전환인지 확인한 뒤 stable `rag_main_promotion.py rollback --confirm-main`으로 이전 릴리스를 새 generation에 선택한다. 작업 코드 복구는 `06_TOOLS/EXPERIMENTS/adr_0721/rollback_working.py`의 dry check와 `--confirm-working-rollback`으로 별도 수행한다. v5 진행 기록을 v4로 조용히 재해석하지 않으며 binding이 다르면 새 요청으로 전환해야 한다. 실제 롤백은 하지 않았다.

[완료 영수증](artifacts/main-completion.json) · [서비스 선택](artifacts/main-smoke.json) · [측정 결과](artifacts/run-001/result.json) · [전송 원문 감사](artifacts/run-001/wire-audit.json)
'''
(A/'MAIN_RESULT.md').write_text(text)
p=R/'AGENTS.md';s=p.read_text().replace('`compact-input-20261009-r1`(포인터 generation 50)','`request-repair-20261009-r1`(포인터 generation 51)');p.write_text(s)
p=R/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text().replace('2026-10-09 현재 로컬 RAG MAIN은 `compact-input','2026-10-09 MAIN50 전환 당시 로컬 RAG MAIN은 `compact-input',1);intro='2026-10-09 현재 로컬 RAG MAIN은 `request-repair-20261009-r1`(포인터 generation **51**)이다. MAIN50 위에 요청/재개 상태 분리, 정확 대상 gap·반복 제어, 질문 요구 인용, v5 답변 내용 보존·중첩 조건·승인 집계 및 프로세스 RSS 계측을 연결했다. 원문 세대는 유지한다. 신규23검사·기존271개 대비 신규 회귀0과 동일289서빙 파일·실제 service.service 선택을 확인했다. 기존15검사 실패와 의미 정확도 한계는 남는다. GENOS는 별도다. [실제 반영·검증·롤백](../04_EXPERIMENTS/ADR/ADR-0721-request-repair-final-qualification/MAIN_RESULT.md).\n\n';s=s.replace('# MAIN — 원문과 용어 기반 탐색\n\n','# MAIN — 원문과 용어 기반 탐색\n\n'+intro,1);p.write_text(s)
p=R/'07_DOCS/REFERENCE/REPORTS/MAIN50_CM51_REPAIR_IMPLEMENTATION_PLAN_20261009/PLAN.md';s=p.read_text();pos=s.index('\n\n')+2;p.write_text(s[:pos]+'**후속 구현:** 요청 상태·정확 대상 gap·v5 답변 내용 보존을 [로컬 MAIN51](../../../../04_EXPERIMENTS/ADR/ADR-0721-request-repair-final-qualification/MAIN_RESULT.md)에 연결했다. 아래는 구현 전 설계이며 실제 완료 범위·미검증 항목은 연결된 결과를 따른다.\n\n'+s[pos:])
p=R/'07_DOCS/BACKLOG.md';s=p.read_text();s+='\n\n## MAIN50 진단 후속 — 로컬 MAIN51 반영\n\n요청/재개·정확 대상 부족 근거·답변 내용 보존·승인 집계는 [ADR0721](../04_EXPERIMENTS/ADR/ADR-0721-request-repair-final-qualification/MAIN_RESULT.md)에 반영했다. 제목 의미 확장, 범위 검색 사용 효과, CM51 전수 의미 평가, 넓은 반복 검증·동시성 및 하위 프로세스 peak는 미완료다. 신규23검사 통과·기존271개 대비 신규 실패0이며 기존15실패는 별도 정비 대상이다.\n';p.write_text(s)
print('Recorded exact local MAIN51 selection and limitations')
