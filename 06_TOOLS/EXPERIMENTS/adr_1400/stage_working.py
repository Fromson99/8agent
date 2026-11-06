"""Compose only this repair onto the current shared implementation; no MAIN change."""
from common import *
import shutil,importlib.util,ast
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
current=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/current['manifest_path']);m=read(ADR/'실험/manifest.json')
assert read(ART/'unit-r1/result.json')['exit_code']==0
assert read(ART/'compatibility-r2/result.json')['exit_code']==0
before={n:sha(ROOT/n) for n in release['files']};put(DES/'working-before.json',{'pointer':current,'files':before})
can=ac.snapshot(ADR,'working-integration',list(before),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001']);C=can/'snapshot'
source=ROOT/read(DES/'candidate-repaired.json')['code_root'];n='02_BACKEND/semantic_runtime/legal_agent/'
shutil.copyfile(source/(n+'memory_methods.py'),C/(n+'memory_methods.py'))
s=(source/(n+'corrected_memory.py')).read_text()
s=s.replace('from jsonschema import validate, ValidationError','from jsonschema import validate, ValidationError\nfrom .errors import ContractError')
a="""            transition=transition_preview(command,context)
            check=self.invoke"""
b="""            transition=transition_preview(command,context)
            from . import reason_decision_review as reason_review
            reviewed_execution={**model_context(command),'transition':model_context(transition)}
            try:
                receipt=reason_review.for_command(self,visible,raw,reviewed_execution)
            except reason_review.ReviewConflict as exc:
                exc.proposal={'command':deepcopy(raw),'check':None,'transition':transition}
                raise
            # Reason/action consistency and current-request intent are distinct
            # contracts. A reason-review PASS cannot skip the state review.
            check=self.invoke"""
assert a in s;s=s.replace(a,b)
s=s.replace("return {'command':raw,'check':check,'transition':transition}","return {'command':raw,'check':check,'transition':transition,'reason_review':receipt['decision'] if receipt else None}")
s=s.replace("            validate_transition(command,transition,value['check'])", """            validate_transition(command,transition,value['check'])
            from .reason_decision_review import for_command
            receipt=for_command(self,visible,value['command'],
                {**model_context(command),'transition':model_context(transition)})
            if receipt and value['reason_review']!=receipt['decision']:
                raise ContractError('command reason review receipt changed')""")
s=s.replace("        try:\n            value=output.bounded_decision(self,'command-resolver'", "        try:\n            from .reason_decision_review import VERSION as reason_review_version\n            value=output.bounded_decision(self,'command-resolver'")
s=s.replace("'transition_version':'memory-command-transition-v1'},propose", "'transition_version':'memory-command-transition-v1','reason_review':reason_review_version},propose")
(C/(n+'corrected_memory.py')).write_text(s)
spec=importlib.util.spec_from_file_location('prepare_queries',ROOT/'06_TOOLS/maintenance/prepare_oracle_queries.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder);original=builder.source_queries;builder.ROOT=C;builder.source_queries=lambda:original(C)
sys.argv=['prepare_queries','--report',str(DES/'integrated-native-plans.json')];builder.main()
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 for name in v.get('files',{}):v['files'][name]=sha(C/name)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=C/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(C/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
from genos_codespace_engine_preflight import check
engines,count,errors=check(C);assert not errors,errors
for name in ('memory_methods.py','corrected_memory.py'):ast.parse((C/n/name).read_text())
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
rev=read(can/'candidate.json')['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
pin={'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(DES/'candidate-working.json',{'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in before},'pin':pin})
m=read(ADR/'실험/manifest.json');runner=Path(__file__).with_name('check.py');m['design']['code_isolation']['candidates'].append(dict(pin,candidate_id='working-integration',experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner)));put(ADR/'실험/manifest.json',m)
put(DES/'integration-scope.json',{'own_products':[n+'memory_methods.py',n+'corrected_memory.py'],'base_MAIN':current,'common_reason_review_preserved':True,'current_request_review_is_always_required':True,'engines':engines,'files':count,'errors':errors,'product_changes':[p for p in before if sha(C/p)!=before[p] and not p.startswith('02_BACKEND/ENGINES/') and p not in ('00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py')]})
print('Integration candidate frozen with current MAIN'+str(current['generation'])+' common review preserved; no working/MAIN writes.')
