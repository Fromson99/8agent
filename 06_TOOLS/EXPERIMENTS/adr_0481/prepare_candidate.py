"""Copy ADR-0480 frozen candidate and build separated hard-10 fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0481-reviewed-links-hard10'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0481/hard10-reviewed-links'
OLD = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0480/explicit-link'
SOURCE = ROOT / '04_EXPERIMENTS/ADR/ADR-0474-double-harness-live-quality-probe/artifacts/frozen-inputs.json'
BASE_FIXTURE = ROOT / '04_EXPERIMENTS/ADR/ADR-0475-source-first-double-harness-wiring/fixture.json'
CASES = ['cm-003','cm-008','cm-012','cm-014','cm-018','cm-024','cm-030','cm-033','cm-038','cm-045']

def tool(*args):
    subprocess.run([str(ROOT/'.venv/bin/python'), str(ROOT/'06_TOOLS/run_tool.py'),
                    'adr_candidate.py', *args], cwd=ROOT, check=True)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

def main():
    parent = json.loads((OLD/'candidate.json').read_text())
    rev = next(r for r in parent['revisions'] if r['revision_id']=='rev-002')
    by_snapshot = {r['snapshot_path']:r for r in parent['files']}
    rows=[]
    for frozen in rev['files']:
        source=ROOT/frozen['frozen_path']
        assert sha(source)==frozen['snapshot_sha256']
        meta=by_snapshot[frozen['snapshot_path']]
        rows.append({**frozen,'target_path':meta['target_path']})
    present=[r for r in rows if (ROOT/r['target_path']).is_file()]
    absent=[r for r in rows if not (ROOT/r['target_path']).is_file()]
    args=['snapshot','--adr',str(ADR),'--candidate-id','hard10-reviewed-links',
          '--experiment-id','ADR-0481-experiment-v1','--arm-id','reviewed-links','--run-id','run-001']
    for row in present:
        args += ['--source',row['target_path']]
    tool(*args)
    for row in rows:
        dest=CAND/'snapshot'/row['target_path'];dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/row['frozen_path'],dest)
    for row in absent:
        tool('register',str(CAND),'--target',row['target_path'],'--upstream-state','absent')

    frozen=json.loads(SOURCE.read_text()); base=json.loads(BASE_FIXTURE.read_text())
    chosen={c['case_id']:c for c in frozen['cases'] if c['case_id'] in CASES}
    assert sorted(chosen)==sorted(CASES)
    product={'schema_version':'cm-hard10-reviewed-links-product-v1',
             'generation':base['generation'],
             'public_scope_document_ids':base['public_scope_document_ids'],
             'cases':[{'case_id':cid,'question':chosen[cid]['question'],
                       'reviewed_relation_source_ids':chosen[cid]['decisive_source_ids']}
                      for cid in CASES]}
    gold={'schema_version':'cm-hard10-gold-v1',
          'source_path':str(SOURCE.relative_to(ROOT)),'source_sha256':sha(SOURCE),
          'cases':[{'case_id':cid,'reference_answer':chosen[cid]['reference_answer'],
                    'decisive_source_ids':chosen[cid]['decisive_source_ids']}
                   for cid in CASES]}
    write(ADR/'product-cases.json',product);write(ADR/'gold-cases.json',gold)
    print(json.dumps({'candidate_files':len(rows),'cases':CASES},ensure_ascii=False))

if __name__=='__main__':main()
