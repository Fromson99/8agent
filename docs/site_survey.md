# 사이트 구조 조사 — 규정 문서 수집기 (Phase 1)

조사일: 2026-08-07. 모든 URL·파라미터·응답은 실제 요청으로 검증했다.
원문 응답 전체는 `tests/fixtures/law_crawler/`에 저장 (테스트 픽스처 겸용).

## 대상 규정 → 식별자 해석 결과

| 대상 | 소스 | 식별자 (실측) |
|---|---|---|
| 표준투자권유준칙 | law.kofia.or.kr | seq=149, 현행 historySeq=1787 |
| 증권 인수업무 등에 관한 규정 | law.kofia.or.kr | seq=140, 현행 historySeq=1782 |
| 대표주관업무 등 모범기준 | law.kofia.or.kr | seq=153, 현행 historySeq=1783 |
| 금투협 모범규준 | law.kofia.or.kr | **단일 문서 아님** — 분류 폴더 seq=3 (하단 §KOFIA-6) |
| 기업공시서식 작성기준 | www.fss.or.kr | 게시판 B0000145, 최신 게시물 nttId=220457 (2026.8.3 시행) |
| 유가증권시장 상장규정 | **rule.krx.co.kr** | bookid=210233498, statehistoryid=210234678 |
| 유가증권시장 상장규정 시행세칙 | **rule.krx.co.kr** | bookid=210233783 |

---

# 1. 금투협 법규정보시스템 — law.kofia.or.kr

인코딩: 페이지 UTF-8, 다운로드 파일명 헤더는 **EUC-KR**. 쿠키: 첫 응답에서
`JSESSIONID` 발급되나 **쿠키 없이도 모든 조회·다운로드 동작 확인**(무세션 GET로 재현됨).

### 1-1. 목록 조회

**규정 트리 (전체 규정 열거)**
- `GET /service/law/lawCurrentPartTree.do` — 파라미터 없음, HTML(JS 트리 데이터 내장)
- 각 규정이 `gotoLawList('<lawcode>', '<folder>', '<규정명>', ..., '<lawType>', '<hseq>', '<url>')`
  JS 호출로 나열됨. `folder='1'`이면 분류 폴더, `lawType='1'`이면 정형 규정(조문 뷰어),
  `'2'`면 비정형(파일 직다운), `'3'`이면 외부 URL.
- 페이지네이션 없음 — 트리 1회 호출로 전 규정 열거 가능. 우리 대상 4건 모두 lawType='1'.

**분류별 목록**
- `GET /service/law/lawPartCurrentList.do?seq=<분류코드>&root=0` — HTML,
  규정별 `lawView.do?seq=..&historySeq=..` 직링크 포함. 페이지당 10건, `goPage` JS 페이징.

**최신 제·개정 목록 (개정 이력 열거)**
- `POST /service/revision/revisionlist.do` — form-urlencoded
- 파라미터(실증): `page=<n>` (1부터, 페이지당 10건 고정 — 폼에 크기 변경 필드 없음),
  `searchValue=<검색어>` (규정명 부분일치)
- 총 143페이지. 응답 HTML 테이블: 번호 | 규정명(→`revisionView.do?historySeq=N`) | 구분(제정/개정) | 개정일

### 1-2. 본문 조회

- 뷰 프레임: `GET /service/law/lawView.do?seq=<lawcode>&historySeq=0&gubun=cur&tree=part`
  (`historySeq=0` + `gubun=cur` = 현행판 자동 해석. 응답 안에 실제 historySeq가 박힌
  iframe 링크가 있음)
- **본문 실체**: `GET /service/law/lawFullScreenContent.do?seq=<lawcode>&historySeq=<hseq>`
  — 조문 전체가 든 HTML (표준투자권유준칙: 288,116 bytes). 조문·부칙·[별표/서식 파일] 섹션 포함.
- 조항 목록: `GET /service/law/lawFullScreenTitle.do?seq=..&historySeq=..`
- 식별자 체계: `seq`(=lawcode, 규정 불변 ID) + `historySeq`(=hseq, 판(version) ID)

