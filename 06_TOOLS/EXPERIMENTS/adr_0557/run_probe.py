"""Exact selected MAIN product execution with experiment-only public Qwen transport."""
import argparse
from contextlib import contextmanager
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0557-structure-main-qwen14'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(8388608):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def pin():
    design = read(ADR / 'artifacts/frozen-design.json')
    for name, expected in design['file_hashes'].items():
        if sha(ROOT / name) != expected:
            raise RuntimeError('Frozen input drift: ' + name)
    code = ROOT / design['code_root']
    sys.path[:0] = [str(code / '02_BACKEND'), str(ROOT / '02_BACKEND')]
    import lawrag
    lawrag.__path__.append(str(ROOT / '02_BACKEND/lawrag'))
    spec = importlib.util.spec_from_file_location('lawrag.research.experiment_client', ROOT / design['transport_path'])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    import semantic_runtime
    assert Path(semantic_runtime.__file__).is_relative_to(code)
    return design


def validate_export_authorization(binding):
    """Preserved server-owned public grant, scoped model policy and immutable source flags."""
    from semantic_runtime.legal_agent.errors import ContractError
    grant = binding.get('export_authorization') or {}
    policy_path = ADR / 'artifacts/scoped-model-policy.json'
    policy = read(policy_path)
    auth_path = ROOT / '08_DEPLOYMENT/CONFIG/legal-source-export.json'
    auth = read(auth_path)
    model = binding['model']
    scope = set(binding['scope']['document_version_ids'])
    if (not auth.get('enabled') or not scope
            or grant.get('experiment_policy_path') != str(policy_path.relative_to(ROOT))
            or grant.get('policy_sha256') != sha(policy_path)
            or grant.get('source_authorization_sha256') != sha(auth_path)
            or policy.get('adr_id') != 'ADR-0557'
            or policy.get('schema_version') != 'user-authorized-openrouter-product-v2'
            or policy.get('authorization', {}).get('source') != 'user_message'
            or policy.get('source_scope') != ['public']
            or policy.get('fallback_allowed') is not False
            or policy.get('main_wiring') != 'unchanged'
            or policy.get('model') != 'qwen/qwen3.8-27b'
            or grant.get('model') != policy['model']
            or model['model'] != policy['model']
            or grant.get('destination') != policy['endpoint']
            or model['endpoint_identity'] != hashlib.sha256(policy['endpoint'].encode()).hexdigest()
            or binding['generation_id'] != grant.get('generation_id')
            or binding['store_sha256'] != grant.get('source_store_sha256')
            or binding['source_export_allowed'] != grant.get('source_manifest_export_allowed')
            or grant.get('public_questions_only') is not True
            or grant.get('private_documents_allowed') is not False
            or scope - set(grant.get('scope_document_ids', []))
            or not any(scope <= set(b['document_version_ids']) for b in auth.get('bindings', []))):
        raise ContractError('Public source/model scoped authorization mismatch')


