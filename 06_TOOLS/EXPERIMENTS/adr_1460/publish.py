"""Write ADR-1460 documents and manifest results from the saved runs; no model call."""
from common import *
import gzip, tarfile, shutil, statistics

criteria, case = read(DES / 'criteria.json'), read(DES / 'case.json')
source = read(DES / 'comparison-source.json')
analysis, interruption = read(ART / 'analysis.json'), read(ART / 'interruption-run-001.json')
diagnosis = read(ART / 'deferred-diagnosis.json')
rel = lambda p: str(Path(p).relative_to(ROOT))
calls = read(ART / 'run-001/calls.json')
resume = read(ART / 'run-003/result.json')
usage = [c.get('usage') or {} for c in calls]
cost = round(sum(u.get('cost') or 0 for u in usage), 8)
tokens_in, tokens_out = sum(u.get('prompt_tokens') or 0 for u in usage), sum(u.get('completion_tokens') or 0 for u in usage)
seconds = sorted(c['seconds'] for c in calls if c.get('status') == 'responded' and 'seconds' in c)
p50, p95 = round(statistics.median(seconds), 2), round(seconds[int(len(seconds) * 0.95)], 2)
stage = {}
for c in calls:
    key = 'child' if (c.get('stage') or '').startswith('source-') else c.get('stage')
    stage[key] = stage.get(key, 0) + 1
http = {}
for c in calls:
    http[str(c.get('http_status'))] = http.get(str(c.get('http_status')), 0) + 1
overflow = sum(1 for c in calls if c.get('http_status') == 400)

# Archive the runtime folders (all hashes verified before removal); analysis.json already holds the measured values.
for folder in (ART / 'run-001', ART / 'preflight/resume-dry-2', ART / 'preflight/scripted'):
    if not (folder / 'runtime').exists():
        continue
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
        'members': len(members), 'restore': 'tar -xzf runtime.tar.gz -C <' + rel(folder) + '>', 'verified_every_member_before_removal': True,
        'files': members})
    shutil.rmtree(folder / 'runtime')

shared = analysis['shared_groups']
cand, base = shared['candidate'], shared['baseline']
met = {
    'http_200_selected': 'not measured: run-001 was killed by another session before its response (groups saved in state)',
    'primary_open_share_le_0.70': cand['open_share'] <= 0.70,
    'more_substantive_than_baseline': cand['substantive'] > base['substantive'],
    'both_sides_cited': analysis['substantive_with_both_sides'][0] == analysis['substantive_with_both_sides'][1],
    'no_question_definitions': analysis['children']['definition_targets'] == 0,
    'no_context_bound_stop': True,
    'duplicate_adds_zero_calls': 'not measured: no completed response to repeat',
    'frozen_hashes_unchanged': read(ART / 'run-003/resource-final.json')['candidate_unchanged']}
kinds = {}
for r in diagnosis:
    if r['verdict'] == 'DEFERRED':
        kinds[r['kind']] = kinds.get(r['kind'], 0) + 1
