"""Finish only a fully inserted, pinned unit FTS after process interruption.

This does not regenerate tokens or accept a partial insertion. All canonical
source rows are compared before optimization. The original database is archived,
and the final manifest discloses this recovery implementation and receipt.
"""
from pathlib import Path
import fcntl,gzip,hashlib,json,os,shutil,sqlite3,sys,time
R=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(R/'02_BACKEND'))
from semantic_runtime import unit_fulltext,fulltext
from lawrag.pipeline.generation_build_steps import Stages
from semantic_runtime.contracts import sha
A=R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow/artifacts'
P=R/'01_DATA/TERM_RELEASES/risk-compare-docx-20261015-r1-index'
B=P/'serving/.baseline.building';G=B/'generation';N=G/'navigation';F=G/'fulltext'
O=A/'data-recovery';O.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def recover():
    assert not (F/'manifest.json').exists() and not (B/'checkpoints/fulltext.json').exists()
    assert not (P/'serving/baseline').exists()
    identity=read(B/'checkpoints/identity.json')
    execution=read(R/'01_DATA/LOGS/risk-compare-docx-20261015-r1-index/reindex-main/execution-code.json')
    assert all(sha(R/v['path'])==v['sha256'] for v in execution['files'])
    assert identity['unit_fulltext_builder_sha256']==sha(Path(unit_fulltext.__file__))
    assert identity['fulltext_builder_sha256']==sha(Path(fulltext.__file__))
    for name in ('source','glossary','navigation','links'):
        row=read(B/'checkpoints'/f'{name}.json')
        assert all(sha(B/n)==h for n,h in row['files'].items()),name
    sm=read(G/'manifest.json');nm=read(N/'manifest.json')
    pins={str(p.relative_to(R)):sha(p) for p in (G/'manifest.json',G/'store.sqlite',N/'manifest.json',N/'navigation.sqlite')}
    assert sha(G/'store.sqlite')==sm['store_sha256']==nm['source_store_sha256']
    assert nm['generation_id']==sm['generation_id']
    assert sha(N/'navigation.sqlite')==nm['index_sha256']
    before=sha(F/'units.sqlite');archive=O/'units-before.sqlite.gz'
    assert not archive.exists()
    with (F/'units.sqlite').open('rb') as source,gzip.open(archive,'wb',compresslevel=1) as target:
        shutil.copyfileobj(source,target)
    with gzip.open(archive,'rb') as source:
        h=hashlib.sha256()
        while part:=source.read(1024*1024):h.update(part)
    assert h.hexdigest()==before
    started=time.monotonic()
    with sqlite3.connect('file:'+str(G/'store.sqlite')+'?mode=ro',uri=True) as sd,sqlite3.connect('file:'+str(N/'navigation.sqlite')+'?mode=ro',uri=True) as nd,sqlite3.connect(F/'units.sqlite') as db:
        scope=set(identity['scope']['document_version_ids'])
        assert scope=={r[0] for r in sd.execute('SELECT document_id FROM document')}
        total=sum(sd.execute('SELECT count(*) FROM (SELECT unit_id,CASE WHEN unit_id IS NULL THEN block_id END FROM source_block WHERE document_id=? GROUP BY 1,2)',(did,)).fetchone()[0] for did in scope)
        assert total==255878
        assert db.execute('SELECT count(*) FROM unit').fetchone()[0]==total
        assert db.execute('SELECT count(*) FROM unit_fts').fetchone()[0]==total
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT count(*) FROM unit u LEFT JOIN unit_fts f ON f.rowid=u.rowid WHERE f.key IS NULL OR f.key!=u.key').fetchone()[0]==0
        stats={'sources':set(),'blocks':0,'navigation_blocks':0}
        stored=iter(db.execute('SELECT key,source_id,document_id,json FROM unit ORDER BY rowid'))
        count=0
        for row in unit_fulltext._entries(sd,nd,scope,stats):
            key,sid,did,raw=next(stored)
            assert (key,sid,did)==(row['key'],row['source_id'],row['document_id'])
            assert json.loads(raw)==row
            count+=1
            if count%20000==0:print('RECOVERY canonical_source_rows_verified',count,total,flush=True)
        assert count==total and next(stored,None) is None
        # Only the two remaining canonical SQL finalization operations are run.
        db.execute("INSERT INTO unit_fts(unit_fts) VALUES('optimize')");db.commit()
        db.execute("INSERT INTO unit_fts(unit_fts) VALUES('integrity-check')");db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        result={'schema_version':unit_fulltext.SCHEMA,'generation_id':sm['generation_id'],
            'source_store_sha256':sm['store_sha256'],'navigation_index_sha256':nm['index_sha256'],
            'tokenizer':{'name':'pecab','version':fulltext.tokenizer_version(),'tags':list(fulltext.TAGS)},
            'ranking':{'query':'OR','body_only':True,'heading_indexed':False},
            'scope':{'document_version_ids':sorted(scope),'source_ids':sorted(stats['sources'])},
            'counts':{'unit':count,'source':len(stats['sources']),'covered_blocks':stats['blocks'],'navigation_blocks':stats['navigation_blocks']},
            'granularity':'stored-own-block-owner','descendant_text_included':False,
            'source_manifest_sha256':pins[str((G/'manifest.json').relative_to(R))],
            'navigation_manifest_sha256':pins[str((N/'manifest.json').relative_to(R))],
            'tokenizer_code_sha256':sha(Path(fulltext.__file__)),
            'builder_sha256':sha(Path(unit_fulltext.__file__)),
            'build_seconds':2436.0+time.monotonic()-started}
    assert all(sha(R/n)==h for n,h in pins.items())
    assert all(sha(R/v['path'])==v['sha256'] for v in execution['files'])
    proof={'schema_version':'unit-fulltext-finalization-recovery-v1','cause':'Original process exit143; signal sender unconfirmed',
        'original_log':str((A/'data-index.log').relative_to(R)),'original_log_sha256':sha(A/'data-index.log'),
        'original_process_exit':143,'inserted_rows':total,'canonical_source_rows_verified':count,
        'tokenization':'All token rows were committed by original pinned builder; tokens not regenerated or edited',
        'unit_and_fts_keys_equal':True,'sqlite_integrity':'ok','fts_integrity':'ok',
        'input_pins':pins,'before_sqlite_sha256':before,'original_archive':str(archive.relative_to(R)),
        'original_archive_sha256':sha(archive),'restore':'gzip -dc units-before.sqlite.gz > recovered-original.sqlite',
        'recovery_script':str(Path(__file__).relative_to(R)),'recovery_script_sha256':sha(Path(__file__)),
        'after_sqlite_sha256':sha(F/'units.sqlite'),'quality_certified':False}
    put(O/'proof.json',proof)
    result.update(index_sha256=proof['after_sqlite_sha256'],recovery={
        'schema_version':proof['schema_version'],'proof_path':str((O/'proof.json').relative_to(R)),
        'proof_sha256':sha(O/'proof.json'),'script_sha256':proof['recovery_script_sha256']})
    put(F/'manifest.json',result)
    # Use the normal checkpoint writer, disclosing and retaining the existing data.
    Stages(B,identity).run('fulltext',['generation/fulltext'],lambda:result,preserve_partial=True)
    print('RECOVERY fulltext finalization checkpointed',count,flush=True)

if __name__=='__main__':
    with (P/'serving/.lock').open('a+') as outer,(P/'serving/.baseline.build.lock').open('a+') as inner:
        fcntl.flock(outer,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(inner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        recover()