### 1-3. 첨부파일 다운로드 — 단일 엔드포인트 `GET /download.do?gubun=<종류>&seq=<파일ID>`

| gubun | 의미 | seq의 의미 | 실측 |
|---|---|---|---|
| 101 | 규정 전문 HWP | historySeq | `증권 인수업무...개정전문_260312 (최종).hwp` 144,896B OLE |
| 102 | 별표/서식 파일 | 첨부 고유번호 (본문 HTML에서 파싱) | `0000_[참고 1].hwp` 94,208B OLE |
| 104 | 개정문 | 별도 파일ID (revisionView HTML에서 파싱) | `...개정 주요내용_260312 (최종).hwp` 79,360B OLE |
| **105** | **신구조문대비표** | 별도 파일ID (revisionView HTML에서 파싱) | `매매거래계좌설정약관 신구조문대비표(시행 20260318).hwp` 49,152B OLE |
| 914 | 제·개정예고 첨부 | 예고 게시물 번호 | `20260805_...개정안_개정예고_FF.hwpx` 69,451B **ZIP(HWPX)** |

- Content-Disposition 실제 값(raw bytes): `attachment; fileName="0000_[\xc2\xfc\xb0\xed 1].hwp";`
  → **EUC-KR** 디코딩 시 `0000_[참고 1].hwp`. UTF-8 디코딩은 실패함 (task §8-5 예상과 일치).
- Content-Type: `application/octet-stream;charset=utf-8` (파일 형식 정보 없음 — 매직바이트 판정 필수)
- `.hwpx` 확장자 파일이 실제 ZIP 컨테이너임을 실측 확인 (`50 4B 03 04`).

### 1-4. 버전 정보

- 개정정보 팝업: `GET /service/law/revisionInfo.do?historySeq=<hseq>` — HTML 표:
  분야 / 담당부서 / 규정명 / 제개정구분 / **개정일**(예: 2026-04-09) / 요약문
- revisionlist 행에도 개정일 있음. **시행일 필드는 없다** — 신구조문대비표 파일명에
  `(시행 20260318)` 형태로 박히는 경우가 유일한 시행일 흔적. 개정일+historySeq를
  버전 키로 쓰고, 해시를 개정 감지 수단으로 삼아야 함 (task §8-7과 일치).

### 1-5. 신구조문대비표

- **별도 게시물이 아니라 개정 건 상세의 첨부 버튼**: `GET /service/revision/revisionView.do?historySeq=<hseq>`
  응답 HTML에 최대 3개 버튼 — 전문(gubun=101)·개정문(gubun=104)·신구대비표(gubun=105).
  어떤 버튼이 있는지는 개정 건마다 다르며, **gubun=104/105의 seq는 페이지 HTML에서만 얻을 수 있다**
  (규칙성 없음: historySeq=1785 건의 신구대비표 seq=1781, 개정문 없음).
- 본문과의 연결: revisionView의 historySeq = 해당 판의 historySeq (lawView와 동일 키).
- 증권 인수업무 등에 관한 규정 최신 개정(historySeq=1782)에는 신구대비표 버튼이 없고
  전문+개정문만 있음. 신구대비표 존재 여부는 개정 건별로 파싱해서 판정해야 함.

### 1-6. "금투협 모범규준" 해석 문제 — **판단 필요 (task §10)**

트리에서 "모범규준"(seq=3)은 폴더이고, 하위에 10건+ 규정이 있다 (page 1 실측):
표준투자권유준칙(149) / 금융투자회사 표준내부통제기준(150) / 대표주관업무 등 모범기준(153) /
금융투자회사의 표준윤리준칙(154) / 리스크관리 모범규준(155) / 컴플라이언스 매뉴얼 Ⅲ편(262) /
컴플라이언스 매뉴얼 공통·증권·선물편(284) / 증권형 크라우드펀딩 표준업무방법서(318) /
영업행위 표준윤리준칙(333) / 증권 대차 및 공매도 업무처리 모범규준(336) — 이하 페이징.
**대상 1·3(표준투자권유준칙, 대표주관업무 모범기준)도 이 폴더의 구성원이다.**
→ "금투협 모범규준"을 (a) 폴더 전체 수집으로 볼지 (b) 특정 규정 하나로 볼지 결정 필요.

