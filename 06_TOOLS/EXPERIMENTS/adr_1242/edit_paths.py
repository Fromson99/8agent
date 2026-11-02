"""Patch only the isolated candidate's explicit runtime consumers."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1242/oracle-records/snapshot'
names='''service.py
02_BACKEND/semantic_runtime/app.py
02_BACKEND/semantic_runtime/contracts.py
02_BACKEND/semantic_runtime/feedback.py
02_BACKEND/semantic_runtime/legal_agent_adapter.py
02_BACKEND/semantic_runtime/legal_agent/repository.py
02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py
02_BACKEND/semantic_runtime/legal_agent/case_repository.py
02_BACKEND/semantic_runtime/legal_agent/shortcut_repository.py
02_BACKEND/semantic_runtime/legal_agent/shortcut_cases.py
02_BACKEND/semantic_runtime/legal_agent/shortcut_store.py
02_BACKEND/semantic_runtime/legal_agent/publication.py
02_BACKEND/semantic_runtime/legal_agent/unified_runtime.py
02_BACKEND/semantic_runtime/legal_agent/unified_publication.py
02_BACKEND/semantic_runtime/legal_agent/deferred_publication.py
02_BACKEND/semantic_runtime/legal_agent/completion_budget.py
02_BACKEND/semantic_runtime/legal_agent/workflow_execution.py
02_BACKEND/semantic_runtime/legal_agent/storage_admission.py
02_BACKEND/semantic_runtime/legal_agent/source_handoff.py
02_BACKEND/semantic_runtime/legal_agent/successful_answer.py
02_BACKEND/semantic_runtime/workflow_bridge.py
02_BACKEND/semantic_runtime/workflow_rag.py
02_BACKEND/semantic_runtime/request_journals.py
02_BACKEND/semantic_runtime/progress.py
02_BACKEND/semantic_runtime/request_report.py
02_BACKEND/semantic_runtime/request_summary.py
02_BACKEND/semantic_runtime/process_trace.py
02_BACKEND/semantic_runtime/session_identity.py
02_BACKEND/semantic_runtime/ad_mode.py
02_BACKEND/semantic_runtime/ad_request_report.py
02_BACKEND/semantic_runtime/ad_store.py
02_BACKEND/semantic_runtime/action_memory_store.py
02_BACKEND/semantic_runtime/task_policy.py
02_BACKEND/semantic_runtime/relation_issues.py
02_BACKEND/semantic_runtime/learning_store.py
02_BACKEND/semantic_runtime/reference_resolution_repository.py
02_BACKEND/semantic_runtime/state_sqlite.py
02_BACKEND/semantic_runtime/ontology_work/domain_cli.py
02_BACKEND/workflow/repository.py'''.splitlines()
changed=[]
for name in names:
 p=C/name
 if not p.is_file():
  # Some non-serving authoring helpers are not in the selected release inventory.
  # They are copied/registered separately only if a live consumer actually needs them.
  print('not in selected serving snapshot:',name);continue
 t=p.read_text();old=t
 if name=='service.py' or name.startswith('02_BACKEND/workflow/'):
  prefix='semantic_runtime.';module='from semantic_runtime import runtime_sqlite as sqlite3'
 elif '/legal_agent/' in name or '/ontology_work/' in name:
  prefix='..';module='from .. import runtime_sqlite as sqlite3'
 else:
  prefix='.';module='from . import runtime_sqlite as sqlite3'
 t=t.replace('from pathlib import Path',f'from {prefix}oracle_runtime_paths import Path')
 t=t.replace('import sqlite3\n',module+'\n')
 if t!=old:p.write_text(t);changed.append(name)
print('Explicit path/connection consumer patches:',len(changed))
