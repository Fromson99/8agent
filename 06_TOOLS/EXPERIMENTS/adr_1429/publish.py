"""Write ADR-1429 documents and manifest results from the saved run; no model call."""
from common import *
import gzip, tarfile, shutil

result, calls, generations = read(RUN / 'result.json'), read(RUN / 'calls.json'), read(RUN / 'generations.json')
criteria, case, candidate = read(DES / 'criteria.json'), read(DES / 'case.json'), read(DES / 'candidate.json')
source, issues = read(DES / 'comparison-source.json'), read(ART / 'preparation-issues.json')
body = json.load(gzip.open(RUN / 'response.json.gz', 'rt'))['body']
rel = lambda p: str(Path(p).relative_to(ROOT))
items = body['comparison_items']['items']
both = [i for i in items if i['internal']['citations'] and i['external']['citations']]
tokens_in = sum((c.get('usage') or {}).get('prompt_tokens', 0) for c in calls)
tokens_out = sum((c.get('usage') or {}).get('completion_tokens', 0) for c in calls)
cost = round(sum((c.get('usage') or {}).get('cost', 0) or 0 for c in calls), 8)
frozen_changed = [n for n, h in read(DES / 'freeze.json')['files'].items() if sha(ROOT / n) != h]
required = {
    'http200_no_supervisor_error': result['http_status'] == 200 and result['status'] in ('completed', 'partial') and not result['error'],
    'both_sides_originals_and_item_with_both': all(s['export_mode'] == 'SOURCE_HANDOFF' and s['evidence'] > 0 for s in result['sides'].values()) and bool(both),
    'accounting': result['unknown'] == 0 and result['physical_calls'] <= criteria['limits']['physical_total']
                  and result['duplicate']['extra_physical_calls'] == 0 and result['duplicate']['same_answer'] and not frozen_changed}
planted = [
    {'point': criteria['planted_points'][0], 'in_report': 'found', 'note': '설명 2: 내규 100분의 110, 외규 100분의 100, 내규가 더 높은 기준이라고 적음'},
    {'point': criteria['planted_points'][1], 'in_report': 'partly', 'note': '설명 3: 보고 대상과 시한이 다르다고 적었으나 "내부·외부 보고 절차가 병존"이라고만 하고 내규에 감독원장 보고 규정이 없다는 점은 적지 않음'},
    {'point': criteria['planted_points'][2], 'in_report': 'partly', 'note': '설명 4: 분기와 반기의 주기 차이는 적었으나 보고 대상(대표이사와 이사회) 차이는 의견에 적지 않음'}]
summary = {'schema_version': 'adr-1429-summary-v1', 'criteria_sha256': sha(DES / 'criteria.json'), 'required': required,
           'success_criteria_met': all(required.values()), 'http_status': result['http_status'], 'workflow_status': result['status'],
           'request_seconds': result['request_seconds'], 'physical_calls': result['physical_calls'], 'unknown': result['unknown'],
           'input_tokens': tokens_in, 'output_tokens': tokens_out, 'reported_cost_usd': cost, 'provider': sorted({c.get('actual_provider') for c in calls}),
           'stages': result['stages'], 'rejected_generations': result['rejected_generations'], 'sides': result['sides'],
           'comparison_items': [{'issue_id': i['issue_id'], 'field': i['field'], 'content_status': i['content_status'],
                                 'internal': i['internal']['status'], 'external': i['external']['status']} for i in items],
           'items_reviewed': sum(i['content_status'] != 'UNKNOWN' for i in items), 'items_total': len(items),
           'planted_points_operator_reading': planted, 'duplicate': result['duplicate'], 'frozen_files_changed': frozen_changed,
           'findings': [
               'Item review for concept-2 (single field "condition") returned three items covering other concepts; the wire projection maps them to the same field and rejects "duplicate field-side patch". The one corrective call repeated it, review stopped (WORKFLOW_REPAIR_EXHAUSTED) and 4 of 5 items stayed unreviewed.',
               'Corrective feedback carried only the text "duplicate field-side patch" and "Correct the entire proposal using the same evidence and scope".',
               'The final report is written by the finalization step from the acquired originals: four explanations each citing an internal and an external original.',
               'A concept-stage note that the external article 12 was not yet acquired remains in the final report although it was acquired and cited later.',
               'The external rule named in the internal article 1 was reached by model-driven search and reading (6 child calls), not by a named lookup.']}
