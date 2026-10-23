from common import *
C=ROOT/read(ART/'stage.json')['root']
p=C/'05_TESTS/CONTRACTS/test_read_judgment_api.py';p.parent.mkdir(parents=True,exist_ok=True)
t=(ROOT/'05_TESTS/CONTRACTS/test_small_connection_context_api.py').read_text()
t=t.replace("@pytest.mark.parametrize('route', ['connection', 'context', 'chain', 'narrow', 'whole', 'batch'])", "@pytest.mark.parametrize('mode', ['normal','navigation_repair','final_repair','open_need','conflict'])")
t=t.replace('def test_small_connection_api_original_delivery_and_request_reuse(tmp_path, term_glossary, route, monkeypatch):','def test_read_judgment_api_retains_decisions_and_reuses_request(tmp_path, term_glossary, mode, monkeypatch):\n    route = "connection"')
t=t.replace("            self.reference_calls = 0", "            self.reference_calls = 0\n            self.views = []\n            self.omitted_navigation = False\n            self.omitted_final = False")
t=t.replace("            self.calls.append(phase)", '''            self.calls.append(phase)
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
                    updates=[]
                    if value['choice']=='FINISH':
                        assert ctx['judgments'] and ctx['needs'], 'prior judgment/need must survive omission'
                        if mode=='conflict':
                            rows[-1].update(operation='CONFLICT',use='DEFER',conflicts_with=[ctx['judgments'][0]['id']],
                                reason='처음 판단과 새 원문의 적용 범위가 충돌하여 보류한다.')
                        if mode not in ('open_need','conflict'):
                            updates=[{'id':n['id'],'status':'RESOLVED','reason':'추가 원문에서 적용 기준을 확인하였다.',
                                'basis_refs':rows[-1]['basis_refs']} for n in ctx['needs']]
                    value['read_review']={'judgments':rows,'need_updates':updates,'conflict_updates':[]}
                    if value['choice'] not in ('FINISH','PENDING'):
                        for action in value['selections'] if value['choice']=='READ' else [value]:
                            action['judgment_refs']=[r['judgment_id'] for r in rows] or [r['id'] for r in ctx['judgments']]
                    if mode=='navigation_repair' and ctx['required'] and not self.omitted_navigation:
                        self.omitted_navigation=True
                        value['read_review']['judgments']=[]
                if phase.startswith('memory-assess'):
                    ctx=view['read_judgments']
                    assert len(ctx['judgments'])==2, ctx
                    assert len(ctx['needs'])==1
                    if mode=='conflict':assert len(ctx['conflicts'])==1
                    review={'judgments':[],'needs':[],'conflicts':[]}
                    used=set(value['claims'][0]['evidence_refs'])
                    for head in ctx['judgments']:
                        refs=list(used & set(head['available_evidence_refs']))
                        review['judgments'].append({'id':head['id'],'disposition':'USE' if refs else 'NOT_USED',
                            'claim_refs':[value['claims'][0]['claim_id']] if refs else [],'basis_refs':refs,
                            'reason':'현재 원문과 적용 범위를 대조하여 최종 사용 여부를 판단하였다.'})
                    for field in ('needs','conflicts'):
                        review[field]=[{'id':r['id'],'status':'OPEN' if mode in ('open_need','conflict') else 'RESOLVED',
                            'reason':'추가 조건을 아직 확인하지 못했다.' if mode in ('open_need','conflict') else '추가 원문으로 적용 범위를 확인했다.',
                            'material':True,'basis_refs':list(used)} for r in ctx[field]]
                    value['read_judgment_review']=review
                    if mode=='final_repair' and not self.omitted_final:
                        self.omitted_final=True
                        value['read_judgment_review']['needs']=[]
                return wire(value)''')
t=t.replace('return wire(', 'return respond(')
# Only wrapper's own return calls raw harness serialization.
t=t.replace('                return respond(value)\n            if phase', '                return wire(value)\n            if phase')
t=t.replace('answer_progress_control=False)', 'answer_progress_control=False,read_judgment=True)')
t=t.replace("assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage'] == 'COVERED'", "assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage'] == ('PARTIAL' if mode in ('open_need','conflict') else 'COVERED')\n        if mode in ('open_need','conflict'):assert '추가 조건을 아직 확인하지 못했다' in result['answer']['text']")
t=t[:t.index('    expected = (')]+'''    expected=['READ','FOLLOW_CONNECTION','READ_LINK','FINISH']
    if mode=='navigation_repair':expected.insert(2,'READ_LINK')
    # A rejected proposal may select a different tool in the corrected call;
    # neither rejected action nor its opinion is committed.
    assert transport.choices == expected
    assert len([p for p in transport.calls if p.startswith('memory-assess')]) == (2 if mode=='final_repair' else 1)
    assert len(transport.calls) == 6 + (mode in ('navigation_repair','final_repair'))
    assert not any('judgment' in p for p in transport.calls), 'review must share existing calls'
    app.state.pipeline.store.close()
'''
p.write_text(t)