### 1-7. 운영 특성 (수집기 설계에 반영)

- 존재하지 않는 경로: 307 → `/common/error.html` (200) — 상태코드만으로 성공 판정 불가.
- `service/revision/boarList.do?type=1`, `download.do?gubun=106`(비정의 값):
  응답 없이 **행업** — 모든 요청에 타임아웃 필수 (30s 권장).
- **전문 HWP 가 없는 규정도 행업으로 표현된다** (Phase 3 실측): "채권형 투자일임 및
  특정금전신탁 리스크 관리 지침"(hseq=1669), "표준사채관리계약 면제 채권 기준"(hseq=1731)의
  `gubun=101` 다운로드는 재시도·백오프 후에도 일관 타임아웃. 404 를 주지 않으므로
  조문 HTML 을 본문 폴백으로 삼아야 한다.
- 요청 간 1초 간격으로 수십 회 요청 시 차단 징후 없음.

### 1-8. 실제 응답 샘플 (원문)

샘플 1 — 트리의 대상 규정 항목 (`lawCurrentPartTree.do` 응답 중):
```
var tree149 =  new WebFXTreeItem('표준투자권유준칙', '', '', '/images/service/tree/file.png', '/images/service/tree/file.png', 'a149');
tree149.action="javascript:gotoLawList('149', '0', '표준투자권유준칙', '0', '', '1', '9', '표준투자권유준칙', 'a149', '1', '1787', '')";
```

샘플 2 — 개정 상세의 다운로드 버튼 (`revisionView.do?historySeq=1785` 응답 중):
```html
/download.do?gubun=101&seq=1785 | 전문다운로드(새창열림)
/download.do?gubun=105&seq=1781 | 신구대비표다운로드(새창열림)
```
(historySeq=1782 건은 `gubun=101&seq=1782` 전문 + `gubun=104&seq=1778` 개정문 구성)

샘플 3 — 본문 내 별표 섹션 (`lawFullScreenContent.do?seq=149&historySeq=1787` 응답 중):
```html
<a name="inclosure" />
<div class="article" style="font-size:10pt;">[별표/서식 파일]</div>
...
<a href="/download.do?gubun=102&seq=27611" title="별지서식다운로드(새창열림)" target="_blank">
    1. 0000_[참고 1].hwp
</a>
```

---

# 2. 금감원 — www.fss.or.kr (기업공시서식 작성기준)

표준 eGovFrame 게시판. UA에 `curl` 문자열만 없으면 접근 제약 없음 (Phase 0 참조).
인코딩: 페이지 UTF-8, 다운로드 파일명은 **퍼센트인코딩된 UTF-8** (KOFIA와 다름).

### 2-1. 목록 조회

- `GET /fss/bbs/B0000145/list.do?menuNo=200152` — 게시판 "기업공시제도일반", HTML, 페이지당 10건
- 페이지네이션(실증): `&pageIndex=<n>`
- 검색(실증): `&searchCnd=1&searchWrd=기업공시서식` — searchCnd=1이 제목 검색.
  이 조합으로 "기업공시서식 작성기준(YYYY.M.D. 시행)" 게시물만 정확히 필터링됨.
- 게시물 행: 제목(→`view.do?nttId=<n>&menuNo=200152`) | 담당부서(기업공시국) | 게시일

### 2-2. 본문 조회

- `GET /fss/bbs/B0000145/view.do?nttId=<게시물ID>&menuNo=200152` — HTML (최신 건 292,607B)
- 식별자: `nttId` (게시물 단위. 판 개념 없음 — 개정판마다 새 게시물)

### 2-3. 첨부파일