put(RUN / 'summary.json', summary)

# Runtime journals are kept losslessly as one archive.
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
                                                'original_bytes': sum(m['bytes'] for m in members.values()), 'restore': 'tar -xzf runtime.tar.gz -C <run-001>',
                                                'verified_every_member_before_removal': True, 'files': members})
    shutil.rmtree(RUN / 'runtime')

ok = lambda flag: '충족' if flag else '미충족'
call_rows = '\n'.join('| %d | %s | %s | %s | %.1f | %s | %s | `raw/call-%03d/` |' % (
    c['number'], c['stage'], c.get('http_status'), c.get('finish_reason'), c['seconds'], (c.get('usage') or {}).get('prompt_tokens'),
    (c.get('usage') or {}).get('completion_tokens'), c['number']) for c in calls)
gen_rows = '\n'.join('| %d | %s | %s | %.1f | %s |' % (g['number'], g['stage'], '수락' if g['status'] == 'accepted' else '거절', g['seconds'], (g.get('error') or '').replace('|', '/')[:90]) for g in generations)
item_rows = '\n'.join('| %s | %s | %s | %s (%d) | %s (%d) |' % (i['issue_id'], i['field'], i['content_status'], i['internal']['status'], len(i['internal']['citations']),
                                                                i['external']['status'], len(i['external']['citations'])) for i in items)
documents = '\n'.join('- %s 「%s」 (%s): %s' % (d['document_id'], d['name'], '내규' if d['category'] == 'internal' else '외규', ', '.join(d['articles'])) for d in source['documents'])
example = json.load(gzip.open(RUN / 'raw/call-001/request.json.gz', 'rt'))

