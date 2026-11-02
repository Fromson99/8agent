"""Synthetic workspace contracts; no model, production corpus or Oracle writes."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_domain_profile_workflow import env, proposal as typed_proposal
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.ontology_work.domain_workflow import SaveUnconfirmed
from semantic_runtime.ontology_work.wiki_workspace import Workspace
from semantic_runtime.ontology_work.wiki_projection import compile_selection
from semantic_runtime.ontology_work import wiki_contracts as wc, runtime, assembly_compiler


@pytest.fixture
def ws(env):
    original = env.w.generate
    def modern(prompt, context, schema):
        value, receipt = original(prompt, context, schema)
        if 'raw' in context: value = wire_normalization(value)
        return value, receipt
    env.w.generate = modern
    w = Workspace(env.repo, env.w.store, actor=env.w.actor, source_reader=env.w.source_reader,
        generate=env.w.generate, namespace=env.w.namespace, source_snapshot=env.w.source_snapshot,
        acl_ref=env.w.acl_ref, document_ids=env.w.document_ids, producer_binding='wiki-test', can_publish=True)
    env.w.can_publish_workspace = True
    env.repo.workspace_scopes = {wc.scope_key(w.scope())}
    return w


def wire_normalization(value):
    """Only adapt the historical synthetic generator to the current request wire."""
    value = deepcopy(value)
    for row in value['observations']:
        for name in ('reason', 'purpose'):
            old = row.pop(name)
            assert old['state'] == 'NOT_RECORDED'
            row['recorded_' + name] = None
    value['coverage'] = {r['pointer']: {k: v for k, v in r.items() if k != 'pointer'} for r in value['coverage']}
    def walk(v):
        if isinstance(v, dict):
            if set(v) == {'payload_hash', 'pointer', 'start', 'end', 'quote'}:
                assert v['start'] == 0
                return {'pointer': v['pointer'], 'quote': v['quote'], 'occurrence': 0}
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list): return [walk(x) for x in v]
        return v
    return walk(value)


def seed(e, w, change='one', text='가상 주체는 물건을 제출한다.', *, basis=True, open_items=()):
    raw = w.import_payload(text, event_id=change, run_id='wiki-test')
    source = e.source
    bases = [{'anchor': source['anchor'], 'quote': source['text'], 'start_cp': 0, 'end_cp': len(source['text'])}] if basis else []
    spec = {'change_id': change, 'raw_ids': [raw['bundle_id']], 'operations': [
        {'op': 'ADD_STATEMENT', 'target': '@s', 'value': {'text': text, 'origin_refs': [raw['bundle_id']], 'source_basis': bases, 'open_items': list(open_items)}},
        {'op': 'CREATE_ENTRY', 'target': '@e', 'value': {'title': '자유 항목 ' + change, 'body': '자유 설명', 'statement_refs': ['@s']}},
        {'op': 'CREATE_VIEW', 'target': '@v', 'value': {'title': '임시 보기', 'member_refs': ['@e']}}]}
    result = w.apply(**spec)
    return SimpleNamespace(raw=raw, spec=spec, result=result, sid=result['handles']['@s'], eid=result['handles']['@e'], vid=result['handles']['@v'])


def pin(w, *ids):
    return {bid: {k: w.item(bid)[k] for k in ('revision', 'work_hash')} for bid in ids}


def compiled(e, w, item, *, coverage='INCLUDED'):
    observation = e.w.normalize(item.raw['bundle_id'], profile_id=e.profile_id, profile_work_hash=e.profile_work_hash)
    p = typed_proposal(e, observation)
    p['graph']['nodes'][0]['text'] = w.item(item.sid)['content']['text']
    p['graph']['nodes'][0]['slots']['statement']['value'] = w.item(item.sid)['content']['text']
    value = {'accumulation': p, 'coverage': [{'statement_id': item.sid, 'decision': coverage, 'node_ids': ['N1'], 'reason': '합성 범위 검토'}]}
    args = dict(statement_ids=[item.sid], purpose='합성 제출 규칙', profile_id=e.profile_id,
                profile_work_hash=e.profile_work_hash, originals=[e.source], observation_ids=[observation['bundle_id']], proposal=value)
    return compile_selection(e.w, w, **args), args


def published(e, w, item):
    d, args = compiled(e, w, item)
    e.w.review(d['bundle_id'], d['revision'], d['work_hash'], True, '합성 원문·범위 검토')
    stage = e.w.stage_publication(d['bundle_id'], d['revision'], d['work_hash'], 0)
    receipt = e.w.verify_publication(stage['publication_id'])
    e.w.activate_publication(stage['publication_id'], 0, receipt)
    return d, stage, receipt


def test_dataiku_journal_page_preserves_corrections_and_partial_retry(env, ws, monkeypatch):
    import importlib.util
    from semantic_runtime.legal_agent import journal_storage
    root = Path(__file__).resolve().parents[2]
    path = root / '08_DEPLOYMENT/DATAIKU/ontology_workflow_20261028_r1/ingest_agent_events.py'
    spec = importlib.util.spec_from_file_location('workspace_ingest_recipe', path)
    recipe = importlib.util.module_from_spec(spec); spec.loader.exec_module(recipe)
    db = journal_storage.connect(':memory:'); journal_storage.initialize(db)
    db.execute('CREATE TABLE run(singleton INTEGER,run_id TEXT,binding_hash TEXT)')
    db.execute('INSERT INTO run VALUES(1,?,?)', ('past-run', 'producer-hash'))
    db.execute('CREATE TABLE event(seq INTEGER,event_id TEXT,payload_json TEXT,payload_hash TEXT)')
    for seq, text in enumerate(['원래 판단', '철회와 정정'], 1):
        payload = {'opinion': text}
        db.execute('INSERT INTO event VALUES(?,?,?,?)',
            (seq, str(seq), journal_storage.store(db, json.dumps(payload, ensure_ascii=False)), digest(payload)))
    arguments = dict(after=0, metadata=ws.scope(ws.document_ids), authorize=lambda run: None)
    original = ws.ingest; imported = []
    def fail_second(raw):
        if raw['raw_event_id'] == '2': raise OSError('synthetic interrupted import')
        value = original(raw); imported.append(value); return value
    monkeypatch.setattr(ws, 'ingest', fail_second)
    with pytest.raises(OSError): recipe.ingest_journal_page(db, ws, **arguments)
    assert len(imported) == 1
    monkeypatch.setattr(ws, 'ingest', original)
    page = recipe.ingest_journal_page(db, ws, **arguments)
    assert page['checkpoint'] == 2 and len(page['receipts']) == 2
    assert page['receipts'][0]['bundle_id'] == imported[0]['bundle_id']
    assert page['stage'] == 'RAW_STORED_NOT_APPROVED'
    assert ws.load(page['receipts'][1]['bundle_id'])['raw']['payload']['opinion'] == '철회와 정정'
    assert ws.list_items()['items'] == []
    def deny(run): raise ContractError('unauthorized journal')
    with pytest.raises(ContractError, match='unauthorized'):
        recipe.ingest_journal_page(db, ws, **{**arguments, 'authorize': deny})
    db.close()


def test_profile_free_storage_layout_and_idempotence(env, ws):
    item = seed(env, ws, basis=False)
    assert ws.glossary is None
    assert ws.item(item.sid)['content']['source_basis'] == []
    before = ws.item(item.sid)
    same = ws.apply(**item.spec)
    assert same['reused'] and same['objects'] == item.result['objects']
    ws.apply(change_id='rename', expected=pin(ws, item.eid, item.sid), operations=[
        {'op': 'REVISE_ENTRY', 'target': item.eid, 'value': {'title': '새로운 제목'}}])
    assert ws.item(item.sid) == before
    assert ws.item(item.eid)['revision'] == 2
    assert ws.list_items(query='새로운')['items'][0]['bundle_id'] == item.eid
    assert env.repo.head(item.sid)['publication_id'] is None


def test_free_link_cycle_is_not_compiler_dependency(env, ws):
    a, b = seed(env, ws), seed(env, ws, 'two')
    expected = pin(ws, a.eid, b.eid, a.sid, b.sid)
    ws.apply(change_id='cycle', expected=expected, operations=[
        {'op': 'LINK', 'target': a.eid, 'value': {'label': '관련', 'target': b.eid}},
        {'op': 'LINK', 'target': b.eid, 'value': {'label': '되돌아보기', 'target': a.eid}}])
    d, _ = compiled(env, ws, a)
    assert env.w.preview(d['bundle_id'])['graph']['edges'] == []
    assert ws.item(a.eid)['content']['navigation_links'][0]['navigation_only']


def test_compile_review_publish_actual_current_source_binding(env, ws):
    item = seed(env, ws, open_items=['긴급처리 관계 미확인'])
    d, stage, _ = published(env, ws, item)
    package = env.repo.lookup(env.source['anchor'], {'fictional'})[0]['context']['assembly_package']
    assert package['authority'] == 'APPROVED' and package['runtime_compilation'] is False
    assert package['paths'][0]['status'] == 'PARTIAL'
    assert '긴급처리' in package['graph']['unresolved'][0]
    catalog = assembly_compiler.bind_current(package, [{'anchor': env.source['anchor'], 'text': env.source['text'], 'evidence_refs': ['actual-current-ref']}])
    assert catalog['paths'][0]['source_refs'] == ['actual-current-ref']
    assert ws.catalog()[0]['publications'][stage['publication_id']]['statement_ids'] == [item.sid]
    assert env.w.load(d['bundle_id'])['workspace_projection']['coverage'][0]['decision'] == 'INCLUDED'


def test_compile_requires_real_origins_and_no_implicit_approval(env, ws):
    item = seed(env, ws)
    d, args = compiled(env, ws, item)
    assert env.w.load(d['bundle_id'])['status'] == 'DRAFT'
    assert not env.repo.lookup(env.source['anchor'], {'fictional'})
    assert compile_selection(env.w, ws, **args)['reused']
    args['proposal']['accumulation']['graph']['nodes'][0]['text'] = '다른 의미'
    with pytest.raises(ContractError, match='differs'): compile_selection(env.w, ws, **args)
    other = seed(env, ws, 'other')
    args.update(statement_ids=[other.sid], proposal=None)
    with pytest.raises(ContractError, match='exactly'): compile_selection(env.w, ws, **args)


def test_plain_domain_cannot_bypass_projection(env, ws):
    item = seed(env, ws); d, _ = compiled(env, ws, item)
    work = env.w.load(d['bundle_id'])
    with pytest.raises(ContractError, match='selected-statement'):
        env.w.save_accumulation(bundle_id=d['bundle_id'], expected_revision=1,
            profile_id=env.profile_id, profile_work_hash=env.profile_work_hash,
            observation_ids=work['observation_ids'], originals=[env.source], proposal=work['proposal'])
    with pytest.raises(ContractError, match='workspace workflow'):
        env.repo.activate(d['bundle_id'], None, 0, 'unprivileged-editor')


def test_workspace_publication_verification_respects_author_scope(env, ws):
    item = seed(env, ws); d, stage, receipt = published(env, ws, item)
    env.w.namespace = 'another-team'
    with pytest.raises(ContractError): env.w.verify_publication(stage['publication_id'])
    with pytest.raises(ContractError): env.w.activate_publication(stage['publication_id'], 1, receipt)


@pytest.mark.parametrize('fault', ['quote', 'range', 'hash', 'document', 'missing_origin', 'navigation_exec', 'extra_field'])
def test_invalid_changes_do_not_commit(env, ws, fault):
    item = seed(env, ws)
    spec = deepcopy(item.spec); spec['change_id'] = 'bad-' + fault
    value = spec['operations'][0]['value']; basis = value['source_basis'][0]
    if fault == 'quote': basis['quote'] = '없는 문장'
    if fault == 'range': basis['end_cp'] += 1
    if fault == 'hash': basis['anchor']['content_sha256'] = 'f'*64
    if fault == 'document': basis['anchor']['document_id'] = 'denied'
    if fault == 'missing_origin': value['origin_refs'] = ['raw-missing']
    if fault == 'navigation_exec': spec['operations'][1]['value']['navigation_links'] = [{'label': 'rule', 'target': '@s', 'navigation_only': False}]
    if fault == 'extra_field': value['approved'] = True
    before = env.repo.latest(ws.catalog_id)
    with pytest.raises(ContractError): ws.apply(**spec)
    assert env.repo.latest(ws.catalog_id) == before


def test_conflicting_update_and_operation_identity(env, ws):
    item = seed(env, ws); expected = pin(ws, item.sid)
    spec = {'change_id': 'edit', 'expected': expected, 'operations': [{'op': 'REVISE_STATEMENT', 'target': item.sid, 'value': {'text': '새 해석'}}]}
    ws.apply(**spec)
    with pytest.raises(ContractError, match='operation ID'): ws.apply(**{**spec, 'operations': [{'op': 'REVISE_STATEMENT', 'target': item.sid, 'value': {'text': '또 다른 해석'}}]})
    with pytest.raises(ContractError, match='expected revision'): ws.apply(**{**spec, 'change_id': 'another'})
    assert ws.item(item.sid, 1)['content']['text'] != ws.item(item.sid)['content']['text']


def test_atomic_failure_and_reconcile_no_model(env, ws, monkeypatch):
    item = seed(env, ws)
    expected = pin(ws, item.eid, item.sid); before = env.repo.latest(ws.catalog_id)
    original = env.repo.event
    def fail(c, bid, *args, **kwargs):
        if bid == item.sid: raise OSError('injected SQL failure')
        return original(c, bid, *args, **kwargs)
    monkeypatch.setattr(env.repo, 'event', fail)
    with pytest.raises(SaveUnconfirmed) as error:
        ws.apply(change_id='atomic', expected=expected, operations=[
            {'op': 'REVISE_ENTRY', 'target': item.eid, 'value': {'title': '새 제목'}},
            {'op': 'REVISE_STATEMENT', 'target': item.sid, 'value': {'text': '새 문장'}}])
    assert env.repo.latest(ws.catalog_id) == before
    assert ws.item(item.eid)['revision'] == ws.item(item.sid)['revision'] == 1
    monkeypatch.setattr(env.repo, 'event', original)
    assert ws.reconcile_change(error.value.object_hash)['objects'][item.sid]['revision'] == 2
    assert not env.calls


def test_commit_ack_lost_reconciles_once(env, ws, monkeypatch):
    item = seed(env, ws); original = env.repo.commit_workspace_change
    def lost(**kwargs): original(**kwargs); raise OSError('commit acknowledgment lost')
    monkeypatch.setattr(env.repo, 'commit_workspace_change', lost)
    with pytest.raises(SaveUnconfirmed) as error:
        ws.apply(change_id='lost', expected=pin(ws, item.sid), operations=[{'op': 'REVISE_STATEMENT', 'target': item.sid, 'value': {'text': '추가 검토'}}])
    monkeypatch.setattr(env.repo, 'commit_workspace_change', original)
    result = ws.reconcile_change(error.value.object_hash)
    assert result['reused'] and ws.item(item.sid)['revision'] == 2


def test_withdrawal_removes_active_and_rejects_old_answer(env, ws):
    item = seed(env, ws); d, stage, receipt = published(env, ws, item)
    row = env.repo.lookup(env.source['anchor'], {'fictional'})[0]
    refs = [{'bundle_id': d['bundle_id'], 'publication_id': stage['publication_id'], 'package_sha256': digest(row['context'])}]
    assessment = {'assessment_basis': {'workspace_publications': refs}}
    runtime.assert_assessment(assessment, {'fictional'}, env.repo)
    ws.apply(change_id='withdraw', expected=pin(ws, item.sid), operations=[{'op': 'RETRACT', 'target': item.sid, 'value': {'reason': '근거 재검토'}}])
    assert env.repo.lookup(env.source['anchor'], {'fictional'}) == []
    assert env.repo.publication(stage['publication_id'], {'fictional'})['context'] == row['context']
    with pytest.raises(ContractError, match='REVOKED'): runtime.assert_assessment(assessment, {'fictional'}, env.repo)
    with pytest.raises(ContractError): env.w.activate_publication(stage['publication_id'], 2, receipt, rollback=True)
    assert env.repo.head(d['bundle_id'])['publication_id'] is None


def test_ordinary_draft_edit_keeps_old_publication_and_blocks_new_activation(env, ws):
    item = seed(env, ws); d, stage, receipt = published(env, ws, item)
    ws.apply(change_id='draft-change', expected=pin(ws, item.sid), operations=[{'op': 'REVISE_STATEMENT', 'target': item.sid, 'value': {'text': '아직 미검토인 새 해석'}}])
    assert env.repo.head(d['bundle_id'])['publication_id'] == stage['publication_id']
    assert env.repo.lookup(env.source['anchor'], {'fictional'})
    with pytest.raises(ContractError, match='changed'): env.w.activate_publication(stage['publication_id'], 1, receipt)


def test_scope_filters_metadata_and_runtime_publications(env, ws):
    item = seed(env, ws); published(env, ws, item)
    ws.document_ids = frozenset()
    assert ws.list_items()['items'] == []
    with pytest.raises(ContractError, match='scope'): ws.item(item.sid)
    env.repo.workspace_scopes = set()
    assert env.repo.lookup(env.source['anchor'], {'fictional'}) == []


def test_cursor_generation_and_index_bound(env, ws, monkeypatch):
    seed(env, ws); seed(env, ws, 'two')
    first = ws.list_items(limit=1)
    second = ws.list_items(limit=1, cursor=first['cursor'])
    assert first['items'][0]['bundle_id'] != second['items'][0]['bundle_id']
    seed(env, ws, 'three')
    with pytest.raises(ContractError, match='cursor'): ws.list_items(cursor=first['cursor'])
    from semantic_runtime.ontology_work import wiki_index
    monkeypatch.setattr(wiki_index, 'SHARD_LIMIT', 0)
    with pytest.raises(ContractError, match='partition limit'): seed(env, ws, 'overflow')


def test_manager_permission_and_model_unknown(env, ws):
    item = seed(env, ws); ws.can_publish = False
    with pytest.raises(ContractError, match='permission'):
        ws.apply(change_id='no-right', expected=pin(ws, item.sid), operations=[{'op': 'RETRACT', 'target': item.sid, 'value': {'reason': 'not authorized'}}])
    calls = []
    def unknown(*args): calls.append(1); raise TimeoutError('provider outcome unknown')
    ws.generate = unknown
    with pytest.raises(TimeoutError): ws.propose(change_id='model-unknown', raw_ids=[item.raw['bundle_id']])
    with pytest.raises(ContractError, match='UNKNOWN'): ws.propose(change_id='model-unknown', raw_ids=[item.raw['bundle_id']])
    assert len(calls) == 1


def test_cli_existing_entrypoint_and_factory_without_profile(env, ws, monkeypatch, capsys):
    from semantic_runtime.ontology_work import cli, wiki_cli
    monkeypatch.setattr(wiki_cli, 'workspace_workflow', lambda **kwargs: ws)
    item = seed(env, ws)
    cli.main(['workspace-status', '--bundle', item.eid])
    assert json.loads(capsys.readouterr().out)['content']['title'] == '자유 항목 one'
    cli.main(['workspace-list'])
    assert len(json.loads(capsys.readouterr().out)['items']) == 1
    from semantic_runtime.ontology_work import configuration
    cfg = {'operators': {'reviewer': {'document_ids': ['fictional']}},
           'workspace': {'namespace': 'team1', 'source_snapshot': 'snapshot-1', 'acl_ref': 'acl1'}}
    monkeypatch.setattr(configuration, 'settings', lambda: cfg)
    made = configuration.workspace_workflow(actor='reviewer', ports={'workflow': env.w})
    assert made.glossary is None and made.item(item.eid)['kind'] == 'ENTRY'


def test_compiler_v1_bytes_remain_unchanged():
    root = Path(__file__).resolve().parents[2]
    import hashlib
    baseline = json.loads((root / '09_ARTIFACTS/AUDITS/20261030-wiki-workspace-implementation/baseline.json').read_text())
    pins = {r['path']: r['sha256'] for r in baseline['files']}
    for name in ('profile.py', 'profile_schema.py', 'assembly_ir.py', 'assembly_compiler.py'):
        path = '02_BACKEND/semantic_runtime/ontology_work/' + name
        assert hashlib.sha256((root/path).read_bytes()).hexdigest() == pins[path]


@pytest.mark.parametrize('always_invalid', [False, True])
def test_proposal_repairs_once_and_preserves_failed_output(env, ws, always_invalid):
    raw = ws.import_payload('새 기록', event_id='propose', run_id='run')
    calls = []
    def generate(prompt, context, schema):
        calls.append(deepcopy(context))
        title = '' if len(calls) == 1 or always_invalid else '새 항목'
        return {'operations': [{'op': 'CREATE_ENTRY', 'target': '@e', 'value': {'title': title, 'body': '새 기록'}}]}, {'call': len(calls)}
    ws.generate = generate
    args = {'change_id': 'propose', 'raw_ids': [raw['bundle_id']]}
    if always_invalid:
        with pytest.raises(ContractError): ws.propose(**args)
        with pytest.raises(ContractError, match='INVALID'): ws.propose(**args)
        assert ws.list_items()['items'] == []
    else:
        value = ws.propose(**args)
        assert ws.list_items()['items'] == []
        ws.apply(**value)
        assert ws.list_items()['items'][0]['title'] == '새 항목'
    assert len(calls) == 2 and calls[1]['repair']['previous']['response']['operations'][0]['value']['title'] == ''


def projection_generator(env, item, calls):
    from test_domain_profile_workflow import normalized_output
    from semantic_runtime.ontology_work.authoring_semantics import AXES
    def generate(prompt, ctx, schema):
        calls.append(deepcopy(ctx))
        if 'raw' in ctx: return wire_normalization(normalized_output(ctx)), {'call': len(calls)}
        source_id = ctx['originals'][0]['id']
        if ctx.get('operation') == 'SOURCE_ANALYSIS':
            assert 'statements' not in ctx and 'observations' not in ctx
            return {source_id: {'norms': [{'quote': env.source['text'], 'modality': 'OBLIGATION',
                    'regulated_actions': [{'text': '물건을 제출한다', 'quote': '물건을 제출한다'}],
                    'applicability_conditions': [], 'performance_requirements': []}], 'unresolved': []}}, {'call': len(calls)}
        required = next(k['required_review_slots'] for k in ctx['profile']['node_types'] if k['kind'] == 'EFFECT')
        slots = {k: {'state': 'NOT_RECORDED', 'value': None} for k in required if k not in ('action', 'modality')}
        text = ctx['statements'][0]['content']['text']; slots['statement'] = {'state': 'PRESENT', 'value': text}
        ref = next(iter(ctx['observations']))
        graph = {'nodes': [{'id': 'N1', 'kind': 'EFFECT', 'text': text, 'slots': slots,
                  'basis': [{'source': source_id, 'quote': env.source['text']}], 'observation_refs': [ref], 'glossary_refs': []}],
                 'edges': [], 'purposes': [{'id': 'P1', 'purpose': 'required-action', 'roots': ['N1'], 'title': '합성 제출'}],
                 'unused_nodes': [], 'unresolved': []}
        return {'accumulation': {'graph': graph, 'comparisons': [{'observation_ref': ref, 'relation': 'NEW',
                    'verdict': 'SUPPORTED', 'reason': '합성 검토', 'basis': graph['nodes'][0]['basis'], 'node_ids': ['N1'],
                    'semantic_check': {axis: 'MATCH' for axis in AXES}}], 'removed_nodes': [],
                    'norm_links': [{'node_id': 'N1', 'source': source_id, 'norm_index': 0}], 'condition_links': []},
                'coverage': [{'statement_id': item.sid, 'decision': 'INCLUDED', 'node_ids': ['N1'], 'reason': '포함'}]}, {'call': len(calls)}
    return generate


def test_model_projection_runs_source_only_analysis_then_existing_compiler(env, ws):
    item = seed(env, ws); calls = []
    ws.generate = projection_generator(env, item, calls)
    args = dict(statement_ids=[item.sid], purpose='현재 원문 재사용', profile_id=env.profile_id,
                profile_work_hash=env.profile_work_hash, originals=[env.source])
    d = compile_selection(env.w, ws, **args)
    assert len(calls) == 3
    assert compile_selection(env.w, ws, **args)['reused'] and len(calls) == 3
    assert env.w.preview(d['bundle_id'])['paths'][0]['body'] == ws.item(item.sid)['content']['text']


def test_simultaneous_changes_have_one_winner(env, ws):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    item = seed(env, ws); expected = pin(ws, item.sid); barrier = Barrier(2)
    original = env.repo.commit_workspace_change
    def commit(**kwargs):
        barrier.wait(5)
        return original(**kwargs)
    env.repo.commit_workspace_change = commit
    def change(n):
        try:
            return ws.apply(change_id='concurrent-' + str(n), expected=expected,
                operations=[{'op': 'REVISE_STATEMENT', 'target': item.sid, 'value': {'text': '수정 ' + str(n)}}])
        except ContractError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(change, [1, 2]))
    assert sum(x is not None for x in outcomes) == 1
    assert ws.item(item.sid)['revision'] == 2


def test_withdraw_activation_race_uses_one_catalog_lock(env, ws, monkeypatch):
    item = seed(env, ws); d, _ = compiled(env, ws, item)
    env.w.review(d['bundle_id'], 1, d['work_hash'], True, '검토')
    stage = env.w.stage_publication(d['bundle_id'], 1, d['work_hash'], 0)
    receipt = env.w.verify_publication(stage['publication_id'])
    original = env.repo.activate_workspace
    def race(**kwargs):
        ws.apply(change_id='race-withdraw', expected=pin(ws, item.sid), operations=[
            {'op': 'RETRACT', 'target': item.sid, 'value': {'reason': '동시 철회'}}])
        return original(**kwargs)
    monkeypatch.setattr(env.repo, 'activate_workspace', race)
    with pytest.raises(ContractError, match='stale workspace'):
        env.w.activate_publication(stage['publication_id'], 0, receipt)
    assert env.repo.head(d['bundle_id'])['publication_id'] is None


def test_nfs_diagnostic_missing_never_copies_wire_to_work_store(env, monkeypatch):
    from semantic_runtime.ontology_work import wiki_transport
    from semantic_runtime import detailed_log_storage
    monkeypatch.setattr(detailed_log_storage, 'oracle_mode', lambda: True)
    monkeypatch.setattr(detailed_log_storage, 'capture', lambda *args, **kwargs: {'storage': detailed_log_storage.MARKER, 'capture_status': 'UNCONFIGURED', 'sha256': digest(args[0])})
    keys = []
    def once(store, *args):
        keys.append(store.put({'status': 'SENT', 'request': {'secret_original': '원시 전송'}}))
        return {'structured': True}, {'store_hash': keys[0]}
    monkeypatch.setattr(wiki_transport, 'generate_once', once)
    value, _ = wiki_transport.generate(env.w.store, 'reviewer', 'prompt', {}, {})
    stored = env.w.store.get(keys[0])
    assert value['structured'] and stored['detail']['capture_status'] == 'UNCONFIGURED'
    assert 'request' not in stored and '원시 전송' not in json.dumps(stored, ensure_ascii=False)
