from pathlib import Path
import json,sys,ast,inspect,tempfile
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1250-main129-oracle-live-retest';D=A/'artifacts/design';O=A/'artifacts/run-001';b=json.loads((D/'before.json').read_text())['binding'];sys.path[:0]=[str(R/b['engine_root']/'02_BACKEND'),str(Path(__file__).parent)]
from safety import SharedBudget
from semantic_runtime.oracle_dp_io import BudgetPause
from semantic_runtime.legal_agent.errors import TransportError
entry=R/json.loads((D/'candidate.json').read_text())['entry'];tree=ast.parse(entry.read_text());rows=[]
for node in ast.walk(tree):
 if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='TransportError':assert 'code' not in {k.arg for k in node.keywords}
rows.append('transport_supported_signature')
x=TransportError('synthetic deadline',retryable=False,unknown=True);x.http_status=504;assert x.unknown and not x.retryable and x.http_status==504;rows.append('deadline_type_and_unknown_preserved')
s=SharedBudget(3,initial_calls=1);s.reserve('agent');s.reserve('source')
try:s.reserve('agent');raise AssertionError('limit ignored')
except BudgetPause:pass
assert s.calls==3 and s.by_port=={'source':2,'agent':1};rows.append('single_source_record_sql_budget')
assert 'faulthandler.enable' in entry.read_text() and 'os.fsync(resource_log.fileno())' in entry.read_text();rows.append('crash_and_resource_checkpoints')
from semantic_runtime.legal_agent import provider_routing as routing
policy=json.loads((R/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json').read_text());routing.validate_policy(policy);rows.append('native_provider_policy_valid')
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
write_summary(O/'checks.json',{'passed':len(rows),'failed':0,'checks':rows,'model_calls':0});print('Checks',len(rows),'PASS; model0')
