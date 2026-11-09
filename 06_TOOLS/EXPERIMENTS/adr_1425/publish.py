"""Write the ADR-1425 documents and manifest results from the saved result files; no model call."""
from common import *
import json, tarfile

result, groups = read(RUN / 'result.json'), read(RUN / 'groups.json')
criteria, plan, stop = read(DES / 'criteria.json'), read(DES / 'plan.json'), read(RUN / 'resource-stop.json')
batch = read(next(RUN.glob('batch-stopped-*.json')))
auth = read(DES / 'authorization.json')
archive = read(RUN / 'calls-archive-receipt.json')
review = modules('rows15')[1]
tar = tarfile.open(RUN / 'calls.tar.gz')
GIB = 1024 ** 3


def saved(folder, name):
    return json.loads(tar.extractfile(folder + '/' + name).read())


def executed(case, arm):
    return [g for g in groups if g['case'] == case and g['arm'] == arm and g['final'] != 'NOT_RUN']


def line(case, arm):
    row, done = result['by_case_arm'][case][arm], executed(case, arm)
    first = sum(g['attempts'][0]['status'] == 'COMPLETE' for g in done)
    return row, done, first


ARM_LABEL = {'baseline': '30행(기본)', 'rows15': '15행', 'rows60': '60행'}
rel = lambda p: str(Path(p).relative_to(ROOT))

