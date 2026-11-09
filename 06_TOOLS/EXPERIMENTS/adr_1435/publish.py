"""Write ADR-1435 documents and manifest results from the saved run; no model call (pattern of ADR-1433 publish.py)."""
from common import *
import gzip, tarfile, shutil

result, calls, generations = read(RUN / 'result.json'), read(RUN / 'calls.json'), read(RUN / 'generations.json')
criteria, case, candidate = read(DES / 'criteria.json'), read(DES / 'case.json'), read(DES / 'candidate.json')
source, issues = read(DES / 'comparison-source.json'), read(ART / 'preparation-issues.json')
body = json.load(gzip.open(RUN / 'response.json.gz', 'rt'))['body']
rel = lambda p: str(Path(p).relative_to(ROOT))
items = body['comparison_items']['items']
reviewed = sum(i['content_status'] != 'UNKNOWN' for i in items)
tokens_in = sum((c.get('usage') or {}).get('prompt_tokens', 0) for c in calls)
tokens_out = sum((c.get('usage') or {}).get('completion_tokens', 0) for c in calls)
cost = round(sum((c.get('usage') or {}).get('cost', 0) or 0 for c in calls), 8)
frozen_changed = [n for n, h in read(DES / 'freeze.json')['files'].items() if sha(ROOT / n) != h]
external = body['rag_results']['external']; returned = external.get('investigation_return') or {}
acquired = (returned.get('acquisition') or {}).get('documents') or {}
named_first = bool(acquired) and all(d.get('delivered') and d.get('read_complete') for d in acquired.values())
external_calls = [c for c in calls if c['stage'].startswith('source-law')][1:]  # the first source-law call is the internal child
exhausted = any('REPAIR_EXHAUSTED' in str(u) for u in (body.get('unresolved') or []))
pair_notes = [n for row in body['comparison_table']['rows'] for n in (row.get('unresolved') or [])]
unresolved = body.get('unresolved') or []
stage_note = [u for u in unresolved if '외규 조사 전' in str(u)]
unlabelled_missing = [u for u in unresolved if '미확보' in str(u) and '외규 조사 전' not in str(u)]
parent = criteria['parent_observation']
required = {
    'http200_no_supervisor_error': result['http_status'] == 200 and result['status'] in ('completed', 'partial') and not result['error'],
    'both_sides_originals': all(s['export_mode'] == 'SOURCE_HANDOFF' and s['evidence'] > 0 for s in result['sides'].values()),
    'item_review_complete': not exhausted and not result['rejected_generations'] and bool(items) and reviewed == len(items),
    'named_rule_acquired_first': named_first,
    'accounting': result['unknown'] == 0 and result['physical_calls'] <= criteria['limits']['physical_total']
                  and result['duplicate']['extra_physical_calls'] == 0 and result['duplicate']['same_answer'] and not frozen_changed}
planted = [
    {'point': criteria['planted_points'][0], 'in_report': '있음', 'note': '항목 concept-2/조건: 내규 100분의 110 이상, 외규 100분의 100 이상. 판정 표기는 "상충"'},
    {'point': criteria['planted_points'][1], 'in_report': '있음', 'note': '항목 concept-3/의무: 내규는 리스크관리위원회에 지체 없이(내부 보고), 외규는 5영업일 이내 감독원장에게 사실·개선계획(외부 보고)'},
    {'point': criteria['planted_points'][2], 'in_report': '있음', 'note': '항목 concept-4/의무: 분기와 반기, 대표이사와 이사회. 판정 표기는 "상충"'}]
