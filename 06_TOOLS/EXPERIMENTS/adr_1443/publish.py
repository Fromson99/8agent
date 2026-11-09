"""Write ADR-1443 documents and manifest results from the saved runs; no model call."""
from common import *
import gzip, tarfile, shutil

criteria, case = read(DES / 'criteria.json'), read(DES / 'case.json')
source = read(DES / 'comparison-source.json')
issues = read(ART / 'preparation-issues.json')
rel = lambda p: str(Path(p).relative_to(ROOT))
runs = {}
for name in ('run-001',):
    folder = ART / name
    calls = read(folder / 'calls.json') if (folder / 'calls.json').exists() else []
    result = read(folder / 'result.json') if (folder / 'result.json').exists() else None
    runs[name] = {'calls': calls, 'result': result,
                  'cost': round(sum(((c.get('usage') or {}).get('cost') or 0) for c in calls), 8),
                  'tokens_in': sum(((c.get('usage') or {}).get('prompt_tokens') or 0) for c in calls),
                  'tokens_out': sum(((c.get('usage') or {}).get('completion_tokens') or 0) for c in calls)}
    if (folder / 'runtime').exists():
        files = sorted(p for p in (folder / 'runtime').rglob('*') if p.is_file())
        members = {str(p.relative_to(folder)): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in files}
        with tarfile.open(folder / 'runtime.tar.gz', 'w:gz') as tar:
            for p in files:
                tar.add(p, arcname=str(p.relative_to(folder)))
        with tarfile.open(folder / 'runtime.tar.gz') as tar:
            for item, meta in members.items():
                data = tar.extractfile(item).read()
                assert hashlib.sha256(data).hexdigest() == meta['sha256'] and len(data) == meta['bytes'], item
        put(folder / 'runtime-archive-receipt.json', {'archive': 'runtime.tar.gz', 'archive_sha256': sha(folder / 'runtime.tar.gz'),
            'members': len(members), 'restore': 'tar -xzf runtime.tar.gz -C <' + name + '>', 'verified_every_member_before_removal': True, 'files': members})
        shutil.rmtree(folder / 'runtime')
calls = [dict(c, run=name) for name, r in runs.items() for c in r['calls']]
cost = round(sum(r['cost'] for r in runs.values()), 8)
findings = [
    '요청 1건이 54분(3,254초) 동안 모델 %d번(묶음 정리 13, 외규 조사 302, 단위 비교 98)을 부르고 HTTP 500으로 끝났다. 결과 불명 0, 보고 비용 %s달러.' % (len(calls), cost),
    '외규 조사는 단위 원문과 사용자 요청으로 일반 RAG 검색을 했다(96단위 중 95단위). 입력은 한 번에 최대 약 10만 토큰으로 한도 안이었다. ADR-1440의 87만 토큰 문제는 다시 나지 않았다.',
    '32개 묶음 중 12개를 끝냈다(97단위: 판정 보류 80, 내부 추가기준 14, 부합 2; 대상 아님 50행, 보류 13행). 판정 보류가 많다(외규 조사 상태 completed 56, partial 36, failed 4).',
    '실패 원인: 외규 이름이 적힌 단위 1개에서 검색 범위를 그 법령으로 좁혔는데, 다음 단위 시작 전 이전 외규 조사 기록을 다시 검사하는 코드가 좁히기 전 전체 외규 목록과 비교해 "범위가 바뀌었다"는 무결성 오류를 냈다. 이 오류로 실행이 영구 실패가 되어 끝낸 묶음이 부분 결과로 남지 않았다.',
    '공급자 응답: 확정 429가 16번(Near AI 전환), 공급자 오류 400이 4번. 결과 불명은 0번.',
    '후속 수정(이 ADR 범위 밖): 재검사가 그 호출이 요청한 좁힌 범위와 비교하도록 고쳤고, 외규 2개짜리 시험 묶음으로 수정 전 실패·수정 뒤 통과를 확인했다.']
