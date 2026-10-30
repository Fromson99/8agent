from common import *
p=Path(__file__).with_name('test_scenario_native.py');s=p.read_text();s=s.replace("['normal','no_match','repair','conditional']","['normal','multi','repair','conditional','reselect','no_match','still_insufficient','empty_catalog','twice_invalid']")
s=s.replace('    need_more=False',"    fallback=mode in ('no_match','still_insufficient','empty_catalog','twice_invalid')\n    need_more=fallback")
s=s.replace("            self.calls.append(phase);self.views.append(deepcopy(view))\n            catalog=view['ontology_bundles'][0]['scenario_catalog']", """            self.calls.append(phase);self.views.append(deepcopy(view))
            cards=[c['scenario_catalog'] for c in view.get('ontology_bundles',[]) if 'scenario_catalog' in c]
            if not cards:
                assert fallback
                found=next(o for o in view['evidence_options'] if target_text in o['text'])
                value=proposal(target_text,'OBLIGATION',[found['id']],found['id']);value.pop('disposition')
                used=set(value['claims'][0]['evidence_refs']);ctx=view['read_judgments']
                value['read_judgment_review']={'judgments':[{'id':h['id'],'disposition':'USE' if used.intersection(h['available_evidence_refs']) else 'NOT_USED','claim_refs':['C1'] if used.intersection(h['available_evidence_refs']) else [],'basis_refs':list(used.intersection(h['available_evidence_refs'])),'reason':'추가 조사 원문으로 판단'} for h in ctx['judgments']], 'needs':[{'id':n['id'],'status':'NOT_NEEDED','reason':'현재 확보 원문에 반영','material':False,'basis_refs':[]} for n in ctx['needs']], 'conflicts':[]}
                return wire(value)
            catalog=cards[0]""")
s=s.replace("            paths=[] if mode=='no_match' else ['PATH1']", "            paths=[] if mode=='no_match' else ['PATH1','PATH2'] if mode=='multi' else ['PATH1']")
s=s.replace("            if mode=='repair' and phase=='memory-assess':paths=['UNKNOWN']", "            if mode=='twice_invalid' or mode=='repair' and phase=='memory-assess':paths=['UNKNOWN']\n            action='SEARCH' if mode=='no_match' else 'RESELECT' if mode=='still_insufficient' or mode=='reselect' and not view.get('previous_choice') else 'ANSWER'")
s=s.replace("'missing_facts':['대상 거래 여부'] if mode=='conditional' else []", "'missing_facts':['대상 거래 여부'] if mode=='conditional' else [],'next_action':action,'missing_scope':['연결된 적용 기준 원문'] if action!='ANSWER' else []")
s=s.replace("    package=sc.compile_package(recipe,originals)","""    if mode=='multi':
        second=deepcopy(recipe['paths'][0]);second.update(id='PATH2',title='예외 검토 경로');recipe['paths'].append(second)
    if mode=='empty_catalog':
        with sqlite3.connect(tmp_path/'raw.sqlite') as db:second_text=db.execute("SELECT text FROM source_block WHERE document_id='d' AND block_id='1'").fetchone()[0]
        originals[0]['anchor']={**originals[0]['anchor'],'unit_id':'1','label':'합성 제2조','content_sha256':oc.compiler.content_hash(second_text)};originals[0]['text']=second_text
        for component in recipe['components']:component['basis']=[{'source':'P1','quote':second_text}]
    package=sc.compile_package(recipe,originals)""")
s=s.replace("answer_presentation='grounded-narrative-v1'", "answer_presentation='structured' if fallback else 'grounded-narrative-v1'")
s=s.replace("            if mode!='no_match':assert package['paths'][0]['body'] in result['answer']['text']", "            if fallback:assert target_text in result['answer']['text']\n            else:\n                assert package['paths'][0]['body'] in result['answer']['text']\n                if mode=='multi':assert package['paths'][1]['body'] in result['answer']['text']")
s=s.replace("        assert t.calls.index('memory-assess')==2,t.calls\n        assert t.calls.count('memory-assess')==1,t.calls\n        assert t.calls.count('memory-assess-repair')==(1 if mode=='repair' else 0),t.calls\n        assert 'FINISH' not in t.choices", """        catalogs=[v for v in t.views if any('scenario_catalog' in c for c in v.get('ontology_bundles',[]))]
        assert len(catalogs)==(0 if mode=='empty_catalog' else 2 if mode in ('repair','reselect','still_insufficient','twice_invalid') else 1),t.calls
        if fallback:
            assert 'FOLLOW_CONNECTION' in t.choices and 'READ_LINK' in t.choices and 'FINISH' in t.choices,t.choices
            ordinary=[v for v in t.views if v.get('source_stage')=='memory-assess' and not any('scenario_catalog' in c for c in v.get('ontology_bundles',[]))]
            assert len(ordinary)==1,t.calls
            assert any(target_text in o['text'] for o in ordinary[0]['evidence_options'])
            assert ordinary[0]['gap_history']
        else:assert 'FINISH' not in t.choices
        assert t.calls.count('memory-assess-repair')==(1 if mode in ('repair','twice_invalid') else 0),t.calls""")
p.write_text(s)