findings = [
    '외규 이름 먼저 읽기가 발동했다: 외규 조사의 첫 모델 호출 입력에 「모의 금융투자업 감독규정」 제12~16조 원문 5개가 이미 들어 있었고, 모델은 "모두 확보, 추가 조사 대상 없음"으로 한 번에 끝냈다. '
    '외규 조사 모델 호출 %d회(ADR-1433은 5회, ADR-1429는 6회), 외규 조사 상태 %s(ADR-1433은 partial/NO_PROGRESS). 관계없는 「모의 전자금융 감독규정」은 입력에 없었다.' % (len(external_calls), external['status']),
    '항목 검토 %d/%d건이 첫 응답에 통과했다. 보완 호출 0, 거절 0. 이번에는 모델이 개념을 4개로 나눴다(ADR-1433은 개념 2개·항목 5개).' % (reviewed, len(items)),
    '비교 %d쌍이 모두 실행됐고 쌍별 추가 확인 사항은 %d건이다. 다른 쌍의 원문이 없다는 문구는 나오지 않았다.' % (len(body['comparison_table']['rows']), len(pair_notes)),
    '개념 단계 메모는 "내규 개념 정리 단계 메모(외규 조사 전)"로 시점 표시가 붙어 남았다(사전 규칙상 허용). 표시 없는 "외규 미확보" 문구는 %d건이다. 다만 외규 원문을 모두 비교한 보고서의 추가 확인 사항에 이 메모가 그대로 남아 있다.' % len(unlabelled_missing),
    '새로 남은 것: concept-2 항목 검토에서 외규 제13조(유동성비율의 산정)를 "사용"으로 선언하고 어느 항목에도 인용하지 않아, 서버가 "반영 미완료"로 보존했다. '
    '보고서에는 어느 원문·어느 항목인지 없이 "확보 원문의 항목 반영 추가 확인 필요 — … 반영 추가 확인 필요로 보존했습니다."로 표시된다. 추가 확인 사항 2건이 남았고 최종 상태는 partial이다.',
    '내규가 외규보다 엄격한 두 차이(110 대 100, 분기 대 반기)를 모두 "상충"으로 표기했다. 엄격한 내규를 상충으로 부를지는 표기 기준 문제이며 채점하지 않았다.',
    '확정 HTTP 429는 0회였다. 12회 모두 Parasail로 처리됐다.']
summary = {'schema_version': 'adr-1435-summary-v1', 'criteria_sha256': sha(DES / 'criteria.json'), 'required': required, 'success_criteria_met': all(required.values()),
           'http_status': result['http_status'], 'workflow_status': result['status'], 'request_seconds': result['request_seconds'],
           'physical_calls': result['physical_calls'], 'known_429': sum(1 for c in calls if c.get('http_status') == 429), 'unknown': result['unknown'],
           'input_tokens': tokens_in, 'output_tokens': tokens_out, 'reported_cost_usd': cost, 'stages': result['stages'],
           'items_reviewed': reviewed, 'items_total': len(items), 'parent': parent,
           'external_child': {'status': external['status'], 'stop_reason': returned.get('stop_reason'), 'named_rule_read_first': named_first,
                              'model_calls': len(external_calls), 'acquired_documents': sorted(acquired)},
           'pair_notes': pair_notes, 'unresolved': unresolved, 'stage_note_labelled': bool(stage_note), 'unlabelled_missing_notes': unlabelled_missing,
           'planted_points_operator_reading': planted, 'duplicate': result['duplicate'], 'frozen_files_changed': frozen_changed, 'findings': findings}
put(RUN / 'summary.json', summary)
if (RUN / 'runtime').exists():
    files = sorted(p for p in (RUN / 'runtime').rglob('*') if p.is_file())
    members = {str(p.relative_to(RUN)): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in files}
    with tarfile.open(RUN / 'runtime.tar.gz', 'w:gz') as tar:
        for p in files:
            tar.add(p, arcname=str(p.relative_to(RUN)))
    with tarfile.open(RUN / 'runtime.tar.gz') as tar:
        for name, meta in members.items():
            data = tar.extractfile(name).read()
            assert hashlib.sha256(data).hexdigest() == meta['sha256'] and len(data) == meta['bytes'], name
    put(RUN / 'runtime-archive-receipt.json', {'archive': 'runtime.tar.gz', 'archive_sha256': sha(RUN / 'runtime.tar.gz'), 'members': len(members),
                                                'restore': 'tar -xzf runtime.tar.gz -C <run-001>', 'verified_every_member_before_removal': True, 'files': members})
    shutil.rmtree(RUN / 'runtime')

