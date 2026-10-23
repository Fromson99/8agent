"""Reserve-first isolated successor of the completed ADR0996 candidate."""
from pathlib import Path
import json, hashlib, shutil, sys

ROOT = Path(__file__).resolve().parents[3]
D = Path(__file__).parent
OLD = ROOT / '06_TOOLS/EXPERIMENTS/adr_0996'
(D / 'common.py').write_text((OLD / 'common.py').read_text().replace(
    'ADR-0996-knowledge-use-first-prompt', 'ADR-1019-source-required-answer-items'))
sys.path.insert(0, str(D))
from common import *
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as ac

parent = ROOT / '04_EXPERIMENTS/ADR/ADR-0996-knowledge-use-first-prompt/artifacts'
for name in ['curated-source-values.json', 'method-templates.json', 'selected.json', 'cases.json']:
    put(DES / name, read(parent / 'design' / name))
for name in ['criteria.json', 'extra-source.json']:
    put(ART / 'offline' / name, read(parent / 'offline' / name))
put(ART / 'agent_layer/corrected-experiences.json', read(parent / 'agent_layer/corrected-experiences.json'))
cases = read(DES / 'cases.json')
criteria = {
    'hypothesis': 'Source-bound required review items retained in the native assessment journal and deterministically rendered will prevent silent omission; separately test whether model explanations improve over the same use-first prompt.',
    'success': [
        'Every bound item appears exactly once in the final required-review section with an explicit status; missing model decisions are UNKNOWN, never silently removed or counted as explained.',
        'Each EXPLAINED result refers to current source-validated claims; NOT_APPLICABLE has a reason; changed prior results retain history and require a reason. No source/ACL/hash/state regression.',
        'Model-only required explanation coverage is not lower overall or on any case, and there is no new forbidden inference. Copied source notes and UNKNOWN markers do not count as explanation success.',
        'Candidate physical model calls <= baseline + 5 and total latency <= 1.5 times baseline. Same per-request 24 calls / 900 seconds; no added retry owner.'
    ],
    'limits': {'max_requests': 10, 'max_model_calls_per_request': 24, 'wall_seconds_per_request': 900,
               'concurrency': 1, 'rss_gib': 6, 'minimum_available_gib': 3},
    'order': [[c['id'], a] for i, c in enumerate(cases) for a in
              (['baseline', 'candidate'] if i % 2 == 0 else ['candidate', 'baseline'])],
    'failure': 'First provider/transport/binding or source/ACL/state integrity failure stops remaining dispatch. Existing one schema repair, no case rerun or fallback.',
    'failure_contract': {
        'owner': 'Existing ASSESS executor owns its one correction and cumulative budget; no new model stage.',
        'omission': 'Host creates UNKNOWN or retains prior review as stale, and renders the review note; never invent a claim or interpret absence as non-applicability.',
        'change': 'KEEP reuses a validated prior outcome only after source revalidation. EXPLAIN/NOT_APPLICABLE/UNKNOWN changes require a reason when a prior outcome exists.',
        'meaning': 'Item coverage is structural, not semantic correctness. Applicability remains the model opinion. No extra investigation solely to satisfy a checklist.',
        'resume': 'Read hash-checked append-only item snapshots for the same question, principal, source binding and plan. Idempotent acceptance; no reset of native budget.',
        'publication': 'Final renderer and replay verifier use the same bound receipt, including source identities and persisted statuses.'
    },
    'controls': 'Both arms inherit ADR0996 candidate, use-first prompt ON, same four source wiki units/nine ontology records, same model, original delivery, CLOSED/EXTEND policy and questions. Candidate alone adds required-item records, output mapping, journal persistence and deterministic rendering.',
    'scope': 'Known CM four plus developer-composed extension, all in-sample. No MAIN/product path/Oracle/GENOS change; this is not a new production knowledge release.'
}
put(DES / 'criteria.json', criteria)
put(DES / 'active-before.json', read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'))
m = read(ADR / '실험/manifest.json')
m['lineage']['hypothesis_delta'] = criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'], primary_metric='Required item display/state coverage, separately model explanation coverage',
    success_criteria=criteria['success'], failure_criteria=criteria['failure'], criteria_frozen_before_run=True, execution=criteria)
