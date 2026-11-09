"""Write ADR-1440 documents and manifest results from the saved runs; no model call."""
from common import *
import gzip, tarfile, shutil

criteria, case = read(DES / 'criteria.json'), read(DES / 'case.json')
source = read(DES / 'comparison-source.json')
issues, stops = read(ART / 'preparation-issues.json'), read(ART / 'run-001-stop-and-resume.json')
rel = lambda p: str(Path(p).relative_to(ROOT))
runs = {}
for name in ('run-001', 'run-002', 'run-003'):
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
over = json.load(gzip.open(ART / 'run-003/raw/call-003/response.json.gz', 'rt'))['error']['message']
findings = [
    '세 번 실행 모두 문서 전체 대사를 끝내지 못했다. 모델 호출은 모두 %d번(정상 응답 %d, 거절 1, 결과 불명 1), 보고 비용 %s달러다.'
    % (len(calls), sum(c.get('http_status') == 200 for c in calls), cost),
    'run-001: 다른 세션 테스트로 남은 메모리가 2.44GiB까지 떨어져 자원 보호 장치가 멈췄다(우리 프로세스 0.37GiB, 응답 대기 중 호출 없음).',
    'run-002: run-001 상태를 이어 가려다 HTTP 500. 강제 종료가 하위 조사 기록에 복구용 파일(journal.sqlite-journal)을 남겼고, '
    '이어 가기 코드가 그 기록을 읽기 전용으로 열어 실패했다. 이 실패로 상위 실행이 영구 실패가 됐다.',
    'run-003(처음부터 다시): 묶음 2개 정리 뒤 첫 단위의 외규 조사가 입력 약 878,224토큰으로 모델 한도(262,144)를 넘어 HTTP 400. '
    '단위 원문에 외규 이름이 없을 때 문서 전체에서 나온 외규 이름(자본시장법 시행령·자본시장법·금융투자업규정, 합계 약 180만 자)을 먼저 읽게 한 문서 대사 코드 때문이다. '
    '큰 법령은 목차만 보여 주는 기존 보호 장치도 목차(조·항·호 수천 개) 자체가 커서 막지 못했다.',
    'run-003: 둘째 단위의 외규 조사는 같은 하위 대화 세션을 이어 써서 멀티턴 해석(memory-resolve)으로 들어갔고, Parasail이 HTTP200 뒤 공백 660바이트만 보내 180초에 결과 불명이 됐다.',
    'run-003: 결과 불명 뒤 실행 도구가 전송 중지를 무결성 오류로 올려 문서 대사 전체가 HTTP 500으로 끝났다. 끝낸 묶음도 부분 결과로 남지 않았다.',
    '후속 수정(이 ADR 범위 밖, 수정본에서 시험): 외규 이름이 없으면 일반 RAG 검색, 이름이 있으면 그 법령 안에서만 검색, 단위마다 하위 세션 분리, '
    '결과 불명이면 끝낸 묶음을 부분 결과로 남기고 멈춤. 질문 대사의 큰 법령 목차 문제와 이어 가기 복구 파일 문제는 미수정.']
put(ART / 'summary.json', {'schema_version': 'adr-1440-summary-v1', 'criteria_sha256': sha(DES / 'criteria.json'),
    'success_criteria_met': False, 'runs': {n: {'calls': len(r['calls']), 'cost': r['cost'], 'result': r['result'] and {k: r['result'].get(k) for k in ('http_status', 'status', 'request_seconds', 'physical_calls', 'unknown', 'stage_counts', 'error')}} for n, r in runs.items()},
    'model_calls': len(calls), 'reported_cost_usd': cost, 'context_overflow_message': over, 'stop_and_resume': stops, 'findings': findings})
call_rows = '\n'.join('| %s | %d | %s | %s | %s | %s | %s |' % (c['run'], c['number'], c['stage'], c.get('http_status'), c['status'], c.get('seconds'),
                      (c.get('usage') or {}).get('prompt_tokens')) for c in calls)
finding_lines = '\n'.join('- ' + f for f in findings)
prep = '\n'.join('- %s: %s' % (i['step'], i['issue']) for i in issues)
required_lines = '\n'.join('- ' + x for x in criteria['required'])