general = sum(r['general_risk_presented'] for r in diagnosis)
findings = [
    '같은 15개 읽기 묶음에서 판정 보류: ADR-1447 %d/%d(%.1f%%) → 이번 %d/%d(%.1f%%). 실질 판정 %d → %d건(부합 %d·내부 추가기준 %d·상충 %d). '
    '사전 성공 기준(70%% 이하)은 충족하지 못했다.' % (base['open'], base['units'], 100 * base['open_share'], cand['open'], cand['units'], 100 * cand['open_share'],
                                       base['substantive'], cand['substantive'], cand['verdicts'].get('CONFORMS', 0),
                                       cand['verdicts'].get('ADDITIONAL_INTERNAL', 0), cand['verdicts'].get('CONFLICT', 0)),
    '실질 판정 %d건 모두 내규·외규 원문을 함께 인용했다.' % analysis['substantive_with_both_sides'][1],
    '하위 조사 %d개 모두 question_definitions=false, 질문 속 용어의 정의 자동 확보 0건(ADR-1447: 하위 조사 %d개에서 %d건).'
    % (analysis['children']['count'], analysis['children']['baseline_count'], analysis['children']['baseline_definition_targets']),
    '하위 조사의 외규 읽기 중 단위와 같은 조문 번호: %d/%d건(ADR-1447: %d/%d건).'
    % (analysis['number_chasing']['candidate']['same_number_as_unit'], analysis['number_chasing']['candidate']['external_reads'],
       analysis['number_chasing']['baseline']['same_number_as_unit'], analysis['number_chasing']['baseline']['external_reads']),
    '비교 호출 %d건 모두 이웃 단위 조문이 들어갔고, %d단위가 이웃 단위 조문을 실제 인용했다. 비교 입력 중앙값 %d자·최대 %d자(한도 80,000자).'
    % (analysis['compare_inputs']['calls'], analysis['units_citing_a_nearby_article'], analysis['compare_inputs']['median_chars'], analysis['compare_inputs']['max_chars']),
    '보류 이유(문장 분류): 넣어 준 외규에 대응 조항 없음 %d, 외규는 일반 규정뿐 %d, 다른 업종·범위 %d, 모범규준 자체 사항 %d, 기타 %d. '
    '금융투자업규정 일반 위험관리 조문(제3-42~44·3-64조)이 비교 입력에 든 호출은 %d/%d건뿐이고, 들어간 경우에도 "외규는 위험관리 일반, 내규는 유동성리스크 구체"로 보류한 사례가 있다.'
    % (kinds.get('no_matching_provision_shown', 0), kinds.get('external_only_general', 0), kinds.get('different_business_or_scope', 0),
       kinds.get('self_regulatory_no_legal_counterpart', 0), kinds.get('other', 0), general, len(diagnosis)),
    'run-001은 15/32 묶음을 끝낸 뒤 17:02(KST)에 다른 세션(ADR-1459 작업)이 PID를 자기 남은 프로세스로 오인해 SIGTERM으로 종료했다. '
    '그 순간의 433번 호출은 결과 불명이며 다시 보내지 않았다. 자원 보호 장치 중단은 아니다.',
    '이어 가기(run-003, 제품 resume API)는 모델 호출 0회로 HTTP 500: "abandoned request is not the current workflow child". '
    '중단된 하위 조사 복구 검사가 세션 이름을 workflow:<실행>:<쪽>으로만 보는데 문서 대사는 단위 키를 붙인다(MAIN173부터의 제품 결함, 이번 수정과 무관). '
    '이 실패로 run-001 실행이 실패 상태가 돼 "계속"도 쓸 수 없어, 사전에 정한 계속 실행은 하지 않았다.',
    '하위 조사 %d건이 모델 입력 한도(262,144토큰) 초과로 거절됐다(큰 법령 목차가 입력에 들어가는 기존 문제).' % overflow,
    'run-001: 물리 호출 %d(응답 %d, 결과 불명 1), 묶음 정리 %d·하위 조사 %d·단위 비교 %d, 입력 %d·출력 %d토큰, 보고 비용 %s달러, 약 42분(15묶음). '
    'ADR-1447 run-001은 14묶음에 448호출·$2.88·52분.' % (len(calls), sum(c['status'] == 'responded' for c in calls), stage.get('workflow-group_read', 0),
                                                 stage.get('child', 0), stage.get('workflow-unit_compare', 0), tokens_in, tokens_out, cost)]
put(ART / 'summary.json', {'schema_version': 'adr-1460-summary-v1', 'criteria_sha256': sha(DES / 'criteria.json'),
    'success_criteria': met, 'success_criteria_met': False, 'shared_groups': shared, 'all_groups': {'candidate': analysis['candidate_all'], 'baseline': analysis['baseline_all']},
    'deferred_reason_kinds': kinds, 'general_risk_article_presented': [general, len(diagnosis)],
    'run_001': {'calls': len(calls), 'http': http, 'stage': stage, 'tokens_in': tokens_in, 'tokens_out': tokens_out, 'reported_cost_usd': cost,
                'p50_seconds': p50, 'p95_seconds': p95, 'interruption': interruption},
    'run_003_resume': {k: resume.get(k) for k in ('http_status', 'mode', 'request_seconds', 'physical_calls', 'error')},
    'findings': findings})
