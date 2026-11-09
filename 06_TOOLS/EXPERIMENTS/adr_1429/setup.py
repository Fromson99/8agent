"""Freeze candidate code, synthetic corpora, authorization and criteria before any model call (ADR-1429)."""
from common import *
import importlib, shutil, sqlite3
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as ac

DES.mkdir(parents=True, exist_ok=True)
assert not (DES / 'freeze.json').exists(), 'already frozen'
REQUEST = '실제모델로 한번 돌려봐봐 2번'
rel = lambda path: str(Path(path).relative_to(ROOT))

# 1. Candidate = selected MAIN164 + the two-file source-mode fix (+ recomputed pins), already checked without a model.
# The selected MAIN moved to 165 (Oracle navigation compatibility) after the fix was checked on MAIN164. The files the
# comparison path uses are identical in both, so the candidate stays on the claimed MAIN164 base; the pointer is recorded.
pointer = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
selected = read(ROOT / pointer['manifest_path'])['files']
release = read(BASELINE / 'release.json'); files = release['files']
differs = sorted(n for n in set(files) | set(selected) if files.get(n) != selected.get(n))
assert not [n for n in differs if n.startswith(('02_BACKEND/semantic_runtime/legal_agent/', '02_BACKEND/workflow/'))
               or n.endswith(('workflow_rag.py', 'profile-unified-v6.json'))], differs
assert all(sha(BASELINE / 'code' / n) == h for n, h in files.items())
staged = {n: sha(STAGED / n) for n in files}
changed = sorted(n for n in files if staged[n] != files[n])
products = [n for n in changed if not n.startswith('02_BACKEND/ENGINES/') and n != '00_SYSTEM/PIPELINE.json']
assert products == ['02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py',
                    '02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py'] and len(changed) == 33
manifest = read(ADR / '실험/manifest.json')
path = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1429/fixed'
# A first setup attempt froze the candidate and then stopped at the corpus imports; the frozen revision is reused as is.
if not (path / 'candidate.json').exists():
  path = ac.snapshot(ADR, 'fixed', list(files), experiment_id=manifest['experiment_id'], arm_id='fixed', run_ids=['run-001'])
  for n in files:
    if sha(path / 'snapshot' / n) != staged[n]:
        shutil.copyfile(STAGED / n, path / 'snapshot' / n)
  ac.freeze(path)
assert not ac.validate(path), ac.validate(path)
revision = read(path / 'candidate.json')['revisions'][-1]
C = path / 'revisions' / revision['revision_id'] / 'snapshot'
assert all(sha(C / n) == staged[n] for n in files)
pin = {'manifest_path': rel(path / 'candidate.json'), 'manifest_sha256': sha(path / 'candidate.json'),
       'revision_id': revision['revision_id'], 'revision_sha256': revision['revision_sha256']}
if (DES / 'candidate.json').exists():
    assert read(DES / 'candidate.json')['pin'] == pin and read(DES / 'candidate.json')['files'] == staged
    (DES / 'candidate.json').unlink()
put(DES / 'candidate.json', {'code_root': rel(C), 'files': staged, 'changed_from_main164': changed, 'product_changes': products, 'pin': pin,
                             'baseline': {'release_id': 'dev-unsuffixed-20261106-r2', 'generation': 164, 'manifest_sha256': sha(BASELINE / 'release.json')},
                             'selected_at_freeze': {'release_id': pointer['release_id'], 'generation': pointer['generation'],
                                                    'differs_from_baseline': [n for n in differs if not n.startswith('02_BACKEND/ENGINES/')],
                                                    'comparison_path_files_identical': True},
                             'offline_evidence': '09_ARTIFACTS/AUDITS/20261106-comparison-source-mode/수정과_검증결과.txt'})
