# corpus/raw — 근거 문서 원문을 넣는 곳

여기에 원문을 넣으면 컴파일 타임에 라우터를 거쳐 구조화되고, 체크리스트가 요구하는
좌표만 발췌로 물질화된다. **런타임 LLM 은 이 폴더를 읽지 않는다** — 물질화된
`corpus/excerpts/` 만 읽는다(AGENT6_SPEC §2).

    raw/{ID}.pdf  +  raw/{ID}.meta.yaml
        ↓ corpus_build.py  →  router.route(파일, doc_type=...)
    structured/{ID}.doc.json      코어와 동일한 doc.json
        ↓ section 좌표 lookup
    excerpts/{ID}/{좌표}.txt      런타임이 로드하는 최종 형태
    manifest.json                 해소/미해소 — 이것이 빌드 게이트다

빌드:

    .venv/bin/python -m agents.agent6.src.corpus_build          # 운영
    .venv/bin/python -m agents.agent6.src.corpus_build --strict # CI (미해소 있으면 실패)

## 1. 파일 이름 = 코퍼스 ID

| ID | 문서 | 비고 |
|---|---|---|
| `KSB` | 금융소비자 보호에 관한 법률 (법률 본문) | 항목 basis 의 1차 근거 |
| `KSB-D` | 금소법 시행령 | |
| `KSB-S` | 금융소비자보호 감독규정 | |
| `KOFIA-R` | 표준투자권유준칙 (금융투자협회) | 권유 절차·고령자 보호 |
| `REC` | 고난도상품·고령·부적합 투자자 녹취/숙려 제도 | 조건부 항목 근거 |
| `CASE` | 금감원 제재사례·분쟁조정 사례 | few-shot·lexicon 시드 |
| `INT` | 사내 녹취 체크리스트 원본·내부통제기준 | 항목 목록의 원천 |

ID 는 항목 스펙의 basis 좌표 앞부분과 **정확히** 같아야 한다:
`basis: [{doc: KSB, section: "제19조/제3항"}]` → `KSB/제19조/제3항` → `raw/KSB.pdf`

한 ID 에 원문은 하나다. 같은 ID 를 두 파일이 주장하면 둘 다 거부된다 — 어느 쪽이
근거인지 정해지지 않은 채로 판정이 나가는 것보다 낫다.

## 2. provenance — 출처 없는 원문은 근거가 될 수 없다

두 가지 표기법이 있고, 검증은 같다.

**(a) 사이드카 `{ID}.meta.yaml`** — PDF 는 안에 주석을 넣을 자리가 없으므로 이쪽뿐이다.

```yaml
# agents/agent6/corpus/raw/KSB.meta.yaml
doc_id: KSB                      # 파일명과 같아야 한다
title: 금융소비자 보호에 관한 법률
source: law.go.kr                # 어디서 받았는가
source_url: https://www.law.go.kr/...   # 선택
enforced: 2026-01-02             # 시행일 (법령이면)
revision: 법률 제21065호           # 법령 번호 (있으면)
collected: 2026-08-05            # 받은 날 (YYYY-MM-DD)
verification: UNVERIFIED         # VERIFIED | UNVERIFIED | SYNTHETIC
doc_type: 금소법                  # 라우터에 넘길 doc_type (생략하면 자동 판별)
```

**(b) 첫머리 주석** — txt/md 원문은 파일 첫머리 `#` 주석 블록에 같은 항목을 적는다.
본문이 시작되면 헤더는 끝난다.

```
# doc_id: KSB
# title: …
# source: …
# collected: 2026-08-05
# verification: SYNTHETIC
# doc_type: 금소법
```

필수는 `doc_id · title · source · collected · verification` 다섯이다. 하나라도 없으면,
또는 `doc_id` 가 파일명과 다르면 그 원문은 **거부**되고 manifest 에 `REJECTED` 로 남는다.

선택 항목 중 빌드 동작을 바꾸는 것:

| 키 | 뜻 |
|---|---|
| `doc_type` | 라우터에 넘길 유형. 등록부(`core/registry.yaml`)에 없는 유형이면 `UNROUTABLE` — 구조가 다른 문서를 억지로 자르지 않는다 |
| `partial` | 발췌본이라 조 번호가 원래 띄엄띄엄하다. 결번은 그대로 보고하되 경고로 올리지 않는다 |
| `superseded` | 현행이 아닌 판본. 빌드는 되지만 **낡은 근거 경고**가 manifest 에 남는다 |
| `strip_patterns` | 발췌에서 지울 줄의 정규식 목록(아래 §3) |

`verification` 의 뜻:

- `VERIFIED` — 사람이 원문과 대조해 확인했다. 운영에 쓸 수 있다.
- `UNVERIFIED` — 받아서 넣기만 했다. 빌드는 되지만 경고가 남고 manifest 에 그대로 기록된다.
- `SYNTHETIC` — 합성물. **테스트 전용**이며 운영 빌드에서는 거부된다(`--allow-synthetic`).

## 3. 페이지 장식 — 발췌를 더럽히는 것들

