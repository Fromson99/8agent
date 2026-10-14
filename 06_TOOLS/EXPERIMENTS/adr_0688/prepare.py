"""Freeze the scope and baseline before candidate changes or any model calls."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0688-followup-structure-observability-recovery'
D = A / 'artifacts/design'
D.mkdir(parents=True, exist_ok=True)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def put(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

pointer = json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
release = json.loads((R/pointer['manifest_path']).read_text())
pipeline = json.loads((R/'00_SYSTEM/PIPELINE.json').read_text())
sources = set(release['files'])
for binding in pipeline['engines'].values():
    sources.add(binding['manifest'])
    sources.update(json.loads((R/binding['manifest']).read_text())['files'])
sources = sorted(f for f in sources if (R/f).is_file())
criteria = {
    'frozen_at': datetime.now(timezone.utc).isoformat(),
    'scope': 'Three explicitly requested fixes on current working v6 followup structure tools; preserve active MAIN45 and unrelated edits.',
    'baseline': 'Exact current working serving files, including the preceding ordinary structure-navigation fix. The selected MAIN45 frozen release is provenance, not the A/B baseline.',
    'primary': 'Prespecified synthetic contract coverage; no new serious source/ACL/hash/state/read/adoption/publication regression.',
    'required': [
        'Typed coordinate/title/branch, lookup outcome and actual path survive action chain, return, resume and final source result.',
        'Structure lookup, browse and recovery journal events become scoped live progress and workflow final display without raw source bodies or out-of-scope titles.',
        'Three fulltext page navigation actions for the same document/expression without new delivered original trigger structure recovery; the next page action is withheld.',
        'New original delivery, another document or a different fulltext expression remain valid independent progress; historical menus cannot bypass recovery.',
        'Lookup failures distinguish missing document/coordinate/title/branch, ambiguous document/coordinate, invalid coordinates, unresolved binding and missing/nonunique original.',
        'MISS never silently selects another branch/document or fulltext; candidates remain browsable and current structure stays available.',
        'Existing 27 followup structure contracts and maintained 61 source/navigation/completion contracts introduce no new serious failures.'
    ],
    'recovery_threshold': 3,
    'synthetic_contract_categories': ['typed-history', 'scoped-progress', 'workflow-render', 'paging-recovery',
        'new-original-reset', 'document-query-isolation', 'historical-menu-guard', 'resume-return',
        'failure-taxonomy', 'ambiguity-no-read', 'current-tree-retention', 'native-publication'],
    'model_probe': {
        'dataset': 'Four independently authored synthetic public-style navigation requests; artificial source trees contain no actual company material or copied photo questions.',
        'cases': [
            {'id': 'article-direct', 'question': '모의공개금융법 제6조의 금융투자업 종류를 확인하기 위해 해당 조문을 읽어줘.', 'scenario': 'literal-article'},
            {'id': 'paging-recovery', 'question': '모의공개금융법 제6조를 읽어야 한다. 관련 없는 fulltext 조문 후보를 여러 페이지 넘겼지만 아직 해당 원문을 읽지 못했다.', 'scenario': 'three-pages'},
            {'id': 'missing-coordinate', 'question': '모의공개금융법 제999조를 찾지 못했다. 현재 문서 목차와 실패 원인을 확인하고 실제 있는 위치를 다시 찾아줘.', 'scenario': 'missing'},
            {'id': 'heading-search', 'question': '현재 모의공개금융법에서 금융투자업이라는 제목의 조문을 찾아 원문을 읽어줘.', 'scenario': 'heading'}
        ],
        'arms': ['baseline', 'integrated'], 'order': 'Alternate B/A and A/B by case index; temperature zero; one prespecified run; no answer/gold in product input.',
        'max_model_calls': 24, 'max_calls_per_arm_case': 3,
        'model': 'qwen/qwen3.8-27b', 'provider': 'Parasail FP8 only', 'reasoning': 'none', 'fallback': False,
        'semantic_legal_grading': False, 'decision_role': 'supplemental in-sample navigation probe, not GENOS field performance or legal-answer certification',
        'cost_latency_claim': 'Record actual usage, provider IDs and call latency; no timing acceptance threshold on a shared network.'
    },
    'source_scope': 'synthetic only for external calls; immutable real local source read checks remain local',
    'adoption': 'Functional audit may be Accepted only after prespecified independent contracts and unchanged regression invariants pass. Probe meaning errors are recorded separately. No MAIN/GENOS activation.',
    'tool_resolution': 'The stable adr_structure entry is used. Receipt-bound run_tool adr_candidate currently rejects unrelated WORKSPACE receipt drift; use exact working 06_TOOLS/COMMANDS/adr_candidate.py, preserving the receipt and logging its hash.'
}
assert not (D/'criteria.json').exists(), 'criteria already frozen'
put(D/'criteria.json', criteria)
put(D/'baseline.json', {'pointer': pointer, 'pointer_sha256': sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'release_manifest_sha256': sha(R/pointer['manifest_path']), 'release': release,
    'working_files': {f: sha(R/f) for f in sources},
    'snapshot_tool_sha256': sha(R/'06_TOOLS/COMMANDS/adr_candidate.py')})
m = json.loads((A/'실험/manifest.json').read_text())
m['decision_eligible'] = True
m['lineage']['hypothesis_delta'] = criteria['scope']
m['design'].update(hypothesis='Visible structure outcomes and source-aware navigation recovery remove silent lookup misses and unbounded fulltext paging without changing original authority.',
    primary_metric=criteria['primary'], success_criteria='; '.join(criteria['required']),
    failure_criteria='Any missing required functional behavior or new serious original/ACL/state/hash/serving-connection regression rejects the audit.', criteria_frozen_before_run=True)
for arm in m['design']['arms']:
    arm.update(changes='Unchanged frozen working baseline' if arm['id']=='baseline' else 'Scoped chain/progress/workflow, recovery and failure diagnostics changes',
               controls='Same synthetic fixture source and schema, pinned model policy and immutable source data; no company/private data')
m['dataset'].update(name='Independent synthetic contract audit and supplemental synthetic Qwen navigation probe', version='followup-structure-v1',
    frozen_source=str((D/'criteria.json').relative_to(R)), sha256=sha(D/'criteria.json'), legal_version_checked=True, reference_version_checked=True)
m['runs'][0].update(purpose='holdout', selection_rule='Prespecified contract categories and same maintained regressions; supplemental four synthetic model cases in frozen criteria',
    artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)), sha256=None)
m['llm_policy']['llm_calls']=[{'role':'navigation-probe', 'class':'product', 'model':'qwen/qwen3.8-27b', 'repeats':1}]
m['retrieval_accounting'].update(changed=False, not_applicable_reason='No corpus/retrieval index or candidate ranking change. Contract audit and exact action-menu navigation outcomes; no legal-answer retrieval recall claim.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable', not_applicable_reason='No retrieval effectiveness measurement; synthetic action options and READ scopes are audited separately with exact product views.')
put(A/'실험/manifest.json', m)
for candidate, arm in [('baseline','baseline'), ('integrated','integrated')]:
    cmd=[str(R/'.venv/bin/python'), '06_TOOLS/COMMANDS/adr_candidate.py', 'snapshot', '--adr', str(A.relative_to(R)),
         '--candidate-id', candidate, '--experiment-id', m['experiment_id'], '--arm-id', arm, '--run-id', 'run-001']
    for f in sources:
        cmd += ['--source',f]
    subprocess.run(cmd, cwd=R, check=True)
print('Frozen criteria and two snapshots:', len(sources), 'serving files each; no active pointer changes.')
