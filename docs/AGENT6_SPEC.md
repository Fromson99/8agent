# AGENT6 지시사항서 — AI 기반 불완전판매 Zero 시스템 (녹취 체크리스트 점검)

> 이 문서는 Claude Code가 단독으로 Agent6을 구현할 수 있도록 작성된 자립형 스펙이다.
> 플랫폼 원칙은 `SPEC.md`(v2), 값 대조 에이전트는 `AGENT1_SPEC.md` 참조. Agent6은 같은
> 뼈대(항목 스펙 외재화 · 단위 판정 반복 · provenance · 놓침 방지)를 쓰되, **판정기가
> `==`가 아니라 LLM**이라는 점이 다르다 — 검증 대상이 값이 아니라 행위이기 때문이다.

---

## 0. 시스템 한 문장 + 핵심 설계 원칙

**Agent6 = STT 전사가 들어오면, 체크리스트 항목마다 "미리 연결해둔 근거 문서 발췌 + 판정
기준 + few-shot"을 맥락으로 주입해 LLM이 항목별 pass/fail/unclear를 판정하고, 미비사항
안내문을 생성하는 시스템.**

원칙 (이 프로젝트 전체와 동일한 수법):
1. **런타임에 규정을 검색하지 않는다.** "이 발화에 관련된 조문 찾기"라는 열린 문제를 풀지
   않는다. 규정→체크항목 번역은 **컴파일 타임**에 사람이 검수하며 1회 수행되고, 각 항목에
   근거 조문 **발췌문이 물리적으로 첨부**된다. 런타임 LLM은 금소법을 읽지 않는다 — 항목
   스펙과 전사만 읽는다. (벡터 검색 없음. 유사도는 위반 여부를 판정하지 못한다.)
2. **닫힌 판정 문제.** 검사 항목이 약 30개로 고정. 열린 해석이 아니라 항목별 이진+UNCLEAR 판정.
3. **판정에는 근거 인용 강제.** 전사의 발화 스팬(타임스탬프)을 인용하지 못하는 판정은 무효
   → UNCLEAR. (Agent1의 "스팬 없으면 버린다"와 동일.)
4. **비대칭 임계.** 거짓 FAIL 비용(PB 재설명 몇 분) ≪ 거짓 PASS 비용(불완전판매 통과).
   "Zero" = 놓침 0. 자동 PASS 문턱이 가장 높고, 애매하면 UNCLEAR로 기운다.
5. **모호함은 제거가 아니라 수렴이 목표.** UNCLEAR는 1급 판정이며, 3단 경로로 해소되고
   few-shot으로 회수되어 항목별 UNCLEAR 비율이 우하향해야 한다.

---

## 1. 입력 / 출력

- 입력: STT 전사 파일(수동 업로드). 형식 `transcript.json`:
  `[{ "speaker": "PB|고객", "start": 12.3, "end": 15.1, "text": "..." }]`
  전사는 **라우터를 통해서만** 읽는다 — `router.require(path, doc_type="STT전사")`. 발화 하나가
  section 하나이며 좌표는 `발화001`, `발화002` …다(표기 규약은 §7). 여기서 json을 직접 열면
  agent6만 다른 방식으로 전사를 자르게 되고, 좌표가 어긋난 인용은 근거가 아니다.
  (speaker 라벨·타임스탬프가 없는 평문 txt도 수용하되, 근거 인용이 문자 오프셋으로 대체되고
  판정 confidence가 한 단계 감점됨을 리포트에 명시한다.)
  **confidence는 `high | medium | low` 3단계로 고정**이며, "한 단계 감점"은 이 사다리에서
  한 칸 내리는 것이다(`schema.downgrade()`, `low`에서 더 내려가지 않는다). 감점 사유는
  판정기 바깥에서 오며 집계 단계에서 한 번에 적용된다: 메타 부족으로 보수 활성된 항목
  (when UNKNOWN) · 화자/타임스탬프 없는 평문 전사 · STT 신뢰도 저하(`stt_confidence < 0.85`).
- 상품·고객 메타(선택): `{ "product_type": "ELS|펀드|신탁|...", "customer_age": 67,
  "risk_profile": "안정추구", "is_high_difficulty": true }` — 조건부 항목 활성화에 사용(§3).
- 출력: `report.json`(§7) + PB용 미비사항 안내문 `guidance.md` (정해진 형태 다운로드 요구 충족).

---

## 2. 근거 문서 코퍼스 (`corpus/`) — "미리 연결"의 재료

컴파일 타임에 아래 문서를 수집·발췌해 로컬에 둔다. **런타임은 이 발췌만 사용한다.**
**코퍼스 ID = `corpus/raw/`의 파일명**이며(사이드카의 `doc_id`와도 같아야 한다), basis 좌표가
그 ID로 원문을 찾는다.

