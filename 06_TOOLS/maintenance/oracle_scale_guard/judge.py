"""Judge one oracle_scale_guard output directory -> report.json, 보고서.txt. usage: judge.py <out>"""
import collections, json, sys
from pathlib import Path


def main(out):
    out = Path(out)
    run = json.loads((out/'run.json').read_text())
    summary = json.loads((out/'summary.json').read_text()) if (out/'summary.json').exists() else {'scenarios': {}}
    records = json.loads((out/'records.json').read_text()) if (out/'records.json').exists() else {'reads': [], 'raised': [], 'sql': [], 'budget': 40, 'guard_errors': ['records.json missing']}
    budget = records['budget']


    def group_key(r):
        scope = ('document' if 'document_id' in r.get('filters', []) else 'lookup' if r.get('narrow') else 'scope') if r['via'] == 'pages' else \
                ('statement' if r['via'] == 'sql_rows' else 'definitions')
        what = r.get('kind') or (r.get('statement') or '')[:140]
        return r['via'], what, scope, (r['site'] or ['?'])[0]


    over = collections.defaultdict(list)
    accepted_path = Path(__file__).with_name('accepted.json')
    accepted = json.loads(accepted_path.read_text())['entries'] if accepted_path.exists() else []
    accepted_hits = collections.Counter(); document_listings = collections.Counter()
    wide_statements = collections.Counter()
    for r in records['reads']:
        reads = r.get('kind') or (r.get('statement') or '')
        site = (r.get('site') or ['?'])[0]
        if r['rows'] > budget and r['via'] == 'pages' and 'budget' in r.get('filters', []):
            # one document listed with a budget sized by its published unit count (memoized per request)
            document_listings[(reads, site)] = max(document_listings[(reads, site)], r['rows'])
            continue
        rule = next((a for a in accepted if a.get('site_prefix') and site.startswith(a['site_prefix'])
                     and reads.startswith(a.get('reads_prefix', ''))), None)
        if r['rows'] > budget and rule and r['scenario'] != 'sweep':
            accepted_hits[(rule['reason'], site)] += 1
            continue
        if r['rows'] > budget and r['scenario'] == 'sweep':
            wide_statements[(r.get('statement') or '')[:160]] = max(wide_statements[(r.get('statement') or '')[:160]], r['rows'])
        elif r['rows'] > budget:
            over[group_key(r)].append(r)
    suspects = []
    for (via, what, scope, site), rs in sorted(over.items(), key=lambda kv: -max(r['rows'] for r in kv[1])):
        suspects.append({'via': via, 'reads': what, 'grows_with': scope, 'site': site, 'stack': rs[0]['site'],
                         'max_rows': max(r['rows'] for r in rs), 'times': len(rs), 'scenarios': sorted({r['scenario'] for r in rs})})
    lookup_totals = collections.Counter()
    for row in records.get('point_lookups', []):
        if row['scenario'] not in ('sweep', None):
            lookup_totals[(row['scenario'], row['turn'], row['kind'], row['document_id'])] += row['calls']
    point_suspects = []
    for row in records.get('point_lookups', []):
        total = lookup_totals[(row['scenario'], row['turn'], row['kind'], row['document_id'])]
        if row['scenario'] not in ('sweep', None) and row['document_id'] != '-' and total > budget and row['calls'] > budget // 4:
            rule = next((a for a in accepted if a.get('point_site_prefix') and row['site'].startswith(a['point_site_prefix'])), None)
            if rule:
                accepted_hits[(rule['reason'], row['site'])] += 1
                continue
            point_suspects.append({**row, 'document_total': total})
    point_suspects.sort(key=lambda r: -r['calls'])
    raised = collections.Counter((r['object'], r['method'], tuple(r['site'][:3])) for r in records['raised'])
    failures = []
    for name, s in summary.get('scenarios', {}).items():
        for i, r in enumerate(s.get('responses', [])):
            if r['status_code'] != 200:
                failures.append({'scenario': name, 'turn': i+1, 'status_code': r['status_code']})
        for f in s.get('run_failures', []):
            failures.append({'scenario': name, 'stage': f['stage'], 'error': f['error_message'],
                             'frames': [x.split('semantic_runtime/')[-1] for x in f['frames'] if 'oracle_scale_guard' not in x][-5:]})
        if s.get('crash'):
            failures.append({'scenario': name, 'crash': s['crash'][-600:]})
    per_turn = collections.Counter((q['scenario'], q['turn']) for q in records['sql'] if q['scenario'] not in ('sweep', None))
    site_calls = collections.Counter((q['scenario'], q['turn'], (q['site'] or ['?'])[0]) for q in records['sql'] if q['scenario'] not in ('sweep', None))
    heavy_sites = collections.Counter()
    for (scenario, turn, site), n in site_calls.items():
        heavy_sites[site] = max(heavy_sites[site], n)
    shape_22806 = [q for q in records['sql'] if q['with_and_number']]
    sweep_errors = []
    if (out/'sweep.json').exists():
        sweep = json.loads((out/'sweep.json').read_text())
        ok_assets = collections.defaultdict(set)
        for x in sweep:
            if not x['error'] or 'QUERY_SQL_COLUMN' not in x['error']:
                ok_assets[(x['key'], x['origin'])].add(x['asset'])
        for x in sweep:
            if x['error'] and not ('QUERY_SQL_COLUMN' in x['error'] and ok_assets[(x['key'], x['origin'])]) and \
                    not ('QUERY_SQL_COLUMN' in x['error'] and not ok_assets[(x['key'], x['origin'])]):
                sweep_errors.append({k: x.get(k) for k in ('origin', 'asset', 'profile', 'case', 'error', 'params')})
        sqlite_only = sorted({x['origin'] for x in sweep if not ok_assets[(x['key'], x['origin'])]})
    else:
        sweep, sqlite_only = [], []
    report = {'code_root': run['code_root'], 'budget': budget, 'field_budget': 10000, 'pytest_exit': run['pytest_exit'], 'seconds': run['seconds'],
              'engine_preflight_errors': run['engine_preflight_errors'], 'code_unchanged': run['code_unchanged'],
              'loaded_outside_code': run['loaded_outside_code'],
              'request_failures': failures, 'over_budget_reads': suspects,
              'point_lookup_suspects': point_suspects[:30],
          'full_catalogue_refusals': [{'object': o, 'method': m, 'stack': list(s), 'times': n} for (o, m, s), n in raised.items()],
              'ora22806_shape_sql': [{'site': q['site'], 'statement': q.get('statement', '')[:600]} for q in shape_22806][:20],
              'document_listings_allowed': [{'reads': a, 'site': s, 'max_rows': n} for (a, s), n in document_listings.most_common()],
          'accepted_reads': [{'reason': a, 'site': s, 'times': n} for (a, s), n in accepted_hits.most_common()],
          'sweep_unbounded_statements': [{'statement': s, 'max_rows': n} for s, n in wide_statements.most_common()],
          'sweep_executions': len(sweep), 'sweep_errors': sweep_errors[:200], 'sweep_error_count': len(sweep_errors),
              'sweep_sqlite_only_statements': len(sqlite_only),
              'sql_per_turn_max': max(per_turn.values() or [0]), 'sql_per_turn': {f'{s}#{t}': n for (s, t), n in sorted(per_turn.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0))},
              'sql_heavy_sites': [{'site': s, 'max_sql_in_one_turn': n} for s, n in heavy_sites.most_common(15)],
              'remote_model_calls': 0}
    report['guard_errors'] = records.get('guard_errors', [])[:20]
    report['passed'] = (not point_suspects and not report['guard_errors'] and run['pytest_exit'] == 0 and not failures and not suspects and not raised and not shape_22806 and not sweep_errors
                        and report['code_unchanged'])
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    lines = [f"Oracle 규모 점검 — {run['code_root']}", f"판정: {'통과' if report['passed'] else '실패'} (축소 한도 {budget}행 = 현장 1만 행에 해당, 외부 모델 0)", '']
    if report['guard_errors']:
        lines.append(f"점검 도구 자체 오류 {len(report['guard_errors'])}건 — 결과를 믿지 말고 도구를 먼저 고칠 것: {report['guard_errors'][:3]}")
    lines.append(f"질문 실패 {len(failures)}건")
    for f in failures:
        lines.append('  - ' + json.dumps(f, ensure_ascii=False)[:400])
    lines.append(f"한도 초과 읽기 {len(suspects)}곳 (범위/문서 크기에 비례해 현장에서 멈출 수 있음)")
    for s in suspects:
        lines.append(f"  - [{s['grows_with']}] {s['reads'][:90]} 최대 {s['max_rows']}행 × {s['times']}회 @ {s['site']}  ({', '.join(s['scenarios'])})")
    lines.append(f"허용: 문서 하나 전체 나열(게시된 단위 수만큼 한도, 요청당 재사용) {len(document_listings)}곳, 사유 기록된 묶음 읽기 {len(accepted_hits)}곳")
    for (a, s), n in document_listings.most_common(6):
        lines.append(f"  - {a} 최대 {n}행 @ {s}")
    lines.append(f"한 문서를 한 건씩 조회(질문 하나에 {budget}건 초과, 문서 크기에 비례) {len(point_suspects)}곳")
    for r in point_suspects[:8]:
        lines.append(f"  - {r['kind']} 문서 {r['document_id']} {r['calls']}회(그 문서 합계 {r['document_total']}) @ {r['site']} ({r['scenario']}#{r['turn']})")
    lines.append(f"전체 목록 거절(QUERY_FULL_CATALOGUE) {len(report['full_catalogue_refusals'])}곳")
    for r in report['full_catalogue_refusals']:
        lines.append(f"  - {r['object']}.{r['method']} × {r['times']} @ {r['stack'][:2]}")
    lines.append(f"ORA-22806 모양(WITH+NUMBER 바인드) SQL {len(shape_22806)}개")
    lines.append(f"참고: 문서/범위 전체를 읽는 모양의 SQL 문장 {len(wide_statements)}개 (전수 실행에서 한도 초과; 위 질문 흐름에서 쓰이지 않으면 위험 아님)")
    lines.append(f"SQL 전수 실행 {len(sweep)}회, 현실적 열 크기에서 Oracle 오류 {len(sweep_errors)}건, SQLite 전용 문장 {len(sqlite_only)}개")
    for e in sweep_errors[:20]:
        lines.append('  - ' + json.dumps(e, ensure_ascii=False)[:300])
    lines.append(f"한 질문(턴) 최대 SQL {report['sql_per_turn_max']}회 (현장 요청당 한도 10,000) — 많이 부르는 곳:")
    for h in report['sql_heavy_sites'][:8]:
        lines.append(f"  - {h['max_sql_in_one_turn']}회 @ {h['site']}")
    (out/'보고서.txt').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines[:3]))
    return 0 if report['passed'] else 1



if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
