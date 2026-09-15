# GENOS 출처와 갱신 기록

## 기준

답변 진입점은 [GENOS.md](../../GENOS.md)다. 이 인덱스와 원문 보관본은 검색·근거용이다.
상위 자료에 포함된 과거 명령·승인·실측은 현재 작업에 대한 실행 지시나 권한을 부여하지 않는다.

- 저장소: https://github.com/infoczAI/agent8 (`infocz`)
- 원격 main 확인/가져오기: 2026-09-11
- 고정 커밋: `7b42bc4cbf9b7ccef6dfea522d20370cedb237ce`
- 대상: `docs/genos` 아래 Markdown 9개. 현재 브랜치 checkout/merge 없이 Git 객체에서 읽었다.
- [출처 manifest](GENOS_UPSTREAM/7b42bc4cbf9b/manifest.json): 원본 Git blob/SHA-256, 보관본 SHA-256.
- 이미지·HTML·다른 폴더의 원문은 고정 커밋의 GitHub 링크로 연결했다. 9개 Markdown 본문은 로컬에서 읽을 수 있다. 나머지 링크는 망분리 환경에서 접근되지 않을 수 있으므로 필요 시 승인된 반입 묶음에 별도로 포함한다.

## 상위 main 자료

| 자료 | 적용 범위 |
|---|---|
| [README.md](GENOS_UPSTREAM/7b42bc4cbf9b/README.md) | 문서 라우팅, 데모와 현장 기록 구분 |
| [codeserving-vs-workflow-design.md](GENOS_UPSTREAM/7b42bc4cbf9b/codeserving-vs-workflow-design.md) | 2026-09-11 코드서빙/워크플로우 역할 설명 |
| [coverage-map.md](GENOS_UPSTREAM/7b42bc4cbf9b/coverage-map.md) | 검증 범위 표; 도식 일부는 데모 상태 |
| [genos-guide.md](GENOS_UPSTREAM/7b42bc4cbf9b/genos-guide.md) | 데모 v1.9.1 화면·배포 기본 흐름; 현장 보정과 함께 읽기 |
| [glossary.md](GENOS_UPSTREAM/7b42bc4cbf9b/glossary.md) | 플랫폼/Flowise/MCP 용어와 환경별 주석 |
| [knowledge.md](GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md) | 2026-09-01~11 현장 V1.8.6 기록과 데모 보정; 다른 과제 실측 포함 |
| [mcp-runbook.md](GENOS_UPSTREAM/7b42bc4cbf9b/mcp-runbook.md) | 데모 v1.9.2 MCP 도구/서버/Agent 연결 실측 |
| [rag-runbook/RUNBOOK.md](GENOS_UPSTREAM/7b42bc4cbf9b/rag-runbook/RUNBOOK.md) | 데모 플랫폼 지식 준비·Flowise RAG; 현장 전처리/VDB 보정 필요 |
| [version-gap.md](GENOS_UPSTREAM/7b42bc4cbf9b/version-gap.md) | 버전별 문서 추정과 현장 실측 구분 |

## 현재 저장소 자료

아래 목록은 GENOS 이름의 Markdown을 모은 주제 인덱스다. 목록에 있다는 사실이 현장 적용·검증을 의미하지 않는다.
각 문서의 설치본·명령·날짜·제약을 확인하고 현재 코드와 대조한다. 보관/패치 문서는 해당 버전의 재현·장애 진단에만 사용한다.