국가법령정보센터 PDF 에는 페이지마다 머리글이 붙고, 그것이 조문 본문 사이에 섞인다.
제거는 두 층이다.

1. 파서가 `page_header`/`page_footer` 로 분류한 요소는 **자동 제거**된다(문서 구조 신호다).
2. 그렇게 분류되지 않은 반복 줄(예: `법제처 7 국가법령정보센터` 는 docling 이 본문으로 본다)은
   코드가 정하지 않는다. 사이드카의 `strip_patterns` 가 정한다:

   ```yaml
   strip_patterns:
     - '^법제처\s\d+\s국가법령정보센터$'
   ```

   빌드는 미지정 반복 줄을 `noise_candidates` 로 세어 **붙여 넣을 정규식까지** 제안한다.
   자동으로 지우지 않는 이유: 같은 규칙이 `삭제 <2020. 3. 24.>` 같은 진짜 본문도 잡는다.
   무엇이 장식인지는 사람이 확정한다.

## 4. 절대 규칙 — 법령 원문을 지어내지 않는다

기억에 의존해 조문을 써 넣지 말 것. 가짜 법조문이 진짜처럼 유통되는 것이 이 시스템의
최악의 실패다. 원문이 없으면 없는 채로 두면 된다 — manifest 가 MISSING 으로 시끄럽게
보고하고, 그 좌표를 basis 로 갖는 체크리스트 항목은 **활성화가 차단된다**(조용한 실패 금지).

테스트용 조문은 `tests/agent6/fixtures/corpus/` 아래에만, `verification: SYNTHETIC` 과
본문 첫 줄 "합성 픽스처 — 실제 법령 아님" 을 달아 둔다.

## 5. 원문 확보 경로

law.go.kr·fsc.go.kr 은 자동 접근을 차단한다. 다음 중 하나로 확보한다:

- **국가법령정보센터 Open API** (open.law.go.kr, 무료 신청제) — 자동화하려면 이쪽
- **수동 다운로드** — 담당자가 PDF/HWP 로 내려받아 이 폴더에 넣는다 (지금의 경로)

HWP 는 라우터가 받지 못한다. PDF 로 변환해 넣는다(텍스트 레이어가 살아 있어야 한다).

## 6. 수집 현황 — 지금 무엇이 없는가

넣을 때마다 이 표를 갱신한다. `python -m agents.agent6.src.corpus_build` 가
manifest 로 실제 상태를 다시 보고하므로, 이 표는 사람용 요약이다.
아래는 2026-08-05 빌드 결과 그대로다.

| ID | 상태 | 비고 |
|---|---|---|
| `KSB` | **확보** (2026-08-05) | [시행 2026.1.2.] 법률 제21065호. 제1~69조 결번 0, 잔여 0, 게이트 92% 통과. 요구 좌표 9개 전부 해소. `strip_patterns` 미지정 — 발췌에 `법제처 N 국가법령정보센터` 가 남아 있다 |
| `KSB-D` | 수집 대기 | 현행 시행령(대통령령). 아래 KSB-D-2021 은 대체물이 **아니다** |
| `KSB-D-2021` | 참고 보관 | 2021년 제정 시점 판본 — 현행 아님. 어느 항목도 basis 로 삼지 않아 빌드에서 `SKIPPED` |
| `KSB-S` | 수집 대기 | 금융소비자보호 감독규정 |
| `KOFIA-R` | 확보, **route 대기** | 조/항/호 구조가 아니다(로마숫자→N.→N)). `준칙` route 등록 전까지 `UNROUTABLE` |
| `REC` | 수집 대기 | 고난도·고령·부적합 녹취/숙려 |
| `CASE` | 수집 대기 | 사내 축적분 포함 |
| `INT` | 수집 대기 | 확보되면 체크리스트 목업(AGENT6 §3)을 교체한다 |

### 이것이 지금 막고 있는 것 (2026-08-05 빌드 기준)

미해소 basis 4개(`KOFIA-R`, `REC`, `CASE`, `INT`)가 체크리스트 30개 중 **11개**의
활성화를 막는다. 근거 없이 판정하느니 판정하지 않는다는 뜻이다.

| 미수집 코퍼스 | 차단되는 항목 |
|---|---|
| `KOFIA-R` (route 대기) | A-01, A-04, D-25, E-27, F-30 |
| `REC` | A-03, B-10, C-18, E-26, E-27 |
| `CASE` | D-20 (단정적 판단 제공 없음 — 부재형 대표 항목) |
| `INT` | A-02 |

`D-20` 이 막히는 것이 가장 아프다. 이 항목의 1차 근거인 `KSB/제21조/제1호` 는 이미
해소돼 있고 막는 것은 few-shot 시드용 `CASE` 좌표뿐이다. 제재사례가 들어올 때까지
이 항목을 돌리려면 호출자가 **명시적으로** 완화해야 한다:

    basis.blocked_items(items, manifest, allow_missing=["CASE"])

전부 푸는 스위치는 없다. 그런 스위치는 결국 켜진 채로 운영에 나간다.
