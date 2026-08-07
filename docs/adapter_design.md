# 어댑터 인터페이스 설계 — 규정 문서 수집기 (Phase 2)

Phase 1 조사(`docs/site_survey.md`)를 전제로 한다. 원칙: **소스별로 다른 것은
"목록을 어떻게 얻고 파일 URL을 어떻게 얻는가"뿐이다.** 다운로드·재시도·저장·
manifest·차단 감지는 공통 파이프라인이 소유한다.

## 배치

```
collect.py                 # CLI 진입점: --source --dry-run --force --max-targets
sources/
  __init__.py              # 어댑터 레지스트리 {source_id: factory}
  base.py                  # Target / DocumentRef / FetchResult / SourceAdapter
  common.py                # HttpClient(레이트리밋·백오프·차단감지·로깅), 파일명/매직바이트/해시, manifest IO
  kofia.py                 # Phase 3
  fss.py                   # Phase 4 (동일 패턴)
  krx.py                   # Phase 4 (동일 패턴)
corpus/<source_id>/<규정명>/    # 산출물 (git 미추적)
corpus/<source_id>/manifest.json
logs/                      # 요청 로그 (git 미추적)
tests/law_crawler/         # 픽스처 기반, 네트워크 없음
scripts/merge_manifests.py # 소스별 manifest 병합
```

## 자료형 (`sources/base.py`)

```python
Role = Literal["body", "attachment", "comparison_table"]

@dataclass(frozen=True)
class Target:
    source_id: str          # "kofia" | "fss" | "krx"
    key: str                # 출력 디렉터리명이자 manifest doc_no 결합키 (예: "표준투자권유준칙")
    label: str              # 사람이 읽는 규정명 (검색·트리 매칭에 사용)
    hints: Mapping[str, str] = field(default_factory=dict)
    # kofia: {"seq": "149"}  — 트리 검색 생략용 (없으면 label로 트리에서 해석)
    # fss:   {"bbs": "B0000145", "menu": "200152", "search": "기업공시서식"}
    # krx:   {"bookid": "210233498"}

@dataclass(frozen=True)
class DocumentRef:
    title: str              # 목록/페이지에서 얻은 제목 (파일명 폴백의 근거)
    url: str                # 요청 URL
    role: Role
    version_hint: str       # kofia: historySeq / fss: 제목의 시행일 / krx: statehistoryid
    file_ext: str           # 선언된 확장자 (".hwp" 등) — 신뢰하지 않음, 참고용
    subdir: str = ""        # 저장 하위 폴더 ("별표서식", "신구조문대비표", "")
    method: str = "GET"
    data: Mapping[str, str] | None = None    # POST 본문 (krx CSRF 흐름)
    headers: Mapping[str, str] | None = None # 요청별 추가 헤더 (krx Referer 등)

@dataclass
class FetchResult:
    status: Literal["ok", "error", "skipped"]
    file: Path | None
    sha256: str | None
    actual_format: str | None    # "hwp5(ole)" | "hwpx(zip)" | "pdf" | "html" | "unknown"
    size: int
    content_disposition_raw: str | None   # 원본 헤더 값 (바이트를 latin-1 문자열로)
    error: str | None = None

class SourceAdapter(Protocol):
    source_id: str
    def session(self) -> requests.Session: ...
    def discover(self, target: Target) -> list[DocumentRef]: ...
    def fetch(self, ref: DocumentRef, dest: Path) -> FetchResult: ...
```

`role`은 명시 필드다. 신구조문대비표(좌우 2단 표)는 본문과 파서가 완전히 달라
파일명 추측으로 구분하면 하위 파이프라인이 깨진다 (task §7). `fetch`의 기본 구현은
`common.HttpClient`에 위임하고, 어댑터는 세션 준비와 discover만 소유한다.

## 공통 파이프라인 (`collect.py` + `sources/common.py`)

```
for target in targets:
    if manifest에 status=ok && 모든 파일 존재 && sha256 일치 && not --force:
        skip (네트워크 요청 0회 — 수용 기준)
    refs = adapter.discover(target)          # dry-run이면 여기서 출력 후 끝
    for ref in refs:
        result = adapter.fetch(ref, dest)    # 실패해도 다음 ref 진행
    manifest[target] = 항목 갱신 (부분 실패는 status="error" + 사유)
```

### HttpClient 불변 규칙 (Phase 0·1 실측 근거)

- 직렬 1커넥션, 요청 간 ≥1초 (`monotonic` 기준 강제 대기)
- 타임아웃 30초 필수 — KOFIA에 응답 없이 행업하는 엔드포인트 실재
- `429/503` → 2s → 8s → 32s 백오프, 3회 소진 시 해당 문서 실패
- 연속 `403` 3회 또는 캡차 문구 감지 → `CrawlAborted` 예외로 **전체 중단**
- 200이어도 콘텐츠 검증: KOFIA 에러페이지(307→`/common/error.html`),
  KRX `"잘못된 접근"` 88B 스크립트, 기대 타입이 파일인데 HTML이 온 경우 → 실패 처리
- UA는 브라우저 문자열 + `Accept-Language: ko-KR` 고정 (FSS의 curl-UA 드롭 대응, 전 도메인 무해)
- 모든 요청을 `logs/<source>_<ts>.log`에 기록: 시각, method, URL, status, bytes, 소요, 재시도

