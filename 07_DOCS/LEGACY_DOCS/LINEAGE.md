# 계보 원장(lineage) — 수집→변환→구조화→연결을 문서 단위로 관통하는 파생 뷰

전처리 파이프라인의 각 단계는 자기 기록을 이미 갖고 있다 — 수집은 corpus
manifest, 변환은 사이드카와 리포트, 구조화는 문서별 meta.json, 연결은
links.json. 그런데 이 기록들은 서로를 모른다. "이 문서가 어느 단계까지
갔나", "수집 103건 중 구조화가 왜 29건인가" 에 답할 수 있는 곳이 없었다.
계보 원장이 그 답이다.

(이름 주의: `data/structure_ledger.json` 은 구조화 지문 관측 원장으로 별개다.
이 문서의 원장은 lineage — 문서 계보다.)

## 원칙

1. **원장은 파생이다 — 두 번 기록하지 않는다.** 각 단계의 자기 기록이
   ground truth 고, 원장은 요청 때마다 그것들을 조인해 계산하는 뷰다.
   별도 원장 파일을 두고 단계마다 갱신 의무를 지우면, 잊힌 자리에서
   원장이 거짓말하는 날이 온다. 파생이면 늦을 수는 있어도 틀리지 않는다.
2. **조인 키는 본문 sha256 이다 — 이름 매칭 금지.** 구조화 스토어의
   doc_id 는 본문 바이트의 sha256 앞 16자리다 (ingest_lawxml·업로드 공통,
   2026-08-13 실측 검증). 수집 manifest 도 본문 sha256 을 기록하므로
   `body_sha256[:16] == doc_id` 로 결정적으로 이어진다. 이름은 개정·개칭으로
   흔들리지만 바이트는 흔들리지 않는다.
3. **낙차는 정직하게.** 수집됐는데 구조화 안 된 것, 수집 밖에서 들어온 것
   (업로드), 재수집으로 낡은 것 — 전부 그대로 드러낸다. 조용한 누락 없음.

## 단계 모델

문서(= manifest 항목) 단위 세 단계 + 말뭉치 단위 한 국면:

| 단계 | ground truth | done 판정 |
|---|---|---|
| 수집 | `data/corpus/<출처>/manifest.json` | 항목 status=ok 이고 본문 sha 가 있다 |
| 변환 | 본문 옆 `.md` 사이드카 (lawrag/core/hwp5_md.py) | 본문 형식이 hwp 계열일 때만 요구되고, 사이드카 존재가 완료다 |
| 구조화 | `data/structure/<doc_id>/meta.json` | doc_id 디렉토리가 스토어에 있다 (passed·score 는 상세로 병기) |
| 연결 | `data/links.json` | 말뭉치 국면 — 문서 단위가 아니다 (아래) |

- 변환은 형식 조건부다: 법령 XML 은 ingest_lawxml 이 직접 옮기므로 변환
  단계가 없고(required=false), PDF 업로드도 마찬가지다. hwp 본문만 md
  사이드카가 필요하다. 별표서식 hwp 첨부의 사이드카는 개수로만 병기한다 —
  본문 계보의 관문이 아니라 부속물 손실의 기록이므로.

### 형식 → 경로 선언 — 다른 로직의 일원화

구조화까지 가는 **로직**은 형식마다 다르다: XML 은 태그에서 결정적 이관,
hwp 는 md 사이드카를 거치고, PDF·DOCX 는 업로드 해석 직행. 이것을
일원화하는 방법은 로직을 합치는 것이 아니라 **단계 모델을 하나로 두고
형식이 자기 경로만 선언하게** 하는 것이다 — lawrag/core/lineage.py `ROUTES`:

| 계열 | 변환 요구 | 구조화로 가는 길 |
|---|---|---|
| xml | 없음 | lawxml 결정적 이관 (lawrag/pipeline/ingest_lawxml.py) |
| hwp | md 사이드카 | lawrag/core/hwp5_md.py(레코드 XML 직독) → 구조화 — 파일 묶음은 lawrag/pipeline/ingest_files.py |
| pdf · docx | 없음 | 업로드 해석 직행 (POST /v1/structure/documents · lawrag/pipeline/ingest_files.py) |
| docx (내규) | 없음 | 유도 경로 + 내규 프로파일 (lawrag/pipeline/ingest_naegyu.py → core/internal_rules.py) |

새 형식이 오면 이 표에 한 줄이 늘 뿐, 단계 모델·조인 키(sha256)·화면은
그대로다. 선언은 형식 단위다 — 문서별 상수는 금지. 미선언 형식은 경로
없음으로 그대로 보인다(조용히 아는 척하지 않는다). 어느 길로 왔든
스토어에 닿는 순간 doc_id 가 본문 sha 이므로 원장 조인은 동일하다 —
XML 로 구조화된 25건이 아무 추가 기록 없이 원장에 서는 이유다.

**코드단도 한 문이다 — lawrag/core/ingest.py.** 선언(ROUTES)이 어휘라면 실행부는
`core.ingest.ingest(raw, filename, store=…)` 하나다: 계열 판정 →
xml 은 lawxml 이관, pdf 는 직행, hwp·docx 는 parse_adapter+합성 지면 —
전부 이 문 안의 분기다. 업로드 API(lawrag/api/routers/structure.py)와
CLI(lawrag/pipeline/ingest_lawxml.py)는 이 문을 부르는 낯일 뿐이고, 형식 바인딩(틀 연결)은
api 소유라 조회 함수(binding_of)로 주입받는다 — core 가 api 를 임포트하는
역방향을 만들지 않기 위해서다. 실행부 계열과 ROUTES 선언의 어휘 일치는
규약 테스트(tests/core/test_ingest.py)가 지킨다.
- 연결(settle)은 문서별 걸음이 아니라 말뭉치 전체를 한 번에 판정하는
  컴파일 국면이다. 그래서 원장의 최상위에 기록한다: links.json 존재 여부,
  확정 간선 수, settle 실행 이력(runs). 문서별로는 그 문서가 출발·도착인
  확정 간선 수만 센다. 사람의 pick 은 개별 수선이고 간선 자체에 via=사람
  으로 남으므로 runs 에 따로 쌓지 않는다.