for arm in m['design']['arms']:
    arm.update(changes='Use-first prompt ON; required-item enforcement ' + ('OFF' if arm['id'] == 'baseline' else 'ON'), controls=criteria['controls'])
m['design']['retrieval_stage_plan']['stages_by_arm'] = {a: [
    {'stage_id': 'original_read', 'kind': 'source', 'parent_stage_ids': []},
    {'stage_id': 'final_cited', 'kind': 'present', 'parent_stage_ids': ['original_read']}]
    for a in ['baseline', 'candidate']}
m['dataset'].update(name='Same ADR0996 CM5 public cases', version='20261023', frozen_source=str((DES/'cases.json').relative_to(ROOT)),
    sha256=sha(DES/'cases.json'), legal_version_checked=False, reference_version_checked=False)
m['llm_policy']['llm_calls'] = [{'role':'native_rag_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Same frozen five cases; alternating paired order; one request per arm', artifact_path=str((RUN/'result.json').relative_to(ROOT)))
put(ADR / '실험/manifest.json', m)

selected = read(DES / 'selected.json'); release = selected['release']; C = ROOT / release['code_root']
P = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1019/candidate'
assert not P.exists(), 'Do not overwrite an existing candidate'
P = ac.snapshot(ADR, 'candidate', [str((C/n).relative_to(ROOT)) for n in release['files']] + [
    '02_BACKEND/lawrag/research/experiment_client.py', '02_BACKEND/lawrag/pipeline/shortcut_package.py',
    '02_BACKEND/lawrag/pipeline/legal_wiki_compiler.py'], experiment_id=m['experiment_id'], arm_id='candidate', run_ids=['run-001'])
pm = read(parent/'design/candidate.json'); PP = ROOT/pm['path']; rev = read(PP/'candidate.json')['revisions'][-1]
for f in rev['files']:
    source = ROOT/f['frozen_path']; assert sha(source) == f['snapshot_sha256']
    target = str(source.relative_to(PP/'revisions'/rev['revision_id']/'snapshot'))
    dest = P/'snapshot'/target; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dest)
    if not (ROOT/target).exists(): ac.register_file(P, target, upstream_state='absent')
put(DES/'candidate.json', {'path':str(P.relative_to(ROOT)), 'selected_code_relative':release['code_root']})
for name in ['e2e.py','pin.py','contracts.py','audit.py','report_common.py','archive_runtime.py','delivery_audit.py']:
    text = (OLD/name).read_text().replace('ADR-0996', 'ADR-1019').replace('ADR0996','ADR1019')
    if name == 'e2e.py':
        text = text.replace("t.knowledge_use_first_prompt=(arm=='candidate');t.knowledge_reuse_mode=case['reuse_mode']",
            "t.knowledge_use_first_prompt=True;t.knowledge_required_items=(arm=='candidate');t.knowledge_reuse_mode=case['reuse_mode']")
    (D/name).write_text(text)
diffs=[]
base=P/'snapshot'/release['code_root']
for n in release['files']:
    current=ROOT/n; frozen=base/n
    if current.is_file() and frozen.is_file() and sha(current)!=sha(frozen):
        diffs.append({'path':n,'working_sha256':sha(current),'parent_sha256':sha(frozen)})
put(DES/'working-parent-differences.json', {'basis':'Completed ADR0996 branch, not current MAIN102 or concurrently modified working code',
    'files':diffs, 'product_files_overwritten':False})
print('PREPARED', len(rev['files']), 'parent files; design fixed before implementation; model calls 0')