finding_lines = '\n'.join('- ' + f for f in findings)
required_lines = '\n'.join('- ' + x for x in criteria['required'])
met_lines = '\n'.join('- %s: %s' % (k, v) for k, v in met.items())
group_rows = '\n'.join('| %s | %s | %s |' % (g['group_id'][:12], json.dumps(g['baseline'], ensure_ascii=False), json.dumps(g['candidate'], ensure_ascii=False))
                       for g in analysis['by_shared_group'])
sample_rows = '\n'.join('| %s | %s | %s | %s |' % (s['label'], s['verdict'], (s['external'][0] if s['external'] else '')[:80].replace('|', '/').replace('\n', ' '),
                                                  (s['reason'] or '')[:120].replace('|', '/').replace('\n', ' ')) for s in analysis['samples'])
deferred_rows = '\n'.join('| %s | %s | %s |' % (r['label'], r['kind'], (r['reason'] or '')[:140].replace('|', '/').replace('\n', ' '))
                          for r in diagnosis if r['verdict'] == 'DEFERRED')

q = ADR / '실험' / ('질문-001-%s.md' % CASE)
q.write_text(f'''# 질문 001 — {CASE}

## 1. 실행 메타

- ADR: `ADR-1460`
- experiment: `ADR-1460-experiment-v1`
- case ID: `{CASE}`
- run ID: `run-001`(15/32 묶음 뒤 외부 종료), `run-003`(이어 가기, HTTP 500, 모델 호출 0)
- 실행 시각: 2026-11-08 16:20~17:02(KST) run-001, 17:21(KST) run-003
- 원본 상태: `exact` — 호출별 요청·응답 원문은 `artifacts/run-001/raw/call-NNN/`, 단계별 입력·출력은 `artifacts/run-001/canonical/`
- 제품·중간 호출 모델: `qwen/qwen3.8-27b` (Parasail FP8, 확정 429에만 Near AI FP8, reasoning none, 출력 상한 없음)
- 오프라인 평가 모델: 없음 — 채점 호출 0회
- 실행 arm: `extfix` (baseline은 ADR-1447 저장 상태 참조)

## 2. 사용자 질문 원문

```text
{case['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

기준답변 없음. 같은 읽기 묶음의 판정 분포를 ADR-1447 저장 상태와 비교한다.

```text
해당 없음
```

## 4. 제품 입력을 구성한 원값

### 회수 전 전체·후보·제시 규모

```json
{json.dumps({'corpus': [{k: d[k] for k in ('name', 'category', 'blocks', 'chars')} for d in source['documents']], 'retrieval': '제품 하위 조사 그대로(로컬 SQLite·키워드 첫 검색), 회수율 미측정', 'compare_inputs': analysis['compare_inputs']}, ensure_ascii=False)}
```

### 회수 좌표·조문·정의·Wiki·관계 — 전체

ADR-1440 시험용 묶음(공개 허용 문서 5개, 모범규준만 내규 분류)을 해시로 재사용했다.

```json
{json.dumps({'generation_id': source['source_manifest']['generation_id'], 'store_sha256': source['source_manifest']['store_sha256']}, ensure_ascii=False)}
```

### 회수·탈락 단계 원장 — run·arm별

회수 단계 원장은 해당 없음이다(stage_ledger mode=not_applicable).

| run | arm | stage | kind | before | +added | -discarded | after | gold before | gold + | gold - | gold after/total | recall | 대표 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| run-001 | extfix | 해당 없음 | 해당 없음 | - | - | - | - | - | - | - | - | - | 원장 미작성 |

```json
{json.dumps({'stage_ledger_artifact': None, 'discarded_gold_and_reasons': '해당 없음', 'gold_visible_to_product': False}, ensure_ascii=False)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

### run-001 / extfix / system

호출마다 system이 다르다. 원문은 `artifacts/run-001/raw/call-NNN/request.json.gz`에 있다.

### run-001 / extfix / user

`artifacts/run-001/raw/call-001/request.json.gz`(묶음 행 정리)부터 433번까지.

### run-001 / extfix / schema·tool

`artifacts/run-001/canonical/NNN.json.gz`의 `schema`.

### run-001 / extfix / provider 원응답·structured output·usage·지연

물리 호출 {len(calls)}회(HTTP {json.dumps(http)}), 단계 {json.dumps(stage, ensure_ascii=False)}, 입력 {tokens_in}·출력 {tokens_out}토큰, 보고 비용 {cost}달러, 응답 호출 p50 {p50}초·p95 {p95}초. 호출별 원장은 `artifacts/run-001/calls.json`.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

하위 조사의 해석·감독·보완 호출은 run-001 호출 원장에 단계 이름으로 들어 있다. 채점 호출 없음.

```json
{json.dumps({'generations': 'artifacts/run-001/generations.json'}, ensure_ascii=False)}
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

| run | arm | 결과 | 핵심 근거 | 실패 유형 |
|---|---|---|---|---|
| run-001 | extfix | 같은 15묶음 판정 보류 {cand['open']}/{cand['units']} (ADR-1447 {base['open']}/{base['units']}) | 사전 기준 70% 이하 미충족, 실질 판정 {base['substantive']}→{cand['substantive']} | retrieval_miss(대응 외규 미제시) |
| run-001 | extfix | 15/32 묶음 뒤 종료 | 다른 세션의 SIGTERM | other: external_kill |
| run-003 | extfix | HTTP 500, 모델 호출 0 | 문서 대사 하위 조사 복구 검사의 세션 이름 불일치 | other: resume_child_session_key |

같은 묶음 판정 분포:

| 묶음 | ADR-1447 | ADR-1460 |
|---|---|---|
{group_rows}

보류 단위와 이유(이번 실행):

| 단위 | 분류 | 이유 |
|---|---|---|
{deferred_rows}

실질 판정 표본:

| 단위 | 판정 | 외규 인용 | 이유 |
|---|---|---|---|
{sample_rows}
''', 'utf-8')