# ---- question files ---------------------------------------------------------
def question(number, case):
    did, name = CASES[case], auth['documents'][case]['name']
    done_any = any(executed(case, arm) for arm in ARMS)
    totals = plan[case]['baseline']['totals']
    out = ['# 질문 %03d — %s' % (number, case), '', '## 1. 실행 메타', '',
           '- ADR: `ADR-1425`', '- experiment: `ADR-1425-experiment-v1`', '- case ID: `%s`' % case, '- run ID: `run-001`',
           '- 실행 시각: ' + ('%s ~ %s (UTC, 배치 전체)' % (result['started_at'], result['ended_at']) if done_any else '미실행 — 자원 보호 중단으로 이 문서의 묶음은 한 건도 보내지 않음'),
           '- 원본 상태: ' + ('`exact` — 보낸 요청과 받은 응답 원문을 호출별로 저장(인증 헤더 제외), `artifacts/run-001/calls.tar.gz`' if done_any else '`unavailable` — 호출 없음'),
           '- 제품·중간 호출 모델: `qwen/qwen3.8-27b` (Parasail FP8, reasoning none, 출력 상한 없음)',
           '- 오프라인 평가 모델: 없음 — 채점 호출 0회', '- 실행 arm: `baseline`, `rows15`, `rows60`', '',
           '## 2. 사용자 질문 원문', '', '```text',
           '해당 없음 — 사용자 질문 없이 문서 「%s」(document_id %s) 전체 원문을 읽기 묶음으로 나눠 고정 지시문과 함께 보냈다.' % (name, did), '```', '',
           '## 3. 기준답변 — 채점 전용, 제품 입력 비공개', '', '```text',
           '없음 — 기준답변과 채점 호출이 없다. 대사 단위의 법적 타당성은 채점하지 않았다.', '```', '',
           '## 4. 제품 입력을 구성한 원값', '', '### 회수 전 전체·후보·제시 규모', '', '```json',
           json.dumps({'retrieval': '해당 없음 — 회수·필터 없이 문서 전체를 결정적으로 나눔', 'document_id': did, 'document': name,
                       'text_blocks': totals['blocks'], 'chars': totals['chars'], 'rows': totals['rows'],
                       'groups_by_arm': {arm: plan[case][arm]['groups'] for arm in ARMS}}, ensure_ascii=False), '```', '',
           '### 회수 좌표·조문·정의·Wiki·관계 — 전체', '', '```json',
           json.dumps({'generation_id': auth['generation_id'], 'store_sha256': auth['store_sha256'], 'schedule': rel(DES / 'schedule.json'),
                       'schedule_sha256': sha(DES / 'schedule.json'), 'row_ids_sha256': plan[case]['baseline']['row_ids_sha256'],
                       'note': '행·묶음은 reading-groups-v1이 저장 구조와 문단 소유자로 만든다. 정의·Wiki·관계 입력 없음.'}, ensure_ascii=False), '```', '',
           '### 회수·탈락 단계 원장 — run·arm별', '',
           '회수가 없어 단계 원장은 해당 없음이다(stage_ledger mode=not_applicable).', '',
           '| run | arm | stage | kind | before | +added | -discarded | after | gold before | gold + | gold - | gold after/total | recall | 대표 탈락 이유 |',
           '|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|',
           '| run-001 | 전체 | 해당 없음 | 해당 없음 | - | - | - | - | - | - | - | - | - | 회수 없음 |', '', '```json',
           json.dumps({'stage_ledger_artifact': None, 'discarded_gold_and_reasons': '해당 없음', 'gold_visible_to_product': False}, ensure_ascii=False), '```', '',
           '## 5. 제품 모델 호출 — run·arm별 실제 원문', '']
    for arm in ARMS:
        row, done, first = line(case, arm)
        out += ['### run-001 / %s / system' % arm, '', '```text', review.SYSTEM if done else '미실행', '```', '',
                '### run-001 / %s / user' % arm, '']
        if done:
            example = saved(done[0]['call_folders'][0], 'request.json')
            out += ['묶음마다 user 입력이 다르다. 전체 %d건의 원문은 보관 파일의 `<호출 폴더>/request.json`에 있다. 아래는 첫 묶음(`%s`)의 실제 전문이다.' % (len(done), done[0]['call_folders'][0]), '',
                    '```text', example['messages'][1]['content'], '```', '',
                    '### run-001 / %s / schema·tool' % arm, '', '첫 묶음의 실제 응답 스키마(묶음마다 ref 목록만 다르다).', '', '```json',
                    json.dumps(example['response_format']['json_schema']['schema'], ensure_ascii=False), '```', '',
                    '### run-001 / %s / provider 원응답·structured output·usage·지연' % arm, '',
                    '응답 원문은 보관 파일의 `<호출 폴더>/response.json`, 검증된 출력은 `output.json`이다. 실행 %d/%d 묶음, 첫 응답 완전 %d, 보완 후 완전 %d.' % (len(done), row['groups'], first, row['final_complete']), '',
                    '| 묶음 | 제목 | 행 | 시도(상태/초) | 입력·출력 토큰 | 대사 단위 | 호출 폴더 |', '|---:|---|---:|---|---:|---:|---|']
            for g in done:
                tokens = '/'.join('%s·%s' % ((a['usage'] or {}).get('input_tokens'), (a['usage'] or {}).get('output_tokens')) for a in g['attempts'])
                out.append('| %d | %s | %d | %s | %s | %s | %s |' % (g['group_index'], g['title'].replace('|', '/')[:60], g['rows'],
                           ' → '.join('%s/%.1f' % (a['status'], a['seconds']) for a in g['attempts']), tokens, g['units'], '<br>'.join('`%s`' % f for f in g['call_folders'])))
            missing = row['groups'] - len(done)
            out += ['', '미실행 묶음 %d건: 자원 보호 중단 뒤 보내지 않았다.' % missing if missing else '미실행 묶음 없음.', '']
        else:
            out += ['미실행 — 자원 보호 중단(%s) 뒤 이 문서의 묶음은 보내지 않았다.' % stop['reason'], '',
                    '### run-001 / %s / schema·tool' % arm, '', '```json', json.dumps({'not_run': True}), '```', '',
                    '### run-001 / %s / provider 원응답·structured output·usage·지연' % arm, '', '```json', json.dumps({'not_run': True, 'physical_requests': 0}), '```', '']
    repairs = [{'arm': g['arm'], 'group_index': g['group_index'], 'rows': g['rows'], 'first_status': g['attempts'][0]['status'],
                'missing': g['attempts'][0]['missing'], 'duplicated': g['attempts'][0]['duplicated'], 'after_corrective_call': g['attempts'][1]['status'],
                'call_folders': g['call_folders']} for g in groups if g['case'] == case and len(g['attempts']) > 1]
    out += ['## 6. 중간 LLM 호출 — router/compiler/verifier/repair', '',
            '중간 호출은 묶음당 최대 1회의 보완 호출뿐이다. 보완 입력 = 같은 rows + 직전 출력 + 누락·중복 ref.', '', '```json', json.dumps(repairs, ensure_ascii=False), '```', '',
            '## 7. 채점 호출과 반복 판정', '', '### judge system/user — 기준답변 포함', '', '```json',
            json.dumps({'judge_calls': 0, 'reason': '채점 호출 없음. 서버의 행 계수 검사(모든 ref가 정확히 한 번)만 적용'}, ensure_ascii=False), '```', '',
            '### judge 원응답과 최종 다수결', '', '```json', json.dumps({'judge_calls': 0}, ensure_ascii=False), '```', '',
            '## 8. 사례 최종 판정', '', '| run | arm | 정답 | 핵심 근거 | 실패 유형 |', '|---|---|---:|---|---|']
    for arm in ARMS:
        row, done, first = line(case, arm)
        if not done:
            out.append('| run-001 | %s | 판정 없음 | 미실행 | other: resource_guard_stop |' % arm)
        else:
            verdict = '기준 충족' if len(done) == row['groups'] and first / len(done) >= .9 and row['final_complete'] == row['groups'] else '판정 불가(일부 미실행)' if len(done) < row['groups'] else '기준 미달'
            out.append('| run-001 | %s | %s | 첫 응답 완전 %d/%d, 보완 후 %d/%d, 결과 불명 %d | %s |' % (arm, verdict, first, len(done), row['final_complete'], len(done), row['unknown'],
                       'other: row_omitted_first_response %d건' % row['first_incomplete'] if row['first_incomplete'] else '없음'))
    out += ['', '- 사전 지정 비교쌍의 신규 정답·회귀: 묶음 경계가 arm마다 달라 묶음 단위 짝 비교는 없다. 행 단위 배치 일치는 README 6절.',
            '- 공통 실패 유형: `other` — ' + ('첫 응답에서 머리 문장 행 1개 누락(보완 1회로 해소)' if done_any else '자원 보호 중단으로 미실행'),
            '- 사람이 확인한 직접 원인: ' + ('누락된 행은 "다음 각 호" 머리 문장이었다. 의미 품질은 사람이 채점하지 않았다.' if done_any else '다른 세션의 후처리 프로세스로 호스트 스왑이 늘어 동결 한도(512MiB)를 넘었다.'),
            '- 다음 분기에서 검증할 가설: ' + ('제목뿐인 행과 정의 조문의 처리 규칙을 지시문에 명시하면 arm 간 배치 불일치가 줄어든다.' if done_any else '같은 동결 코드로 이 문서의 9개 묶음을 실행하면 행 한도 판정 규칙을 적용할 수 있다.'), '']
    path = ADR / '실험' / ('질문-%03d-%s.md' % (number, case))
    path.write_text('\n'.join(out), 'utf-8')
    return path


