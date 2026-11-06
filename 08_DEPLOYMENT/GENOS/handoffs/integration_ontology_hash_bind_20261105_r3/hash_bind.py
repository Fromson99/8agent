"""Name lookup, then an explicit operator-selected document hash binding.

The original reviewed text/claims are unchanged. Only exact text at the same
legal coordinate can acquire the selected destination document/version/unit IDs.
"""
import argparse
from contextlib import closing
from copy import deepcopy
import getpass
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
import zipfile

OLD_DOCUMENT='11478916f48b00e5'
DOCUMENT_NAME='위험관리위원회운영준칙'
R2_NAME='INTEGRATION_ONTOLOGY_B03_B05_R2.zip'
R2_SHA='1bfc357186c44890b58159aabb703ffee573cd21b07721d7b2ac4405a048ff34'
PHOTO_GENERATION='/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'
PRODUCER_FILES=['ontology_work/workflow.py','ontology_work/schema.py','ontology_work/repository.py',
    'ontology_work/store.py','legal_agent/ontology_compiler.py','legal_agent/ontology_scenarios.py']

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(obj):return (json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()
def read(path):return json.loads(Path(path).read_text())
def name_key(name):return re.sub(r'\s+','',name or '')
def open_source(generation):
    p=Path(generation)/'store.sqlite'
    if not p.is_file() or p.is_symlink():raise ValueError('Existing regular source store.sqlite required')
    db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
    db.execute('PRAGMA query_only=ON');return db

def candidates(generation,query=DOCUMENT_NAME):
    with closing(open_source(generation)) as db:
        # Names/hashes only; never load a whole document's source text for lookup.
        rows=db.execute('SELECT document_id,name,source_artifact_sha256 FROM document').fetchmany(20001)
        if len(rows)>20000:raise ValueError('Document metadata bound exceeded')
        found=[]
        for did,name,version in rows:
            if name_key(query) not in name_key(name):continue
            units=db.execute('SELECT COUNT(*) FROM source_unit WHERE document_id=?',(did,)).fetchone()[0]
            blocks=db.execute('SELECT COUNT(*) FROM source_block WHERE document_id=?',(did,)).fetchone()[0]
            found.append({'document_id':did,'document_hash':version,'document_name':name,'units':units,'blocks':blocks})
    return sorted(found,key=lambda r:(r['document_name'],r['document_id']))

def search(generation):
    found=candidates(generation)
    result={'status':'DOCUMENT_CANDIDATES' if found else 'NO_EXACT_NAME_MATCH','generation':str(generation),'query':DOCUMENT_NAME,
            'candidates':found,'database_writes':0,'ontology_writes':0}
    if not found:result['nearby_names']=candidates(generation,'위험관리위원회')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('\n확인할 값은 document_hash입니다. 자동 선택·연결은 하지 않았습니다.')
    print('문서명과 해시를 확인한 뒤: bash GENOS_ONTOLOGY_BIND_R3.txt <확인한_64자리_해시> [문서ID]')
    return result

def selected_document(generation,confirmed_hash,document_id=None):
    if not re.fullmatch('[0-9a-fA-F]{64}',confirmed_hash or ''):
        raise ValueError('확인한 64자리 문서 해시가 필요합니다. 먼저 FIND를 실행하십시오.')
    found=[r for r in candidates(generation) if (r['document_hash'] or '').lower()==confirmed_hash.lower()
           and (document_id is None or r['document_id']==document_id)]
    if len(found)!=1:raise ValueError('이름·확인한 해시에 맞는 문서가 유일하지 않습니다. FIND 결과와 문서ID를 확인하십시오.')
    return found[0]

def coordinate(value):
    if not isinstance(value,dict):return None
    return (value.get('unit'),value.get('n'),value.get('sub'),value.get('dash'),
            tuple(coordinate(c) for c in value.get('chain',[])))

def remap_sources(generation,selected,expected):
    with closing(open_source(generation)) as db:
        rows=db.execute('SELECT unit_id,json FROM source_unit WHERE document_id=?',(selected['document_id'],)).fetchmany(4097)
        if not rows or len(rows)>4096:raise ValueError('Selected internal document unit bound')
        units=[]
        for uid,raw in rows:
            meta=json.loads(raw)
            blocks=db.execute('SELECT block_id,text FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',
                              (selected['document_id'],uid)).fetchmany(4097)
            if len(blocks)>4096:raise ValueError('Source block bound')
            units.append({'unit_id':str(uid),'coordinate':coordinate(meta.get('legal_coordinate')),
                'scope':meta.get('coordinate_scope'),'block_ids':[str(b[0]) for b in blocks],
                'text_hash':sha('\n'.join(b[1] for b in blocks).encode())})
        result={}
        for item in expected:
            old=item['anchor']
            if old['document_id']!=OLD_DOCUMENT:continue
            wanted=coordinate(item['coordinate'])
            matches=[u for u in units if u['coordinate']==wanted and u['scope']=='body' and u['text_hash']==old['content_sha256']]
            if len(matches)!=1:
                text_matches=sum(u['text_hash']==old['content_sha256'] for u in units)
                location_matches=sum(u['coordinate']==wanted and u['scope']=='body' for u in units)
                raise ValueError('원문/조항 대조 중단: '+old['label']+' '+json.dumps({'same_text_units':text_matches,'same_coordinate_units':location_matches,'exact_matches':len(matches)}))
            unit=matches[0]
            result[old['unit_id']]={'before':old,'after':{**old,'document_id':selected['document_id'],
                'version':selected['document_hash'],'unit_id':unit['unit_id']},'block_ids':unit['block_ids']}
    if len(result)!=17 or len({r['after']['unit_id'] for r in result.values()})!=17:
        raise ValueError('All 17 internal source units must match one-to-one')
    return result

def unpack_r2(archive,target):
    raw=Path(archive).read_bytes()
    if sha(raw)!=R2_SHA:raise ValueError('Original validated R2 ZIP hash mismatch')
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or sum(i.file_size for i in z.infolist())>64*1024*1024:raise ValueError('ZIP inventory/size')
        for n in names:
            p=PurePosixPath(n)
            if p.is_absolute() or '..' in p.parts or '\\' in n or str(p)!=n:raise ValueError('ZIP path')
        checks=json.loads(z.read('PACKAGE_MANIFEST.json'))['files']
        if set(names)!=set(checks)|{'PACKAGE_MANIFEST.json'}:raise ValueError('ZIP inventory')
        for n,d in checks.items():
            if sha(z.read(n))!=d:raise ValueError('ZIP content changed')
        z.extractall(target)

def fresh_imports(package,root):
    for name in ('it35_common','genos_install','genos_verify'):sys.modules.pop(name,None)
    sys.path[:0]=[str(package),str(root/'02_BACKEND')]
    common=importlib.import_module('it35_common');installer=importlib.import_module('genos_install')
    return common,installer

def validate_all(generation,sources):
    with closing(open_source(generation)) as db:
        for item in sources:
            a=item['anchor'];row=db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(a['document_id'],)).fetchone()
            blocks=db.execute('SELECT block_id,text FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',
                (a['document_id'],a['unit_id'])).fetchmany(4097)
            if not row or row[0]!=a['version'] or [str(r[0]) for r in blocks]!=item['block_ids'] or sha('\n'.join(r[1] for r in blocks).encode())!=a['content_sha256']:
                raise ValueError('Source validation failed: '+a['document_id']+'/'+a['unit_id'])