각 항목에는 `next` — 다음 할 일 — 를 계산해 붙인다: 수집(본문 미확보) →
변환(사이드카 없음) → 구조화(스토어에 없음) → (없음). 감독 화면은 이
필드만 집계해도 깔때기가 된다.

## manifest 본문 정규화 — 두 세대

수집 manifest 에는 항목 모양이 두 세대 섞여 있다:

- 신형 (kofia·krx·law 대부분): 항목 수준 `body_sha256`·`body_file`·`body_format`
- 구형 (law 초기 4건): `attachments[]` 안의 `role == "body"` 첨부

원장의 본문 규칙: `body_sha256` 이 있으면 그것, 없으면 role=body 첨부의
sha256·file·actual_format. 둘 다 없으면 본문 미확보(수집 미완 — kofia
partial 2건이 실제 사례)다. 이 규칙은 lawrag/core/lineage.py `body_of()` 한 곳에만
있다.

## 고아 — 수집분과 조인되지 않는 스토어 문서

스토어에 있는데 현재 manifest 의 어느 본문 sha 와도 맞지 않는 문서는
버리지 않고 `extras` 로 보고한다. 둘로 가른다:

- **낡음(stale)**: 이름이 manifest 항목과 일치하는데 sha 가 다르다 —
  재수집으로 판이 갈린 것. 재구조화(ingest) 대상이라는 뜻이다.
- **수집 밖 유입**: 이름도 없다 — 화면 업로드 등. 정상 유입이되 수집
  파이프라인 밖이라는 사실을 그대로 보인다. (실측: 상품설명서 PDF 3건과
  초기 수동 인제스트 1건이 여기 해당)

## 연결 실행 이력 — links.json 의 "runs"

연결 단계만 자기 실행 기록이 없었다 (links.json 은 간선만 담고, settle 을
언제 몇 건 판정했는지는 응답으로 흘러가 버렸다). 그래서 단계 자신의
기록을 보강한다: `/v1/rag/links/settle` 이 저장할 때 links.json 에
`"runs": [{at, via, saved, ...판정 요약}]` 을 덧붙인다 (최근 50회 보관).
원장은 이것을 읽기만 한다. 기존 독자는 전부 `.get("links")` 로 읽으므로
키 추가는 호환이다.

## API · 화면

- `GET /v1/lineage/summary` — 출처별 깔때기 수치(항목·수집·변환·구조화)와
  연결 국면·고아 수. 홈 현황 카드용으로 싸다.
- `GET /v1/lineage` — 문서별 전체 계보(items·extras). 감독 화면용.
- `/lineage/` — 감독 화면. 출처별 깔때기(단계 상자를 누르면 그 단계에서
  멈춘 문서로 필터), 문서 표(수집·변환·구조화·참조·다음), 원장 밖 목록.
  읽기 전용 — 고치는 손은 각 단계의 화면·CLI 다.

경로 해석은 라우터가 한 번만 한다 — STRUCTURE_STORE 는
api.routers.structure 의 STORE 를, links 는 core.rag.index.links_path() 를
빌린다 (ops.py 와 같은 이유: env 를 두 번 해석하면 어긋나는 날이 온다).
corpus 는 lawrag/pipeline/collect.py 와 같은 저장소 루트의 `data/corpus/` 가 기본이고
CORPUS_DIR 로만 바꾼다(테스트용).

## 지금 실측 (2026-08-13)

수집 103 (law 25 · kofia 72 · krx 6) → 본문 확보 101 → 구조화 29
(조인 25 + 고아 4) → 연결 0 (links.json 없음, settle 무실행).
kofia·krx 의 hwp 본문 76건은 md 변환까지만 가 있다 — 구조화로 넘기는
걸음이 다음 공사다.

## 다음

- 코퍼스 배치 러너 — hwp 본문 76건의 낙차 해소. 파일 묶음 러너는 생겼다
  (lawrag/pipeline/ingest_files.py — 2026-08-19 KRX 상장 서식 9건·상장회사
  표준정관 1건을 이것으로 넣었다, kind=krx-form·klca-model). 남은 것은
  manifest 본문을 돌며 출처를 실어 문을 부르는 걸음과 KOFIA 무스타일 문서의
  구조화 품질 검증이다.
- hwp 변환은 2026-08-19 부터 레코드 XML 직독이 기본이다(lawrag/core/hwp5_md.py
  --engine xml). XSLT 로 120초를 두 번 넘겨 텍스트 폴백(표 전부 손실)으로
  떨어지던 상장 신청서 서식 3건이 5초 안에 표 120~307개를 살려 나왔고, 병합 셀
  정렬도 보존된다. 옛 XSLT 는 --engine html 로 대조용으로만 남는다.
- settle 은 `POST /v1/rag/links/settle?src_doc=<id>&src_doc=…` 로 출발 문서를
  좁힐 수 있다 — 새 문서 몇 건의 보류만 굳히는 비용(위 10건: 보류 150 → 확정
  131, haiku 23콜)으로 끝난다. 판정은 개수·글자 예산으로 묶어 부른다.
- 홈 화면에도 `/v1/lineage/summary` 요약 칩 하나 (자세한 감독은 /lineage/).
