"""Actual FTS builder/reader checks under sealed candidate code, not a timing run."""
from pathlib import Path
import argparse
import hashlib
import json
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[3]
ART=ROOT/'04_EXPERIMENTS/ADR/ADR-1181-pipeline02-balanced-tokenization/artifacts'


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main(arm):
    runtime=ART/'runtimes'/arm
    sys.path.insert(0,str(runtime/'02_BACKEND'))
    from semantic_runtime import fulltext,unit_fulltext
    assert Path(fulltext.__file__).resolve().is_relative_to(runtime.resolve())
    work=ART/'consumer'/arm;work.mkdir(parents=True,exist_ok=False)
    source=work/'generation';source.mkdir();nav=work/'navigation';nav.mkdir()
    db=sqlite3.connect(source/'store.sqlite')
    db.executescript('CREATE TABLE document(document_id TEXT PRIMARY KEY);CREATE TABLE source_unit(document_id TEXT,unit_id TEXT);CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT);')
    nd=sqlite3.connect(nav/'navigation.sqlite');nd.execute('CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,json TEXT)')
    for did,n in [('allowed',257),('denied',1)]:
        db.execute('INSERT INTO document VALUES(?)',(did,));blocks=[]
        for i in range(n):
            text=('긴급 승인과 영업일 신청을 규정한다. '+str(i)) if did=='allowed' else '비밀 제한 문서'
            uid=str(i);db.execute('INSERT INTO source_unit VALUES(?,?)',(did,uid))
            db.execute('INSERT INTO source_block VALUES(?,?,?,?)',(did,uid,uid,text))
            blocks.append({'block_id':uid,'text':text})
        value={'id':did,'document_id':did,'unit_id':'root','document_name':did,'heading':'규정','blocks':blocks}
        nd.execute('INSERT INTO source VALUES(?,?,?)',(did,did,json.dumps(value,ensure_ascii=False)))
    db.commit();nd.commit();db.close();nd.close()
    sm={'generation_id':'technical-1180','store_sha256':sha(source/'store.sqlite')}
    nm={'generation_id':sm['generation_id'],'source_store_sha256':sm['store_sha256'],'index_sha256':sha(nav/'navigation.sqlite')}
    (source/'manifest.json').write_text(json.dumps(sm));(nav/'manifest.json').write_text(json.dumps(nm))
    before={p:sha(p) for p in [source/'store.sqlite',nav/'navigation.sqlite']}
    workers=3 if arm=='baseline' else 4
    out=work/'index';manifest=unit_fulltext.build(source,nav,out,document_ids=['allowed'],workers=workers)
    assert manifest['counts']['unit']==257 and manifest['scope']['document_version_ids']==['allowed']
    idx=fulltext.open_index(out,nm)
    with idx.connect() as db:
        hits=idx.rank_units(db,['승인']);assert hits and all(h['document_id']=='allowed' for h in hits)
        assert idx.rank_units(db,['승인'],set())==[]
        try:idx.rank_units(db,['승인'],{'denied'})
        except ValueError:pass
        else:raise AssertionError('foreign scope accepted')
        rows=list(db.execute('SELECT key,source_id,document_id,json FROM unit ORDER BY key'))
        fts=list(db.execute('SELECT key,body FROM unit_fts ORDER BY key'))
    assert all(sha(p)==expected for p,expected in before.items())
    with (out/'units.sqlite').open('ab') as f:f.write(b'tamper')
    try:idx.connect()
    except ValueError:pass
    else:raise AssertionError('input mutation undetected')
    sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
    from experiment_json import write_summary,write_raw_json
    raw=write_raw_json(work/'rows.json.gz',{'rows':rows,'fts':fts})
    write_summary(work/'result.json',{'status':'PASS','arm':arm,'unit_rows':257,'workers':workers,
        'row_digest':hashlib.sha256(json.dumps([rows,fts],ensure_ascii=False).encode()).hexdigest(),
        'checks':['source scope','empty scope','foreign scope rejected','payload tamper rejected','original inputs unchanged','actual builder and reader'],
        'raw':raw,'model_calls':0})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('arm');main(p.parse_args().arm)
