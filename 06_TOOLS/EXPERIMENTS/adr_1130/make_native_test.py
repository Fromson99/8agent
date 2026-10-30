from common import *
p=ROOT/'06_TOOLS/EXPERIMENTS/adr_1124/test_direct.py';s=p.read_text()
s=s.replace('@pytest.mark.parametrize(\'with_semantics\',[False,True])\n@pytest.mark.parametrize(\'need_more\',[False,True])', "@pytest.mark.parametrize('mode',['normal','no_match','repair','conditional'])")
s=s.replace('def test_main106_native_direct_and_gap(tmp_path,term_glossary,monkeypatch,need_more,with_semantics):','def test_native_scenario_choice_and_publication(tmp_path,term_glossary,monkeypatch,mode):\n    need_more=False')
start=s.index('            assert view[\'ontology_bundles\'][0][\'status\']==\'COMPLETE\'')
end=s.index('            return wire(value)',start)
s=s[:start]+'''            catalog=view['ontology_bundles'][0]['scenario_catalog']
            assert catalog['paths'][0]['body']==package['paths'][0]['body']
            paths=[] if mode=='no_match' else ['PATH1']
            if mode=='repair' and self.calls.count('memory-assess')==1:paths=['UNKNOWN']
            value={'choices':[{'issue_id':'Q1','path_ids':paths,'status':'NO_MATCH' if mode=='no_match' else 'CONDITIONAL' if mode=='conditional' else 'GENERAL_RULE','reason':'选择된 업무의 사전 경로', 'missing_facts':['대상 거래 여부'] if mode=='conditional' else []}]}
''' +s[end:]
s=s.replace("if phase!='memory-assess':", "if phase not in ('memory-assess','memory-assess-repair'):")
start=s.index('    if with_semantics:');end=s.index('    profile.update(',start)
s=s[:start]+'''    from semantic_runtime.legal_agent import ontology_scenarios as sc
    from test_scenarios import fixture
    recipe,_,_=fixture();recipe['bundle_id']=bundle_value['bundle_id']
    originals=[{'id':'P1','anchor':bundle_value['provisions'][0]['anchor'],'text':provisions[0][1]}]
    for component in recipe['components']:component['basis']=[{'source':'P1','quote':provisions[0][1]}]
    recipe['components'][1]['text']='사전 조립된 합성 승인 경로의 결과'
    package=sc.compile_package(recipe,originals)
    profile['candidate_navigation']['ontology_context']['scenario_package']=package
    monkeypatch.setattr(sc,'compile_package',lambda *a,**k:(_ for _ in ()).throw(AssertionError('compiler invoked during request')))
''' +s[end:]
s=s.replace("answer_presentation='structured'", "answer_presentation='narrative'")
s=s.replace("result=response.json();assert target_text in result['answer']['text']", "result=response.json();assert result['answer']['text']\n            if mode!='no_match':assert package['paths'][0]['body'] in result['answer']['text']\n            assert not any('compose' in phase for phase in t.calls),t.calls")
s=s.replace("assert t.calls.count('memory-assess')==(2 if need_more else 1),t.calls", "assert t.calls.count('memory-assess')==1,t.calls\n        assert t.calls.count('memory-assess-repair')==(1 if mode=='repair' else 0),t.calls")
s=s.replace("print('MAIN106_DIRECT_HTTP',need_more,t.calls)","print('SCENARIO_NATIVE_HTTP',mode,t.calls)")
Path(__file__).with_name('test_scenario_native.py').write_text(s)
