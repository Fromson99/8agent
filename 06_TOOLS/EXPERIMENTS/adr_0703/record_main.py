"""Activation evidence is separate from the immutable qualification decision."""
from pathlib import Path
import hashlib,json,datetime,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0703-exception-coupled-final-holdout'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);smoke=read(A/'artifacts/main-smoke.json');assert smoke['status']=='passed' and smoke['pointer']==pointer
assert smoke['completion_contract']=='investigation-completion-v4';assert pointer['release_id']=='structured-judgment-20261009-r1'
manifest=R/pointer['manifest_path'];release=read(manifest);assert sha(manifest)==pointer['release_manifest_sha256'];rebase=read(A/'artifacts/design/release-rebase.json');assert release['files']==rebase['staged_files']
for name,h in release['files'].items():assert sha(R/name)==sha(R/release['code_root']/name)==h,name
result=read(A/'artifacts/run-001/result.json');assert result['strict_success'];auth=read(A/'artifacts/main-authorization.json')
for ref in auth['qualification'].values():
 if isinstance(ref,dict) and 'path' in ref:assert sha(R/ref['path'])==ref['sha256']
checks=list(E.parse(A/'artifacts/working-required.xml').iter('testcase'));assert all(t.find('failure') is None and t.find('error') is None for t in checks)
record={'status':'local-main-verified','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'active_pointer':bound(p),'release_manifest':bound(manifest),'pointer':pointer,'qualification':auth['qualification'],'working_install_receipt':bound(A/'artifacts/working-install-receipt.json'),'working_tests':bound(A/'artifacts/working-required.xml'),'working_passed':len(checks),'service_verification':bound(A/'artifacts/main-smoke.json'),'execution_binding':smoke['execution_binding'],'exact_working_validated_release_inventory':True,'serving_file_count':len(release['files']),'git_main_merged':False,'genos_deployed':False,'resident_server_restarted':False,'semantic_quality_certified':False}
apply_path=R/'01_DATA/ACTIVE/local/receipts/semantic-apply-659c877b6ae44a1aa047cc9ec3fba6f6.json'
apply=read(apply_path);assert apply['action']=='VALIDATED_ADR_PROMOTION' and apply['after']==pointer
assert apply['before']==read(A/'artifacts/design/baseline.json')['pointer']
record['apply_receipt']=bound(apply_path)
record['rollback_files']=[bound(q) for q in (manifest.parent/'rollback').iterdir() if q.is_file()]
record['working_rollback_dry_check']='Verified installed bytes and every backup hash; no rollback executed.'
(A/'artifacts/main-completion.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
b=result['primary_comparison']['baseline'];c=result['primary_comparison']['structured-reading']
text=f'''# 구조 우선 검색·판단·오류 표시의 로컬 MAIN 반영

2026-10-09, 검증한 `structured-judgment-20261009-r1`을 로컬 MAIN 포인터 generation **{pointer['generation']}**에 반영했다. 이것은 전체 MAIN 파이프라인 중 RAG 서빙 변경이다. 용어집·입력 구조화·문서 연결·색인 생성의 책임과 선택 원문 세대는 그대로 결속한다.

## 바뀐 동작

- 문서명·제목·조문 좌표·목차를 먼저 찾는다. 같은 검색 묶음의 번호 단독 질의는 명시된 문서 범위로 결속하고, 제목이 빗나가도 찾은 문서의 목차를 유지한다. fulltext는 모델이 선택한 문서/하위 구조 안에서만 실행한다.
- 내부 오류·거절·재시도는 전체 로그에 보존한다. 채팅·진행 카드·SSE·저장된 표시 결과에는 공개 필드만 전달하며 최종 실패는 짧은 안내와 조회 번호를 표시한다.
- 현재 요청/근거/상태와 결속한 승인 판단을 소비한다. 오래된 판단을 거절하고 같은 근거와 부족 상태의 검증된 판단은 재사용한다. 공통 claim, 부족별 완료 행동과 새 근거, 조건 ALL/ANY/UNKNOWN·예외·사용자 사실의 출처를 검사한다.
- 선택한 범위의 묶음 읽기·중복 제거·페이지 처리·중단 후 재개를 기존 실행기에 연결했다. 확보, 실제 모델 전달, 근거 채택을 별도로 기록한다.

## 실제 검증

- 최종 코드 신규 공개3문항 **{c['supported']}/3**, 알려진 회귀 **{result['by_arm']['structured-reading']['supported_known']}/2**. 사전 동결한 모든 필수 기준을 통과했다.
- 동일 코드의 누적 합성 계약263개 통과. 기존9개 legacy fixture 실패와 기존1개 제외는 부모와 동일하게 보존했다. 선별 작업 통합 후 실행한 필수 계약 **{len(checks)}개 전부 통과**.
- 작업 코드 → 검증 후보 → 선택 릴리스의 서빙 파일 **{len(release['files'])}개 전체 해시 일치**. 코드/프로필/원문/색인/검색 정책 지문과 실제 실행 binding을 영수증에 연결했다.
- 신규3문항 전체 파이프라인 비교: 실제 모델 호출 **{b['calls']} → {c['calls']}**, 입력 토큰 **{b['input_tokens']:,} → {c['input_tokens']:,}**, 요청 시간 합계 **{b['request_seconds']:.1f}초 → {c['request_seconds']:.1f}초**. 출력 토큰은 **{b['output_tokens']:,} → {c['output_tokens']:,}**, 실제 모델에 전달된 조문은 **{b['presented_roots']} → {c['presented_roots']}**개다. 모든 필수 원문이 모델에 전달됐으며 전역 본문 검색과 공개 진단 누출은0건이다.
- 행동 최적화의 독립 비교는 [ADR0697](../ADR-0697-structure-wire-public-holdout/README.md)에 남겼다. 수정 전에는 호출·토큰이 늘어난 사례도 있었다. 최종 작은 표본의 수치를 일반 성능 보장으로 확대하지 않는다.
- 새 WSL 로컬 프로세스의 실제 `service.service`에서 HEALTH·RAG_SEARCH를 실행하여 활성 코드/프로필/데이터 선택을 확인했다. 별도 상주 HTTP 서버 재시작을 주장하지 않는다.

## 주요 변경 경로

| 책임 | 파일 |
|---|---|
| 구조 우선·문서 범위 검색 | `legal_agent/structure_query.py`, `law_candidates.py`, `law_navigation.py`, `unit_fulltext.py` |
| 읽기 중복·페이지·재개 | `legal_agent/unit_reading.py`, `law_navigation.py` |
| 판단/조건/승인 저장 | `completion_contracts.py`, `completion_execution.py`, `case_repository.py`, `corrected_memory.py`, `unified_rag.py` |
| 공개 표시 경계 | `app.py`, `progress.py`, `chat_adapter.py`, `service.py`, `main_workflow.py`, `GENOS/stream_app.py`, `GENOS/workflow/genos_rag_chat.py` |
| 실제 선택과 패키지 | `control.py`, 두 프로필, engine/PIPELINE pins, 동일 세대 별칭·폴더 projection |

작업 파일은 변경이 필요한 것만 이전 해시와 대조해 백업 후 반영했다. 후보 전체를 작업 트리에 덮어쓰지 않았다. 관련 없는 진행 중 변경은 보존했다.

## 남은 범위와 복구

조건 구조 검사는 법률 해석의 정답을 인증하지 않는다. 적용 조건과 이행 의무·예외 구분 및 중복 서술은 [의미 검토](SEMANTIC_REVIEW.md)와 후속 백로그로 남긴다. 실패0695/0697/0701과 미실행699는 그대로 보존했다.

**GENOS 현장 반입·워크플로우 편집기 적용·코드서빙 배포·내부 모델 검증은 수행하지 않았다.** Git main 병합도 별도 상태다.

전체 ADR graph 검사는 기존8개 이력 오류가 남아 있어 전체 성공으로 보고하지 않는다. 이번 ADR의 final 검증과 계보는 통과했다.

서빙 복구: 저장소의 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 이전 선택을 복구한다. 작업 코드 복구는 `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0703/rollback_working.py`로 후속 변경 여부를 먼저 검사하고, 필요할 때 `--confirm-working-rollback`을 추가한다. 두 복구는 별도다.

[최종 실험](README.md) · [완료 영수증](artifacts/main-completion.json) · [실제 서비스 선택](artifacts/main-smoke.json) · [작업 반영 영수증](artifacts/working-install-receipt.json) · [동결한 승격 대상](artifacts/design/release-rebase.json)
'''
(A/'MAIN_RESULT.md').write_text(text);print(json.dumps({'status':record['status'],'release':pointer['release_id'],'generation':pointer['generation'],'working_tests':len(checks)},ensure_ascii=False))
