> 출처 보관본: infocz/main @ `7b42bc4cbf9b7ccef6dfea522d20370cedb237ce`의 `docs/genos/rag-runbook/RUNBOOK.md`.
> 날짜·환경·과제별 관찰 기록이며 현재 8-AGENT의 실행 지침이 아닙니다. 먼저 [GENOS.md](../../../../../GENOS.md)를 읽습니다.
> 본문은 보존하고 이미지·미포함 자료 링크만 원본 커밋으로 연결했습니다.

# RUNBOOK — GenOS 지식 준비(문서→벡터DB) + RAG 워크플로우

데모(genos.genon.ai, v1.9.1)에서 **실제로 돌려보며** 작성. 예시 문서: 감전재해 예방 기술지침 PDF.
Part A(지식 준비)는 **라이브 완주 검증**(벡터 37개 임베딩 완료). Part B(RAG 체인)는 작동 레퍼런스(워크플로우 5416) 기반.
스크린샷: `img/` (이 폴더) — 시각 버전은 `runbook.html`

> ⚠️ **실환경 V1.8.6과 다른 지점이 이미 여럿 확인됐다 (2026-09-02, 과제2 ELS가 온프렘에서 Part A를 실행).**
> 이 런북의 화면 흐름은 여전히 유효한 뼈대지만, **전처리기 형태·임베딩 모델·벡터DB 속성 규약이 다르다**:
> 전처리기 = **파이썬 단일 파일**(도커 이미지 등록 아님)이고 **벡터 청크만 반환할 수 있다** ·
> 임베딩 = **`kure-v1` 단일**(bge-m3 없음) · 컬렉션 이름이 곧 **인증키**, 본문·name은 **AES-256-GCM 암호화**,
> **`chunk_id`·`content_hash` 속성이 없고** 기본 속성 20개의 이름이 **복수형**(`n_chars`·`n_words`·`n_lines`·
> `n_pages`·`n_chunk_of_pages`) · 원본 파일명이 **`Document-38423`** 형태로 넘어온다.
> 실환경 규약 정본은 [`../knowledge.md`](../knowledge.md) §정석 경로 실환경 실측.
> **Part B(Flowise RAG 체인)는 실환경에서 아직 확인되지 않았다** — RAG형 과제 착수 시 재확인 대상.

---

## 0. 메뉴 지도 (지식 준비 관련)

| 메뉴 | 경로 | 역할 |
|---|---|---|
| 데이터 > **벡터 DB** | `/data/vectordb-source/` | 벡터 컬렉션 생성 + **문서 업로드(전처리·임베딩 트리거)** |
| 데이터 > AI 드라이브 | `/data/ai-drive/` | 드라이브 단위로 문서 관리(임베딩·전처리·청킹 속성 보유). 벡터DB 업로드와 유사 |
| 데이터 > 자동 적재 | `/data/auto-ingestion/` | 스케줄 적재(하루 여러 시간대) — 문서가 계속 늘어나는 과제용 |
| 문서 전처리 > **전처리기** | `/ingestion/preprocessor/` | 표준 전처리기 목록(첨부용/적재용 v2.2.4). ~~**커스텀 = 도커 이미지 등록(admin)**~~ → ⚠️ **실환경 V1.8.6은 파이썬 단일 파일**(9/2 과제2 실측 — admin 도커 등록 불요) |
| 문서 전처리 > 파이프라인 | `/ingestion/pipeline/` | 확장자·큐·워크플로우 타입 지정 파이프라인(현재 비어있음) |
| 모델 서빙 목록 | `/serving/model/` | 임베딩 서빙(bge-m3 등) 확인. ⚠️ **실환경은 `kure-v1` 하나뿐**(서빙 id 19, 9/1 확인) — bge-m3 기준 수치는 재측정 대상 |
[원본 이미지: 사이드바 메뉴 지도](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/rag-runbook/img/01_menu_map.png)


---

## Part A. 지식 준비 — 문서 → 벡터 DB  ✅ 라이브 검증 완료