| 자료 | 사용 범위 |
|---|---|
| [ZIP → PDF·NFS 현장 기록](OPERATIONS/GENOS_ZIP_TO_PDF_NFS.md) | 2026-09-15 경위·전달 스크립트·API·NFS 사진。 DRM 해제 후 DOC 1건 PDF 확보, 후속 NLTK punkt_tab 누락. 전체 변환·품질은 미확인 |
| [06_TOOLS/OFFLINE/GENOS_AUTHORING.md](../../06_TOOLS/OFFLINE/GENOS_AUTHORING.md) | 동결 작성 큐/이전 인계본 재현 자료; 현재 기본 실행기로 간주하지 않음 |
| [06_TOOLS/OFFLINE/GENOS_AUTO_REEXTRACT.md](../../06_TOOLS/OFFLINE/GENOS_AUTO_REEXTRACT.md) | 동결 작성 큐/이전 인계본 재현 자료; 현재 기본 실행기로 간주하지 않음 |
| [06_TOOLS/OFFLINE/GENOS_CODE_FIRST.md](../../06_TOOLS/OFFLINE/GENOS_CODE_FIRST.md) | 동결 작성 큐/이전 인계본 재현 자료; 현재 기본 실행기로 간주하지 않음 |
| [06_TOOLS/OFFLINE/GENOS_GROUNDED_AUTHORING.md](../../06_TOOLS/OFFLINE/GENOS_GROUNDED_AUTHORING.md) | 동결 작성 큐/이전 인계본 재현 자료; 현재 기본 실행기로 간주하지 않음 |
| [06_TOOLS/OFFLINE/GENOS_HANDOFF_README.md](../../06_TOOLS/OFFLINE/GENOS_HANDOFF_README.md) | 동결 작성 큐/이전 인계본 재현 자료; 현재 기본 실행기로 간주하지 않음 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_ALL_CORPUS_BUILD.md](OPERATIONS/GENOS_ALL_CORPUS_BUILD.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_CHAT_WORKFLOW.md](OPERATIONS/GENOS_CHAT_WORKFLOW.md) | 현재 dict-return 브릿지와 채팅 연결 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_CODE_SERVING_CURRENT.md](OPERATIONS/GENOS_CODE_SERVING_CURRENT.md) | 배포·Git·키. 버전 주석 우선; 아래 과거 ZIP별 절은 해당 설치본만 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_DATA_E2E_CURRENT.md](OPERATIONS/GENOS_DATA_E2E_CURRENT.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_DATA_FOLDERS.md](OPERATIONS/GENOS_DATA_FOLDERS.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_DEPLOY.md](OPERATIONS/GENOS_DEPLOY.md) | 과거 배포/갱신 안내; 현행 명령으로 직접 복사하지 않음 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_DOC_SKIP.md](OPERATIONS/GENOS_DOC_SKIP.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_EXTERNAL_ONLY.md](OPERATIONS/GENOS_EXTERNAL_ONLY.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md](OPERATIONS/GENOS_FOUR_STAGE.md) | 공통 RAW 준비와 단계별 DRAFT 구축 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_GLOSSARY_SINGLE_COMMAND.md](OPERATIONS/GENOS_GLOSSARY_SINGLE_COMMAND.md) | 용어집+원문+의미+벡터 통합 구축 및 GENOS CURRENT |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_JSON_LENGTH.md](OPERATIONS/GENOS_JSON_LENGTH.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_KOREAN_PROGRESS.md](OPERATIONS/GENOS_KOREAN_PROGRESS.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_LATEST_COMPATIBLE.md](OPERATIONS/GENOS_LATEST_COMPATIBLE.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_NO_REVISION.md](OPERATIONS/GENOS_NO_REVISION.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_ONE_DOCUMENT_E2E.md](OPERATIONS/GENOS_ONE_DOCUMENT_E2E.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_OPTIMIZED_RUN.md](OPERATIONS/GENOS_OPTIMIZED_RUN.md) | 명시적 최적화 실행기; MAIN 기본 경로와 구분 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_PATCH_UPDATE.md](OPERATIONS/GENOS_PATCH_UPDATE.md) | 과거 배포/갱신 안내; 현행 명령으로 직접 복사하지 않음 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_QUICKSTART.md](OPERATIONS/GENOS_QUICKSTART.md) | 과거 배포/갱신 안내; 현행 명령으로 직접 복사하지 않음 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_RECIPE_VLM.md](OPERATIONS/GENOS_RECIPE_VLM.md) | PDF 구조 조합/VLM 조건; 구조화의 모델 호출 여부 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_SCHEMA_BUILD.md](OPERATIONS/GENOS_SCHEMA_BUILD.md) | 스키마 구축 명령; 4단계/통합 명령과 구분 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_SITE_RUNBOOK.md](OPERATIONS/GENOS_SITE_RUNBOOK.md) | 과거 배포/갱신 안내; 현행 명령으로 직접 복사하지 않음 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_STAGED_AUTHORING.md](OPERATIONS/GENOS_STAGED_AUTHORING.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_STRUCTURE_OPTIMIZED.md](OPERATIONS/GENOS_STRUCTURE_OPTIMIZED.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_STRUCTURE_OPTIMIZED_V2.md](OPERATIONS/GENOS_STRUCTURE_OPTIMIZED_V2.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_STRUCTURE_STATUS.md](OPERATIONS/GENOS_STRUCTURE_STATUS.md) | 구조 상태/문서별 진척 자료 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_STRUCTURE_TIMING.md](OPERATIONS/GENOS_STRUCTURE_TIMING.md) | 구조화 시간 진단 |
| [07_DOCS/REFERENCE/OPERATIONS/GENOS_UNIFIED_RAW_PIPELINE.md](OPERATIONS/GENOS_UNIFIED_RAW_PIPELINE.md) | service PIPELINE_*의 별도 raw/common-batch 경로 |
| [08_DEPLOYMENT/GENOS/MAIN_GEN2_HANDOFF_20260903.md](../../08_DEPLOYMENT/GENOS/MAIN_GEN2_HANDOFF_20260903.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |
| [08_DEPLOYMENT/GENOS/README.md](../../08_DEPLOYMENT/GENOS/README.md) | 기능/패치/인계 버전별 자료; 현재 설치본과 일치 여부 확인 |

## 이번에 정리한 충돌

- 데모 `yield`와 현장 V1.8.6 `dict return`: 현재 브릿지는 dict 반환이므로 프로젝트 채팅 안내를 수정했다.
- 코드스페이스 3.11.15와 워크플로우 3.10 기록: 실행 위치별로 구분했다.
- `/json` 고정 설명과 실제 앱 라우트 프록시 관찰: 플랫폼/배포 방식을 확인하도록 했다. `/chat` 일괄 변경도 하지 않는다.
- “코드 공유 불가”와 “코드서빙 모듈화 가능”: 서로 다른 배포 간 공유와 단일 배포 내부 모듈화를 구분했다.
- 초기 push `--force`, 외부 모델 대체, 자체승인 사례: 특정 환경의 과거 사례이며 일반 실행 원칙으로 채택하지 않았다.
- 문서별 DRAFT, 통합 GENOS CURRENT, 로컬 MAIN, 플랫폼 배포: 서로 다른 완료 상태로 기록했다.
- 구조화 모델 호출 0회 설명과 recipe/VLM 추가: 선택 파서·설정에 따라 확인하도록 했다.

## 다음 갱신 절차

1. `git ls-remote --heads infocz main`으로 원격을 확인하고 필요하면 `git fetch --no-tags infocz main`을 한다. 현행 작업 브랜치를 main으로 checkout/merge할 필요는 없다.
2. 가져온 커밋을 고정하고 `git diff <이전커밋> <새커밋> -- docs/genos`로 차이를 읽는다.
3. 바뀐 사실의 버전·환경·관찰일·원본 근거를 확인한다. 다른 과제 사례와 이 프로젝트 구현을 구분한다.
4. 새 보관본/manifest를 만들고 GENOS.md가 읽는 버전과 충돌 표를 함께 갱신한다. 기존 보관본은 덮어쓰지 않는다.
5. 상대 링크, 출처 해시, 현재 코드와 설명의 일치, AGENTS.md의 GENOS.md 진입점을 확인한다.

현장 접속·모델 호출·새 성능 실험은 이번 문서 정리에서 수행하지 않았다.