def swap(old, new, text):
    assert text.count(old) == 1, old
    return text.replace(old, new)

index = (ADR / '실험/README.md').read_text('utf-8')
index = swap('- 이 분기의 변경 가설: TODO', '- 이 분기의 변경 가설: ' + criteria['question'], index)
index = swap('| `baseline` | baseline | ROOT | TODO | TODO |', '| `baseline` | baseline | ROOT | ADR-1447 maindoc 저장 상태(참조, 재실행 없음) | 같은 묶음·질문·문서 |', index)
index = swap('| `extfix` | candidate | baseline | TODO | TODO |', '| `extfix` | candidate | baseline | 외규 조사 수정 6파일(stage r3) | 선택 프로필, 공개 문서 5개, Qwen3.8, 로컬 SQLite |', index)
index = swap('| 001 | `%s` | `run-001` | TODO | TODO | TODO |' % CASE,
             '| 001 | `%s` | `run-001`, `run-003` | 같은 15묶음 보류 %d/%d→%d/%d, 기준 미충족 | 해당 없음 | retrieval_miss, other: external_kill, resume_child_session_key |'
             % (CASE, base['open'], base['units'], cand['open'], cand['units']), index)
index = swap('- run 상태: `run-001 / planned`', '- run 상태: `run-001 / failed`(15/32 묶음 뒤 외부 종료), `run-003 / failed`(이어 가기 HTTP 500)', index)
index = swap('- arm별 정답: TODO', '- arm별 정답: 해당 없음(판정 분포 비교). 같은 15묶음 보류 비율 %.1f%% → %.1f%%' % (100 * base['open_share'], 100 * cand['open_share']), index)
index = swap('- 사전 지정 비교쌍별 신규 정답 / 회귀: TODO', '- 사전 지정 비교쌍별 신규 정답 / 회귀: 단위 경계가 실행마다 달라 단위 대응 비교 없음', index)
index = swap('- judge 불일치: TODO', '- judge 불일치: 채점 호출 없음', index)
index = swap('| `run-001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |', '| `run-001` | extfix | 해당 없음 | 해당 없음 | - | - | - | - | 원장 미작성 |', index)
(ADR / '실험/README.md').write_text(index, 'utf-8')