q = ADR / '실험' / ('질문-001-%s.md' % CASE)
q.write_text(f'''# 질문 001 — {CASE}

## 1. 실행 메타

- ADR: `ADR-1440`
- experiment: `ADR-1440-experiment-v1`
- case ID: `{CASE}`
- run ID: `run-001`, `run-002`, `run-003`
- 실행 시각: 2026-11-06 21:47~22:31(KST)
- 원본 상태: `exact` — 호출별 요청·응답 원문은 각 run의 `raw/call-NNN/`, 단계별 입력·출력은 `canonical/`
- 제품·중간 호출 모델: `qwen/qwen3.8-27b` (Parasail FP8 우선, 확정 429에만 Near AI FP8, reasoning none, 출력 상한 없음)
- 오프라인 평가 모델: 없음 — 채점 호출 0회
- 실행 arm: `docmode`

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

공개 허용 문서 5개를 원래 구조·원문 그대로 시험용 묶음에 복사했다. 모범규준만 내규로 분류를 바꿨다.

```json
{json.dumps({'generation_id': source['source_manifest']['generation_id'], 'store_sha256': source['source_manifest']['store_sha256'], 'copied_from': source['copied_from']}, ensure_ascii=False)}
```

### 회수·탈락 단계 원장 — run·arm별

회수 단계 원장은 해당 없음이다(stage_ledger mode=not_applicable).

| run | arm | stage | kind | before | +added | -discarded | after | gold before | gold + | gold - | gold after/total | recall | 대표 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| run-001 | docmode | 해당 없음 | 해당 없음 | - | - | - | - | - | - | - | - | - | 원장 미작성 |

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

합계: 물리 호출 {len(calls)}회, 보고 비용 {cost}달러. run-003 호출 3의 거절 메시지: `{over}`

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
| run-001 | docmode | 미완료 | 자원 보호 장치 중단(다른 세션 메모리) | other: resource_stop |
| run-002 | docmode | 미완료 | 이어 가기 HTTP 500(복구용 파일 읽기 전용 열기) | other: resume_hot_journal |
| run-003 | docmode | 미완료 | 외규 조사 입력 한도 초과 HTTP 400, 결과 불명 1, 전체 HTTP 500 | other: external_context_overflow |

- 공통 실패 유형: `other`.
- 사람이 확인한 직접 원인: 문서 전체에서 나온 큰 법령 이름 3개를 단위마다 먼저 읽게 한 문서 대사 코드, 하위 세션 공유, 전송 중지를 무결성 오류로 올린 실행 도구.
- 다음 분기에서 검증할 가설: 이름이 없으면 일반 RAG, 이름이 있으면 그 법령 안에서만 검색, 단위별 세션, 결과 불명이면 부분 결과로 멈추면 문서 전체가 끝난다.
''', 'utf-8')

index = (ADR / '실험/README.md').read_text('utf-8')
def swap(old, new, text):
    assert text.count(old) == 1, old
    return text.replace(old, new)
index = swap('- 이 분기의 변경 가설: TODO', '- 이 분기의 변경 가설: ' + criteria['question'], index)
index = swap('| `baseline` | baseline | ADR-1435-experiment-v1/namedscope | TODO | TODO |', '| `baseline` | baseline | ADR-1435-experiment-v1/namedscope | ADR-1435 질문 대사(참조, 재실행 없음) | 다른 요청 종류 |', index)
index = swap('| `docmode` | candidate | baseline | TODO | TODO |', '| `docmode` | candidate | baseline | 문서 대사 모드(16개 제품 파일) | 선택 프로필, 공개 문서 5개, Qwen3.8 |', index)
index = swap('| 001 | `%s` | `run-001` | TODO | TODO | TODO |' % CASE,
             '| 001 | `%s` | `run-001`~`run-003` | 문서 전체 대사 미완료 3회 | 해당 없음 | other: 자원 중단, 이어 가기 실패, 외규 입력 한도 초과 |' % CASE, index)
index = swap('- run 상태: `run-001 / planned`', '- run 상태: `run-001 / failed`, `run-002 / failed`, `run-003 / failed`', index)
index = swap('- arm별 정답: TODO', '- arm별 정답: docmode 기술 기준 미충족(문서 전체 미완료)', index)
index = swap('- 사전 지정 비교쌍별 신규 정답 / 회귀: TODO', '- 사전 지정 비교쌍별 신규 정답 / 회귀: 해당 없음(비교쌍 없음)', index)
index = swap('- judge 불일치: TODO', '- judge 불일치: 채점 호출 없음', index)
index = swap('| `run-001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |', '| `run-001` | docmode | 해당 없음 | 해당 없음 | - | - | - | - | 원장 미작성 |', index)
(ADR / '실험/README.md').write_text(index, 'utf-8')