put(ART / 'summary.json', {'schema_version': 'adr-1440-summary-v1', 'criteria_sha256': sha(DES / 'criteria.json'),
    'success_criteria_met': False, 'runs': {n: {'calls': len(r['calls']), 'cost': r['cost'], 'result': r['result'] and {k: r['result'].get(k) for k in ('http_status', 'status', 'request_seconds', 'physical_calls', 'unknown', 'stage_counts', 'error')}} for n, r in runs.items()},
    'model_calls': len(calls), 'reported_cost_usd': cost, 'findings': findings})
call_rows = '\n'.join('| %s | %d | %s | %s | %s | %s | %s |' % (c['run'], c['number'], c['stage'], c.get('http_status'), c['status'], c.get('seconds'),
                      (c.get('usage') or {}).get('prompt_tokens')) for c in calls)
finding_lines = '\n'.join('- ' + f for f in findings)
prep = '\n'.join('- %s: %s' % (i['step'], i['issue']) for i in issues)
required_lines = '\n'.join('- ' + x for x in criteria['required'])

q = ADR / '실험' / ('질문-001-%s.md' % CASE)
q.write_text(f'''# 질문 001 — {CASE}

## 1. 실행 메타

- ADR: `ADR-1443`
- experiment: `ADR-1443-experiment-v1`
- case ID: `{CASE}`
- run ID: `run-001`
- 실행 시각: 2026-11-06 23:13 ~ 2026-11-07 00:07(KST)
- 원본 상태: `exact` — 호출별 요청·응답 원문은 각 run의 `raw/call-NNN/`, 단계별 입력·출력은 `canonical/`
- 제품·중간 호출 모델: `qwen/qwen3.8-27b` (Parasail FP8 우선, 확정 429에만 Near AI FP8, reasoning none, 출력 상한 없음)
- 오프라인 평가 모델: 없음 — 채점 호출 0회
- 실행 arm: `docsearch`

## 2. 사용자 질문 원문

```text
{case['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

기준답변 없음. 문서 전체 대사가 끝나는지와 묶음·단위 처리를 기술 기준으로만 본다.

```text
해당 없음
```

## 4. 제품 입력을 구성한 원값

### 회수 전 전체·후보·제시 규모

```json
{json.dumps({'corpus': [{k: d[k] for k in ('name', 'category', 'blocks', 'chars')} for d in source['documents']], 'retrieval': '제품 하위 조사 그대로, 회수율 미측정'}, ensure_ascii=False)}
```

### 회수 좌표·조문·정의·Wiki·관계 — 전체

ADR-1440의 시험용 묶음(공개 허용 문서 5개, 모범규준만 내규로 분류)을 해시로 확인해 그대로 썼다.

```json
{json.dumps({'generation_id': source['source_manifest']['generation_id'], 'store_sha256': source['source_manifest']['store_sha256'], 'copied_from': source['copied_from']}, ensure_ascii=False)}
```

### 회수·탈락 단계 원장 — run·arm별

회수 단계 원장은 해당 없음이다(stage_ledger mode=not_applicable).

| run | arm | stage | kind | before | +added | -discarded | after | gold before | gold + | gold - | gold after/total | recall | 대표 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| run-001 | docsearch | 해당 없음 | 해당 없음 | - | - | - | - | - | - | - | - | - | 원장 미작성 |

```json
{json.dumps({'stage_ledger_artifact': None, 'discarded_gold_and_reasons': '해당 없음', 'gold_visible_to_product': False}, ensure_ascii=False)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

### run-001 / docmode / system

호출마다 system이 다르다. 원문은 `artifacts/run-00N/raw/call-NNN/request.json.gz`에 있다.

### run-001 / docmode / user

`artifacts/run-001/raw/call-001/request.json.gz` (묶음 행 정리).

### run-001 / docmode / schema·tool

`artifacts/run-00N/canonical/NNN.json.gz`의 `schema`.

### run-001 / docmode / provider 원응답·structured output·usage·지연

| run | 호출 | 단계 | HTTP | 상태 | 초 | 입력 토큰 |
|---|---:|---|---:|---|---:|---:|
{call_rows}

합계: 물리 호출 {len(calls)}회, 보고 비용 {cost}달러.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

보완 호출 없음. 하위 조사의 질문 해석·감독 검토·멀티턴 해석 호출은 위 표에 있다.

```json
{json.dumps({'corrective_calls': 0}, ensure_ascii=False)}
```

## 7. 채점 호출과 반복 판정

### judge system/user — 기준답변 포함

```json
{json.dumps({'judge_calls': 0}, ensure_ascii=False)}
```

### judge 원응답과 최종 다수결

```json
{json.dumps({'judge_calls': 0}, ensure_ascii=False)}
```

## 8. 사례 최종 판정

| run | arm | 정답 | 핵심 근거 | 실패 유형 |
|---|---|---:|---|---|
| run-001 | docsearch | 미완료 | 12/32 묶음 뒤 재검사 무결성 오류로 HTTP 500 | other: narrowed_scope_reverification |

- 사람이 확인한 직접 원인: 좁힌 검색 범위를 재검사가 전체 외규 목록과 비교함.
- 다음 분기에서 검증할 가설: 재검사를 요청 범위와 비교하면 문서 전체가 끝난다.
''', 'utf-8')

