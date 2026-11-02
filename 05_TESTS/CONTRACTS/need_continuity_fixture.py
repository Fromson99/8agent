"""Synthetic native API fixture adapted from ADR1202; old fixture stays immutable.

The model explicitly selects both targets; no reference auto-expansion is used.
"""
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


def run_api(tmp_path, term_glossary, mode, monkeypatch, coverage_fault=None, *, exercise=None):
    from api_fixture_integrated import instrument,decode,to_wire
    instrument(monkeypatch)
    route = "connection"
    mode='goal_control'
    rejected_need = coverage_fault in ('rejected_need', 'rejected_need_first', 'rejected_need_twice')
    rejected_text = '거절된 조사 응답이 선언한 별도 예외 기준 확인'
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
    first = '제2조 또는 제3조에 따른 적용 범위를 확인한다.' if route in ('connection','chain') else '업무 절차를 확인한다.'
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
    texts.append('제3조 별도 기준: 제외 여부를 확인할 별도 근거.')
    if mode=='page_handoff':
        texts[0]='제1조 업무 절차: 제2조 및 제3조 및 제4조에 따른 적용 범위를 확인한다.'
        texts.extend(['제3조 보충 절차: 참고 검토 자료.','제4조 추가 절차: 다른 참고 검토 자료.'])
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
            phase = view.get('source_stage') or view['phase']
            self.calls.append(phase)
            self.views.append(deepcopy(view))
            if phase=='source-law-navigation-supervisor-read-choice':
                if coverage_fault=='handoff' and view['proposed_action']['choice']=='FINISH':
                    return wire({'directive':'STOP_UNRESOLVED','reason':'조사 종료와 충분성을 구분',
                        'remaining_scope':'위임 기준 원문', 'source_targets':[],'source_goal_exclusions':[]})
                if mode=='route_recovery' and view['proposed_action']['choice']=='FINISH' and not any(target_text in r['text'] for r in view['sources']):
                    candidate=next(c for c in view['read_candidates'] if c.get('coordinate')=='제2조')
                    action={'choice':'READ','selections':[{'target':candidate['target'],'issue_id':'Q1',
                        'missing_need':'위임한 적용 기준의 원문이 아직 필요하다','relation':'DEPENDENCY',
                        'source_ref':view['sources'][0]['id'],
                        'judgment_refs':[r['id'] for r in view['read_judgments']['judgments']]}]}
                    return wire(to_wire({'directive':'CONTINUE_TARGETED','reason':'잘못된 유지 지시와 유효한 추가 읽기',
                        'remaining_scope':'제2조 적용 기준 원문 미확보','action':action}))
                if mode=='page_handoff' and self.calls.count(phase)==2:
                    moves=view['read_candidate_page']['actions'];assert moves
                    return wire({'directive':'REDIRECT','reason':'다른 후보 페이지 확인','remaining_scope':'미확인 후보','action':{'choice':moves[0]}})
                action={k:v for k,v in view['proposed_action'].items() if k!='answer_progress'}
                extra={'source_targets':[],'source_goal_exclusions':[]} if mode=='goal_control' else {}
                return wire({**extra,'directive':'CONTINUE_TARGETED','reason':'필수 위임 원문 읽기 또는 확인 근거의 최종 판단','remaining_scope':'현재 질문의 위임 기준 검토','action':action})
            def respond(value):
                if mode=='goal_control' and '-read-choice' in phase:
                    value.update(source_targets=[],source_goal_exclusions=[])
                    if view['sources'] and not any(target_text in x['text'] for x in view['sources']) and not view.get('source_goal_context',{}).get('goals'):
                        opt=view['source_target_options'][0]
                        value['source_targets']=[{'document_ref':opt['document_ref'],'coordinate':coordinate,'coordinate_scope':'body','issue_id':'Q1','reason':'적용 기준 원문 필요'} for coordinate in ('제2조','제3조')]
                if mode=='page_handoff' and value.get('choice')=='READ':
                    visible={x['target'] for x in view['read_candidates']}
                    if any(x['target'] not in visible for x in value['selections']):
                        return wire({'choice':view['read_candidate_page']['actions'][0]})
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
                        if mode not in ('open_need','conflict') and (mode!='route_recovery' or any(target_text in r['text'] for r in view['sources'])):
                            updates=[{'id':n['id'],'status':'RESOLVED','reason':'추가 원문에서 적용 기준을 확인하였다.',
                                'basis_refs':rows[-1]['basis_refs'] if rows else [s['id'] for s in view['sources'] if target_text in s['text']]} for n in ctx['needs']]
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
                    assert len(ctx['judgments'])==3, ctx
                    if rejected_need:
                        assert sum(h['use']=='DEFER' for h in ctx['judgments'])==2
                    assert any(n.get('origin')=='ANSWER_PROGRESS' for n in ctx['needs'])
                    if mode=='conflict':assert len(ctx['conflicts'])==1
                    review={'judgments':[],'needs':[],'conflicts':[]}
                    used=set(value['claims'][0]['evidence_refs'])
                    for head in ctx['judgments']:
                        refs=list(used & set(head['available_evidence_refs']))
                        review['judgments'].append({'id':head['id'],'disposition':'USE' if refs else 'NOT_USED',
                            'claim_refs':[value['claims'][0]['claim_id']] if refs else [],'basis_refs':refs,
                            'reason':'현재 원문과 적용 범위를 대조하여 최종 사용 여부를 판단하였다.'})
                    from need_continuity_fixture import change_review
                    for row,head in zip(review['judgments'],ctx['judgments']):
                        if row['disposition']=='NOT_USED' and head.get('change_from'):
                            row['change_review']=change_review(head)
                    for field in ('needs','conflicts'):
                        review[field]=[{'id':r['id'],'status':'OPEN' if mode in ('open_need','conflict') else 'RESOLVED',
                            'reason':'추가 조건을 아직 확인하지 못했다.' if mode in ('open_need','conflict') else '추가 원문으로 적용 범위를 확인했다.',
                            'material':True,'basis_refs':list(used)} for r in ctx[field]]
                    assert ctx['need_continuity']['latest_goals'][0]['material_need']=='위임 기준 원문'
                    targets={t['id']:t for t in ctx['need_continuity']['targets']}
                    for row,need in zip(review['needs'],ctx['needs']):
                        row.update(claim_refs=[value['claims'][0]['claim_id']],gap_indices=[],target_refs=need.get('target_refs') or [],scope_quote='')
                        for target_id in row['target_refs']:
                            target=targets[target_id]
                            refs=target['available_evidence_refs']
                            if not (set(refs)&used):
                                row.update(status='NOT_NEEDED',claim_refs=[],basis_refs=refs,reason='원문에서 별도 기준으로 확인하여 이번 적용 기준에서는 제외')
                    if coverage_fault=='open' or rejected_need:
                        pending_id=next(n['id'] for n in ctx['needs'] if n.get('origin')=='ANSWER_PROGRESS' and (not rejected_need or n['text']==rejected_text))
                        pending=next(r for r in review['needs'] if r['id']==pending_id)
                        pending.update(status='OPEN',claim_refs=[],basis_refs=[],gap_indices=[1],reason=rejected_text if rejected_need else '위임 기준의 추가 확인이 아직 필요하다.')
                        value['issue_assessments'][0]['status']='PARTIAL'
                        value['gaps']=[{**GAP,'kind':'MISSING_SOURCE','material_id':None,'material':True,'missing_target':'','previous_gap_key':None,'reason':pending['reason'],'suggested_action':'RESEARCH'}]
                    if coverage_fault in ('need_first','need_twice') and (coverage_fault=='need_twice' or not phase.endswith('-repair')):
                        review['needs']=[]
                    if rejected_need and (coverage_fault=='rejected_need_twice' or coverage_fault=='rejected_need_first' and not phase.endswith('-repair')):
                        review['needs']=[r for r in review['needs'] if r['id']!=pending_id]
                    from scope_review_fixture import scope_rows
                    scope_rows(value,ctx,review)
                    if coverage_fault in ('scope_first','scope_twice') and (coverage_fault=='scope_twice' or not phase.endswith('-repair')):
                        review['scope_reviews']=[]
                    value['read_judgment_review']=review
                    if mode=='final_failed' or mode=='final_repair' and not self.omitted_final:
                        self.omitted_final=True
                        value['read_judgment_review']['needs']=[]
                if '-read-choice' in phase and mode!='off':
                    prior=bool(view.get('answer_progress_context',{}).get('current_goals'))
                    terminal=value['choice']=='FINISH'
                    value['answer_progress']={'goals':[{'issue_id':i['id'],'status':'NEEDS_SOURCE','answer_so_far':'확인한 기준' if view['sources'] else '', 'basis_refs':[s['id'] for s in view['sources']][:4], 'material_need':'위임 기준 원문', 'next_answer_change':'기준 확인', 'previous_effect':'NO_CHANGE' if prior else 'INITIAL'} for i in view['issues']]}
                    if rejected_need and value['choice']=='FOLLOW_CONNECTION' and any(target_text in s['text'] for s in view['sources']):
                        unreviewed=next(iter(value['read_review']['new_reviews']))
                        del value['read_review']['new_reviews'][unreviewed]
                        value['judgment_refs']=[unreviewed]
                        value['answer_progress']['goals'][0]['material_need']=rejected_text
                if phase.startswith('memory-assess'):
                    from test_native import coverage_rows
                    assert 'requirement_context' in view
                    value['requirement_review']=coverage_rows(value,view['requirement_context'])
                    if coverage_fault=='gap_link':
                        value['issue_assessments'][0]['status']='PARTIAL'
                        value['gaps']=[{**GAP,'kind':'MISSING_SOURCE','material_id':None,'material':True,'missing_target':'','previous_gap_key':None,'reason':'별도 수량 기준을 확인할 원문이 필요하다.','suggested_action':'RESEARCH'}]
                    if coverage_fault=='twice' or coverage_fault=='first' and not phase.endswith('-repair'):
                        value['requirement_review']=[]
                if phase.startswith('memory-assess') and coverage_fault in ('change_first','change_twice') and (coverage_fault=='change_twice' or not phase.endswith('-repair')):
                    for row in value['read_judgment_review']['judgments']:row.pop('change_review',None)
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
                if mode=='goal_control' and read_target and view.get('connection_review',{}).get('required_before_finish'):
                    opt=next(o for o in view['tool_options'] if o['choice']=='FOLLOW_CONNECTION')
                    return respond({'choice':'FOLLOW_CONNECTION','target':opt['target'],'issue_id':'Q1','missing_need':'실제 실행되지 않은 연결 범위 확인','relation':'DEPENDENCY','source_ref':view['sources'][0]['id']})
                if mode=='goal_control' and view['sources'] and not read_target:
                    candidate=next((c for c in view.get('read_candidates',[]) if c.get('coordinate')=='제2조'),None)
                    if candidate:
                        return respond({'choice':'READ','selections':[{'target':candidate['target'],'issue_id':'Q1','missing_need':'필요 원문','relation':'DIRECT','source_ref':None}]})
                if view['sources'] and not read_target and route not in ('batch','missing','failure','chain'):
                    wanted='제3조' if route=='chain' and any('제3조에 따른 승인 기준' in s['text'] for s in view['sources']) else '제10조' if route=='context' else '제2조'
                    cards=view['references']['dependency_cards']
                    candidates=[c for c in cards if c.get('read_action') and wanted in c['target']['heading']]
                    if candidates:
                        if route=='context':assert len(cards)==9
                        if nested:
                            headings={c['target']['heading'].split()[0] for c in cards}
                            assert headings==({'제2조'} if route=='narrow' else {'제2조','제3조'})
                        c=candidates[0]
                        if mode=='route_recovery':
                            self.choices.append('EARLY_FINISH')
                            return respond({'choice':'FINISH','basis_refs':[s['id'] for s in view['sources']],
                                'issue_refs':['Q1'],'evidence_sufficient':False,'reason':'확보 원문으로 종료 제안'})
                        self.choices.append('READ_LINK')
                        return respond({'choice':'READ','selections':[{'target':c['read_action'],'issue_id':'Q1',
                            'missing_need':'필요한 연결 원문 확인','relation':'DEPENDENCY','source_ref':view['sources'][0]['id']}]})
                    if mode=='page_handoff' and self.link_selected and view['references'].get('dependency_cards_on_other_pages'):
                        # The normal compact input intentionally hides cards on
                        # other pages. Scan forward before claiming completion.
                        moves=view['read_candidate_page'].get('actions',[])
                        assert 'NEXT_READ_CANDIDATES' in moves, (wanted,view['read_candidate_page'])
                        return wire({'choice':'NEXT_READ_CANDIDATES'})
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
                    candidate = next((c for c in view['read_candidates'] if c.get('coordinate')==wanted),None)
                    if mode=='page_handoff' and candidate is None:
                        assert 'NEXT_READ_CANDIDATES' in view['read_candidate_page'].get('actions',[])
                        return wire({'choice':'NEXT_READ_CANDIDATES'})
                    assert candidate is not None, wanted
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
                    result['issue_assessments'][0].update(status='COVERED' if mode in ('supported','route_recovery','goal_control') else 'PARTIAL',reason='현재 원문으로 요구한 기준 확인' if mode in ('supported','route_recovery','goal_control') else '추가 해석 또는 사건 사실을 아직 확인하지 못했다.')
                    if mode in ('limited_source','limited_fact') or mode=='partial_repair' and phase.endswith('-repair'):
                        result['gaps']=[{**GAP,'kind':'MISSING_SOURCE' if mode=='limited_source' else 'MISSING_FACT',
                            'material_id':None,'material':True,'missing_target':'','previous_gap_key':None,
                            'reason':'구체적인 산정 단위를 확정할 추가 근거가 필요하다.' if mode=='limited_source' else '사용자의 실제 서면 승인 여부가 제공되지 않았다.',
                            'suggested_action':'RESEARCH' if mode=='limited_source' else 'REQUEST_FACT'}]
                    else:result['gaps']=[]
                    return respond(result)
                gap = {**GAP, 'reason': '원문검토검증규정 제2조 적용 범위 원문이 필요하다.',
                       'missing_target': '원문검토검증규정 제2조'}
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
    profile['candidate_navigation'].update(source_goal_control=False,stable_navigation_references=True,new_read_reviews=True,independent_read_recovery=True,minimal_input=True,read_candidate_page_size=20,selected_connection_scope=True,small_connection_context=True,answer_first=False,answer_progress_control=False,read_judgment=True)
    if mode=='goal_control':profile['candidate_navigation']['source_goal_control']=True
    if mode=='off':profile['candidate_navigation']['supervisor_mode']='off'
    if mode=='page_handoff':profile['candidate_navigation']['read_candidate_page_size']=1
    profile['candidate_navigation'].update(assessment_consistency=True,assessment_reentry_limit=0)
    profile.update(model_binding=transport.binding, answer_presentation='accepted-content-v1' if mode in ('supported','route_recovery','goal_control') else 'grounded-narrative-v1')
    app = create_app(tmp_path, generation, contracts_root=root, provider=object(),
        implementation='legal-agent-unified-v6', legal_agent_profile=profile, legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id': 'synthetic', 'team_id': 'risk_team', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = index
    with TestClient(app) as api:
        request = {'question': question, 'session_id': route, 'request_id': 'r1'}
        if exercise is not None:
            return exercise(api, transport, request, tmp_path / '90_RUNTIME/semantic')
        from semantic_runtime.legal_agent.answer_stream import capture
        tokens=[]
        with capture('r1',tokens.append):response = api.post('/v1/rag/ask', json=request)
        if mode=='partial_twice' or coverage_fault in ('twice','change_twice','need_twice','rejected_need_twice','scope_twice'):
            assert response.status_code==200,response.text
            result=response.json();outcome=result['assembly']['term_agent']['accepted_outcome']
            assert not result['answer']['claims']
            assert outcome['disposition']=='LIMITED_ANSWER' and outcome['answer_coverage']!='COVERED'
            assert outcome['stop_reason']=='ASSESSMENT_CONTRACT_UNRESOLVED'
            assert target_text in result['answer']['text'] and result['answer']['unresolved']
            count=len(transport.calls);again=api.post('/v1/rag/ask',json=request)
            assert again.status_code==200 and again.json()['answer']==result['answer']
            assert len(transport.calls)==count
            assert not tokens
            assert len([p for p in transport.calls if p.startswith('memory-assess')])==2
            assert not any(p.startswith('memory-compose') for p in transport.calls)
            from semantic_runtime.legal_agent import read_judgment as rj
            journal=next(tmp_path.glob('90_RUNTIME/semantic/legal-agent/runs/*/'+result['run_id']+'/journal.sqlite'))
            with __import__("semantic_runtime.legal_agent.journal_storage",fromlist=["connect"]).connect(journal) as db:
                events=[json.loads(v) for v, in db.execute("SELECT payload_json FROM event WHERE kind='READ_JUDGMENT_RECORDED'")]
                assert sum(len(e['changes']) for e in events)>=(1 if rejected_need else 3)
            app.state.pipeline.store.close()
            return
        assert response.status_code == 200, response.text
        result = response.json()
        # Structured limited responses are delivered in the final API body.
        # There must be no generated narrative tokens before that result.
        assert not tokens
        assert target_text in result['answer']['text']
        assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage'] == ('COVERED' if mode in ('supported','route_recovery','goal_control') and coverage_fault not in ('gap_link','open') and not rejected_need else 'PARTIAL')
        assert result['assembly']['term_agent']['accepted_outcome']['disposition']==('ANSWER' if mode in ('supported','route_recovery','goal_control') and coverage_fault not in ('gap_link','open') and not rejected_need else 'LIMITED_ANSWER')
        if mode not in ('supported','route_recovery','goal_control'):
            assert '확인 범위' in result['answer']['text']
            assert ('산정 단위' if mode=='limited_source' else '실제 서면 승인 여부') in result['answer']['text']
        assert not any(p.startswith('memory-compose') for p in transport.calls)
        if mode in ('open_need','conflict'):assert '추가 조건을 아직 확인하지 못했다' in result['answer']['text']
        stages={r['stage']:r for r in result['assembly']['term_agent']['judgment_view']['stages']}
        assert stages['SELECT']['read_judgments']
        assert len([r for r in stages['SELECT']['data'] if r.get('judgment_id')])==(1 if rejected_need else 3)
        assert any('이유:' in r for r in stages['SELECT']['decisions'])
        if mode!='final_truncated':assert stages['ASSESS']['decisions']
        receipt=stages['ASSESS']['read_judgment_review']
        assert len(receipt['prior_judgments'])==3 and len(receipt['prior_needs'])>=3
        assert receipt['status']==('INCOMPLETE' if mode=='final_truncated' else 'REVIEWED')
        from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
        from semantic_runtime.legal_agent.unified_publication import validate_saved
        journal=next(tmp_path.glob('90_RUNTIME/semantic/legal-agent/runs/*/'+result['run_id']+'/journal.sqlite'))
        repo=UnifiedRepository(journal)
        if mode=='goal_control':
            from semantic_runtime.legal_agent import judgment_view
            original_build=judgment_view.build
            def diagnostic_build(*args,**kwargs):
                expected=original_build(*args,**kwargs)
                (tmp_path/'view-difference.json').write_text(json.dumps({'actual':result['assembly']['term_agent']['judgment_view'],'expected':expected},ensure_ascii=False,indent=2))
                return expected
            monkeypatch.setattr(judgment_view,'build',diagnostic_build)
        try:validate_saved(repo,result)
        finally:repo.close()
        if rejected_need:
            assert rejected_text in result['answer']['text']
            assert stages['SELECT']['stop_reason']=='MODEL_DECISION_UNRESOLVED'
            with __import__("semantic_runtime.legal_agent.journal_storage",fromlist=["connect"]).connect(journal) as db:
                failures=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='OUTPUT_DECISION_STATE'")]
                observed=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='NEED_DECLARATION_OBSERVED'")]
                selected=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='READ_CHOICE_SELECTED'")]
            from semantic_runtime.contracts import digest
            failures=[x for x in failures if x['status']=='REJECTED' and x.get('proposal',{}).get('choice')=='FOLLOW_CONNECTION']
            assert len(failures)==2
            assert all('READ_ACTION_JUDGMENT_REFERENCE' in str(x['failure']) for x in failures)
            assert {x['proposal_hash'] for x in failures}<={x['proposal_hash'] for x in observed}
            assert not ({x['proposal_hash'] for x in failures}&{digest(x['choice']) for x in selected})
        if mode in ('independent_after_failure','independent_conflict_after_failure'):
            with __import__("semantic_runtime.legal_agent.journal_storage",fromlist=["connect"]).connect(journal) as db:
                recoveries=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='INDEPENDENT_READ_RECOVERY'")]
                assert len(recoveries)==1 and recoveries[0]['judgments_adopted'] is False
                heads=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='READ_JUDGMENT_RECORDED'")]
                assert '채택되면 안 되는 수정' not in json.dumps(heads,ensure_ascii=False)
        calls = len(transport.calls)
        again = api.post('/v1/rag/ask', json=request)
        assert again.status_code == 200 and again.json()['answer'] == result['answer']
        assert len(transport.calls) == calls
    if mode=='goal_control':
        assert transport.calls.count('source-law-navigation-supervisor-read-choice')<=2
        with __import__("semantic_runtime.legal_agent.journal_storage",fromlist=["connect"]).connect(journal) as db:
            goal_rows=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='SOURCE_GOAL_RESULT'")]
        assert len([x for x in goal_rows if x['status']=='ACQUIRED'])>=2
        with __import__("semantic_runtime.legal_agent.journal_storage",fromlist=["connect"]).connect(journal) as db:
            bundles=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='SOURCE_REFERENCE_BUNDLE_BOUND'")]
        assert not bundles, 'server must not expand unselected sibling references'
        assert any('제3조 별도 기준' in str(v.get('evidence_options',[])) for v in transport.views if v.get('source_stage',v['phase']).startswith('memory-assess'))
    elif mode=='route_recovery':assert transport.calls.count('source-law-navigation-supervisor-read-choice')<=2
    else:assert transport.calls.count('source-law-navigation-supervisor-read-choice')==(0 if mode=='off' else 2)
    assert transport.reference_calls == 0
    expected=['READ','FOLLOW_CONNECTION','READ_LINK','FINISH']
    if mode=='navigation_repair':expected.insert(2,'FOLLOW_CONNECTION')
    if mode in ('independent_after_failure','independent_conflict_after_failure'):expected.insert(3,'READ_LINK')
    # A rejected proposal may select a different tool in the corrected call;
    # neither rejected action nor its opinion is committed.
    if mode not in ('page_handoff','goal_control','route_recovery'):assert transport.choices == expected
    elif mode=='page_handoff':
        with __import__("semantic_runtime.legal_agent.journal_storage",fromlist=["connect"]).connect(journal) as db:
            moves=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='READ_CANDIDATE_PAGE_SELECTED'")]
        assert any(x.get('actor')=='supervisor' for x in moves)
        assert all(not x['originals_acquired'] and not x['judgments_completed'] for x in moves)
        assert len(transport.calls)<=40
    assert len([p for p in transport.calls if p.startswith('memory-assess')]) == (2 if mode=='partial_repair' or coverage_fault in ('first','change_first','need_first','rejected_need_first','scope_first') else 1)
    if mode not in ('page_handoff','goal_control','route_recovery'):assert len(transport.calls) == (6 if mode=='off' else 8) + (mode in ('navigation_repair','independent_after_failure','independent_conflict_after_failure','final_repair','partial_repair')) + (coverage_fault=='first')
    assert not any('judgment' in p for p in transport.calls), 'review must share existing calls'
    app.state.pipeline.store.close()

    with __import__("semantic_runtime.legal_agent.journal_storage",fromlist=["connect"]).connect(journal) as db:
        reviews=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='REQUIREMENT_COVERAGE_REVIEWED'")]
        assessments=[json.loads(x[0]) for x in db.execute("SELECT payload_json FROM event WHERE kind='ASSESSMENT_VALIDATED'")]
    assert len(reviews)==1 and reviews[0]['separate_model_call'] is False
    assert len(assessments)==1 and assessments[0]['assessment']['requirement_review']['rows']
    if coverage_fault=='gap_link':
        a=assessments[0]['assessment'];assert a['requirement_review']['reconciliation']['gaps_unchanged'] and a['requirement_review']['reconciliation']['claims_unchanged']
        assert any(r['status']=='UNRESOLVED' for r in a['requirement_review']['rows'])
        assert '별도 수량 기준' in result['answer']['text']
    if mode=='route_recovery':
        with __import__("semantic_runtime.legal_agent.journal_storage",fromlist=["connect"]).connect(journal) as db:
            recovered=[json.loads(v) for v, in db.execute("SELECT payload_json FROM event WHERE kind='SUPERVISOR_INDEPENDENT_ROUTE_RECOVERED'")]
            rejected=[json.loads(v) for v, in db.execute("SELECT payload_json FROM event WHERE kind='SUPERVISOR_DIRECTIVE_REJECTED'")]
        assert len(recovered)==len(rejected)==1
        assert recovered[0]['next_action']=='READ_ARTICLES' and recovered[0]['directive_accepted'] is False
        assert 'EARLY_FINISH' in transport.choices
    return result, transport.calls, reviews


def change_review(head):
    old=head.get('change_from',{'version':0,'finding':''})
    return {'prior_version':old['version'],'prior_finding_quote':old['finding'],
        'purpose_reviews':[{'purpose_id':p['id'],'source_quote':p['source_quote'],'status':'ROLE_ONLY',
            'basis_refs':list(dict.fromkeys(head['available_evidence_refs']+p.get('origin_evidence_refs',[])+p.get('target_evidence_refs',[]))),
            'claim_refs':[],'gap_indices':[],'reason':'이전 해석은 유지하며 이번 답변에서 사용하지 않음'} for p in head['review_purposes']]}