readme = (ADR / 'README.md').read_text('utf-8')
head, _ = readme.split('## 2. 문제와 변경 전 구조', 1)
head = swap('TODO: 채택·기각·보류와 운영 배선 변경 여부를 먼저 적는다.',
            f'기각(Rejected). 공개 「금융투자회사의 리스크관리 모범규준」(약 20쪽)을 내규 역할로 둔 문서 대사를 세 번 실행했지만 모두 끝내지 못했다. '
            f'모델 호출 {len(calls)}번, 보고 비용 {cost}달러. 원인은 자원 중단(다른 세션), 이어 가기 복구 파일 문제, 큰 법령을 단위마다 먼저 읽게 한 문서 대사 코드의 입력 한도 초과와 결과 불명이다. '
            '후속 수정은 다른 ADR에서 시험한다. 운영 배선 변경 없음.', head)
text = head + f'''## 2. 문제와 변경 전 구조

ADR-1435까지 대사는 질문 쟁점만 비교했다. 문서 대사 모드(조회 방식 "문서 대사")는 문서 하나를 읽기 묶음으로 나눠 행마다 정리하고, 단위마다 외규를 찾아 비교한다. 모의 테스트 13개와 회귀(새 실패 0)만 통과했고 실제 모델과 큰 문서는 처음이다.

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
| baseline | ADR-1435 namedscope(질문 대사), 재실행 없음 | 다른 요청 종류 | baseline |
| docmode | ADR-1435 사본 + 문서 대사 16개 제품 파일 | 선택 프로필, 공개 문서 5개, Qwen3.8 정책, 시간·호출 한도 없음 | candidate |

- 시험용 묶음: 공개 허용 문서 5개(모범규준, 자본시장법, 시행령, 금융투자업규정, 영업 및 업무에 관한 규정)의 원래 구조·원문 복사. 모범규준만 내규로 분류.
- run-002는 run-001 상태 이어 가기, run-003은 같은 요청을 새 세션에서 처음부터 다시(실행 도구 수정 후).

### 다른 ADR과의 관계

- 관련 ADR: 없음

- experiment 계보와 직접 부모 arm: [실험 manifest](실험/manifest.json)

## 5. 데이터·모델·재현성

- 데이터셋과 버전: 시험용 묶음 세대 `{source['source_manifest']['generation_id']}`.
- frozen source와 SHA-256: `{rel(DES / 'comparison-source.json')}` `{sha(DES / 'comparison-source.json')}`; 동결 목록 `{rel(DES / 'freeze.json')}`(재동결 이력 포함).
- 제품/중간/채점 모델: `qwen/qwen3.8-27b`. 채점 호출 없음.
- 반복 수와 다수결: 요청 1건(실행 3회는 중단 뒤 다시 시도).
- 법령·기준답변 버전 점검: 해당 없음.

## 6. 결과

| arm | 정답/전체 | 정확도 | baseline 대비 | 입력 토큰 | p50/p95 |
|---|---:|---:|---:|---:|---:|
| baseline | 참조 | - | - | - | - |
| docmode | 미완료 3/3 | - | - | {sum(r['tokens_in'] for r in runs.values())} | 호출 {len(calls)}건 |

| paired outcome | 건수 | 비율 |
|---|---:|---:|
| 비교 arm만 정답 | 해당 없음 | - |
| 기준 arm만 정답(회귀) | 해당 없음 | - |
| 둘 다 정답 | 해당 없음 | - |
| 둘 다 오답 | 해당 없음 | - |

호출 표:

| run | 호출 | 단계 | HTTP | 상태 | 초 | 입력 토큰 |
|---|---:|---|---:|---|---:|---:|
{call_rows}

관찰:

{finding_lines}

## 7. 사례별 오류 분석

| 실패 유형 | 건수/분모 | 대표 질문 | 해석 |
|---|---:|---|---|
| other: resource_stop | 1 / 3 실행 | {CASE} | 다른 세션 테스트가 메모리를 써서 보호 장치가 멈춤 |
| other: resume_hot_journal | 1 / 3 실행 | {CASE} | 강제 종료가 남긴 복구용 파일 때문에 이어 가기 실패, 상위 실행 영구 실패 |
| other: external_context_overflow | 1 / 3 실행 | {CASE} | 단위마다 큰 법령 3개를 먼저 읽게 해 입력 한도 초과, 하위 세션 공유, 결과 불명 뒤 전체 실패 |

질문별 실제 입출력은 [실험 인덱스](실험/README.md)에 연결한다.

## 8. 비용·지연·회수 규모

| 항목 | 값 | 측정 단위·분모 |
|---|---:|---|
| 전체 corpus | 5문서 33,090문단 | 시험용 묶음 |
| 필터 전/후 후보 | 측정 안 함 | 제품 하위 조사 그대로 |
| LLM 제시 수 | 측정 안 함 | - |
| golden recall | 해당 없음 | 기준 좌표 없음 |
| 제시 비율 | 해당 없음 | - |
| LLM 호출·토큰·지연 | {len(calls)}회 · 입력 {sum(r['tokens_in'] for r in runs.values())} · 출력 {sum(r['tokens_out'] for r in runs.values())} | {cost}달러 |

회수 점수는 측정하지 않았다. 단계 원장은 해당 없음(`stage_ledger.mode=not_applicable`).

### 단계별 회수·탈락 원장

| run | arm | stage | kind | 후보 before→after | added / discarded | gold before→after | gold gain / loss | recall | 주요 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| run-001 | docmode | 해당 없음 | 해당 없음 | - | - | - | - | - | 원장 미작성 |

## 9. 해석

- 사실: 문서 확정, 읽기 묶음 32개·654행 나누기, 묶음 행 정리 2회는 실제 모델로 동작했다.
- 사실: 외규 조사는 단위 원문에 이름이 없을 때 문서 전체의 큰 법령 3개를 먼저 읽게 한 코드 때문에 입력 한도를 넘었다.
- 사실: 하위 조사 세션을 단위끼리 공유해 둘째 단위가 멀티턴 해석으로 들어갔다.
- 추론: 일반 RAG 검색으로 바꾸고 세션을 나누면 외규 조사가 진행될 것이다(후속 ADR에서 시험).

## 10. 한계와 일반화 가능 범위

- 요청 1건, 공개 문서(내규 대체), 인샘플. 끝까지 간 실행이 없어 시간·비용·판정 품질은 모른다.

## 11. 운영 결정·롤백 조건

- 메인 배선 변경 없음. 수정은 `09_ARTIFACTS/AUDITS/20261106-document-compare/code`에서 하고 다른 ADR로 시험한다.
- 질문 대사의 큰 법령 목차 문제, 이어 가기 복구 파일 문제, 프로세스가 죽은 실행의 채팅 "계속"은 미수정.

## 12. 재현 명령

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1440/setup.py
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1440/live.py --scripted
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1440/live.py            # run-001
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1440/live.py --resume   # run-002
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1440/live.py --fresh    # run-003
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1440/publish.py
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
    'by_arm': {'baseline': {'status': 'reference', 'correct': None, 'total': None, 'accuracy': None, 'decision_eligible': False,
                            'scope': 'ADR-1435 question comparison; not re-executed'},
               'docmode': {'status': 'complete', 'correct': 0, 'total': 1, 'accuracy': None, 'decision_eligible': False,
                           'scope': 'whole-document comparison finished / requested; three attempts, none finished'}},
    'comparisons': [], 'judge_disagreements': 0,
    'usage': {'physical_requests': len(calls), 'offline_evaluator_requests': 0, 'input_tokens': sum(r['tokens_in'] for r in runs.values()),
              'output_tokens': sum(r['tokens_out'] for r in runs.values()), 'reported_cost_usd': cost, 'unknown': 1},
    'latency': {'per_call_seconds': [c.get('seconds') for c in calls]},
    'error_taxonomy': [{'type': 'other: resource_stop', 'run': 'run-001'}, {'type': 'other: resume_hot_journal', 'run': 'run-002'},
                       {'type': 'other: external_context_overflow', 'run': 'run-003'}],
    'frozen_criteria': {'required': criteria['required'], 'success_criteria_met': False}}
manifest['runs'][0].update(status='failed', sha256=sha(ART / 'summary.json'), artifact_path=rel(ART / 'summary.json'), success_criteria_met=False)
for name, parent in (('run-002', 'run-001'), ('run-003', 'run-001')):
    if not any(r['id'] == name for r in manifest['runs']):
        manifest['runs'].append({'id': name, 'purpose': 'repeat', 'parent_run_id': parent, 'arm_ids': ['docmode'],
                                 'selection_rule': manifest['runs'][0]['selection_rule'], 'status': 'failed',
                                 'artifact_path': rel(ART / name / 'result.json'), 'sha256': sha(ART / name / 'result.json')})
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
