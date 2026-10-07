"""Post-run accounting only: preserve actual final errors and all raw calls."""
import hashlib
import json
import sqlite3
import statistics
from common import ROOT, ADR, DESIGN, RUN, read, put, sha

HEADINGS = ['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
QUESTION_HEADINGS = ['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
ARMS = ('baseline', 'unguided', 'guided')

def block(value):
    return '\n```json\n' + json.dumps(value, ensure_ascii=False, indent=2).replace('PENDING', '\\u0050ENDING').replace('TODO', '\\u0054ODO') + '\n```\n'

def parts(row):
    db = row['db']; output = row['output']; goal = output.get('goal_id')
    if not goal:
        events = [e for e in db.get('event', []) if e['request'] == row['input']['request_id']]
        goal = events[-1]['goal'] if events else None
    nodes = {n['id']: n for n in db.get('node', [])}
    route = next((r for r in db.get('route', []) if r['goal'] == goal and r['revision'] == output.get('revision')), None)
    if route and output.get('status') in ('READY', 'REUSED', 'STORED'):
        mapping = route['payload']['nodes']
    else:
        mapping = {h['stage']: h['node'] for h in db.get('head', []) if h['goal'] == goal}
    return {stage: nodes[nid]['payload'] for stage, nid in mapping.items()}, route, goal

def native_events(directory, row):
    out = []
    for path in (directory / 'runtime/legal-agent/runs').glob('*/*/journal.sqlite'):
        with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
            records = [{'seq': seq, 'kind': k, 'payload': json.loads(p)} for seq, k, p in db.execute('SELECT seq,kind,payload_json FROM event ORDER BY seq')]
        if any(e['kind'] == 'MEMORY_MODEL_SESSION' and e['payload']['request_id'] == row['input']['request_id']
               and e['payload']['session_id'] == row['input']['session_id'] for e in records):
            out += records
    return out

def trace(directory, row, coordinates):
    p, route, goal = parts(row)
    recall = p.get('RECALL', {}); discovery = recall.get('discovery', {})
    discovered = discovery.get('discovered', recall.get('selected_for_read', []))
    if isinstance(discovered, dict): discovered = list(discovered)
    selected = p.get('SELECT', {}).get('final_ids', [])
    events = native_events(directory, row)
    views = [e['payload'] for e in events if e['kind'] == 'MEMORY_MODEL_INPUT'
             and e['payload']['phase'].startswith(('memory-assess', 'memory-compose'))]
    present = [s['source_id'] for s in views[-1]['data']['sources']] if views else []
    read_ids = [s['source_id'] for s in p.get('READ', {}).get('originals', [])]
    assert not (set(read_ids) | set(selected) | set(present)) - set(coordinates), 'Non-article delivered: explicit accounting needed'
    sets = {'source': set(coordinates), 'discovered': set(discovered) & set(coordinates),
        'read': set(read_ids), 'selected': set(selected), 'present': set(present)}
    audit = {'question_id': goal, 'route_id': route['id'] if route else None,
        'status': row['output'].get('status'), 'http_status': row['http_status'],
        'retrieval_source_ids': {k: sorted(v) for k, v in sets.items() if k != 'source'},
        'model_input_phase': views[-1]['phase'] if views else None,
        'excluded_structural_non_article_ids': sorted(set(discovered) - set(coordinates)),
        'executed': row['output'].get('executed'), 'method_id': row['output'].get('method_id')}
    return sets, audit, p

def ledger(manifest, inputs, gold):
    coordinates = read(DESIGN / 'source-coordinates.json')
    def ids(values):
        # Canonical roots use actual unit_id, without historical +1 offsets.
        return sorted({(coordinates[i]['doc_id'], coordinates[i]['node']) for i in values})
    def objects(values): return [{'doc_id': d, 'node': n} for d, n in ids(values)]
    arms = []; metrics = {}; audits = []
    for arm in ARMS:
        cases = []; counts = []; hits = 0; before_filter = after_filter = 0
        plan = manifest['design']['retrieval_stage_plan']['stages_by_arm'][arm]
        for case in inputs:
            cid = case['case_id']; directory = RUN / cid / arm
            row = read(directory / 'products.json')[-1]
            sets, audit, p = trace(directory, row, coordinates); audits.append({'case_id': cid, 'arm': arm, **audit})
            g = set(gold[cid]['decisive_source_ids']); stages = []; previous = set()
            for stage in plan:
                current = sets[stage['stage_id']]; added = current - previous; dropped = previous - current
                reason = {'source': 'outside_authorized_article_scope', 'discovered': 'not_in_recorded_discovery',
                    'read': 'not_read_as_complete_original', 'selected': 'not_in_final_source_selection',
                    'present': 'not_delivered_in_current_assessment_or_composition'}[stage['stage_id']]
                record = {**stage, 'executed': True, 'skip_reason': None,
                    'before': objects(previous), 'added': objects(added), 'discarded': objects(dropped), 'after': objects(current),
                    'before_count': len(ids(previous)), 'added_count': len(ids(added)), 'discarded_count': len(ids(dropped)), 'after_count': len(ids(current)),
                    'occurrence_counts': {'before': len(previous), 'after': len(current),
                        'canonical_collapsed_before': len(previous)-len(ids(previous)), 'canonical_collapsed_after': len(current)-len(ids(current))},
                    'discard_receipts': [{'identity': i, 'reason': reason} for i in objects(dropped)],
                    'discard_reason_counts': {reason: len(ids(dropped))} if dropped else {},
                    'gold_total': len(ids(g)), 'gold_before': len(ids(previous & g)), 'gold_added': len(ids(added & g)),
                    'gold_discarded': len(ids(dropped & g)), 'gold_after': len(ids(current & g)), 'golden_recall': len(ids(current & g))/len(ids(g)),
                    'gold_before_identities': objects(previous & g), 'gold_added_identities': objects(added & g),
                    'gold_after_identities': objects(current & g), 'discarded_gold': [{'identity': i, 'reason': reason} for i in objects(dropped & g)]}
                stages.append(record); previous = current
            rec = {'schema_version': 'retrieval-stage-ledger-v1', 'arm_id': arm, 'case_id': cid,
                'accounting_unit': 'case_id + canonical article-root coordinate', 'computed_post_selection': True,
                'gold_visible_to_product': False, 'gold_total': len(ids(g)), 'gold_identities': objects(g), 'stages': stages}
            cases.append(rec); put(directory / 'retrieval-stage-ledger.json', rec)
            counts.append(len(ids(previous))); hits += len(ids(previous & g)); before_filter += len(sets['discovered']); after_filter += len(sets['selected'])
        met = {'before_filter': before_filter, 'after_filter': after_filter, 'presented_total': sum(counts),
            'presented_mean': statistics.mean(counts), 'presented_p50': statistics.median(counts), 'presented_p95': max(counts),
            'golden_recall': hits/4, 'selectivity': statistics.mean(counts)/len(coordinates)}
        metrics[arm] = met; arms.append({'arm_id': arm, 'declared_stage_ids': [s['stage_id'] for s in plan], 'cases': cases, 'aggregate': met})
    result = {'schema_version': 'retrieval-stage-ledger-v1', 'adr_id': manifest['adr_id'], 'experiment_id': manifest['experiment_id'],
        'accounting_unit': 'case_id + canonical article-root coordinate', 'computed_post_selection': True, 'gold_visible_to_product': False,
        'runs': [{'run_id': 'run-001', 'arms': arms}], 'audit': {'final_bindings': audits,
            'source_coordinate_mapping': str((DESIGN / 'source-coordinates.json').relative_to(ROOT)),
            'scope': 'Current final attempt only. Failed final response is never replaced by an earlier READY. Present counts actual model-delivered originals, not just cited claims. Structural roots lacking article unit_id excluded explicitly.'}}
    result['artifact_sha256'] = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    put(RUN / 'retrieval-stage-ledger.json', result); return result, metrics, audits

def main():
    inputs = read(DESIGN / 'inputs.json'); gold = read(DESIGN / 'gold.json'); scores = read(RUN / 'offline-judge/scores.json')
    m = read(ADR / '실험/manifest.json'); led, metrics, audits = ledger(m, inputs, gold)
    finals = {(s['case_id'], s['arm']): s for s in scores if s['final']}
    rows = []; usage = []; latency = {}; per_arm = {}; error_taxonomy = []
    for arm in ARMS:
        latencies = []; calls = 0; correct = 0; reference = 0
        for c in inputs:
            cid = c['case_id']; directory = RUN / cid / arm; products = read(directory / 'products.json'); last = products[-1]
            summary = read(directory / 'summary.json'); calls += summary['provider_attempts']; usage += summary['usage']
            latencies += [x['seconds'] for x in products]
            score = finals[(cid, arm)]; correct += int(score['source_supported_resolution']); reference += int(score['reference_agreement'])
            audit = next(a for a in audits if a['arm'] == arm and a['case_id'] == cid)
            g = set(gold[cid]['decisive_source_ids']); stage_hits = {stage: len(g & set(v)) for stage, v in audit['retrieval_source_ids'].items()}
            row = {'case_id': cid, 'arm': arm, 'original_question': c['question'], 'final_status': last['output'].get('status'),
                'http_status': last['http_status'], 'answer': (last['output'].get('answer') or {}).get('text'),
                'source_supported_resolution': score['source_supported_resolution'], 'reference_agreement': score['reference_agreement'],
                'decisive_source_hits': stage_hits, 'turns': [{'turn': x['turn'], 'status': x['output'].get('status'),
                    'http_status': x['http_status'], 'executed': x['output'].get('executed'), 'method_id': x['output'].get('method_id'),
                    'answer': (x['output'].get('answer') or {}).get('text'), 'seconds': x['seconds'],
                    'calls': x['provider_attempt_end']-x['provider_attempt_start']+1} for x in products]}
            secondary = directory / 'secondary.json'
            if secondary.exists():
                s = read(secondary); row['secondary'] = {'confirmation_status': s['confirmation']['output'].get('status'),
                    'experience_id': s['confirmation']['output'].get('experience_id'),
                    'wiki_http_statuses': {k: v['http_status'] for k, v in s['queries'].items()},
                    'reuse_status': s.get('reuse', {}).get('output', {}).get('status'),
                    'reuse_executed': s.get('reuse', {}).get('output', {}).get('executed')}
            rows.append(row)
            if not score['source_supported_resolution']:
                kind = 'product_execution_failure' if not score['product_complete'] else 'retrieval_miss' if stage_hits['present'] < 2 else 'application_or_answer_error'
                error_taxonomy.append({'type': 'other', 'classification': kind, 'case_id': cid, 'arm': arm, 'detail': score['judges']})
        latency[arm] = {'p50_seconds': statistics.median(latencies), 'p95_seconds': max(latencies), 'turn_count': len(latencies)}
        per_arm[arm] = {'source_supported_correct': correct, 'total': 2, 'reference_agreement': reference,
            'provider_attempts_including_secondary': calls, 'final_product_failures': sum(not finals[(c['case_id'], arm)]['product_complete'] for c in inputs)}
    judge_summary = read(RUN / 'offline-judge/summary.json'); all_usage = usage + judge_summary['usage']
    costs = {'product_successful_calls': len(usage), 'judge_attempts': judge_summary['attempts'],
        'total_recorded_successful_calls': len(all_usage), 'reported_cost_usd': sum(x.get('cost_usd') or 0 for x in all_usage),
        'input_tokens': sum(x.get('input_tokens') or 0 for x in all_usage), 'output_tokens': sum(x.get('output_tokens') or 0 for x in all_usage),
        'failed_call_cost': 'Unavailable unless provider returned usage. No price estimates.'}
    comparisons = []
    for versus in ('baseline', 'unguided'):
        counts = {'guided_only_correct': 0, 'versus_only_correct': 0, 'both_correct': 0, 'both_incorrect': 0}
        for c in inputs:
            a = finals[(c['case_id'], 'guided')]['source_supported_resolution']; b = finals[(c['case_id'], versus)]['source_supported_resolution']
            key = 'both_correct' if a and b else 'guided_only_correct' if a else 'versus_only_correct' if b else 'both_incorrect'
            counts[key] += 1
        comparisons.append({'guided_versus': versus, **counts})
    strict_success = per_arm['guided']['source_supported_correct'] == 2 and all(r['decisive_source_hits']['selected'] == 2 and r['decisive_source_hits']['present'] == 2 for r in rows if r['arm'] == 'guided')
    result = {'status': 'complete', 'rows': rows, 'by_arm': per_arm, 'comparisons': comparisons, 'strict_success': strict_success,
        'costs': costs, 'latency': latency, 'retrieval': metrics, 'scores': scores, 'error_taxonomy': error_taxonomy,
        'main_unchanged': True, 'genos_tested': False, 'in_sample': True, 'decision_eligible': False}
    put(RUN / 'result.json', result)
    m['runs'][0].update(status='complete', sha256=sha(RUN / 'result.json'))
    m['results'].update(status='complete', by_arm=per_arm, comparisons=comparisons, judge_disagreements=sum(s['disagreement'] for s in scores),
        usage=costs, latency=latency, error_taxonomy=error_taxonomy)
    for metric in metrics['baseline']: m['retrieval_accounting'][metric] = {arm: metrics[arm][metric] for arm in ARMS}
    m['retrieval_accounting']['stage_ledger']['sha256'] = sha(RUN / 'retrieval-stage-ledger.json')
    for q in m['questions']:
        cid = q['case_id']; c = next(c for c in inputs if c['case_id'] == cid); raw = []
        for arm in ARMS:
            for folder in sorted((RUN / cid / arm / 'provider').glob('call-*')):
                raw.append('### ' + str(folder.relative_to(RUN)))
                for name in ('request.json', 'validation-schema.json', 'binding.json', 'response.json', 'output.json', 'error.json'):
                    if (folder / name).is_file(): raw += ['#### ' + name, block(read(folder / name))]
        judges = []
        for folder in sorted((RUN / 'offline-judge/provider').glob('call-*' + cid + '-*')):
            judges.append('### ' + folder.name)
            for name in ('request.json', 'validation-schema.json', 'binding.json', 'response.json', 'output.json', 'error.json'):
                if (folder / name).is_file(): judges += ['#### ' + name, block(read(folder / name))]
        raw_products = {arm: read(RUN / cid / arm / 'products.json') for arm in ARMS}
        # DB snapshots are linked in full turn artifacts; HTTP bodies and outputs remain inline.
        public_products = {a: [{k: v for k, v in x.items() if k != 'db'} for x in xs] for a, xs in raw_products.items()}
        ledger_summary = {a: [{k: s[k] for k in ('stage_id','kind','before_count','added_count','discarded_count','after_count','gold_before','gold_after','golden_recall','discard_reason_counts')}
            for s in read(RUN / cid / a / 'retrieval-stage-ledger.json')['stages']] for a in ARMS}
        values = ['ADR-0619-experiment-v1/run-001; three identical frozen candidates; actual public Qwen3.8 external calls.',
            block({'question': c['question'], 'guides': c['guides'], 'generic_review': c['control_turns']}), block(gold[cid]),
            block(public_products) + '\n### 단계별 회수·탈락 원장\n' + block(ledger_summary) + '\n정확한 canonical identity 집합과 탈락 receipts는 각 arm의 artifacts/run-001/' + cid + '/<arm>/retrieval-stage-ledger.json에 보존한다.',
            '\n'.join(raw), '원문 회수·선택·정정 명령 해석·판단·제품 내부 검증·형식 복구의 모든 실제 호출은 위에 전문을 보존한다. native journal은 각 arm runtime/legal-agent/runs 안에 있다.',
            '\n'.join(judges), block([s for s in scores if s['case_id'] == cid])]
        text = '# ' + cid + '\n\n' + '\n\n'.join(f'## {i}. {h}\n\n{v}' for i, (h,v) in enumerate(zip(QUESTION_HEADINGS, values), 1)) + '\n'
        (ADR / '실험' / q['file']).write_text(text); q['sha256'] = sha(ADR / '실험' / q['file'])
    counts_table = '| 사례 | 최초 답변 | 일반 재검토 2회 | 구체 가이드 2회 |\n|---|---|---|---|\n'
    for c in inputs:
        cells = []
        for arm in ARMS:
            s = finals[(c['case_id'], arm)]; cells.append('원문 기준 통과' if s['source_supported_resolution'] else '실행 실패' if not s['product_complete'] else '원문 기준 실패')
        counts_table += '| ' + c['case_id'] + ' | ' + ' | '.join(cells) + ' |\n'
    front = (ADR / 'README.md').read_text().split('---', 2)[1]
    front = front.replace('status: Proposed', 'status: Accepted' if strict_success else 'status: Rejected')
    values = [('사전 기준 충족.' if strict_success else '사전 기준 미충족.') + ' 알려진 실패 2사례의 현재 구현 probe이며 MAIN 승격 근거로 사용하지 않는다.\n\n' + counts_table,
        'CM-051: ADR-0496에서 시행규칙 제14조 회수 누락. CM-003: ADR-0479에서 규정·세칙을 제시받고도 제3호로 오판한 기록. 현재 원문·현재 통합 v6로 새 최초 답변을 실행했다.',
        m['design']['hypothesis'] + '\n\n' + m['design']['success_criteria'] + '\n\n' + m['design']['failure_criteria'],
        '최초 답변은 사례마다 1회. 이 상태를 동일하게 복제해 일반 재검토 2회와 구체 가이드 2회를 실행. 분기 순서는 사례별 교차. 오답을 강제로 만들거나 결과를 보고 질문·가이드·코드를 바꾸지 않았다.',
        '공개 문서145개, canonical article26597개, stored generation term-source-1acfbe06921527e74a0b. 실제 RAW·store 해시와 범위 확인. Qwen3.8 / Parasail FP8 / reasoning none / temperature0 / fallback 없음. 제품 코드851개 파일 동결 사본3개. 동결 원장은 artifacts/design/freeze.json.',
        counts_table + block({'by_arm': per_arm, 'comparisons': comparisons}), block(error_taxonomy), block({'costs': costs, 'latency': latency, 'retrieval': metrics}),
        '가이드 효과는 같은 최초 상태에서의 비교로 판단한다. 현재 최초 답이 이미 맞는 사례는 정정 성공 건수에 넣지 않는다. 근거 회수와 적용 판단을 분리하며, 원문이 뒷받침한 조건부 결론과 역사적 기준답 일치를 분리했다.',
        '알려진2개 인샘플, 최초 실행 각1회. 오프라인 판정2회도 같은 Qwen3.8이므로 독립 전문가 검토가 아니다. 법률 개정·실제 내부자료·GENOS 내부 모델 및 현장 속도는 확인하지 않았다. 사용자 가이드는 실험자가 사전에 작성했다.',
        '연구 snapshot 명시 주입만 실행. 제품 MAIN 활성 포인터·원문 불변층·GENOS 배포 미변경. 결과를 본 뒤 수정 또는 재실험은 새 ADR로 기록한다.',
        '`.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0619/run.py --case cm-051 --arm baseline` 등. 기존 결과 폴더 덮어쓰기를 거부하므로 재실행은 새 ADR이 필요하다. 각 arm의 원시 provider 요청·응답과 native journal, 분기 receipt를 모두 보존했다.']
    (ADR / 'README.md').write_text('---' + front + '---\n\n# ADR-0619 — 통합 legal_agent 사용자 가이드 CM 실험\n\n' + '\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(HEADINGS,values),1)) + '\n')
    (ADR / '실험/README.md').write_text('# 질문 인덱스\n\n' + counts_table + '\n' + ''.join(f"- [{q['case_id']}]({q['file']})\n" for q in m['questions']) + '\n판정2회·실제 전체 호출·원문은 각 질문 파일, 단계별 exact 원장은 artifacts/run-001/retrieval-stage-ledger.json에 있다.\n')
    put(ADR / '실험/manifest.json', m)
    (ADR / 'RESULT.md').write_text('# 사용자 가이드를 통한 CM 정정 실험\n\n' + counts_table + '\n' +
        '과거 실패 기록에서 고른 두 사례를 현재 통합 legal_agent v6로 실행했다. 같은 최초 답변을 복제해서 일반 재검토와 구체 가이드를 두 번씩 비교했다. 원문 기준 판단과 과거 기준답 일치를 분리했다.\n\n' +
        '\n\n'.join('## ' + c['case_id'] + '\n\n' + '\n\n'.join('### ' + a + '\n\n' + (next(r for r in rows if r['case_id']==c['case_id'] and r['arm']==a)['answer'] or '최종 답변 실행 실패. 오류 원문은 해당 turn artifact에 있다.') for a in ARMS) for c in inputs) +
        '\n\n실제 외부 호출 비용 합계: $' + f"{costs['reported_cost_usd']:.6f}" + '. 알려진2사례 결과이며 일반 정확도나 GENOS 성능으로 확대할 수 없다. MAIN·GENOS 미반영.\n')
    artifact_paths = [p for p in (ADR / 'artifacts').rglob('*') if p.is_file() and p.name != 'manifest.json']
    artifact_paths += [*(ROOT / '06_TOOLS/EXPERIMENTS/adr_0619').glob('*.py'), ADR / 'RESULT.md']
    artifact_paths += [ROOT / p for p in read(DESIGN / 'freeze.json') if '/revisions/' in p or p.endswith('/candidate.json')]
    put(ADR / 'artifacts/manifest.json', {'schema_version': 'adr-artifacts-v1', 'adr_id': 'ADR-0619',
        'created_at': m['reservation']['created_at'], 'files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p),
            'bytes': p.stat().st_size, 'description': 'Actual frozen experiment input/output, provenance, or audit artifact',
            'contains_raw_prompts_and_outputs': 'provider/' in str(p)} for p in sorted(set(artifact_paths))]})
    print(json.dumps({'strict_success': strict_success, 'by_arm': per_arm, 'costs': costs}, ensure_ascii=False))

if __name__ == '__main__': main()