paths = [question(1, 'risk-model-code'), question(2, 'bond-demand-code')]

# ---- numbers used in the summaries ------------------------------------------
R = {arm: line('risk-model-code', arm) for arm in ARMS}
usage_total = {k: sum(result['by_arm'][arm][k] for arm in ARMS) for k in ('physical_requests', 'input_tokens', 'output_tokens')}
cost_total = round(sum(result['by_arm'][arm]['reported_cost_usd'] for arm in ARMS), 8)
agree = result['agreement']['risk-model-code']
swap_growth = (stop['current']['swap_used'] - stop['baseline']['swap_used']) / 1024 ** 2
arm_rows = {arm: '첫 응답 완전 %d/%d(%.1f%%), 보완 후 %d/%d' % (R[arm][2], len(R[arm][1]), 100 * R[arm][2] / len(R[arm][1]), R[arm][0]['final_complete'], len(R[arm][1])) for arm in ARMS}

# ---- 실험/README.md ----------------------------------------------------------
index = (ADR / '실험/README.md').read_text('utf-8')
def swap(old, new, text, count=1):
    assert text.count(old) >= count, old
    return text.replace(old, new, count)
index = swap('- 이 분기의 변경 가설: TODO', '- 이 분기의 변경 가설: ' + criteria['question'], index)
for arm in ARMS:
    index = swap('| `%s` | %s | %s | TODO | TODO |' % (arm, 'baseline' if arm == 'baseline' else 'candidate', 'ROOT' if arm == 'baseline' else 'baseline'),
                 '| `%s` | %s | %s | max_rows=%d | 같은 동결 코드·지시문·문서·모델, max_chars=8000 |' % (arm, 'baseline' if arm == 'baseline' else 'candidate', 'ROOT' if arm == 'baseline' else 'baseline', ARMS[arm]), index)