| 코퍼스 ID | 문서 | 출처 | 용도 |
|---|---|---|---|
| KSB | 금융소비자보호법 (6대 판매규제: §17 적합성, §18 적정성, §19 설명의무, §20 불공정영업 금지, §21 부당권유 금지, §22 광고 + §23 계약서류, §46 청약철회, §47 위법계약해지) | law.go.kr | 항목의 1차 근거 |
| KSB-D-2021 | 금소법 시행령 (수집분의 판본을 ID에 붙인다) | law.go.kr | 설명의무 세부항목 — 현재 어느 항목도 근거로 삼지 않아 SKIPPED |
| KOFIA-R | 표준투자권유준칙 (금융투자협회 모범규준) | law.kofia.or.kr | 권유 절차·투자자정보 확인·고령자 보호 |
| REC | 고난도상품·고령(만65세+)·부적합판정 투자자 녹취/숙려 제도 | 금융위 보도자료·금투업규정 | 조건부 항목 근거 |
| CASE | 금감원 제재사례·분쟁조정 사례 (사내 축적분 포함) | fss.or.kr + 사내 | few-shot·lexicon 시드 |
| INT | 사내 녹취 체크리스트 원본·내부통제기준 | 사내 | 항목 목록의 원천 (§3은 이것이 올 때까지의 목업) |

**코퍼스는 평문 발췌 모음이 아니라 플랫폼 코어로 구조화된 문서다.** 규정 문서도 계약서와
같은 파이프라인을 탄다 — 즉 **bespoke 파서를 만들지 않고 registry에 route를 등록한다.**
법령은 조→항→호→목 구조가 계약서보다도 규칙적이어서 조/항/호 인식기가 그대로 적용된다:

```
corpus/raw/{ID}.pdf|txt (+ {ID}.meta.yaml)   # 원문 + provenance (출처·수집일·verification)
        ↓ corpus_build.py → router.route(파일, doc_type=…)   # 코어가 배차·구조화·채점
corpus/structured/{ID}.doc.json              # Agent1과 **동일한** doc.json 스키마
        ↓ 좌표 lookup (find_sections + 자손 subtree)
corpus/excerpts/{ID}/{좌표}.txt              # 컴파일 타임 물질화 (런타임이 로드하는 최종 형태)
corpus/manifest.json                         # basis 좌표의 해소/미해소 — 빌드 게이트
```

구현: `agents/agent6/src/corpus_build.py` (CLI `python -m agents.agent6.src.corpus_build`).
이 파일에는 **파싱도 구조화도 없다** — `router.route()`를 부르고, 나온 doc.json에서
체크리스트가 요구한 좌표만 골라 발췌로 굳힌다. 요구되지 않은 조문은 뽑지 않는다(발췌는
"미리 연결"의 결과물이지 조문 덤프가 아니다). 런타임이 발췌를 만나는 유일한 통로는
`agents/agent6/src/basis.py`이며, 그 안에 검색은 없다 — 좌표로 파일 하나를 여는 것이 전부다.

이 승격의 효과: (a) 항목 스펙의 basis가 파일 경로가 아니라 **section 좌표**
(`KSB/제21조/제1호`)가 되어 Agent1과 동일한 좌표 체계로 통일된다. (b) 법 개정 시 raw만
갱신하면 발췌가 재물질화된다(발췌 파일 수동 관리 소멸 — 이번 빌드에서 물질화되지 않은
묵은 발췌는 **지운다**. 회수된 코퍼스의 잔재를 런타임이 읽으면 manifest가 MISSING이라고
말해도 소용이 없다). (c) **manifest가 빌드 게이트를 겸한다** — 미수집 조문은 MISSING으로
시끄럽게 보고되며, 미해소 basis를 가진 항목은 `basis.blocked_items()`로 활성화가 차단된다
(조용한 실패 금지).

### 2.1 route 등록 — 코퍼스가 라우터를 타는 방법

`core/registry.yaml`에 agent6이 owner인 route 4개가 등록돼 있고, 그 자산은
`agents/agent6/{formats,glossary}/`에 있다:

| doc_type | detect | format / glossary | 임계 |
|---|---|---|---|
| 금소법 | `content_all: 금융소비자 보호에 관한 법률` + `content_any: ["[시행", "법률 제"]` | `statute.*` | 0.60 |
| 금소법시행령 | `content_all: … 시행령` + `content_any: ["이영은","이 영은"]` | `decree.*` | 0.60 |
| 표준투자권유준칙 | `content_any: ["표준투자권유준칙","투자권유준칙"]` | `kofia_rule.*` | 0.60 |
| STT전사 | `extension: .json` + `schema_hint: speaker` | `transcript.*` (parser 플러그인 `transcript`) | 0.50 |

detect 규칙이 이름만으로 갈리지 않는다는 것이 실측의 교훈이다 — 계약서 본문도 금소법을
인용하므로, 국가법령정보센터 산출물의 시행일·법률번호 머리글을 원문의 표지로 쓴다.
표준투자권유준칙은 법령이 아니라 모범규준이라 113쪽에서 `제N조` 마커가 1개뿐이고, 그래서
조/항/호가 아닌 별도 형식(로마숫자 → `N.` → `N)`)을 갖는다. **구조가 다르면 route가 다르다.**

원문에는 provenance가 필수다 — txt는 첫머리 `# key: value` 주석, PDF는 `{ID}.meta.yaml`
사이드카. 필수 항목은 `doc_id · title · source · collected · verification`이고, `doc_id`는
파일명과 같아야 한다(코퍼스 ID = 파일명이어야 좌표가 원문을 찾는다). `verification: SYNTHETIC`은
운영 빌드에서 **기본 거부**이며 `--allow-synthetic`으로만 통과한다 — 합성 조문이 진짜 법령처럼
유통되는 것이 이 시스템의 최악 실패다.

### 2.2 현재 코퍼스 상태 (`corpus/manifest.json`, 2026-08-05 빌드)