# ---- question file ------------------------------------------------------------
q = ADR / '실험' / ('질문-001-%s.md' % CASE)
q.write_text(f'''# 질문 001 — {CASE}

## 1. 실행 메타

- ADR: `ADR-1429`
- experiment: `ADR-1429-experiment-v1`
- case ID: `{CASE}`
- run ID: `run-001`
- 실행 시각: 2026-11-06 18:08~18:10 KST (요청 {result['request_seconds']}초)
- 원본 상태: `exact` — 물리 호출별 요청·응답 원문을 `artifacts/run-001/raw/call-NNN/`에 gzip으로 저장(인증 헤더 제외), 단계별 입력·검증된 출력은 `canonical/`
- 제품·중간 호출 모델: `qwen/qwen3.8-27b` (Parasail FP8, reasoning none, 출력 상한 없음)
- 오프라인 평가 모델: 없음 — 채점 호출 0회
- 실행 arm: `fixed` (`baseline`은 미실행 — MAIN164는 첫 내규 조사 행동에서 멈추는 것이 모델 없이 재현됨)

## 2. 사용자 질문 원문

```text
{case['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

합성 문서에 심어 둔 차이 3가지다. 제품 입력에는 넣지 않았고, 보고서에 나왔는지는 실행자가 읽어서 확인했다(채점 호출 없음).

```text
''' + '\n'.join(criteria['planted_points']) + f'''
```

## 4. 제품 입력을 구성한 원값

### 회수 전 전체·후보·제시 규모

```json
{json.dumps({'corpus': source['source_manifest']['counts'], 'retrieval': '제품의 하위 조사가 수행(변경 없음). 회수율은 측정하지 않음', 'internal_evidence': result['sides']['internal']['evidence'], 'external_evidence': result['sides']['external']['evidence']}, ensure_ascii=False)}
```

### 회수 좌표·조문·정의·Wiki·관계 — 전체

합성 문서(이 ADR 전용, 실제 내규·외규 아님):

{documents}

```json
{json.dumps({'generation_id': source['source_manifest']['generation_id'], 'store_sha256': source['source_manifest']['store_sha256'], 'frozen_source': rel(DES / 'comparison-source.json'), 'ontology': 'off (profile default)'}, ensure_ascii=False)}
```

### 회수·탈락 단계 원장 — run·arm별

회수 단계 원장은 해당 없음이다(stage_ledger mode=not_applicable). 확보 원문은 내규 5개 조 전부, 외규는 감독규정 제12~15조와 전자금융 제5조였다.

| run | arm | stage | kind | before | +added | -discarded | after | gold before | gold + | gold - | gold after/total | recall | 대표 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| run-001 | fixed | 해당 없음 | 해당 없음 | - | - | - | - | - | - | - | - | - | 원장 미작성 |

```json
{json.dumps({'stage_ledger_artifact': None, 'discarded_gold_and_reasons': '해당 없음', 'gold_visible_to_product': False}, ensure_ascii=False)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

### run-001 / baseline / system

```text
미실행
```

### run-001 / fixed / system

호출마다 system이 다르다. 전체 13건의 원문은 `artifacts/run-001/raw/call-NNN/request.json.gz`에 있다. 아래는 첫 호출(workflow-intake)의 system 전문이다.

```text
{example['messages'][0]['content']}
```

### run-001 / fixed / user

첫 호출의 user 전문(나머지는 같은 위치의 보관 파일).

```text
{example['messages'][1]['content']}
```

### run-001 / fixed / schema·tool

단계별 스키마는 `artifacts/run-001/canonical/NNN.json.gz`의 `schema`에 있다.

```json
{json.dumps({'stages': result['stages']}, ensure_ascii=False)}
```

### run-001 / fixed / provider 원응답·structured output·usage·지연

| 호출 | 단계 | HTTP | 종료 | 초 | 입력 토큰 | 출력 토큰 | 원문 위치 |
|---:|---|---:|---|---:|---:|---:|---|
{call_rows}

합계: 물리 호출 {len(calls)}회, 입력 {tokens_in} / 출력 {tokens_out} 토큰, 보고 비용 {cost}달러, 결과 불명 0건, 공급자 {', '.join(summary['provider'])}.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

단계별 수락·거절(거절된 12번은 11번의 보완 호출이다).

| 순번 | 단계 | 결과 | 초 | 사유 |
|---:|---|---|---:|---|
{gen_rows}

```json
{json.dumps({'corrective_calls': 1, 'stage': 'workflow-items', 'error': 'duplicate field-side patch', 'outcome': 'WORKFLOW_REPAIR_EXHAUSTED'}, ensure_ascii=False)}
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
| run-001 | baseline | 판정 없음 | 미실행(모델 없이 재현된 첫 단계 오류) | other: supervisor_authorization |
| run-001 | fixed | 기술 기준 {ok(summary['success_criteria_met'])} | HTTP {result['http_status']}/{result['status']}, 양쪽 원문 확보, 항목 {summary['items_reviewed']}/{summary['items_total']}건 검토 | other: item_review_duplicate_field_patch |

- 사전 지정 비교쌍의 신규 정답·회귀: baseline 미실행이라 짝 비교 없음.
- 공통 실패 유형: `other` — 항목 검토 단계의 응답이 한 항목에 여러 건을 담아 형식 검증에 걸렸고 보완 1회에도 반복됨.
- 사람이 확인한 직접 원인: 쟁점 하나(항목 1개)를 묻는 호출에 모델이 다른 쟁점의 내용까지 3건을 제출했다. 보완 안내는 "duplicate field-side patch"뿐이었다.
- 다음 분기에서 검증할 가설: 항목 수를 쟁점의 항목 수로 제한하고 보완 안내에 어느 항목이 겹쳤는지 적으면 항목 검토가 통과한다.
''', 'utf-8')

