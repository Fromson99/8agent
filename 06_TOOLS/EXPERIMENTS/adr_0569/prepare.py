"""Prospective design and isolated snapshots; no model calls or gold imports in product."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0569-compact-plan-smallpool'
P = R / '04_EXPERIMENTS/ADR/ADR-0568-action-concepts-presql'
D = A / 'artifacts/design'
CP = R / '02_BACKEND/lawrag/research/candidates/adr_0568/integrated/revisions/rev-001/snapshot'
ARMS = ['baseline', 'compact', 'combined']


def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
def tool(*args):
    subprocess.run([str(R / '.venv/bin/python'), str(R / '06_TOOLS/run_tool.py'), *args], cwd=R, check=True)


def main():
    D.mkdir(exist_ok=False)
    for name in ['corpus.json', 'cases.json', 'expected-offline.json', 'ontology.json',
                 'schemas.json', 'prompts.json', 'concept-catalogue.json']:
        shutil.copyfile(P / 'artifacts/design' / name, D / name)
    m = read(A / '실험/manifest.json'); pm = read(P / '실험/manifest.json')
    criteria = {
        'primary_quality': 'candidate-only strict answer/citation regressions0 vs fresh parent baseline; required originals presented100%; original gold byte-identical, common failures disclosed',
        'planning': 'compact plan output tokens lower than baseline; no separate concept classifier; query_concepts exact query alignment and closed enum',
        'selection': 'combined APP cases use one content-based selection call, all6 complete original candidates are in that call; incomplete/large/structural pools preserve native path',
        'speed': 'combined mean case latency at least10pct below fresh parent baseline; phase timings and p50/p95 reported; 7cases1repeat not speed certification',
        'scope': 'all arms use unchanged ADR0568 SQL scopes/READ guards; mixed applicable/performance scopes and drift fallback retained',
        'controls': 'same corpus55/questions7/gold/Gemma/native recall/native answer prompt; rotated3arm order; plan schemas differ; no API/MAIN/GENOS change',
        'small_pool_gate': 'not structural;1..16 original roots; every selected_for_read root complete; total original chars<=16000; serialized first input<=80000 chars; full original text rather than excerpts',
        'limits': 'max4product calls; max1536output; schema-in-prompt true; thinking off; provider ParasailFP8; retries/repairs0; retained failures; no posthoc tuning',
    }
    changes = {
        'baseline': 'Fresh replay of ADR0568 integrated: verbose per-action context, existing native2pass selector',
        'compact': 'Existing catalogue reason reused; one concept ID or empty string per query, no repeated query/reason/expected_information; existing native2pass selector',
        'combined': 'compact plus one content-based selection call for small fully read pools; all candidate originals supplied; other pools keep native2pass selector',
    }
    m['lineage']['hypothesis_delta'] = 'Reduce duplicated planning output and fuse content selection/recovery only when all candidate originals fit in one native selector call.'
    m['design'].update(hypothesis='Concept ID annotation and full-content small-pool selection reduce planning and selection cost while preserving frozen source/citation contracts.',
        primary_metric='no candidate-only regressions; required originals100%; lower planning output; APP selection1call; mean combined wall>=10pct lower',
        success_criteria=criteria, failure_criteria=['candidate-only evidence/answer regression', 'incomplete/oversized pool bypasses review', 'scope escapes or drift loss', 'combined wall improvement under10pct'],
        criteria_frozen_before_run=True)
    for arm in m['design']['arms']:
        arm.update(changes=changes[arm['id']], controls=criteria['controls'])
        if arm['id'] == 'combined': arm['derived_from'] = ['compact']
    stages = pm['design']['retrieval_stage_plan']['stages_by_arm']['integrated']
    m['design']['retrieval_stage_plan']['stages_by_arm'] = {arm: stages for arm in ARMS}
    m['runs'][0].update(selection_rule='All7 byte-identical parent synthetic cases; each3arm order rotates once; one repeat; no filtering based on outcomes',
        case_ids=[c['id'] for c in read(D / 'cases.json')['cases']], artifact_path=str((A / 'artifacts/run-001/result.json').relative_to(R)))
    m['llm_policy']['llm_calls'] = [{'role':'catalogue/selection/answer','class':'product','model':'google/gemma-4-31b-it','repeats':1}]
    m['dataset'].update(name='Synthetic same55origins and7questions from ADR0568', version='synthetic-generation-v1',
        frozen_source=str((D / 'corpus.json').relative_to(R)), sha256=sha(D / 'corpus.json'),
        legal_version_checked=True, reference_version_checked=True, classification='SYNTHETIC')
    m['retrieval_accounting'].update(changed=True, corpus_total=55, not_applicable_reason=None,
        stage_ledger={'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate',
            'summary_run_id':'run-001','artifact_path':str((A / 'artifacts/run-001/retrieval-stage-ledger.json').relative_to(R)), 'sha256':'PENDING', 'not_applicable_reason':None})
    m['design']['code_isolation'].update(mode='candidate_snapshot', reason=None)
    write(D / 'criteria.json', criteria)
    write(A / '실험/manifest.json', m)  # criteria recorded before snapshot modifications
    present = ['source_query_planning.py', 'source_recall.py', 'source_recall_global.py', 'source_selection.py']
    candidate_paths = []
    for arm in ['compact', 'combined']:
        args = ['adr_candidate.py', 'snapshot', '--adr', str(A.relative_to(R)), '--candidate-id', arm,
            '--experiment-id', m['experiment_id'], '--arm-id', arm, '--run-id', 'run-001']
        sources = ['02_BACKEND/semantic_runtime/legal_agent/' + name for name in present] + ['02_BACKEND/semantic_runtime/fulltext.py']
        for source in sources: args += ['--source', source]
        tool(*args)
        candidate = R / ('02_BACKEND/lawrag/research/candidates/adr_0569/' + arm)
        candidate_paths.append(candidate)
        for source in sources:
            if (CP / source).exists(): shutil.copyfile(CP / source, candidate / 'snapshot' / source)
        for name in ['investigation_graph.py', 'investigation_actions.py']:
            source = '02_BACKEND/lawrag/core/' + name
            dest = candidate / 'snapshot' / source; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(CP / source, dest)
            tool('adr_candidate.py', 'register', str(candidate.relative_to(R)), '--target', source, '--upstream-state', 'absent')
        planner = candidate / 'snapshot/02_BACKEND/semantic_runtime/legal_agent/source_query_planning.py'
        # Rebuild extension from the unchanged serving catalogue contract.
        original = (R / '02_BACKEND/semantic_runtime/legal_agent/source_query_planning.py').read_text()
        planner.write_text(original + '''

ACTION_SYSTEM = CATALOGUE_SYSTEM + """
reason은 기존 분기·검색 판단의 이유를30자 이내 한 구절로 기록한다.
SEARCH에서는 각 queries와 같은 순서로 query_concepts에 개념 ID 하나씩 기록한다.
supplied investigation_concepts에서 해당 검색 행동이 확인하려는 정보에 맞는 ID를 고른다.
불명확하거나 목적이 섞인 검색은 빈 문자열이다. 규정 확인과 실적 수치 확인은 별도 검색으로 만든다.
검색어·이유·기대 정보를 별도 객체로 다시 출력하지 않는다. 개념은 탐색 맥락이며 법적 결론이 아니다.
SEARCH 이외의 query_concepts는 비운다.
"""

def action_catalogue_schema(names, concept_ids):
    value=catalogue_schema(names)
    value['properties']['reason']['maxLength']=160
    value['properties']['query_concepts']={'type':'array','maxItems':4,
        'items':{'type':'string','enum':['']+concept_ids}}
    value['required'].append('query_concepts')
    return value

def validate_action_catalogue(value,names,concept_ids):
    jsonschema.validate(value,action_catalogue_schema(names,concept_ids))
    validate_catalogue({k:v for k,v in value.items() if k!='query_concepts'},names)
    if len(value['query_concepts'])!=len(value['queries']):
        raise ValueError('query concept count must exactly match planned queries')
    return value

def as_actions(value):
    return [{'query':q,'concept_refs':[c] if c else []}
        for q,c in zip(value['queries'],value['query_concepts'])]
''')
        if arm == 'combined':
            selector = candidate / 'snapshot/02_BACKEND/semantic_runtime/legal_agent/source_selection.py'
            text = selector.read_text()
            needle = "    first = call('source-triage', first_data, first_schema)"
            assert text.count(needle) == 1
            text = text.replace(needle, '''    small_fulltext = (not structural and 0 < len(ids) <= POLICY['first_limit']
        and set(record['selected_for_read']) <= set(source_map)
        and sum(len(source_map[sid]['text']) for sid in ids) <= 16000)
    full_cards = []
    if small_fulltext:
        full_cards = [card(sid, len(source_map[sid]['text'])) for sid in ids]
        full_data = {**first_data,
            'task': '후보 원문 전부의 전체 내용을 제공했다. 원질문의 각 요구, 정의·예외·위임·수치를 원문 내용과 경로로 확인해 직접 필요한 근거를 최대16개 choices로 고른다. 이 호출에서 선별과 누락 점검을 함께 한다. 원문에 없는 결론을 추측하지 않는다. 이유30자 이내.',
            'originals': full_cards}
        if len(json.dumps(full_data, ensure_ascii=False)) > max_fulltext_chars:
            small_fulltext = False
        else:
            first_data = full_data
    result['small_pool_full_originals'] = small_fulltext
    result['omission_review_skip_reason'] = ('ALL_CANDIDATE_ORIGINALS_IN_FIRST_SELECTION' if small_fulltext else None)
    result['full_original_candidate_ids'] = ids if small_fulltext else []
    first = call('source-triage', first_data, first_schema)''')
            text = text.replace("{'phase':'triage','cards': cards}", "{'phase':'triage','cards': full_cards if small_fulltext else cards}")
            text = text.replace('if deferred and not structural:', 'if deferred and not structural and not small_fulltext:')
            text = text.replace("'reason':'not_selected_for_question_after_provenance_and_omission_review'", "'reason':('not_selected_after_all_originals_single_pass' if small_fulltext else 'not_selected_for_question_after_provenance_and_omission_review')")
            selector.write_text(text)
    pins = read(P / 'artifacts/design/code-pins.json')
    for p in [R/'06_TOOLS/EXPERIMENTS/adr_0568/run.py', R/'02_BACKEND/semantic_runtime/legal_agent/source_selection.py',
              R/'02_BACKEND/lawrag/research/candidates/adr_0568/integrated/candidate.json']:
        pins[str(p.relative_to(R))] = sha(p)
    write(D / 'code-pins.json', pins)
    write(D / 'upstream-receipts.json', {'parent_gold_path':str((P / 'artifacts/design/expected-offline.json').relative_to(R)),
        'parent_gold_sha256':sha(P / 'artifacts/design/expected-offline.json'),
        'baseline_candidate_manifest':str((R/'02_BACKEND/lawrag/research/candidates/adr_0568/integrated/candidate.json').relative_to(R)),
        'baseline_candidate_sha256':sha(R/'02_BACKEND/lawrag/research/candidates/adr_0568/integrated/candidate.json'),
        'sql_scope_note':'Unchanged parent FTS, READ, graph and recall product code; output compaction and selector are only changed stages.'})
    print('Prospective3arm criteria and isolated candidates prepared; no model calls.')


if __name__ == '__main__': main()
