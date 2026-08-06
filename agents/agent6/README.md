# agent6 — 녹취 체크리스트 점검 (불완전판매 Zero)

**입력은 STT 전사 하나, 출력은 30개 항목의 점검 리포트다.**

```bash
.venv/bin/python -m agents.agent6.src.cli run \
    --transcript 전사.json \
    --meta       상품고객메타.json \
    -o agents/agent6/output/
```

```
종료코드  0  완전판매요건충족
         1  보완필요 (FAIL·UNCLEAR·점검불가가 있다)
         2  입력이 잘못됐다
         3  점검 실패 — 판정자를 쓸 수 없어 점검하지 못한 항목이 있다
```

---

## 1. agent1 과 무엇이 다른가

| | agent1 | **agent6** |
|---|---|---|
| 대조 대상 | **값** (신탁보수 1% ↔ 1%) | **행위** (설명의무를 이행했는가) |
| 판정기 | 코드 (`==`, 정규화 비교) | **LLM** |
| LLM 없이 | 돈다 | **못 돈다** — 종료코드 3 |

"설명의무를 이행했는가"는 문자열 매칭으로 잴 수 없다. 같은 뜻을 백 가지로 말할 수 있고,
고객이 먼저 말한 것과 PB 가 고지한 것은 글자가 같아도 다른 사건이다. 그래서 판정기가
LLM 이다. 대신 **판정에 필요한 것을 전부 결정론으로 준비해서** 넣는다 — 그게 아래 §2 다.

> **왜 결정론 폴백을 없앴는가.** 예전에는 키가 없으면 항목마다 `lexicon: {hit, guard}` 로
> 전사에서 문자열을 찾아 판정하고 끝까지 돌았다. 적대적 검증에서 그 판정기가 사실상
> 아무것도 잡지 못한다는 것이 드러났고 — 표현을 조금만 바꾸면 전부 통과했다 — 통째로
> 없앴다. 못 하는 것을 한 척하는 쪽이 안 하는 것보다 나쁘다. 키 없이 결정론적으로
> 돌려야 하는 자리(테스트)는 녹화 재생(`--llm-mode replay`)을 쓴다.

---

## 2. 기제 — "미리 연결해 둔 근거"

핵심은 판정 프롬프트를 **상상 없이** 만드는 것이다.

```
① 항목 스펙       checklist/items/*.yaml — 30개. 운영정의 · 근거좌표 · few_shot
② 근거 연결       각 항목이 법령·준칙의 어느 조항을 근거로 보는지 (basis)
③ 코퍼스 빌드     원문 PDF → (라우터) → doc.json → 그 좌표만 발췌로 물질화
④ 전처리          전사를 펴고, meta 로 활성 항목 확정 (when DSL)
⑤ 컨텍스트 조립   항목마다: 운영정의 + 근거 발췌 + few_shot + 전사 전문
⑥ 판정            LLM 단독 + 자기일관성 k회 (기본 3)
⑦ 집계·리포트     파생 항목 · 라우팅 · 3종 산출물
```

### 근거 규정도 같은 파이프라인을 탄다

법령이라고 특별한 파서를 쓰지 않는다. `KSB.pdf`(금소법)·`KOFIA-R.pdf`(표준투자권유준칙)은
계약서와 **같은 `core.router`** 를 타고 doc.json 이 된다. `core/registry.yaml` 에
`금소법`·`금소법시행령`·`표준투자권유준칙` route 가 등록돼 있는 이유가 이것이다.

그 다음 `corpus_build` 가 체크리스트가 요구한 좌표만 골라 발췌 파일로 굳힌다.
**런타임은 코퍼스 전체를 만나지 않는다** — `basis.py` 라는 얇은 통로로 발췌만 읽는다.

```bash
.venv/bin/python -m agents.agent6.src.corpus_build --strict
```

`--strict` 는 미해소 basis 가 하나라도 있으면 실패로 끝낸다(CI 게이트용).

### 근거 연결은 화면에서 사람이 잇는다

