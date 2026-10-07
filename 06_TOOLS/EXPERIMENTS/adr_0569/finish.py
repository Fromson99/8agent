"""Offline phase attribution and gate audit. Product outputs remain immutable."""
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree
import hashlib
import json
import statistics

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0569-compact-plan-smallpool'
O = A / 'artifacts/run-001'
ARMS = ['baseline', 'compact', 'combined']
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, v): p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')
def block(v): return '```json\n' + json.dumps(v, ensure_ascii=False, indent=2) + '\n```\n'


def main():
    m = read(A / '실험/manifest.json'); data = read(O / 'result.json'); grade = read(O / 'offline-grade.json')
    assert data['status'] == 'complete'
    for r in data['results']:
        assert r == read(O / 'cases' / r['case_id'] / r['arm'] / 'result.json')
    totals = {}; small = []; mixed = {}; drift = {}; sql = []; current = []
    for line in (A / 'artifacts/live-console.log').read_text().splitlines():
        try: v = json.loads(line)
        except ValueError: continue
        if v.get('event') == 'fulltext.sql.timings': current.append(v)
        if 'case' in v and 'arm' in v:
            sql.append({'case_id':v['case'], 'arm':v['arm'], 'rank_calls':len(current),
                'fetched_rows':sum(x['fetched_count'] for x in current),
                'sql_seconds':sum(sum(x.get(k, 0) for k in ['sql_execute_ms','sql_first_row_ms','sql_fetch_ms']) for x in current)/1000})
            current = []
    assert len(sql) == 21 and not current
    for arm in ARMS:
        rs = [r for r in data['results'] if r['arm'] == arm]
        phases = defaultdict(lambda: {'calls':0, 'seconds':0, 'input_tokens':0, 'output_tokens':0})
        for r in rs:
            for u in r['usage']:
                x = phases[u['phase']]; x['calls'] += 1
                for k in ['seconds', 'input_tokens', 'output_tokens']: x[k] += u.get(k) or 0
            p = O / 'cases' / r['case_id'] / arm / 'selection.json'
            if p.exists():
                s = read(p)
                if s.get('small_pool_full_originals'):
                    request = read(next((p.parent / 'calls').glob('call-*-source-triage/request.json')))
                    wire = json.loads(next(msg['content'] for msg in request['messages'] if msg['role'] == 'user'))
                    cards = wire.get('originals', [])
                    full = (cards == s['actual_selector_excerpts'][0]['cards']
                        and {s['label_to_source'][c['id']] for c in cards} == set(s['all_source_ids'])
                        and all(len(c['excerpts']) == 1 and c['excerpts'][0]['start'] == 0
                            and c['excerpts'][0]['end'] == c['total_chars'] == len(c['excerpts'][0]['text']) for c in cards))
                    review_count = sum(u['phase'] == 'source-omission-review' for u in r['usage'])
                    small.append({'case_id':r['case_id'], 'arm':arm, 'wire_full_originals':full,
                        'candidate_count':len(cards), 'omission_review_calls':review_count,
                        'selection_calls':sum(u['phase'].startswith('source-') and u['phase'] != 'source-query-plan' for u in r['usage'])})
        times = [r['seconds'] for r in rs]
        ss = [s for s in sql if s['arm'] == arm]
        totals[arm] = {'phases':dict(phases), 'recall_seconds':sum(r.get('recall_seconds',0) for r in rs),
            'mean_seconds':statistics.mean(times), 'p50':statistics.median(times), 'p95':max(times),
            'sql_rank_calls':sum(s['rank_calls'] for s in ss), 'sql_fetched_rows':sum(s['fetched_rows'] for s in ss),
            'sql_seconds':sum(s['sql_seconds'] for s in ss), 'read_chars':sum(r.get('read_chars',0) for r in rs)}
        mx = next(r for r in rs if r['case_id'] == 'MIX-01')
        c_nodes = {sid for sid,v in mx.get('catalogue',{}).items() if v['document_id'] == 'mock-performance:v1'}
        app, perf = [], []
        for action in mx.get('normalized_actions', []):
            scope = (mx.get('policy') or {}).get('queries',{}).get(action['query'], {})
            intersects = bool(c_nodes & set(scope.get('allowed_node_ids', [])))
            if action['concept_refs'] == ['purpose:applicable']: app.append(not intersects)
            if action['concept_refs'] == ['purpose:performance']: perf.append(intersects)
        mixed[arm] = bool(app and perf and all(app) and all(perf))
        dr = next(r for r in rs if r['case_id'] == 'DRIFT-01')
        drift[arm] = any(v.get('fallback_reason') for v in (dr.get('policy') or {}).get('queries',{}).values())
    rowids = read(O / 'fts-projection.json')['source_rowids']
    sql_scopes = all(f['sql_scope_applied'] and all(rowids[sid] in set(f['scope_rowids']) for sid in f['returned_ids'])
        for r in data['results'] for f in r['fts'])
    paired = []
    for baseline, candidate in [('baseline','compact'), ('baseline','combined'), ('compact','combined')]:
        counts = dict(both_correct=0, candidate_only_correct=0, baseline_only_correct=0, both_wrong=0)
        for case_id in m['runs'][0]['case_ids']:
            b = next(g for g in grade['grades'] if g['case_id']==case_id and g['arm']==baseline)['pass']
            c = next(g for g in grade['grades'] if g['case_id']==case_id and g['arm']==candidate)['pass']
            counts['both_correct' if b and c else 'baseline_only_correct' if b else 'candidate_only_correct' if c else 'both_wrong'] += 1
        counts.update(baseline=baseline, candidate=candidate,
            wall_reduction=1-totals[candidate]['mean_seconds']/totals[baseline]['mean_seconds'],
            cost_reduction=1-grade['usage'][candidate]['cost_usd']/grade['usage'][baseline]['cost_usd'])
        paired.append(counts)
    tests = list(ElementTree.parse(A/'artifacts/contracts.xml').getroot().iter('testcase'))
    contracts_ok = all(t.find('failure') is None and t.find('error') is None for t in tests)
    gold_ok = sha(A/'artifacts/design/expected-offline.json') == read(A/'artifacts/design/upstream-receipts.json')['parent_gold_sha256']
    all_answered = all(r['status']=='ANSWER' for r in data['results'])
    common_cases = [cid for cid in m['runs'][0]['case_ids'] if all(next(r for r in data['results'] if r['case_id']==cid and r['arm']==arm)['status']=='ANSWER' for arm in ARMS)]
    completed_comparison = {}
    for arm in ARMS:
        rs=[r for r in data['results'] if r['arm']==arm and r['case_id'] in common_cases]
        completed_comparison[arm]={'count':len(rs),'case_ids':common_cases,
            'mean_seconds':statistics.mean(r['seconds'] for r in rs) if rs else None,
            'model_calls':sum(r['model_calls'] for r in rs),
            'cost_usd':sum(u.get('cost_usd') or 0 for r in rs for u in r['usage'])}
    completed_gain=1-completed_comparison['combined']['mean_seconds']/completed_comparison['baseline']['mean_seconds'] if common_cases else None
    for comparison in paired:
        comparison['whole_run_timing_comparable']=all(next(r for r in data['results'] if r['case_id']==cid and r['arm']==arm)['status']=='ANSWER' for cid in m['runs'][0]['case_ids'] for arm in [comparison['baseline'],comparison['candidate']])
    gates = {
        'all_product_cases_answered':all(r['status']=='ANSWER' for r in data['results']),
        'gold_byte_identical':gold_ok,
        'required_originals_presented100':all(not g['missing_presented'] for g in grade['grades']),
        'no_candidate_only_regression':all(not p['baseline_only_correct'] for p in paired if p['baseline']=='baseline'),
        'planner_output_lower':all(totals[a]['phases']['source-query-plan']['output_tokens'] < totals['baseline']['phases']['source-query-plan']['output_tokens'] for a in ['compact','combined']),
        'standalone_classifier_calls0':all('purpose-recognition' not in totals[a]['phases'] for a in ARMS),
        'app_single_selection':{v['case_id'] for v in small if v['arm']=='combined' and v['wire_full_originals'] and v['selection_calls']==1 and v['omission_review_calls']==0} == {'APP-01','APP-02','APP-03'},
        'combined_calls_at_most25':grade['usage']['combined']['calls']<=25,
        'sql_scopes_preserved':sql_scopes,
        'mixed_scope_preserved':all(mixed.values()), 'drift_fallback_preserved':all(drift.values()),
        'contracts_passed':contracts_ok,
        'combined_mean_wall_at_least10pct_lower':all_answered and paired[1]['wall_reduction']>=.1,
    }
    audit = {'classification':'SYNTHETIC', 'gates':gates, 'all_gates_passed':all(gates.values()),
        'totals':totals, 'paired':paired, 'small_pool_wire_checks':small, 'mixed':mixed, 'drift':drift,
        'contracts':{'passed':sum(t.find('failure') is None and t.find('error') is None for t in tests),'total':len(tests)},
        'sql_cases':sql, 'main_changed':False,
        'failure_timing_not_valid_for_speed_claim':not all_answered,
        'supplemental_common_completed_cases':completed_comparison,
        'supplemental_common_completed_wall_reduction':completed_gain,
        'boundaries':['fresh baseline is ADR0568 integrated, not current MAIN or past timing reuse',
            '7synthetic questions1repeat; rotated3arm order; external latency/cache variable',
            'small-pool full-input coverage is not proof of legal adequacy or full-corpus retrieval',
            'large/mixed/drift pools keep native review; no independent second model pass in eligible small pool',
            'same parent SQL with possible temporary rank sort; no FTS speed optimization',
            'not full service API/BoundedSourceSession/GENOS/log learning']}
    write(O/'phase-gate-audit.json', audit)
    m['results'].update(phase_gate_audit={k:v for k,v in audit.items() if k!='sql_cases'}, comparisons=paired)
    for arm in ARMS:
        m['results']['latency']['by_arm'][arm].update(case_seconds_p50=totals[arm]['p50'],case_seconds_p95=totals[arm]['p95'])
    write(A/'실험/manifest.json', m)
    front=(A/'README.md').read_text().split('---',2)[1]
    front=front.replace('status: Rejected','status: Proposed') if audit['all_gates_passed'] else front
    sections = [
        ('1. 결정 요약', '사전 동결한 게이트 '+('통과' if audit['all_gates_passed'] else '미통과')+'. MAIN 변경 없음. 기본 API 전체·실제 로그·현장 성능 인증은 별도다.'),
        ('2. 문제와 변경 전 구조','부모 ADR0568은 query/reason/expected_information을 행동마다 중복 출력하고, 후보가6개여도 제목 기반 선별과 원문 기반 누락 검토를 두 호출로 수행했다.'),
        ('3. 가설과 사전 판정 기준',block(m['design']['success_criteria'])),
        ('4. 실험 설계',block(m['design']['arms'])+'\n세 구현을 실제로 새 실행했다. baseline은 부모 integrated다. compact는 개념 ID만 기존 query에 연결한다. combined는 완독·소형 pool 전체 원문을 첫 선별 호출에 넣는다. SQL·recall·DB scope·READ guard는 부모와 바이트 동일하다.'),
        ('5. 데이터·모델·재현성','부모 corpus55·질문7·gold byte동일, 합성 수작업 온톨로지. Gemma ParasailFP8 thinking off,1536출력, schema-in-prompt true, repairs/retries0.3arm 순서순환·반복1. gold는 제품 선택 이후 offline report만 읽는다.'),
        ('6. 결과',block({k:v for k,v in audit.items() if k!='sql_cases'})),
        ('7. 사례별 오류 분석',block([g for g in grade['grades'] if not g['pass']])),
        ('8. 비용·지연·회수 규모',block({'grade':{k:v for k,v in grade.items() if k!='grades'},'phases':totals})),
        ('9. 해석','계획 출력·입력, 선별 호출 수, 전체 답변 시간을 분리한다. 후보의 원문을 전부 제시했다는 조건은 의미 판단의 무오류를 보장하지 않는다. 최종 답변 입력/출력이 바뀌거나 외부 지연이 흔들릴 수 있으므로 전체 시간 delta를 특정 단계 하나의 인과 효과로 단정하지 않는다.'),
        ('10. 한계와 일반화 가능 범위',block(audit['boundaries'])),
        ('11. 운영 결정·롤백 조건','Proposed/Rejected probe. MAIN generation31·registry·GENOS 불변. 큰 후보·미완독·입력 초과·구조 전용 경로에는 fast path를 쓰지 않는다. 실제 로그·holdout·부하와 전수 근거 검증 없이 운영 승격하지 않는다.'),
        ('12. 재현 명령','`.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0569/run.py --live`. 완료 산출물을 덮어쓰지 않고 새 ADR로 분기한다.'),
    ]
    (A/'README.md').write_text('---'+front+'---\n\n# ADR-0569 개념 ID 최소 출력·소형 원문 단일 선별\n\n'+'\n\n'.join('## '+h+'\n\n'+s for h,s in sections)+'\n')
    index = '# ADR-0569 질문·실행 인덱스\n\n'+ '\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n\n'+block({k:v for k,v in audit.items() if k!='sql_cases'})
    (A/'실험/README.md').write_text(index)
    print(json.dumps({'gates':gates,'totals':totals,'paired':paired},ensure_ascii=False))


if __name__=='__main__':main()
