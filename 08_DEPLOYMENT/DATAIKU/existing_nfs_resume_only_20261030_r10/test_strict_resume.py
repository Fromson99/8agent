import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

HERE=Path(__file__).resolve().parent;CODE=HERE/'candidate'
sys.path[:0]=[str(CODE),str(CODE/'client'),str(CODE/'client/02_BACKEND')]
import strict_resume as resume
from lawrag.pipeline import oracle_deferred_import as d,oracle_migration as m,oracle_existing_nfs as nfs


def descriptor_fixture(tmp_path):
    root=tmp_path/'generation';root.mkdir()
    (root/'store.sqlite').write_bytes(b'unchanged-source-content')
    manifest={'schema_version':'term-source-generation-v2','store_sha256':d.io.file_sha(root/'store.sqlite')}
    (root/'manifest.json').write_text(json.dumps(manifest))
    binding,_=m.source_binding(root/'store.sqlite');binding['target_binding']='target'
    logs=tmp_path/'oracle-import-r2';logs.mkdir();(logs/'full-state.json').write_text('{}')
    path=logs/'source'/'matching'/'state.json';path.parent.mkdir(parents=True)
    counts={k:i+1 for i,k in enumerate(d.io.TABLES)}
    rows={k:{'rows':counts[k],'chain':d.io.digest(k)} for k in d.io.TABLES}
    state={'status':'VERIFIED','pending':None,'binding':binding,'tables':rows}
    path.write_text(json.dumps(state))
    files={'store.sqlite':manifest['store_sha256'],'manifest.json':d.io.file_sha(root/'manifest.json')}
    source={'schema_version':d.assets.SCHEMA,'status':'COMPLETE','dataset_version':files['manifest.json'],
        'source_manifest':manifest,'source_manifest_text':(root/'manifest.json').read_text(),
        'source_rows':rows,'assets':[],'search_selection':None,
        'codec':'zlib-per-1MiB-part-v1','source_projection':'compact-source-v2-logical-rows-v1'}
    body={'binding':{'source':d.io.digest(source),'files':files},'paths':{},'tables':{}}
    (logs/'projection-descriptor-r7.json').write_text(json.dumps(dict(body,checksum=d.io.digest(body))))
    return root,manifest,files,logs,path,state,source,counts


def test_exact_saved_source_reconstructed_without_reading_rows(tmp_path):
    root,manifest,files,logs,path,state,source,counts=descriptor_fixture(tmp_path)
    with patch.object(m,'source_open',side_effect=AssertionError('source row scan forbidden')):
        assert resume.source_descriptor(root,manifest,[],files,None,logs,'target',counts)==source


@pytest.mark.parametrize('damage',['pending','partial','binding','chain','missing','modified_input','failed_without_completion'])
def test_incomplete_or_changed_receipt_refuses_to_recalculate(tmp_path,damage):
    root,manifest,files,logs,path,state,source,counts=descriptor_fixture(tmp_path)
    if damage=='pending':state['pending']={'rows':20}
    elif damage=='partial':next(iter(state['tables'].values()))['rows']=0
    elif damage=='binding':state['binding']['target_binding']='other'
    elif damage=='chain':next(iter(state['tables'].values()))['chain']='0'*64
    elif damage=='modified_input':(root/'store.sqlite').write_bytes(b'changed')
    elif damage=='failed_without_completion':state['status']='FAILED'
    if damage=='missing':path.unlink()
    else:path.write_text(json.dumps(state))
    with patch.object(m,'source_open',side_effect=AssertionError('must not restart')):
        with pytest.raises(d.io.DPError,match='RECEIPT_REQUIRED'):
            resume.source_descriptor(root,manifest,[],files,None,logs,'target',counts)


def test_later_remote_verify_failure_reuses_only_prior_completed_local_descriptor(tmp_path):
    root,manifest,files,logs,path,state,source,counts=descriptor_fixture(tmp_path)
    state.update(status='FAILED',completed_at=123,source_hash_verified=True,counts=counts,
                 failure={'error':'VERIFY_MISSING'})
    path.write_text(json.dumps(state))
    with patch.object(m,'source_open',side_effect=AssertionError('source row scan forbidden')):
        assert resume.source_descriptor(root,manifest,[],files,None,logs,'target',counts)==source


@pytest.mark.parametrize('damage',['missing','binding','checksum'])
def test_strict_descriptor_never_falls_back_to_full_describe(tmp_path,damage):
    with patch.object(d.query,'describe',return_value=({}, {}, {})):d.prepared_descriptor(tmp_path,{'id':'same'},{},tmp_path)
    path=tmp_path/'projection-descriptor-r7.json'
    if damage=='missing':path.unlink()
    else:
        value=json.loads(path.read_text())
        if damage=='checksum':value['tables']={'invalid':{}}
        else:
            value['binding']['source']='other'
            value['checksum']=d.io.digest({k:v for k,v in value.items() if k!='checksum'})
        path.write_text(json.dumps(value))
    with patch.object(d.query,'describe',side_effect=AssertionError('must not recalculate')):
        with pytest.raises(d.io.DPError):d.prepared_descriptor(tmp_path,{'id':'same'},{},tmp_path,strict=True)


def snapshot_fixture(tmp_path):
    root=tmp_path/'generation';root.mkdir();(root/'manifest.json').write_text('{}');(root/'store.sqlite').write_bytes(b'input')
    files={str(p.relative_to(tmp_path)):{'bytes':p.stat().st_size,'sha256':d.io.file_sha(p)} for p in root.iterdir()}
    info={'protocol':nfs.PROTOCOL,'code_sha256':'a'*64,'generation':'/nfs/frozen/generation',
          'chunk_bytes':nfs.CHUNK,'source_modified':False,'rebuild':False,'files':files,
          'dataset_version':files['generation/manifest.json']['sha256']}
    info['snapshot_sha256']=nfs.digest(info)
    (tmp_path/'full-manifest.json').write_text(json.dumps({'nfs_snapshot':info,'files':files,'dataset_version':info['dataset_version']}))
    store=SimpleNamespace(value={'snapshot_sha256':info['snapshot_sha256']})
    return store,info


def test_local_snapshot_only_does_not_create_new_files(tmp_path):
    store,info=snapshot_fixture(tmp_path)
    before=sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*'))
    assert resume.local_snapshot(store,tmp_path,expected_code='a'*64,generation='/nfs/frozen/generation')==info
    assert before==sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*'))


@pytest.mark.parametrize('damage',['marker','data','snapshot'])
def test_missing_local_inputs_stop_without_fetch(tmp_path,damage):
    store,info=snapshot_fixture(tmp_path)
    if damage=='marker':(tmp_path/'full-manifest.json').unlink()
    elif damage=='data':(tmp_path/'generation/store.sqlite').unlink()
    else:store.value['snapshot_sha256']='b'*64
    with pytest.raises(ValueError):resume.local_snapshot(store,tmp_path,expected_code='a'*64,generation='/nfs/frozen/generation')
    if damage=='data':assert not (tmp_path/'generation/store.sqlite').exists()
