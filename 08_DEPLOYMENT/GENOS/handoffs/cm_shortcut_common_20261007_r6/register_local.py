"""Register user-directed shared catalogue in existing local state; preserve history."""
import contextlib
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.pipeline.unified_memory import main
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from semantic_runtime.legal_agent.shortcut_store import selected_store,store_owner
from semantic_runtime.legal_agent import core_evidence_route as core
from types import SimpleNamespace

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def run():
    os.environ.pop('GENOS_STATE_DIR',None)
    runtime=ROOT/'90_RUNTIME/semantic';generation=ROOT/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation'
    pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';before_main=sha(pointer.read_bytes())
    before_source=sha((generation/'store.sqlite').read_bytes())
    dbpath=selected_store(runtime)
    backup=OUT/'LOCAL_SQLITE_BEFORE.sqlite.gz'
    assert not backup.exists(),'Do not overwrite an existing state backup'
    with store_owner(runtime,exclusive=True),TemporaryDirectory() as directory:
        target=Path(directory)/'before.sqlite'
        with sqlite3.connect(dbpath) as source,sqlite3.connect(target) as dest:source.backup(dest)
        raw=target.read_bytes();backup.write_bytes(gzip.compress(raw,mtime=0))
        (OUT/'LOCAL_SQLITE_BEFORE.json').write_bytes(encoded({'store':str(dbpath),'sqlite_sha256':sha(raw),
            'gzip_sha256':sha(backup.read_bytes()),'restore':'gzip -dc LOCAL_SQLITE_BEFORE.sqlite.gz > NEW.sqlite; explicit store rollback only; do not replace a running DB'}))
    base=['--root',str(ROOT),'--runtime',str(runtime),'--generation',str(generation),'--store-version','4']
    transcript=io.StringIO()
    def call(command,source,output,*,common=True,principal=None):
        args=[command,*base,'--source',str(source),'--output',str(output)]
        args += ['--common'] if common else ['--principal',str(principal)]
        with contextlib.redirect_stdout(transcript):assert main(args)==0
    receipt=OUT/'LOCAL_COMMON_IMPORT_RECEIPT.json'
    call('package-check',OUT/'CM51_SOURCE_PACKAGE.json',OUT/'LOCAL_COMMON_CHECK.json')
    call('package-import',OUT/'CM51_SOURCE_PACKAGE.json',receipt)
    call('package-verify',receipt,OUT/'LOCAL_COMMON_VERIFIED.json')
    prior=OUT.with_name('cm_shortcut_data_20261007_r2')
    call('package-retire',prior/'LOCAL_IMPORT_RECEIPT.json',OUT/'LOCAL_R2_PRIVATE_RETIRED.json',
         common=False,principal=prior/'LOCAL_PRINCIPAL.json')
    data=json.loads(receipt.read_bytes());assert len(data['records'])==51 and data['visibility']=='COMMON_CATALOG'
    package=json.loads((OUT/'CM51_SOURCE_PACKAGE.json').read_bytes())
    repo=ShortcutRepository(dbpath)
    host=SimpleNamespace(shortcut=repo,binding=data['source_binding'],
        model=SimpleNamespace(pipeline=SimpleNamespace(term_agent=SimpleNamespace(transport=SimpleNamespace(binding={'trust_zone':'genos'})))))
    readers=[]
    for user,team in [('jin','CM'),('common-other-user','risk_team'),('common-other-team-user','financial_team')]:
        principal={'user_id':user,'team_id':team,'authenticated':True,'document_ids':data['documents']}
        state={'task':package['cases'][0]['question'],'facts':[],'document_ids':data['documents']}
        found=repo.search(principal,limit=100)['pages'];path=core.lookup(host,state,principal)
        assert len(found)==51 and path['unit_id']==data['records'][0]['unit_id']
        readers.append({'user_id':user,'team_id':team,'shared_units':len(found),'same_unit':True})
    counts=[dict(r) for r in repo.db.execute("SELECT json_extract(k.payload,'$.visibility') visibility,l.status,count(*) units FROM sw_knowledge k JOIN sw_lifecycle l USING(unit,revision) GROUP BY visibility,l.status")]
    repo.close()
    assert sha(pointer.read_bytes())==before_main and sha((generation/'store.sqlite').read_bytes())==before_source
    result={'shared_catalogue':True,'cases':51,'entries':98,'readers':readers,'counts':counts,
            'sqlite':str(dbpath),'source_store_sha256_unchanged':before_source,'MAIN_pointer_sha256_unchanged':before_main,
            'MAIN45_includes_common_consumer':False,'model_calls':0,'GENOS_field_verified':False}
    (OUT/'LOCAL_REGISTRATION_VERIFIED.json').write_bytes(encoded(result))
    (OUT/'LOCAL_REGISTRATION.log.gz').write_bytes(gzip.compress(transcript.getvalue().encode(),mtime=0))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':run()
