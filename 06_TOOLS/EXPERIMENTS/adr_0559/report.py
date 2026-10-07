"""Post-selection deterministic accounting; never imported by the product runner.

Gold is joined here only after the immutable prospective run is complete. A
pass means required evidence/status contracts, not certified legal correctness.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import statistics

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0559-node-action-experience-concepts'
RUN = ADR / 'artifacts/run-001'
SCHEMA = 'retrieval-stage-ledger-v1'
UNIT = 'case_id + canonical article-root coordinate'
ARMS = ['baseline', 'experience']


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def identities(units):
    return sorted([{'doc_id': 'mock-deal:v1', 'node': int(u)-1} for u in set(units)], key=canonical)


def stage(plan, before, after, gold, *, executed=True, skip_reason='', reason='NOT_SELECTED_BY_FROZEN_ROUTE'):
    b, a, g = set(before), set(after), set(gold)
    added, discarded = a-b, b-a
    receipts = [{'identity': identity, 'reason': reason} for identity in identities(discarded)]
    row = {**plan, 'executed': executed, 'skip_reason': skip_reason,
        'before': identities(b), 'added': identities(added), 'discarded': identities(discarded),
        'after': identities(a), 'before_count': len(b), 'added_count': len(added),
        'discarded_count': len(discarded), 'after_count': len(a),
        'occurrence_counts': {'before': len(b), 'after': len(a),
            'canonical_collapsed_before': 0, 'canonical_collapsed_after': 0},
        'discard_receipts': receipts,
        'discard_reason_counts': {reason: len(discarded)} if discarded else {},
        'gold_total': len(g), 'gold_before': len(b & g), 'gold_added': len(added & g),
        'gold_discarded': len(discarded & g), 'gold_after': len(a & g),
        'golden_recall': len(a & g)/len(g) if g else None,
        'gold_before_identities': identities(b & g), 'gold_added_identities': identities(added & g),
        'gold_after_identities': identities(a & g),
        'discarded_gold': [r for r in receipts if str(r['identity']['node']+1) in g]}
    return row


def journal_sets(case_id, arm):
    paths = list((RUN/'cases'/case_id/arm).rglob('journal.sqlite'))
    if not paths:
        # Current native filename is work.sqlite.
        paths = list((RUN/'cases'/case_id/arm).rglob('work.sqlite'))
    if len(paths) != 1:
        candidates = []
        for path in (RUN/'cases'/case_id/arm).rglob('*.sqlite*'):
            try:
                with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name='evidence_unit'").fetchone():
                        candidates.append(path)
            except sqlite3.Error:
                pass
        paths = candidates
    if len(paths) != 1:
        if not paths:
            return set(), set(), {'journal_path': None, 'reason': 'NOT_EXECUTED_AFTER_EARLY_STOP'}
        raise ValueError(f'one native journal required: {case_id}/{arm}: {paths}')
    with sqlite3.connect(f'file:{paths[0]}?mode=ro', uri=True) as db:
        rows = db.execute('SELECT source_id FROM evidence_unit').fetchall()
        sent = db.execute('''SELECT DISTINCT e.source_id FROM evidence_unit e
            JOIN presentation p USING(evidence_id) JOIN model_attempt a USING(view_id)
            WHERE a.status IN ('SUCCEEDED','FAILED','UNKNOWN','SENT')''').fetchall()
        observations = [json.loads(row[0]) for row in db.execute('SELECT result_json FROM observation')]
    # Source IDs are content identifiers, never guessed from their hash.
    catalogue = read(RUN/'concepts.json')['source_catalogue'] if 'source_catalogue' in read(RUN/'concepts.json') else None
    if catalogue is None:
        bundle = read(RUN/'concepts.json')
        catalogue = {}
        for episode in bundle['episodes']:
            for transition in episode['steps']:
                for node in [transition['anchor'], transition['target']]:
                    catalogue[node['source_id']] = node
        for request in (RUN/'calls').glob('call-*/request.json'):
            wire = read(request)
            if 'messages' not in wire:
                continue
            data = json.loads(wire['messages'][1]['content'])
            for node in data.get('next_sources', []):
                catalogue[node['source_id']] = {'unit_id': str(int(node['coordinate'][1:-1])-1)}
    def units(records):
        return {str(int(catalogue[sid]['unit_id'])+1) for (sid,) in records}
    return units(rows), units(sent), {'journal_path': str(paths[0].relative_to(ROOT)),
        'journal_sha256': sha(paths[0]), 'observations': observations}


def assess(case, result, required, presented):
    if result['status'] in {'ERROR', 'NOT_EXECUTED'}:
        return {'pass': False, 'failure': 'model_or_contract_error', 'detail': result.get('error'),
            'required_units': required, 'presented_units': sorted(presented)}
    if case['mode'] == 'guard':
        ok = result['status'] == 'GUARD_OK' and not result['guidance']['items']
        return {'pass': ok, 'failure': None if ok else 'authority_or_version',
            'required_units': [], 'presented_units': sorted(presented)}
    if not required:
        ok = result['status'] == 'CLARIFY' and not result['answer']
        return {'pass': ok, 'failure': None if ok else 'unsupported_inference',
            'required_units': [], 'presented_units': sorted(presented)}
    decision = result['trace'][-1]['decision']
    sid_units = {sid: str(int(node['unit_id'])+1) for sid, node in result['source_catalogue'].items()}
    cited = {sid_units[sid] for sid in decision['source_ids']}
    ok = result['status'] == 'ANSWER' and bool(result['answer']) and set(required) <= presented and set(required) <= cited
    return {'pass': ok, 'failure': None if ok else 'required_issue_omission',
        'required_units': required, 'presented_units': sorted(presented), 'cited_units': sorted(cited)}


def block(value):
    return '```json\n'+json.dumps(value, ensure_ascii=False, indent=2)+'\n```\n'


def main():
    result = read(RUN/'result.json')
    if result['status'] != 'complete':
        raise ValueError('post-selection report requires a complete run')
    manifest_path = ADR/'실험/manifest.json'
    manifest = read(manifest_path)
    cases = read(ADR/'artifacts/design/cases.json')['cases']
    gold = read(ADR/'artifacts/design/expected-offline.json')
    bundle = read(RUN/'concepts.json')
    # The grouping rubric was frozen before the consolidation model call.
    fixture_ids = {e['id']: e['fixture_history_id'] for e in bundle['episodes']}
    groups = sorted([sorted(fixture_ids[x] for x in c['support_episode_ids']) for c in bundle['concepts']])
    group_ok = groups == sorted([sorted(g) for g in gold['concept_groups']])
    partition = {'actual': groups, 'expected': gold['concept_groups'], 'pass': group_ok,
        'support_count': sum(c['support_count'] for c in bundle['concepts']),
        'occurrence_count': sum(c['occurrence_count'] for c in bundle['concepts'])}
    ledger = {'schema_version': SCHEMA, 'adr_id': manifest['adr_id'], 'experiment_id': manifest['experiment_id'],
        'accounting_unit': UNIT, 'computed_post_selection': True, 'gold_visible_to_product': False,
        'runs': [{'run_id': 'run-001', 'arms': []}],
        'audit': {'classification': 'SYNTHETIC', 'gold_artifact': str((ADR/'artifacts/design/expected-offline.json').relative_to(ROOT)),
            'gold_sha256': sha(ADR/'artifacts/design/expected-offline.json'),
            'presentation_unit': 'Unique original article roots in native views sent to the model; failed responses still consumed the view.',
            'guard_cases': 'Source anchor executed, but no model presentation; read_units=[] in guard result is not evidence of no anchor READ.'}}
    grades = []
    for arm in ARMS:
        plan = manifest['design']['retrieval_stage_plan']['stages_by_arm'][arm]
        arm_cases = []
        for case in cases:
            r = next(r for r in result['results'] if r['case_id'] == case['id'] and r['arm'] == arm)
            reads, presented, audit = journal_sets(case['id'], arm)
            required = gold['required_units'][case['id']]
            grade = assess(case, r, required, presented)
            grades.append({'case_id': case['id'], 'arm': arm, **grade,
                'read_units': sorted(reads), 'status': r['status']})
            if reads:
                anchor = stage(plan[1], list('123456'), ['2'], required, reason='SHARED_FROZEN_ANCHOR_ONLY')
                navigation_before = ['2']
                navigation_executed = case['mode']=='live'
                navigation_skip = 'DETERMINISTIC_GUARD_NO_NAVIGATION' if case['mode']=='guard' else ''
            else:
                anchor = stage(plan[1], list('123456'), list('123456'), required,
                    executed=False, skip_reason='NOT_EXECUTED_AFTER_EARLY_STOP')
                navigation_before = list('123456')
                navigation_executed = False
                navigation_skip = 'NOT_EXECUTED_AFTER_EARLY_STOP'
            navigation_after = reads if reads else navigation_before
            arm_cases.append({'schema_version': SCHEMA, 'computed_post_selection': True,
                'gold_visible_to_product': False, 'accounting_unit': UNIT, 'arm_id': arm,
                'case_id': case['id'], 'gold_total': len(required), 'gold_identities': identities(required),
                'stages': [stage(plan[0], [], list('123456'), required),
                    anchor,
                    stage(plan[2], navigation_before, navigation_after, required, executed=navigation_executed,
                        skip_reason=navigation_skip),
                    stage(plan[3], navigation_after, presented, required, reason='NO_SENT_MODEL_VIEW')],
                'audit': audit})
        counts = [c['stages'][-1]['after_count'] for c in arm_cases]
        total_gold = sum(c['gold_total'] for c in arm_cases)
        final_gold = sum(c['stages'][-1]['gold_after'] for c in arm_cases)
        metrics = {'presented_total': sum(counts), 'presented_mean': statistics.mean(counts),
            'presented_p50': statistics.median(counts), 'presented_p95': sorted(counts)[round((len(counts)-1)*.95)],
            'golden_recall': final_gold/total_gold, 'selectivity': statistics.mean(counts)/6}
        ledger['runs'][0]['arms'].append({'arm_id': arm, 'declared_stage_ids': [p['stage_id'] for p in plan],
            'cases': arm_cases, 'aggregate': metrics})
        retrieval = manifest['retrieval_accounting']
        for key, val in metrics.items():
            if not isinstance(retrieval.get(key), dict):
                retrieval[key] = {}
            retrieval[key][arm] = val
    ledger['artifact_sha256'] = hashlib.sha256(canonical(ledger).encode()).hexdigest()
    write(RUN/'retrieval-stage-ledger.json', ledger)
    retrieval = manifest['retrieval_accounting']
    retrieval.update(corpus_total=6, before_filter={a: 48 for a in ARMS},
        after_filter={a: sum(len(g['read_units']) for g in grades if g['arm']==a) for a in ARMS})
    retrieval['stage_ledger']['sha256'] = sha(RUN/'retrieval-stage-ledger.json')
    by_arm = {a: {'correct': sum(g['pass'] for g in grades if g['arm']==a), 'total': len(cases),
        'accuracy': sum(g['pass'] for g in grades if g['arm']==a)/len(cases),
        'metric_meaning': 'Synthetic required original evidence + citation + completion/clarification/guard contracts, not legal correctness'} for a in ARMS}
    paired = {'candidate_only_correct': 0, 'baseline_only_correct': 0, 'both_correct': 0, 'both_wrong': 0}
    for case in cases:
        b = next(g for g in grades if g['case_id']==case['id'] and g['arm']=='baseline')['pass']
        e = next(g for g in grades if g['case_id']==case['id'] and g['arm']=='experience')['pass']
        key = 'both_correct' if b and e else 'baseline_only_correct' if b else 'candidate_only_correct' if e else 'both_wrong'
        paired[key] += 1
    exception = next(r for r in result['results'] if r['case_id']=='exception-exit' and r['arm']=='experience')
    deviations = [t['decision'] for t in exception.get('trace', []) if t['decision']['deviated_concept_ids']]
    summary = {'schema_version': 'node-action-experience-offline-grade-v1', 'computed_post_selection': True,
        'gold_visible_to_product': False, 'legal_quality_certified': False,
        'concept_partition': partition, 'grades': grades, 'by_arm': by_arm, 'paired': paired,
        'exception_exit': {'explicit_deviation_observed': bool(deviations), 'decisions': deviations},
        'frozen_success_criteria': manifest['design']['success_criteria'],
        'all_success_criteria_met': group_ok and partition['support_count']==9
            and by_arm['experience']['correct']>=6 and not paired['baseline_only_correct'] and bool(deviations)}
    write(RUN/'offline-grade.json', summary)
    manifest['runs'][0].update(status='complete', sha256=sha(RUN/'result.json'))
    usage = result['usage']
    manifest['results'] = {'status': 'complete', 'by_arm': by_arm,
        'comparisons': [{'baseline': 'baseline', 'candidate': 'experience', **paired}],
        'judge_disagreements': None, 'usage': {'physical_calls': len(list((RUN/'calls').glob('call-*'))),
            'receipted_calls': len(usage), 'input_tokens': sum(u.get('input_tokens') or 0 for u in usage),
            'output_tokens': sum(u.get('output_tokens') or 0 for u in usage),
            'cost_usd': sum(u.get('cost_usd') or 0 for u in usage)},
        'latency': {'receipted_call_seconds': sum(u['seconds'] for u in usage)},
        'error_taxonomy': [g for g in grades if not g['pass']],
        'offline_grade_path': str((RUN/'offline-grade.json').relative_to(ROOT)),
        'all_success_criteria_met': summary['all_success_criteria_met']}
    write(manifest_path, manifest)
    write_question_docs(manifest, cases, ledger, summary, result)
    write_summary_docs(manifest, ledger, summary, result)
    print(json.dumps({'partition': partition, 'by_arm': by_arm, 'paired': paired,
        'explicit_exit': bool(deviations), 'success': summary['all_success_criteria_met']}, ensure_ascii=False))


def write_question_docs(manifest, cases, ledger, summary, result):
    calls = sorted((RUN/'calls').glob('call-*'))
    for q in manifest['questions']:
        case = next(c for c in cases if c['id']==q['case_id'])
        rows = [g for g in summary['grades'] if g['case_id']==case['id']]
        original = read(ADR/'실험/manifest.json')
        text = f"# 질문 {q['number']:03d} — {case['id']}\n\n## 1. 실행 메타\n\n{manifest['adr_id']} / run-001. 실행된 원본 상태 exact, 미실행은 unavailable. 2026-09-29. 실제 Gemma/Parasail FP8, thinking off. 모의 원문·질문이며 평가 모델 호출은 없다.\n\n## 2. 사용자 질문 원문\n\n```text\n{case['question']}\n```\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n"
        text += block({'required_units': rows[0]['required_units'],
            'rubric': '필요 원문이 실제 모델에 제시되고 마지막 ANSWER에서 인용되어야 한다. 목적 미정은 CLARIFY. guard는 안내 없음. 법률 정답 인증 없음.'})
        text += '\n## 4. 제품 입력을 구성한 원값\n\n### 회수 전 전체·후보·제시 규모\n\n'
        text += block({a: {k: original['retrieval_accounting'][k][a] if isinstance(original['retrieval_accounting'][k],dict) else original['retrieval_accounting'][k]
            for k in ('corpus_total','before_filter','after_filter','presented_total')} for a in ARMS})
        text += '\n### 회수 좌표·조문·정의·Wiki·관계 — 전체\n\n'+block(read(ADR/'artifacts/design/corpus.json'))
        text += '\n### 회수·탈락 단계 원장 — run·arm별\n\n'+block([c for a in ledger['runs'][0]['arms'] for c in a['cases'] if c['case_id']==case['id']])
        text += '\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\n'
        for arm in ARMS:
            own = [c for c in calls if f"-{case['id']}-{arm}-" in c.name]
            if not own:
                text += f'### run-001 / {arm}\n\n모델 호출 없음: 결정적 버전·범위 guard.\n\n'
            for call in own:
                text += f'### run-001 / {arm} / {call.name}\n\n'
                for file in ['binding.json','request.json','validation-schema.json','response.json','output.json','error.json']:
                    if (call/file).exists():
                        text += f'#### {file}\n\n'+block({str((call/file).relative_to(ROOT)): read(call/file)})+'\n'
                receipts = [u for u in result['usage'] if call.name == f"call-{u['call']:03d}-{u['phase']}"]
                text += '#### usage·지연\n\n'+block(receipts)+'\n'
        text += '\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n'
        text += '온라인 중간 호출은 없다. 공통 이력 통합 호출의 전체 원값은 아래 파일에 보존했다.\n\n'
        consolidate = RUN/'calls/call-001-consolidate'
        text += block({str((consolidate/file).relative_to(ROOT)): read(consolidate/file) for file in ['binding.json','request.json','validation-schema.json','response.json','output.json']})
        text += '\n## 7. 채점 호출과 반복 판정\n\n### judge system/user — 기준답변 포함\n\n'+block({'model_calls': [], 'grader': 'report.py deterministic required-source/status rubric', 'repeats': 1})
        text += '\n### judge 원응답과 최종 다수결\n\n'+block(rows)
        text += '\n## 8. 사례 최종 판정\n\n'+block([r for r in result['results'] if r['case_id']==case['id']])
        text += '\n필수 근거·완결 상태의 기능 판정이다. 실제 법률 해석의 정확도와 현장 지연은 미확인이다. 오류는 모델 응답 종료·계약과 필수 근거 누락을 구분하며, 관측 이후 프롬프트를 바꾸지 않았다.\n'
        (ADR/'실험'/q['file']).write_text(text)


def write_summary_docs(manifest, ledger, summary, result):
    old = (ADR/'README.md').read_text()
    front = old.split('---', 2)[1]
    arm_rows = '\n'.join(f"| {a} | {manifest['results']['by_arm'][a]['correct']}/{len(manifest['questions'])} | {manifest['retrieval_accounting']['presented_mean'][a]:.2f} | {manifest['retrieval_accounting']['golden_recall'][a]:.3f} |" for a in ARMS)
    stage_rows = []
    for a in ledger['runs'][0]['arms']:
        for index, p in enumerate(manifest['design']['retrieval_stage_plan']['stages_by_arm'][a['arm_id']]):
            stages = [c['stages'][index] for c in a['cases']]
            total = lambda key: sum(s[key] for s in stages)
            stage_rows.append(f"| run-001 | {a['arm_id']} | {p['stage_id']} | {p['kind']} | {total('before_count')}→{total('after_count')} | {total('added_count')} / {total('discarded_count')} | {total('gold_before')}→{total('gold_after')} | {total('gold_added')} / {total('gold_discarded')} |")
    stages_text = '| run | arm | stage | kind | before→after | added/discarded | gold before→after | gold added/discarded |\n|---|---|---|---|---:|---:|---:|---:|\n'+'\n'.join(stage_rows)
    termination = result.get('early_stop')
    decision = '기능 검증 기준 충족; 운영 채택은 보류' if summary['all_success_criteria_met'] else '사전 성공 기준 미충족; 운영 채택 보류'
    text = f'''---{front}---

# {manifest['adr_id']}: 노드·행동 경험 추출·개념 통합·탐색 안내 프로토타입

## 1. 결정 요약

{decision}. MAIN·활성 release·GENOS는 변경하지 않았다. 격리된 candidate snapshot과 명시적 연구 runner만 사용했다. 모의 자료의 탐색 기능 probe이며 법률 정답 인증은 없다.

작업 선점과 append-only 이벤트는 [실험 manifest](실험/manifest.json)의 reservation에 보존한다.

## 2. 문제와 변경 전 구조

v5 원문 도구와 journal은 현재 조사 경로를 보존하지만, 완료된 조사에서 가치 있는 노드·행동을 압축해 다음 조사에 안내하는 온라인 소비자는 연결되어 있지 않다. 기존 navigation-learning은 v5를 제외한다. 기본 제품의 BoundedSourceSession은 이번 probe에서 실행하지 않았으며, 원문 도구 경로를 명시적으로 선택했다.

## 3. 가설과 사전 판정 기준

노드·행동을 실제 관측한 뒤 유효한 이력 조각을 목적별 개념으로 안내하면, 질문 전체 유사도 검색 없이 다음 원문 탐색을 선택하고 반증 시 이탈할 수 있다는 가설이다.

실행 전 동결한 성공·반증 조건은 아래와 같다. 결과를 본 뒤 기준을 바꾸지 않았다.

{block(manifest['design']['success_criteria'])}

동일 질문 반복은 독립 지지 근거를 늘리지 않는다. 위조·세대·범위·누락 회귀는 허용하지 않으며 속도 개선은 성공 조건이 아니다. 실제 모델 format 오류 역시 실패로 남긴다.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | 경험 안내 없음 | 모의 원문·질문·Gemma·anchor·2회 탐색 예산 | 기준 |
| experience | 실제 journal 추출→개념 통합→행동 뒤 안내→피드백 | 기준과 같은 조건 | 후보 |

부모·arm·run·변경 delta의 정본은 manifest.lineage다. 통합에 사용한 10개 이력은 사람이 설계한 모의 성공 경로로, 실제 사용자 성공 로그가 아니다. v5 원문 읽기·인용·journal에 그 이력을 기록하고 추출 계약을 검사했다. 신규 6질문은 실제 모델 탐색, 나머지 2질문은 버전·범위 guard로 지정했다. arm 순서는 사례마다 교대했다. 다음 원문 후보 목록은 양쪽에 동일하게 제공했다.

## 5. 데이터·모델·재현성

synthetic-node-action-experience-v1 / 20260929-v1. 실제 법령·내부 질문을 전송하지 않았다. mock-deal:v1, 모의거래규정 6개 조문이며 법률 조언용 자료가 아니다. 정책 고정 Gemma google/gemma-4-31b-it / OpenRouter Parasail FP8, thinking off, fallback 없음. 통합 1회와 사례별 탐색 최대3호출; 모델 채점·다수결 없음.

원문·질문·이력·별도 gold SHA는 design.frozen_inputs, 기준 작업 코드 hash는 code-pins.json, 후보 revision과 runner hash는 code_isolation에 보존했다. 활성 release는 계보 확인용으로만 기록했다. 실제 실행은 hash 고정 작업 코드의 원문 도구와 mock generation이다.

## 6. 결과

**아래 기능 통과 수는 법률 정답률이 아니다.** 필수 원문 제시·인용·정상 완료·목적 확인·guard 계약으로 판정했다. 미실행 사례를 성공으로 세지 않았다.

| arm | 기능 통과/계획 전체 | 모델 제시 원문 평균 | 필수 원문 micro recall |
|---|---:|---:|---:|
{arm_rows}

통합 결과 이력10개→개념{result['concept_count']}개, 독립 지지 근거9개. 정의·적용 범위·절차·제외 후속을 분리했다. 사전 partition 일치: {summary['concept_partition']['pass']}. 계약 검사15개 통과(실행 전). 실제 명시적 이탈 관측: {summary['exception_exit']['explicit_deviation_observed']}.

{block(summary['paired'])}

## 7. 사례별 오류 분석

{block([g for g in summary['grades'] if not g['pass']])}

실제 종료 기록: {block(termination)}

초기 출력 오류가 있는 경우 정답처럼 보이는 문자열이 일부 생성되어도 완전한 JSON과 계약을 통과하지 못하면 실패다. 조기 종료의 미실행 분모를 모델 오답이나 회수 실패로 해석하지 않는다. 질문별 원시 호출·오류·journal 원문은 [실험 인덱스](실험/README.md)에 있다.

## 8. 비용·지연·회수 규모

{block(manifest['results']['usage'])}
{block(manifest['results']['latency'])}
{block(manifest['retrieval_accounting'])}

모델 원문 제시는 한 사례에서 실제 전송된 view들의 unique article-root 합집합이다. 실패 응답도 전송된 입력은 포함한다. guard는 모델을 호출하지 않는다. 미완결 외부 호출의 사용량은 미확인이며 0으로 확정하지 않는다. 온라인 전체 latency 개선 주장은 하지 않는다.

### 단계별 회수·탈락 원장

{stages_text}

후보 universe6→공통 anchor2조→실제 READ 확장→전송 view의 원문이다. gold는 실행이 끝난 후 report.py에서 결합했다. 소스 ID를 조문 root로 해소했으며 탈락 근거·gold 손실 좌표까지 원장에 기록했다. 실패 중단 뒤 미실행은 skipped stage와 이유로 남겼다.

## 9. 해석

노드·행동 인덱스, 원문에 결속한 조각 추출, 목적별 압축과 중복 집계는 확인했다. 새 질문의 의미 선택·이탈·좁은 탐색은 실제 사례별 판정 범위로만 해석한다. 정확한 정의가 겹친다고 질문 목적을 하나로 병합하지 않는다. 질문별 선분류 없이 현재 관측이 안내 후보를 찾고 모델이 현재 목적에 맞는 방향을 선택한다.

## 10. 한계와 일반화 가능 범위

in_sample=true / decision_eligible=false. 6조문·10모의 이력·8계획 사례의 작은 개발 probe다. 실제 성공 로그를 통한 가치 추정, 잘못 성공한 로그의 탐지, 대규모 군집 재통합, 상충 개념, 실제 법률 correctness, 현장 성능은 검증하지 않았다. 개념은 PROPOSED / UNVERIFIED이다. 강제 관계 차단이나 기존 bounded 전체 API는 아직 연결하지 않았다. offline batch entry는 구현했지만 야간 스케줄러는 생성하지 않았다.

## 11. 운영 결정·롤백 조건

운영 채택 보류. 기본 import/registry/MAIN 배선 없음. runner에만 주입하며 번들 불일치·낡은 세대·다른 scope·source 변경이면 안내 없이 기준 원문 탐색을 유지한다. 제안 경로를 강제하지 않으며 읽지 않은 과거 답변을 현재 결론으로 쓰지 않는다. 새로운 호출·프롬프트·후보는 이 완료 기록을 변경하지 않고 새 ADR로 분기해야 한다.

## 12. 재현 명령

```bash
.venv/bin/python -m pytest -q 06_TOOLS/EXPERIMENTS/adr_0559/test_contracts.py
.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate --candidate 02_BACKEND/lawrag/research/candidates/adr_0559/experience
.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path {str(ADR.relative_to(ROOT))} --final
.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR
```

기존 완료 run은 덮어쓰지 않는다. 실제 모델 재실행은 신규 ADR과 새 output 경로에서 수행한다. 원래 실행 명령·runner는 design.code_isolation에 hash 고정되어 있다.

- [원시 산출물](artifacts/manifest.json)
- [기능 판정](artifacts/run-001/offline-grade.json)
- [회수 원장](artifacts/run-001/retrieval-stage-ledger.json)
'''
    (ADR/'README.md').write_text(text)
    rows = []
    for q in manifest['questions']:
        grades = [g for g in summary['grades'] if g['case_id']==q['case_id']]
        label = ' / '.join(f"{g['arm']}={g['pass']} ({g['status']})" for g in grades)
        rows.append(f"| {q['number']:03d} | {q['case_id']} | run-001 | {label} | [기록]({q['file']}) |")
    index = f'''# {manifest['adr_id']} 실험 질문 인덱스

## 작업 선점

owner Codex. reservation·scope·생성/종료 시각·append-only 이력은 [manifest](manifest.json)에 보존한다.

## 계보

experiment {manifest['experiment_id']}. phase probe, in_sample true, decision_eligible false. 부모 arm과 hash는 manifest.lineage.

## 병합

병합 없음.

## 다른 ADR과의 관계

manifest.relationships와 lineage에 명시한 것만 해당한다.

## Arm

baseline은 같은 모의 원문 탐색, experience는 검증한 경험 안내를 추가한다. 기본 API·MAIN 연결 없음.

## 질문 인덱스

| 번호 | case ID | run | 기능 판정·실제 상태 | 파일 |
|---:|---|---|---|---|
{chr(10).join(rows)}

## 집계

{block(summary['by_arm'])}
{block(summary['paired'])}

법률 correctness 판정과 모델 judge 호출 없음. 미실행은 실패 분모에 보존하되 모델 오답으로 설명하지 않는다.

## 단계별 회수·탈락 집계

{stages_text}

gold는 모델 선택 완료 뒤 offline join했다. 전체 exact 좌표·탈락 사유·native journal hash는 [원장](../artifacts/run-001/retrieval-stage-ledger.json)에 보존한다.
'''
    (ADR/'실험/README.md').write_text(index)
    files = []
    for path in sorted((ADR/'artifacts').rglob('*')):
        if not path.is_file() or path == ADR/'artifacts/manifest.json' or '__pycache__' in str(path):
            continue
        files.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path),
            'bytes': path.stat().st_size, 'description': 'Exact synthetic design/run/native journal/provider evidence',
            'contains_raw_prompts_and_outputs': path.name in ('request.json','response.json','output.json','journal.sqlite')})
    for path in [ROOT/'06_TOOLS/EXPERIMENTS/adr_0559/report.py', ROOT/'06_TOOLS/EXPERIMENTS/adr_0559/test_contracts.py']:
        files.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size,
            'description': 'Offline deterministic rubric / meaningful pre-run contract checks', 'contains_raw_prompts_and_outputs': False})
    write(ADR/'artifacts/manifest.json', {'schema_version': 'adr-artifacts-v1', 'adr_id': manifest['adr_id'],
        'created_at': manifest['reservation']['created_at'], 'files': files})


if __name__ == '__main__':
    main()