- 패턴: `GET /fss/cmmn/file/fileDown.do?menuNo=200152&atchFileId=<32hex>&fileSn=<n>&bbsId=`
- `atchFileId`는 게시물당 1개, `fileSn`으로 파일 구분 (view.do HTML에서 파싱)
- 실측 (nttId=220457, 2026.8.3 시행판): PDF 4건
  1. `(붙임1) 기업공시서식 작성기준 개정(요약).pdf` — 87KB
  2. `(붙임2) 기업공시서식 작성기준 개정내용(본문).pdf` — 138KB
  3. `(붙임3) 기업공시서식 작성기준 개정(신구조문대비표).pdf` — 100KB
  4. `(붙임4) 기업공시서식 작성기준(2026.8.3. 시행).pdf` — 2,653KB ← **전체본**
- Content-Disposition 실제 값(raw): `attachment; filename="(%EB%B6%99%EC%9E%841) %EA%B8%B0%EC%97%85...pdf"`
  → URL-decode(UTF-8)하면 복원. Content-Type: `application/octet-stream;charset=UTF-8`.
  매직바이트 `%PDF-` 확인.

### 2-4. 버전 정보

- **시행일이 게시물 제목에 있음**: "기업공시서식 작성기준(2026.8.3. 시행)". 게시일 별도 표시.
- 최신판 판정 = 검색 결과 최상단 게시물. 과거판도 게시물로 전부 남아 있음
  (p1~p2 실측: 2026.8.3 / 7.28 / 7.23 / 6.30 / 5.1 / 4.1 / 2025.12.30 / 12.5 ...).

### 2-5. 신구조문대비표

- 같은 게시물의 **첨부 3번**으로 배포 (별도 게시물 아님). 파일명에 "신구조문대비표" 포함
  → 파일명 기반으로 role=comparison_table 판정 가능.

### 2-6. 실제 응답 샘플 (원문)

샘플 1 — 목록 행 (list.do 응답에서 추출한 링크·제목 원문):
```
/fss/bbs/B0000145/view.do?nttId=220457&menuNo=200152 | 기업공시서식 작성기준(2026.8.3. 시행) 기업공시국2026-08-03
/fss/bbs/B0000145/view.do?nttId=219441&menuNo=200152 | 기업공시서식 작성기준(2026.7.28. 시행) 기업공시국2026-07-27
```

샘플 2 — 첨부 링크 (view.do?nttId=220457 응답 중):
```
/fss/cmmn/file/fileDown.do?menuNo=200152&atchFileId=a6301cbd601e44768e3947a00879fa2a&fileSn=3&bbsId= | (붙임3) 기업공시서식 작성기준 개정(신구조문대비표).pdf (파일크기: 100KB)
/fss/cmmn/file/fileDown.do?menuNo=200152&atchFileId=a6301cbd601e44768e3947a00879fa2a&fileSn=4&bbsId= | (붙임4) 기업공시서식 작성기준(2026.8.3. 시행).pdf (파일크기: 2,653KB)
```

샘플 3 — 다운로드 응답 헤더 (fileSn=1):
```
HTTP 200, 89177 bytes, magic=%PDF-
Content-Type: application/octet-stream;charset=UTF-8
Content-Disposition: attachment; filename="(%EB%B6%99%EC%9E%841) %EA%B8%B0%EC%97%85%EA%B3%B5%EC%8B%9C%EC%84%9C%EC%8B%9D %EC%9E%91%EC%84%B1%EA%B8%B0%EC%A4%80 %EA%B0%9C%EC%A0%95(%EC%9A%94%EC%95%BD).pdf"
```

---

# 3. 거래소 — rule.krx.co.kr (KRX 법무포털)

### 3-0. ⚠ law.krx.co.kr(내규 검색 서비스)은 동결된 구서비스

- `law.krx.co.kr/las/`의 유가증권시장 상장규정: 최신 개정 **2022-12-07 제2087호**,
  사이트 전체 최신 개정이 2024-11-14에서 멈춤.
- `rule.krx.co.kr`의 동일 규정: **2026-08-03 제2475호, 시행일 2026.8.3**까지 반영.
- → 수집은 rule.krx.co.kr로 한다. (구서비스 응답은 `krx/las_vol_detail_..._STALE.html` 픽스처로 보존)

### 3-1. 세션·CSRF 모델 (모든 요청의 전제)