# ---- 실험/README.md -------------------------------------------------------------
index = (ADR / '실험/README.md').read_text('utf-8')
def swap(old, new, text):
    assert text.count(old) == 1, old
    return text.replace(old, new)
index = swap('- 이 분기의 변경 가설: TODO', '- 이 분기의 변경 가설: ' + criteria['question'], index)
index = swap('| `baseline` | baseline | ROOT | TODO | TODO |', '| `baseline` | baseline | ROOT | MAIN164 그대로(미실행) | 같은 프로필·워크플로우 |', index)
index = swap('| `fixed` | candidate | baseline | TODO | TODO |', '| `fixed` | candidate | baseline | 원문 반환 모드에서 감독·원문 목표 관리 제외(제품 2개 파일) | 선택 프로필(감독 enforce), 합성 문서, Qwen3.8 |', index)
index = swap('| 001 | `%s` | `run-001` | TODO | TODO | TODO |' % CASE,
             '| 001 | `%s` | `run-001` | fixed: HTTP 200·partial, 기술 기준 %s | baseline 미실행 | other: 항목 검토 형식 오류 |' % (CASE, ok(summary['success_criteria_met'])), index)
index = swap('- run 상태: `run-001 / planned`', '- run 상태: `run-001 / complete` (요청 1건)', index)
index = swap('- arm별 정답: TODO', '- arm별 정답: fixed 기술 기준 3개 %s, 항목 검토 %d/%d건' % (ok(summary['success_criteria_met']), summary['items_reviewed'], summary['items_total']), index)
index = swap('- 사전 지정 비교쌍별 신규 정답 / 회귀: TODO', '- 사전 지정 비교쌍별 신규 정답 / 회귀: 해당 없음(baseline 미실행)', index)
index = swap('- judge 불일치: TODO', '- judge 불일치: 채점 호출 없음', index)
index = swap('| `run-001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |', '| `run-001` | fixed | 해당 없음 | 해당 없음 | - | - | - | - | 원장 미작성 |', index)
(ADR / '실험/README.md').write_text(index, 'utf-8')

# ---- README.md -----------------------------------------------------------------
readme = (ADR / 'README.md').read_text('utf-8')
head, _ = readme.split('## 2. 문제와 변경 전 구조', 1)
head = swap('TODO: 채택·기각·보류와 운영 배선 변경 여부를 먼저 적는다.',
            f"보류(Proposed). 감독 제외 수정본으로 합성 내규·외규 대사 1건을 실제 Qwen3.8로 실행했다. 첫 단계 오류 없이 HTTP {result['http_status']}로 보고서까지 갔고 "
            f"사전 기술 기준 3개를 충족했다. 다만 항목 검토 단계에서 모델 응답이 형식 검증에 걸려 {summary['items_total']}개 항목 중 {summary['items_reviewed']}개만 검토됐고 상태는 partial이다. "
            "보고서의 설명은 마무리 단계가 확보 원문으로 쓴 것이다. 운영 배선 변경 없음.", head)