index = swap('| 001 | `risk-model-code` | `run-001` | TODO | TODO | TODO |',
             '| 001 | `risk-model-code` | `run-001` | 30행 %s / 15행 %s(13묶음 미실행) / 60행 %s | 묶음 경계가 달라 짝 비교 없음 | other: 머리 문장 행 누락 2건(보완으로 해소) |' % (arm_rows['baseline'], arm_rows['rows15'], arm_rows['rows60']), index)
index = swap('| 002 | `bond-demand-code` | `run-001` | TODO | TODO | TODO |', '| 002 | `bond-demand-code` | `run-001` | 미실행(자원 보호 중단) | 해당 없음 | other: resource_guard_stop |', index)
index = swap('- run 상태: `run-001 / planned`', '- run 상태: `run-001 / complete` (123묶음 중 101묶음 실행 뒤 자원 보호 중단, 재개 없음)', index)
index = swap('- arm별 정답: TODO', '- arm별 정답(리스크관리 모범규준, 실행한 묶음 기준): ' + '; '.join('%s %s' % (ARM_LABEL[a], arm_rows[a]) for a in ARMS), index)
index = swap('- 사전 지정 비교쌍별 신규 정답 / 회귀: TODO', '- 사전 지정 비교쌍별 신규 정답 / 회귀: 해당 없음(묶음 단위 짝 없음). 행 배치 일치 30행↔60행 %d/%d' % (agree['pairs']['baseline|rows60']['same'], agree['pairs']['baseline|rows60']['both']), index)
index = swap('- judge 불일치: TODO', '- judge 불일치: 채점 호출 없음', index)
index = swap('| `run-001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |', '| `run-001` | 전체 | 해당 없음 | 해당 없음 | - | - | - | - | 회수 없음 |', index)
(ADR / '실험/README.md').write_text(index, 'utf-8')

# ---- README.md ----------------------------------------------------------------
readme = (ADR / 'README.md').read_text('utf-8')
head, _ = readme.split('## 2. 문제와 변경 전 구조', 1)
head = swap('TODO: 채택·기각·보류와 운영 배선 변경 여부를 먼저 적는다.',
            '보류(Proposed). 읽기 묶음을 실제 Qwen3.8에 주는 시험을 123묶음 중 101묶음까지 실행한 뒤, 다른 세션의 후처리 프로세스로 호스트 스왑이 %.0fMiB 늘어 '
            '동결한 자원 보호 한도(512MiB)에 걸려 멈췄다. 호출 중 끊긴 것은 없고 결과 불명 0건이다. 「금융투자회사의 리스크관리 모범규준」에서는 30행 %s, 60행 %s로 '
            '모든 행을 빠짐없이 처리했다. 두 번째 문서는 한 건도 실행하지 못해 사전에 고정한 "두 문서 모두" 판정 규칙은 적용할 수 없다. 권장 한도 없음, 운영 배선 변경 없음.' % (swap_growth, arm_rows['baseline'], arm_rows['rows60']), head)