### A-1. 벡터 DB 생성
1. `데이터 > 벡터 DB` → 우측 **`+ 벡터 DB 생성`**
2. 폼 입력:
   - **제목*** (예: `[A8-DK] 감전재해 RAG 테스트`) — 팀 네이밍 프리픽스 권장
   - 상세 설명(선택)
   - **관리 그룹*** = `인포시즈-테스트페이지` (드롭다운)
   - **데이터 형식*** = **문서** (라디오. 다른 옵션: QA(deprecated)/자동적재/FAQ)
   - 수동 스키마 = off (기본 스키마 사용)
3. **생성** → 확인 모달 **예**
4. 결과: 벡터 DB 생성. **백엔드 = Weaviate, 1024차원**. (⚠️ 실환경도 1024차원인데 **모델이 다르다** — `kure-v1`은 bge-m3 파인튜닝이라 차원이 같아 **적재/질의 모델이 어긋나도 에러가 안 난다**. [`../../onprem/rag-quality.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/onprem/rag-quality.md) 2순위)

[원본 이미지: 벡터 DB 생성 폼](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/rag-runbook/img/02_vdb_form.png)
 기본 속성 자동 부여
   (`doc_id, original text, summary, chunk_bboxes, n_lines, file_hash, n_words, i_page, n_chunk_of_pages, i_chunk_on_doc` …)
   → **doc-level + summary-level 임베딩** 둘 다 저장하는 구조.

> ⚠️ **자동화 함정(사람은 무관)**: 관리 그룹은 MUI Select라 좌표 클릭이 잘 안 먹힘. 사람이 UI로 하면 문제없음.

### A-2. 문서 업로드 = 전처리 + 임베딩 (핵심 설정 지점)
벡터 DB 상세 → **문서 목록** 탭 → 우측 **`+ 업로드`** → **문서 추가(2단계 마법사)**
[원본 이미지: 문서 목록 탭 — 업로드 진입점](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/rag-runbook/img/06_docs_tab.png)


**1단계 — 임베딩/전처리 설정** (여기가 "청킹·임베딩을 어디서 정하나"의 답):
| 필드 | 값 / 의미 |
|---|---|
| **임베딩 서빙*** | `Direct Serving`(모델 직접) vs `Service Router` 선택 → 드롭다운에서 **`bge-m3 (Rev ID=1923)`** (최신 리비전) |
| **배치 크기*** | 기본 64 |
| **문서 유형*** (전처리기) | **`적재용 전처리기 (표준) v2.2.4`** ← 지식베이스 적재는 이것 / `첨부용`은 채팅 첨부파일용. 둘 다 `pdf, docx, ppt, hwp, csv, xlsx, txt, json, md` 지원 |
| **파라미터** | Chunk Size / Chunk Overlap 등 (전처리기 선택 시 노출) |
| 상세 설명 | 선택 |
→ **다음**
[원본 이미지: 문서 추가 1단계 — 임베딩·전처리·청킹 설정](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/rag-runbook/img/07_upload_step1.png)


**2단계 — 파일**: 드롭존에 파일 놓기/선택 → **생성** → 확인 **예**
- 지원 확장자: `.docx .pdf .ppt .pptx .hwp .hwpx .csv .xlsx .txt .json .md`
- 업로드 API: `POST /api/admin/system/filesystem/upload?filename=...` (200)
[원본 이미지: 2단계 — 파일 드롭](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/rag-runbook/img/09_upload_step2.png)


### A-3. 임베딩 완료 확인
- 문서 목록에 행 생김 → 상태 **`실행 중`**(전처리→청킹→임베딩) → 잠시 후 **`완료됨`**, **벡터 개수** 표시.
- **실측**: 감전재해 PDF(148KB) → 약 1분 내 **벡터 37개**, 상태 완료됨. 전처리기=적재용, 임베딩=bge-m3.
[원본 이미지: 적재 완료 — 벡터 37](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/rag-runbook/img/10_embed_done.png)

- ⚠️ 상세 페이지를 리로드하면 **기본 정보 탭으로 리셋**됨 → 상태 확인은 매번 **문서 목록 탭** 재클릭.

> **커스텀 전처리기(팀 안건의 "표 문서")**: 표준 전처리기(Docling 계열)로 부족하면 커스텀 전처리기 = **도커 이미지로 패키징 → admin에 등록**(`/admin/resource/docker-image/`, 관리자 권한). `/ingestion/preprocessor/`의 표준 2종도 도커 "전처리기 패키지"(#455 첨부용, #456 적재용).

---

## Part B. RAG 워크플로우 — 벡터 DB → 질의응답  ✅ **자체 체인 e2e 라이브 완주 (2026-08-06)**

**우리 손으로 처음부터 끝까지 재현 성공** — 워크플로우 5500 `[A8-DK] 감전재해 RAG`:
벡터DB 2638 연결 → 배포 → 질의 `"이동형 전기기계·기구 감전 방지 조치"` → **우리 PDF의 제11조 청크가 sourceDocuments로 반환** (검색+체인 실행 확인).

### 자체 체인 구축 절차 (실측)
1. **워크플로우 생성** → 리비전 수정 → 도커 `llmops-workflow-api:latest` + **인스턴스 타입(smicro)** ← 빼먹으면 저장 거부
2. **Flowise 단계 추가** → 유형 Chatflow → **공용**(대기 없음; 한번 정하면 변경 불가)
3. 단계 클릭 → **캔버스(iframe /flowise300/canvas/)** — ⭐ **기본 템플릿이 이미 RAG로 프리와이어링**:
   `Genos OpenAI Embeddings → DeepSearfing(Weaviate Retriever) → Genos Unified RAG Chain ← ChatGenos`
4. 노드 설정 4개만 채움 (노드 카드의 필드 직접 편집):
   - Embeddings: Serving=`bge-m3`, Revision=`1923` (**적재 때와 동일 모델 필수**)
   - ChatGenos: Serving=`gemini 3 flash preview`, Revision=`1546`
   - DeepSearfing: **Weaviate Host 필드 = 벡터DB 픽커!** 드롭다운에서 우리 벡터DB 제목 선택 → **Index(컬렉션 ID) 자동 채움**. Credential은 비워도 됨
   - Unified RAG Chain: 기본값 (Max Context 7000, Return Source Documents on)
5. **저장 → 배포**(자체승인 불요였음) → 1분 내 "배포 완료" → **테스트**: `{"question": "..."}` → sourceDocuments+답변

### 검증 이력
- 레퍼런스 5416(승호): 이용 로그 Success + 직접 테스트로 실작동 확인 (목차 생성용 구조화 출력)
- **자체 5500: 위 절차로 신규 구축, 우리 문서 검색 e2e 성공** ← 이 런북만으로 재현 가능함을 증명
[원본 이미지: 5500 테스트 — 우리 PDF 청크 반환](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/rag-runbook/img/12_rag_test_ok.png)


### 채팅 앱 연결 (문서형 테마) — ✅ e2e 완주 (A-1)
1. **앱 > 채팅 앱 > 채팅 앱 생성** — 이름·관리그룹·**인사말***·**테마=문서형**("근거 문서를 함께 제공")·워크플로우 검색 선택
2. 생성 확인 모달에서 **"배포까지 한번에 진행하기" 체크** → 생성 → 승인 1회 → 정상·Online
   (신규 앱은 이 체크박스로 버전생성·배포 단계가 생략됨 — 기존 앱 재바인딩 사이클보다 훨씬 빠름)
3. **채팅 앱 열기 → 질의** — Flowise(Chatflow)는 **네이티브 SSE라 스트리밍 규약 작업 불필요**
   (Python 단계의 JSON 이벤트 yield는 Python 단계 전용 이슈)
4. **실측 결과**: "이동형 전기기계·기구 감전 방지 조치" 질의 → 지침 기반 답변(7초 스트리밍) +
   **근거 문서 카드 자동 렌더** — PDF 파일명·조항 청크 원문(제11조·제5조·제8조)·페이지 뱃지.
   → ③ 법규정 챗봇의 "출처 표시" 요건이 문서형 테마 기본 기능으로 충족됨.
[원본 이미지: 채팅 답변 + 근거 문서 카드](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/rag-runbook/img/13_chat_sources.png)



지식 준비가 끝난 벡터 DB를 **Flowise RAG 체인**에 연결. 레퍼런스: 워크플로우 **5416**(`[TEST-SH] 목차 워크플로우`, 승호 — 발행어음 문서초안용 **목차 생성** 워크플로우).

**검증 근거(2026-08-06):**
- 이용 로그: 5416·5419·5431 모두 당일 오전 **Success 3건씩** (소요 3.6~10.5초, Failed 0)
- **직접 테스트 실행**: 입력 `{"question": "발행어음 시장금리 데이터 내용 요약"}` → 적재 문서(시장금리데이터.docx 등) 기반 **구조화 JSON 응답**(보고서 목차) 정상 반환 — Weaviate 검색+bge-m3 임베딩+ChatGenos(gemini) 체인 실작동 확인
- 단, 5416은 "RAG 챗봇"이 아니라 **구조화 출력(목차 JSON)** 용도 — 채팅형 QA로 쓰려면 출력부(Prompt/Parser)와 채팅 스트리밍 계약(과제6에서 확보한 규약)을 맞춰야 함


[원본 이미지: Flowise RAG 캔버스 실물 (5416)](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/genos/rag-runbook/img/11_rag_canvas.png)
구조:

```
[Genos OpenAI Embeddings]  (Direct Serving, bge-m3)
        │
        ▼
[Weaviate 벡터스토어 노드]  (Weaviate Host/Index=우리 벡터DB 컬렉션, Record Manager, Credential)
        │
        ▼
[Genos Merge Retriever]  (Vector Store Retrievers, Embeddings, Query, Similarity Threshold)
        │                         [Prompt Template]      [ChatGenos] (Direct Serving, gemini 3 flash)
        └──────────────┬───────────────┴────────────────────┘
                       ▼
                  [LLM Chain]  (Language Model + Prompt + Output Parser + Input Moderation)
                       │  (+ [Advanced Structured Output Parser] 필요 시)
                       ▼
                    Output → (2단계 Python: 후처리/스트리밍)
```

**핵심 배선 요점:**
- **임베딩 노드 = 적재 때와 같은 모델(bge-m3)** 이어야 검색이 맞음.
- **Weaviate 노드의 Index/컬렉션 = Part A에서 만든 벡터 DB**. (Weaviate Host·Index·Credential로 연결)
- **Merge Retriever**가 사용자 Query로 top-k 청크 검색 → Prompt Template의 컨텍스트로.
- **ChatGenos = LLM 서빙**(gemini 3 flash 등, GenOS 서빙에 붙어 키 불요) → LLM Chain이 프롬프트+검색결과로 답 생성.
- 5416은 워크플로우가 서빙 **#10 bge-m3(임베딩) + #758 gemini(LLM)** 사용 중으로 표시됨.
- 2단계 **Python**은 후처리/채팅 스트리밍(우리 과제6에서 확인한 `json.dumps({"event":"token"...})` yield 규약 적용 지점).

> **캔버스는 UI 수작업 or 레퍼런스 복제**가 현실적. (드래그-드롭 노드 배선은 헤드리스 자동화 불가 — 팀이 5416 열어 구조 보고 손으로 구성하거나 복제.)
> **질의 검증**: 워크플로우 "테스트" 또는 채팅 앱 연결 후 질문 → 검색된 청크 기반 답변. (retriever 단독 API: `/api/data/retriever` 존재)

---

## Part C. 자동 적재 (스케줄) — 개념

`데이터 > 자동 적재`: 임베딩 서빙·전처리 모듈·대상 벡터DB·**감시 디렉터리**·**스케줄(하루 여러 시간대)**·수동 실행·실행 이력. 문서가 계속 늘어나는 과제(② ELS 상품설명서)에 유용. 연 2~3회 갱신(③ 법규정)은 수동으로 충분.

---

## 발견한 함정·사실 (버전 주의: 데모 v1.9.1 / 실환경 V1.8.6)

1. ~~**전처리기 = 도커 패키지**(admin 등록). 커스텀 전처리는 관리자 권한 필요 → 8/10 또는 투입 후 권한 확인 항목.~~ → ⚠️ **9/2 해소 — 실환경 V1.8.6의 커스텀 전처리기는 «파이썬 단일 파일»이고 admin 도커 등록이 필요 없다**(과제2 실측, 위 §메뉴 표와 동일. [`../../onprem/unverified.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/onprem/unverified.md) B1). 남은 제약은 권한이 아니라 **전처리기가 벡터 청크만 반환할 수 있다**는 것(정형 적재는 코드서빙 API 별도 호출).
2. **임베딩 모델은 적재·검색 양쪽 동일해야** 함(bge-m3 고정 권장).
3. **적재용 vs 첨부용 전처리기** 구분 중요 — 지식베이스는 적재용, 채팅 첨부는 첨부용.
4. 벡터 DB 백엔드 = **Weaviate**(1024-dim). 수동 스키마로 커스텀 속성 가능.
5. 상세 페이지 리로드 시 탭 리셋(문서 목록 재클릭 필요).
6. RAG 캔버스(Flowise)는 UI 수작업 — 자동화·문서화 대상은 "노드 구성"이지 클릭 스크립트가 아님.