Spring Security CSRF. 재현 절차(실증):
1. `GET /out/index.do` → `JSESSIONID` 쿠키 + 페이지 내 `_csrf` 토큰
   (인라인 JS `name:"_csrf", value:"<uuid>"` 또는 `<meta name="_csrf" content="...">`)
2. 이후 모든 POST에 `_csrf` 폼 필드 또는 `X-CSRF-TOKEN` 헤더 (메타 `_csrf_header`가 헤더명 지정)
3. GET은 대부분 405 (POST 전용). 오류 시 1423B 커스텀 404/오류 페이지 (역시 fresh 토큰 포함)

### 3-2. 목록 조회 — JSON 트리 API

- `POST /out/regulation/getTreeNode.do` (X-CSRF-TOKEN 헤더 필요)
- 파라미터: `node=<부모ID>` (루트=0), `statecd=현행`, `mtype=htree`, `Menucd=BYLAW`,
  `webgbn=OUT`, `gbnid=0`, `gbn2=out`
- 응답: **JSON 배열** — `{id, text, catcd(folder|doc), bookid, noformyn, leaf, ...}`
- 실측 계층: 0 → [정관, 업무규정] → 업무규정(204789005) → 11개 분류(공통/유가/코스닥/코넥스/
  파생/일반상품/증권시장청산결제/장외파생청산/거래정보저장/시장감시/회원관리) →
  유가증권시장규정(204789022) → 규정 14건 (규정·시행세칙이 같은 폴더의 형제 문서로 존재)
- 별표·서식 트리: `POST /out/regulation/getByulNode.do` (`mtype=byul`) — 루트 응답은
  [별표, 별지서식] 2개 카테고리 노드

### 3-3. 본문 조회

- 선행: `POST /out/regulation/regulationMain.do` — `Menucd=BYLAW&index=law_rule&gbn=out&_csrf=<tok>`
- 본문: `POST /out/regulation/regulationView.do` —
  `bookid=<bookid>&noformyn=N&gbnid=0&mtype=htree&searchForm=&Menucd=BYLAW&_csrf=<tok>`
- 응답: 조문 전체 HTML (상장규정 711,747B). 개정 이력 줄(`개정 2026. 08. 03. 규정 제2475호`),
  조문별 `<시행일 : 2026. 8. 3>` 마커, 부칙 포함.
- **`STATEHISTORYID`(판 ID)는 이 페이지의 JS에서만 얻을 수 있음**:
  `name:"STATEHISTORYID", value:"210234678"` — 다운로드에 필수.
- 식별자 체계: `bookid`(문서 판번호에 가까움 — 트리에서 획득) + `statehistoryid`(상태이력 ID)

### 3-4. 첨부/문서 파일 다운로드 — 2단계

1. `POST /web/regulation/downloadRuleFile.do` (X-CSRF-TOKEN) —
   `bookid, statehistoryid, filecd` → JSON `{"fileMap":{"SERVERFILE":"...","PCFILENAME":"..."}}`
   (없으면 `fileMap: null`)
   - `filecd` 실측 값: `JUN`=전문, `REA`=개정이유, `GAE`=개정문, **`SIN`=신구조문**, `ENG`=영문전문
2. `POST /Download.do` (**루트 컨텍스트** — /out 아님) —
   `Serverfile=<SERVERFILE>&Pcfilename=<PCFILENAME>&folder=ATTACH&_csrf=<fresh>`
   - fresh 토큰: `POST /login/getData.do` → JSON `data._csrf`
   - **주의(실증)**: 같은 세션에서 regulationView.do를 연 상태 + `Referer` 헤더 없이는
     200 + `<script>alert("잘못된 접근...")` 88B 응답이 옴. 즉 200이어도 본문 검증 필수.
- 전체 다운로드: `POST /web/regulation/allDownload.do` — `STATEHISTORYID=<id>&_csrf=<tok>` [미확인: 응답 형식 — 버튼만 확인, 호출은 안 함]
- Content-Disposition (SIN 실측, raw):
  `attachment; filename="%EC%9C%A0%EA%B0%80...%EC%8B%A0%EA%B5%AC..."` — **퍼센트인코딩 UTF-8**
  → `유가증권시장 상장규정_신구...hwp`. 47,104B, 매직 `D0 CF 11 E0`(HWP 5.0 OLE).