readme = (ADR / 'README.md').read_text('utf-8')
head, _ = readme.split('## 2. 문제와 변경 전 구조', 1)
head = swap('TODO: 채택·기각·보류와 운영 배선 변경 여부를 먼저 적는다.',
            f'기각(Rejected). 외규 조사 수정본으로 같은 공개 모범규준 문서 대사를 실제 Qwen으로 실행했다. 다른 세션이 실행을 15/32 묶음에서 종료해 문서 전체는 끝내지 못했다. '
            f'같은 15묶음에서 판정 보류는 ADR-1447 {base["open"]}/{base["units"]}({100 * base["open_share"]:.1f}%) → {cand["open"]}/{cand["units"]}({100 * cand["open_share"]:.1f}%), '
            f'실질 판정은 {base["substantive"]} → {cand["substantive"]}건으로 개선됐지만 사전 성공 기준(70% 이하)은 충족하지 못했다. '
            '정의 자동 확보 0건, 같은 번호 조문 쫓기 0건, 양쪽 인용 100%는 확인했다. 남은 보류의 주원인은 하위 조사가 대응 외규 조문을 찾지 못하는 것이다. 운영 배선 변경 없음.', head)
text = head + f'''## 2. 문제와 변경 전 구조

ADR-1447(MAIN173 코드)은 같은 문서에서 단위 비교 142건 중 127건을 판정 보류했다. 원인 분석(`09_ARTIFACTS/AUDITS/20261108-document-compare-deferred/결과.txt`):
외규 첫 검색어가 번호 붙은 단위 이름, 질문에 넣은 내규 원문 속 용어의 정의 조문 자동 확보, 외규가 1~2문장 조각으로 전달, 같은 장 단위끼리 외규를 나누지 못함.
수정(`09_ARTIFACTS/AUDITS/20261108-document-compare-external-fix/결과.txt`): 번호 뺀 검색어와 과제 문장, `question_definitions=false`, 조 전체 비교(4,000자 이하), 묶음 안 이웃 조문 공유(16,000자).

## 3. 가설과 사전 판정 기준

### 가설

{criteria['question']}

### 성공 기준

{required_lines}

### 반증 기준

- 같은 묶음 판정 보류 비율 > 0.70
- HTTP 500 또는 워크플로우 실패, 비교 입력 한도 중단, 제품이 보고한 원문·권한·해시 불일치.
- 멈춤 규칙: {criteria['stop']}

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | ADR-1447 maindoc(MAIN173) 저장 상태, 재실행 없음 | 같은 묶음·질문·문서·프로필·모델 정책 | baseline |
| extfix | stage r3 = MAIN178 + 외규 조사 수정 6파일 | 선택 프로필(감독 enforce), 공개 문서 5개, Qwen3.8, 로컬 SQLite·키워드 첫 검색 | candidate |

- 사용자 지시: 기본 설정은 Oracle + 벡터지만 이 시험은 SQL(로컬 SQLite)로 해도 된다.
- 읽기 묶음은 코드가 같아 두 실행의 group_id가 같다. 단위 경계는 실행마다 모델이 다시 정하므로 묶음 단위로 비교한다.

### 다른 ADR과의 관계

- `informed_by` → `ADR-1447`: 판정 보류 90%의 기준 실행(같은 공개 묶음·질문, MAIN173 코드)

- experiment 계보와 직접 부모 arm: [실험 manifest](실험/manifest.json)

## 5. 데이터·모델·재현성

- 데이터셋과 버전: 시험용 묶음 세대 `{source['source_manifest']['generation_id']}`(ADR-1440·1443·1447과 같음).
- frozen source와 SHA-256: `{rel(DES / 'comparison-source.json')}` `{sha(DES / 'comparison-source.json')}`; 동결 목록 `{rel(DES / 'freeze.json')}`.
- 제품/중간/채점 모델: `qwen/qwen3.8-27b`. 채점 호출 없음.
- 반복 수와 다수결: 요청 1건(외부 종료 뒤 이어 가기 1회 실패).
- 법령·기준답변 버전 점검: 해당 없음.

## 6. 결과

| arm | 정답/전체 | 정확도 | baseline 대비 | 입력 토큰 | p50/p95 |
|---|---:|---:|---:|---:|---:|
| baseline | 같은 15묶음 보류 {base['open']}/{base['units']} | 실질 {base['substantive']} | - | ADR-1447 기록 | - |
| extfix | 같은 15묶음 보류 {cand['open']}/{cand['units']} | 실질 {cand['substantive']} | 보류 {100 * cand['open_share']:.1f}% vs {100 * base['open_share']:.1f}% | {tokens_in} | {p50}/{p95}초 |

| paired outcome | 건수 | 비율 |
|---|---:|---:|
| 비교 arm만 정답 | 해당 없음(단위 경계 다름) | - |
| 기준 arm만 정답(회귀) | 해당 없음 | - |
| 둘 다 정답 | 해당 없음 | - |
| 둘 다 오답 | 해당 없음 | - |

사전 기준별:

{met_lines}

관찰:

{finding_lines}

## 7. 사례별 오류 분석

| 실패 유형 | 건수/분모 | 대표 질문 | 해석 |
|---|---:|---|---|
| retrieval_miss | {kinds.get('no_matching_provision_shown', 0)} / {cand['open']} 보류 | {CASE} | 하위 조사가 대응 외규 조문을 비교 입력까지 가져오지 못함(내규 "리스크"↔외규 "위험" 표현 차이 포함) |
| other: external_only_general | {kinds.get('external_only_general', 0)} / {cand['open']} 보류 | {CASE} | 외규는 일반 규정, 내규는 구체 규정 — 판정 표기 기준 문제 |
| scope_actor_mismatch | {kinds.get('different_business_or_scope', 0)} / {cand['open']} 보류 | {CASE} | 다른 업종·범위 조문만 제시 |
| other: external_kill | 1 / 2 실행 | {CASE} | 다른 세션이 PID를 오인해 종료 |
| other: resume_child_session_key | 1 / 2 실행 | {CASE} | 문서 대사 하위 조사 세션 키 때문에 이어 가기 복구 검사 실패 |

질문별 실제 입출력은 [실험 인덱스](실험/README.md)에 연결한다.

## 8. 비용·지연·회수 규모

| 항목 | 값 | 측정 단위·분모 |
|---|---:|---|
| 전체 corpus | 5문서 33,090문단 | 시험용 묶음 |
| 필터 전/후 후보 | 측정 안 함 | 제품 하위 조사 그대로 |
| LLM 제시 수 | 비교 입력 중앙값 {analysis['compare_inputs']['median_chars']}자·최대 {analysis['compare_inputs']['max_chars']}자 | 단위 비교 {analysis['compare_inputs']['calls']}건 |
| golden recall | 해당 없음 | 기준 좌표 없음 |
| 제시 비율 | 해당 없음 | - |
| LLM 호출·토큰·지연 | {len(calls)}회 · 입력 {tokens_in} · 출력 {tokens_out} · p50 {p50}초/p95 {p95}초 | {cost}달러, 약 42분(15묶음) |

회수 점수는 측정하지 않았다. 단계 원장은 해당 없음(`stage_ledger.mode=not_applicable`).

### 단계별 회수·탈락 원장

| run | arm | stage | kind | 후보 before→after | added / discarded | gold before→after | gold gain / loss | recall | 주요 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| run-001 | extfix | 해당 없음 | 해당 없음 | - | - | - | - | - | 원장 미작성 |

## 9. 해석

- 사실: 정의 자동 확보와 같은 번호 조문 쫓기는 수정대로 사라졌다(0건).
- 사실: 같은 묶음의 보류 비율은 91.0%에서 82.8%로 줄고 실질 판정은 9건에서 16건으로 늘었다.
- 사실: 남은 보류의 대부분은 비교 입력에 대응 외규 조문이 없다는 이유이고, 실제로 넣어 준 조문 다수가 다른 업종·별표 조문이었다.
- 추론: 다음 병목은 하위 조사의 외규 검색(표현 차이, 낱말 OR 순위)이다. 조 전체·이웃 공유는 찾은 조문이 맞을 때만 효과가 있다.
- 추론: 외규가 일반 규정이고 내규가 구체 규정인 경우의 판정 표기(보류 대신 내부 추가기준 등)는 사용자와 정할 기준이다.

## 10. 한계와 일반화 가능 범위

- 요청 1건, 32묶음 중 15묶음, 공개 문서(내규 대체), 인샘플(ADR-1447 기록을 보고 수정). 판정의 법률 타당성은 채점하지 않았다.
- 로컬 SQLite·키워드 첫 검색이며 기본 설정(Oracle + 벡터)과 다르다.
- 같은 요청 재전송·문서 전체 완료는 측정하지 못했다.

## 11. 운영 결정·롤백 조건

- 메인 배선 변경 없음. 수정은 작업 코드에만 있다.
- 제품 결함 발견: 문서 대사 하위 조사 도중 프로세스가 죽으면 이어 가기가 "abandoned request is not the current workflow child"로 실패하고 실행이 실패 상태가 돼 "계속"도 막힌다(`workflow_execution.recover_abandoned_request`의 세션 이름 검사). 미수정.

## 12. 재현 명령

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1460/setup.py
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1460/live.py --scripted
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1460/live.py --preflight
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1460/live.py            # run-001
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1460/live.py --resume   # run-003 (번호 2는 점검용 resume-dry-2)
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1460/analyze.py
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1460/diagnose_deferred.py
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1460/publish.py
```

- 외부 종료 기록: `{rel(ART / 'interruption-run-001.json')}`; 재개 순서 기록: `{rel(ART / 'chain/chain.log')}`.
- 원시 산출물: [artifacts/manifest.json](artifacts/manifest.json)
- 질문 파일 hash: [실험/manifest.json](실험/manifest.json)
'''
(ADR / 'README.md').write_text(text.replace('status: Proposed', 'status: Rejected', 1), 'utf-8')

