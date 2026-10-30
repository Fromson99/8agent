from pathlib import Path
# Execute the same replay harness against the current frozen candidate. Stored
# prelude responses are semantic data; the first newly required model call stops.
p=Path(__file__).with_name('replay.py');s=p.read_text()
a=s.index("candidate=read(ROOT/read(DES/'candidate.json')");b=s.index("baseline=read(DES/'baseline.json')",a);s=s[:a]+s[b:]
s=s.replace("'baseline-replay-v5'","('candidate-replay-'+f['candidate_revision']['revision_id'])")
s=s.replace("if number>target:raise errors.TransportError", """if number>=target:
  from semantic_runtime.legal_agent import query_scope as qs
  inv=active['inv'];original_grants=deepcopy(inv.s.scope_read_grants)
  cp=deepcopy(inv.p);cp['scope_read_grants']=original_grants
  scope=deepcopy(qs.active(inv.s));qs.attach(inv.s,scope);qs.restore_grants(inv.s,cp)
  assert all(set(rows)<=qs.permitted_blocks(inv.s,sid) for sid,rows in original_grants.items())
  put(base/'grant-resume.json',{'passed':True,'blocks':sum(len(x) for x in original_grants.values()),'direct_scope_unchanged':qs.active(inv.s)==scope})
  put(base/'before-next-model.json',{'phase':active['phase'],'state':active['inv'].p,'data':active['data'],'model_calls_for_required_goal':0})
  raise errors.TransportError""")
# Baseline stored documents become the new document_ref only, using the same
# authorized tool's exact document identity. No prose parsing.
s=s.replace("refs=NavigationReferences(active['view']);saved=refs._map(saved,remap)", """refs=NavigationReferences(active['view']);saved=refs._map(saved,remap)
 if saved.get('source_targets'):
  for goal in saved['source_targets']:
   token=goal.pop('lookup_target');goal['document_ref']=active['actions'][token]['identity']['document_id']""")
# For007 the stored target is itself the new verified declaration, so consume it
# once, then forbid the next model call;001 already has a durable ASSESS target.
s=s.replace("if number>=target:", "if number>target if case_id=='cm-007' else number>=target:")
exec(compile(s,str(p),'exec'))
