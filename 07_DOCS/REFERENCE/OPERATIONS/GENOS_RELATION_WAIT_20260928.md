# 관계 탐색의 별도 시간 제한 해제

2026-09-28 사용자 사진에서 `follow_relations`가 5,861ms 후
`OperationalError: interrupted`로 실패했다. 작업 코드의 별도 5초 SQL 중단과
목록 순회 제한을 사용자 지시로 제거했다. 사진은 현장 실패 근거이며,
현장 배포 리비전·선택된 프로필·상세 로그가 없으므로 같은 원인으로 확정하지 않는다.

## 실행 경로와 계약

`service.py LEGAL_AGENT` → 선택 GENOS generation → v5 세션 →
`workflow_tiers_tools.TiersTools` → `workflow_relations_tools.execute` →
`follow_relations` / `follow_reference` → 선택 원문·용어집 SQLite와 관계 목록.
v3·v4의 기존 `relations_tools` / `tiers_tools`에도 동일 요청 deadline을 적용한다.

SQL progress callback은 전체 `RequestContext.deadline`만 검사한다.
Python 목록 순회도 `context.remaining()`으로 같은 deadline만 확인한다.
고정된 프로필의 `relation_scan_seconds=5`는 호환 필드로 보존하며 실행 제한에
사용하지 않는다. 프로필 파일·데이터 세대·색인·원문·관계 내용은 수정하지 않는다.
페이지/문자 수·도구 횟수·자동 참조 읽기 깊이와 범위/해시 검증은 기존 계약이다.

관계 SQL 진단은 `deadline_scope=request`를 기록한다. 전체 요청 시간이 지났으면
`failure_kind=REQUEST_DEADLINE`, 다른 interrupted는 `SQL_INTERRUPTED_UNKNOWN`,
나머지 DB 오류는 `SQL_OPERATIONAL_ERROR`로 보존한다. 오류를 성공이나 0건으로
바꾸지 않는다. `RELATION_SCAN_TIMEOUT`과 고정 `scan_limit_ms=5000`은 새 경로에서
생성하지 않는다. 전체 요청·워크플로우·플랫폼 시간 설정은
[기존 대기 설정](GENOS_FULLTEXT_WAIT_20260927.md)을 따른다.

## 반입·검증·원복

정본 설치 절차는 [패치노트](../../../08_DEPLOYMENT/GENOS/patches/relation_wait_20260928_r1/PATCH_NOTES.txt),
실행기는 [APPLY TXT](../../../08_DEPLOYMENT/GENOS/patches/GENOS_RELATION_WAIT_20260928_R1_APPLY.txt)다.
latency R2 또는 동시요청 해제 R1의 관계 실행 코드 바이트를 기준으로 7개 모듈만
기존 `~/DEV`에 백업 후 적용한다. 다른 판이나 무관한 코드/스키마 변형은 적용 전에
중단한다. 엔진 manifest와 PIPELINE의 코드 해시는 새 파일에 맞춰 갱신한다.

적용 뒤 변경 파일을 검토·commit하고 같은 checkout·Python·실제 선택 generation으로
release gate를 실행한다. 통과한 commit을 push해 새 코드서빙 리비전으로 배포한다.
데이터 재구축·CURRENT 변경·환경변수 추가·워크플로우 Python 변경은 필요 없다.
현장 질문은 워크플로우 테스트 화면에서 확인한다.
원복은 적용 receipt의 백업과 이전 코드서빙 리비전을 사용한다.

로컬 검증은 모의 원문/SQLite를 사용한다. 가상 시각을 5초 이상 진행해도 SQL과
Python 관계 탐색이 끝나는지, 전체 요청 deadline에서 중단하는지, 페이지 cursor와
실행 후 DB callback이 유지되는지 확인한다. 실제 내부 데이터 성능이나 모델 품질
실험은 아니다. GENOS generation 경로·manifest 해시·배포 commit·코드서빙 리비전·
워크플로우 질문 성공은 현장 확인 전까지 미확인이다.