table = '\n'.join('| %s | %d | %d | %d | %d | %d | %d | %s | %s / %s | %.1f | %d | %d·%d·%d |' % (
    ARM_LABEL[a], R[a][0]['groups'], len(R[a][1]), R[a][2], R[a][0]['final_complete'], R[a][0]['physical_requests'], R[a][0]['input_tokens'],
    R[a][0]['output_tokens'], R[a][0]['seconds_p50'], R[a][0]['seconds_p95'], R[a][0]['seconds_total'], R[a][0]['units'],
    R[a][0]['rows_placed']['units'], R[a][0]['rows_placed']['not_target'], R[a][0]['rows_placed']['hold']) for a in ARMS)
body = f'''## 2. 문제와 변경 전 구조

전수 대사(문서 하나의 모든 구조 단위 확인)를 위해 `reading_groups.py`가 문서를 "읽기 묶음"으로 나눈다. 이 모듈은 단위 테스트와 내규 11개 문서의 누락·중복 검사만 통과했고, 실제 모델이 묶음 안의 행을 빠짐없이 처리하는지와 묶음당 행 한도(시작값 30)는 확인된 적이 없다. 대사 워크플로우에는 아직 연결하지 않았다.

## 3. 가설과 사전 판정 기준

### 가설

{criteria['question']}. 예상: 30행 이하에서는 첫 응답에 빠짐없이 처리하고 60행에서는 누락·중복이 늘어난다.

### 성공 기준

- 주 지표: {criteria['primary_metric']}
''' + '\n'.join('- ' + x for x in criteria['required']) + f'''
- 판정 규칙: {criteria['decision_rule']}
- 한도: 물리 호출 {criteria['limits']['physical_total']}회, 보고 비용 {criteria['limits']['reported_cost_usd']}달러, 호출당 180초, 묶음당 보완 1회.

### 반증 기준

- {criteria['stop']}
- 보낸 원문이 두 공개 문서 밖이거나 저장 원문과 다르면 실패.
- 기본 arm이 기준에 못 미치면 Rejected이며 한도를 권장하지 않는다.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | max_rows=30 (모듈 기본값) | 같은 동결 코드·지시문·문서·모델, max_chars=8000, max_spine_chars=2000 | baseline |
| rows15 | max_rows=15 | 위와 같음 | candidate |
| rows60 | max_rows=60 | 위와 같음 | candidate |

- 모델이 하는 일: 묶음의 각 행(R번호)을 units(대사 단위), not_target(대사 대상 아님), hold(보류) 중 한 곳에 넣는다. 서버는 모든 행이 정확히 한 번 들어갔는지만 검사한다.
- 실행 순서: 문서별로 세 arm의 묶음을 번갈아 한 줄로 실행했다(`artifacts/design/schedule.json`).
- 코드 격리: `rows15`·`rows60` 후보 스냅샷(바이트 동일)을 동결했고 baseline은 rows15 스냅샷을 쓴다. `group_review.py`는 후보 스냅샷에만 있는 새 파일이다.

### 다른 ADR과의 관계

- 관련 ADR: 없음

- experiment 계보와 직접 부모 arm: [실험 manifest](실험/manifest.json)

## 5. 데이터·모델·재현성

- 데이터셋과 버전: 공개 허용 목록의 두 문서 — 「금융투자회사의 리스크관리 모범규준」(654행, 43,838자), 「무보증사채 수요예측 모범규준」(50행, 4,660자). 세대 `{auth['generation_id']}`. 내규 문서는 공개 허용 목록에 없어 쓰지 않았다.
- frozen source와 SHA-256: `{rel(DES / 'schedule.json')}` `{sha(DES / 'schedule.json')}`; 동결 목록 `{rel(DES / 'freeze.json')}`.
- 제품/중간/채점 모델: `qwen/qwen3.8-27b` (Parasail FP8, reasoning none, 출력 상한 없음). 채점 호출 없음.
- 반복 수와 다수결: 묶음당 1회, 내용 오류에만 보완 1회. 반복·다수결 없음.
- 법령·기준답변 버전 점검: 해당 없음(기준답변 없음). 문서 판본은 선택된 세대 그대로다.

## 6. 결과

「금융투자회사의 리스크관리 모범규준」(654행). 「무보증사채 수요예측 모범규준」은 미실행이다.

| arm | 계획 묶음 | 실행 묶음 | 첫 응답 완전 | 보완 후 완전 | 물리 호출 | 입력 토큰 | 출력 토큰 | 호출 p50 / p95(초) | 합계(초) | 대사 단위 | 행 배치(단위·대상 아님·보류) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{table}

- 15행 arm은 65묶음 중 52묶음만 실행했다(13묶음 미실행). 표의 값은 실행한 묶음 기준이다.
- 첫 응답에서 행이 빠진 묶음은 2건(30행 arm 1건, 15행 arm 1건), 각 1행이며 보완 1회로 모두 해소됐다. 중복 0건, 형식 오류 0건, 결과 불명 0건, 공급자 전환 0건.
- 전체 물리 호출 {usage_total['physical_requests']}회 = 저장된 요청 {result['integrity']['request_folders']}건, 보고 비용 {cost_total}달러, 실행 {batch['seconds']}초.
- 저장된 요청의 행 원문은 모두 저장 원문과 같았다(불일치 {len(result['integrity']['requests_differing_from_stored_original'])}건). 동결 파일 변경 {len(result['integrity']['frozen_files_changed'])}건.

| 행 배치 일치(같은 행을 같은 곳에 넣음) | 같음 / 양쪽 모두 배치 | 비율 |
|---|---:|---:|
| 30행 ↔ 60행 | {agree['pairs']['baseline|rows60']['same']} / {agree['pairs']['baseline|rows60']['both']} | {100 * agree['pairs']['baseline|rows60']['same'] / agree['pairs']['baseline|rows60']['both']:.1f}% |
| 30행 ↔ 15행 | {agree['pairs']['baseline|rows15']['same']} / {agree['pairs']['baseline|rows15']['both']} | {100 * agree['pairs']['baseline|rows15']['same'] / agree['pairs']['baseline|rows15']['both']:.1f}% |
| 15행 ↔ 60행 | {agree['pairs']['rows15|rows60']['same']} / {agree['pairs']['rows15|rows60']['both']} | {100 * agree['pairs']['rows15|rows60']['same'] / agree['pairs']['rows15|rows60']['both']:.1f}% |
| 세 arm 모두 | {agree['same_place_in_all_arms']} / {agree['rows_placed_in_all_arms']} | {100 * agree['same_place_in_all_arms'] / agree['rows_placed_in_all_arms']:.1f}% |

사전 기준 판정: 원문·전송 일치는 충족. 기본 arm 기준은 두 문서 모두를 요구하므로 미충족(둘째 문서 미실행). 계수·동결 기준은 미실행 22묶음 때문에 미충족. 권장 한도 없음.

## 7. 사례별 오류 분석

| 실패 유형 | 건수/분모 | 대표 질문 | 해석 |
|---|---:|---|---|
| other: 첫 응답 행 누락 | 2 / 101 묶음 | risk-model-code 30행 arm 묶음 20 | 빠진 행은 "다음 각 호의 사항을 반영하여야 한다" 머리 문장이었다. 보완 호출에서 해당 단위에 들어갔다. |
| other: resource_guard_stop | 22 / 123 묶음 미실행 | bond-demand-code 전체 | 다른 세션의 후처리 프로세스(메모리 약 5GiB)로 호스트 스왑이 늘었다. 이 실행기의 스왑 증가는 1MiB 미만이었다. |

질문별 실제 입출력은 [실험 인덱스](실험/README.md)에 연결한다.

## 8. 비용·지연·회수 규모

| 항목 | 값 | 측정 단위·분모 |
|---|---:|---|
| 전체 corpus | 해당 없음 | 회수 없음 — 두 문서 전체를 나눠 보냄 |
| 필터 전/후 후보 | 해당 없음 | 회수 없음 |
| LLM 제시 수 | 실행 101묶음 | 30행 arm 32, 15행 arm 52, 60행 arm 17 |
| golden recall | 해당 없음 | 기준답변 없음 |
| 제시 비율 | 해당 없음 | 회수 없음 |
| LLM 호출·토큰·지연 | {usage_total['physical_requests']}회 · 입력 {usage_total['input_tokens']} · 출력 {usage_total['output_tokens']} | 보고 비용 {cost_total}달러, arm별 지연은 6절 |

회수를 변경하지 않았다. 단계 원장은 해당 없음(`stage_ledger.mode=not_applicable`).

### 단계별 회수·탈락 원장

| run | arm | stage | kind | 후보 before→after | added / discarded | gold before→after | gold gain / loss | recall | 주요 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| run-001 | 전체 | 해당 없음 | 해당 없음 | - | - | - | - | - | 회수 없음 |

## 9. 해석

- 사실: 한 문서(654행)에서 30행 묶음과 60행 묶음 모두 보완 1회 안에 모든 행을 정확히 한 번씩 처리했다. 60행 arm은 첫 응답에서 17/17이었고 호출 수·합계 시간·비용이 30행 arm보다 적었다.
- 사실: 예상("60행에서는 누락·중복이 늘어난다")은 이 문서에서 관찰되지 않았다.
- 사실: arm 간 행 배치는 94~97% 같았다. 30행↔60행에서 달랐던 22행은 조·장 제목뿐인 행 13개, 용어를 정의하는 조문(제6-4조 머리 문장과 6개 호) 7개가 단위와 대상 아님 사이에서 갈린 것, "별표 8/9와 같다" 행 2개가 보류와 단위 사이에서 갈린 것이다.
- 추론: 제목뿐인 행과 정의 조문의 처리 규칙을 지시문에 정하면 배치 불일치가 줄 가능성이 있다(미검증).
- 대사 단위가 법적으로 맞는지는 채점하지 않았다. 표본 열람에서 "①항 머리 문장 + 각 호"가 한 단위로 묶이는 것은 확인했으나 채점 결과가 아니다.

## 10. 한계와 일반화 가능 범위

- 인샘플 probe이며 decision_eligible=false다. 문서 1개, arm당 1회 실행이고 반복 안정성은 측정하지 않았다.
- 둘째 문서와 15행 arm의 13묶음은 미실행이라 사전 판정 규칙을 적용하지 못했다.
- 조문형 공개 문서만 시험했다. "1. / 가. / (1)" 형식의 실제 내규와 외규 대조 단계는 시험하지 않았다.
- 실행기의 대기 조건은 실험 도구 경로가 명령줄에 있는 프로세스만 감지한다. 작업 폴더 안에서 `python ledger.py`로 실행된 다른 세션의 후처리는 감지하지 못했다.
- GENOS 내부 모델에서의 동작은 확인하지 않았다.

## 11. 운영 결정·롤백 조건

- 메인 배선: 변경 없음. `reading_groups.py`는 작업 코드에 미연결 상태로 남는다. `group_review.py`는 후보 스냅샷에만 있다.
- 이 ADR 안에서는 재개하지 않는다(자원 보호 중단 기록 `no_retry`). 남은 22묶음은 같은 동결 코드로 새 ADR에서 실행한다.
- 롤백 대상 없음.

## 12. 재현 명령

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1425/setup.py      # 설계·코드 동결(최초 1회)
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1425/live.py       # 동결 일정 실행
tar -xzf 04_EXPERIMENTS/ADR/ADR-1425-reading-groups-row-limit-qwen/artifacts/run-001/calls.tar.gz -C 04_EXPERIMENTS/ADR/ADR-1425-reading-groups-row-limit-qwen/artifacts/run-001
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1425/finalize.py   # 집계(호출 폴더 복원 뒤)
```

- 원시 산출물: [artifacts/manifest.json](artifacts/manifest.json)
- 질문 파일 hash: [실험/manifest.json](실험/manifest.json)
'''
(ADR / 'README.md').write_text(head + body, 'utf-8')