ok = lambda flag: '충족' if flag else '미충족'
met = sum(required.values())
call_rows = '\n'.join('| %d | %s | %s | %s | %s | %.1f | %s | %s | `raw/call-%03d/` |' % (
    c['number'], c['stage'], c.get('http_status'), c.get('actual_provider') or '-', c.get('finish_reason') or '-', c['seconds'],
    (c.get('usage') or {}).get('prompt_tokens'), (c.get('usage') or {}).get('completion_tokens'), c['number']) for c in calls)
gen_rows = '\n'.join('| %d | %s | %s | %.1f |' % (g['number'], g['stage'], '수락' if g['status'] == 'accepted' else '거절', g['seconds']) for g in generations)
item_rows = '\n'.join('| %s | %s | %s | %s (%d) | %s (%d) | %s |' % (i['issue_id'], i['field'], i['content_status'], i['internal']['status'], len(i['internal']['citations']),
                                                                   i['external']['status'], len(i['external']['citations']), (i.get('difference') or '').replace('|', '/')[:70]) for i in items)
finding_lines = '\n'.join('- ' + f for f in findings)
example = json.load(gzip.open(RUN / 'raw/call-002/request.json.gz', 'rt'))
required_lines = '\n'.join('- ' + x for x in criteria['required'])

q = ADR / '실험' / ('질문-001-%s.md' % CASE)
q.write_text(f'''# 질문 001 — {CASE}

## 1. 실행 메타

- ADR: `ADR-1435`
- experiment: `ADR-1435-experiment-v1`
- case ID: `{CASE}`
- run ID: `run-001`
- 실행 시각: 2026-11-06 저녁(KST), 요청 {result['request_seconds']}초
- 원본 상태: `exact` — 물리 호출별 요청·응답 원문은 `artifacts/run-001/raw/call-NNN/`(gzip, 인증 헤더 제외), 단계별 입력·검증된 출력은 `canonical/`
- 제품·중간 호출 모델: `qwen/qwen3.8-27b` (Parasail FP8 우선, 확정 429에만 Near AI FP8, reasoning none, 출력 상한 없음)
- 오프라인 평가 모델: 없음 — 채점 호출 0회
- 실행 arm: `namedscope` (`baseline`은 ADR-1433 itemsnamed arm의 실제 결과를 참조, 재실행 없음)

## 2. 사용자 질문 원문

```text
{case['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

합성 문서에 심어 둔 차이 3가지(ADR-1429·1433과 동일). 제품 입력에는 넣지 않았고 실행자가 보고서를 읽어 확인했다.

```text
''' + '\n'.join(criteria['planted_points']) + f'''
```

## 4. 제품 입력을 구성한 원값

### 회수 전 전체·후보·제시 규모

```json
{json.dumps({'corpus': source['source_manifest']['counts'], 'retrieval': '제품 하위 조사 그대로. 회수율 미측정', 'internal_evidence': result['sides']['internal']['evidence'], 'external_evidence': result['sides']['external']['evidence']}, ensure_ascii=False)}
```

### 회수 좌표·조문·정의·Wiki·관계 — 전체

ADR-1429의 합성 문서 3개(내규 1, 외규 2, 조문 12개)를 해시로 확인해 그대로 썼다.

```json
{json.dumps({'generation_id': source['source_manifest']['generation_id'], 'store_sha256': source['source_manifest']['store_sha256'], 'reused_from': 'ADR-1429', 'ontology': 'off (profile default)'}, ensure_ascii=False)}
```

### 회수·탈락 단계 원장 — run·arm별

회수 단계 원장은 해당 없음이다(stage_ledger mode=not_applicable).

| run | arm | stage | kind | before | +added | -discarded | after | gold before | gold + | gold - | gold after/total | recall | 대표 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| run-001 | namedscope | 해당 없음 | 해당 없음 | - | - | - | - | - | - | - | - | - | 원장 미작성 |

```json
{json.dumps({'stage_ledger_artifact': None, 'discarded_gold_and_reasons': '해당 없음', 'gold_visible_to_product': False}, ensure_ascii=False)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

### run-001 / baseline / system

```text
이 ADR에서 미실행. ADR-1433 run-001 참조.
```

### run-001 / namedscope / system

호출마다 system이 다르다. 전체 {len(calls)}건의 원문은 `artifacts/run-001/raw/call-NNN/request.json.gz`에 있다. 아래는 둘째 호출(내규 조사)의 system 전문이다.

```text
{example['messages'][0]['content']}
```

### run-001 / namedscope / user

```text
{example['messages'][1]['content']}
```

### run-001 / namedscope / schema·tool

단계별 스키마는 `artifacts/run-001/canonical/NNN.json.gz`의 `schema`에 있다.

```json
{json.dumps({'stages': result['stages']}, ensure_ascii=False)}
```

### run-001 / namedscope / provider 원응답·structured output·usage·지연

| 호출 | 단계 | HTTP | 공급자 | 종료 | 초 | 입력 토큰 | 출력 토큰 | 원문 위치 |
|---:|---|---:|---|---|---:|---:|---:|---|
{call_rows}

합계: 물리 호출 {len(calls)}회(확정 429 {summary['known_429']}회), 입력 {tokens_in} / 출력 {tokens_out} 토큰, 보고 비용 {cost}달러, 결과 불명 0건.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

보완 호출은 없었다. 단계별 수락 기록:

| 순번 | 단계 | 결과 | 초 |
|---:|---|---|---:|
{gen_rows}

```json
{json.dumps({'corrective_calls': 0, 'rejected_generations': result['rejected_generations']}, ensure_ascii=False)}
```

## 7. 채점 호출과 반복 판정

### judge system/user — 기준답변 포함

```json
{json.dumps({'judge_calls': 0, 'reason': '채점 호출 없음. 심어 둔 차이는 실행자가 보고서를 읽어 확인'}, ensure_ascii=False)}
```

### judge 원응답과 최종 다수결

```json
{json.dumps({'judge_calls': 0, 'operator_reading': planted}, ensure_ascii=False)}
```

## 8. 사례 최종 판정

| run | arm | 정답 | 핵심 근거 | 실패 유형 |
|---|---|---:|---|---|
| run-001 | baseline | 참조 | ADR-1433: 항목 5/5, 외규 조사 5회·NO_PROGRESS, 외규 이름 미도달 | other: named_rule_not_reached, stale_notes |
| run-001 | namedscope | 기술 기준 {met}/{len(required)} {ok(summary['success_criteria_met'])} | HTTP {result['http_status']}/{result['status']}, 항목 {reviewed}/{len(items)}건, 외규 조사 {len(external_calls)}회·이름으로 먼저 확보 | other: used_original_not_cited |

- 사전 지정 비교쌍의 신규 정답·회귀: 외규 이름 먼저 읽기 미발동 → 발동, 외규 조사 호출 5 → {len(external_calls)}, 항목 검토 전부 통과 유지(같은 질문, 각 1회).
- 공통 실패 유형: `other` — 사용 선언한 외규 원문의 항목 미인용.
- 사람이 확인한 직접 원인: concept-2 항목 검토가 외규 제13조를 "유지 기준 비교의 전제"로 사용 선언했지만 어느 항목에도 인용하지 않았다.
- 다음 분기에서 검증할 가설: 사용 선언한 원문은 항목 인용을 함께 내게 하거나, 전제 확인용 원문은 "참고"로 따로 선언하게 하면 반영 미완료가 남지 않는다.
''', 'utf-8')

