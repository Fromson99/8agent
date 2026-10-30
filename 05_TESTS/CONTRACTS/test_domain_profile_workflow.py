"""Synthetic contract tests, not legal-quality or live-model experiments."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest

from semantic_runtime.contracts import digest
from semantic_runtime.full_glossary import concept_id
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.ontology_compiler import content_hash
from semantic_runtime.ontology_work.repository import Repository
from semantic_runtime.ontology_work.store import LocalFolderStore
from semantic_runtime.ontology_work.domain_workflow import DomainWorkflow, SaveUnconfirmed
from semantic_runtime.ontology_work.glossary_binding import GlossaryBinding
from semantic_runtime.ontology_work import profile, observations, accumulation, assembly_compiler

ROOT = Path(__file__).resolve().parents[2]


class Glossary:
    def __init__(self):
        self.binding = {'manifest_sha256': '1'*64, 'dictionary_sha256': '2'*64, 'compiler_sha256': '3'*64}
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE label(source TEXT,node_id TEXT)')
        db.execute('INSERT INTO label VALUES (?,?)', ('dictionary', 'term1'))
        self.dbs = {'lookup': db}
        self.changed = False

    def check_unchanged(self):
        if self.changed:
            raise ContractError('glossary changed')

    def card(self, source, node):
        return {'id': concept_id(source, node), 'source': source, 'node_id': node,
                'canonical_approval': False, 'labels': [{'text': '가상 용어', 'kind': 'LABEL'}]}

    def lookup(self, label, **kwargs):
        return {'concepts': [self.card('dictionary', 'term1')], 'total': 1, 'next_offset': None}

    def inspect(self, cid):
        return {'definitions': [], 'relations': [], 'status': 'UNREVIEWED'}

    def entry_links(self, cid):
        return [{'entry_id': 'term1', 'mapping_id': 'm1', 'status': 'CANDIDATE'}]

    def close(self):
        self.dbs['lookup'].close()


def normalized_output(context):
    raw = context['raw']; row = next(r for r in raw['index'] if r['text'])
    locator = {'payload_hash': raw['payload_hash'], 'pointer': row['pointer'],
               'start': 0, 'end': len(row['text']), 'quote': row['text']}
    absent = {'state': 'NOT_RECORDED', 'value': None, 'locators': []}
    observation = {'id': 'O1', 'kind': 'CLAIM', 'statement': {'state': 'PRESENT', 'value': row['text'], 'locators': [locator]},
        'reason': deepcopy(absent), 'purpose': deepcopy(absent), 'scope': deepcopy(absent),
        'previous_refs': [], 'semantic_elements': [], 'glossary_refs': [], 'source_claims': [], 'unresolved': []}
    return {'observations': [observation], 'coverage': [{'pointer': s['pointer'],
        'state': 'USED' if s['pointer'] == row['pointer'] else 'NON_JUDGMENT',
        'observation_ids': ['O1'] if s['pointer'] == row['pointer'] else [], 'reason': '기록 분류'} for s in raw['index']],
        'unresolved': []}


@pytest.fixture
def env(tmp_path):
    database = tmp_path / 'work.sqlite'
    repo = Repository(lambda: sqlite3.connect(database)); repo.initialize()
    glossary = GlossaryBinding(Glossary(), snapshot='snapshot-1')
    source = {'id': 'S1', 'anchor': {'document_id': 'fictional', 'version': 'a'*64, 'unit_id': 'article1',
              'content_sha256': content_hash('가상 주체는 물건을 제출한다. 단 가상 예외에는 제출하지 않는다.'), 'label': '가상 규정 제1조'},
              'text': '가상 주체는 물건을 제출한다. 단 가상 예외에는 제출하지 않는다.'}
    calls = []
    def generate(prompt, context, schema):
        calls.append(context)
        return normalized_output(context), {'call_id': str(len(calls))}
    w = DomainWorkflow(repo, LocalFolderStore(tmp_path/'objects'), actor='reviewer',
        source_reader=lambda a: source['text'] if a['document_id'] == 'fictional' and a['version'] == 'a'*64 else None,
        generate=generate, namespace='team1', source_snapshot='snapshot-1', acl_ref='acl1',
        document_ids=['fictional'], glossary=glossary, producer_binding='authoring-v1')
    domain = json.loads((ROOT/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json').read_text())
    business = json.loads((ROOT/'00_SYSTEM/ONTOLOGY_PROFILES/business-profile-v1.json').read_text())
    registered = w.save_profile(domain, business)
    w.review_profile(registered['bundle_id'], registered['revision'], registered['work_hash'], True, '합성 계약 검토')
    yield SimpleNamespace(w=w, repo=repo, source=source, calls=calls, domain=domain, business=business,
                          profile_id=registered['bundle_id'], profile_work_hash=registered['work_hash'], tmp=tmp_path)
    glossary.reader.close()


def add_observation(e, event='A', payload=None):
    raw = e.w.import_payload(payload or {'opinion': '이것은 원래의 가상 판단이다.'}, run_id='run-'+event, event_id=event)
    return e.w.normalize(raw['bundle_id'], profile_id=e.profile_id, profile_work_hash=e.profile_work_hash, labels=['가상 용어'])


def proposal(e, observation, *, base=None, exception=False, relation='NEW'):
    n = e.w.load(observation['bundle_id'])['normalized']
    oid = next(iter(accumulation.observation_rows([n])))
    p = e.w.selected_profile(e.profile_id, e.profile_work_hash)['effective']
    def node(key, kind, text):
        required = next(r['required_review_slots'] for r in p['node_types'] if r['kind'] == kind)
        slots = {s: {'state': 'NOT_RECORDED', 'value': None} for s in required}
        slots['statement'] = {'state': 'PRESENT', 'value': text}
        return {'id': key, 'kind': kind, 'text': text, 'slots': slots,
                'basis': [{'source': 'S1', 'quote': e.source['text']}], 'observation_refs': [oid], 'glossary_refs': []}
    graph = deepcopy(base) if base else {'nodes': [node('N1', 'EFFECT', '가상 주체는 물건을 제출한다.')],
        'edges': [], 'purposes': [{'id': 'P1', 'purpose': 'required-action', 'roots': ['N1'], 'title': '가상 제출 규칙'}],
        'unused_nodes': [], 'unresolved': []}
    if exception:
        x = node('N2', 'EXCEPTION', '가상 예외에는 제출하지 않는다.')
        x['slots']['modified_targets'] = {'state': 'PRESENT', 'value': ['N1']}
        graph['nodes'].append(x)
        graph['edges'].append({'id': 'E1', 'type': 'MODIFIES', 'from': 'N2', 'to': 'N1',
                               'basis': [{'source': 'S1', 'quote': e.source['text']}]})
    return {'graph': graph, 'comparisons': [{'observation_ref': oid, 'relation': relation, 'verdict': 'SUPPORTED',
             'reason': '가상 원문 대조', 'basis': [{'source': 'S1', 'quote': e.source['text']}], 'node_ids': ['N1']}], 'removed_nodes': []}


def save(e, obs, p, rev=0, bid='cb-kb-rule'):
    return e.w.save_accumulation(bundle_id=bid, expected_revision=rev, profile_id=e.profile_id,
        profile_work_hash=e.profile_work_hash, observation_ids=[obs['bundle_id']], originals=[e.source], proposal=p)


def approve_stage(e, d):
    e.w.review(d['bundle_id'], d['revision'], d['work_hash'], True, '조건·예외·원문 검토')
    return e.w.stage_publication(d['bundle_id'], d['revision'], d['work_hash'], e.repo.head(d['bundle_id'])['sequence'])


def test_a_then_b_exception_then_staged_c_consumption(env):
    a = add_observation(env); first = save(env, a, proposal(env, a))
    b = add_observation(env, 'B', '앞선 판단에 예외를 추가한다.')
    second = save(env, b, proposal(env, b, base=env.w.load(first['bundle_id'])['proposal']['graph'], exception=True, relation='COMPLEMENT'), 1)
    loaded = env.w.load(second['bundle_id'])
    assert len(loaded['observation_ledger']) == 2 and loaded['diff']['nodes']['added'] == ['N2']
    stage = approve_stage(env, second)
    assert env.repo.head(second['bundle_id'])['publication_id'] is None
    assert env.repo.lookup(env.source['anchor'], {'fictional'}) == []
    checked = env.w.verify_publication(stage['publication_id'])
    assert checked['binding']['actual_model_delivery'] is False
    activated = env.w.activate_publication(stage['publication_id'], 0, checked)
    assert activated['active']
    rows = env.repo.lookup(env.source['anchor'], {'fictional'})
    package = rows[0]['context']['assembly_package']
    catalog = assembly_compiler.bind_current(package, [{'anchor': env.source['anchor'], 'text': env.source['text'], 'evidence_refs': ['CURRENT_C1']}])
    assert catalog['paths'][0]['node_ids'] == ['N1', 'N2']
    assert catalog['paths'][0]['source_refs'] == ['CURRENT_C1']
    assert '제출하지 않는다' in catalog['paths'][0]['body']
    assert catalog['runtime_compilation'] is False
    assert env.repo.lookup(env.source['anchor'], set()) == []


def test_stale_accumulation_and_same_rule_guard(env):
    a = add_observation(env); p = proposal(env, a); save(env, a, p)
    b = add_observation(env, 'B'); changed = proposal(env, b, relation='SAME')
    with pytest.raises(ContractError, match='SAME'):
        save(env, b, changed, 1)
    with pytest.raises(ContractError, match='stale accumulation'):
        save(env, b, proposal(env, b), 2)
    assert env.repo.latest('cb-kb-rule')['revision'] == 1


@pytest.mark.parametrize('relation', ['DIFFERENT_SCOPE', 'VERSION_CHANGE'])
def test_different_scope_and_version_cannot_overwrite(env, relation):
    a = add_observation(env); save(env, a, proposal(env, a))
    b = add_observation(env, 'B')
    with pytest.raises(ContractError, match='separate bundle'):
        save(env, b, proposal(env, b, relation=relation), 1)
    assert save(env, b, proposal(env, b, relation=relation), bid='cb-kb-other')['revision'] == 1


def test_duplicate_raw_and_extraction_not_independent(env):
    a = add_observation(env); again = add_observation(env)
    assert a['work_hash'] == again['work_hash'] and len(env.calls) == 1
    n = env.w.load(a['bundle_id'])['normalized']
    with pytest.raises(ContractError, match='multiple independent'):
        accumulation.observation_rows([n, n])
    with pytest.raises(ContractError, match='immutable event'):
        env.w.import_payload('changed', run_id='run-A', event_id='A')


@pytest.mark.parametrize('payload', [{'nested': [{'weird/key~': '오답😀'}]}, ['오답😀', None, 3], '순서 있는 원래 오답😀'])
def test_format_independent_locations_preserve_wrong_opinions(env, payload):
    row = add_observation(env, payload=payload)
    n = env.w.load(row['bundle_id'])['normalized']
    raw = env.calls[0]['raw']
    assert n['proposal']['observations'][0]['statement']['value'] == raw['index'][0]['text']
    assert n['proposal']['observations'][0]['reason']['state'] == 'NOT_RECORDED'


@pytest.mark.parametrize('fault', ['quote', 'pointer', 'hash', 'coverage', 'invented_glossary', 'silently_corrected'])
def test_normalizer_rejects_invalid_provenance(env, fault):
    raw = env.w.load(env.w.import_payload({'nested': '원래 오답😀'}, run_id='r', event_id='e')['bundle_id'])['raw']
    candidates = env.w.glossary.candidates(['가상 용어'])
    p = env.w.selected_profile(env.profile_id, env.profile_work_hash)
    value = normalized_output({'raw': raw}); o = value['observations'][0]; l = o['statement']['locators'][0]
    if fault == 'quote': l['end'] -= 1
    if fault == 'pointer': l['pointer'] = '/missing'
    if fault == 'hash': l['payload_hash'] = 'b'*64
    if fault == 'coverage': value['coverage'] = []
    if fault == 'invented_glossary': o['glossary_refs'] = [{'concept_id': 'fake', 'state': 'CONTEXT_LINKED', 'mention_refs': [deepcopy(l)], 'reason': 'guess'}]
    if fault == 'silently_corrected': o['statement']['value'] = '새로 고친 정답'
    with pytest.raises(ContractError): observations.validate_observations(value, raw, p, candidates)


def test_format_repair_only_once_and_invalid_history(env):
    count = []
    def generate(prompt, ctx, schema):
        count.append(ctx); p = normalized_output(ctx)
        if len(count) == 1: p['coverage'] = []
        return p, {'call': len(count)}
    env.w.generate = generate
    add_observation(env)
    assert len(count) == 2 and 'repair' in count[1]
    job = env.w.load(env.repo.list(prefix='job-')[0]['bundle_id'])
    assert job['phase'] == 'READY' and len(job['attempts']) == 1
    assert job['attempts'][0]['response']['coverage'] == []


def test_repeat_format_error_stops_after_two(env):
    calls = []
    def generate(prompt, ctx, schema):
        calls.append(1); return {'invalid': True}, {'call': len(calls)}
    env.w.generate = generate
    for _ in range(2):
        with pytest.raises(ContractError): add_observation(env)
    assert len(calls) == 2
    assert env.w.load(env.repo.list(prefix='job-')[0]['bundle_id'])['phase'] == 'INVALID'


def test_unknown_transport_no_retry_on_resume(env):
    calls = []
    def fail(*args):
        calls.append(1); raise TimeoutError('unknown request')
    env.w.generate = fail
    with pytest.raises(TimeoutError): add_observation(env)
    with pytest.raises(ContractError, match='UNKNOWN'): add_observation(env)
    assert len(calls) == 1


def test_deadline_late_result_preserves_response(env):
    now = [100.0]; env.w.clock = lambda: now[0]
    def generate(prompt, ctx, schema):
        now[0] = 500
        return normalized_output(ctx), {'call': 1}
    env.w.generate = generate
    with pytest.raises(ContractError, match='late'): add_observation(env)
    job = env.w.load(env.repo.list(prefix='job-')[0]['bundle_id'])
    assert job['phase'] == 'BUDGET_EXHAUSTED' and job['response']['observations']


def test_save_failure_reconciles_exact_result_without_model_recall(env, monkeypatch):
    original = env.repo.draft; failed = []
    def failing(bid, key, *args, **kwargs):
        if bid.startswith('job-') and env.w.store.get(key)['phase'] == 'RESPONSE_RECEIVED' and not failed:
            failed.append(key); raise OSError('SQL unavailable')
        return original(bid, key, *args, **kwargs)
    monkeypatch.setattr(env.repo, 'draft', failing)
    with pytest.raises(SaveUnconfirmed) as error: add_observation(env)
    jobid = env.repo.list(prefix='job-')[0]['bundle_id']
    env.w.reconcile(error.value.object_hash, env.repo.latest(jobid)['revision'])
    add_observation(env)
    assert len(env.calls) == 1


def test_glossary_restore_drift_and_no_implicit_approval(env):
    candidate = env.w.glossary.candidates(['가상 용어'])
    assert candidate['candidates'][0]['source_status']['canonical_approval'] is False
    assert candidate['candidates'][0]['entry_links'][0]['status'] == 'CANDIDATE'
    with pytest.raises(ContractError, match='no longer exists'): env.w.glossary.restore('dictionary', 'fake')
    env.w.glossary.reader.changed = True
    with pytest.raises(ContractError): env.w.glossary.verify_candidates(candidate)


@pytest.mark.parametrize('fault', ['missing_basis', 'fake_source', 'bad_edge', 'cycle', 'dangling', 'missing_exception_target', 'slot_edge_disagreement'])
def test_graph_security_and_dependency_failures(env, fault):
    a = add_observation(env); p = proposal(env, a, exception=True); graph = p['graph']
    if fault == 'missing_basis': graph['nodes'][0]['basis'] = []
    if fault == 'fake_source': graph['edges'][0]['basis'][0]['source'] = 'UNKNOWN'
    if fault == 'bad_edge': graph['edges'][0]['from'] = 'N1'
    if fault == 'dangling': graph['nodes'][1]['slots']['modified_targets']['value'] = ['MISSING']
    if fault == 'missing_exception_target': graph['edges'] = []
    if fault == 'slot_edge_disagreement': graph['nodes'][0]['slots']['exceptions'] = {'state': 'PRESENT', 'value': []}
    if fault == 'cycle':
        graph['nodes'][1]['kind'] = 'CONDITION'
        graph['nodes'][1]['slots'] = {k: deepcopy(graph['nodes'][1]['slots'].get(k, {'state':'NOT_RECORDED','value':None})) for k in ['statement','scope','expression','time_basis']}
        graph['edges'] = [{'id':'E2','type':'REQUIRES_CONDITION','from':'N2','to':'N2','basis':graph['nodes'][1]['basis']}]
    with pytest.raises(ContractError): save(env, a, p)


def test_current_original_missing_or_changed_withholds_whole_path(env):
    a = add_observation(env); d = save(env, a, proposal(env, a)); stage = approve_stage(env, d)
    package = env.repo.publication(stage['publication_id'], {'fictional'})['context']['assembly_package']
    assert assembly_compiler.bind_current(package, [])['withheld'][0]['missing_originals'] == ['S1']
    with pytest.raises(ContractError): assembly_compiler.bind_current(package, [{'anchor':env.source['anchor'], 'text':'partial', 'evidence_refs':['E1']}])


def test_staging_cas_rollback_and_double_publish(env):
    a = add_observation(env); d = save(env, a, proposal(env, a)); stage = approve_stage(env, d)
    assert env.w.stage_publication(d['bundle_id'],d['revision'],d['work_hash'],0)['publication_id'] == stage['publication_id']
    checked = env.w.verify_publication(stage['publication_id'])
    with pytest.raises(ContractError, match='stale activation'): env.w.activate_publication(stage['publication_id'], 9, checked)
    with pytest.raises(ContractError): env.repo.activate(d['bundle_id'], stage['publication_id'], 0, 'reviewer')
    env.w.activate_publication(stage['publication_id'], 0, checked)
    env.repo.activate(d['bundle_id'], None, 1, 'reviewer')
    assert env.w.stage_publication(d['bundle_id'],d['revision'],d['work_hash'],2)['active'] is False
    assert env.repo.head(d['bundle_id'])['publication_id'] is None
    env.w.activate_publication(stage['publication_id'], 2, checked)
    assert env.repo.head(d['bundle_id'])['sequence'] == 3


def test_no_profile_self_approval_or_parent_drift(env):
    d = deepcopy(env.domain); d['runtime_enabled'] = True
    with pytest.raises(ContractError): profile.compile_profile(d)
    b = deepcopy(env.business); b['parent']['sha256'] = 'f'*64
    with pytest.raises(ContractError, match='parent'): profile.compile_profile(env.domain, b)
    b = deepcopy(env.business); b['selected_review_rules'] = []
    with pytest.raises(ContractError): profile.compile_profile(env.domain, b)
    assert profile.compile_profile(env.domain, env.business) == profile.compile_profile(env.domain, env.business)


def test_acl_prevents_loading_cross_team_raw(env):
    row = add_observation(env)
    env.w.namespace = 'other-team'
    with pytest.raises(ContractError, match='scope'): env.w.load(row['bundle_id'])


def test_existing_cli_uses_same_store_and_reviewer(env, monkeypatch, capsys):
    from semantic_runtime.ontology_work import domain_cli, cli
    monkeypatch.setattr(domain_cli, 'domain_workflow', lambda **kwargs: env.w)
    monkeypatch.setattr(env.w.glossary.reader, 'close', lambda: None)
    a = add_observation(env); d = save(env, a, proposal(env, a))
    cli.main(['domain-review','--bundle',d['bundle_id'],'--revision','1','--work-hash',d['work_hash'],'--approve','--reason','CLI 검토'])
    assert json.loads(capsys.readouterr().out)['approval']
    cli.main(['stage-publication','--bundle',d['bundle_id'],'--revision','1','--work-hash',d['work_hash'],'--expected-sequence','0'])
    stage = json.loads(capsys.readouterr().out); assert not stage['active']
    cli.main(['verify-publication','--publication-id',stage['publication_id']])
    receipt = json.loads(capsys.readouterr().out)
    path = env.tmp/'consumer.json'; path.write_text(json.dumps(receipt))
    cli.main(['activate-publication','--publication-id',stage['publication_id'],'--expected-sequence','0','--receipt',str(path)])
    assert json.loads(capsys.readouterr().out)['active']
    cli.main(['domain-status','--bundle',d['bundle_id']])
    loaded = json.loads(capsys.readouterr().out)
    assert loaded['status'] == 'APPROVED' and loaded['reviewer'] == 'reviewer'


def test_compressed_journal_export_keeps_history_and_checkpoint(env, monkeypatch):
    from semantic_runtime.legal_agent import journal_storage
    monkeypatch.setenv('GENOS_JOURNAL_STORAGE','compact')
    db = journal_storage.connect(':memory:'); journal_storage.initialize(db)
    db.execute('CREATE TABLE run(singleton INTEGER,run_id TEXT,binding_hash TEXT)')
    db.execute('INSERT INTO run VALUES(1,?,?)',('past-run','producer-hash'))
    db.execute('CREATE TABLE event(seq INTEGER,event_id TEXT,payload_json TEXT,payload_hash TEXT)')
    for seq, text in enumerate(['원래 오답 '*200,'철회·정정 '*200],1):
        payload={'anything':text}; db.execute('INSERT INTO event VALUES(?,?,?,?)',
            (seq,'event'+str(seq),journal_storage.store(db,json.dumps(payload,ensure_ascii=False)),digest(payload)))
    metadata=dict(namespace='team1',source_snapshot='snapshot-1',acl_ref='acl1',document_ids=['fictional'])
    first=observations.export_journal(db,after=0,limit=1,authorize=lambda r: None,metadata=metadata)
    second=observations.export_journal(db,after=first['checkpoint'],limit=1,authorize=lambda r: None,metadata=metadata)
    assert first['events'][0]['payload']['anything'].startswith('원래 오답')
    assert second['events'][0]['payload']['anything'].startswith('철회·정정')
    assert second['checkpoint']==2 and second['events'][0]['verified_source_receipts']==[]
    env.w.ingest(first['events'][0]);env.w.ingest(second['events'][0])
    db.close()


def test_v1_reader_and_publication_stay_separate(env):
    from semantic_runtime.ontology_work.workflow import Workflow
    from semantic_runtime.ontology_work import schema
    a=add_observation(env);d=save(env,a,proposal(env,a))
    legacy=Workflow(env.repo,env.w.store,actor='reviewer',source_reader=env.w.source_reader)
    with pytest.raises(ContractError,match='domain-profile reader'):legacy.load(d['bundle_id'])
    work={'version':schema.VERSION,'concept':'legacy','originals':[env.source], 'judgments':[],'origin':{'run_id':'legacy'}}
    proposal_v1={'components':[{'id':'A','text':'기존 조건','requires':[],'basis':[{'source':'S1','quote':env.source['text']}]},
                               {'id':'B','text':'기존 효과','requires':['A'],'basis':[{'source':'S1','quote':env.source['text']}]}],
                 'paths':[{'id':'P1','title':'기존 경로','business_use':'기존 업무','conditions':['A'],'calculations':[],'outcomes':['B'],'notes':[]}],
                 'unused_components':{}}
    draft=legacy.save(work,proposal_v1,bundle_id='cb-legacy')
    legacy.review('cb-legacy',1,draft['work_hash'],True,'legacy review')
    published=legacy.publish('cb-legacy',1,draft['work_hash'],0)
    assert published['active']
    assert 'scenario_package' in env.repo.lookup(env.source['anchor'],{'fictional'})[0]['context']


def test_contradiction_preserves_old_opinion_and_source_drift_blocks_publication(env):
    a=add_observation(env);first=save(env,a,proposal(env,a))
    b=add_observation(env,'B','원래 판단을 반박한다.')
    second=save(env,b,proposal(env,b,relation='CONTRADICTION'),1)
    assert env.w.load(second['bundle_id'])['review_state']=='REVIEW_CONFLICT'
    assert len(env.w.load(second['bundle_id'])['comparison_history'])==2
    assert env.w.load(first['bundle_id'],1)['proposal']==proposal(env,a)
    env.w.source_reader=lambda _: 'different'
    with pytest.raises(ContractError,match='source version/content'):approve_stage(env,second)


def test_late_staged_revision_needs_explicit_rollback(env):
    a=add_observation(env);first=save(env,a,proposal(env,a));stage=approve_stage(env,first)
    checked=env.w.verify_publication(stage['publication_id'])
    b=add_observation(env,'B');save(env,b,proposal(env,b,relation='COMPLEMENT'),1)
    with pytest.raises(ContractError,match='stale staged work'):env.w.activate_publication(stage['publication_id'],0,checked)
    assert env.repo.head(first['bundle_id'])['publication_id'] is None
    assert env.w.activate_publication(stage['publication_id'],0,checked,rollback=True)['active']


def test_model_not_configured_does_not_reserve_stuck_job(env):
    original=env.w.generate;env.w.generate=None
    with pytest.raises(ContractError,match='not configured'):add_observation(env)
    assert env.repo.list(prefix='job-')==[]
    env.w.generate=original;row=add_observation(env);env.w.generate=None
    assert add_observation(env)['work_hash']==row['work_hash']


def test_glossary_drift_during_call_is_not_a_model_repair(env):
    calls=[]
    def generate(prompt,context,schema):
        calls.append(1);env.w.glossary.reader.changed=True
        return normalized_output(context),{'call':1}
    env.w.generate=generate
    with pytest.raises(ContractError):add_observation(env)
    assert len(calls)==1
    job=env.w.load(env.repo.list(prefix='job-')[0]['bundle_id'])
    assert job['phase']=='BINDING_FAILED' and job['response']['observations']


def test_concurrent_duplicate_job_calls_model_once(env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    entered=Event();release=Event();calls=[]
    def generate(*args):
        calls.append(1);entered.set();assert release.wait(5);return {'ok':True},{'call':1}
    env.w.generate=generate
    with ThreadPoolExecutor(max_workers=1) as pool:
        first=pool.submit(env.w._job,'TEST',{},'prompt',{},lambda p:None)
        assert entered.wait(5)
        try:
            with pytest.raises(ContractError,match='SENT'):env.w._job('TEST',{},'prompt',{},lambda p:None)
        finally:release.set()
        assert first.result()[0]=={'ok':True}
    assert len(calls)==1


@pytest.mark.parametrize('mode',['valid','invalid_json','incomplete','http_error'])
def test_authoring_transport_classifies_known_responses_and_no_token_cap(env,monkeypatch,mode):
    import httpx,time
    from semantic_runtime.ontology_work import authoring_model
    from semantic_runtime import genos
    from lawrag.core import request_deadline
    endpoint=SimpleNamespace(headers={},url=lambda p:'https://synthetic.invalid'+p)
    monkeypatch.setattr(genos,'from_env',lambda kind:(endpoint,'synthetic'))
    monkeypatch.setattr(genos,'advertised_model',lambda *a:'synthetic')
    requests=[]
    def post(url,**kwargs):
        requests.append(kwargs)
        if mode=='http_error':return httpx.Response(429,text='synthetic rejection')
        return httpx.Response(200,json={'choices':[{'finish_reason':'length' if mode=='incomplete' else 'stop',
            'message':{'content':'{broken' if mode=='invalid_json' else '{"ok":true}'}}]})
    monkeypatch.setattr(request_deadline,'post_json',post)
    if mode in ('incomplete','http_error'):
        with pytest.raises(authoring_model.AuthoringFailure) as error:
            authoring_model.generate(env.w.store,'prompt',{'call_budget':{'absolute_deadline':time.time()+180}}, {})
        assert error.value.status==('INCOMPLETE_RESPONSE' if mode=='incomplete' else 'HTTP_REJECTED')
    else:
        value,receipt=authoring_model.generate(env.w.store,'prompt',{'call_budget':{'absolute_deadline':time.time()+180}}, {})
        assert value==({'invalid_json_text':'{broken'} if mode=='invalid_json' else {'ok':True})
        assert receipt['physical_calls']==1
    assert len(requests)==1
    assert not ({'max_tokens','max_output_tokens','max_completion_tokens'} & requests[0]['json_body'].keys())
