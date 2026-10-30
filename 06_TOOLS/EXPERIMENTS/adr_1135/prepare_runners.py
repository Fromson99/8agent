from common import *
p=Path(__file__).with_name('direct.py');s=p.read_text().replace("for case in read(ART/'cases.json'):","for case in [c for c in read(ART/'cases.json') if c['mode']=='saved_source_selector']:").replace('max_calls=2','max_calls=4')
s=s.replace(" def event(self,kind,value):", " def budget(self):return {'model_limit':40,'finalization_reserve':4,'model_reserved':client.calls}\n def event(self,kind,value):")
s=s.replace("self.s=SimpleNamespace(work=journal);", "self.s=SimpleNamespace(work=journal,context=SimpleNamespace(remaining=lambda:1800-(time.monotonic()-start)),sources=SimpleNamespace(profile={'selection_time_reserve_seconds':30}));")
old="""  answer=cc.compose(assessment,cc.default_plan(assessment,'text',issues));cc.verify_composition(assessment,answer)
  put(out/'assessment.json',assessment);put(out/'answer.json',answer);(out/'answer.txt').write_text(answer['text'])
"""
new="""  receipt=assessment['assessment_basis']['scenario_choice']
  put(out/'assessment.json',assessment)
  if receipt['effective_action']=='ANSWER':
   answer=cc.compose(assessment,cc.default_plan(assessment,'text',issues));cc.verify_composition(assessment,answer)
   put(out/'answer.json',answer);(out/'answer.txt').write_text(answer['text'])
  else:
   (out/'answer.txt').write_text('SEARCH_REQUESTED: this isolated selector probe stops before ordinary retrieval; the separate native case exercises it.')
  result.update(effective_action=receipt['effective_action'],selection_history=receipt['selection_history'],search_executed=False)
"""
assert old in s;s=s.replace(old,new)
s=s.replace("put(ART/'run-001/raw-summary.json'","put(ART/'run-001/direct-summary.json'")
p.write_text(s)
p=Path(__file__).with_name('native.py');s=p.read_text().replace("arm=sys.argv[1]","arm='scenario'").replace("assert arm in ('baseline','semantic')","assert arm=='scenario'")
start=s.index("if arm in ('baseline','semantic'):");end=s.index('profile=check_profile',start)
s=s[:start]+"""snapshot=read(ROOT/f['snapshot_path'])
pinned['candidate_navigation'].update(ontology_direct_assessment=True,ontology_context={'mode':'A1','snapshot':snapshot,'snapshot_sha256':f['snapshot_digest'],'scenario_package':read(ART/'package.json')})
"""+s[end:]
start=s.index("    if view.get('source_stage')=='memory-assess' and number==3:");end=s.index("    current['active'].append(row)",start);s=s[:start]+s[end:]
start=s.index('    if n<=2:');end=s.index("    row['new_model_call']=True",start);s=s[:start]+s[end:]
s=s.replace("cases=read(ART/'cases.json')", "cases=[c for c in read(ART/'cases.json') if c['mode']=='native_http_fresh']")
s=s.replace("'environment':'WSL MAIN107 isolated native HTTP with A1 only on ontology arm'", "'environment':'WSL MAIN107 based1134 identical candidate native HTTP, fresh actual navigation, A1 scenario package; no prefix replay'")
s=s.replace("f['binding']","f['binding']")
s=s.replace("completed',len(complete)","completed',len(complete)")
p.write_text(s)
p=Path(__file__).with_name('source_audit.py');s=p.read_text().replace("for case in read(ART/'cases.json'):","for case in [c for c in read(ART/'cases.json') if c['mode']=='native_http_fresh']:");p.write_text(s)