index = (ADR / '실험/README.md').read_text('utf-8')
def swap(old, new, text):
    assert text.count(old) == 1, old
    return text.replace(old, new)
index = swap('- 이 분기의 변경 가설: TODO', '- 이 분기의 변경 가설: ' + criteria['question'], index)
index = swap('| `baseline` | baseline | ADR-1433-experiment-v1/itemsnamed | TODO | TODO |', '| `baseline` | baseline | ADR-1433-experiment-v1/itemsnamed | ADR-1433 itemsnamed arm(참조, 재실행 없음) | 같은 합성 문서·질문 |', index)
index = swap('| `namedscope` | candidate | baseline | TODO | TODO |', '| `namedscope` | candidate | baseline | ADR-1433 후보 + 외규 이름을 인용한 내규 문서의 읽은 원문 전체에서 찾기·개념 단계 메모 시점 표시·비교를 자기 쌍으로 한정(제품 8개 파일) | 선택 프로필, 합성 문서, Qwen3.8 |', index)
index = swap('| 001 | `%s` | `run-001` | TODO | TODO | TODO |' % CASE,
             '| 001 | `%s` | `run-001` | namedscope: HTTP 200·%s, 기술 기준 %d/%d, 항목 %d/%d | 외규 이름 먼저 읽기 미발동→발동, 외규 조사 5→%d회 | other: 사용 선언 원문 미인용 |' % (CASE, result['status'], met, len(required), reviewed, len(items), len(external_calls)), index)