prep = '\n'.join('- %s: %s' % (i['step'], i['issue']) for i in issues)
text = head + f'''## 2. 문제와 변경 전 구조

대사(`risk_team_compare_workflow`)는 내규·외규 조사를 원문 반환 모드로 기존 RAG에 맡긴다. 선택 프로필은 감독을 켜 두는데, 이 모드의 선택 코드는 감독 승인을 받지 않아 첫 조사 행동에서 `native action lacks current supervisor authorization`으로 멈췄다(ADR-1293 실제 실행, MAIN164에서 모델 없이 재현). 수정본은 원문 반환 모드에서 감독과 원문 목표 관리를 적용하지 않는다(`investigation_supervisor.py`, `source_goal_control.py`). 가짜 응답 검사는 통과했으나 실제 모델로 개념·항목 대조·보고서 단계가 도는지는 확인된 적이 없었다.

## 3. 가설과 사전 판정 기준

### 가설

{criteria['question']}. 예상: 첫 단계 오류 없이 보고서까지 간다. 개념·항목 단계에서 형식 보완이 생길 수 있다.

### 성공 기준

''' + '\n'.join('- ' + x for x in criteria['required']) + f'''
- 한도: 요청 1건, 물리 호출 {criteria['limits']['physical_total']}회, 호출당 180초, 보고 비용 {criteria['limits']['reported_cost_usd']}달러.

### 반증 기준

- {criteria['stop']}
- HTTP 500 또는 감독 승인 오류.
- 제품이 보고한 원문·권한·해시 불일치.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | MAIN164 그대로(미실행) | 같은 프로필·워크플로우 | baseline |
| fixed | 원문 반환 모드에서 감독·원문 목표 관리 제외(제품 2개 파일, 고정값 31개 재계산) | 선택 프로필 `profile-unified-v6`(감독 enforce) 그대로, 워크플로우 1.20.8, 합성 문서, Qwen3.8 정책 | candidate |

- 후보 코드는 MAIN164 기준 533개 파일 스냅샷이다. 동결 시점의 선택 MAIN은 165였고(Oracle 탐색 호환 수정), 대사 경로 파일은 164와 같다.
- 실행: 네이티브 API(`/v1/rag/ask`)에 요청 1건, 같은 요청을 한 번 더 보내 추가 호출이 없는지 확인. 제품 코드는 스냅샷에서만 불러왔다.
- 합성 문서에 차이 3가지를 심어 두고 보고서에 나오는지 읽어서 확인했다(채점 호출 없음).

### 다른 ADR과의 관계

- 관련 ADR: 없음

- experiment 계보와 직접 부모 arm: [실험 manifest](실험/manifest.json)

## 5. 데이터·모델·재현성

- 데이터셋과 버전: 이 ADR용 합성 문서 3개(내규 1, 외규 2), 조문 12개. 세대 `{source['source_manifest']['generation_id']}`. 실제 내규·외규는 쓰지 않았다.
- frozen source와 SHA-256: `{rel(DES / 'comparison-source.json')}` `{sha(DES / 'comparison-source.json')}`; 동결 목록 `{rel(DES / 'freeze.json')}`(호출 전 실행기 수정 3회 기록 포함).
- 제품/중간/채점 모델: `qwen/qwen3.8-27b` (Parasail FP8, reasoning none, 출력 상한 없음). 채점 호출 없음.
- 반복 수와 다수결: 요청 1건, 반복 없음.
- 법령·기준답변 버전 점검: 해당 없음(합성 문서).

## 6. 결과

| arm | 정답/전체 | 정확도 | baseline 대비 | 입력 토큰 | p50/p95 |
|---|---:|---:|---:|---:|---:|
| baseline | 미실행 | - | - | - | - |
| fixed | 기술 기준 {sum(required.values())}/3 | - | 첫 단계 오류 없음 | {tokens_in} | 호출 13건, 요청 {result['request_seconds']}초 |

- HTTP {result['http_status']}, 상태 `{result['status']}`, 물리 호출 {len(calls)}회(모두 HTTP 200·정상 종료), 결과 불명 0건, 보고 비용 {cost}달러.
- 하위 조사: 내규 5개 조 전부, 외규 5개 조(감독규정 제12~15조, 전자금융 제5조)를 원문 반환으로 확보. 감독 관련 오류 없음.
- 같은 요청 재전송: 같은 답, 추가 호출 0.
- 동결 파일 변경 {len(frozen_changed)}건, 후보 코드 변경 없음.

단계별 결과:

| 순번 | 단계 | 결과 | 초 | 사유 |
|---:|---|---|---:|---|
{gen_rows}

항목 대조표(제품 출력):

| 쟁점 | 항목 | 내용 상태 | 내규(인용 수) | 외규(인용 수) |
|---|---|---|---|---|
{item_rows}

| paired outcome | 건수 | 비율 |
|---|---:|---:|
| 비교 arm만 정답 | 해당 없음 | baseline 미실행 |
| 기준 arm만 정답(회귀) | 해당 없음 | - |
| 둘 다 정답 | 해당 없음 | - |
| 둘 다 오답 | 해당 없음 | - |

심어 둔 차이(실행자 읽기, 채점 아님):

| 차이 | 보고서 | 메모 |
|---|---|---|
''' + '\n'.join('| %s | %s | %s |' % (p['point'], {'found': '있음', 'partly': '일부'}[p['in_report']], p['note']) for p in planted) + f'''

## 7. 사례별 오류 분석

| 실패 유형 | 건수/분모 | 대표 질문 | 해석 |
|---|---:|---|---|
| other: 항목 검토 형식 오류 | 1 / 1 요청 | {CASE} | 쟁점 concept-2(항목 1개)를 묻는 호출에 모델이 다른 쟁점 내용까지 3건을 냈다. 항목 이름이 없는 응답이라 3건이 같은 항목으로 묶여 "duplicate field-side patch"로 거절됐고, 보완 1회도 같은 형태였다. 그 뒤 남은 쟁점은 검토하지 않았다. |
| other: 낡은 안내 문구 | 1 / 1 요청 | {CASE} | 개념 단계에 적은 "외규 제12조 미확보"가 이후 확보·인용된 뒤에도 보고서의 추가 확인 사항에 남았다. |

질문별 실제 입출력은 [실험 인덱스](실험/README.md)에 연결한다.

## 8. 비용·지연·회수 규모

| 항목 | 값 | 측정 단위·분모 |
|---|---:|---|
| 전체 corpus | 3문서 12조문 | 합성 |
| 필터 전/후 후보 | 측정 안 함 | 제품 하위 조사 그대로 |
| LLM 제시 수 | 내규 5, 외규 5 | 확보 원문 조문 수 |
| golden recall | 해당 없음 | 기준 좌표 없음 |
| 제시 비율 | 10 / 12 | 확보 조문 / 전체 조문 |
| LLM 호출·토큰·지연 | {len(calls)}회 · 입력 {tokens_in} · 출력 {tokens_out} | 요청 {result['request_seconds']}초, {cost}달러 |

회수를 변경하지 않았다. 단계 원장은 해당 없음(`stage_ledger.mode=not_applicable`).

### 단계별 회수·탈락 원장

| run | arm | stage | kind | 후보 before→after | added / discarded | gold before→after | gold gain / loss | recall | 주요 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| run-001 | fixed | 해당 없음 | 해당 없음 | - | - | - | - | - | 원장 미작성 |

## 9. 해석

- 사실: 수정본에서는 실제 모델로도 내규 조사, 개념 정하기, 외규 조사가 오류 없이 진행됐다. 감독 승인 오류는 나오지 않았다.
- 사실: 항목 검토는 첫 쟁점만 통과했고 둘째 쟁점에서 형식 검증에 걸려 멈췄다. 이 문제는 감독 수정과 무관하게 항목 검토 단계에 원래 있던 것이다.
- 사실: 그래도 마무리 단계가 확보 원문으로 설명 4개를 썼고, 각 설명이 내규와 외규 원문을 함께 인용한다. 같은 보고서에 "판정할 수 없습니다" 문구가 함께 나온다.
- 사실: 내규 제1조에 적힌 외규 이름은 이름으로 바로 찾지 않고, 하위 조사가 검색과 읽기 6회로 찾았다.
- 추론: 항목 수 제한과 구체적인 보완 안내를 넣으면 항목 검토가 통과할 가능성이 있다(미검증).

## 10. 한계와 일반화 가능 범위

- 요청 1건, 합성 문서, 인샘플이다. 실제 내규·외규, 반복 안정성, 법적 품질, GENOS 내부 모델은 확인하지 않았다.
- 심어 둔 차이의 확인은 실행자가 읽은 것이며 채점이 아니다.
- baseline은 실행하지 않았다(모델 없이 재현된 오류와 ADR-1293 기록에 근거).
- 후보는 MAIN164 기준이다. 현재 선택 MAIN165에 얹은 상태로는 실모델을 돌리지 않았다.

## 11. 운영 결정·롤백 조건

- 메인 배선: 변경 없음. 수정 2개 파일은 작업 코드에 있고 선택 MAIN에는 없다.
- MAIN 반영은 별도 결정이며, 현재 선택 MAIN165 위에 다시 얹어 검사한 뒤 공식 절차로 한다.
- 항목 검토 형식 문제와 낡은 안내 문구는 후속 수정 대상이다.

## 12. 재현 명령

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1429/setup.py              # 후보·합성 문서·기준 동결(최초 1회)
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1429/live.py --scripted    # 가짜 응답 배선 점검(호출 없음)
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1429/live.py               # 실제 요청 1건
```

준비 과정의 실패(모델 호출 0건):

{prep}

- 원시 산출물: [artifacts/manifest.json](artifacts/manifest.json)
- 질문 파일 hash: [실험/manifest.json](실험/manifest.json)
'''
(ADR / 'README.md').write_text(text, 'utf-8')