index = (ADR / '실험/README.md').read_text('utf-8')
def swap(old, new, text):
    assert text.count(old) == 1, old
    return text.replace(old, new)
index = swap('- 이 분기의 변경 가설: TODO', '- 이 분기의 변경 가설: ' + criteria['question'], index)
index = swap('| `baseline` | baseline | ADR-1440-experiment-v1/docmode | TODO | TODO |', '| `baseline` | baseline | ADR-1440-experiment-v1/docmode | ADR-1440 문서 대사(미완료, 재실행 없음) | 같은 묶음·질문 |', index)
index = swap('| `docsearch` | candidate | baseline | TODO | TODO |', '| `docsearch` | candidate | baseline | 일반 RAG 외규 검색·단위별 세션·결과 불명 시 부분 결과 | 선택 프로필, 같은 묶음, Qwen3.8 |', index)
index = swap('| 001 | `%s` | `run-001` | TODO | TODO | TODO |' % CASE,
             '| 001 | `%s` | `run-001` | 12/32 묶음 뒤 HTTP 500 | 해당 없음 | other: 좁힌 범위 재검사 오류 |' % CASE, index)
index = swap('- run 상태: `run-001 / planned`', '- run 상태: `run-001 / complete`(요청은 끝까지 돌았고 HTTP 500, 기준 미충족)', index)
index = swap('- arm별 정답: TODO', '- arm별 정답: docsearch 기술 기준 미충족(12/32 묶음)', index)
index = swap('- 사전 지정 비교쌍별 신규 정답 / 회귀: TODO', '- 사전 지정 비교쌍별 신규 정답 / 회귀: 해당 없음(비교쌍 없음)', index)
index = swap('- judge 불일치: TODO', '- judge 불일치: 채점 호출 없음', index)
index = swap('| `run-001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |', '| `run-001` | docsearch | 해당 없음 | 해당 없음 | - | - | - | - | 원장 미작성 |', index)
(ADR / '실험/README.md').write_text(index, 'utf-8')

readme = (ADR / 'README.md').read_text('utf-8')
head, _ = readme.split('## 2. 문제와 변경 전 구조', 1)
head = swap('TODO: 채택·기각·보류와 운영 배선 변경 여부를 먼저 적는다.',
            f'기각(Rejected). ADR-1440의 실패 원인을 고친 문서 대사 수정본으로 같은 공개 시험 묶음(모범규준 약 20쪽)을 실행했다. '
            f'일반 RAG 외규 검색으로 입력 한도 문제는 사라졌고 32개 묶음 중 12개(97단위)를 끝냈지만, 좁힌 검색 범위를 재검사가 전체 외규 목록과 비교한 무결성 오류로 54분 만에 HTTP 500으로 끝났다. '
            f'모델 호출 {len(calls)}번, 보고 비용 {cost}달러, 결과 불명 0. 수정은 다른 ADR에서 시험한다. 운영 배선 변경 없음.', head)