shutil.copyfile(C / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json', DES / 'provider-policy.json')
assert read(ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json') == read(DES / 'provider-policy.json')

# 2. Transport modules pinned to immutable copies (same list as ADR-1424).
pins = read(ROOT / '04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
    target = ART / 'transport' / name; target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target); pins['files'][name] = sha(target)
put(ART / 'transport/transport-pins.json', pins)

# 3. Synthetic corpora, built with the candidate's own runtime code.
os.environ.update(WORKFLOW_TEST_CODE_ROOT=str(C), LOOP_TEST_CODE_ROOT=str(C), LAWRAG_WORKSPACE_ROOT=str(ROOT), PYTHONDONTWRITEBYTECODE='1')
sys.path[:0] = [str(C / '02_BACKEND'), str(ROOT / '05_TESTS'), str(ROOT / '05_TESTS/CONTRACTS'), str(ROOT)]
# The test bootstrap puts every experiment tool folder first on sys.path; load the standard modules it could shadow first.
import inspect, traceback, dataclasses, pytest  # noqa: F401
import lawrag
lawrag.__path__.append(str(ROOT / '02_BACKEND/lawrag'))
for name in ('core', 'pipeline'):
    module = importlib.import_module('lawrag.' + name); module.__path__.append(str(ROOT / '02_BACKEND/lawrag' / name))
import conftest
sys.path[:0] = [str(C / '02_BACKEND')]
from lawrag.pipeline.term_generation import build_generation
from lawrag.pipeline.fulltext_stage import derive
from lawrag.pipeline.search_selection import plan, activate

LIVE = [
    ('inside', '모의 유동성리스크 관리지침', 'internal', [
        ('제1조', '목적', '제1조(목적) 이 지침은 「모의 금융투자업 감독규정」 제12조에 따라 회사의 유동성리스크 관리 기준과 절차를 정함을 목적으로 한다.'),
        ('제2조', '정의', '제2조(정의) 이 지침에서 "유동성비율"이란 잔존만기 3개월 이내 유동성자산을 잔존만기 3개월 이내 유동성부채로 나눈 비율을 말한다.'),
        ('제3조', '유동성비율의 유지', '제3조(유동성비율의 유지) ① 회사는 유동성비율을 100분의 110 이상으로 유지하여야 한다. ② 유동성비율이 100분의 110에 미달한 경우 리스크관리부서장은 지체 없이 리스크관리위원회에 보고하여야 한다.'),
        ('제4조', '위기상황분석', '제4조(위기상황분석) 리스크관리부서는 매 분기 1회 이상 유동성 위기상황분석을 실시하고 그 결과를 대표이사에게 보고하여야 한다.'),
        ('제5조', '한도 초과 거래의 승인', '제5조(한도 초과 거래의 승인) 유동성 한도를 초과하는 거래는 리스크관리위원회의 사전 승인을 받아야 한다. 다만, 긴급한 경우에는 대표이사의 승인을 받아 거래한 후 다음 영업일까지 리스크관리위원회에 보고할 수 있다.')]),
    ('outside', '모의 금융투자업 감독규정', 'external', [
        ('제12조', '유동성리스크 관리', '제12조(유동성리스크 관리) ① 금융투자업자는 유동성리스크 관리에 관한 내부기준을 마련하여야 한다. ② 금융투자업자는 유동성비율을 100분의 100 이상으로 유지하여야 한다.'),
        ('제13조', '유동성비율의 산정', '제13조(유동성비율의 산정) 유동성비율은 잔존만기 3개월 이내 유동성자산을 잔존만기 3개월 이내 유동성부채로 나누어 산정한다.'),
        ('제14조', '위기상황분석', '제14조(위기상황분석) 금융투자업자는 반기 1회 이상 유동성 위기상황분석을 실시하고 그 결과를 이사회에 보고하여야 한다.'),
        ('제15조', '기준 미달 시 보고', '제15조(기준 미달 시 보고) 유동성비율이 제12조제2항의 기준에 미달한 금융투자업자는 미달한 날부터 5영업일 이내에 그 사실과 개선계획을 감독원장에게 보고하여야 한다.'),
        ('제16조', '한도 초과 거래', '제16조(한도 초과 거래) 금융투자업자는 유동성 한도를 초과하는 거래를 하려는 경우 위험관리위원회의 사전 승인을 받아야 한다.')]),
    ('other', '모의 전자금융 감독규정', 'external', [
        ('제5조', '접근통제', '제5조(접근통제) 금융회사는 전산실 출입자를 통제하고 출입 기록을 1년 이상 보관하여야 한다.'),
        ('제6조', '비밀번호 관리', '제6조(비밀번호 관리) 금융회사는 이용자 비밀번호를 암호화하여 보관하여야 한다.')])]
# The fixture pair used by the scripted model in 05_TESTS (wiring check only).
SCRIPTED = [('inside', '모의내규', 'internal', [('제1조', '승인', '제1조(승인) 모의승인규정에 따라 승인 후 보고한다.')]),
            ('outside', '모의승인규정', 'external', [('제1조', '승인', '제1조(승인) 승인 후 보고한다.')])]


def corpus(folder, documents):
    folder.mkdir(parents=True, exist_ok=False)
    raw = folder / 'source.sqlite'
    with sqlite3.connect(raw) as db:
        db.executescript('''CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
          CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
          CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);''')
        for did, name, category, articles in documents:
            artifact = hashlib.sha256(json.dumps(articles, ensure_ascii=False).encode()).hexdigest()
            db.execute('INSERT INTO document VALUES (?,?,?,?)', (did, name, artifact, json.dumps({
                'document_category': category, 'document_metadata': {'team': 'risk_team'},
                'workflow_version': {'verified': True, 'valid_from': '2020-01-01', 'valid_to': None}}, ensure_ascii=False)))
            for index, (surface, title, text) in enumerate(articles):
                unit = {'family': 'kr_article', 'surface': surface, 'title': title, 'span': [index, index + 1]}
                db.execute('INSERT INTO source_unit VALUES (?,?,?,?)', (did, str(index), None, json.dumps(unit, ensure_ascii=False)))
                db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)', (did, str(index), str(index), text, artifact, '{}'))
    glossary = conftest.term_glossary.__wrapped__(folder)
    build_generation(raw, glossary, folder / 'built', serving=True)
    derive(folder / 'built/generation', folder / 'indexed', workers=1)
    activate(plan(folder / 'indexed', latest=True))
    return {'data_path': rel(folder / 'indexed'), 'source_manifest': read(folder / 'indexed/manifest.json'),
            'documents': [{'document_id': d, 'name': n, 'category': c, 'articles': [a[0] for a in rows]} for d, n, c, rows in documents],
            'synthetic': True, 'files': {rel(p): sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}}


live = corpus(ART / 'corpus', LIVE)
scripted = corpus(ART / 'scripted-corpus', SCRIPTED)
put(DES / 'comparison-source.json', live); put(DES / 'scripted-source.json', scripted)
case = {'id': CASE, 'question': '대사: 모의 유동성리스크 관리지침의 유동성비율 유지 기준, 기준 미달 시 조치, 위기상황분석 주기가 외규와 맞는지 양쪽 원문을 제시하여 비교해 주세요.',
        'document_ids': ['inside', 'other', 'outside'], 'synthetic': True}
put(DES / 'case.json', case)
put(DES / 'scripted-case.json', {'id': 'scripted-wiring', 'question': '대사: 모의내규와 모의승인규정의 승인 기준을 비교해 주세요.',
                                 'document_ids': ['inside', 'outside'], 'synthetic': True})
put(DES / 'authorization.json', {'user_instruction': REQUEST, 'workflow_id': 'risk_team_compare_workflow', 'question': case['question'],
                                 'documents': live['documents'], 'generation_id': live['source_manifest']['generation_id'],
                                 'store_sha256': live['source_manifest']['store_sha256'],
                                 'scope': 'Synthetic documents written for this ADR only (no stored internal or external original). '
                                          'Real internal documents are not used: recent integration runs kept internal-document questions for the internal model.'})
criteria = {
    'request': REQUEST,
    'question': '감독 제외 수정본에서 대사가 실제 Qwen3.8로 내규 조사→개념→외규 조사→항목 대조→보고서까지 진행하는가',
    'primary_metric': 'One real request: HTTP status and workflow stages reached',
    'required': ['HTTP 200 workflow-result-v1 with status completed or partial; no supervisor authorization error',
                 'Both child investigations return originals (SOURCE_HANDOFF with evidence) and the report has at least one comparison item citing an internal and an external original',
                 'UNKNOWN 0; physical requests within the limit; the same request again adds 0 model calls; frozen candidate/transport/corpus hashes unchanged'],
    'planted_points': ['P1 유동성비율: 내규 100분의 110 이상 vs 외규 100분의 100 이상(내규가 더 엄격)',
                       'P2 기준 미달 시: 내규는 리스크관리위원회 보고만, 외규는 5영업일 이내 감독원장 보고(내규에 외부 보고 없음)',
                       'P3 위기상황분석: 내규 분기 1회·대표이사 보고 vs 외규 반기 1회·이사회 보고'],
    'secondary': ['Planted points found in the report with both originals (operator reading, descriptive; no evaluator call)',
                  'Stages, rejected proposals and corrective calls; physical requests, tokens, cost, seconds',
                  'Whether the external rule named in the internal original was reached, and how (search vs named lookup)'],
    'not_measured': 'Legal quality, real internal/external documents, repeat stability and GENOS internal model are not measured. One request, in-sample.',
    'stop': 'One request only. An unknown provider outcome stops external sending and is not re-sent; resource floors stop the run. No rerun in this ADR.',
    'limits': {'physical_total': 60, 'per_physical_seconds': 180, 'reported_cost_usd': 1.0, 'request_seconds': 600,
               'ram_start_gib': 5, 'swap_free_start_gib': 1.2, 'wait_seconds': 5400,
               'guard': 'resource_guard.py copied from ADR-1424: RAM floor 3GiB, free swap floor 1GiB, worker swap growth 128MiB, host swap growth 512MiB'},
    'baseline': 'MAIN164 fails at the first internal-investigation action with "native action lacks current supervisor authorization" '
                '(reproduced without a model; ADR-1293 real run on MAIN133). The baseline arm is not executed here.',
    'quality_certified': False, 'in_sample': True}
put(DES / 'criteria.json', criteria)

manifest['lineage']['hypothesis_delta'] = criteria['question']
manifest['design'].update(hypothesis=criteria['question'] + ' — 예상: 첫 단계 오류 없이 보고서까지 간다. 개념·항목 단계에서 형식 보완이 생길 수 있다.',
                          primary_metric=criteria['primary_metric'], success_criteria=criteria['required'],
                          failure_criteria=[criteria['stop'], 'HTTP 500 or a supervisor authorization error', 'Any source/ACL/hash mismatch reported by the product'],
                          criteria_frozen_before_run=True,
                          criteria_freeze_evidence={'path': rel(DES / 'criteria.json'), 'sha256': sha(DES / 'criteria.json')})
manifest['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[
    {**pin, 'candidate_id': 'fixed', 'experiment_id': manifest['experiment_id'], 'arm_id': 'fixed', 'run_ids': ['run-001'],
     'runner_path': rel(TOOLS / 'live.py'), 'runner_sha256': sha(TOOLS / 'live.py')}])
