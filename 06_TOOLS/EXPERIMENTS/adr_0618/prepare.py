"""Freeze two historical public CM failures and their user guidance before calls."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0618-unified-cm-guidance-two-failures'
DESIGN = ADR / 'artifacts/design'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def read(path):
    return json.loads(path.read_text())


def main():
    assert not (DESIGN / 'freeze.json').exists(), 'Design already frozen'
    parent = ROOT / '04_EXPERIMENTS/ADR/ADR-0496-qwen-source-workflow-cm51-fsc10'
    products = {c['case_id']: c for c in read(parent / 'product-cases.json')['cases']}
    references = {c['case_id']: c for c in read(parent / 'gold-cases.json')['cases']}
    cases = [
        {'case_id': 'cm-051', 'historical_failure': 'retrieval_miss',
         'question': products['cm-051']['question'],
         'guides': []},
        {'case_id': 'cm-003', 'historical_failure': 'condition_exception',
         'question': products['cm-003']['question'], 'guides': []},
    ]
    cases[0]['guides'] = [
        '이 질문은 공동주관회사 선임의무에서 보유비율을 산정하는 문제야. 검색 계획을 정정해. '
        '증권 인수업무 등에 관한 규정의 공동주관회사 조항과 그 조항이 준용하는 원문을 함께 찾아서 다시 판단해. '
        '단순한 지분율 설명으로 끝내지 말고 일반 산정기준과 조합·집합투자기구의 별도 산정기준을 구분해.',
        '검색 계획을 한 번 더 정정해. 증권 인수업무 등에 관한 규정 제6조와 '
        '자본시장과 금융투자업에 관한 법률 시행규칙 제14조 제1항을 검색해서 실제 원문을 읽어. '
        '다른 공개매수 의무에 대한 답으로 바꾸지 말고, 공동주관회사 선임의무의 보유비율 질문에 '
        '준용되는 산정방법과 예외를 대조해서 답해.',
    ]
    cases[1]['guides'] = [
        '원문을 읽었더라도 적용 판단을 다시 검토해. 코스닥시장 상장규정 제26조 제1항 제3호의 '
        '단서와 시행세칙 제23조 제4항의 예외 조건을 각각 대조해. 제3자배정이라는 취득 방식만으로 '
        '분류하지 말고, 투자자의 법적 유형과 제4호의 요건을 함께 확인해. '
        '제3호 적용에서 제외되는 것과 의무보유 자체가 면제되는 것을 구분해. 새로운 사건 사실은 추가하지 마.',
        '검색 계획을 정정해서 코스닥시장 상장규정 제26조 제1항 제3호·제4호와 '
        '코스닥시장 상장규정 시행세칙 제23조 제4항 제2호를 모두 원문으로 확인해. '
        '현재 질문은 그대로 유지해. 각 호의 대상·예외·투자기간 요건을 비교해서 적용 판단을 다시 하고, '
        '재무적투자자의 법적 자격이나 투자기간이 질문에 없으면 분기별 조건부 결론으로 남겨.',
    ]
    for case in cases:
        case['control_turns'] = ['방금 질문의 적용 판단을 다시 검토해서 답해.', '같은 질문을 다시 조사하고 판단해. 검색 계획도 다시 세워.']
        case['branch_order'] = ['unguided', 'guided'] if case['case_id'] == 'cm-051' else ['guided', 'unguided']
    put(DESIGN / 'inputs.json', cases)
    gold = {c['case_id']: references[c['case_id']] for c in cases}
    gold['cm-003']['source_supported_rubric'] = (
        '제3호 본문의 제3자배정 취득 요건과 단서, 세칙의 벤처금융/전문투자자 예외, '
        '제4호의 법적 유형·취득 방식·투자기간 조건을 원문과 일치하게 설명한다. '
        '재무적투자자라는 일반 명칭만으로 벤처금융/전문투자자 자격이나 투자기간을 단정하지 않는다. '
        '제3호 제외를 전체 의무보유 면제로 오해하지 않으며 필요한 사실은 미확인/조건부로 표시한다. '
        '역사적 기준답의 무조건 제4호 결론과의 일치는 별도 reference_agreement 지표다.')
    gold['cm-051']['source_supported_rubric'] = (
        '규정 제6조제2항의 시행규칙 제14조제1항 준용을 제시하고 실제 준용 원문을 읽은 근거를 든다. '
        '규정 제6조제4항 조합/집합투자기구의 출자·투자비율만큼 보유 간주를 구분한다. '
        '규정에서 제시한 제외/조건에 모순되는 보유비율이나 일반 공개매수 결론을 만들지 않는다.')
    generation = ROOT / '01_DATA/TERM_RELEASES/pecab-only-public-main-20260929-v1/generation'
    binding = read(ROOT / '04_EXPERIMENTS/ADR/ADR-0556-pecab-qwen-authorized-routing/artifacts/export-rebinding.json')
    policy = read(ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
    grant = read(ROOT / '00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
    export = read(ROOT / '08_DEPLOYMENT/CONFIG/legal-source-export.json')
    assert export['enabled'] and any(set(grant['public_document_ids']) <= set(x['document_version_ids']) for x in export['bindings'])
    binding.update(generation=str(generation.relative_to(ROOT)), policy_sha256=sha(ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),
                   destination=policy['endpoint'], model=policy['model'],
                   basis='This user explicitly requested two CM guidance experiments; public CM questions and verified public original documents only.',
                   source_manifest_sha256=sha(generation / 'manifest.json'))
    binding['source_authorization_sha256'] = sha(ROOT / '08_DEPLOYMENT/CONFIG/legal-source-export.json')
    assert set(binding['scope_document_ids']) == set(grant['public_document_ids'])
    assert sha(generation / 'store.sqlite') == binding['source_store_sha256'] == grant['source_store_sha256']
    with sqlite3.connect('file:' + str(generation / 'store.sqlite') + '?mode=ro', uri=True) as db:
        provenance = dict(db.execute('SELECT document_id,source_artifact_sha256 FROM document'))
    for row in binding['document_provenance']:
        assert not row['raw_relative_path'].startswith('internal/')
        assert sha(ROOT / '01_DATA/RAW' / row['raw_relative_path']) == row['raw_sha256']
        assert provenance[row['document_id']] == row['source_artifact_sha256']
    nav = next((generation / 'navigation').glob('*.sqlite'))
    with sqlite3.connect('file:' + str(nav) + '?mode=ro', uri=True) as db:
        source_rows = [json.loads(r[0]) for r in db.execute('SELECT json FROM source')]
    coordinates = {r['id']: {'doc_id': r['document_id'], 'node': int(r['unit_id'])}
                   for r in source_rows if r['document_id'] in binding['scope_document_ids'] and str(r.get('unit_id')).isdigit()}
    for key, case in gold.items():
        case['source_originals'] = [r for r in source_rows if r['id'] in case['decisive_source_ids']]
        case['source_originals_sha256'] = hashlib.sha256(json.dumps(case['source_originals'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        assert len(case['source_originals']) == 2
    put(DESIGN / 'gold.json', gold)
    put(DESIGN / 'source-binding.json', binding)
    put(DESIGN / 'source-coordinates.json', coordinates)
    manifest = read(ADR / '실험/manifest.json')
    manifest['lineage']['hypothesis_delta'] = 'First live probe of current unified v6: explicit user guidance versus equally repeated unguided review on two historically failed CM cases.'
    manifest['design'].update(
        hypothesis='Concrete user source/interpretation guidance can repair historically failed CM questions through existing unified execution; records must show whether retrieval or assessment actually changes.',
        primary_metric='source_supported_resolution of final guided turn versus baseline and equal-count unguided review; historical reference agreement separately',
        success_criteria='Both guided final answers complete, read and adopt both decisive sources, satisfy source-supported rubric, and introduce no unsupported facts; no regression versus baseline; record guide1/guide2 separately. Confirmation/wiki/reuse measured separately without changing answer accuracy denominator.',
        failure_criteria='Any final guided product failure, missing decisive source, unsupported assumption, stale route reuse, or unchanged wrong conclusion. Baseline already-correct cases cannot count as repaired errors.',
        criteria_frozen_before_run=True,
        repeats=1, guide_turns=2, control_turns=2,
        budget={'native_model_attempts_per_request': 40, 'physical_product_calls_upper_bound': 560,
                'offline_judge_calls_upper_bound': 24, 'fallback': False, 'transport_retries': 0},
        version_scope='Stored corpus only; no claim of current-law or GENOS accuracy.',
        order='Cases independently executable; cm051 control then guided, cm003 guided then control; each branch copies the exact baseline case store and immutable journals.',
        confirmation_rule='Only guided final answers that complete are explicitly confirmed, then looked up in both wikis and reused once; confirmation is experiment-issued, not expert legal certification.',
        guide_scope='Experiment-authored procedural guidance/locators, no gold reference answer or new case facts. Failure taxonomy follows actual baseline trace, not historical label.')
    manifest['design']['arms'] = [
        {'id': arm, 'role': 'candidate', 'derived_from': [] if arm == 'baseline' else ['baseline'],
         'changes': {'baseline': 'None: frozen current working unified v6, original CM question once',
                     'unguided': 'Same first-turn state, two generic review requests',
                     'guided': 'Same first-turn state, two frozen concrete procedural/source guidance requests'}[arm],
         'controls': 'Exact same code, source generation, public scope, native budget, model/provider; no production edits or forced wrong output.'}
        for arm in ('baseline', 'unguided', 'guided')]
    stages = [{'stage_id': 'source', 'kind': 'source', 'parent_stage_ids': []},
              {'stage_id': 'discovered', 'kind': 'retrieve', 'parent_stage_ids': ['source']},
              {'stage_id': 'read', 'kind': 'filter', 'parent_stage_ids': ['discovered']},
              {'stage_id': 'selected', 'kind': 'select', 'parent_stage_ids': ['read']},
              {'stage_id': 'present', 'kind': 'present', 'parent_stage_ids': ['selected']}]
    manifest['design']['retrieval_stage_plan']['stages_by_arm'] = {arm: stages for arm in ('baseline', 'unguided', 'guided')}
    manifest['runs'][0].update(selection_rule='Fixed cm051 historical missing governing rule and cm003 historical wrong conclusion despite delivered originals; no outcome-based replacement.',
                               artifact_path=str((ADR / 'artifacts/run-001/result.json').relative_to(ROOT)))
    manifest['dataset'].update(name='cm051-cm003-frozen-user-guidance', version='stored-cm-v1-guidance-v1',
                              frozen_source=str((DESIGN / 'inputs.json').relative_to(ROOT)), sha256=sha(DESIGN / 'inputs.json'),
                              legal_version_checked=True, reference_version_checked=True,
                              current_law_verified=False, caveat='Raw provenance and stored source versions checked; historic reference assumptions may be underspecified, scored separately.')
    manifest['retrieval_accounting'].update(changed=True, corpus_total=len(coordinates), not_applicable_reason=None)
    manifest['retrieval_accounting']['stage_ledger'].update(mode='measured', summary_run_id='run-001',
        artifact_path=str((ADR / 'artifacts/run-001/retrieval-stage-ledger.json').relative_to(ROOT)), not_applicable_reason=None)
    manifest['llm_policy']['llm_calls'] = [
        {'role': 'product', 'class': 'product', 'model': policy['model'], 'repeats': 1, 'temperature': 0},
        {'role': 'offline-answer-source-judge', 'class': 'offline_evaluator', 'model': policy['model'], 'repeats': 2, 'temperature': 0}]
    put(ADR / '실험/manifest.json', manifest)
    put(DESIGN / 'pre-snapshot-design.json', manifest)
    # Snapshot all bounded production dependencies and additional local imports.
    config = read(ROOT / '00_SYSTEM/PIPELINE.json'); paths = {'00_SYSTEM/PIPELINE.json', '00_SYSTEM/WORKSPACE.json'}
    for step in config['profiles']['legal-agent-rag-v6']['nodes']:
        path = config['engines'][step['engine']]['manifest']; paths.add(path)
        paths.update(read(ROOT / path)['files'])
    for directory in ('00_SYSTEM/SCHEMAS', '00_SYSTEM/MIGRATION'):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / directory).rglob('*.json'))
    for base in ('02_BACKEND/semantic_runtime', '02_BACKEND/PIPELINE', '02_BACKEND/lawrag'):
        for directory, dirs, files in os.walk(ROOT / base):
            dirs[:] = [d for d in dirs if d not in ('candidates', '__pycache__', '.git')]
            paths.update((Path(directory) / f).relative_to(ROOT).as_posix() for f in files if f.endswith(('.py', '.sql')))
    for key in ('origin_projections', 'alias_projections'):
        paths.update(x['path'] for x in config['profiles']['legal-agent-rag-v6']['nodes'][0]['parameters']['term_agent'][key])
    for engine in config['engines'].values():
        paths.add(engine['manifest'])
    # Policy is copied; credentials are intentionally never copied.
    paths.update(['00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', '00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'])
    put(DESIGN / 'snapshot-source-files.json', sorted(paths))
    for arm in ('baseline', 'unguided', 'guided'):
        args = [str(ROOT / '.venv/bin/python'), str(ROOT / '06_TOOLS/run_tool.py'), 'adr_candidate.py', 'snapshot',
                '--adr', str(ADR), '--candidate-id', 'unified-' + arm,
                '--experiment-id', manifest['experiment_id'], '--arm-id', arm, '--run-id', 'run-001']
        for path in sorted(paths):
            args += ['--source', path]
        subprocess.run(args, cwd=ROOT, check=True)
    print(json.dumps({'prepared_cases': [c['case_id'] for c in cases], 'public_documents': len(binding['scope_document_ids']),
                      'corpus_articles': len(coordinates), 'snapshot_files_per_arm': len(paths), 'model_calls': 0}))


if __name__ == '__main__':
    main()
