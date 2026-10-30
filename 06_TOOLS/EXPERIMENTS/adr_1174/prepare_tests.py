from common import *
T=Path(__file__).parent
s=(T/'test_native_supervisor.py').read_text()
s=s.replace("['normal','off','page_handoff','goal_control']", "['partial_repair','partial_twice','limited_source','limited_fact']")
s=s.replace('def test_read_judgment_api_retains_decisions_and_reuses_request','def test_consistency_native_api_store_and_retry')
s=s.replace("                    result.pop('disposition')", """                    result.pop('disposition')
                    result['issue_assessments'][0].update(status='PARTIAL',reason='추가 해석 또는 사건 사실을 아직 확인하지 못했다.')
                    if mode in ('limited_source','limited_fact') or mode=='partial_repair' and phase.endswith('-repair'):
                        result['gaps']=[{**GAP,'kind':'MISSING_SOURCE' if mode=='limited_source' else 'MISSING_FACT',
                            'material_id':None,'material':True,'missing_target':'','previous_gap_key':None,
                            'reason':'구체적인 산정 단위를 확정할 추가 근거가 필요하다.' if mode=='limited_source' else '사용자의 실제 서면 승인 여부가 제공되지 않았다.',
                            'suggested_action':'RESEARCH' if mode=='limited_source' else 'REQUEST_FACT'}]
                    else:result['gaps']=[]""")
s=s.replace("    profile.update(model_binding=transport.binding, answer_presentation='structured')", "    profile['candidate_navigation'].update(assessment_consistency=True,assessment_reentry_limit=0)\n    profile.update(model_binding=transport.binding, answer_presentation='grounded-narrative-v1')")
s=s.replace("if mode=='final_failed':\n            assert response.status_code==422", "if mode=='partial_twice':\n            assert response.status_code==422")
s=s.replace("            assert len([p for p in transport.calls if p.startswith('memory-assess')])==2", "            assert len([p for p in transport.calls if p.startswith('memory-assess')])==2\n            assert not any(p.startswith('memory-compose') for p in transport.calls)")
s=s.replace("('INSUFFICIENT' if mode=='final_truncated' else 'PARTIAL' if mode in ('open_need','conflict') else 'COVERED')", "'PARTIAL'")
s=s.replace("        if mode in ('open_need','conflict'):assert", "        assert result['assembly']['term_agent']['accepted_outcome']['disposition']=='LIMITED_ANSWER'\n        assert '확인 범위' in result['answer']['text']\n        assert ('산정 단위' if mode=='limited_source' else '실제 서면 승인 여부') in result['answer']['text']\n        assert not any(p.startswith('memory-compose') for p in transport.calls)\n        if mode in ('open_need','conflict'):assert")
s=s.replace("(2 if mode=='final_repair' else 1)","(2 if mode=='partial_repair' else 1)")
s=s.replace("'independent_conflict_after_failure','final_repair'))", "'independent_conflict_after_failure','final_repair','partial_repair'))")
(T/'test_consistency_native.py').write_text(s)
p=T/'check.py';s=p.read_text().replace("str(T/'test_serving_provider.py')", "str(T/'test_serving_provider.py'),str(T/'test_consistency.py'),str(T/'test_consistency_native.py')");p.write_text(s)
p=T/'regression.py';s=p.read_text();s=s.replace("mode=sys.argv[1];C=ROOT/(read(DES/'baseline.json')['release']['code_root'] if mode=='main112' else f['code_root'])", "mode=sys.argv[1];C=ROOT/(read(DES/'baseline.json')['release']['code_root'] if mode=='main112' else read(DES/'parent-freeze.json')['code_root'] if mode=='parent' else f['code_root'])")
s=s.replace("if mode!='main112':", "if mode not in ('main112','parent'):");p.write_text(s)
print('native fault tests prepared')