for arm in manifest['design']['arms']:
    if arm['id'] == 'baseline':
        arm.update(changes='Selected MAIN164 unchanged; reference only, not executed (known first-step failure)', controls='Same profile and workflow')
    else:
        arm.update(changes='MAIN164 + source-return mode excluded from supervisor and source-goal control (2 product files, pins recomputed)',
                   controls='Selected profile-unified-v6 unchanged (supervisor enforce), same workflow 1.20.8, synthetic corpus, Qwen3.8 policy')
manifest['runs'][0].update(arm_ids=['fixed'], selection_rule='One predeclared synthetic comparison request; ' + criteria['stop'],
                           artifact_path=rel(RUN / 'result.json'))
manifest['dataset'].update(name='Synthetic internal rule and two external rules written for ADR-1429', version=live['source_manifest']['generation_id'],
                           frozen_source=rel(DES / 'comparison-source.json'), sha256=sha(DES / 'comparison-source.json'),
                           legal_version_checked=False, reference_version_checked=False)
manifest['llm_policy']['llm_calls'] = [{'role': 'product', 'class': 'product', 'model': 'qwen/qwen3.8-27b', 'repeats': 1}]
reason = 'Retrieval is unchanged product behaviour inside the workflow children; this probe records stages and originals, not recall. No gold coordinates.'
manifest['retrieval_accounting'].update(not_applicable_reason=reason)
manifest['retrieval_accounting']['stage_ledger'].update(not_applicable_reason=reason)
(ADR / '실험/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')