prep = '\n'.join('- %s: %s' % (i['step'], i['issue']) for i in issues) or '- 없음'
text = head + f'''## 2. 문제와 변경 전 구조

ADR-1440은 단위마다 문서 전체의 큰 법령 3개를 먼저 읽게 해 입력 한도를 넘었고, 하위 세션을 공유했으며, 결과 불명 뒤 전체가 실패했다. 이번 후보는 외규 이름이 없으면 일반 RAG, 있으면 그 법령 안에서만 검색, 단위별 하위 세션, 결과 불명이면 부분 결과로 멈춤을 넣었다.

## 3. 가설과 사전 판정 기준

### 가설

{criteria['question']}

### 성공 기준

{required_lines}

### 반증 기준

- {criteria['stop']}
- HTTP 500 또는 워크플로우 실패, 끝에 남은 대기 묶음, 제품이 보고한 원문·권한·해시 불일치.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | ADR-1440 docmode, 재실행 없음 | 같은 묶음·질문 | baseline |
| docsearch | ADR-1440 후보 + 일반 RAG 외규 검색·단위별 세션·결과 불명 시 부분 결과 | 선택 프로필, 같은 묶음, Qwen3.8, 시간·호출 한도 없음 | candidate |

### 다른 ADR과의 관계

- 관련 ADR: 없음

- experiment 계보와 직접 부모 arm: [실험 manifest](실험/manifest.json)

## 5. 데이터·모델·재현성

- 데이터셋과 버전: ADR-1440 시험용 묶음 세대 `{source['source_manifest']['generation_id']}`(해시로 재사용).
- frozen source와 SHA-256: `{rel(DES / 'comparison-source.json')}` `{sha(DES / 'comparison-source.json')}`; 동결 목록 `{rel(DES / 'freeze.json')}`.
- 제품/중간/채점 모델: `qwen/qwen3.8-27b`. 채점 호출 없음.
- 반복 수와 다수결: 요청 1건.
- 법령·기준답변 버전 점검: 해당 없음.

## 6. 결과

| arm | 정답/전체 | 정확도 | baseline 대비 | 입력 토큰 | p50/p95 |
|---|---:|---:|---:|---:|---:|
| baseline | ADR-1440 미완료 | - | - | - | - |
| docsearch | 12/32 묶음 | - | 묶음 0 → 12 | {sum(r['tokens_in'] for r in runs.values())} | 호출 {len(calls)}건 |

| paired outcome | 건수 | 비율 |
|---|---:|---:|
| 비교 arm만 정답 | 해당 없음 | - |
| 기준 arm만 정답(회귀) | 해당 없음 | - |
| 둘 다 정답 | 해당 없음 | - |
| 둘 다 오답 | 해당 없음 | - |

관찰:

{finding_lines}

## 7. 사례별 오류 분석

| 실패 유형 | 건수/분모 | 대표 질문 | 해석 |
|---|---:|---|---|
| other: narrowed_scope_reverification | 1 / 1 실행 | {CASE} | 좁힌 검색 범위의 기록을 재검사가 전체 외규 목록과 비교해 무결성 오류 |
| other: many_deferred | 80 / 97 단위 | {CASE} | 판정 보류가 많음. 외규 조사 partial 36·failed 4 포함. 원인은 후속 분석 대상 |

질문별 실제 입출력은 [실험 인덱스](실험/README.md)에 연결한다.

## 8. 비용·지연·회수 규모

| 항목 | 값 | 측정 단위·분모 |
|---|---:|---|
| 전체 corpus | 5문서 33,090문단 | 시험용 묶음 |
| 필터 전/후 후보 | 측정 안 함 | 제품 하위 조사 그대로 |
| LLM 제시 수 | 측정 안 함 | - |
| golden recall | 해당 없음 | 기준 좌표 없음 |
| 제시 비율 | 해당 없음 | - |
| LLM 호출·토큰·지연 | {len(calls)}회 · 입력 {sum(r['tokens_in'] for r in runs.values())} · 출력 {sum(r['tokens_out'] for r in runs.values())} | 3,254초, {cost}달러 |

회수 점수는 측정하지 않았다. 단계 원장은 해당 없음(`stage_ledger.mode=not_applicable`).

### 단계별 회수·탈락 원장

| run | arm | stage | kind | 후보 before→after | added / discarded | gold before→after | gold gain / loss | recall | 주요 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| run-001 | docsearch | 해당 없음 | 해당 없음 | - | - | - | - | - | 원장 미작성 |

## 9. 해석

- 사실: 일반 RAG 외규 검색으로 바꾼 뒤 입력 한도 초과는 없었고, 묶음 12개를 실제 모델로 끝냈다.
- 사실: 좁힌 검색 범위의 재검사 오류 하나로 실행 전체가 실패해 부분 결과가 남지 않았다.
- 추론: 재검사 수정 뒤에는 남은 20묶음도 진행될 것이다. 판정 보류 비율이 높은 원인은 따로 본다.

## 10. 한계와 일반화 가능 범위

- 요청 1건, 공개 문서(내규 대체), 인샘플. 끝까지 간 실행이 없다.

## 11. 운영 결정·롤백 조건

- 메인 배선 변경 없음. 수정은 `09_ARTIFACTS/AUDITS/20261106-document-compare/code`에서 하고 다른 ADR로 시험한다.

## 12. 재현 명령

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1443/setup.py
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1443/live.py --scripted
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1443/live.py
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1443/publish.py
```

준비 과정의 실패와 재동결:

{prep}

- 원시 산출물: [artifacts/manifest.json](artifacts/manifest.json)
- 질문 파일 hash: [실험/manifest.json](실험/manifest.json)
'''
(ADR / 'README.md').write_text(text, 'utf-8')

