"""Pin both common-schema control and merged integrated arm before live calls."""
import json
import subprocess
from harness import R,A,sha,write

def main():
    m=json.loads((A/'실험/manifest.json').read_text());candidates=[]
    for arm in ['baseline','integrated']:
        c=R/f'02_BACKEND/lawrag/research/candidates/adr_0575/{arm}'
        subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(c.relative_to(R))],check=True)
        subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','validate',str(c.relative_to(R))],check=True)
        cm=json.loads((c/'candidate.json').read_text());rev=cm['revisions'][-1]
        candidates.append({'candidate_id':arm,'experiment_id':m['experiment_id'],'arm_id':'integrated','run_ids':['run-001'],
          'manifest_path':str((c/'candidate.json').relative_to(R)),'manifest_sha256':sha(c/'candidate.json'),
          'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
          'runner_path':'06_TOOLS/EXPERIMENTS/adr_0575/run.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0575/run.py')})
    m['design']['code_isolation']['candidates']=candidates
    files=list((R/'02_BACKEND/semantic_runtime').rglob('*.py'))+list((R/'02_BACKEND/semantic_runtime/legal_agent').glob('*.sql'))
    files += [R/'00_SYSTEM/PIPELINE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',
      R/'02_BACKEND/lawrag/research/experiment_client.py',R/'02_BACKEND/lawrag/research/openrouter_legal_adapter.py',
      R/'02_BACKEND/lawrag/pipeline/term_generation.py',R/'05_TESTS/conftest.py',R/'05_TESTS/CONTRACTS/test_legal_agent_double_harness.py',
      R/'05_TESTS/CONTRACTS/test_document_release.py',R/'05_TESTS/CONTRACTS/test_bounded_source_main.py',R/'05_TESTS/CONTRACTS/test_legal_agent_v5.py']
    files+=list((R/'06_TOOLS/EXPERIMENTS/adr_0575').glob('*.py'))+list((A/'artifacts/design').glob('*.json'))
    for arm in ['baseline','integrated']:
        c=R/f'02_BACKEND/lawrag/research/candidates/adr_0575/{arm}'
        cm=json.loads((c/'candidate.json').read_text());files+=[c/'candidate.json']+[R/f['frozen_path'] for f in cm['revisions'][-1]['files']]
    m['design']['frozen_inputs']={str(p.relative_to(R)):sha(p) for p in files}
    m['design']['baseline_binding']={'active_pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'source':'frozen active generation31 synthetic original design, native full API with common schema visibility'}
    write(A/'실험/manifest.json',m)
    print('Both arms, code and new holdout frozen')

if __name__=='__main__':main()
