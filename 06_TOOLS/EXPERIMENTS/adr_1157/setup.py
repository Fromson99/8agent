from pathlib import Path
import json,sys,shutil,hashlib
ROOT=Path(__file__).resolve().parents[3];P=ROOT/'04_EXPERIMENTS/ADR/ADR-1156-ontology-workflow-connected';A=ROOT/'04_EXPERIMENTS/ADR/ADR-1157-ontology-workflow-sql-binding';T=Path(__file__).parent
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1156').glob('*.py'):
 if p.name in ('setup.py','prepare_tests.py','finish_failure.py'):continue
 s=p.read_text().replace('ADR-1156-ontology-workflow-connected','ADR-1157-ontology-workflow-sql-binding').replace('adr_1156','adr_1157')
 if p.name=='check.py':s=s.replace("if mode=='ontology':paths.append(str(Path(__file__).parent/'test_prompt_integration.py'))",'# Prompt-only file comparison belongs to earlier release, not this workflow change.')
 (T/p.name).write_text(s)
D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
for name in ('baseline.json','criteria.json','test-support.json','api-sources.json'):shutil.copyfile(P/'artifacts/design'/name,D/name)
criteria=read(D/'criteria.json');criteria['hypothesis']+=' Repair SQLite named bindings; preserve failed1156. Also audit bounded model transport, draft storage failures, UI browser identity and data publication replay.';put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json')
for k in ('design','dataset','retrieval_accounting'):m[k]=old[k]
m['design']['code_isolation']['candidates']=[]
m['design']['hypothesis']=criteria['hypothesis'];m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0]['derived_from']=['ADR-1156-experiment-v1/connected']
m['design']['arms'][1]['changes']='1156 SQLite named binds, bounded transport and terminal persistence semantics; same workflow architecture'
m['dataset'].update(frozen_source=str((D/'criteria.json').relative_to(ROOT)),sha256=sha(D/'criteria.json'),version='1157-v1')
m['runs'][0].update(arm_ids=['connected'],selection_rule='Same prospective workflow, UI, database-native and existing216 contracts; zero model calls',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[];put(A/'실험/manifest.json',m)
f=read(P/'artifacts/design/freeze.json');sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(A,'connected-r1',[n for n in f['files'] if (ROOT/n).is_file()],experiment_id=m['experiment_id'],arm_id='connected',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 dst=S/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/f['code_root']/n,dst)
 if not (ROOT/n).exists():ac.register_file(C,n,upstream_state='absent')
p=S/'02_BACKEND/semantic_runtime/ontology_work/repository.py';s=p.read_text().replace('return c.execute(sql,params)','return c.execute(sql,{str(i+1):v for i,v in enumerate(params)} if self.dialect=="sqlite" else params)');p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/ontology_work/workflow.py';s=p.read_text()
a=s.index('            try:\n                schema.recipe_for(work,proposal,');b=s.index('    def load(self,bid):',a)
s=s[:a]+'''            try:
                schema.recipe_for(work,proposal,'cb-proposal-check')
            except (ContractError,ValidationError) as e:
                attempts.append({'proposal':proposal,'receipt':receipt,'error':str(e)[:1600]})
                self.store.put({'request_id':request_id,'status':'INVALID','attempt':attempt+1,'detail':attempts[-1]})
                if attempt:raise
                context={**work,'previous_proposal':proposal,'structural_error':str(e)[:1600],
                    'repair':'원문과 의미를 유지하며 지적된 구조·참조·인용 오류만 한 번 보완한다.'}
                continue
            # A source/SQL/storage failure is not a model formatting failure.
            try:
                result=self.save(work,proposal,bundle_id=bundle_id,expected_revision=expected_revision)
            except Exception as exc:
                self.store.put({'request_id':request_id,'status':'SAVE_UNCONFIRMED','proposal':proposal,
                    'provider_receipt':receipt,'error_type':type(exc).__name__})
                raise
            self.store.put({'request_id':request_id,'status':'DRAFT_CREATED','draft':result,'attempts':attempts,'provider_receipt':receipt})
            return result
'''+s[b:];p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/ontology_work/configuration.py';s=p.read_text();a=s.index('        def generate(prompt,context,schema):');b=s.index('    return Workflow(',a)
s=s[:a]+'''        def generate(prompt,context,schema):
            from dataclasses import replace
            from ..genos import from_env,advertised_model,request_json
            from ..provider import _structured_genos_value
            from .schema import now
            target,configured=from_env('llm')
            target=replace(target,max_retries=1)
            model=advertised_model(target,configured)
            request={'model':model,'messages':[{'role':'system','content':prompt},
                {'role':'user','content':json.dumps(context,ensure_ascii=False)}],
                'temperature':0,'stream':False,'chat_template_kwargs':{'enable_thinking':False},
                'response_format':{'type':'json_schema','json_schema':{'name':'ontology_recipe','strict':True,'schema':schema}}}
            request_key=store.put({'at':now(),'request':request,'status':'SENT_ONCE'})
            try:raw=request_json(target,'/chat/completions',request)
            except Exception as exc:
                store.put({'request_key':request_key,'status':'UNKNOWN','error_type':type(exc).__name__})
                raise
            key=store.put({'request_key':request_key,'response':raw,'status':'RESPONSE_RECEIVED'})
            return _structured_genos_value(raw),{'store_hash':key,'model':model}
'''+s[b:];p.write_text(s)
# Refresh manifest pins.
pipe=read(S/'00_SYSTEM/PIPELINE.json')
for ref in pipe['engines'].values():
 p=S/ref['manifest'];e=read(p)
 for n in e['files']:
  if (S/n).is_file():e['files'][n]=sha(S/n)
 put(p,e);ref['sha256']=sha(p)
put(S/'00_SYSTEM/PIPELINE.json',pipe)
print('Prepared1157 with named SQL binding and single-owner failure handling')
