from pathlib import Path
import json,hashlib,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1234-gold-ontology-reference-repair';D=A/'artifacts/design';O=A/'artifacts/run-001';P=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';D.mkdir(parents=True);O.mkdir()
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
old=R/'04_EXPERIMENTS/ADR/ADR-1233-gold-ontology-on-live';F=R/read(old/'artifacts/design/candidate.json')['snapshot'];m=read(A/'실험/manifest.json');C=R/read(P/'binding.json')['engine_root']
criteria={'hypothesis':'Current exact original spans can rebind an acquired ontology fragment across equivalent read receipts; generated claim IDs remain in their output namespace.','success':['Regression reproductions and relevant existing contracts pass','Real HTTP200 and persisted nonempty answer','Actual ontology369 all3paths and4exactsource units in final model wire; generated3claims cite these sources and final answer includes all3requested rules','Exact original hashes/ACL/wire/physical budget, no unknown or resource stop'],'sample':'Known public article369 question once; ordinary ASSESS with required need/requirement review, no forced scenario mode','limits':read(old/'artifacts/design/criteria.json')['limits'],'failures':'Preserve first failure and one existing contract repair; no automatic external repeat','deploy_scope':'User-authorized separate Gold connector ON; never modify frozen engine or MAIN123; general legal quality uncertified'}
put(D/'criteria.json',criteria);put(D/'cases.json',read(old/'artifacts/design/cases.json'));auth=read(old/'artifacts/design/authorization.json');auth['dispatches']='One new question execution after two isolated connection repairs; native limits unchanged';put(D/'authorization.json',auth)
put(D/'before.json',{'active_mapping':read(P/'ACTIVE_MAPPING.json'),'main_pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'engine_binding_sha256':sha(P/'binding.json')})
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual native ontology + original + claim + saved final answer chain',success_criteria=criteria['success'],failure_criteria=['Any required gate false'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((D/'criteria.json').relative_to(R)),'sha256':sha(D/'criteria.json')});m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design']['arms'][0].update(changes='Historical ADR1233 failure; not repeated',controls='Raw failure retained');m['design']['arms'][1].update(changes='Exact-span rebinding and new claim namespace; latest DTLS mapping explicitly bound',controls='Same public question/model, original checks/budgets and ordinary required review')
m['runs'][0].update(arm_ids=['repaired'],selection_rule=criteria['sample'],artifact_path=str((O/'result.json').relative_to(R)));m['dataset'].update(name='Public Gold article369 known functional case',version='20261030-2',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'));m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}];reason='No ranking change or recall comparison; source/ontology/answer IDs and actual SQL are audited.';m['retrieval_accounting'].update(changed=False,corpus_total=1,not_applicable_reason=reason);m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason;put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
base='08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';target=base+'/connect.py';S=ac.snapshot(A,'repaired',[target],experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001']);SP=S/'snapshot';code=(F/target).read_text();code=code.replace('ROOT=HERE.parents[2]','ROOT=HERE.parents[2]\nPATCH_ROOT=HERE')
loader='''def install_runtime_patches(code):
 import importlib
 pin=read(PATCH_ROOT/'runtime_patch_binding.json')
 if pin['schema_version']!='gold-runtime-patches-v1':raise RuntimeError('Gold runtime patch binding')
 for name,row in pin['modules'].items():
  module=importlib.import_module(name)
  if Path(module.__file__).resolve()!=(code/row['base_path']).resolve() or sha(module.__file__)!=row['base_sha256']:
   raise RuntimeError('Gold runtime patch base changed: '+name)
  patch=PATCH_ROOT/row['patch_file']
  if sha(patch)!=row['patch_sha256']:raise RuntimeError('Gold runtime patch changed: '+name)
  exec(compile(patch.read_text(),str(patch),'exec'),module.__dict__)

'''
code=code.replace('def load_runtime():',loader+'def load_runtime():').replace(' import engine_runtime\n return engine_runtime,binding',' import engine_runtime\n install_runtime_patches(code)\n return engine_runtime,binding');(SP/target).write_text(code)
pin={'schema_version':'gold-runtime-patches-v1','modules':{}}
for name in ['ontology_assessment','navigation_input']:
 rel='02_BACKEND/semantic_runtime/legal_agent/'+name+'.py';original=(C/rel).read_text();patched=original
 if name=='ontology_assessment':
  patched=patched.replace("if str(p['block_id']) in wanted and p['evidence_id'] in row['evidence_ids']]", "if str(p['block_id']) in wanted]")
  patched=patched.replace("and o['evidence_id'] in row['evidence_ids']]", "and o['evidence_id'] in {p['evidence_id'] for p in spans}]")
  patched=patched.replace("            spans = [p", "            # Current verified originals may use an equivalent, newer read receipt.\n            # Binding, own-block coverage and full anchor content hash stay mandatory.\n            spans = [p")
 else:
  patched=patched.replace('return self._map(value,self.reverse)\n    def restore(self,value):return self._map(value,self.reverse)', '''return self.restore(value)
    def restore(self,value):
        result=self._map(value,self.reverse)
        # New claims are declared by this response, not selected from the input's
        # ontology component/reference namespace. Preserve declarations and their
        # references; canonical validation still rejects undeclared/duplicate IDs.
        if isinstance(value,dict) and isinstance(value.get('claims'),list) and any(
                isinstance(c,dict) and 'claim_id' in c for c in value['claims']):
            def local(raw,out):
                if isinstance(raw,list) and isinstance(out,list):
                    for a,b in zip(raw,out):local(a,b)
                elif isinstance(raw,dict) and isinstance(out,dict):
                    for key,item in raw.items():
                        if key in ('claim_id','claim_refs','claim_ids'):
                            out[key]=deepcopy(item)
                        elif key=='claim_evidence_refs' and isinstance(item,dict):
                            out[key]={k:self._map(v,self.reverse) for k,v in item.items()}
                        elif key in out:local(item,out[key])
            local(value,result)
        return result''')
 assert patched!=original
 patchfile='runtime_patches/'+name+'.py';(SP/base/patchfile).parent.mkdir(parents=True,exist_ok=True);(SP/base/patchfile).write_text(patched);ac.register_file(S,base+'/'+patchfile,upstream_state='absent')
 pin['modules']['semantic_runtime.legal_agent.'+name]={'base_path':rel,'base_sha256':sha(C/rel),'patch_file':patchfile,'patch_sha256':sha(SP/base/patchfile)}
put(SP/base/'runtime_patch_binding.json',pin);ac.register_file(S,base+'/runtime_patch_binding.json',upstream_state='absent');put(SP/base/'ontology_settings.json',{'schema_version':'gold-ontology-settings-v1','enabled':True});ac.register_file(S,base+'/ontology_settings.json',upstream_state='absent')
entry='06_TOOLS/EXPERIMENTS/adr_1234/live.py';source=(F/'06_TOOLS/EXPERIMENTS/adr_1233/live.py').read_text().replace('adr_1233','adr_1234').replace('ADR-1233-gold-ontology-on-live','ADR-1234-gold-ontology-reference-repair').replace('gold-ontology-on-1233','gold-ontology-repaired-1234')
source=source.replace("ontology_settings=FROZEN/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/ontology_settings.json',", "ontology_settings=FROZEN/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/ontology_settings.json',mapping=P/'mapping_local_dtls_current.json',mapping_sha256='"+read(P/'ACTIVE_MAPPING.json')['sha256']+"',")
(SP/entry).parent.mkdir(parents=True);(SP/entry).write_text(source);ac.register_file(S,entry,upstream_state='absent');ac.freeze(S);assert not ac.validate(S),ac.validate(S);rev=read(S/'candidate.json')['revisions'][-1];RF=S/'revisions'/rev['revision_id']/'snapshot';put(D/'candidate.json',{'root':str(S.relative_to(R)),'snapshot':str(RF.relative_to(R)),'entry':str((RF/entry).relative_to(R)),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']})
print('Frozen',rev['revision_id'])