# ---- manifest results -------------------------------------------------------
manifest = read(ADR / '실험/manifest.json')
manifest['results'] = {
    'status': 'complete',
    'by_arm': {arm: {'correct': R[arm][2], 'total': len(R[arm][1]), 'accuracy': round(R[arm][2] / len(R[arm][1]), 4),
                     'scope': 'risk-model-code groups whose first response placed every shown row exactly once / executed groups; bond-demand-code not run',
                     'planned_groups': result['by_arm'][arm]['groups'], 'not_run_groups': result['by_arm'][arm]['groups'] - len(R[arm][1]),
                     'complete_after_one_corrective_call': R[arm][0]['final_complete'], 'unknown': result['by_arm'][arm]['unknown'],
                     'decision_eligible': False, 'meets_frozen_thresholds_on_both_documents': result['arm_meets_thresholds'][arm]} for arm in ARMS},
    'comparisons': [{'kind': 'row_placement_agreement', 'pair': pair, **values, 'case_id': 'risk-model-code',
                     'note': 'Group boundaries differ by arm; no group-level paired outcome'} for pair, values in agree['pairs'].items()],
    'judge_disagreements': 0,
    'usage': {**usage_total, 'offline_evaluator_requests': 0, 'reported_cost_usd': cost_total, 'unknown': 0, 'provider_switches': len(batch['provider_switches']),
              'usage_complete': all(result['by_arm'][arm]['usage_complete'] for arm in ARMS)},
    'latency': {'by_arm': {arm: {'p50_seconds': R[arm][0]['seconds_p50'], 'p95_seconds': R[arm][0]['seconds_p95'], 'total_seconds': R[arm][0]['seconds_total']} for arm in ARMS},
                'batch_seconds': batch['seconds'], 'unit': 'seconds per group attempt including transport'},
    'error_taxonomy': [{'type': 'other: resource_guard_stop', 'groups_not_run': result['integrity']['groups_not_run'], 'reason': stop['reason'],
                        'global_swap_growth_mib': round(swap_growth, 1), 'worker_swap_growth_mib': round((stop['current']['worker_swap'] - stop['baseline']['worker_swap']) / 1024 ** 2, 2)},
                       {'type': 'other: row_omitted_first_response', 'count': 2, 'denominator_groups': 101, 'resolved_by_one_corrective_call': 2}],
    'frozen_criteria': {'required': result['required'], 'success_criteria_met': result['success_criteria_met'], 'recommended_max_rows': result['recommended_max_rows']}}
manifest['runs'][0].update(status='complete', sha256=sha(RUN / 'result.json'), success_criteria_met=False)
for row, path in zip(manifest['questions'], paths):
    row['sha256'] = sha(path)
put(ADR / '실험/manifest.json', manifest)

# ---- artifacts manifest -----------------------------------------------------
existing = read(ART / 'manifest.json')
described = {'design': '호출 전 동결한 범위·일정·기준·후보 핀', 'preflight': '호출 전 구조 검사·가짜 응답 점검·요청 크기 점검 기록', 'run-001': '실제 실행 기록·집계'}
files = []
for path in sorted(p for p in ART.rglob('*') if p.is_file() and p != ART / 'manifest.json'):
    files.append({'path': rel(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
                  'description': described[path.relative_to(ART).parts[0]], 'contains_raw_prompts_and_outputs': path.name == 'calls.tar.gz'})
existing['files'] = files
(ART / 'manifest.json').write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print('published', len(files), 'artifact files;', arm_rows)
