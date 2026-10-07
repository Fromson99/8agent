"""Read-only provenance diagnosis of the interrupted run, not a new arm."""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import hashlib
import json
import sqlite3

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0519-root-selection-protected-relations'
P = R / '04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union'
def read(p): return json.loads(p.read_text())
def write(p, v): p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')

def main():
    record = read(P / 'artifacts/run-001/cm-004/result.json')
    result = read(A / 'artifacts/run-001/cm-004/result.json')
    cache = read(R / '04_EXPERIMENTS/ADR/ADR-0518-five-source-replacement-loop/artifacts/reference-witnesses.json')
    refs = cache['references']
    db = sqlite3.connect('file:' + str(R / cache['source_database']) + '?mode=ro', uri=True)
    adj = defaultdict(list)
    for target, routes in record['routes'].items():
        for route in routes:
            if route.get('anchor'):
                adj[route['anchor']].append((target, route))
    depth = {s: 0 for s in result['selected_root_ids']}
    previous = {}
    queue = list(depth)
    for source in queue:
        for target, route in adj[source]:
            if target not in depth:
                depth[target] = depth[source] + 1
                previous[target] = (source, route)
                queue.append(target)
    pool = set(record['read_complete'])
    assert set(depth) & pool == set(result['final_ids'])
    source_cache = {}
    def source(sid):
        if sid not in source_cache:
            row = db.execute('SELECT json FROM source WHERE id=?', (sid,)).fetchone()
            source_cache[sid] = json.loads(row[0]) if row else {'id': sid, 'heading': sid}
        return source_cache[sid]
    def label(sid):
        s = source(sid)
        return s.get('document_name', '') + ' ' + s['heading']
    checked = []
    for rid in ['ref:2ba4a0d1349450708ade6335', 'ref:0bd816f397922782f25d9ab7', 'ref:5b41e3550c4d04edf5aed739']:
        native = json.loads(db.execute('SELECT json FROM reference WHERE id=?', (rid,)).fetchone()[0])
        assert native == refs[rid]
        assert native['source_text'] in source(native['source_id'])['text']
        assert hashlib.sha256(native['source_text'].encode()).hexdigest() == native['source_text_sha256']
        checked.append({'reference': native, 'source': label(native['source_id']), 'targets': [label(s) for s in native['target_source_ids']], 'native_row_matches_cache': True, 'witness_matches_original': True})
    target = 'article:d7dbd03e1557fae2afd9a575'
    path = []
    while target in previous:
        parent, route = previous[target]
        ref = refs.get(route.get('reference_id'), {})
        path.append({'from': label(parent), 'to': label(target), 'route': route, 'witness': ref.get('source_text'), 'target_unit_path': ref.get('target_unit_path'), 'source_unit_path': ref.get('source_unit_path'), 'from_acquired': parent in pool, 'to_acquired': target in pool})
        target = parent
    path.reverse()
    route_refs = {x['reference_id'] for s in depth for t, x in adj[s] if x.get('reference_id') in refs}
    suspect = []
    for rid in sorted(route_refs):
        ref = refs[rid]
        # This is a diagnostic candidate pattern, not automatic data correction.
        if ref.get('mention_start') == 0 and ref['source_text'].startswith(ref['locator'] + '(') and source(ref['source_id'])['heading'].startswith('부칙'):
            suspect.append({'reference_id': rid, 'source': label(ref['source_id']), 'witness': ref['source_text'], 'targets': [label(s) for s in ref['target_source_ids']]})
    audit = {'case_id': 'cm-004', 'kind': 'read_only_path_diagnosis', 'not_new_evaluation_arm': True, 'source_database': cache['source_database'], 'roots': [label(s) for s in result['selected_root_ids']], 'acquired_pool': len(pool), 'reachable_total': len(depth), 'reachable_acquired': len(set(depth) & pool), 'reachable_unacquired': len(set(depth) - pool), 'acquired_by_depth': dict(sorted(Counter(depth[s] for s in pool if s in depth).items())), 'roles_unique_references': dict(Counter(refs[r]['reference_role'] for r in route_refs)), 'confirmed_examples': checked, 'example_path': path, 'heading_reference_suspects_not_all_adjudicated': suspect}
    write(A / 'artifacts/expansion-diagnosis.json', audit)
    finished = sorted(p.parent.name for p in (A / 'artifacts/run-001').glob('*/result.json'))
    started = sorted(p.name for p in (A / 'artifacts/run-001').iterdir() if p.is_dir() and list(p.glob('model/call-*')))
    write(A / 'artifacts/interruption.json', {'recorded_at': datetime.now(timezone.utc).isoformat(), 'reason': 'User questioned 200-source expansion; stopped remaining live calls to inspect relation data and traversal.', 'status': 'INTERRUPTED_NOT_EVALUATED', 'completed_case_ids': finished, 'started_case_ids': started, 'interrupted_case_ids': sorted(set(started) - set(finished)), 'interrupted_provider_usage_may_be_unrecorded': True, 'no_resume_or_overwrite_this_run': True, 'main_changed': False})
    lines = ['# 연결 200개 증가 원인 진단', '', 'Gemma 실행은 사용자 지적 후 중단했다. 완료 18문항, 호출 시작 21문항이며 중단 시 진행 중 3문항의 provider 사용량은 미확인이다. 전체 61문항 성능 결과가 아니다.', '', '## 실제 회수 경로', '', '|시작점에서 거리|추가 회수 완료 조항|누적|', '|---|---:|---:|']
    cumulative = 0
    for depth_value, count in audit['acquired_by_depth'].items():
        cumulative += count
        lines.append(f'|{depth_value}|{count}|{cumulative}|')
    lines += ['', '시작점 2개, 직접 연결까지 15개, 최대 7단계 뒤 200개. 전체 경로상 도달 노드는 1,150개이며 그중 950개는 해당 원문 풀에 없다. 조항 중복은 제거되어 있으며 중복 로그를 200개로 센 것이 아니다.', '', '## 확인한 결함', '', '1. 이번 root_bundles 구현은 모든 anchor 경로를 이어 붙여 방향·관계 종류·항호 범위·미확정 상태를 구분하지 않고 재귀 확장한다. 서로 다른 회수 가지와 미회수 중간 노드까지 이어진다.', '2. 제26조 → 제2조제1항제10호로 간 뒤, 같은 제2조의 제39호나목을 인용한 환매청구권 조문을 역참조로 붙인다. 참조 데이터에는 서로 다른 target_unit_path가 있지만 이번 탐색에서는 article ID만 사용해 이 차이를 잃는다.', '3. navigation.sqlite 원본 관계 행에서 부칙의 제목 「제1조(시행일)」을 본문 「제1조(목적)」에 대한 CITES로 저장한 오류를 확인했다. 부칙/본문 범위 구분과 제목 인용 오인식 문제다. EXACT 표시는 좌표 해석 성공이지 인용 의미 정확성 검증이 아니다.', '', '## 원문으로 검증한 예시', '']
    for item in checked:
        lines += ['- ' + item['reference']['id'] + ': ' + item['source'] + ' → ' + ', '.join(item['targets']), '  - ' + item['reference']['source_text']]
    lines += ['', '## 실제로 이어진 7단계 경로', '']
    for i, edge in enumerate(path, 1):
        lines += [f'{i}. {edge["from"]} → {edge["to"]} ({edge["route"].get("direction")})', '   - ' + str(edge['witness'])]
    lines += ['', '## 수정 순서', '', '관계 생성에서 제목을 참조로 추출하지 않도록 하고 본문/부칙 좌표를 분리해야 한다. 이후 실제 항·호·목의 연결 범위, 참조 방향, 관계 종류를 보존한 탐색을 설계해야 한다. 정상 연결 묶음은 보존하되 단순히 같은 조를 가리킨다는 이유로 다른 가지를 잇지 않는다. 역참조는 별도 시작점 후보를 발견하는 용도와 필수 연결 보존을 구분한다.', '', '진단은 이 사례 및 세 개 native 관계 행을 원문 대조한 결과다. 모든 관계 데이터 오류율이나 수정 후 검색 성능은 아직 측정하지 않았다. 원문·완료 데이터·MAIN은 수정하지 않았다.', '', '[기계 판독 진단](artifacts/expansion-diagnosis.json) · [실행 중단 기록](artifacts/interruption.json)']
    (A / 'EXPANSION_DIAGNOSIS.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({k: audit[k] for k in ['acquired_by_depth', 'roles_unique_references', 'reachable_total', 'reachable_acquired', 'reachable_unacquired']}, ensure_ascii=False))
    print('heading_reference_suspects', len(suspect))

if __name__ == '__main__':
    main()