index = swap('- run 상태: `run-001 / planned`', '- run 상태: `run-001 / complete` (요청 1건)', index)
index = swap('- arm별 정답: TODO', '- arm별 정답: namedscope 기술 기준 %d/%d %s, 항목 검토 %d/%d건' % (met, len(required), ok(summary['success_criteria_met']), reviewed, len(items)), index)
index = swap('- 사전 지정 비교쌍별 신규 정답 / 회귀: TODO', '- 사전 지정 비교쌍별 신규 정답 / 회귀: 외규 이름 먼저 읽기 미발동→발동, 항목 검토 전부 통과 유지, 회귀 없음', index)
index = swap('- judge 불일치: TODO', '- judge 불일치: 채점 호출 없음', index)
index = swap('| `run-001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |', '| `run-001` | namedscope | 해당 없음 | 해당 없음 | - | - | - | - | 원장 미작성 |', index)
(ADR / '실험/README.md').write_text(index, 'utf-8')

readme = (ADR / 'README.md').read_text('utf-8')
head, _ = readme.split('## 2. 문제와 변경 전 구조', 1)
head = swap('TODO: 채택·기각·보류와 운영 배선 변경 여부를 먼저 적는다.',
            f"보류(Proposed). ADR-1429·1433과 같은 합성 대사 1건을 2차 수정 후보로 실행했다. 사전 기술 기준 {met}/{len(required)}개 {ok(summary['success_criteria_met'])}. "
            f"내규 제1조에 적힌 외규를 조사 시작 때 이름으로 먼저 읽었고(외규 조사 모델 호출 5 → {len(external_calls)}회), 항목 {reviewed}/{len(items)}건이 첫 응답에 검토됐으며, 비교 {len(body['comparison_table']['rows'])}쌍 모두 다른 쌍의 미확보를 적지 않았다. "
            "개념 단계 메모는 시점 표시와 함께 남았다. 사용 선언한 외규 원문 하나가 항목에 인용되지 않아 상태는 partial이다. 운영 배선 변경 없음.", head)