def run_one(case, fixture, design, *, preflight=False, mock=False):
    from lawrag.research.experiment_client import ExperimentClient
    from lawrag.research.openrouter_legal_adapter import OpenRouterSingleSendAdapter
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.legal_agent import workflow_tiers_policy as policy
    from semantic_runtime.legal_agent.errors import ContractError
    arm = 'structure-main'
    run_name = 'mock-contract-001' if mock else 'preflight-001' if preflight else 'run-001'
    out = ADR / 'artifacts' / run_name / case['case_id'] / arm
    out.mkdir(parents=True, exist_ok=False)
    client = ExperimentClient(ROOT, out / 'calls', max_calls=14, max_output_tokens=6400,
        scoped_policy_path=ADR / 'artifacts/scoped-model-policy.json',
        scoped_policy_sha256=sha(ADR / 'artifacts/scoped-model-policy.json'), max_repairs=0)
    if mock:
        import httpx
        value = {'mode':'DIRECT', 'reason':'인사',
            'answer':'안녕하세요. 법령과 규정 검색을 돕는 법률 검색 에이전트입니다.',
            'law_names':[], 'queries':[], 'browse_view':'documents',
            'document_category':'all', 'title_query':'', 'inspect_documents':False}
        def response(request):
            body = json.loads(request.content)
            assert body['provider']['only'] == ['parasail/fp8']
            assert body['reasoning'] == {'effort':'none'}
            return httpx.Response(200, json={'id':'mock-only', 'model':'qwen/qwen3.8-27b',
                'provider':'Parasail', 'choices':[{'message':{'content':json.dumps(value, ensure_ascii=False)}, 'finish_reason':'stop'}],
                'usage':{'prompt_tokens':1, 'completion_tokens':1,
                         'completion_tokens_details':{'reasoning_tokens':0}, 'cost':0}})
        client.transport = httpx.MockTransport(response)
    grant = design['export_authorization']

    class Transport(OpenRouterSingleSendAdapter):
        def authorize(self, query, request, manifest, *, public_question):
            if not public_question or not request['use_llm']:
                raise ContractError('Explicit public question required')
            check = {**manifest, 'source_export_allowed':manifest['export_allowed'],
                     'export_authorization':grant, 'scope':query['scope'], 'model':self.binding}
            validate_export_authorization(check)
            return {'public_question_asserted':True, 'grant':grant,
                    'scope_document_ids':query['scope']['document_version_ids']}

        def validate_authorization(self, context):
            receipt = context.binding.get('external_authorization') or {}
            expected = self.authorize(context.query, context.request, context.binding,
                                      public_question=receipt.get('public_question_asserted') is True)
            if expected != receipt or context.binding['model'] != self.binding:
                raise ContractError('External authorization drift')

    wire = Transport(client)
    settings = policy.profile({**read(ROOT / design['profile_path']),
        'model_binding':wire.binding, 'wall_seconds':300, 'max_schema_repairs':0,
        'max_transport_retries':0}, require_model=True)
    assert settings['bounded_source_selection_enabled'] is True
    started = time.monotonic()
    store = None
    row = {'case_id':case['case_id'], 'arm':arm, 'run_id':run_name, 'error':None,
           'settings':settings, 'started_at':time.time(), 'preflight':preflight,
           'mock_only':mock, 'release_binding':design['release_binding']}
    try:
        store = Store(ROOT / design['generation'])
        p = Pipeline(ROOT / design['code_root'], store, implementation=policy.IMPLEMENTATION,
                     legal_agent_profile=settings, legal_agent_transport=wire)
        original = p.term_agent.open_session

        @contextmanager
        def capture(*args, **kwargs):
            with original(*args, **kwargs) as session:
                row.update(binding=session.context.binding,
                           loaded_session_module=__import__('inspect').getfile(type(session)))
                try:
                    yield session
                finally:
                    repo = session.work
                    ev = repo.evidence()
                    evidence_to_source = {e['evidence_id']:e['source_id'] for e in ev}
                    handles = [dict(r) for r in repo.db.execute('SELECT * FROM navigation_handle')]
                    read_ids = {e['source_id'] for e in ev}
                    discovered = {json.loads(h['identity_json']).get('source_id') for h in handles} - {None}
                    presented = {evidence_to_source[eid] for (eid,) in repo.db.execute(
                        "SELECT DISTINCT p.evidence_id FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'") if eid in evidence_to_source}
                    selected = {evidence_to_source[h['payload']['evidence_id']] for h in repo.heads('source_selection', current=True)
                                if h['payload']['status']=='SELECTED'}
                    events = [dict(r) for r in repo.db.execute('SELECT seq,kind,payload_json FROM event')]
                    routed = [json.loads(e['payload_json']) for e in events if e['kind']=='REQUEST_ROUTED']
                    row.update(request_route=routed[-1] if routed else None,
                        metadata_only=session.metadata_only, structure_first_search=getattr(session,'structure_first_record',None),
                        stages={'discovered':sorted(discovered|read_ids), 'read':sorted(read_ids),
                                'presented':sorted(presented), 'selected':sorted(selected)},
                        budget=repo.budget(), journal_run=repo.run(), limitations=session.limitations,
                        source_recall_summary={k:v for k,v in (getattr(session,'source_recall_record',None) or {}).items()
                                               if k not in ('evidence','packets','paths')},
                        journal_path=str(repo.path.relative_to(ROOT)))
                    trace = {'handles':handles, 'evidence':ev, 'events':events,
                        'observations':repo.observations(10000), 'actions':[dict(r) for r in repo.db.execute('SELECT * FROM action_context')],
                        'claims':repo.heads('claim', current=True), 'source_selections':repo.heads('source_selection'),
                        'errors':session.errors, 'packed':session.packed}
                    with gzip.open(out/'trace.json.gz','wt',encoding='utf-8') as f:
                        json.dump(trace,f,ensure_ascii=False,separators=(',',':'))

        p.term_agent.open_session = capture
        if preflight:
            query = p.plan(case['question'], fixture['public_scope_document_ids'])
            request = {'question':case['question'], 'document_ids':fixture['public_scope_document_ids'], 'use_llm':True}
            with p.term_agent.open_session(request, query=query, runtime=out/'runtime',
                    release=design['release_binding'], external_public_question=True) as s:
                row['view_keys'] = list(s.view('investigate'))
        else:
            from semantic_runtime.progress import capture as capture_progress
            progress = []
            with capture_progress('adr0557-'+case['case_id'],out/'runtime',progress.append):
                result = p.run(case['question'], fixture['public_scope_document_ids'], use_llm=True,
                    execution_context={'runtime':out/'runtime', 'publish':True,
                        'external_public_question':True, 'release':design['release_binding']})
            write(out/'progress.json',progress)
            db = sqlite3.connect('file:'+str(ROOT/row['journal_path'])+'?mode=ro',uri=True)
            publication = db.execute('SELECT status FROM publication WHERE singleton=1').fetchone()
            control = db.execute("SELECT payload_json FROM event WHERE kind='CONTROL' ORDER BY seq DESC LIMIT 1").fetchone()
            db.close()
            row.update(result=result, publication_status=publication[0] if publication else None,
                       control=json.loads(control[0]) if control else None,
                       progress_decisions=[e for e in progress if e.get('kind')=='decision'])
            answer = result.get('answer', {})
            bundle = result.get('assembly',{}).get('term_agent',{}).get('source_bundle',{})
            row['stages'].update(answer=sorted({sid for c in answer.get('claims',[]) for sid in c['source_ids']}),
                payload_sources=sorted({s['source_id'] for s in bundle.get('sources',[])}))
            if mock:
                assert client.calls == 1 and row['publication_status']=='PUBLISHED'
                assert row['request_route']['mode']=='DIRECT'
    except Exception as exc:
        row['error'] = {'type':type(exc).__name__, 'message':str(exc), 'traceback':traceback.format_exc()}
    finally:
        if store is not None:
            store.close()
        row.update(physical_calls=client.calls, usage=client.usage, seconds=round(time.monotonic()-started,3))
        write(out/'result.json',row)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--case')
    parser.add_argument('--mock',action='store_true')
    args = parser.parse_args()
    fixture = read(ADR/'product-cases.json')
    if args.case:
        design = pin()
        row = run_one(next(c for c in fixture['cases'] if c['case_id']==args.case), fixture, design,
                      preflight=not args.execute and not args.mock, mock=args.mock)
        print(json.dumps({'case':args.case, 'calls':row['physical_calls'], 'seconds':row['seconds'],
                          'route':row.get('request_route'), 'error':row['error'],
                          'publication':row.get('publication_status')},ensure_ascii=False),flush=True)
        if row['error'] and not args.execute:
            raise SystemExit(1)
        return
    assert args.execute, 'Specify --case for no-call preflight'
    from concurrent.futures import ThreadPoolExecutor, as_completed
    target = ADR/'artifacts/run-001'
    target.mkdir(exist_ok=False)
    results = {'cases':{}, 'run_id':'run-001', 'started_at':time.time(), 'arms':['structure-main']}

    def one(case):
        with (target/(case['case_id']+'.log')).open('w') as f:
            proc = subprocess.Popen([sys.executable,str(Path(__file__)),'--execute','--case',case['case_id']],
                                    cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
            try:
                code = proc.wait(timeout=360)
                expired = False
            except subprocess.TimeoutExpired:
                proc.kill()
                code = proc.wait()
                expired = True
        out = target/case['case_id']/'structure-main'
        path = out/'result.json'
        if not path.exists():
            calls = list((out/'calls').glob('call-*'))
            usage = read(out/'calls/usage.json') if (out/'calls/usage.json').exists() else []
            write(path, {'case_id':case['case_id'],'arm':'structure-main',
                'error':{'type':'HardDeadlineExceeded' if expired else 'ChildProcessFailed','exit_code':code},
                'physical_calls':len(calls),'usage':usage,'seconds':360 if expired else None,
                'stages':{},'in_flight_usage_unknown':expired})
        row = read(path)
        return case['case_id'], {'path':str(path.relative_to(ROOT)), 'sha256':sha(path),
            'calls':row['physical_calls'],'seconds':row['seconds'],'error':row['error'],
            'publication':row.get('publication_status')}

    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(one,c) for c in fixture['cases']]):
            cid, row = future.result()
            results['cases'][cid] = {'structure-main':row}
            write(target/'results.partial.json',results)
            print(json.dumps({'case':cid,**row},ensure_ascii=False),flush=True)
    results['finished_at'] = time.time()
    write(target/'results.json',results)


if __name__ == '__main__':
    main()