`basis` 좌표를 손으로 적으면 두 가지가 자주 틀린다 — **없는 좌표**와 **여러 곳에 걸리는
좌표**다. 실측(2026-08-06)에서 30개 항목 중 6개가 후자로 활성화 차단 상태였다. 사람이
구조화된 문서를 보지 못한 채 좌표를 상상해서 적었기 때문이다.

그래서 `/agent6/` 화면이 구조화 산출물을 그대로 펴서 보여 주고, 고른 구역의 `section_id`
를 그대로 basis 에 적는다. **쓰기는 항목 YAML 이 정본**이다 — 별도 DB 에 두면 체크리스트
파일과 어긋나고, YAML 은 git 이 이력을 남긴다.

```bash
docker compose up -d    # → http://localhost:5566/agent6/
```

선을 바꾼 뒤에는 **코퍼스를 다시 빌드해야 한다.** 발췌는 basis 를 보고 물질화되므로 선을
이었다고 발췌가 저절로 생기지 않는다. API 응답의 `needs_rebuild` 가 그 사실을 알린다.

---

## 3. 항목 스펙 — 데이터가 지식을 갖는다

코드는 항목을 모른다. 30개 항목의 지식은 전부 `checklist/items/*.yaml` 에 있다.

```yaml
id: A-01
name: 판매자 소속·성명 고지
type: 존재형
when: always                    # 조건부 활성화 DSL (§4)
basis:                          # 근거 좌표 — 여기가 발췌로 물질화된다
  - { doc: KOFIA-R, term: 성명, note: "준칙 14. 설명의무 — …" }
operational_definition: >        # 판정자가 읽는 규칙. 이게 가장 중요하다
  PB가 자신의 소속과 성명을 밝혔는지 판정한다. 둘 다 나와야 충족이며 …
  근거는 **PB의 발화만** 인정한다 — 고객이 "김 팀장님이시죠?"라고 부른 것은 아니다.
  판정은 낱말이 아니라 뜻으로 한다. 아래 예시는 견본일 뿐이다.
few_shot:                        # 경계 사례. 특히 UNCLEAR 예시가 값어치가 크다
  - { utterance: "…", verdict: PASS,    reason: "소속·성명 모두 고지" }
  - { utterance: "…", verdict: UNCLEAR, reason: "성만 밝히고 소속이 없다" }
judgment_hints:
  fail_route: PB보완              # FAIL 이면 PB가 다시 말하면 된다
  unclear_route: 준법감시큐        # UNCLEAR 는 사람이 본다
```

항목을 고치는 것은 **YAML 을 고치는 일**이지 파이썬을 고치는 일이 아니다.
`lexicon` 을 없앤 뒤로 판정자가 읽는 것은 **운영정의 · 근거발췌 · few_shot 셋뿐**이라,
운영정의가 짧으면 경고가 뜬다.

---

## 4. `when` — 조건부 활성화와 세 값 논리

항목마다 언제 점검할지 다르다(고령자 보호는 65세 이상에만). 자연어를 그대로 평가할 수
없어 아주 좁은 문법을 정의하고 파서를 손으로 짰다. **`eval()` 은 쓰지 않는다** — 항목
스펙은 데이터지 코드이고, 데이터가 임의 코드로 실행되면 결정론이 깨진다.

```
always
customer_age >= 65
product_type in [ELS, ELB, DLS, DLB]
is_high_difficulty == true or customer_age >= 65
```

**결과는 세 값이다 — ACTIVE / INACTIVE / UNKNOWN.**

메타는 선택 입력이다. 전사만 올라오고 상품·고객 메타가 비어 있는 호출이 실제로 있다.
이때 `customer_age >= 65` 를 조용히 거짓으로 접으면 C-18(숙려기간)·E-27(고령자 보호)이
통째로 사라지고, **점검하지 않은 항목이 점검한 것처럼 보인다.** 그래서 UNKNOWN 은

- 보수적으로 **활성**시키고,
- "메타 부족: customer_age" 라는 이유를 리포트에 남긴다.