prep = '\n'.join('- %s: %s' % (i['step'], i['issue']) for i in issues) or '- 없음'
text = head + f'''## 2. 문제와 변경 전 구조

ADR-1433에서 항목 검토는 5/5로 통과했지만 두 가지가 남았다. (1) 외규 이름이 개념이 인용하지 않은 내규 제1조(목적)에 있어서 이름으로 먼저 읽기가 발동하지 않았고, 외규 조사가 검색·읽기 5단계 뒤 NO_PROGRESS로 끝났다. (2) 개념 단계의 "외규 원문 미확보"와 첫째 쌍 비교의 "위기상황분석 외규 원문 없음"이 최종 보고서에 남았다. 이번 후보는 외규 이름을 개념이 인용한 내규 문서의 읽은 원문 전체에서 찾고, 개념 단계 메모에 시점을 표시하며, 비교 호출이 자기 쌍만 다루도록 지시했다.

## 3. 가설과 사전 판정 기준

### 가설

{criteria['question']}. 예상: 외규 문서를 조사 시작 때 바로 읽어 외규 조사 호출이 줄고, 범위 밖 미확보 문구가 표시 없이 남지 않는다.

### 성공 기준

{required_lines}
- 한도: 요청 1건, 물리 호출 {criteria['limits']['physical_total']}회, 호출당 180초.
- 개념 단계 메모는 시점 표시와 함께라면 남아도 된다. 비교 호출은 다른 쌍의 원문 미확보를 적지 않는 것을 관찰한다(필수 기준 아님).

### 반증 기준

- {criteria['stop']}
- HTTP 500 또는 감독 승인 오류, 항목 검토의 보완 소진, 외규 이름 먼저 읽기 미발동, 제품이 보고한 원문·권한·해시 불일치.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | ADR-1433 itemsnamed arm(MAIN165 + 제품 7개 파일), 재실행 없이 실제 결과 참조 | 같은 합성 문서·질문 | baseline |
| namedscope | MAIN165 + 제품 8개 파일, 워크플로우 1.20.9 | 선택 프로필 그대로(감독 enforce), 합성 문서, Qwen3.8 정책 | candidate |

- 합성 문서는 ADR-1429의 것을 해시로 확인해 그대로 썼다. 질문도 같다. 이전 결과를 본 뒤 설계한 후속 실험이다.
- 동결 시점의 선택 MAIN은 166이었고, 대사 경로 파일은 MAIN165와 같다(동결 스크립트가 확인).
- 시작 조건: 다른 실험의 모델 실행기가 없고 RAM 여유 5GiB 이상일 때 시작한다. RAM 4.86GiB로 30초 기다린 뒤 시작했다.

### 다른 ADR과의 관계

- 관련 ADR: 없음

- experiment 계보와 직접 부모 arm: [실험 manifest](실험/manifest.json)

## 5. 데이터·모델·재현성

- 데이터셋과 버전: ADR-1429의 합성 문서 3개(조문 12개), 세대 `{source['source_manifest']['generation_id']}`. 실제 내규·외규 미사용.
- frozen source와 SHA-256: `{rel(DES / 'comparison-source.json')}` `{sha(DES / 'comparison-source.json')}`; 동결 목록 `{rel(DES / 'freeze.json')}`.
- 제품/중간/채점 모델: `qwen/qwen3.8-27b` (Parasail FP8 우선, 확정 429에 Near AI FP8). 채점 호출 없음.
- 반복 수와 다수결: 요청 1건, 반복 없음.
- 법령·기준답변 버전 점검: 해당 없음(합성 문서).

## 6. 결과

| arm | 정답/전체 | 정확도 | baseline 대비 | 입력 토큰 | p50/p95 |
|---|---:|---:|---:|---:|---:|
| baseline (ADR-1433) | 항목 {parent['items_reviewed']}/{parent['items_total']}, 외규 이름 미도달 | - | - | 121147 | 호출 {parent['physical_calls']}건, 요청 {parent['request_seconds']}초 |
| namedscope | 항목 {reviewed}/{len(items)}, 기술 기준 {met}/{len(required)} | - | 외규 이름 먼저 읽기 발동, 외규 조사 5→{len(external_calls)}회 | {tokens_in} | 호출 {len(calls)}건, 요청 {result['request_seconds']}초 |

- HTTP {result['http_status']}, 상태 `{result['status']}`, 물리 호출 {len(calls)}회(확정 429 {summary['known_429']}회), 결과 불명 0건, 보고 비용 {cost}달러.
- 같은 요청 재전송: 같은 답, 추가 호출 0. 동결 파일 변경 {len(frozen_changed)}건.
- 입력 토큰은 121147 → {tokens_in}으로 줄었다(외규 조사 호출이 줄어든 몫이 크다). 개념 수가 2 → 4로 달라져 항목·비교 호출은 각각 2 → 4회가 됐으므로 전체 호출·시간을 개선율로 쓰지 않는다.

항목 대조표(제품 출력):

| 쟁점 | 항목 | 내용 상태 | 내규(인용 수) | 외규(인용 수) | 차이 |
|---|---|---|---|---|---|
{item_rows}

| paired outcome | 건수 | 비율 |
|---|---:|---:|
| 비교 arm만 정답 | 외규 이름 먼저 읽기 1건 | 같은 질문 각 1회 |
| 기준 arm만 정답(회귀) | 0 | - |
| 둘 다 정답 | 항목 검토 전부 통과 | - |
| 둘 다 오답 | 추가 확인 사항 잔존(상태 partial) | - |

심어 둔 차이(실행자 읽기, 채점 아님):

| 차이 | 보고서 | 메모 |
|---|---|---|
''' + '\n'.join('| %s | %s | %s |' % (p['point'], p['in_report'], p['note']) for p in planted) + f'''

관찰:

{finding_lines}

## 7. 사례별 오류 분석

| 실패 유형 | 건수/분모 | 대표 질문 | 해석 |
|---|---:|---|---|
| other: 사용 선언 원문 미인용 | 1 / 1 요청 | {CASE} | concept-2 검토가 외규 제13조를 전제 확인용으로 "사용" 선언하고 항목 인용을 내지 않았다. 서버는 반영 미완료로 보존했고, 보고서 문구는 어느 원문인지 알려 주지 않는다. |
| other: 단계 메모 잔존 | 1 / 1 요청 | {CASE} | 시점 표시는 붙었지만, 외규를 모두 비교한 보고서의 추가 확인 사항에 개념 단계 메모가 남는다. |

질문별 실제 입출력은 [실험 인덱스](실험/README.md)에 연결한다.

## 8. 비용·지연·회수 규모

| 항목 | 값 | 측정 단위·분모 |
|---|---:|---|
| 전체 corpus | 3문서 12조문 | 합성 |
| 필터 전/후 후보 | 측정 안 함 | 제품 하위 조사 그대로 |
| LLM 제시 수 | 내규 {result['sides']['internal']['evidence']}, 외규 {result['sides']['external']['evidence']} | 확보 원문 조문 수 |
| golden recall | 해당 없음 | 기준 좌표 없음 |
| 제시 비율 | 10 / 12 | 확보 조문 / 전체 조문 |
| LLM 호출·토큰·지연 | {len(calls)}회 · 입력 {tokens_in} · 출력 {tokens_out} | 요청 {result['request_seconds']}초, {cost}달러 |

회수 점수는 측정하지 않았다. 단계 원장은 해당 없음(`stage_ledger.mode=not_applicable`).

### 단계별 회수·탈락 원장

| run | arm | stage | kind | 후보 before→after | added / discarded | gold before→after | gold gain / loss | recall | 주요 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| run-001 | namedscope | 해당 없음 | 해당 없음 | - | - | - | - | - | 원장 미작성 |

## 9. 해석

- 사실: 이름을 찾는 범위를 인용한 내규 문서의 읽은 원문 전체로 넓히자, 개념이 인용하지 않은 제1조의 외규 이름으로 그 문서를 먼저 읽었다. 외규 조사는 모델 1회로 끝났고 상태도 completed였다.
- 사실: 비교 호출 4건 모두 자기 쌍 밖의 미확보를 적지 않았다.
- 사실: 개념 단계 메모는 지시대로 시점 표시가 붙었지만 보고서에서 빠지지는 않았다.
- 사실: 새로 사용 선언 원문의 항목 미인용 1건이 생겨 상태가 partial로 남았다.
- 추론: 남은 partial은 외규 확보 문제가 아니라 항목 검토의 "사용" 선언 규칙과 보고서 표시 문제다(미검증).

## 10. 한계와 일반화 가능 범위

- 요청 1건, 합성 문서, 인샘플이며 ADR-1429·1433 결과를 본 뒤 같은 질문으로 설계했다.
- 외규 이름이 내규 원문에 그대로 적힌 경우만 확인했다. 약칭·조문 번호만 적힌 경우는 확인하지 않았다.
- 실제 내규·외규, 반복 안정성, 법적 품질, GENOS 내부 모델은 확인하지 않았다.
- 심어 둔 차이의 확인은 실행자가 읽은 것이며 채점이 아니다.

## 11. 운영 결정·롤백 조건

- 메인 배선: 변경 없음. 후보는 MAIN165 + 제품 8개 파일이다(MAIN166에도 패치 그대로 적용됨).
- MAIN 반영은 이 ADR 범위 밖이며 사용자 지시 후 인계 문서 4.3의 순서로 한다.
- 후속 수정 대상: 사용 선언 원문의 항목 인용 규칙, 반영 미완료 문구에 원문·항목 표시, 외규를 모두 비교한 뒤 개념 단계 메모 정리.

## 12. 재현 명령

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1435/setup.py
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1435/live.py --scripted
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1435/live.py
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1435/publish.py
```

준비 과정의 실패(모델 호출 0건):

{prep}

- 원시 산출물: [artifacts/manifest.json](artifacts/manifest.json)
- 질문 파일 hash: [실험/manifest.json](실험/manifest.json)
'''
(ADR / 'README.md').write_text(text, 'utf-8')

