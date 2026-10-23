"""Correct offline case join label; preserve original ledger and all measurements."""
from common import *
import shutil
p=ART/'retrieval-ledger.json'; backup=ART/'retrieval-ledger-original-label.json'
assert not backup.exists()
shutil.copyfile(p,backup)
m=read(ADR/'실험/manifest.json'); actual=m['questions'][0]['case_id']
ledger=read(p);changes=[]
for run in ledger['runs']:
    for arm in run['arms']:
        for case in arm['cases']:
            assert case['case_id']=='known-query'
            changes.append({'run':run['run_id'],'arm':arm['arm_id'],'from':case['case_id'],'to':actual})
            case['case_id']=actual
save(p,ledger)
m['retrieval_accounting']['stage_ledger']['sha256']=sha(p)
save(ADR/'실험/manifest.json',m)
save(ART/'offline-report-repairs.json',{
    'case_mapping':changes,'original_ledger_sha256':sha(backup),'mapped_ledger_sha256':sha(p),
    'reason':'Frozen analyzer inherited known-query label; sole frozen question is public-capital-gains. Values, source coordinates, criteria and counts unchanged.',
    'judgment_auditor':'Raw projected singleton IDs can be absent; final coverage is measured from canonical validated receipt instead. No evaluation criterion change.',
    'model_calls_added':0,'product_changes':0})
print('Mapped only case label:',changes)
