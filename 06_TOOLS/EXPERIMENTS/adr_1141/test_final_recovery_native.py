"""Deterministic navigation contracts; no live-model quality or speed claims."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import pytest
from jsonschema import validate
from conftest import term_glossary
from semantic_runtime.legal_agent import connected_exploration as connected
from semantic_runtime.legal_agent import completion_execution as ce
from semantic_runtime.legal_agent import completion_v5, completion_v6, completion_v7, completion_v8
from semantic_runtime.legal_agent import output_contract as oc
from test_main50_request_repair import GAP
from test_unattempted_gap_finish import Journal


@pytest.mark.parametrize('mode', ['final_independent'])
def test_read_judgment_api_retains_decisions_and_reuses_request(tmp_path, term_glossary, mode, monkeypatch):
    from api_fixture_integrated import instrument,decode,to_wire
    instrument(monkeypatch)
    route = "connection"
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from semantic_runtime.unit_fulltext import build, UnitFulltextIndex
    from semantic_runtime.legal_agent.navigation_input import expand_cards
    from lawrag.core.legal_coordinate import find_coordinates
    from lawrag.pipeline.term_generation import build_generation
    from test_document_release import source
    from test_legal_agent_double_harness import wire
    from test_source_span_norm import proposal

    import os
    root=Path(os.environ['WORKFLOW_TEST_CODE_ROOT'])
    target_text = '이 확인 업무는 서면 승인 후 시행한다.'
    first = '제2조에 따른 적용 범위를 확인한다.' if route in ('connection','chain') else '업무 절차를 확인한다.'
    if route=='context':first=' '.join(f'제{i}조에 따른 기준을 확인한다.' for i in range(2,11))
    if route=='batch':first='제2조 및 제3조에 따른 적용 범위를 확인한다.'
    nested = route in ('narrow', 'whole')
    texts = (['제1조 업무 절차', '① 제2조에 따른 적용 범위를 확인한다.',
        '② 제3조에 따른 별도 업무를 확인한다.', '제2조 적용 범위: '+target_text,
        '제3조 별도 업무: 다른 업무의 절차.'] if nested else [
        '제1조 업무 절차: ' + first, '제2조 적용 범위: ' + ('제3조에 따른 승인 기준을 확인한다.' if route=='chain' else '참고 절차 2.' if route=='context' else target_text),
        *(['제3조 승인 기준: '+target_text] if route=='chain' else []),
        *(['제3조 별도 기준: 함께 확인할 원문.'] if route=='batch' else []),
        *([f'제{i}조 참고 사항: '+(target_text if i==10 else f'참고 절차 {i}.') for i in range(3,11)] if route=='context' else [])])
    raw = source(tmp_path / 'raw.sqlite', [('d', '원문검토검증규정', texts)])
    with sqlite3.connect(raw) as db:
        if nested:
            from lawrag.core.structure.viewer import annotate_coordinate_scopes
            nodes=[{'id':i,'parent':parent,'family':family,'surface':surface,'title':'', 'block':i,'span':[i,hi]}
                for i,parent,family,surface,hi in [(0,None,'kr_article','제1조',3),
                    (1,0,'circled','①',2),(2,0,'circled','②',3),
                    (3,None,'kr_article','제2조',4),(4,None,'kr_article','제3조',5)]]
            annotate_coordinate_scopes(nodes,'law')
            db.execute('DELETE FROM source_unit')
            for node in nodes:
                db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',('d',str(node['id']),
                    str(node['parent']) if node['parent'] is not None else None,json.dumps(node,ensure_ascii=False)))
        else:
            for did, uid, text in db.execute('SELECT document_id,unit_id,json FROM source_unit').fetchall():
                unit = json.loads(text)
                coordinate = find_coordinates(unit['surface'])[0].coordinate
                unit.update(legal_coordinate=coordinate.as_dict(), coordinate_scope='body',
                            coordinate_key='body:' + coordinate.canonical_surface())
                db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',
                           (json.dumps(unit, ensure_ascii=False), did, uid))
    build_generation(raw, term_glossary, tmp_path / 'built', serving=True)
    generation = tmp_path / 'built/generation'
    build(generation, generation / 'navigation', tmp_path / 'index', workers=1)
    index = UnitFulltextIndex(tmp_path / 'index', json.loads((generation / 'navigation/manifest.json').read_text()))
    question = '원문검토검증규정의 적용 기준은?'

    class Transport:
        binding = {'provider': 'fixture', 'model': 'synthetic-contract', 'adapter_version': 'fixture-v1',
                   'endpoint_identity': 'no-network', 'trust_zone': 'internal', 'max_input_bytes': 500000}

        def __init__(self):
            self.calls = []
            self.choices = []
            self.link_selected = False
            self.target_bound = False
            self.assess_repairs = 0
            self.located = False
            self.reference_calls = 0
            self.views = []
            self.omitted_navigation = False
            self.omitted_final = False

        def validate_model(self):
            return {'verified': True, 'synthetic': True}

        def send_once(self, *, body, ticket):
            view = decode(json.loads(body['messages'][1]['content'])['view'])
            phase = view.get('source_stage', view['phase'])
            self.calls.append(phase)
            self.views.append(deepcopy(view))
            def respond(value):
                if '-read-choice' in phase:
                    ctx=view['read_judgments']
                    originals={r['id']:r for r in ctx['current_originals']}
                    rows=[]
                    for jid in ctx['required']:
                        row=originals[jid]
                        target=any(target_text in s['text'] for s in view['sources'] if s['id'] in row['source_refs'])
                        rows.append({'judgment_id':jid,'operation':'SET','use':'CORE' if target else 'SUPPORT',
                            'finding':'승인이 필요하다.' if target else '적용 범위를 연결 조항에 위임한다.',
                            'reason':'질문한 적용 기준과 이 원문의 범위를 비교하였다.','issue_refs':['Q1'],
                            'basis_refs':row['source_refs'],'missing':[] if target else ['적용 범위의 세부 기준 확인'],
                            'conflicts_with':[]})
                    if mode in ('keep_delta','keep_exact'):
                        reviewed={r['judgment_id'] for r in rows}
                        for head in ctx['judgments']:
                            if head['id'] in reviewed or head['id'] not in originals:continue
                            keep={'judgment_id':head['id'],'operation':'KEEP','reason':'같은 원문으로 기존 판단 유지',
                                'basis_refs':originals[head['id']]['source_refs']}
                            if mode=='keep_exact':
                                keep.update(finding=head['finding'],use=head['use'],issue_refs=head['issue_refs'],missing=[],conflicts_with=[])
                            rows.append(keep)
                    updates=[]
                    if value['choice']=='FINISH':
                        assert ctx['judgments'] and ctx['needs'], 'prior judgment/need must survive omission'
                        if mode=='conflict':
                            rows[-1].update(operation='CONFLICT',use='DEFER',conflicts_with=[ctx['judgments'][0]['id']],
                                reason='처음 판단과 새 원문의 적용 범위가 충돌하여 보류한다.')
                        if mode not in ('open_need','conflict') and rows and any(target_text in s['text'] for s in view['sources']):
                            updates=[{'id':n['id'],'status':'RESOLVED','reason':'추가 원문에서 적용 기준을 확인하였다.',
                                'basis_refs':rows[-1]['basis_refs']} for n in ctx['needs']]
                    value['read_review']={'judgments':rows,'need_updates':updates,'conflict_updates':[]}
                    if value['choice'] not in ('FINISH','PENDING'):
                        for action in value['selections'] if value['choice']=='READ' else [value]:
                            action['judgment_refs']=[r['judgment_id'] for r in rows] or [r['id'] for r in ctx['judgments']]
                    if mode=='navigation_repair' and ctx['required'] and not self.omitted_navigation:
                        self.omitted_navigation=True
                        self.link_selected=False
                        rows[0]['basis_refs']=[]
                    if mode in ('independent_after_failure','independent_conflict_after_failure') and value['choice']=='READ' and view['sources'] and not any(target_text in s['text'] for s in view['sources']):
                        # The model explicitly asks for an independent direct original.
                        # Its separate revised judgment is invalid on both attempts.
                        if not rows:
                            head=ctx['judgments'][0]
                            rows.append({'judgment_id':head['id'],'operation':'SET','use':head['use'],
                                'finding':'채택되면 안 되는 수정','reason':'합성 오류 주입','basis_refs':[],
                                'issue_refs':head['issue_refs'],'missing':[],'conflicts_with':[]})
                        else:rows[0]['basis_refs']=[]
                        if mode=='independent_conflict_after_failure':
                            rows[0].update(operation='CONFLICT',use='SUPPORT',basis_refs=originals[rows[0]['judgment_id']]['source_refs'],conflicts_with=[])
                        for action in value['selections']:
                            action.update(relation='DIRECT',source_ref=None,judgment_refs=[])
                    retained={h['id'] for h in ctx['judgments']}
                    value['read_review']={'new_reviews':{},'revisions':{},'need_updates':updates,'conflict_updates':[]}
                    for row in rows:
                        field='revisions' if row['judgment_id'] in retained else 'new_reviews'
                        value['read_review'][field][row['judgment_id']]={k:v for k,v in row.items() if k!='judgment_id'}
                if phase.startswith('memory-assess'):
                    ctx=view['read_judgments']
                    assert len(ctx['judgments']) in (1,2), ctx
                    assert len(ctx['needs'])==1
                    if mode=='conflict':assert len(ctx['conflicts'])==1
                    review={'judgments':[],'needs':[],'conflicts':[]}
                    used=set(value['claims'][0]['evidence_refs']) if value['claims'] else set(ctx['judgments'][0]['available_evidence_refs'])
                    for head in ctx['judgments']:
                        refs=list(used & set(head['available_evidence_refs']))
                        review['judgments'].append({'id':head['id'],'disposition':'USE' if refs else 'NOT_USED',
                            'claim_refs':[value['claims'][0]['claim_id'] if value['claims'] else 'C404'] if refs else [],'basis_refs':refs,
                            'reason':'현재 원문과 적용 범위를 대조하여 최종 사용 여부를 판단하였다.'})
                    for field in ('needs','conflicts'):
                        review[field]=[{'id':r['id'],'status':'OPEN' if mode in ('open_need','conflict') else 'RESOLVED',
                            'reason':'추가 조건을 아직 확인하지 못했다.' if mode in ('open_need','conflict') else '추가 원문으로 적용 범위를 확인했다.',
                            'material':True,'basis_refs':list(used)} for r in ctx[field]]
                    value['read_judgment_review']=review
                    if mode=='final_failed' or mode=='final_repair' and not self.omitted_final:
                        self.omitted_final=True
                        value['read_judgment_review']['needs']=[]
                return wire(to_wire(value))
            if phase == 'request-entry':
                from test_unified_scope_semantic_authority import wire as entry
                value = entry(question)
                value = json.loads(json.dumps(value,ensure_ascii=False).replace('모의승인규정','원문검토검증규정'))
                value['intent']['issues'][0]['request_quote'] = question
                value['command']['queries'] = ['원문검토검증규정 제1조']
                value['search']['mode'] = 'STRUCTURE'
                return respond(value)
            if '-read-choice' in phase:
                read_target = any(target_text in s['text'] for s in view['sources'])
                gaps = view.get('assessment_gaps', [])
                if view['sources'] and not read_target and route not in ('batch','missing','failure','chain'):
                    wanted='제3조' if route=='chain' and any('제3조에 따른 승인 기준' in s['text'] for s in view['sources']) else '제10조' if route=='context' else '제2조'
                    cards=view['references']['dependency_cards']
                    candidates=[c for c in cards if c.get('read_action') and wanted in c['target']['heading']]
                    if candidates and not gaps:
                        self.choices.append('FINISH')
                        return respond({'choice':'FINISH','basis_refs':[s['id'] for s in view['sources']], 'issue_refs':['Q1'],'evidence_sufficient':False,'reason':'최종 평가에서 누락 원문을 특정한다.'})
                    if candidates:
                        if route=='context':assert len(cards)==9
                        if nested:
                            headings={c['target']['heading'].split()[0] for c in cards}
                            assert headings==({'제2조'} if route=='narrow' else {'제2조','제3조'})
                        c=candidates[0];self.choices.append('READ_LINK')
                        return respond({'choice':'READ','selections':[{'target':c['read_action'],'issue_id':'Q1',
                            'missing_need':'필요한 연결 원문 확인','relation':'DEPENDENCY','source_ref':view['sources'][0]['id']}]})
                if route=='batch' and self.link_selected and not read_target:
                    cards=[c for c in view['references']['dependency_cards'] if c.get('read_action')]
                    assert len(cards)==2
                    self.choices.append('READ_BATCH')
                    return respond({'choice':'READ','selections':[{'target':c['read_action'],'issue_id':'Q1',
                        'missing_need':'같은 선택 범위의 두 연결 원문 확인','relation':'DEPENDENCY',
                        'source_ref':view['sources'][0]['id']} for c in cards]})
                if view['sources'] and not read_target and (not self.link_selected or route=='chain'):
                    anchor = '제2조' if route=='chain' and self.link_selected else '제1조'
                    options=[o for o in view['tool_options'] if o['choice']=='FOLLOW_CONNECTION' and anchor in o['label']]
                    if not self.link_selected:
                        assert not view['references']['dependency_cards']
                        assert all(c['connection_preview']['status']=='NOT_SELECTED' for c in view['connection_scope_choices'])
                    if nested:
                        uid='1' if route=='narrow' else '0'
                        option=next(o for o in options if o['selected_scope']['structural_selection']['unit_id']==uid)
                        assert any('별도 업무' in s['text'] for s in view['sources'])
                    else:
                        option=options[0]
                    self.link_selected=True
                    self.choices.append('FOLLOW_CONNECTION')
                    return respond({'choice':'FOLLOW_CONNECTION','target':option['target'],'issue_id':'Q1',
                        'missing_need':'선택한 범위의 연결 확인','relation':'DEPENDENCY',
                        'source_ref':next(s['id'] for s in view['sources'] if anchor in s['heading'])})
                if view['sources'] and not read_target and route in ('missing', 'failure') and self.link_selected and not self.located:
                    option = next(o for o in view['tool_options'] if o['choice'] == 'LOCATE')
                    if route=='failure':
                        assert view['references']['absence_proven'] is False
                        assert any(c['connection_preview']['status']=='FAILED' for c in view['connection_scope_choices'])
                        assert not any(o['choice']=='FOLLOW_CONNECTION' and '제1조' in o['label'] for o in view['tool_options'])
                    else:
                        assert view['references']['absence_proven'] is False
                    self.located = True
                    self.choices.append('LOCATE')
                    return respond({'choice': 'LOCATE', 'target': option['target'], 'issue_id': 'Q1',
                        'missing_need': '알려진 적용 범위 조문 조회', 'relation': 'DIRECT', 'source_ref': None,
                        'structure_filter': {'coordinate': '제2조', 'title': '', 'coordinate_scope': 'body'}})
                if not view['sources'] or not read_target and self.located:
                    wanted = '제1조' if not view['sources'] else '제2조'
                    candidate = next(c for c in view['read_candidates'] if c.get('coordinate')==wanted)
                    if gaps:
                        self.target_bound = any(candidate['target'] in g['read_actions'] for g in view['gap_targets'])
                        assert self.target_bound
                    self.choices.append('READ')
                    return respond({'choice': 'READ', 'selections': [{'target': candidate['target'], 'issue_id': 'Q1',
                        'missing_need': '모의 적용 범위 원문 확인', 'relation': 'DIRECT', 'source_ref': None}]})
                self.choices.append('FINISH')
                if route=='batch':
                    assert any('함께 확인할 원문' in s['text'] for s in view['sources'])
                return respond({'choice': 'FINISH', 'basis_refs': [s['id'] for s in view['sources']],
                    'issue_refs': ['Q1'], 'evidence_sufficient': read_target, 'reason': '확보한 원문으로 판단'})
            if phase.startswith('source-reference-law-'):raise AssertionError('Nested reference model must not run')
            if phase.startswith('memory-assess'):
                if mode=='final_truncated':
                    result=wire('{"claims":[')
                    result['body_json']['choices'][0]['finish_reason']='length'
                    return result
                found = next((o for o in view['evidence_options'] if target_text in o['text']), None)
                if found:
                    result = proposal(target_text, 'OBLIGATION', [found['id']], found['id'])
                    result.pop('disposition')
                    return respond(result)
                gap = {**GAP, 'reason': '원문검토검증규정 제2조 적용 범위 원문이 필요하다.',
                       'missing_target': next(o['target'] for o in view['locator_options'] if '제2조' in o['target'])}
                if route == 'gap_repair' and not phase.endswith('-repair'):
                    gap.pop('missing_target')
                elif route == 'gap_repair':
                    self.assess_repairs += 1
                return respond({'claims': [], 'issue_assessments': [
                    {'issue_id': 'Q1', 'status': 'INSUFFICIENT', 'reason': '적용 범위 원문 필요'}], 'gaps': [gap]})
            raise AssertionError('Unexpected phase: ' + phase)

    if route=='failure':
        from semantic_runtime.legal_agent import unit_relations
        def fail(*a,**kw):raise TimeoutError('synthetic connection store timeout')
        monkeypatch.setattr(unit_relations,'catalog',fail)
    transport = Transport()
    profile = json.loads((root / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    assert profile['candidate_navigation']['small_connection_context'] is False
    profile['candidate_navigation'].update(stable_navigation_references=True,new_read_reviews=True,independent_read_recovery=True,minimal_input=True,read_candidate_page_size=20,selected_connection_scope=True,small_connection_context=True,answer_first=False,answer_progress_control=False,read_judgment=True)
    profile.update(model_binding=transport.binding, answer_presentation='structured')
    app = create_app(tmp_path, generation, contracts_root=root, provider=object(),
        implementation='legal-agent-unified-v6', legal_agent_profile=profile, legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id': 'synthetic', 'team_id': 'risk_team', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = index
    with TestClient(app) as api:
        request = {'question': question, 'session_id': route, 'request_id': 'r1'}
        response = api.post('/v1/rag/ask', json=request)
        if mode=='final_failed':
            assert response.status_code==422
            assert len([p for p in transport.calls if p.startswith('memory-assess')])==2
            from semantic_runtime.legal_agent import read_judgment as rj
            journal=next(tmp_path.glob('90_RUNTIME/semantic/legal-agent/runs/*/*/journal.sqlite'))
            with sqlite3.connect(journal) as db:
                events=[json.loads(v) for v, in db.execute("SELECT payload_json FROM event WHERE kind='READ_JUDGMENT_RECORDED'")]
                assert len(events)==4 and sum(len(e['changes']) for e in events)==2
            app.state.pipeline.store.close()
            return
        assert response.status_code == 200, response.text
        result = response.json()
        assert target_text in result['answer']['text']
        assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage'] == ('INSUFFICIENT' if mode=='final_truncated' else 'PARTIAL' if mode in ('open_need','conflict') else 'COVERED')
        if mode in ('open_need','conflict'):assert '추가 조건을 아직 확인하지 못했다' in result['answer']['text']
        stages={r['stage']:r for r in result['assembly']['term_agent']['judgment_view']['stages']}
        assert stages['SELECT']['read_judgments']
        assert len([r for r in stages['SELECT']['data'] if r.get('judgment_id')])==2
        assert any('이유:' in r for r in stages['SELECT']['decisions'])
        if mode!='final_truncated':assert stages['ASSESS']['decisions']
        receipt=stages['ASSESS']['read_judgment_review']
        assert len(receipt['prior_judgments'])==2 and len(receipt['prior_needs'])==1
        assert receipt['status']==('INCOMPLETE' if mode=='final_truncated' else 'REVIEWED')
        from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
        from semantic_runtime.legal_agent.unified_publication import validate_saved
        journal=next(tmp_path.glob('90_RUNTIME/semantic/legal-agent/runs/*/'+result['run_id']+'/journal.sqlite'))
        repo=UnifiedRepository(journal)
        try:validate_saved(repo,result)
        finally:repo.close()
        if mode in ('independent_after_failure','independent_conflict_after_failure'):
            with sqlite3.connect(journal) as db:
                recoveries=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='INDEPENDENT_READ_RECOVERY'")]
                assert len(recoveries)==1 and recoveries[0]['judgments_adopted'] is False
                heads=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='READ_JUDGMENT_RECORDED'")]
                assert '채택되면 안 되는 수정' not in json.dumps(heads,ensure_ascii=False)
        with sqlite3.connect(journal) as db:
            recovered=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='FINAL_REVIEW_INDEPENDENT_RESEARCH'")]
            assert len(recovered)==1 and recovered[0]['claims_adopted'] is False and recovered[0]['review_adopted'] is False
            rejected=list(db.execute("SELECT payload_json FROM event WHERE kind='COMPLETION_ASSESSMENT_REJECTED'"))
            assert len(rejected)==2
            assert not db.execute("SELECT 1 FROM event WHERE kind='ASSESSMENT_VALIDATED' AND payload_json LIKE '%C404%'").fetchone()
        calls = len(transport.calls)
        again = api.post('/v1/rag/ask', json=request)
        assert again.status_code == 200 and again.json()['answer'] == result['answer']
        assert len(transport.calls) == calls
    assert transport.reference_calls == 0
    expected=['READ','FOLLOW_CONNECTION','FINISH','READ_LINK','FINISH']
    if mode=='navigation_repair':expected.insert(2,'FOLLOW_CONNECTION')
    if mode in ('independent_after_failure','independent_conflict_after_failure'):expected.insert(3,'READ_LINK')
    # A rejected proposal may select a different tool in the corrected call;
    # neither rejected action nor its opinion is committed.
    assert transport.choices == expected
    assert len([p for p in transport.calls if p.startswith('memory-assess')]) == 3
    assert len(transport.calls) == 9
    assert not any('judgment' in p for p in transport.calls), 'review must share existing calls'
    app.state.pipeline.store.close()