# ---- manifest results and artifacts ---------------------------------------------
manifest = read(ADR / '실험/manifest.json')
manifest['results'] = {
    'status': 'complete',
    'by_arm': {'baseline': {'status': 'not_executed', 'correct': 0, 'total': 0, 'accuracy': None, 'decision_eligible': False,
                            'scope': 'reference only: first-step supervisor authorization failure reproduced without a model'},
               'fixed': {'status': 'complete', 'correct': 1 if summary['success_criteria_met'] else 0, 'total': 1, 'accuracy': None, 'decision_eligible': False,
                         'scope': 'one request; frozen technical criteria met=%s; workflow status partial' % summary['success_criteria_met'],
                         'http_status': result['http_status'], 'workflow_status': result['status'], 'items_reviewed': summary['items_reviewed'], 'items_total': summary['items_total']}},
    'comparisons': [], 'judge_disagreements': 0,
    'usage': {'physical_requests': len(calls), 'offline_evaluator_requests': 0, 'input_tokens': tokens_in, 'output_tokens': tokens_out, 'reported_cost_usd': cost, 'unknown': 0},
    'latency': {'request_seconds': result['request_seconds'], 'per_call_seconds': [c['seconds'] for c in calls]},
    'error_taxonomy': [{'type': 'other: item_review_duplicate_field_patch', 'case_id': CASE, 'stage': 'workflow-items', 'corrective_calls': 1, 'outcome': 'WORKFLOW_REPAIR_EXHAUSTED'},
                       {'type': 'other: stale_unresolved_note', 'case_id': CASE}],
    'frozen_criteria': {'required': required, 'success_criteria_met': summary['success_criteria_met']}}
manifest['runs'][0].update(status='complete', sha256=sha(RUN / 'result.json'), success_criteria_met=summary['success_criteria_met'])
manifest['questions'][0]['sha256'] = sha(q)
(ADR / '실험/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')
existing = read(ART / 'manifest.json')
described = {'design': '호출 전 동결한 후보·합성 문서·기준', 'preflight': '호출 전 점검 기록(실패 포함)', 'run-001': '실제 실행 기록', 'transport': '고정한 전송 모듈',
             'corpus': '합성 문서(실행용)', 'scripted-corpus': '합성 문서(가짜 응답 점검용)'}
files = []
for path in sorted(p for p in ART.rglob('*') if p.is_file() and p != ART / 'manifest.json'):
    top = path.relative_to(ART).parts[0]
    files.append({'path': rel(path), 'sha256': sha(path), 'bytes': path.stat().st_size, 'description': described.get(top, '준비·실행 기록'),
                  'contains_raw_prompts_and_outputs': 'raw/' in rel(path) or 'canonical/' in rel(path) or 'experiment-client/' in rel(path)})
existing['files'] = files
(ART / 'manifest.json').write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print('published', len(files), 'artifact files; criteria', required, '; items', summary['items_reviewed'], '/', summary['items_total'])
