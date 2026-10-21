"""Installed code, read-only guards and synthetic selection. No model/network."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile


def main(root):
    root=Path(root).resolve(strict=True);sys.path.insert(0,str(root/'02_BACKEND'))
    from semantic_runtime.contracts import sha,write
    from semantic_runtime.storage import Store
    from lawrag.pipeline.search_selection import plan,activate,rollback
    assert Path(sys.modules['semantic_runtime.storage'].__file__).resolve()==root/'02_BACKEND/semantic_runtime/storage.py'
    cfg=json.loads((root/'00_SYSTEM/PIPELINE.json').read_bytes())
    for entry in cfg['engines'].values():
        path=root/entry['manifest']; assert sha(path)==entry['sha256'],str(path)
        m=json.loads(path.read_bytes())
        for name,pin in m['files'].items():assert sha(root/name)==pin,name
    with tempfile.TemporaryDirectory(prefix='search-latest-check-') as tmp:
        g=Path(tmp)/'generation';g.mkdir();db=sqlite3.connect(g/'store.sqlite')
        db.executescript('CREATE TABLE document(document_id TEXT,name TEXT,source_artifact_sha256 TEXT,json TEXT);'
                        'CREATE TABLE source_unit(document_id TEXT,unit_id TEXT);'
                        'CREATE TABLE source_block(document_id TEXT,block_id TEXT,text TEXT);')
        for did,date in [('old','20190710'),('new','20220331')]:
            metadata={'source_category':'internal','relative_path':'internal/모의규정('+date+').docx'}
            db.execute('INSERT INTO document VALUES (?,?,?,?)',(did,did,did,json.dumps({'document_metadata':metadata})))
            db.execute('INSERT INTO source_block VALUES (?,?,?)',(did,'1','synthetic'))
        db.commit();db.close();pin=sha(g/'store.sqlite')
        write(g/'manifest.json',{'schema_version':'term-source-generation-v1','generation_id':'synthetic',
                                'store_sha256':pin,'scope':{'document_version_ids':['old','new']}})
        p=plan(g,latest=True);assert [r['document_id'] for r in p['excluded']]==['old']
        receipt=activate(p);assert activate(p)['state']=='ALREADY_APPLIED'
        store=Store(g,verify=False)
        try:
            store.selection.require_latest()
            assert json.loads(store.db.execute('SELECT json FROM document').fetchone()[0])['document_metadata']['is_latest'] is True
            assert [r[0] for r in store.db.execute('SELECT document_id FROM document')]==['new']
            assert store.db.execute("SELECT text FROM source_block WHERE document_id='old'").fetchone() is None
            try:store.db.execute('DELETE FROM main.document')
            except sqlite3.DatabaseError:pass
            else:raise AssertionError('write protection missing')
        finally:store.close()
        assert sha(g/'store.sqlite')==pin
        rollback(receipt['receipt']);store=Store(g,verify=False)
        try:assert store.db.execute('SELECT count(*) FROM document').fetchone()[0]==2
        finally:store.close()
    print(json.dumps({'status':'INSTALLED_CODE_PASS','root':str(root),'python':sys.executable,
                      'version':sys.version,'model_calls':0,'rebuild':False}))


if __name__=='__main__':main(sys.argv[1])