거짓 FAIL 비용(PB 재설명 몇 분) ≪ 거짓 PASS 비용(불완전판매 통과). 임계는 대칭이 아니다.

---

## 5. 산출물 셋 — 독자가 다르다

| 파일 | 독자 | 내용 |
|---|---|---|
| `report.json` | 시스템·감사 | 활성 항목이 **정확히 한 행씩**. 누락·점검불가도 행으로 |
| `guidance.md` | PB | "지금 다시 말해야 하는 것"만. 그 외는 싣지 않는다 |
| `review_queue.jsonl` | 준법감시 | 사람이 해소하고, 해소 결과가 few_shot 으로 돌아온다 |

`guidance.md` 에 준법감시큐 항목의 "권장 문구"를 적지 않는다. UNCLEAR 는 사람이 판단할
일인데 권장 문구를 주면 PB 가 그것을 읽는 것으로 해소해 버린다.

해소 결과를 되먹이는 것이 **수렴 루프**다:

```bash
.venv/bin/python -m agents.agent6.src.cli harvest \
    --queue out/review_queue.jsonl --resolved 해소결과.jsonl [--dry-run]
```

같은 경계 사례가 두 번 큐에 오지 않게 few_shot 이 자란다.

---

## 6. LLM 모드 — live / record / replay

```bash
--llm-mode live      # 기본. 실제 호출
--llm-mode record    # 호출하고 응답을 파일로 남긴다
--llm-mode replay    # 파일만 읽는다. 키도 네트워크도 안 쓴다 (테스트)
```

녹화 키는 `sha256(kind + system + user + 응답스키마)` 앞 16자다. **프롬프트가 바뀌면
키도 바뀐다** — 낡은 녹화를 새 프롬프트에 재생하지 않기 위한 것이다. 그래서 항목 스펙이나
근거 발췌를 고치면 `tests/agent6/fixtures/llm/` 의 녹화가 무효가 되고 재녹화가 필요하다
(`tests/agent6/record_fixtures.py`).

이 성질 때문에 코퍼스를 다시 빌드한 직후 테스트가 CacheMiss 로 무너지는 일이 있다.
그건 결함이 아니라 설계된 알림이다.

---

## 7. 폴더

```
checklist/items/*.yaml       항목 스펙 30개 (A-01 … F-30)  ← 지식은 전부 여기
corpus/raw/                  법령·준칙 원문 PDF + meta.yaml
corpus/structured/           원문을 라우터로 구조화한 doc.json
corpus/excerpts/             체크리스트가 요구한 좌표만 물질화한 발췌  ← 런타임이 읽는 것
corpus/manifest.json         무엇이 해소됐고 무엇이 비었는가
formats/ · glossary/         법령·시행령·준칙·전사 route 자산
src/                         조립 코드만
output/                      생성물 (gitignore)
```

| 모듈 | 역할 |
|---|---|
| `corpus_build.py` | 원문 → 라우터 → doc.json → 발췌 물질화 → manifest |
| `basis.py` | 런타임이 코퍼스를 만나는 **유일한** 통로 |
| `preprocess.py` | 전사를 펴고 활성 항목 확정 |
| `when.py` | 조건부 활성화 DSL (세 값 논리) |
| `context_asm.py` | "미리 연결"을 실제 프롬프트로 |
| `judge.py` | LLM 단독 판정 + 자기일관성 |
| `llm_cache.py` | 녹화/재생 |
| `aggregate.py` | 판정 → 리포트 행 → 하나의 상태 |
| `report.py` | report.json · guidance.md · review_queue.jsonl |
| `harvest.py` | 큐 해소 결과를 few_shot 으로 되돌린다 |
| `transcript.py` | 발화턴 계열 파서 (registry `parsers.transcript`) |
| `schema.py` | 항목 스펙·리포트 스키마 — 데이터 계약 |

규격의 정본은 [../../docs/AGENT6_SPEC.md](../../docs/AGENT6_SPEC.md),
플랫폼 전체는 [../../docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md).