manifest = read(ADR / '실험/manifest.json')
manifest['results'] = {
    'status': 'complete',
    'by_arm': {'baseline': {'status': 'reference', 'correct': None, 'total': None, 'accuracy': None, 'decision_eligible': False,
                            'scope': 'ADR-1447 maindoc saved state; not re-executed'},
               'extfix': {'status': 'complete', 'correct': cand['substantive'], 'total': cand['units'], 'accuracy': round(1 - cand['open_share'], 4),
                          'decision_eligible': False,
                          'scope': 'substantive verdicts / units in the 15 reading groups finished by both runs (ADR-1447: %d/%d)' % (base['substantive'], base['units'])}},
    'comparisons': [], 'judge_disagreements': 0,
    'usage': {'physical_requests': len(calls), 'offline_evaluator_requests': 0, 'input_tokens': tokens_in, 'output_tokens': tokens_out,
              'reported_cost_usd': cost, 'unknown': 1, 'p50_seconds': p50, 'p95_seconds': p95},
    'latency': {'per_call_seconds': [c.get('seconds') for c in calls]},
    'error_taxonomy': [{'type': 'retrieval_miss', 'count': kinds.get('no_matching_provision_shown', 0), 'denominator': cand['open']},
                       {'type': 'other: external_kill', 'run': 'run-001'}, {'type': 'other: resume_child_session_key', 'run': 'run-003'}],
    'frozen_criteria': {'required': criteria['required'], 'success_criteria_met': False, 'per_criterion': met}}