### 파일 처리

- 파일명: Content-Disposition 우선. UTF-8 → 실패 시 EUC-KR/CP949 → 퍼센트인코딩 감지 시
  unquote. 그래도 복원 불가면 `ref.title` 기반 안전 파일명 + 원본 헤더를 manifest에 보존
- 매직바이트: `D0 CF 11 E0`→hwp5(ole), `50 4B`→hwpx(zip), `%PDF`→pdf, `<`(HTML 선언)→html
  → `actual_format` 기록. 확장자와 불일치해도 파일은 받은 그대로 저장 (변환 금지)
- sha256 → manifest. 시행일 필드가 없는 소스(KOFIA)에서 개정 감지의 유일한 수단

### manifest (소스별 `corpus/<source>/manifest.json`, §3 스키마 확장)

```jsonc
{
  "collected_at": "...", "source": "law.kofia.or.kr",
  "items": [{
    "doc_no": "149", "label": "표준투자권유준칙", "kind": "kofia-rule",
    "name": "표준투자권유준칙",
    "enforce": "",                      // 시행일 필드가 없는 소스는 빈 값 (조작 금지)
    "revised": "2026-04-09",            // 확장: 개정일 (revisionInfo 실측)
    "history_seq": "1787",              // 확장: 판 식별자
    "body_file": "corpus/kofia/표준투자권유준칙/….hwp",
    "attachments": [{ "title": "...", "seq": "27611", "file": "...", "url": "...",
                      "role": "attachment", "sha256": "...", "actual_format": "hwp5(ole)",
                      "content_disposition_raw": "..." }],
    "status": "ok" | "error", "error": "사유"
  }]
}
```

병합: `scripts/merge_manifests.py`가 `corpus/*/manifest.json` → `corpus/manifest.json`
(items 이어붙이기, `source` 필드로 구분).

## 소스별 discover 계획

### KofiaAdapter (Phase 3)

1. `lawCurrentPartTree.do` 1회 → `gotoLawList(...)` 파싱 → label 정확일치로 seq/hseq/lawType 해석
   (hints.seq 있으면 트리 생략). 폴더 target(모범규준)은 `lawPartCurrentList.do?seq=3`
   페이징 순회로 구성원 (seq, hseq) 열거 → 개별 target으로 전개.
2. refs 구성:
   - body: `download.do?gubun=101&seq=<hseq>` (전문 HWP) + `lawFullScreenContent.do` (조문 HTML, 참조 저장)
   - attachment: 조문 HTML의 `[별표/서식 파일]` 섹션 → `gubun=102` 링크들 → `별표서식/`
   - comparison_table: `revisionlist.do` POST 검색(label) → 최근 historySeq 목록 →
     각 `revisionView.do` 파싱 → `gubun=105` 발견 시 `신구조문대비표/` (최신 1건 발견에서 중단,
     최대 5개 판까지만 거슬러 탐색), `gubun=104`(개정문)는 최신 판 것만 attachment로
   - 버전: `revisionInfo.do?historySeq` → 개정일
3. 세션: 기본 `requests.Session` + 공통 헤더. 쿠키 불요(실측)나 Session 재사용으로 자연 유지.

### FssAdapter (Phase 4)

`list.do?searchCnd=1&searchWrd=<검색어>` → 제목 `기업공시서식 작성기준(...시행)` 정규식 →
최신 nttId → `view.do` 파싱 → `fileDown.do` 4건. role: 붙임4(전체본)=body,
붙임3(파일명에 "신구조문대비표")=comparison_table, 나머지=attachment.
version_hint = 제목의 시행일. 과거판 수집 범위는 기본 최신 1건.

### KrxAdapter (Phase 4)

세션 핸드셰이크가 discover의 일부: `GET /out/index.do`(토큰) → `POST regulationMain.do` →
`POST regulationView.do?bookid`(STATEHISTORYID 추출·조문 HTML 확보) →
`POST downloadRuleFile.do` filecd∈{JUN,GAE,REA,SIN} → fileMap 있는 것만 ref 생성
(JUN=body, SIN=comparison_table, GAE·REA=attachment). fetch는 `getData.do` 토큰 →
`POST /Download.do` (Referer 필수). version_hint = statehistoryid + 본문 개정 이력 줄.

## 결정 사항 (§10 대응 — 기본값, 변경 시 TARGETS만 수정)

1. "금투협 모범규준" = **모범규준 폴더(seq=3) 전체 수집**. 표준투자권유준칙·대표주관업무
   모범기준과 겹치는 구성원은 seq 기준 중복 제거.
2. KRX = **유가증권시장 상장규정 + 시행세칙** (인수업무 규정은 KOFIA 소관으로 해석,
   코스닥 상장규정은 대상 외 — 필요 시 TARGETS 한 줄 추가).
3. KOFIA 신구조문대비표 = 규정당 **최신 발견 1건** (최대 5개 판 역탐색).

## 테스트 전략

`tests/fixtures/law_crawler/`의 실제 응답으로 파싱 함수를 검증한다 (네트워크 0회):
트리 파싱, 별표 링크 추출, revisionView 버튼 파싱(105 유무), EUC-KR/퍼센트인코딩
파일명 복원, 매직바이트 판정, 멱등 skip 판정, 백오프·차단 감지(모의 응답 주입).