def rebuild(package,root,generation,selected,mapping,binding):
    common,installer=fresh_imports(package,root);common.verify_package();installer.patch_plan(root)
    data=deepcopy(read(package/'payload/ontology.json'));sources=deepcopy(read(package/'payload/sources.json'))
    for item in sources:
        if item['anchor']['document_id']==OLD_DOCUMENT:
            changed=mapping[item['anchor']['unit_id']];item['anchor']=changed['after'];item['block_ids']=changed['block_ids']
    validate_all(generation,sources)  # Every public and internal source before authoring.
    from semantic_runtime.contracts import digest
    from semantic_runtime.ontology_work import schema
    from semantic_runtime.ontology_work.repository import Repository
    from semantic_runtime.ontology_work.store import LocalFolderStore
    from semantic_runtime.ontology_work.workflow import Workflow
    from semantic_runtime.legal_agent.ontology_scenarios import compile_package
    path=package/'payload/ontology.sqlite';path.unlink()
    work=package/'payload/work';shutil.rmtree(work)
    repo=Repository(lambda:sqlite3.connect(path));repo.initialize()
    allowed={s['anchor']['document_id'] for s in sources}
    def source_reader(anchor):
        if anchor['document_id'] not in allowed:raise ValueError('Source scope')
        with closing(open_source(generation)) as db:
            row=db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(anchor['document_id'],)).fetchone()
            if not row or row[0]!=anchor['version']:raise ValueError('Source version changed')
            return '\n'.join(r[0] for r in db.execute('SELECT text FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',
                (anchor['document_id'],anchor['unit_id'])).fetchmany(4097))
    workflow=Workflow(repo,LocalFolderStore(work),actor='operator:'+getpass.getuser(),source_reader=source_reader)
    for entry in data['entries']:
        changed=False
        for original in entry['input']['originals']:
            if original['anchor']['document_id']==OLD_DOCUMENT:
                original['anchor']=deepcopy(mapping[original['anchor']['unit_id']]['after']);changed=True
        if changed:
            entry['input']['origin']['confirmed_source_binding']=binding
            entry['review']['reason']+=' 사용자 지정 문서해시를 현장 원문과 재대조: 동일 조항·동일 본문, 출처 좌표만 재결속.'
        entry['review']['entry_sha256']=digest({'input':entry['input'],'proposal':entry['proposal']})
        entry['preview_package_sha256']=compile_package(schema.recipe_for(entry['input'],entry['proposal'],entry['bundle_id']),entry['input']['originals'])['package_sha256']
    # Complete all validation/compilation before the first new local workflow row.
    for entry in data['entries']:workflow.verify_sources(entry['input'])
    for entry in data['entries']:
        saved=workflow.save(entry['input'],entry['proposal'],bundle_id=entry['bundle_id'])
        workflow.review(entry['bundle_id'],saved['revision'],saved['work_hash'],True,entry['review']['reason'])
        receipt=workflow.publish(entry['bundle_id'],saved['revision'],saved['work_hash'],0)
        if not receipt['active']:raise ValueError('Local publication did not activate')
    (package/'payload/ontology.json').write_bytes(encode(data));(package/'payload/sources.json').write_bytes(encode(sources))
    (package/'SOURCE_REBINDING.json').write_bytes(encode({'binding':binding,'selected':selected,'source_mapping':mapping,
        'semantic_changes':0,'original_claims_and_quotes':'unchanged','original_R2_zip_sha256':R2_SHA,
        'review_tables':'payload/answer_review.json and CSV preserve the original R1 review; destination coordinates are recorded here'}))
    target_name='integration-b03-b05-r3-'+binding['identity'][:12]
    script=package/'genos_install.py';text=script.read_text()
    if text.count("'integration-b03-b05-r2'")!=1:raise ValueError('R2 target anchor')
    script.write_text(text.replace("'integration-b03-b05-r2'",repr(target_name)))
    checks={p.relative_to(package).as_posix():sha(p.read_bytes()) for p in sorted(package.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.name!='PACKAGE_MANIFEST.json'}
    (package/'PACKAGE_MANIFEST.json').write_bytes(encode({'version':'it35-confirmed-binding-r3','files':checks}))

def bind(generation,root,archive,confirmed_hash,document_id=None,output=None):
    generation=Path(generation).resolve(strict=True);root=Path(root).resolve(strict=True)
    selected=selected_document(generation,confirmed_hash,document_id)
    producer={n:sha((root/'02_BACKEND/semantic_runtime'/n).read_bytes()) for n in PRODUCER_FILES}
    binding={'generation':str(generation),'manifest_sha256':sha((generation/'manifest.json').read_bytes()),
        'document_id':selected['document_id'],'confirmed_document_hash':selected['document_hash'],
        'confirmation':'explicit operator hash argument','producer':producer,'original_zip_sha256':R2_SHA}
    binding['identity']=sha(encode(binding))
    out=Path(output).resolve() if output else Path(archive).resolve().parent/('ONTOLOGY_R3_'+binding['identity'][:12])
    package=out/'bound-package'
    # Build on local codespace temporary storage; NFS sees only the sealed output.
    if not package.exists():
        with tempfile.TemporaryDirectory(prefix='it35-bind-r3-') as tmp:
            stage=Path(tmp)/'package';stage.mkdir();unpack_r2(archive,stage)
            mapping=remap_sources(generation,selected,read(stage/'payload/sources.json'))
            rebuild(stage,root,generation,selected,mapping,binding)
            out.mkdir(parents=True,exist_ok=True)
            if package.exists():raise ValueError('Concurrent binding preparation; reuse its receipt')
            preparing=out/('.bound-'+uuid.uuid4().hex)
            try:
                shutil.copytree(stage,preparing)
                preparing.rename(package)
            finally:
                if preparing.exists():shutil.rmtree(preparing)
    else:
        if read(package/'SOURCE_REBINDING.json')['binding']!=binding:raise ValueError('Existing binding differs; preserve it')
    common,installer=fresh_imports(package,root);common.verify_package()
    validate_all(generation,read(package/'payload/sources.json'))
    result=installer.install(root,generation,out/'install-receipt',True)
    verifier=importlib.import_module('genos_verify');verification=verifier.verify(root,result['environment']['GENOS_RAG_ONTOLOGY_CONFIG'])
    result.update(status='CONFIRMED_HASH_ONTOLOGY_PREPARED',selected_document=selected,binding_identity=binding['identity'],
                  source_mapping_path=str(package/'SOURCE_REBINDING.json'),consumer_paths=verification['paths'],field_serving_verified=False)
    (out/'BIND_RECEIPT.json').write_bytes(encode(result));print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['find','bind']);p.add_argument('confirmed_hash',nargs='?');p.add_argument('document_id',nargs='?')
    p.add_argument('--generation',default=os.environ.get('IT35_GENERATION') or os.environ.get('GENOS_GENERATION') or PHOTO_GENERATION)
    p.add_argument('--code-root',default=os.environ.get('IT35_CODE') or str(Path.home()/'DEV'))
    p.add_argument('--archive',default=str(Path.cwd()/R2_NAME));p.add_argument('--output');a=p.parse_args(argv)
    if a.mode=='find':return search(Path(a.generation).resolve(strict=True))
    if not a.confirmed_hash:p.error('먼저 FIND로 문서 해시를 확인하고 그 값을 첫 인수로 넣으십시오.')
    return bind(a.generation,a.code_root,a.archive,a.confirmed_hash,a.document_id,a.output)

if __name__=='__main__':
    try:main()
    except (ValueError,sqlite3.Error,OSError) as exc:
        print('ONTOLOGY_BIND_STOP: '+str(exc),file=sys.stderr);raise SystemExit(2)