manifest = read(ADR / '실험/manifest.json')
manifest['results'] = {
    'status': 'complete',
    'by_arm': {'baseline': {'status': 'reference', 'correct': parent['items_reviewed'], 'total': parent['items_total'], 'accuracy': None, 'decision_eligible': False,
                            'scope': 'ADR-1433 run-001 items reviewed / requested; named rule not read first; not re-executed'},
               'namedscope': {'status': 'complete', 'correct': reviewed, 'total': len(items), 'accuracy': None, 'decision_eligible': False,
                              'scope': 'items reviewed / requested in one request; frozen technical criteria met=%s; named rule read first=%s; workflow status %s' % (
                                  summary['success_criteria_met'], named_first, result['status']),
                              'http_status': result['http_status'], 'workflow_status': result['status']}},
    'comparisons': [{'kind': 'named_rule_read_first', 'baseline': False, 'candidate': named_first, 'note': 'same question, one request each, in-sample'},
                    {'kind': 'external_child_model_calls', 'baseline': 5, 'candidate': len(external_calls), 'note': 'concept count differs (2 vs 4)'}],
    'judge_disagreements': 0,
    'usage': {'physical_requests': len(calls), 'known_http_429': summary['known_429'], 'offline_evaluator_requests': 0, 'input_tokens': tokens_in, 'output_tokens': tokens_out,
              'reported_cost_usd': cost, 'unknown': 0},
    'latency': {'request_seconds': result['request_seconds'], 'per_call_seconds': [c['seconds'] for c in calls]},
    'error_taxonomy': [{'type': 'other: used_original_not_cited', 'case_id': CASE}, {'type': 'other: stage_note_kept_with_label', 'case_id': CASE}],
    'frozen_criteria': {'required': required, 'success_criteria_met': summary['success_criteria_met']}}
manifest['runs'][0].update(status='complete', sha256=sha(RUN / 'result.json'), success_criteria_met=summary['success_criteria_met'])
manifest['questions'][0]['sha256'] = sha(q)
(ADR / '실험/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')
existing = read(ART / 'manifest.json')
described = {'design': '호출 전 동결한 후보·합성 문서 참조·기준', 'preflight': '호출 전 점검 기록', 'run-001': '실제 실행 기록', 'transport': '고정한 전송 모듈'}
files = []
for path in sorted(p for p in ART.rglob('*') if p.is_file() and p != ART / 'manifest.json'):
    top = path.relative_to(ART).parts[0]
    files.append({'path': rel(path), 'sha256': sha(path), 'bytes': path.stat().st_size, 'description': described.get(top, '준비·실행 기록'),
                  'contains_raw_prompts_and_outputs': 'raw/' in rel(path) or 'canonical/' in rel(path) or 'experiment-client/' in rel(path)})
existing['files'] = files
(ART / 'manifest.json').write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print('published', len(files), 'artifact files; criteria', required, '; items', reviewed, '/', len(items), '; external calls', len(external_calls))