### 3-5. 버전 정보

- 본문 HTML 안: 규정 첫머리 개정 이력 줄들(`개정 2026. 08. 03. 규정 제2475호` 등 — 제·개정
  전체 연혁), 조문별 `<시행일 : YYYY. M. D>` 마커. 별도 구조화 필드는 응답에 없음 —
  HTML에서 파싱해야 하며 `statehistoryid`가 판 식별자 역할.

### 3-6. 신구조문대비표

- 별도 게시물이 아니라 **규정 뷰의 문서 버튼** (`filecd=SIN`) — 본문과 같은
  bookid+statehistoryid로 연결. 최신 개정분 기준 1개 파일.

### 3-7. 실제 응답 샘플 (원문)

샘플 1 — getTreeNode.do JSON (유가증권시장규정 폴더 확장, 발췌 원문):
```json
{"id": 210233497, "text": "유가증권시장 상장규정", "catcd": "doc", "bookid": 210233498, "noformyn": "N", "leaf": true}
{"id": 210233782, "text": "유가증권시장 상장규정 시행세칙", "catcd": "doc", "bookid": 210233783, "noformyn": "N", "leaf": true}
```
(전체 원문: `tests/fixtures/law_crawler/krx/rule_get_tree_node_walk.json`)

샘플 2 — downloadRuleFile.do 응답 (bookid=210233498, filecd=SIN, 전문 원문):
```json
{"fileMap":{"SERVERFILE":"210234680.hwp","PCFILENAME":"210234494.hwp"}}
```

샘플 3 — regulationView.do 내 다운로드 폼 생성 JS (원문):
```javascript
newForm.attr("action", "/web/regulation/allDownload.do");
newForm.append($("<input/>", {type:"hidden", name:"STATEHISTORYID", value:"210234678"}));
newForm.append($("<input/>", {type:"hidden", name:"_csrf", value:"86e9c07b-6a78-444e-9f78-29d0e693a966"}));
```

---

# 4. 판단 필요 사항 (task §10 — Phase 2 진행 전 결정 요청)

1. **"금투협 모범규준" 범위** (§1-6): 폴더(seq=3) 전체 수집 vs 특정 규정 지정.
   표준투자권유준칙·대표주관업무 모범기준이 이미 폴더 구성원이라 중복 정의 상태.
2. **KRX "상장/인수업무 규정"의 인수업무**: KRX 내규에는 "인수업무" 명칭 규정이 없다
   (인수업무 규정은 금투협 소관: 증권 인수업무 등에 관한 규정). KRX 측은
   유가증권시장 상장규정 + 시행세칙으로 해석했다. 코스닥시장 상장규정도 포함할지 결정 필요.
3. **KOFIA 신구조문대비표 커버리지**: 대상 4건의 현행 개정분에는 신구대비표 버튼이
   없을 수 있음 (증권 인수업무 최신 건은 전문+개정문만). 수용 기준의
   "role=comparison_table 1건 이상"은 개정 이력을 거슬러 탐색(과거 historySeq의
   revisionView 파싱)해야 충족 가능. 몇 개 판까지 거슬러 수집할지 결정 필요
   (제안: 최신 판 + 신구대비표가 발견되는 최근 1건).

# 5. 남은 [미확인] 목록

- KOFIA `searchTotal.do`(통합검색) 파라미터 — 트리로 전 규정 열거가 가능해 조사 생략
- KOFIA lawType='2'(비정형 규정) fileDown 흐름 — 대상 4건 모두 lawType='1'이라 불필요
- KRX `allDownload.do` 응답 형식 (§3-4) — Phase 3 구현 시 1회 호출로 확정
- KRX 별표·서식 개별 파일 열거 (getByulNode 하위 노드 전개) — 상장규정 별표는 본문 HTML에
  포함되어 있어 우선순위 낮음