frozen = [*sorted(TOOLS.glob('*.py')), *(DES / n for n in ('candidate.json', 'provider-policy.json', 'comparison-source.json', 'scripted-source.json',
                                                         'case.json', 'scripted-case.json', 'authorization.json', 'criteria.json')),
          ART / 'transport/transport-pins.json', ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',
          ROOT / '05_TESTS/CONTRACTS/test_internal_concept_comparison.py']
put(DES / 'freeze.json', {'files': {rel(p): sha(p) for p in frozen if p.name not in ('finalize.py', 'publish.py')}, 'model_calls_before_freeze': 0})
put(ART / 'preparation-issues.json', [
    {'step': 'setup', 'issue': 'Selected MAIN pointer had moved from 164 to 165 before the first run; the assertion stopped setup before any write of design files', 'model_calls': 0},
    {'step': 'setup', 'issue': 'Path filter for comparison-path files also matched engine pin paths; stopped before any design file', 'model_calls': 0},
    {'step': 'setup', 'issue': 'Test bootstrap put an experiment folder with inspect.py ahead of the standard library; corpus imports failed after the candidate was frozen. '
                                'The frozen candidate revision is reused unchanged', 'model_calls': 0}])
print('frozen: candidate', len(files), 'files,', len(changed), 'changed; live corpus', live['source_manifest']['counts'], '; scripted corpus', scripted['source_manifest']['counts'])
