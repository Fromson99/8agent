import sys,json,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
A=ROOT/'04_EXPERIMENTS/ADR/ADR-1086-compact-wire-binding';old=ROOT/'04_EXPERIMENTS/ADR/ADR-1085-compact-agent-input-sql'
f=json.loads((old/'artifacts/design/freeze.json').read_text());base=ROOT/f['code_root']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria={'parent':'ADR1085 complete rejected compact rev002','changes':'Bind schema selection references in canonical saved view, independently rebuild identical pure projection in repository before reserving attempt; preserve exact equality and all receipts','success':['All18pager contracts and9API contracts including repair/resume; tampered body/mapping/marker rejected before transport','Input50percent reduction unchanged; no new corpus SQL; request evidence batch1SELECT','Record unchanged-working regression baseline; candidate cannot add failures','Single public fsc-hard-005 after contract pass only,40calls/1024tools/1800seconds,nulloutputcap,strict Qwen Parasail,no rerun; noMAIN quality claim from knownprobe'],'limits':{'rss_gib':4,'available_gib':3,'disk_gib':20,'swap_gib':0.5},'failure':'No source/wire/hash validator bypass. Preserve failed records, stop live on integrity or provider error.'}
put(A/'artifacts/design/criteria.json',criteria)
existing=[n for n in f['files'] if (ROOT/n).is_file()]
C=ac.snapshot(A,'compact-r1',existing,experiment_id='ADR-1086-experiment-v1',arm_id='compact',run_ids=['run-001']);S=C/'snapshot'
for n in f['files']:
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(base/n,p)
 if n not in existing:ac.register_file(C,n,upstream_state='absent')
def edit(name,old,new):
 p=S/'02_BACKEND/semantic_runtime/legal_agent'/name;s=p.read_text();assert s.count(old)==1,(name,s.count(old));p.write_text(s.replace(old,new))
edit('compact_model_input.py',"'catalogue', 'domain_choice'", "'minimal_input_binding', 'catalogue', 'domain_choice'")
edit('compact_model_input.py','def project(wire_view, schema):',"def bind(data, schema):\n    return {**data, 'minimal_input_binding': {'version': VERSION, 'selection_refs': sorted(_enum_strings(schema))}}\n\n\ndef project(wire_view, schema=None):")
edit('compact_model_input.py','        needed = _enum_strings(schema) - current',"        binding = view.get('minimal_input_binding')\n        needed = (set(binding['selection_refs']) if binding is not None else _enum_strings(schema or {})) - current")
edit('bounded_source_session.py',"        view = self.work.save_view(native_phase, {**data, 'source_stage': phase, **({'budget_class':budget_class} if completion else {})}, evidence_ids)","        from . import compact_model_input as minimal\n        data = {**data, 'source_stage': phase}\n        if minimal.applies(self.profile, data):\n            data = minimal.bind(data, schema)\n        view = self.work.save_view(native_phase, {**data, **({'budget_class':budget_class} if completion else {})}, evidence_ids)")
edit('gateway.py',"            if self.compact:\n                numbered_args['wire_projection'] = WIRE_PROJECTION", "            if self.compact:\n                numbered_args['wire_projection'] = WIRE_PROJECTION\n            from . import compact_model_input as minimal\n            if minimal.applies(self.profile, view):\n                if view.get('minimal_input_binding') != minimal.bind({}, self.protocol.schema(schema_name))['minimal_input_binding']:\n                    raise ContractError('minimal input schema binding differs from canonical view')\n                numbered_args['minimal_input_projection'] = minimal.VERSION")
edit('relations_repository.py','numbered_references=None, wire_projection=None):','numbered_references=None, wire_projection=None, minimal_input_projection=None):')
edit('relations_repository.py',"        if wire != expected or view != stored:","        if minimal_input_projection is not None:\n            from . import compact_model_input as minimal\n            binding = stored.get('minimal_input_binding')\n            if (self.VERSION != 6 or wire_projection is None or minimal_input_projection != minimal.VERSION\n                    or not isinstance(binding, dict) or set(binding) != {'version', 'selection_refs'}\n                    or binding['version'] != minimal.VERSION or not isinstance(binding['selection_refs'], list)\n                    or any(not isinstance(r, str) for r in binding['selection_refs'])\n                    or not minimal.applies({'candidate_navigation': {'minimal_input': True}}, stored)):\n                raise ContractError('unsupported minimal input binding')\n            expected = minimal.project(expected)\n        if wire != expected or view != stored:")
edit('relations_repository.py',"            return ident\n\n    def item_visible", "            if minimal_input_projection is not None:\n                self.event('MINIMAL_INPUT_PROJECTION', {'attempt_id': ident, 'projection': minimal_input_projection,\n                    'stored_view_hash': digest(stored), 'wire_view_hash': digest(wire),\n                    'selection_refs_hash': digest(binding['selection_refs'])})\n            return ident\n\n    def item_visible")
# Refresh only changed dependencies, adding the two new modules.
p=S/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
for ref in v['engines'].values():
 ep=S/ref['manifest'];e=json.loads(ep.read_text())
 if '02_BACKEND/semantic_runtime/legal_agent/decision_projection.py' not in e['files']:continue
 for n in e['files']:
  if (S/n).is_file():e['files'][n]=sha(S/n)
 put(ep,e);ref['sha256']=sha(ep)
put(p,v);ac.freeze(C);cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(A/'artifacts/design/freeze.json',{'code_root':str(code.relative_to(ROOT)),'binding':binding,'files':{n:sha(code/n) for n in f['files']},'baseline_root':str((base.parents[1]/'rev-001/snapshot').relative_to(ROOT))})
m=json.loads((A/'실험/manifest.json').read_text());m['design'].update(hypothesis=criteria['changes'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],primary_metric='Exact independent stored/wire reconstruction; paging/SQL/API contracts',criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id=C.name,arm_id='compact',experiment_id=m['experiment_id'],run_ids=['run-001'],runner_path='06_TOOLS/EXPERIMENTS/adr_1086/contracts.py',runner_sha256=sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1086/contracts.py'))])
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['compact'],'status':'planned','selection_rule':'Predetermined18pager+9API and exact wire tamper contracts, known prior failures baseline separated','artifact_path':str((A/'artifacts/run-001/result.json').relative_to(ROOT)),'sha256':'PENDING'}]
m['dataset'].update(name='Frozen synthetic compact wire contracts',version='v1',frozen_source=str((A/'artifacts/design/criteria.json').relative_to(ROOT)),sha256=sha(A/'artifacts/design/criteria.json'),legal_version_checked=False,reference_version_checked=False)
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Initial synthetic contracts only; live stage is separately frozen before any product call.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason=m['retrieval_accounting']['not_applicable_reason'])
put(A/'실험/manifest.json',m)
print(code)