| ID | 상태 | 비고 |
|---|---|---|
| KSB | **OK** | 25p, 제1~69조 결번 0, 게이트 92% 통과. 요구 좌표 9개 전부 RESOLVED |
| KSB-D-2021 | SKIPPED | 원문은 있으나 어느 항목도 근거로 삼지 않는다 |
| KOFIA-R | UNROUTABLE | 원문(113p)은 있으나 사이드카의 `doc_type`이 등록부의 이름과 어긋나 배차되지 않는다 |
| REC / CASE / INT | MISSING_SOURCE | 원문 수집 대기 |

결과: basis 좌표 13개 중 **해소 9 / 미해소 4**, 그로 인해 **활성화 차단 항목 11개**
(A-01·A-02·A-03·A-04·B-10·C-18·D-20·D-25·E-26·E-27·F-30). 이 숫자가 "지금 무엇을 판정할 수
있는가"의 답이며, 원문이 들어오면 자동으로 줄어든다.

## 3. 체크리스트 목업 (약 30개) — INT 확보 전까지의 대체물

유형: **존재형**(필수 발화의 존재) / **부재형**(금지 발화의 부재) / **충분성형**(정도 판정).
`when`은 조건부 활성화(메타 기반, 결정론).

**`when`은 자연어가 아니라 작은 DSL이다** (`agents/agent6/src/when.py`). 항목 스펙은 데이터지
코드가 아니므로 `eval()`을 쓰지 않고 손으로 짠 재귀 하강 파서가 읽는다. 문법:

```
expr       := or_expr
or_expr    := and_expr ("or" and_expr)*
and_expr   := primary ("and" primary)*
primary    := "(" expr ")" | "always" | comparison
comparison := IDENT (("=="|"!="|">="|"<="|">"|"<") literal
                    | ["not"] "in" "[" literal ("," literal)* "]")
literal    := 수 | true | false | 맨낱말(한글 포함) | "따옴표 문자열"
```

필드명은 ASCII 식별자로 제한한다(메타 키는 코드·JSON이 함께 쓰는 이름이라 한글 필드명을
허용하면 STT 파이프라인 쪽 키와 조용히 어긋난다). 문법 오류는 **로드 시점에** 터진다 —
런타임까지 미루면 판정 도중에 멈춘다.

아래 표의 `when` 열은 `checklist/items/*.yaml`에 실제로 적힌 식이다.

| id | 항목 | 유형 | 근거(basis 좌표) | when |
|---|---|---|---|---|
| A-01 | 판매자 소속·성명 고지 | 존재형 | KOFIA-R | `always` |
| A-02 | 고객 본인확인 실시 | 존재형 | INT | `always` |
| A-03 | 녹취 진행 사실 고지 | 존재형 | REC | `always` |
| A-04 | 투자자정보(투자성향) 확인 실시 | 존재형 | KSB/제17조, KOFIA-R | `always` |
| A-05 | 투자성향 결과 및 상품 위험등급 대비 고지 | 존재형 | KSB/제17조 | `always` |
| B-06 | 상품명·유형 명시 | 존재형 | KSB/제19조 | `always` |
| B-07 | 원금손실 가능성 고지 | 존재형 | KSB/제19조 | `always` |
| B-08 | 예금자보호 미적용 고지 | 존재형 | KSB/제19조 | `always` |
| B-09 | 투자위험등급 고지 | 존재형 | KSB/제19조 | `always` |
| B-10 | 최대 원금손실 가능금액 고지 | 존재형 | REC | `is_high_difficulty == true` |
| B-11 | 판매수수료·보수 설명 | 존재형 | KSB/제19조 | `always` |
| B-12 | 환매 방법·환매수수료 설명 | 존재형 | KSB/제19조 | `always` |
| B-13 | 중도해지 시 불이익 설명 | 존재형 | KSB/제19조 | `has_early_termination_penalty == true` |
| B-14 | 조기상환 조건 설명 | 존재형 | KSB/제19조 | `product_type in [ELS, ELB, DLS, DLB, ELT, ELF]` |
| B-15 | 만기·투자기간 설명 | 존재형 | KSB/제19조 | `always` |
| C-16 | 청약철회권 고지 | 존재형 | KSB/제46조 | `has_withdrawal_right == true` |
| C-17 | 위법계약해지권 고지 | 존재형 | KSB/제47조 | `always` |
| C-18 | 숙려기간 고지 | 존재형 | REC | `is_high_difficulty == true or customer_age >= 65` |
| C-19 | 계약서류 제공 안내 | 존재형 | KSB/제23조 | `always` |
| D-20 | 단정적 판단 제공 없음 | 부재형 | KSB/제21조/제1호, CASE | `always` |
| D-21 | 손실보전·수익보장 약속 없음 | 부재형 | KSB/제21조 | `always` |
| D-22 | 사실과 다른 설명 없음 | 부재형 | KSB/제21조 | `always` |
| D-23 | 확실 오인 소지 표현 없음 | 부재형 | KSB/제21조/제1호 | `always` |
| D-24 | 타상품 비방·왜곡 비교 없음 | 부재형 | KSB/제21조 | `always` |
| D-25 | 투자 재촉·강요 표현 없음 | 부재형 | KOFIA-R | `always` |
| E-26 | 부적합 상품 판매 시 부적합 사실 고지·확인 | 존재형 | KSB/제17조, KSB/제18조, REC | `is_suitable == false` |
| E-27 | 고령투자자 보호절차 안내 | 존재형 | KOFIA-R, REC | `customer_age >= 65` |
| F-28 | 고객 이해 확인(질문·응답 존재) | 존재형 | KSB/제19조/제3항 | `always` |
| F-29 | 위험 설명의 충분성 | 충분성형 | KSB/제19조 | `always` — **`derived: {all_pass: [B-07, B-09, F-28]}`. 독립 LLM 판정 금지** |
| F-30 | 고객 질문에 대한 성실 응답 | 충분성형 | KOFIA-R | `customer_question_count >= 1` |