manifest = read(ADR / '실험/manifest.json')
manifest['results'] = {
    'status': 'complete',
    'by_arm': {'baseline': {'status': 'reference', 'correct': 0, 'total': 1, 'accuracy': None, 'decision_eligible': False,
                            'scope': 'ADR-1440 document comparison; not finished; not re-executed'},
               'docsearch': {'status': 'complete', 'correct': 0, 'total': 1, 'accuracy': None, 'decision_eligible': False,
                             'scope': 'whole-document comparison finished / requested; 12 of 32 groups before HTTP 500'}},
    'comparisons': [], 'judge_disagreements': 0,
    'usage': {'physical_requests': len(calls), 'offline_evaluator_requests': 0, 'input_tokens': sum(r['tokens_in'] for r in runs.values()),
              'output_tokens': sum(r['tokens_out'] for r in runs.values()), 'reported_cost_usd': cost, 'unknown': 0},
    'latency': {'per_call_seconds': [c.get('seconds') for c in calls]},
    'error_taxonomy': [{'type': 'other: narrowed_scope_reverification', 'run': 'run-001'}],
    'frozen_criteria': {'required': criteria['required'], 'success_criteria_met': False}}
manifest['runs'][0].update(status='complete', sha256=sha(ART / 'run-001/result.json'), artifact_path=rel(ART / 'run-001/result.json'), success_criteria_met=False)
manifest['questions'][0]['sha256'] = sha(q)
(ADR / '실험/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')
existing = read(ART / 'manifest.json')
files = []
for path in sorted(p for p in ART.rglob('*') if p.is_file() and p != ART / 'manifest.json'):
    files.append({'path': rel(path), 'sha256': sha(path), 'bytes': path.stat().st_size, 'description': '준비·실행 기록',
                  'contains_raw_prompts_and_outputs': any(k in rel(path) for k in ('raw/', 'canonical/', 'experiment-client/'))})
existing['files'] = files
(ART / 'manifest.json').write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print('published', len(files), 'files; calls', len(calls), 'cost', cost)