manifest['runs'][0].update(status='failed', sha256=sha(ART / 'summary.json'), artifact_path=rel(ART / 'summary.json'), success_criteria_met=False)
if not any(r['id'] == 'run-003' for r in manifest['runs']):
    manifest['runs'].append({'id': 'run-003', 'purpose': 'repeat', 'parent_run_id': 'run-001', 'arm_ids': ['extfix'],
                             'selection_rule': 'Resume of run-001 after an external SIGTERM (deviation from the frozen stop rule; see interruption-run-001.json)',
                             'status': 'failed', 'artifact_path': rel(ART / 'run-003/result.json'), 'sha256': sha(ART / 'run-003/result.json')})
manifest['questions'][0]['sha256'] = sha(q)
(ADR / '실험/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')
existing = read(ART / 'manifest.json')
files = []
for path in sorted(p for p in ART.rglob('*') if p.is_file() and p != ART / 'manifest.json'):
    files.append({'path': rel(path), 'sha256': sha(path), 'bytes': path.stat().st_size, 'description': '준비·실행·분석 기록',
                  'contains_raw_prompts_and_outputs': any(k in rel(path) for k in ('raw/', 'canonical/', 'experiment-client/', 'runtime.tar.gz'))})
existing['files'] = files
(ART / 'manifest.json').write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print('published', len(files), 'files; calls', len(calls), 'cost', cost)
