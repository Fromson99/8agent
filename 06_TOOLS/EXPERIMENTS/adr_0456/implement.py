from pathlib import Path
R=Path.cwd();P=R/'02_BACKEND/lawrag/research/candidates/adr_0455/repaired/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime';B=R/'02_BACKEND/lawrag/research/candidates/adr_0456/stateful/snapshot/02_BACKEND/semantic_runtime'
s=(P/'repaired_navigation.py').read_text().replace('from .compact_handles import CompactHandlesProvider','from .compact_handles import CompactHandlesProvider\nfrom .work_navigation import WorkSession\nfrom .navigation_work_state import WorkState')
s=s.replace('session=previous.TypedSession(matcher,matcher.tools,self.glossary,q,scope,remaining)',"session=WorkSession(matcher,matcher.tools,self.glossary,q,scope,remaining,work_scope={'authorized':authorized,'filters':{'title_query':resolved.get('title_query',''),'scope_mode':resolved.get('scope_mode'),'selected_entities':[registry.get(h) for h in resolved.get('scope_handles',[])]}})")
s=s.replace("'findings':[{'text':j['claim'],'source_ids':[j['source_id']]} for j in state['adopted']]", "'findings':state['synthesis']['findings']")
needle="        return result\n\nclass Conversation"
s=s.replace(needle,"""        if 'work_state' not in state:
            work=WorkState(q,self.pipeline.store.manifest,authorized,scope,{'intent':resolved['intent'],'title_query':resolved.get('title_query',''),'scope_mode':resolved.get('scope_mode')},bindings)
            for record in trace:work.event(record['tool'],record['args'],record.get('result',{}),record['status'],record.get('error'))
            meta=state.get('navigation_output',{});data=meta.get('data',{})
            for doc in data.get('documents',[]):work.put('document',doc['id'],doc)
            for item in data.get('items',[]):
                if item.get('type') and item.get('identity'):work.put(item['type'],item['identity'],item)
            work.event(meta.get('kind','ROUTING_RESULT'),{},data)
            state['work_state']=work.snapshot()
        state['work_state']['routing_receipts']={'interpretation':resolved,'approved_mapping_ids':state['approved_mapping_ids'],'mapping_proposal_ids':proposal_ids}
        return result

class Conversation""")
(B/'stateful_navigation.py').write_text(s)
for f in ['compact_handles.py','expression_probe_binding.py']:
 s=(P/f).read_text().replace("arm=='repaired'","arm=='stateful'");(B/f).write_text(s)
s=(R/'06_TOOLS/EXPERIMENTS/adr_0455/runtime.py').read_text().replace('adr_0455/repaired','adr_0456/stateful').replace('ADR-0455-routing-validation-repair','ADR-0456-persistent-navigation-work-state').replace("ARMS=['baseline','repaired']","ARMS=['baseline','stateful']")
a=s.index(" p=R/'06_TOOLS/EXPERIMENTS/adr_0454/runtime.py'");b=s.index(" path=C/'snapshot'",a)
s=s[:a]+''' p=R/'06_TOOLS/EXPERIMENTS/adr_0455/runtime.py';lock=read(R/'04_EXPERIMENTS/ADR/ADR-0455-routing-validation-repair/artifacts/input-lock.json')['files'];assert sha(p)==lock[rel(p)]
 spec=importlib.util.spec_from_file_location('parent455_runtime',p);parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent);mod,old,multi,mods,root,_=parent.load()
''' +s[b:]
s=s.replace("['compact_handles','repaired_navigation']","['compact_handles','navigation_work_state','work_navigation','stateful_navigation']").replace("'probe455binding'","'probe456binding'").replace('synthetic-expression-routing-455','synthetic-expression-routing-456')
(R/'06_TOOLS/EXPERIMENTS/adr_0456/runtime.py').write_text(s)
p=R/'06_TOOLS/EXPERIMENTS/adr_0456/test_routing.py';s=p.read_text().replace("monkeypatch.setattr(mod.previous,'TypedSession',Session)","monkeypatch.setattr(mod,'WorkSession',Session)").replace('def __init__(self,matcher,tools,glossary,q,scope,limits):','def __init__(self,matcher,tools,glossary,q,scope,limits,**kwargs):').replace("'adopted':[],'stop'", "'synthesis':{'findings':[]},'adopted':[],'stop'");p.write_text(s)
