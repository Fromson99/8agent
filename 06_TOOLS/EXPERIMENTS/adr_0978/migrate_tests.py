"""Update explicit old fixture contracts; preserve original failure logs."""
from common import *
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
s=read(ART/'stage.json');D=ROOT/s['candidate_dir'];C=D/'snapshot'
for name in ('test_source_span_norm','test_assessment_gap_action','test_law_name_recovery'):
 rel=f'05_TESTS/CONTRACTS/{name}.py';p=C/rel
 shutil.copyfile(ROOT/rel,p);ac.register_file(D,rel,upstream_state='present')
 s['working_baseline'][rel]=sha(ROOT/rel)
 t=p.read_text().replace("'team_id': 't'", "'team_id': 'test_team'").replace("'team_id':'t'", "'team_id':'test_team'")
 if name=='test_source_span_norm':
  t=t.replace('def test_exact_duplicate_source_role_is_written_once():','def test_shared_source_role_does_not_prove_semantic_duplication():')
  t=t.replace("    with pytest.raises(ProposalError, match='Repeated source clause'):\n        accepted(p, [{'id': 'S1', 'source_id': 's', 'text': '신고할 수 있다.'}])", "    assert len(accepted(p, [{'id': 'S1', 'source_id': 's', 'text': '신고할 수 있다.'}])['claims']) == 2")
 elif name=='test_assessment_gap_action':
  t=t.replace("assert gap['material'] == (material or kind != 'UNRESOLVED_REFERENCE')", "assert gap['material'] == ((material or kind != 'UNRESOLVED_REFERENCE') if impl is v5 else material)")
  t=t.replace("['unknown_ref', 'reversed_text', 'invented_fact']", "['unknown_ref', 'invented_fact']")
  t=t.replace("'completion_contract': True, 'completion_policy_version': cc.V8, 'compact_input': True,", "'completion_contract': True, 'completion_policy_version': cc.V8, 'compact_input': True, 'answer_first': True,")
 elif name=='test_law_name_recovery':
  t=t.replace("    assert 'law_name_recovery' not in qs.catalogue(inv.s, queries=[query])", "    page=qs.catalogue(inv.s, queries=[query])\n    if query == '제99조':\n        assert 'law_name_recovery' not in page\n    else:\n        clue=page['law_name_recovery']\n        assert clue['structure_filter'] is None and clue['requires_structure_decision']\n        assert clue['original_queries'] == [query]")
 p.write_text(t)
save(ART/'stage.json',s)
save(ART/'test-migrations.json',{'historical_failures':'../ADR-0977-unified-scope-semantic-authority/artifacts/contracts-audit-2.xml',
 'changes':['Team t is invalid under existing MAIN99 identity contract; use test_team.',
 'Source interpretation is model authored, exact original receipts remain separate. Reversed authored text test contradicted existing authored_interpretation test even before this change; private refs and invented facts remain rejected.',
 'Modern materiality and repeated source norms preserve model judgment; legacy v5 expectations unchanged.',
 'Multi-coordinate name recovery exposes unresolved clues without manufacturing a coordinate.',
 'Enable answer_first explicitly in gap native API regression to cover prior premature handoff.']})