`customer_question_count`는 **전처리가 결정론으로 센다** — 판정기(LLM)가 세면 같은 전사가
호출마다 다른 활성 집합을 갖는다. 메타에 값이 이미 있으면 덮지 않는다(사람이 준 값 우선).

### 3.1 메타가 없을 때 — 세 값 논리와 보수적 활성

메타(`product_type` · `customer_age` · …)는 **전부 선택 입력**이다. 전사만 올라오는 호출이
실제로 있다. 이때 `customer_age >= 65`를 조용히 거짓으로 접으면 C-18·E-27이 통째로 사라지고,
리포트에는 흔적조차 남지 않는다 — 점검하지 않은 항목이 점검한 것처럼 보인다. §0 원칙 4가
금지하는 정확히 그 실패다.

그래서 평가 결과는 `ACTIVE / INACTIVE / **UNKNOWN**` 세 값이며, **UNKNOWN은**

1. 보수적으로 **활성**시키고(`WhenResult.active`가 참),
2. 이유("메타 부족: customer_age")를 `when_notes`로 남겨 리포트에 싣고,
3. 판정 confidence를 **한 단계 낮춘다**(high→medium→low).

and/or는 Kleene 3치 논리를 따른다 — UNKNOWN이 결과를 바꾸지 못하는 곳에서는 사라진다.
`is_high_difficulty == true or customer_age >= 65`에서 나이가 67로 확정이면
`is_high_difficulty`가 없어도 결과는 ACTIVE이고 감점도 없다. 타입이 안 맞는 메타
(`customer_age: "예순일곱"`)도 거짓이 아니라 UNKNOWN이다.

주: F-29는 충분성형의 분해 전략 예시다 — "충분히"를 직접 판정하지 않고 관찰 가능한 존재형
항목들의 논리 조합으로 산출한다. F-30만 순수 충분성 판정으로 남고, 초기 confidence가 낮으면
상시 준법감시 큐로 보낸다. **INT(실제 체크리스트) 확보 시 이 표 전체를 교체한다** — 코드는
항목 스펙 파일만 읽으므로 교체 비용은 데이터 교체뿐이어야 한다(하드코딩 금지).

## 4. 항목 스펙 포맷 (`checklist/items/*.yaml`) — 이 시스템의 심장

아래는 `agents/agent6/checklist/items/D-20.yaml`의 실물이다(스키마: `src/schema.py`의 `ChecklistItem`).

```yaml
id: D-20
name: 단정적 판단 제공 없음
type: 부재형
when: always
basis:                                  # ← "미리 연결" — section 좌표 (Agent1과 동일 좌표계)
  - { doc: KSB, section: "제21조/제1호", note: "부당권유 금지 — 조 직속 호 구조" }
  - { doc: CASE, note: "제재·분쟁조정 사례 — 사례 ID 미확정(수집 대기)" }
operational_definition: >
  수익률·가격·상환·손실 등 불확실한 미래 사항에 대해 확정적 표현을 사용했는지 판정한다.
  위반 예: "무조건 오릅니다", "원금 보장이나 다름없어요", "손해 볼 일 없습니다".
  적법 예: "과거 수익률이 이랬습니다(미래 보장 아님을 부연)", "원금 보장 안 됩니다".
lexicon:                                # 결정론 1차 신호 (정규화 후 매칭)
  hit: [확실, 보장, 무조건, 절대, 틀림없, "100%", 걱정 없, 손해 볼 일 없, 반드시, …]
  guard: [보장되지 않, 보장 안 됩, 확실하지 않, 장담할 수 없, …]   # 부정 문맥 — hit 상쇄
few_shot:                               # 사람 해소 결과가 여기로 재적재된다 (§6 루프)
  - { utterance: "이건 나라가 망하지 않는 한 안전해요", verdict: FAIL, reason: "확실 오인 소지" }
  - { utterance: "원금 보장은 안 되지만 변동성은 낮은 편입니다", verdict: PASS, reason: "guard 문맥" }
judgment_hints:
  scan_scope: full                      # 부재형은 전사 전체 스캔
  fail_route: 준법감시큐                 # 부재형 위반은 이미 발화됨 — PB 재설명으로 소거 불가
  unclear_route: 준법감시큐
```

선택 필드: `derived`(파생 규칙 — §3 F-29 참조), `enabled`(끄는 것도 스펙에 남긴다. 파일 삭제
금지), `note`(번역·판단 근거 기록), `basis[].note`, `few_shot[].source`.

**로더가 강제하는 것** (`schema.load_items`) — 어기면 로드 자체가 실패한다:

- `id`는 `A-01` 형식이고 **파일명과 같아야** 한다. id 중복도 거부.
- `basis.section`은 파일 경로가 아니라 **section 좌표**다. 확장자·`..`·`\`가 보이면 거부한다.
  좌표를 모르면 `section`을 **아예 쓰지 않는다**(빈 문자열 금지) — 지어내는 것보다 낫다.
- **부재형의 `fail_route`·`unclear_route`는 반드시 `준법감시큐`**다. 이미 한 말은 PB 재설명으로
  지워지지 않는다. 존재형은 `PB보완`(재설명으로 원천 해소 가능)이 정상이며, 아니면 경고가 뜬다.
- `derived`를 가진 항목은 `type: 충분성형`이어야 하고, 자기 자신·다른 파생 항목을 참조할 수 없다
  (파생의 연쇄 금지 — 순환 위험). 참조 대상이 없으면 로드 실패.
- **파일 하나가 깨지면 로드 전체가 실패한다.** 항목이 27개만 로드되고 3개가 조용히 빠진 채
  "활성 항목 전부 PASS" 리포트가 나가는 것이 최악의 실패다.
- 경고(로드는 되지만 사람이 봐야 하는 것): 부재형인데 lexicon이 빔, few_shot 없음 등.

**유형이 라우팅을 결정한다** — 존재형 미비는 PB가 지금 다시 말하면 해소되지만, 부재형
위반(이미 한 말)은 재녹취로 지울 수 없으므로 사람 검토로 간다.

## 5. 런타임 파이프라인

모듈 대응: `preprocess → lexicon → context_asm → judge → cross_signal → aggregate → report`
(진입점 `agents/agent6/src/cli.py`의 `run_pipeline`). **LLM 키가 없어도 끝까지 돈다** — 키가
없으면 판정기가 결정론 모드로 자동 강등하고 그 사실을 리포트에 적는다(§5.1).

1. **전처리** — 전사 로드(`router.require`, doc_type `STT전사`)·화자 정규화·매칭용 문자열 생성.
   형태소 처리(kiwipiepy)는 **있으면 쓰고 없으면 문자 정규화로 자동 강등**하며, 강등 사실을
   경고로 남겨 리포트에 싣는다(현재 환경에는 kiwipiepy가 설치돼 있지 않다). 메타로 `when`
   평가 → 활성 항목 확정(§3.1). 미해소 basis 항목의 차단은 `basis_policy`가 정한다
   (`warn` 기본 / `block`).
2. **결정론 신호 패스** — 활성 항목의 lexicon을 전 전사에 매칭. 항목별 후보 스팬 목록 생성.
   LLM 이전의 **독립** 신호이며, 상쇄된 적중도 지우지 않고 `guarded=True`로 남긴다(신호를
   조용히 버리면 교차 검증할 것이 없어진다). guard 상쇄는 두 단계다 —
   **거리 0(같은 발화)은 강한 상쇄**, **거리 1(같은 화자의 인접 발화)은 약한 상쇄**다.
   STT가 한 문장을 턴 경계로 자주 자르기 때문이고, 화자가 다르면 다른 말이므로 보지 않는다.
3. **컨텍스트 조립** — 항목별로: `operational_definition + basis 발췌 원문 + few_shot +
   전사(또는 후보 스팬 강조 표시된 전사)`. 검색 없음 — 전부 사전 연결된 파일 로드.
4. **LLM 판정** — structured output: `{item_id, verdict: PASS|FAIL|UNCLEAR,
   evidence: [{section_id, text}], reason, confidence}`. 인용 좌표는 발화 section_id(`발화001`)로
   받는다 — 좌표 없는 인용은 인용이 아니므로 버린다. 인용은 전사와 **문자 대조**하고,
   전사에 없으면 그 인용을 버린다. LLM이 적은 좌표가 실제와 다르면 전사가 이긴다.
   **인용을 대지 못한 판정은 UNCLEAR로 강등**하되, 강등 대상은 "있음을 주장하는 판정"이다 —
   존재형 PASS(말했다)·부재형 FAIL(말했다)·충분성형 PASS/FAIL. "없음의 주장"(존재형 FAIL,
   부재형 PASS)은 인용할 스팬이 원리적으로 없으므로 강등하지 않는다(§7의 B-07 FAIL 예시가
   `evidence: null`인 이유).
   배치 전략: 항목 3~6개씩 한 호출에 묶되(비용·지연 절감, 기본 `max_batch=6`) 항목별 독립
   판정 스키마를 유지한다. `per_item` 설정으로 항목당 한 호출로 전환 가능. 배치 응답에서
   빠진 항목은 조용히 사라지지 않고 결정론 판정으로 대체되며 그 사실이 `method`에 남는다.
5. **신호 교차** — lexicon과 LLM의 불일치 규칙: 부재형에서 lexicon hit(guard 미상쇄)인데
   LLM PASS → UNCLEAR로 승급. 존재형에서 lexicon 무매칭인데 LLM PASS → evidence 스팬이
   실제 전사에 존재하는지 문자 검증(환각 인용 차단), 불일치 시 UNCLEAR.
   교차는 **의심을 더하는 방향으로만** 움직인다 — FAIL→PASS, UNCLEAR→PASS 승급은 없다.
6. **집계·판정** — 파생 항목(F-29) 계산(다른 항목이 다 정해진 **뒤에**). confidence 감점을
   여기서 한 번에 적용한다(§1). 전체 상태: 활성 항목 전부 PASS → `완전판매요건충족`,
   FAIL/UNCLEAR 존재 → `보완필요`(판매 프로세스 진행 불가).
7. **미비사항 안내 생성** — PB보완 라우팅 항목들에 대해 "다음을 명확히 다시 안내해 주세요:
   [항목명 + 무엇이 빠졌는지 + 권장 안내 문구(basis 기반)]" 형태의 guidance.md.
   권장 문구는 **지어내지 않고 스펙에서 가져온다** — 1순위 few_shot의 PASS 예시, 2순위
   운영 정의의 첫 문장, 둘 다 없으면 빈칸(빈 것이 지어낸 것보다 낫다). 파생 항목은 자기
   문구가 없으므로 실패한 구성 항목의 문구를 인용한다.
   준법감시큐 라우팅 항목은 안내문에 "검토 중" 표기 + 큐 파일(`review_queue.jsonl`)에 적재
   (같은 전사·항목은 다시 넣지 않는다 — 큐는 사람의 작업 목록이다).

### 5.1 LLM-off 판정표 (성능 저하 모드)

`--no-llm`이거나, API 키가 없거나, 호출이 실패하면 **자동으로 결정론 판정기로 강등**하고
강등 사실을 리포트에 적는다(`mode: lexicon` / `llm(부분 강등)`, `method: lexicon_only`).
"LLM이 없어서 점검을 못 했다"는 결과는 내지 않는다 — 못 한 점검은 놓침이다.

| 유형 | lexicon 신호 | 판정 | confidence | 라우팅 |
|---|---|---|---|---|
| 부재형 | 유효 적중 있음 | UNCLEAR | low | 준법감시큐 |
| 부재형 | 인접 발화 guard로만 상쇄됨(약한 상쇄) | UNCLEAR | low | 준법감시큐 |
| 부재형 | 적중 없음 / 같은 발화 guard 상쇄 | PASS | low | — |
| 존재형 | 유효 적중 있음 | PASS | low | — |
| 존재형 | 적중 없음(또는 전부 상쇄) | UNCLEAR | low | 준법감시큐 |
| 충분성형 (파생 아님) | 무관 | UNCLEAR | low | 준법감시큐 |
| 충분성형 (파생) | — | aggregate가 계산 (§9-5) | — | 구성 항목이 정함 |

구현은 `agents/agent6/src/judge.py`의 `judge_deterministic()`이다. **표와 코드가 어긋나면
표가 정본이다.**

왜 이렇게 기우는가 — 이 표는 대칭이 아니다. 부재형은 신호가 **있으면** 의심하고, 존재형은
신호가 **없으면** 의심한다. 두 경우 모두 "판단을 미루는 쪽"이 UNCLEAR다(§0 원칙 4: 거짓
FAIL/UNCLEAR의 비용은 사람이 몇 분 더 보는 것, 거짓 PASS의 비용은 불완전판매 통과).
FAIL을 확정하지 않는 것도 같은 이유다 — 문자 매칭은 반어("보장된다고들 하지만")·인용·부정을
구별하지 못하고, 그 구별을 못 하는 판정기의 확신은 잘못된 확신이다. 부재형에서 인접 발화
guard를 믿지 않는 이유도 같다: 인접 상쇄는 문맥 판단인데 이 모드에는 문맥을 읽는 판정자가 없다.

## 6. 모호함 처리 — 감지·라우팅·수렴 루프

- **감지 3종**: (a) evidence 인용 불가, (b) lexicon↔LLM 신호 불일치, (c) (설정 시) k-회
  자기일관성 불일치 — 경계 confidence 판정에만 적용.
- **라우팅**: 항목 스펙의 `fail_route/unclear_route`가 결정. 기본 —
  존재형 미비 → **PB 보완**(가장 싼 해소: 모호한 녹취를 명확한 녹취로 원천 교체) /
  부재형 위반·모든 UNCLEAR → **준법감시 큐** / 항목별 UNCLEAR 비율이 기준(예: 월 15%)
  이상 지속 → **컴파일 타임 스펙 개선**(정의 재작성·분해·few-shot 보강).
- **수렴 루프**: 큐의 사람 해소 결과 `{utterance, verdict, reason}`을 해당 항목의 few_shot에
  재적재하는 CLI(`harvest` 명령, `--dry-run` 지원)를 제공한다. 항목 스펙 YAML은 pyyaml로
  왕복시키지 않고 **텍스트로 다뤄 few_shot 블록에만 줄을 끼워 넣는다** — 왕복하면 주석("이
  when을 왜 이렇게 옮겼는가" 같은 번역 근거)이 전부 사라지고 키 순서가 바뀐다. 쓰고 나서
  `schema.load_item`으로 다시 읽어 검증하고, 깨졌으면 원문을 되돌린다.
  항목별 UNCLEAR 비율은 실행마다 `output/unclear_rate_history.json`에 누적되고 그 시점까지의
  비율이 리포트에 실린다 — UNCLEAR는 없애야 할 것이 아니라 **우하향해야 할 것**이다.

## 7. 리포트 스키마 (`report.json`)

```json
{
  "transcript": "call_2026_0805_001.json", "checklist_version": "mock-1", "generated_at": "…",
  "overall": "보완필요",
  "items": [
    { "id": "B-07", "name": "원금손실 가능성 고지", "type": "존재형", "active": true,
      "verdict": "FAIL", "route": "PB보완",
      "evidence": null, "lexicon_hits": [], "llm_reason": "전사 전체에서 해당 고지 미발견",
      "basis_refs": ["KSB/제19조"], "confidence": "high", "method": "llm+lexicon" },
    { "id": "D-20", "verdict": "UNCLEAR", "route": "준법감시큐",
      "evidence": [{ "section_id": "발화137", "start": 512.4, "end": 519.0,
                     "text": "나라 망하지 않는 한 괜찮아요" }],
      "lexicon_hits": [{ "term": "걱정 없", "section_id": "발화137", "guarded": false }],
      "llm_reason": "확실 오인 소지 경계 사례", "basis_refs": ["KSB/제21조/제1호", "CASE"],
      "confidence": "low", "method": "signal_conflict" },
    { "id": "C-16", "name": "청약철회권 고지", "type": "존재형", "active": false,
      "verdict": "NOT_APPLICABLE", "inactive_reason": "조건 미충족: has_withdrawal_right == true",
      "confidence": "medium", "method": "llm+lexicon" }
  ],
  "stats": { "total": 30, "active": 27, "pass": 24, "fail": 2, "unclear": 1,
             "not_applicable": 3 },
  "unclear_rate_history": { "D-20": [0.22, 0.18, 0.15] },
  "meta": { "customer_age": 67, "product_type": "ELS" },
  "notes": ["판정 모드: llm", "정규화: 문자(kiwipiepy 없음)", "경고: …"]
}
```

**활성 항목 전부가 정확히 한 행씩** 나타난다(NOT_APPLICABLE 포함 — 비활성 사유 명시).
`Report.assert_complete(items)`가 체크리스트와 리포트 행의 집합 일치를 강제한다.

표기 규약 (agent6 담당자 공통 — 코드·데이터·리포트가 모두 이것을 쓴다):

- `basis_refs`는 **`{코퍼스ID}/{section_path}`** — `KSB/제19조`, `KSB/제21조/제1호`,
  `CASE/2023-046`. 조문 번호를 축약한 `KSB/19-1` 같은 표기는 쓰지 않는다(발췌 파일 경로
  `corpus/excerpts/KSB/제21조_제1호.txt`가 이 좌표에서 기계적으로 나온다).
- `evidence[]`는 `{text, section_id, start?, end?, char_start?, char_end?}`이며 **좌표가 최소
  하나는 있어야** 한다. section_id는 전사 발화 좌표(`발화001`)다.
- `route`는 `PB보완 | 준법감시큐`, `confidence`는 `high | medium | low`,
  `verdict`는 `PASS | FAIL | UNCLEAR | NOT_APPLICABLE`.
- `method`는 판정이 어떻게 나왔는지: `llm+lexicon` · `lexicon_only`(LLM-off·강등) ·
  `signal_conflict` · `derived` · `evidence_missing` · `evidence_unverified` · `llm_missing`.
- 스키마가 강제하는 불변량: `active=false ⇔ NOT_APPLICABLE`이며 이때 `inactive_reason`이
  필수, `FAIL`/`UNCLEAR`에는 반드시 `route`가 있다(라우팅 없는 미비는 사라진 미비다).

## 8. 구현 작업 (빌드 오더)

상태 표기: **[구현됨]** = 코드가 저장소에 있고 돈다, **[미구현]** = 아직 없다.

- **T-A6.1 스키마·로더** — 항목 스펙/코퍼스 발췌/전사/리포트 pydantic 모델(`src/schema.py`).
  basis는 파일 경로가 아니라 좌표이므로 **형태 검증**을 하고, 좌표의 해소 여부는 코퍼스
  manifest가 판정한다(`src/basis.py`). **[구현됨]**
- **T-A6.2 코퍼스 구축** — `src/corpus_build.py`. 원문(PDF/txt)을 **라우터에 배차**해
  doc.json을 만들고(§2), 체크리스트가 요구한 좌표만 발췌로 굳히고, manifest를 쓴다.
  CLI: `python -m agents.agent6.src.corpus_build [--raw DIR] [--out DIR] [--items DIR]
  [--allow-synthetic] [--strict]`. `--strict`가 CI 게이트다(미해소 basis가 하나라도 있으면
  실패로 끝난다). 조 번호 결번 보고와 반복 머리글(`noise_candidates`) 보고를 표준 출력에
  포함한다 — 파싱 누락과 발췌 오염이 조용히 지나가지 않게 한다. **[구현됨]**
  남은 작업: (a) **법령 원문 확보** — law.go.kr·fsc.go.kr은 자동 접근을 차단하므로 담당자가
  수동 다운로드한 PDF를 `corpus/raw/`에 투입하고 사이드카를 쓴다(공통 규칙 §4: 조문을
  기억으로 지어내지 않는다). (b) `--strict` 빌드를 CI에 연결. (c) KOFIA-R 사이드카의
  `doc_type`을 등록부의 route 이름과 맞추기(현재 UNROUTABLE의 원인).
- **T-A6.3 목업 체크리스트 작성** — §3의 30개를 §4 포맷 YAML로. `checklist/items/*.yaml`
  30개, lexicon·few_shot 시드 포함. **[구현됨]**
- **T-A6.4 전처리·lexicon 엔진** — `src/preprocess.py`(라우터 경유 전사 로드, 정규화기,
  when 평가, 질문 수 계산) + `src/lexicon.py`(guard 두 단계 상쇄) + `src/when.py`(DSL).
  형태소 처리는 kiwipiepy가 있으면 쓰고 없으면 문자 정규화로 강등한다. **[구현됨]**
- **T-A6.5 컨텍스트 조립기·LLM 판정기** — `src/context_asm.py` + `src/judge.py`.
  인용 문자 검증(환각 차단)과 LLM-off 판정표(§5.1) 포함. **[구현됨]**
- **T-A6.6 신호 교차·집계·라우터** — `src/cross_signal.py` + `src/aggregate.py`. **[구현됨]**
- **T-A6.7 리포트·안내문 생성** — `src/report.py`: report.json + guidance.md +
  review_queue.jsonl + unclear_rate_history.json. **[구현됨]**
- **T-A6.8 harvest CLI** — `src/harvest.py`, 큐 해소 결과 → few_shot 재적재. **[구현됨]**
- **T-A6.9 골든·변이 테스트** — §9. 현재 있는 것은 `tests/agent6/test_corpus.py`(코퍼스 빌드·
  발췌·차단 30여 케이스)와 `tests/agent6/test_when.py`(when DSL). **전사 골든 픽스처
  (clean/violation/ambiguous)와 변이 12종은 [미구현]** — §9가 그 기준이다.

## 9. 완료 기준 (골든 픽스처 기반)

**현황**: 코퍼스 쪽 기준은 `tests/agent6/test_corpus.py`가, when 평가(아래 3의 후반)는
`tests/agent6/test_when.py`가 이미 지킨다. 전사 픽스처 3종과 변이 12종은 아직 없다.

`tests/agent6/fixtures/`에 목업 전사 3종을 작성한다(각 40~80 발화, 화자·타임스탬프 포함):
- `clean.json` — 활성 항목 전부 충족. 기대: overall=완전판매요건충족, fail=0, unclear=0.
- `violation.json` — B-07 누락 + D-20 위반("무조건 오릅니다") + C-17 누락 심음.
  기대: 정확히 그 3개 항목만 FAIL, D-20 evidence가 심은 발화 스팬과 일치,
  B-07·C-17은 route=PB보완으로 guidance.md에 재안내 문구 존재, D-20은 큐 적재.
- `ambiguous.json` — 경계 발화("나라 망하지 않는 한 괜찮아요") 심음.
  기대: D-20=UNCLEAR(신호 교차 발동), 큐 적재, 자동 PASS 아님.

추가 기준:
1. **놓침 0 검증(변이)**: clean에 위반 발화를 1개씩 주입한 변이 **12종
   (부재형 6항목 D-20~D-25 × 항목별 lexicon 대표 표현 2개)** 전부에서 해당 항목이
   FAIL 또는 UNCLEAR — **PASS로 통과하는 변이가 하나도 없다.**
2. evidence의 모든 인용이 전사에 실제 존재(문자 검증 테스트).
3. 활성 항목 수 = 리포트 행 수 (조용한 스킵 없음). when 평가 테스트(age=67 → C-18·E-27 활성).
4. 판정 프롬프트에 코퍼스 발췌가 실제 포함됨(컨텍스트 조립 단위 테스트) — 런타임에 corpus
   외부 검색·벡터 조회가 일절 없음.
5. F-29가 독립 LLM 판정 없이 파생 계산됨.
6. lexicon 단독으로도(LLM off 모드) 변이 12종 중 lexicon 커버 항목이 전부 UNCLEAR 이상으로
   걸림 — LLM 장애 시에도 놓침 0 유지(성능 저하 모드). 판정표는 §5.1.

## 10. 저장소 구조

```
agents/agent6/
  checklist/items/*.yaml            # §4 — 30개 (목업 → INT 교체 예정)
  corpus/
    raw/{ID}.pdf|txt + {ID}.meta.yaml   # 원문 + provenance 사이드카 (+ README.md 규약)
    structured/{ID}.doc.json            # 라우터가 만든 doc.json
    excerpts/{ID}/{좌표}.txt            # 물질화된 발췌 (좌표의 / → _)
    manifest.json                       # 해소/미해소 + 차단 항목 — 빌드 게이트
  formats/   statute · decree · kofia_rule · transcript .format.json
  glossary/  statute · decree · kofia_rule · transcript .glossary.yaml
  src/  schema.py, when.py, basis.py, corpus_build.py, transcript.py,
        preprocess.py, lexicon.py, context_asm.py, judge.py,
        cross_signal.py, aggregate.py, report.py, harvest.py, cli.py
  output/ report.json, guidance.md, review_queue.jsonl, unclear_rate_history.json

tests/agent6/  test_corpus.py, test_when.py, fixtures/corpus/…
               (전사 픽스처 clean/violation/ambiguous·mutations 는 미작성 — §9)
```

route 자산(formats·glossary)은 이 폴더에 있지만 **연결은 `core/registry.yaml`이 한다**(§2.1).

CLI:
```bash
python -m agents.agent6.src.cli run --transcript t.json [--meta m.json] [--no-llm] \
    [--per-item] [--max-batch 6] [--basis-policy warn|block] -o agents/agent6/output/
python -m agents.agent6.src.cli harvest --queue review_queue.jsonl --resolved r.jsonl [--dry-run]
python -m agents.agent6.src.corpus_build [--allow-synthetic] [--strict]
```

## 11. 범위 밖 (후속)
- STT 자체(기존 시스템이 제공) — 단, STT 신뢰도 필드가 오면 confidence에 반영
- AI 스튜디오 프론트 연동(파일 업로드/다운로드 인터페이스만 맞춤)
- 실시간(통화 중) 판정, 소형 분류기 증류(큐 라벨 축적 후), 사내 제재사례 자동 수집
