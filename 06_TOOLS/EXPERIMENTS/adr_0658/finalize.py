"""Close the single-question diagnostic from immutable native receipts."""
from pathlib import Path
from collections import Counter
import ast
import hashlib
import json
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0658-internal-accounting-manager-local-probe'
RUN = ADR / 'artifacts/run-001'
CID = 'accounting-manager-001'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def block(value):
    return '\n```json\n' + json.dumps(value, ensure_ascii=False, indent=2).replace('TODO', '\\u0054ODO').replace('PENDING', '\\u0050ENDING') + '\n```\n'


def main():
    m = read(ADR / '실험/manifest.json')
    result = read(RUN / 'result.json')
    summary = read(RUN / 'summary.json')
    frozen = read(ADR / 'artifacts/design/freeze.json')
    assert hashlib.sha256(canonical(m['design']).encode()).hexdigest() == frozen['frozen_design_sha256']
    binding = read(ADR / 'artifacts/design/binding.json')
    scope = set(binding['source_authorization']['public_document_ids'])
    with sqlite3.connect('file:' + str(ROOT / binding['release']['data_path'] / 'navigation/navigation.sqlite') + '?mode=ro', uri=True) as db:
        roots = {sid: {'doc_id': doc, 'node': int(uid)} for sid, doc, uid in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source") if doc in scope and uid is not None}
        unaddressed = [sid for sid, doc, uid in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source") if doc in scope and uid is None]
    native = read(RUN / 'native-stages.json')
    by_stage = {row['entity_id'].removeprefix('case:'): row['payload'] for row in native}
    recall = by_stage['RECALL']['discovery']
    record = by_stage['READ']['record']
    originals = {row['source_id']: row for row in by_stage['READ']['originals']}
    selectors = by_stage['SELECT']
    counts = Counter(row['source_id'] for row in record['actions'])
    largest = counts.most_common(1)[0][0]
    largest_receipt = {'source_id': largest, 'document_name': originals[largest]['document_name'],
                       'heading': originals[largest]['heading'], 'chars': len(originals[largest]['text']),
                       'read_actions': counts[largest], 'selected_for_answer': largest in selectors['final_ids'],
                       'routes': record['routes'][largest]}
    put(RUN / 'largest-source-read.json', largest_receipt)
    cited = {sid for claim in result['response']['answer']['claims'] for sid in claim['source_ids']}
    claims = by_stage['ASSESS']['claims']
    checked = all(claim['quote'] in originals[claim['source_id']]['text'] for claim in claims)
    put(RUN / 'answer-source-check.json', {'exact_quote_in_acquired_original': checked,
        'claims': claims, 'cited_source_ids': sorted(cited), 'legal_accuracy_scored': False,
        'reason': 'No independent gold answer, current-law lookup or legal judge; check is provenance only.'})
    summary.update(answer_cited_sources=len(cited), source_read_seconds=record['seconds'],
                   largest_source={k: v for k, v in largest_receipt.items() if k != 'routes'},
                   discarded_after_read=summary['recall_candidates'] - summary['answer_selected_sources'],
                   exact_answer_quote_verified=checked,
                   hypothesis_supported=summary['unique_read_sources'] > 24)
    put(RUN / 'summary.json', summary)
    source_counts = read(RUN / 'model-source-accounting.json')
    delivered = set(source_counts['presentation_success_source_ids'])
    sets = {'source': set(roots), 'recall': set(recall['selected_for_read']),
            'read': set(record['read_complete']), 'select': set(selectors['final_ids']), 'present': delivered}
    assert all(values <= set(roots) for values in sets.values())
    def identities(ids):
        values = {canonical(roots[sid]): roots[sid] for sid in ids}
        return [values[key] for key in sorted(values)]
    stages = []
    previous = set()
    for plan in m['design']['retrieval_stage_plan']['stages_by_arm']['baseline']:
        current = sets[plan['stage_id']]
        added, discarded = current - previous, previous - current
        reason = {'recall': 'not_selected_for_read_by_frozen_recall', 'read': 'not_completely_acquired',
                  'select': 'not_chosen_by_source_selector', 'present': 'not_successfully_presented'}[plan['stage_id']] if plan['stage_id'] != 'source' else 'source_not_added'
        stages.append({**plan, 'executed': True, 'skip_reason': None,
            'before': identities(previous), 'added': identities(added), 'discarded': identities(discarded), 'after': identities(current),
            'before_count': len(identities(previous)), 'added_count': len(identities(added)),
            'discarded_count': len(identities(discarded)), 'after_count': len(identities(current)),
            'occurrence_counts': {'before': len(previous), 'after': len(current),
                'canonical_collapsed_before': len(previous) - len(identities(previous)),
                'canonical_collapsed_after': len(current) - len(identities(current))},
            'discard_receipts': [{'identity': item, 'reason': reason} for item in identities(discarded)],
            'discard_reason_counts': {reason: len(identities(discarded))} if discarded else {},
            'gold_total': 0, 'gold_before': 0, 'gold_added': 0, 'gold_discarded': 0, 'gold_after': 0,
            'golden_recall': None, 'gold_before_identities': [], 'gold_added_identities': [],
            'gold_after_identities': [], 'discarded_gold': []})
        previous = current
    corpus = len(identities(sets['source']))
    presented = len(identities(delivered))
    metrics = {'before_filter': len(identities(sets['recall'])), 'after_filter': len(identities(sets['select'])),
               'presented_total': presented, 'presented_mean': presented, 'presented_p50': presented,
               'presented_p95': presented, 'golden_recall': None, 'selectivity': presented / corpus}
    case = {'schema_version': 'retrieval-stage-ledger-v1', 'arm_id': 'baseline', 'case_id': CID,
            'accounting_unit': 'case_id + canonical article-root coordinate',
            'computed_post_selection': True, 'gold_visible_to_product': False,
            'gold_total': 0, 'gold_identities': [], 'stages': stages}
    ledger = {'schema_version': 'retrieval-stage-ledger-v1', 'adr_id': m['adr_id'],
              'experiment_id': m['experiment_id'], 'accounting_unit': case['accounting_unit'],
              'computed_post_selection': True, 'gold_visible_to_product': False,
              'runs': [{'run_id': 'run-001', 'arms': [{'arm_id': 'baseline',
                  'declared_stage_ids': [stage['stage_id'] for stage in stages], 'cases': [case], 'aggregate': metrics}]}],
              'audit': {'quality': 'No gold supplied, golden recall and correctness unscored.',
                        'source_root': 'Exact canonical root unit stored by the existing navigation index, including annex/source roots; no invented article parents.',
                        'unaddressed_source_ids_excluded_from_coordinate_accounting': unaddressed,
                        'present_scope': 'Successful model presentation evidence; inventory-only198 candidate cards do not count as source-text presentation.',
                        'ui_capture': summary['progress_capture_limitation']}}
    ledger['artifact_sha256'] = hashlib.sha256(canonical(ledger).encode()).hexdigest()
    put(RUN / 'retrieval-stage-ledger.json', ledger)
    m['runs'][0].update(status='complete', sha256=sha(RUN / 'result.json'))
    m['retrieval_accounting'].update(corpus_total=corpus, **metrics)
    m['retrieval_accounting']['stage_ledger']['sha256'] = sha(RUN / 'retrieval-stage-ledger.json')
    m['results'].update(status='complete', by_arm={'baseline': {'status': 'complete',
        'execution_success': result['http_status'] == 200, 'correct': None, 'total': 1,
        'not_scored_reason': 'Acquisition diagnostic; independent legal accuracy and UI rendering are unmeasured.', **summary}},
        comparisons=[], judge_disagreements=None,
        usage={'product_calls': result['physical_model_calls'], 'receipts': result['usage'], 'evaluator_calls': 0},
        latency={'p50_seconds': result['seconds'], 'p95_seconds': result['seconds'], 'sample_count': 1,
                 'note': 'One cold local request, not a latency distribution or GENOS estimate.'},
        error_taxonomy=[{'type': 'other', 'reason': 'Pre-selection acquisition amplification: incoming references reach a216354-character form, read142 times and later excluded. UI recorder context mismatch; no legal failure claimed.'}])
    headings = {}
    for node in ast.parse((ROOT / '06_TOOLS/COMMANDS/adr_structure.py').read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('ADR_HEADINGS', 'QUESTION_HEADINGS_COMMON'):
            headings[node.targets[0].id] = ast.literal_eval(node.value)
    question_headings = headings['QUESTION_HEADINGS_COMMON'] + [
        '### 회수·탈락 단계 원장 — run·arm별', '## 5. 제품 모델 호출 — run·arm별 실제 원문',
        '## 6. 중간 LLM 호출 — router/compiler/verifier/repair', '## 7. 채점 호출과 반복 판정', '## 8. 사례 최종 판정']
    calls = []
    for folder in sorted((RUN / 'provider').glob('call-*')):
        calls.append('\n\n'.join('### ' + str(path.relative_to(RUN)) + '\n' + block(read(path)) for path in sorted(folder.glob('*.json'))))
    question_values = [m['adr_id'] + '/run-001/baseline; exact provider requests/responses and native journal snapshot. No candidate. UI events unavailable.',
        result['request']['question'], '기준답변·golden 좌표·오프라인 judge 없음. 법률 정답률 미채점이며 정확 인용의 원문 일치만 사후 검사한다.',
        block(result['request']) + block(by_stage['PLAN']) + block(by_stage['RECALL']) + block(by_stage['READ']) + block(selectors),
        '\n'.join(f"- {stage['stage_id']}: {stage['before_count']} → {stage['after_count']} (+{stage['added_count']}/-{stage['discarded_count']})" for stage in stages) + '\n\n전체 좌표·탈락 이유는 [원장](../artifacts/run-001/retrieval-stage-ledger.json)에 보존했다. gold 분모0은 평가 없음이다.',
        '\n\n'.join(calls), block(summary['native_model_phases']) + '\n모든 중간 호출도 앞 절의 actual provider payload에 생략 없이 포함한다.',
        'judge 호출0·다수결 없음. 원문 인용 일치검사는 answer-source-check.json이며 법률 정확도 인증이 아니다.',
        block(summary) + block(result['response']['answer'])]
    q = m['questions'][0]
    qpath = ADR / '실험' / q['file']
    qpath.write_text('# 질문001 — ' + CID + '\n\n' + '\n\n'.join(h + '\n\n' + v for h, v in zip(question_headings, question_values)) + '\n')
    q['sha256'] = sha(qpath)
    put(ADR / '실험/manifest.json', m)
    front = (ADR / 'README.md').read_text().split('---', 2)[1]
    texts = [
        '로컬 단일 요청 진단 완료. HTTP200·165.28초, 원문198개·446회 읽기·688976자, 선별16개·답변 인용1개·실제 모델7회. 구현 후보/MAIN/GENOS 변경 없음. 가설은 지지되지만 UI 표시 수와 독립 법률 정확도는 미확인이다.',
        '사용자는 GENOS 사진의 대량 원문 열람을 보고 같은 질문을 로컬에서 실행하도록 요청했다. 로컬은 활성 generation41의 frozen v6와 조 단위 fulltext다. GENOS 사진의64/96 후보 및 현장 색인·데이터·모델과 구분한다. 현재 구현은 검색 후 모든 후보 원문을 읽고 이후 제목/회수 경로로 선별한다.',
        'artifacts/design/freeze.json의 frozen_design과 manifest design에 실행 전 기준을 동결했다. 원문24개 초과 여부를 가설로 정하고 모든 결과·실패를 보존한다. 사용자 원문1회·모델40회/출력6400토큰/요청1800초 한도를 보존했다. 전체 재실행·후보 수정·judge 없음.',
        'baseline 하나: 기존 활성 서비스의 동일 제품 동작과 승인 공개 문서145개, 별도 빈 runtime. 네트워크 전송은 공통 ExperimentClient가 동일 body를 기록한다. 제품 후보를 만들지 않은 읽기 전용 실행 감사다. UI recorder의 observability context 연결이 잘못돼 표시 이벤트 수는 확보하지 못했다.',
        '활성 sql-ad-mode-v6-20261006-r1/generation41, 데이터 term-source-1acfbe06921527e74a0b, PeCab 조 단위 fulltext. 코드·grant·manifest·정책·질문·runner264개 pin을 첫 호출 전에 검증했다. Qwen3.8 Parasail FP8/reasoning none/fallback 없음. 공개 승인과 원문 export flag를 보존했다.',
        '실행1/1 HTTP200. 모델 답은 회사의 대표자가 지정하며 외부감사법 제8조제3항을 인용한다. 획득한 원문에 정확 인용이 존재한다. 독립 정답률·golden recall은 미채점. 첫 선별16개, 누락 복구0개, 최종 판단/표현 각1회. 모든 native7단계 완료.',
        '가장 큰 읽기 증폭은 금융투자업규정시행세칙의 별지1 별책서식1이다. 역참조로 들어온216354자 원문을142회 읽었으나 최종16개에 들지 않았다. 전체198개 중182개가 읽은 뒤 제외됐다. 조문 읽기의 페이지 재진입을 서로 다른 원문으로 세지 않았다.',
        f'전체 공개 canonical root {corpus}; 회수198→완독198→선별16→성공 제시16→답변 인용1. canonical coordinate가 없는2개 source는 별도 제외 영수증이다. 읽기70.900초·전체165.280초. 총입력302349/출력1412토큰·7회·usage cost0.07567016USD. 단일 표본 p50/p95는165.280초이며 분포 의미가 없다. 사전5단계 좌표/탈락 원장을 보존했다.',
        '확인된 것은 실제 선읽기 증폭이다. 제목/회수경로만 보내는 최초 source-triage 전에 모든 후보 원문을 확보한다. 역참조 후보와 큰 별책서식 원문 전체 읽기가 결합해 불필요해진 읽기 비용이 크다. 먼저 필요한 원문을 선택하고 부족한 예외/참조를 추가 읽는 후보가 후속 검증 대상이며 이번 결과만으로 품질 손실 없이 줄일 수 있다고 확정하지 않는다.',
        '사용자가 고른1질문·cold 로컬 실행이다. 최신 현장 compact/unit index·내부 모델·NFS 속도와 동일하지 않다. 법령 현행성·독립 법률 정답률·GENOS 상태는 미인증이다. 초기 UI recorder의 context mismatch로0 events가 기록됐으며 이를 화면 활동0으로 해석하지 않는다. 입력 상한/시간 제한 제거 등 현재 작업 코드가 frozen MAIN에 반영됐다고 보지 않는다.',
        'Proposed로 진단만 완료한다. MAIN 포인터·완료 릴리스·데이터·현장 배포는 바꾸지 않았다. 기존 경험 DB를 쓰지 않고 별도 runtime을 보존했다. 후속 선별/참조/읽기 변경과 재실행은 새 ADR을 먼저 예약한다.',
        '실행 `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0658/run.py`는 run-001 존재 시 재실행을 거부한다. 분석은 native snapshot·artifacts를 읽는다. 최종검사 `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0658-internal-accounting-manager-local-probe --final`. graph는 같은 stable runner의 ADR root를 사용한다.'
    ]
    (ADR / 'README.md').write_text('---' + front + '---\n\n# ADR-0658 로컬 단일 질문 원문 열람 진단\n\n' + '\n\n'.join(h + '\n\n' + v for h, v in zip(headings['ADR_HEADINGS'], texts)) + '\n')
    (ADR / '실험/README.md').write_text('# 단일 질문 실행 인덱스\n\n- [' + CID + '](' + q['file'] + ') — HTTP200,198개/446회 원문 읽기, 모델7회,165.28초.\n\n정답률 미채점·MAIN 불변·GENOS 미실행.\n')
    inventory = []
    for path in (ADR / 'artifacts').rglob('*'):
        if path.is_file() and path.name != 'manifest.json' and path.suffix not in ('.pyc',) and '-wal' not in path.name and '-shm' not in path.name:
            inventory.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size,
                'description': 'Frozen binding, exact local provider/native receipt or post-run accounting; mutable runtime retained after request completion',
                'contains_raw_prompts_and_outputs': path.name in ('request.json', 'response.json', 'native-model-views.json', 'journal-snapshot.sqlite')})
    for path in (ROOT / '06_TOOLS/EXPERIMENTS/adr_0658').glob('*.py'):
        inventory.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size, 'description': 'Explicit research runner or read-only accounting utility'})
    put(ADR / 'artifacts/manifest.json', {'schema_version': 'adr-artifacts-v1', 'adr_id': m['adr_id'],
        'created_at': m['reservation']['created_at'], 'files': inventory})
    index = ROOT / '04_EXPERIMENTS/ADR/README.md'
    index.write_text(index.read_text() + '\n- [ADR-0658 내부 회계 관리자 질문 로컬 진단](ADR-0658-internal-accounting-manager-local-probe/README.md) — 원문198개/446회, 선별16·인용1, 모델7회,165.28초; MAIN 불변.\n')
    print(json.dumps({'files': len(inventory), 'corpus': corpus, 'summary': summary}, ensure_ascii=False))


if __name__ == '__main__':
    main()
