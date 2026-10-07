"""Synthetic source/journal/guide contracts, not semantic effectiveness results."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

spec = importlib.util.spec_from_file_location('adr0559_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture(scope='module')
def setup(tmp_path_factory):
    root = tmp_path_factory.mktemp('experience-contracts')
    module = runner.load_candidate()
    generation = runner.build_fixture(root/'fixture')
    episodes, binding, catalogue = runner.seed_histories(module, generation, root)
    def grouping(system, data, schema):
        groups = {}
        for e in data['episodes']:
            groups.setdefault(e['objective'], []).append(e['id'])
        return {'groups': [{'label': objective, 'objective': objective,
            'episode_ids': ids, 'expected_information': objective+'에 필요한 정의·범위·절차 원문',
            'exit_condition': '목적이 다르거나 현재 원문에서 적용 대상이 제외되면 이탈'}
            for objective, ids in groups.items()]}
    bundle = module.consolidate(episodes, grouping)
    module.validate_bundle(bundle, binding, catalogue)
    path = root/'concepts.sqlite'
    receipt = module.publish(bundle, path)
    return root, module, generation, episodes, binding, catalogue, bundle, path, receipt


def test_completed_v5_history_extracts_only_cited_source_transitions(setup):
    _, _, _, episodes, _, _, _, _, _ = setup
    assert len(episodes) == 10
    for episode in episodes:
        assert episode['status'] == 'PROPOSED' and episode['legal_correctness'] == 'UNVERIFIED'
        assert episode['journal_sha256'] and episode['steps'] and episode['evidence_ids']
        assert all(step['anchor']['source_id'] != step['target']['source_id'] for step in episode['steps'])


def test_exact_question_duplicates_do_not_inflate_concept_support(setup):
    _, _, _, episodes, _, _, bundle, _, _ = setup
    by_history = {e['fixture_history_id']: e for e in episodes}
    assert by_history['history-01']['support_key'] == by_history['history-03']['support_key']
    concept = next(c for c in bundle['concepts'] if by_history['history-01']['id'] in c['support_episode_ids'])
    assert concept['occurrence_count'] == 3 and concept['support_count'] == 2
    assert len(bundle['concepts']) == 4


def test_actual_wire_messages_match_native_journal_after_schema_prompt_repair(setup, tmp_path):
    import httpx
    from lawrag.research.experiment_client import ExperimentClient
    _, _, generation, _, _, _, _, _, _ = setup
    output = {'status': 'CLARIFY', 'next_source_ids': [], 'source_ids': [],
        'used_concept_ids': [], 'deviated_concept_ids': [], 'reason': '모의 목적 확인',
        'missing_information': '조사 목적', 'answer': ''}
    captured = []
    def transport(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={'model': 'google/gemma-4-31b-it',
            'provider': 'Parasail', 'choices': [{'finish_reason': 'stop',
                'message': {'content': json.dumps(output, ensure_ascii=False)}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
    client = ExperimentClient(runner.ROOT, tmp_path/'calls', schema_in_prompt=True,
        max_output_tokens=1024, transport=httpx.MockTransport(transport))
    with runner.session(tmp_path/'session', generation, '목적 미정', live=True) as s:
        runner.read_unit(s, '2', 'anchor')
        view = s.view('investigate')
        data = {'view': view, 'original_question': '목적 미정'}
        assert runner.invoke_recorded(s, client, runner.NAV_SYSTEM, data,
            runner.nav_schema([], [], [e["source_id"] for e in s.work.evidence()]), 'wire-contract', view) == output
        request = json.loads(s.work.db.execute('SELECT request_json FROM model_attempt').fetchone()[0])
        assert request['messages'] == captured[0]['messages']
        assert json.loads(request['messages'][1]['content'])['view'] == view


def test_native_evidence_handle_cannot_be_accepted_as_source_citation(setup, tmp_path):
    import httpx
    from lawrag.research.experiment_client import ExperimentClient, ExperimentCallError
    _, _, generation, _, _, _, _, _, _ = setup
    captured = []
    def transport(request):
        captured.append(json.loads(request.content))
        data = json.loads(captured[-1]['messages'][1]['content'])
        wrong = {'status': 'ANSWER', 'next_source_ids': [],
            'source_ids': [data['view']['exact_evidence'][0]['evidence']],
            'used_concept_ids': [], 'deviated_concept_ids': [],
            'reason': '인용 식별자 혼동 재현', 'missing_information': '', 'answer': '모의 답변'}
        return httpx.Response(200, json={'model': 'google/gemma-4-31b-it',
            'provider': 'Parasail', 'choices': [{'finish_reason': 'stop',
                'message': {'content': json.dumps(wrong, ensure_ascii=False)}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
    client = ExperimentClient(runner.ROOT, tmp_path/'calls', schema_in_prompt=True,
        transport=httpx.MockTransport(transport))
    with runner.session(tmp_path/'session', generation, '식별자 검사', live=True) as s:
        runner.read_unit(s, '2', 'anchor')
        view = s.view('investigate')
        read_ids = sorted({e['source_id'] for e in s.work.evidence()})
        schema = runner.nav_schema([], [], read_ids)
        with pytest.raises(ExperimentCallError):
            runner.invoke_recorded(s, client, runner.NAV_SYSTEM, {'view': view},
                schema, 'invalid-citation-contract', view)
        assert s.work.db.execute('SELECT status FROM model_attempt').fetchone()[0] == 'FAILED'
        assert len(captured) == 1
        assert {e['source_id'] for e in s.work.evidence()} == set(read_ids)


def test_prospective_runner_executes_current_read_and_citation_contract(setup, tmp_path):
    import httpx
    from lawrag.research.experiment_client import ExperimentClient
    _, module, generation, _, _, _, _, bundle_path, receipt = setup
    requests = []
    def transport(request):
        wire = json.loads(request.content)
        data = json.loads(wire['messages'][1]['content'])
        requests.append(data)
        if len(requests) == 1:
            selected = next(n['source_id'] for n in data['next_sources'] if n['coordinate']=='제1조')
            answer = {'status': 'CONTINUE', 'next_source_ids': [selected], 'source_ids': [], 'answer': ''}
        else:
            selected = next(e['source_id'] for e in data['view']['exact_evidence'] if '국적이 모의국' in e['text'])
            answer = {'status': 'ANSWER', 'next_source_ids': [], 'source_ids': [selected], 'answer': '모의 원문 정의 확인'}
        answer.update(used_concept_ids=[], deviated_concept_ids=[], reason='현재 원문 정의를 확인한다', missing_information='')
        return httpx.Response(200, json={'model': 'google/gemma-4-31b-it', 'provider': 'Parasail',
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(answer, ensure_ascii=False)}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
    client = ExperimentClient(runner.ROOT, tmp_path/'calls', schema_in_prompt=True,
        transport=httpx.MockTransport(transport))
    result = runner.run_case(module, generation, bundle_path, receipt['sha256'],
        {'id': 'definition-contract', 'question': '외국인 정의 확인', 'mode': 'live'},
        'baseline', client, tmp_path/'case')
    assert result['status'] == 'ANSWER' and result['read_units'] == ['1', '2']
    assert len(requests) == 2
    assert result['trace'][-1]['decision']['source_ids'][0] in requests[-1]['citable_source_ids']


def test_incomplete_journal_and_uncited_reads_do_not_become_experiences(setup, tmp_path):
    _, m, generation, _, _, _, _, _, _ = setup
    with runner.session(tmp_path, generation, '미완료 조사') as s:
        runner.read_unit(s, '2', 'anchor')
        runner.read_unit(s, '1', 'read')
        binding, catalogue = m.binding_from(s.sources), m.source_catalogue(s.sources)
        assert m.collect_journal(s.work.path, catalogue, binding) == []
        s.work.db.execute("UPDATE run SET status='COMPLETED'")
        assert m.collect_journal(s.work.path, catalogue, binding) == []


def test_original_span_tamper_rejected(setup, tmp_path):
    root, m, _, _, binding, catalogue, _, _, _ = setup
    original = next((root/'histories/history-01').rglob('journal.sqlite'))
    copied = tmp_path/'bad.sqlite'
    with sqlite3.connect(original) as src, sqlite3.connect(copied) as dest:
        src.backup(dest)
    bad = deepcopy(catalogue)
    # Change an actually cited source, rather than an unrelated catalogue node.
    with sqlite3.connect(copied) as db:
        sid = db.execute('SELECT source_id FROM evidence_unit ORDER BY evidence_id LIMIT 1').fetchone()[0]
    node = bad[sid]
    block = next(iter(node['blocks'].values()))
    block['text'] += '원문 훼손'
    with pytest.raises(ValueError, match='witness'):
        m.collect_journal(copied, bad, binding)


@pytest.mark.parametrize('change', ['binding', 'source', 'bundle_hash'])
def test_bundle_binding_and_source_witness_guards(setup, change):
    _, m, _, _, binding, catalogue, bundle, _, _ = setup
    bad = deepcopy(bundle)
    if change == 'binding':
        other = {**binding, 'generation_id': 'changed'}
        with pytest.raises(ValueError, match='binding|generation'):
            m.validate_bundle(bad, other, catalogue)
    elif change == 'source':
        target = deepcopy(catalogue)
        for value in target.values():
            value['text_sha256'] = '0'*64
        with pytest.raises(ValueError, match='witness'):
            m.validate_bundle(bad, binding, target)
    else:
        bad['concepts'][0]['objective'] = '변조한 목적'
        with pytest.raises(ValueError, match='hash'):
            m.validate_bundle(bad, binding, catalogue)


def test_model_cannot_drop_or_duplicate_episodes(setup):
    _, m, _, episodes, _, _, _, _, _ = setup
    def incomplete(system, data, schema):
        return {'groups': [{'label': '목적 일부', 'objective': '목적 일부만 배정',
            'episode_ids': [data['episodes'][0]['id']], 'expected_information': '정의 확인하기',
            'exit_condition': '목적이 다른 경우'}]}
    with pytest.raises(ValueError, match='every episode'):
        m.consolidate(episodes, incomplete)


def test_snapshot_is_immutable(setup):
    _, m, _, _, _, _, bundle, path, _ = setup
    with pytest.raises(FileExistsError):
        m.publish(bundle, path)


def test_guidance_only_after_observation_and_new_handles(setup, tmp_path):
    _, m, generation, _, _, _, _, path, receipt = setup
    with runner.session(tmp_path, generation, '거래의 적용 대상인가?') as s:
        guide = m.ExperienceGuide(path, receipt['sha256'], s.sources)
        try:
            assert guide.lookup()['items'] == []
            runner.read_unit(s, '2', 'anchor')
            offered = guide.lookup()
            assert len(offered['items']) == 4
            for item in offered['items']:
                for entry in item['next_actions']:
                    s.sources.validate_action(entry['action'])
                    s.sources.resolve(entry['action']['args']['target'], 'P')
            runner.read_unit(s, '1', 'fresh')
            next_offer = guide.lookup()
            definition_sid = runner.node_for_unit(s, '1')[0]
            assert all(n['source_id'] != definition_sid for i in next_offer['items'] for n in i['next_actions'])
        finally:
            guide.close()


def test_deviation_suppresses_same_advice_and_checks_offered_ids(setup, tmp_path):
    _, m, generation, _, _, _, _, path, receipt = setup
    with runner.session(tmp_path, generation, '의결권 없는 거래는?') as s:
        runner.read_unit(s, '2', 'anchor')
        guide = m.ExperienceGuide(path, receipt['sha256'], s.sources)
        try:
            offered = guide.lookup()
            ident = offered['items'][0]['id']
            with pytest.raises(ValueError, match='not offered'):
                guide.feedback(offered, used=['forged'])
            with pytest.raises(ValueError, match='concrete'):
                guide.feedback(offered, deviated=[ident], reason='')
            guide.feedback(offered, deviated=[ident], reason='현재 원문에서 거래 대상이 제외되어 이탈')
            assert ident not in {i['id'] for i in guide.lookup()['items']}
        finally:
            guide.close()


@pytest.mark.parametrize('condition', ['generation', 'scope', 'file'])
def test_invalid_memory_falls_back_without_guidance_leak(setup, tmp_path, condition):
    _, m, generation, _, _, _, _, path, receipt = setup
    with runner.session(tmp_path, generation, '범위 확인') as s:
        runner.read_unit(s, '2', 'anchor')
        if condition == 'generation':
            s.sources.context.query['generation_id'] = 'changed'
        elif condition == 'scope':
            s.sources.scope = []
        expected_sha = '0'*64 if condition == 'file' else receipt['sha256']
        guide = m.ExperienceGuide(path, expected_sha, s.sources)
        try:
            assert guide.lookup() == {'status': 'INVALID_BINDING_FALLBACK', 'items': [], 'advisory_only': True}
        finally:
            guide.close()


def test_guided_view_retains_exact_original_delivery_ledger(setup, tmp_path):
    _, m, generation, _, _, _, _, path, receipt = setup
    with runner.session(tmp_path, generation, '외국인의 의미 확인') as s:
        runner.read_unit(s, '2', 'anchor')
        guide = m.ExperienceGuide(path, receipt['sha256'], s.sources)
        try:
            view, offered = m.guided_view(s, guide)
            assert view['experience_guidance'] == offered
            assert view['original_question'] == s.context.request['question']
            saved = json.loads(s.work.db.execute('SELECT body_json FROM model_view WHERE view_id=?',
                (view['view_id'],)).fetchone()[0])
            assert saved == view
            assert {e['evidence'] for e in view['exact_evidence']} == {
                r[0] for r in s.work.db.execute('SELECT evidence_id FROM presentation WHERE view_id=?', (view['view_id'],))}
        finally:
            guide.close()
