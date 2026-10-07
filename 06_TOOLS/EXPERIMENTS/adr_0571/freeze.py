"""Pin candidate and the complete upstream execution path before model calls."""
import json
import subprocess
from harness import R,A,C,sha,write

def main():
    subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),'adr_candidate.py','freeze',str(C.relative_to(R))],check=True)
    subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),'adr_candidate.py','validate',str(C.relative_to(R))],check=True)
    m=json.loads((A/'실험/manifest.json').read_text());cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1]
    m['design']['code_isolation']['candidates']=[{'candidate_id':'integrated','experiment_id':m['experiment_id'],'arm_id':'integrated','run_ids':['run-001'],
        'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
        'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0571/run.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0571/run.py')}]
    for arm in m['design']['arms']:
        arm['changes']='Native selected working baseline, same source data and transport' if arm['id']=='baseline' else 'Compact concept IDs, generic memory scopes, full-content small-pool selection, native demand-plan reuse, offline generation and status'
        arm['controls']='Same synthetic originals, HTTP endpoint, native coordinator/publication, Gemma/ParasailFP8/thinking off, no repairs/retries; source/demand/citation validation retained; rotated paired order'
    expected={'required':{'H01':[{'doc_id':'d','node':0},{'doc_id':'d','node':1}],
        'H02':[{'doc_id':'d','node':0},{'doc_id':'d','node':1}],
        'H03':[{'doc_id':'d','node':0}],
        'H04':[{'doc_id':'d','node':0},{'doc_id':'d','node':1}]},
        'terms':{'H01':['승인','위임'],'H02':['승인','위임'],'H03':['승인'],'H04':['승인','예외']},
        'meaning':'Exact synthetic required original/citation/term contract; not legal quality certification'}
    write(A/'artifacts/design/expected-offline.json',expected)
    files=list((R/'02_BACKEND/semantic_runtime').rglob('*.py'))+list((R/'02_BACKEND/semantic_runtime/legal_agent').glob('*.sql'))
    files+=[R/'00_SYSTEM/PIPELINE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',
        R/'02_BACKEND/lawrag/research/experiment_client.py',R/'02_BACKEND/lawrag/research/openrouter_legal_adapter.py',
        R/'02_BACKEND/lawrag/pipeline/term_generation.py',R/'05_TESTS/conftest.py',R/'05_TESTS/CONTRACTS/test_legal_agent_double_harness.py',R/'05_TESTS/CONTRACTS/test_document_release.py',R/'05_TESTS/CONTRACTS/test_bounded_source_main.py',R/'05_TESTS/CONTRACTS/test_legal_agent_v5.py']
    files+=list((R/'06_TOOLS/EXPERIMENTS/adr_0571').glob('*.py'))+list((A/'artifacts/design').glob('*.json'))
    files+=[C/'candidate.json']+[R/f['frozen_path'] for f in rev['files']]
    m['design']['frozen_inputs']={str(p.relative_to(R)):sha(p) for p in files}
    m['design']['baseline_binding']={'active_pointer':json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text()),'execution':'Explicit canonical v5 API, unchanged native code hashes; working five native modules match selected generation31; upstream fixtures/build pinned; not current mutable pointer lookup during run'}
    m['design']['generation_roundtrip']={'input':'Four live integrated native journals plus one native synthetic scripted journal with complete irrelevant performance original','questions':['이사회 승인 원칙과 위임 예외를 확인해 주세요.','적법하게 권한을 위임한 경우 이사회 승인이 필요한지 원칙과 예외를 확인해 주세요.'],
        'originals':'Synthetic three source units: principle, delegation exception, pure approval-count table; no private data','calls':'one Gemma consolidation batch then one live complete native API follow-up; no hand-curated concept IDs'}
    write(A/'실험/manifest.json',m);print('candidate, complete upstream path, holdout rubric and generation roundtrip frozen')

if __name__=='__main__':main()