## 정리 대상 (테스트 리소스)
- 벡터 DB **2638** + 워크플로우 **5500** + 채팅앱 **2866** (전부 [A8-DK] 프리픽스) → ~~데모 정리 시 삭제.~~ ⚠️ **9/3부로 우리 손으로 정리할 수 없다** — 외부망(데모) GenOS 계정이 회수되고 추가 계정 요청도 거부됐다([`../coverage-map.md`](../coverage-map.md)). 이 목록은 **무엇을 만들어 검증했는가의 이력**으로 읽는다.

## 미개척(다음)
- ~~자체 RAG 워크플로우 + 질의 e2e~~ → **완료** (워크플로우 5500 + 채팅앱 2866, 문서형 테마 출처 표시까지)
- ~~표 많은 문서(② ELS)용 **커스텀 전처리기** 필요성·등록 절차 실측.~~ → **완료(9/2, 과제2)** — 파이썬 단일 파일 규약을 실측하고 적재 코드를 한 파일로 합치는 번들러로 **온프렘 적재까지 완주**했다. 표 격자 복원·상품카드 추출 등 파싱 정확도는 그 뒤로도 계속 교정 중이며(9/3·9/8·9/9), **9/9 기준 문서 68건 적재 완료(8건 검증 실패) + 채팅 E2E 구현 완료**([`../../tasks/README.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/tasks/README.md) 과제2 행).
- ~~V1.8.6에서 위 메뉴·전처리기·서빙 존재 여부 재확인(투입 첫날).~~ → **부분 완료** — 9/1 Day-1에 코드서빙·워크플로우·채팅앱·Gitea·파일기반대화 플러그인, 9/2에 **전처리기·벡터DB(Weaviate)·임베딩 `kure-v1`**까지 확인됐다([`../../onprem/day1-runbook.md`](https://github.com/infoczAI/agent8/blob/7b42bc4cbf9b7ccef6dfea522d20370cedb237ce/docs/onprem/day1-runbook.md) Day-1 실행 결과). ⚠️ **남은 미확인 = Part B(Flowise RAG 체인·Chatflow 템플릿)와 MCP 메뉴** — 과제3·5가 GenOS 상에서 파이프라인을 서빙하는 중이라 거기서 판명될 가능성이 크다(9/9 e2e 중간점검: "앱 호출 API 오류, 9/10 오전 마무리 전망").
