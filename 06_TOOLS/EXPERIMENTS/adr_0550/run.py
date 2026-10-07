"""Explicit frozen storage candidate runner; never selected by serving."""
import argparse
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'02_BACKEND'))
sys.dont_write_bytecode=True
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0550-navigation-serving-audit-separation'
CANDIDATE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0550/compact/candidate.json'


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module)
    if '.' in name:
        parent,child=name.rsplit('.',1)
        if parent in sys.modules:setattr(sys.modules[parent],child,module)
    return module


def inject():
    manifest=json.loads(CANDIDATE.read_text())
    revision=next(r for r in manifest['revisions'] if r['revision_id']=='rev-002')
    assert manifest['production_loadable'] is False
    for row in revision['files']:
        if sha(ROOT/row['frozen_path'])!=row['snapshot_sha256']:
            raise ValueError('Frozen candidate file changed')
    frozen=CANDIDATE.parent/'revisions/rev-002/snapshot'
    import semantic_runtime
    import lawrag.pipeline
    for name,target in [('semantic_runtime.navigation_storage','02_BACKEND/semantic_runtime/navigation_storage.py'),
                        ('semantic_runtime.term_index','02_BACKEND/semantic_runtime/term_index.py'),
                        ('lawrag.pipeline.term_generation','02_BACKEND/lawrag/pipeline/term_generation.py'),
                        ('lawrag.pipeline.document_release','02_BACKEND/lawrag/pipeline/document_release.py')]:
        load(name,frozen/target)
    return frozen


def fingerprint(db,table):
    info=list(db.execute(f'PRAGMA table_info("{table}")'))
    columns=[r[1] for r in info]
    pk=[r[1] for r in sorted(info,key=lambda r:r[5]) if r[5]]
    order=','.join('"'+name.replace('"','""')+'"' for name in (pk or columns))
    digest=hashlib.sha256();count=0
    for row in db.execute(f'SELECT * FROM "{table}" ORDER BY {order}'):
        encoded=json.dumps(tuple(row),ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        digest.update(len(encoded).to_bytes(8,'big'));digest.update(encoded);count+=1
    return {'rows':count,'ordered_rows_sha256':digest.hexdigest(),'columns':columns}


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['contracts','migrate']);a=p.parse_args()
    frozen=inject()
    if a.mode=='contracts':
        import pytest
        common=load('storage_research_fixtures',ROOT/'05_TESTS/conftest.py')
        class Fixtures:
            @pytest.fixture
            def term_glossary(self,tmp_path):return common.term_glossary.__wrapped__(tmp_path)
        return pytest.main(['-q','-p','no:cacheprovider',str(frozen/'05_TESTS/CONTRACTS/test_navigation_storage.py'),
                           str(ROOT/'05_TESTS/CONTRACTS/test_document_release.py'),
                           str(ROOT/'05_TESTS/CONTRACTS/test_document_release_stages.py'),
                           str(ROOT/'05_TESTS/CONTRACTS/test_term_tools_cache.py'),
                           str(ROOT/'05_TESTS/CONTRACTS/test_fulltext_ranking.py')],plugins=[Fixtures()])
    from semantic_runtime.navigation_storage import compact_generation,AUDIT_TABLES
    dataset=json.loads((ADR/'artifacts/dataset.json').read_text())
    source=ROOT/dataset['generation']
    if sha(source/'manifest.json')!=dataset['generation_manifest_sha256']:
        raise ValueError('Frozen source manifest changed')
    if sha(source/'navigation/navigation.sqlite')!=dataset['navigation_sqlite_sha256']:
        raise ValueError('Frozen source index changed')
    output=ROOT/'01_DATA/TERM/navigation-storage-main-20260929-v1'
    started=time.monotonic()
    print('Deriving frozen selected MAIN; no model calls',flush=True)
    result=compact_generation(source,output)
    new=output/'generation/navigation/navigation.sqlite';old=source/'navigation/navigation.sqlite'
    audit=output/'audit/navigation/navigation.sqlite'
    if sha(audit)!=sha(old):raise ValueError('Audit does not preserve the entire original index')
    rows={}
    with closing(sqlite3.connect(old.as_uri()+'?mode=ro',uri=True)) as baseline, closing(sqlite3.connect(new.as_uri()+'?mode=ro',uri=True)) as candidate:
        tables={r[0] for r in baseline.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        retained=tables-set(AUDIT_TABLES)
        actual={r[0] for r in candidate.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if actual!=retained:raise ValueError('Runtime table set changed')
        for table in sorted(retained):
            print('Checking all rows:',table,flush=True)
            before=fingerprint(baseline,table);after=fingerprint(candidate,table)
            if before!=after:raise ValueError('Runtime row difference: '+table)
            rows[table]=before
        for table in sorted(retained):
            before=list(baseline.execute("SELECT type,name,sql FROM sqlite_master WHERE tbl_name=? ORDER BY type,name",(table,)))
            after=list(candidate.execute("SELECT type,name,sql FROM sqlite_master WHERE tbl_name=? ORDER BY type,name",(table,)))
            if before!=after:raise ValueError('Runtime schema/index difference: '+table)
    payloads={}
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.suffix=='.json' or path.name=='navigation.sqlite':continue
        relative=path.relative_to(source);target=output/'generation'/relative
        # Exact hardlink identity proves unchanged payload bytes without repeated 14GB glossary hashing.
        if path.stat().st_ino==target.stat().st_ino and path.stat().st_dev==target.stat().st_dev:
            payloads[str(relative)]='same-immutable-inode'
        elif sha(path)==sha(target):payloads[str(relative)]='sha256-equal'
        else:raise ValueError('Source/glossary/fulltext payload changed: '+str(relative))
    reduction=1-new.stat().st_size/old.stat().st_size
    receipt={'schema_version':'navigation-storage-exhaustive-validation-v1',
             'structural_checks_passed':True,'source_generation':str(source.relative_to(ROOT)),
             'new_generation':str((output/'generation').relative_to(ROOT)),
             'dataset_sha256':sha(ADR/'artifacts/dataset.json'),
             'runtime_tables':rows,'runtime_schema_indexes_equal':True,
             'all_original_audit_bytes_preserved':True,'audit_sha256':sha(audit),
             'payloads':payloads,'baseline_navigation_bytes':old.stat().st_size,
             'candidate_navigation_bytes':new.stat().st_size,'serving_reduction_fraction':reduction,
             'elapsed_seconds':round(time.monotonic()-started,3),'llm_calls':0,
             'request_latency_measured':False,'legal_answer_quality_measured':False,
             'baseline_generation_unchanged':sha(source/'manifest.json')==dataset['generation_manifest_sha256'],
             'candidate_result_sha256':sha(output/'result.json')}
    if reduction<0.65:raise ValueError('Serving bytes reduction below frozen criterion')
    run=ADR/'artifacts/run-001';run.mkdir(exist_ok=True)
    with (run/'result.json').open('x') as stream:json.dump(receipt,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['runtime_tables','payloads']},ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
