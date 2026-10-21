from pathlib import Path
import importlib.util
from types import SimpleNamespace
from copy import deepcopy
import pytest
from semantic_runtime.legal_agent.errors import ProposalError
from semantic_runtime.legal_agent import request_repair as rr
p=Path(__file__).resolve().parents[1]/'adr_0870/test_contracts.py'
spec=importlib.util.spec_from_file_location('recorded0870',p);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
@pytest.mark.parametrize('run,call,record,raw',old.rows,ids=[f'{r}-{c}' for r,c,_,_ in old.rows])
def test_recorded_proposal_runtime_and_wire_agree(run,call,record,raw):
 if run=='run-001' and call in (13,14):
  # Those original v8 proposals were shape-valid but never valid completion
  # proofs: both attach evidence to an explicitly unresolved/unneeded gap.
  assert record['view']['completion_contract']=='investigation-completion-v8'
  row=deepcopy(raw['gap_resolutions'][0]);assert row['status'] in ('NOT_NEEDED','UNRESOLVED')
  assert row['basis_refs'] and row['action_refs']
  row['gap_id']='g';inv=SimpleNamespace(p={},current_gap_round=lambda:{'action_receipts':[]})
  with pytest.raises(ProposalError):rr.validate_resolutions(inv,{'gap_resolutions':[row]},{'assessment_gaps':[{'gap_id':'g'}]})
  with pytest.raises(ProposalError):old.test_recorded_navigation_boundary(run,call,record,raw)
 else:old.test_recorded_navigation_boundary(run,call,record,raw)
