"""ADR-0473 보고: run 완료 표시, 집계(metrics.json), 질문 파일·질문 인덱스. 모델을 부르지 않는다.

    .venv/bin/python <this> finalize    # S2 run-002·003을 complete로(모든 문항 답·채점이 있을 때만)
    .venv/bin/python <this> score       # artifacts/metrics.json
    .venv/bin/python <this> questions   # 실험/질문-NNN-cm-XXX.md, 실험/README.md 질문 표, manifest questions
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0473-legal-agent-loop-rev4'
ART = ADR / 'artifacts'
ADR72 = ROOT / '04_EXPERIMENTS/ADR/ADR-0472-legal-agent-loop-rev3/artifacts'
POLICY = ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'
S2_ARMS = ['loop4-flash', 'loop4-qwen']
S2_RUNS = ['run-002', 'run-003']
S1_ARMS = ['s1-flash-control', 's1-flash-pairs', 's1-qwen-control', 's1-qwen-pairs']
REFERENCE = ['ref-loop3-flash', 'ref-loop3-qwen', 'ref-loop2c-qwen']
PRIMARY_REF = {'loop4-flash': 'ref-loop3-flash', 'loop4-qwen': 'ref-loop2c-qwen'}
SECONDARY_REF = {'loop4-qwen': 'ref-loop3-qwen'}
THRESHOLD = {'loop4-flash': (42, 2), 'loop4-qwen': (36, 3)}       # H1·H2: 2회 평균 ≥, 매 회 회귀 ≤


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path: Path):
    return json.loads(Path(path).read_text())


def write(path: Path, obj) -> None:
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + '\n')
    tmp.replace(path)


def now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def load():
    return (read(ART / 'frozen-inputs.json'), read(ART / 'loop-results.json')['results'],
            read(ART / 'replay-results.json')['results'], read(ART / 'judged-results.json')['results'],
            read(ART / 's1-gate.json'))


def verdicts(judged, arm, run, cases):
    return {c: ((judged.get(f'{c}::{arm}::{run}') or {}).get('output') or {}).get('correct') for c in cases}


# ── run 완료 ─────────────────────────────────────────────────────────────
def finalize() -> None:
    frozen, loops, _, judged, _ = load()
    cases = [c['case_id'] for c in frozen['cases']]
    for run in S2_RUNS:
        for arm in S2_ARMS:
            for cid in cases:
                row = loops.get(f'{cid}::{arm}::{run}')
                if row is None or row['error']:
                    raise SystemExit(f'incomplete loop result: {cid} {arm} {run}')
                if (judged.get(f'{cid}::{arm}::{run}') or {}).get('output') is None:
                    raise SystemExit(f'missing judgement: {cid} {arm} {run}')
    for cid in cases:
        for ref in REFERENCE:
            if (judged.get(f'{cid}::{ref}::run-002') or {}).get('output') is None:
                raise SystemExit(f'missing reference judgement: {cid} {ref}')
    path = ADR / '실험/manifest.json'
    manifest = read(path)
    for run in manifest['runs']:
        if run['id'] in S2_RUNS:
            run.update({'status': 'complete', 'artifact_path': str((ART / 'loop-results.json').relative_to(ROOT)),
                        'sha256': sha(ART / 'loop-results.json'), 'completed_at': now()})
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('run-002·run-003 complete')


# ── 집계 ─────────────────────────────────────────────────────────────────
def score() -> None:
    frozen, loops, replayed, judged, gate = load()
    price = read(POLICY)['price_snapshot']
    cases = [c['case_id'] for c in frozen['cases']]
    decisive = {c['case_id']: set(c['decisive_source_ids']) for c in frozen['cases']}
    total_dec = sum(len(v) for v in decisive.values())

    def gemini_cost(usage):
        return sum(((u.get('input_tokens') or 0) * price['input']
                    + ((u.get('output_tokens') or 0) + (u.get('thinking_tokens') or 0)) * price['output']) / 1e6
                   for u in usage if u.get('provider') == 'gemini')

    def pct(values, q):
        values = sorted(values)
        return values[min(len(values) - 1, max(0, round((len(values) - 1) * q)))] if values else None

    by_arm = {ref: {'run-002': sum(v is True for v in verdicts(judged, ref, 'run-002', cases).values())} for ref in REFERENCE}
    s1 = {}
    for arm in S1_ARMS:
        rows = {k: v for k, v in replayed.items() if v['arm'] == arm}
        sample = sorted(v['case_id'] for v in rows.values())
        vv = verdicts(judged, arm, 'run-001', sample)
        usage = [u for v in rows.values() for u in v['usage']]
        s1[arm] = {'cases': len(sample), 'correct': sum(v is True for v in vv.values()),
                   'cost_usd': round(sum(u.get('cost_usd') or 0 for u in usage) + gemini_cost(usage), 4)}
        by_arm[arm] = {'run-001': s1[arm]['correct']}
    detail = {}
    for arm in S2_ARMS:
        per_run = {}
        for run in S2_RUNS:
            rows = [loops[f'{c}::{arm}::{run}'] for c in cases]
            v = verdicts(judged, arm, run, cases)
            ref = verdicts(judged, PRIMARY_REF[arm], 'run-002', cases)
            usage = [u for x in rows for u in x['usage']]
            rounds = [t for x in rows for t in x['trace'] if t.get('step') == 'round']
            listing_adopt = {x['case_id']: [c['label'] for c in x['cards'] if c['handle'] in
                                            {h for t in x['trace'] if t.get('step') == 'round' for h in t['listing_adopted']}]
                             for x in rows if any(t.get('listing_adopted') for t in x['trace'] if t.get('step') == 'round')}
            listing_adopt_decisive = sorted(
                x['case_id'] for x in rows for c in x['cards']
                if c['handle'] in {h for t in x['trace'] if t.get('step') == 'round' for h in t['listing_adopted']}
                and c['source_id'] in decisive[x['case_id']])
            finals = {x['case_id']: {'adopted': [c['label'] for c in x['cards'] if c['handle'] in x['final_pick_adopted']],
                                     'decisive': sorted(c['label'] for c in x['cards'] if c['handle'] in x['final_pick_adopted']
                                                        and c['source_id'] in decisive[x['case_id']]),
                                     'fallback': x['fallback']} for x in rows if x['final_pick']}
            calls = sorted(x['calls'] for x in rows)
            seconds = [u['seconds'] for u in usage if u.get('seconds') is not None]
            item = {
                'score': sum(val is True for val in v.values()),
                'reference': PRIMARY_REF[arm], 'reference_score': sum(val is True for val in ref.values()),
                'new_vs_reference': sorted(c for c in cases if v[c] and not ref[c]),
                'lost_vs_reference': sorted(c for c in cases if ref[c] and not v[c]),
                'both_correct': sum(1 for c in cases if v[c] and ref[c]),
                'both_wrong': sum(1 for c in cases if not v[c] and not ref[c]),
                'decisive_shown': sum(len(decisive[x['case_id']] & set(x['shown_source_ids'])) for x in rows),
                'decisive_adopted': sum(len(decisive[x['case_id']] & set(x['adopted_source_ids'])) for x in rows),
                'decisive_evidence': sum(len(decisive[x['case_id']] & set(x['evidence_source_ids'])) for x in rows),
                'decisive_total': total_dec,
                'listing_adopt_cases': listing_adopt, 'listing_adopt_decisive_cases': listing_adopt_decisive,
                'final_pick_cases': finals, 'fallback_cases': sorted(x['case_id'] for x in rows if x['fallback']),
                'listing_closed_cases': sorted(x['case_id'] for x in rows if x['listing_closed']),
                'listing_taken_max': max(x['listing_taken_total'] for x in rows),
                'listing_refused': sum(len(t['listing_refused']) for t in rounds),
                'listing_dropped': sum(len(t['listing_dropped']) for t in rounds),
                'unknown_handles': sum(len(t['unknown_handles']) for t in rounds),
                'deferrals': sum(x['deferrals'] for x in rows),
                'paired': sum(len(x['paired']) for x in rows),
                'calls_median': statistics.median(calls), 'calls_max': calls[-1], 'calls_total': sum(calls),
                'repairs': sum(1 for u in usage if str(u.get('phase', '')).endswith('-repair')),
                'input_tokens': sum(u.get('input_tokens') or 0 for u in usage),
                'output_tokens': sum(u.get('output_tokens') or 0 for u in usage),
                'cost_usd_recorded': round(sum(u.get('cost_usd') or 0 for u in usage), 4),
                'cost_usd_gemini_estimated': round(gemini_cost(usage), 4),
                'seconds_p50': pct(seconds, .5), 'seconds_p95': pct(seconds, .95),
                'short_answers': sorted(x['case_id'] for x in rows if len(x['text']) <= 30),
                'failure_types': {}}
            for c in cases:
                if v[c] is False:
                    ft = judged[f'{c}::{arm}::{run}']['output']['failure_type']
                    item['failure_types'][ft] = item['failure_types'].get(ft, 0) + 1
            if arm in SECONDARY_REF:
                sec = verdicts(judged, SECONDARY_REF[arm], 'run-002', cases)
                item['secondary'] = {'reference': SECONDARY_REF[arm], 'reference_score': sum(val is True for val in sec.values()),
                                     'new': sorted(c for c in cases if v[c] and not sec[c]),
                                     'lost': sorted(c for c in cases if sec[c] and not v[c])}
            per_run[run] = item
        runs_v = {run: verdicts(judged, arm, run, cases) for run in S2_RUNS}
        mean = statistics.mean(per_run[r]['score'] for r in S2_RUNS)
        need, max_lost = THRESHOLD[arm]
        detail[arm] = {'runs': per_run, 'mean': mean,
                       'flips_between_runs': sorted(c for c in cases if runs_v['run-002'][c] != runs_v['run-003'][c]),
                       'correct_both_runs': sum(1 for c in cases if runs_v['run-002'][c] and runs_v['run-003'][c]),
                       'criterion': {'mean_at_least': need, 'lost_per_run_at_most': max_lost,
                                     'passed': mean >= need and all(len(per_run[r]['lost_vs_reference']) <= max_lost
                                                                    for r in S2_RUNS)},
                       'failure_rule': {'reference_minus_2': per_run['run-002']['reference_score'] - 2,
                                        'triggered': mean <= per_run['run-002']['reference_score'] - 2}}
        by_arm[arm] = {r: per_run[r]['score'] for r in S2_RUNS}
    h4 = {f'{arm}/{run}': {'calls_median': detail[arm]['runs'][run]['calls_median'],
                           'cost_usd': detail[arm]['runs'][run]['cost_usd_recorded']} for arm in S2_ARMS for run in S2_RUNS}
    criteria = {
        'S1-G': f"{'pass' if gate['passed'] else 'fail'} (목표 회복 {gate['recovered_targets']}, 회귀 {gate['report']['s1-flash']['regressed']})",
        'H1': detail['loop4-flash']['criterion'], 'H2': detail['loop4-qwen']['criterion'],
        'H3': 'n/a — S1-G 미달로 C4를 끄고 loop4-flash-nopair를 돌리지 않음' if not gate['passed'] else 'see detail',
        'H4': {'passed': all(v['calls_median'] <= 4 for v in h4.values())
               and all(v['cost_usd'] <= 0.5 for k, v in h4.items() if k.startswith('loop4-qwen')), 'values': h4}}
    judge_usage = [u for r in judged.values() for u in r['usage']]
    metrics = {'schema_version': 'adr0473-metrics-v1', 'by_arm': by_arm, 's1': s1, 's1_gate': gate, 'detail': detail,
               'criteria': criteria,
               'judge': {'calls': len(judge_usage), 'errors': sorted(k for k, r in judged.items() if r['output'] is None),
                         'cost_usd_gemini_estimated': round(gemini_cost(judge_usage), 4)},
               'price_snapshot': price}
    write(ART / 'metrics.json', metrics)
    print(json.dumps(by_arm, ensure_ascii=False))
    for arm in S2_ARMS:
        d = detail[arm]
        print(arm, 'mean', d['mean'], 'flips', d['flips_between_runs'], 'criterion', d['criterion']['passed'])
        for run in S2_RUNS:
            r = d['runs'][run]
            print(' ', run, {k: r[k] for k in ('score', 'reference_score', 'new_vs_reference', 'lost_vs_reference',
                                               'decisive_shown', 'decisive_evidence', 'fallback_cases', 'calls_median',
                                               'cost_usd_recorded', 'cost_usd_gemini_estimated')})
            print('    listing_adopt', r['listing_adopt_cases'], 'decisive', r['listing_adopt_decisive_cases'])
            print('    final_pick', r['final_pick_cases'], 'closed', r['listing_closed_cases'])
            if 'secondary' in r:
                print('    vs', r['secondary'])
    print('criteria', json.dumps({k: (v if isinstance(v, str) else v.get('passed')) for k, v in criteria.items()}, ensure_ascii=False))


# ── 질문 파일 ────────────────────────────────────────────────────────────
def questions() -> None:
    frozen, loops, replayed, judged, gate = load()
    ledger = read(ART / 'retrieval-stage-ledger.json')
    manifest_path = ADR / '실험/manifest.json'
    manifest = read(manifest_path)
    cases = frozen['cases']
    calls_index: dict[str, list[str]] = {}
    for d in sorted((ART / 'calls').glob('run-*/*/worker-*/call-*')):
        m = re.match(r'call-\d+-(?:loop|replay)-(cm-\d+)', d.name)
        if m:
            calls_index.setdefault(f'{m.group(1)}::{d.parent.parent.name}::{d.parent.parent.parent.name}', []).append(
                str(d.relative_to(ADR)))
    judge_index: dict[str, list[str]] = {}
    for d in sorted((ART / 'judge-calls').glob('*/worker-*/call-*')):
        m = re.match(r'call-\d+-judge-(cm-\d+)-(.+)-(run-\d+)$', d.name)
        if m:
            judge_index.setdefault(f'{m.group(1)}::{m.group(2)}::{m.group(3)}', []).append(str(d.relative_to(ADR)))
    stage_rows = {}
    for run in ledger['runs']:
        for arm in run['arms']:
            for case in arm['cases']:
                stage_rows[(run['run_id'], arm['arm_id'], case['case_id'])] = case['stages']
    sample = {arm: set(frozen['s1_sample'][src]) for arm, src in
              (('s1-flash-control', 'loop3-flash'), ('s1-flash-pairs', 'loop3-flash'),
               ('s1-qwen-control', 'loop3-qwen'), ('s1-qwen-pairs', 'loop3-qwen'))}
    entries, index_rows = [], []
    for number, case in enumerate(cases, start=1):
        cid = case['case_id']
        decisive = set(case['decisive_source_ids'])
        s1_keys = [(arm, 'run-001') for arm in S1_ARMS if cid in sample[arm]]
        s2_keys = [(arm, run) for run in S2_RUNS for arm in S2_ARMS]
        ref_keys = [(ref, 'run-002') for ref in REFERENCE]
        all_keys = s1_keys + s2_keys + ref_keys
        lines = [f'# 질문 {number:03d} — {cid}', '', '## 1. 실행 메타', '',
                 f"- ADR: `{manifest['adr_id']}`", f"- experiment: `{manifest['experiment_id']}`", f'- case ID: `{cid}`',
                 f"- run ID: {'`run-001`(S1 재생), ' if s1_keys else ''}`run-002`, `run-003`(S2 E2E), 참고 arm 재채점은 `run-002` 배치",
                 '- 실행 시각(UTC, run 완료): ' + ', '.join(f"{r['id']} `{r.get('completed_at')}`" for r in manifest['runs']),
                 '- 원본 상태: `exact` (루프·조립·채점 호출 원문 calls/·judge-calls/ 보존)',
                 '- 제품 호출 모델: `gemini-3.1-flash-lite`(loop4-flash, s1-flash-*), `qwen/qwen3.5-122b-a10b` OpenRouter FP8(loop4-qwen, s1-qwen-*)',
                 '- 오프라인 평가 모델: `gemini-3.1-flash-lite`',
                 f"- 실행 arm: {', '.join(f'`{a}`' for a, _ in dict.fromkeys(all_keys))}",
                 f"- S1 관문: {'통과' if gate['passed'] else '미달'} → S2 loop4-flash 위임 짝(C4) {'켬' if gate['c4_on_for_loop4_flash'] else '끔'}", '',
                 '## 2. 사용자 질문 원문', '', '```text', case['question'], '```', '',
                 '## 3. 기준답변 — 채점 전용, 제품 입력 비공개', '', '```text', case['reference_answer'], '```', '',
                 '## 4. 제품 입력을 구성한 원값', '', '### 회수 전 전체·후보·제시 규모', '', '```json',
                 json.dumps({'corpus_total': 17637, 'decisive': len(decisive)}), '```', '',
                 '### 회수 좌표·조문·정의·Wiki·관계 — 전체', '']
        for arm, run in s1_keys:
            row = replayed[f'{cid}::{arm}::{run}']
            lines += [f'{run} / {arm} 조립기 입력(ADR-0472 채택 원문{" + 위임 짝" if arm.endswith("pairs") else ""}):', '', '```json',
                      json.dumps({'evidence_source_ids': row['evidence_source_ids'], 'paired': row['paired']}, ensure_ascii=False),
                      '```', '']
        for arm, run in s2_keys:
            row = loops[f'{cid}::{arm}::{run}']
            lines += [f'{run} / {arm} 카드:', '', '```json', json.dumps(
                [{'handle': c['handle'], 'via': c['via'], 'label': c['label'], 'adopted': c['adopted'],
                  'dropped': c['dropped'], 'decisive': c['source_id'] in decisive} for c in row['cards']],
                ensure_ascii=False), '```', '']
        lines += ['### 회수·탈락 단계 원장 — run·arm별', '',
                  '| run | arm | stage | kind | 실행 | before | +added | -discarded | after | gold before | gold + | gold - | gold after/total | recall | 대표 탈락 이유 |',
                  '|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
        for arm, run in s1_keys + s2_keys:
            for s in stage_rows.get((run, arm, cid), []):
                reasons = ', '.join(f'{k}:{v}' for k, v in s['discard_reason_counts'].items()) or '-'
                recall = '-' if s['golden_recall'] is None else f"{s['golden_recall']:.2f}"
                lines.append(f"| {run} | {arm} | {s['stage_id']} | {s['kind']} | {'예' if s['executed'] else '아니오'} | "
                             f"{s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} | "
                             f"{s['gold_before']} | {s['gold_added']} | {s['gold_discarded']} | {s['gold_after']}/{s['gold_total']} | "
                             f"{recall} | {reasons} |")
        lines += ['', '```json', json.dumps({'stage_ledger_artifact': 'artifacts/retrieval-stage-ledger.json',
                                             'gold_visible_to_product': False}), '```', '',
                  '## 5. 제품 모델 호출 — run·arm별 실제 원문', '']
        for arm, run in all_keys:
            lines += [f'### {run} / {arm} / system', '']
            if arm in REFERENCE:
                lines += ['```text', f'제품 호출 없음(저장된 답 재채점: {frozen["reference_arms"][arm]})', '```', '']
            else:
                lines += ['루프 SYSTEM·STEP_SCHEMA·FINAL_SYSTEM과 조립기 system 원문은 호출 디렉터리의 request.json: '
                          + ', '.join(calls_index.get(f'{cid}::{arm}::{run}', [])), '']
            lines += [f'### {run} / {arm} / user', '', '```text', case['question'], '```', '',
                      f'### {run} / {arm} / schema·tool', '', '```json',
                      'null' if arm in REFERENCE else json.dumps(
                          'legal_agent.loop rev-004 STEP_SCHEMA·FINAL_SCHEMA + composer plain' if arm.startswith('loop4')
                          else 'composer plain PLAIN_SCHEMA', ensure_ascii=False), '```', '',
                      f'### {run} / {arm} / provider 원응답·structured output·usage·지연', '']
            if arm in REFERENCE:
                lines += ['```text', case['reference_texts'][arm], '```', '']
                continue
            row = (replayed if run == 'run-001' else loops)[f'{cid}::{arm}::{run}']
            lines += ['사용자 표시 답(채점 대상):', '', '```text', row['text'], '```', '']
            keys = ('error', 'calls', 'usage') if run == 'run-001' else (
                'error', 'calls', 'rounds', 'deferrals', 'fallback', 'final_pick', 'final_pick_adopted', 'paired',
                'listing_taken_total', 'listing_closed', 'trace', 'usage')
            lines += ['```json', json.dumps({k: row.get(k) for k in keys}, ensure_ascii=False, indent=1), '```', '']
        lines += ['## 6. 중간 LLM 호출 — router/compiler/verifier/repair', '', '```json', json.dumps(
            [{'run': run, 'arm': arm, 'phases': [u['phase'] for u in ((replayed if run == 'run-001' else loops)
                                                                      [f'{cid}::{arm}::{run}']['usage'])]}
             for arm, run in s1_keys + s2_keys], ensure_ascii=False), '```', '',
                  '## 7. 채점 호출과 반복 판정', '', '### judge system/user — 기준답변 포함', '', '```json',
                  json.dumps({'judge_system_sha256': frozen['judge_system_sha256'], 'requests': [
                      {'key': f'{cid}::{arm}::{run}', 'user_sha256': judged[f'{cid}::{arm}::{run}']['user_sha256'],
                       'call_dirs': judge_index.get(f'{cid}::{arm}::{run}', [])} for arm, run in all_keys]},
                             ensure_ascii=False, indent=1), '```', '', '### judge 원응답과 최종 다수결', '', '```json',
                  json.dumps({f'{cid}::{arm}::{run}': {'output': judged[f'{cid}::{arm}::{run}']['output'],
                                                        'attempts': judged[f'{cid}::{arm}::{run}']['attempts']}
                              for arm, run in all_keys}, ensure_ascii=False, indent=1), '```', '',
                  '## 8. 사례 최종 판정', '', '| run | arm | 정답 | 핵심 근거 | 실패 유형 |', '|---|---|---:|---|---|']
        verdict = {}
        for arm, run in all_keys:
            o = judged[f'{cid}::{arm}::{run}']['output'] or {}
            verdict[(arm, run)] = o.get('correct')
            lines.append(f"| {run} | {arm} | {'O' if o.get('correct') else 'X'} | {(o.get('reason') or '')[:120]} | "
                         f"{o.get('failure_type', '-')} |")
        notes = []
        for arm in S2_ARMS:
            ref = PRIMARY_REF[arm]
            for run in S2_RUNS:
                if verdict[(arm, run)] and not verdict[(ref, 'run-002')]:
                    notes.append(f'{arm} {run} 신규(대 {ref})')
                elif verdict[(ref, 'run-002')] and not verdict[(arm, run)]:
                    notes.append(f'{arm} {run} 회귀(대 {ref})')
        for base in ('s1-flash', 's1-qwen'):
            if (f'{base}-control', 'run-001') in verdict:
                c, p = verdict[(f'{base}-control', 'run-001')], verdict[(f'{base}-pairs', 'run-001')]
                if c != p:
                    notes.append(f"{base} 위임 짝 {'회복' if p else '회귀'}")
        lines += ['', f"- 사전 지정 비교쌍의 신규 정답·회귀: {', '.join(notes) or '변화 없음'}",
                  f"- 공통 실패 유형: loop4-flash run-002 기준 `{(judged[f'{cid}::loop4-flash::run-002']['output'] or {}).get('failure_type', '-')}`",
                  '- 사람이 확인한 직접 원인: 미확인(모델 채점만)', '']
        name = f'질문-{number:03d}-{cid}.md'
        path = ADR / '실험' / name
        path.write_text('\n'.join(lines) + '\n')
        entries.append({'number': number, 'case_id': cid, 'file': name, 'sha256': sha(path)})
        cells = ' / '.join(f"{a}:{'O' if verdict[(a, r)] else 'X'}" for a, r in s2_keys)
        refs = ' / '.join(f"{a}:{'O' if verdict[(a, 'run-002')] else 'X'}" for a in REFERENCE)
        s1cell = ' / '.join(f"{a}:{'O' if verdict[(a, 'run-001')] else 'X'}" for a, _ in s1_keys) or '-'
        index_rows.append(f"| {number:03d} | `{cid}` | {cells} | {refs} | {s1cell} | {', '.join(notes) or '-'} | [{name}]({name}) |")
    manifest['questions'] = entries
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    readme = ADR / '실험/README.md'
    text = readme.read_text()
    head = text.split('## 계보')[0]
    lineage, design = manifest['lineage'], manifest['design']
    parent = lineage['parents'][0]
    head += '\n'.join([
        '## 계보', '', f"- experiment ID: `{manifest['experiment_id']}`", f"- branch: `{lineage['branch_id']}`",
        f"- parent arm: `{parent['experiment_id']}/{parent['arm_id']}` ({parent['relation']})",
        f"- 이 분기의 변경 가설: {lineage['hypothesis_delta']}", '', '## 병합', '', '- merge: 해당 없음', '',
        '## 다른 ADR과의 관계', '',
        *[f"- `{r['relation']}` → `{r['adr_id']}`: {r['note']}" for r in manifest['relationships']], '',
        '## Arm', '', '| arm ID | 역할 | 직접 부모 | 바뀐 것 | 고정한 것 | 실행 |', '|---|---|---|---|---|---|',
        *[f"| `{a['id']}` | {a['role']} | {', '.join(a['derived_from'])} | {a['changes']} | {a['controls']} | "
          f"{', '.join(r['id'] for r in manifest['runs'] if a['id'] in r['arm_ids']) or ('참고 arm 재채점(run-002 배치)' if a['id'] == 'baseline' else '실행 안 함(S1-G 미달)')} |"
          for a in design['arms']], '', ''])
    table = ['## 질문 인덱스', '',
             'S2 칸은 run-002·run-003 순서, 참고 칸은 같은 판정 배치의 재채점(run-002), S1 칸은 C4 대상 문항만.', '',
             '| 번호 | case ID | S2 loop4 판정 | 참고 arm 판정 | S1 재생 판정 | 비교쌍 신규·회귀 | 파일 |',
             '|---|---|---|---|---|---|---|', *index_rows, '']
    readme.write_text(head + '\n'.join(table))
    print(f'wrote {len(entries)} question files')


if __name__ == '__main__':
    {'finalize': finalize, 'score': score, 'questions': questions}[sys.argv[1]]()
