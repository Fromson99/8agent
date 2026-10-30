"""Freeze test-only dependency closure; preserve selected serving modules."""
from pathlib import Path
import ast,json,shutil,sys
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=R/'02_BACKEND/lawrag/research/candidates/adr_1100/ontology-r1';S=C/'snapshot'
OLD=R/'02_BACKEND/lawrag/research/candidates/adr_1098/direct-r1/revisions/rev-001/snapshot';D=Path(__file__).parent
known={r['target_path'] for r in json.loads((C/'candidate.json').read_text())['files']}
support=[]
def copy(p,n):
 target=S/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
 if n not in known:ac.register_file(C,n,upstream_state='present' if (R/n).exists() else 'absent');known.add(n)
 support.append(n)
for p in (OLD/'02_BACKEND/lawrag').rglob('*.py'):
 n=str(p.relative_to(OLD))
 if not (S/n).exists():copy(R/n if (R/n).is_file() else p,n)
# Current common experiment client is a runner dependency, never an alternate serving implementation.
copy(R/'02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/experiment_client.py')
queue=['conftest','test_ontology_context','test_ontology_compiler','test_read_judgment_api','test_compact_model_input','test_compact_wire_binding','test_journal_evidence_batch'];seen=set()
for test in list(queue):pass
while queue:
 name=queue.pop(0)
 if name in seen:continue
 seen.add(name);n='05_TESTS/'+('' if name=='conftest' else 'CONTRACTS/')+name+'.py'
 p=R/n if (R/n).is_file() else OLD/n
 if not p.is_file():raise RuntimeError(n)
 copy(p,n)
 for node in ast.walk(ast.parse(p.read_text())):
  if isinstance(node,ast.ImportFrom) and node.module and node.module.startswith('test_'):queue.append(node.module.split('.')[0])
  elif isinstance(node,ast.Import):queue.extend(x.name for x in node.names if x.name.startswith('test_'))
# Direct unit tests use inherited real reader fixtures, retaining omission/hash/permission coverage.
s=(R/'06_TOOLS/EXPERIMENTS/adr_1098/test_direct.py').read_text();s=s[:s.index('def test_compact_keeps_only_schema_selectable_pending_source_identity')]
s=s.replace('execution_review=True','completion_contract=True')
(D/'test_projection.py').write_text(s)
p=S/'02_BACKEND/semantic_runtime/legal_agent/law_navigation.py';s=p.read_text()
needle="            self.p['window']='references';self.p['window_groups']=list(dict.fromkeys(self.p.get('window_groups',[])+new_groups))"
assert s.count(needle)==1;s=s.replace(needle,"            if model_selected and new_groups:\n                from .ontology_context import acquire as acquire_ontology\n                new_groups.extend(acquire_ontology(self,list(new_groups)))\n"+needle)
needle="                if self.modern and (accepted['decision']['next_action']=='READ_ARTICLES' or"
assert s.count(needle)==1;s=s.replace(needle,"                ontology_read=(self.policy.get('ontology_context',{}).get('mode','A0')!='A0' and accepted['decision']['next_action'] in ('READ_PARENT','READ_SCOPE','FOLLOW_CONNECTION'))\n                if self.modern and (ontology_read or accepted['decision']['next_action']=='READ_ARTICLES' or")
p.write_text(s)
(R/'04_EXPERIMENTS/ADR/ADR-1100-main106-ontology-direct/artifacts/support-inventory.json').write_text(json.dumps({'test_only_files':support,'tests':sorted(seen)},ensure_ascii=False,indent=2)+'\n')
print('support',len(support),'test helper files',len(seen))
