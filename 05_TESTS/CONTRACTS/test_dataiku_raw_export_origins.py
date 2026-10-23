"""Small RAW export regressions; no field network, models or Oracle writes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / '08_DEPLOYMENT/DATAIKU/raw_export_20261023_r2'
SERVICE = REPO / '08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r3/GENOS_PIPELINE_SERVICE_20261022_R2.zip'


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def exporter(monkeypatch):
    transport = module(PACKAGE / 'transport.py', 'origin_transport')
    monkeypatch.setitem(sys.modules, 'transport', transport)
    return module(PACKAGE / 'export_inputs.py', 'origin_exporter')


def fixture(tmp_path, exporter, count=1):
    import fitz
    dev = tmp_path / 'dev'
    t = exporter.t
    pairs = []
    catalog = {'schema_version': 'raw-preparation-v1', 'files': {}}
    marks = []
    for i in range(count):
        folder = dev / '01_DATA/RAW/internal/risk_team' / str(i)
        folder.mkdir(parents=True)
        origin = folder / ('테스트규정' + str(i) + '(20250101)' + ('.hwp' if i == 4 else '.doc'))
        origin.write_bytes(('synthetic-original-' + str(i)).encode())
        pdf = origin.with_suffix('.pdf')
        doc = fitz.open(); page = doc.new_page(); page.insert_text((72,72),'synthetic '+str(i)); doc.save(pdf); doc.close()
        catalog['files'][str(pdf.relative_to(dev / '01_DATA'))] = {
            'origin': str(origin.relative_to(dev / '01_DATA')), 'origin_sha256': t.sha(origin),
            'sha256': t.sha(pdf), 'kind': 'native_rendered_pdf'}
        marks.append({'document_id': t.sha(pdf)[:16], 'is_latest': True, 'source_artifact_sha256': t.sha(pdf)})
        pairs.append((origin, pdf))
    t.write(dev / '01_DATA/CATALOG/RAW_DERIVATIVES.json', catalog)
    t.write(dev / '01_DATA/CATALOG/TEAM_LAYOUT.json', {'schema_version':'team-raw-v1','files':{}})
    t.write(dev / '00_SYSTEM/GLOSSARY_PIPELINE.json', {'draft_assembly':{},'current_draft':{'path':'LEXICON/draft'},'knowledge_bundle':{'path':'LEXICON/knowledge'}})
    for folder in ('draft','knowledge'):
        path=dev/'01_DATA/LEXICON'/folder/'info.txt'; path.parent.mkdir(parents=True); path.write_text('synthetic')
    selection = {'schema_version':'filename-search-selection-v2', 'latest_documents':marks, 'excluded':[],
                 'exceptions':{'value':t.read(REPO/'00_SYSTEM/FILENAME_EXCEPTIONS.json')}}
    set_selection(dev, exporter, selection)
    return dev, pairs, catalog


def set_selection(dev, exporter, selection):
    path=dev/'00_SYSTEM/SEARCH_SELECTION/generation.json'
    exporter.t.write(path,selection)
    exporter.t.write(dev/'00_SYSTEM/GENOS_SERVING_PATHS.json',{'search_selection':{'path':str(path.relative_to(dev)), 'sha256':exporter.t.sha(path)}})


def members(path):
    with zipfile.ZipFile(path) as z:return json.loads(z.read('TRANSPORT.json'))['files']


def test_five_origins_exported_and_same_consumer_keeps_only_five_pdfs(tmp_path, exporter):
    dev,pairs,catalog=fixture(tmp_path,exporter,5)
    before={p:exporter.t.sha(p) for p in exporter.t.files(dev)}
    out=tmp_path/'out'; result=exporter.export(dev,out)
    assert result['dependency_check']['filename_selection_unchanged']
    assert len(result['mapping']['included_dependencies'])==5
    raw=members(out/'RAW_INPUT.zip')
    assert all(str(p.relative_to(dev)) in raw for pair in pairs for p in pair)
    assert all(exporter.t.sha(p)==sha for p,sha in before.items())
    workspace=tmp_path/'service'
    with zipfile.ZipFile(SERVICE) as z:z.extractall(workspace)
    workspace=workspace/'GENOS_PIPELINE_SERVICE_20261022_R2'
    exporter.t.unpack(out/'RAW_INPUT.zip',workspace)
    exporter.t.unpack(out/'PIPELINE_SUPPORT.zip',workspace)
    layout=exporter.t.read(workspace/'00_SYSTEM/WORKSPACE.json')
    for item in layout['roots']:(workspace/item['canonical_path']).mkdir(exist_ok=True)
    env={**os.environ,'LAWRAG_WORKSPACE_ROOT':str(workspace),'LAWRAG_TOOL_WORKSPACE_ROOT':str(workspace),
         'PYTHONPATH':str(workspace/'02_BACKEND'),'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
         'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH','')}
    command=[sys.executable,'-B',str(workspace/'06_TOOLS/pipeline.py'),'build-data-stages','--run-id','origin-contract',
             '--stage','raw','--execute','--latest-internal-versions','--filename-exceptions',str(workspace/'01_DATA/INPUT_MAPPING/filename-exceptions.json'),
             '--structure-vlm','off','--pdf-conversion','off','--pdf-parser','local']
    check=subprocess.run(command,env=env,cwd=workspace,text=True,capture_output=True,timeout=60)
    assert check.returncode==0,check.stdout[-6000:]+check.stderr[-3000:]
    inventories=list((workspace/'01_DATA/LOGS/origin-contract').glob('inventory-*.json'))
    assert len(inventories)==1
    inventory=exporter.t.read(inventories[0]);assert not inventory['errors']
    rows=inventory['files'];assert len(rows)==5
    assert {r['sha256'] for r in rows}=={exporter.t.sha(p) for _,p in pairs}
    assert all(Path(r['path']).suffix=='.pdf' for r in rows)


@pytest.mark.parametrize('mode,code',[('missing','DEPENDENCY_MISSING'),('changed','DEPENDENCY_HASH_MISMATCH'),('pdf_changed','DEPENDENCY_HASH_MISMATCH'),('unsafe','UNSAFE_PATH'),('scope','DEPENDENCY_SCOPE_REVIEW'),('registered','DEPENDENCY_REGISTRATION_MISMATCH'),('cycle','DEPENDENCY_CYCLE')])
def test_invalid_dependencies_fail_before_zip_and_preserve_sources(tmp_path,exporter,mode,code):
    dev,pairs,catalog=fixture(tmp_path,exporter)
    origin,pdf=pairs[0];meta=next(iter(catalog['files'].values()))
    if mode=='missing':origin.unlink()
    elif mode=='changed':origin.write_text('different')
    elif mode=='pdf_changed':meta['sha256']='f'*64
    elif mode=='unsafe':meta['origin']='RAW/internal/../../secret.doc'
    elif mode=='scope':
        other=origin.with_name('unrelated.doc');origin.rename(other);meta['origin']=str(other.relative_to(dev/'01_DATA'))
    elif mode=='registered':exporter.t.write(dev/'01_DATA/CATALOG/TEAM_LAYOUT.json',{'schema_version':'team-raw-v1','files':{meta['origin']:{'sha256':'f'*64}}})
    elif mode=='cycle':
        catalog['files'][meta['origin']]={'origin':str(pdf.relative_to(dev/'01_DATA')),'origin_sha256':exporter.t.sha(pdf),'sha256':exporter.t.sha(origin)}
    exporter.t.write(dev/'01_DATA/CATALOG/RAW_DERIVATIVES.json',catalog)
    out=tmp_path/'out'
    with pytest.raises(ValueError,match=code):exporter.export(dev,out)
    assert exporter.t.read(out/'export-status.json')['status']=='FAILED'
    assert not (out/'RAW_INPUT.zip').exists() and not (out/'PIPELINE_SUPPORT.zip').exists()


def test_unrelated_old_and_unselected_files_remain_excluded(tmp_path,exporter):
    dev,pairs,_=fixture(tmp_path,exporter)
    old=pairs[0][0].with_name('과거규정(20200101).doc');old.write_text('old')
    unknown=old.with_name('unselected.docx');unknown.write_text('unselected')
    value=exporter.latest_mapping(dev)[1]
    mark={'document_id':'old','is_latest':False,'source_artifact_sha256':exporter.t.sha(old)}
    value['latest_documents'].append(mark);value['excluded'].append(mark);set_selection(dev,exporter,value)
    result=exporter.export(dev,tmp_path/'out');raw=members(tmp_path/'out/RAW_INPUT.zip')
    assert all(str(p.relative_to(dev)) not in raw for p in (old,unknown))
    assert len(result['mapping']['omitted'])==2
    assert old.exists() and unknown.exists()


def test_explicitly_excluded_origin_is_not_silently_reintroduced(tmp_path,exporter):
    dev,pairs,_=fixture(tmp_path,exporter);value=exporter.latest_mapping(dev)[1]
    mark={'document_id':'original','is_latest':False,'source_artifact_sha256':exporter.t.sha(pairs[0][0])}
    value['latest_documents'].append(mark);value['excluded'].append(mark);set_selection(dev,exporter,value)
    with pytest.raises(ValueError,match='DEPENDENCY_SELECTION_CONFLICT'):exporter.export(dev,tmp_path/'out')


def test_output_cannot_overwrite_old_artifacts_or_failure_records(tmp_path,exporter):
    dev,_,_=fixture(tmp_path,exporter);out=tmp_path/'out';exporter.export(dev,out)
    before={p:exporter.t.sha(p) for p in exporter.t.files(out)}
    with pytest.raises(ValueError,match='OUTPUT_NOT_EMPTY'):exporter.export(dev,out)
    assert all(exporter.t.sha(p)==sha for p,sha in before.items())


def test_changed_dependency_between_preflight_and_pack_fails(tmp_path,exporter,monkeypatch):
    dev,pairs,_=fixture(tmp_path,exporter);pack=exporter.t.pack
    def changed(paths,output,**kwargs):
        if output.name=='RAW_INPUT.zip':pairs[0][0].write_text('changed-after-preflight')
        return pack(paths,output,**kwargs)
    monkeypatch.setattr(exporter.t,'pack',changed)
    with pytest.raises(ValueError,match='PACKED_INPUT_CHANGED'):exporter.export(dev,tmp_path/'out')
    assert exporter.t.read(tmp_path/'out/export-status.json')['status']=='FAILED'


def test_changed_catalog_between_preflight_and_pack_fails(tmp_path,exporter,monkeypatch):
    dev,_,_=fixture(tmp_path,exporter);pack=exporter.t.pack
    def changed(paths,output,**kwargs):
        if output.name=='PIPELINE_SUPPORT.zip':(dev/'01_DATA/CATALOG/RAW_DERIVATIVES.json').write_text('{}')
        return pack(paths,output,**kwargs)
    monkeypatch.setattr(exporter.t,'pack',changed)
    with pytest.raises(ValueError,match='PACKED_INPUT_CHANGED'):exporter.export(dev,tmp_path/'out')


def test_single_file_folder_policy_drift_is_rejected(tmp_path,exporter):
    dev,pairs,_=fixture(tmp_path,exporter)
    origin,pdf=pairs[0]
    newer=pdf.parent.parent/'second'/pdf.name.replace('20250101','20260101');newer.parent.mkdir();newer.write_bytes(pdf.read_bytes()+b'\nnew')
    value=exporter.latest_mapping(dev)[1]
    value['latest_documents'].append({'document_id':'second','is_latest':True,'source_artifact_sha256':exporter.t.sha(newer)})
    value['exceptions']['value']={'schema_version':'filename-audit-exceptions-v1','revision':'synthetic','single_file_folder_is_latest':True,'rules':[]}
    set_selection(dev,exporter,value)
    with pytest.raises(ValueError,match='DEPENDENCY_SELECTION_DRIFT'):exporter.export(dev,tmp_path/'out')


def test_archive_dependency_cannot_expand_raw_scope(tmp_path,exporter):
    dev,pairs,catalog=fixture(tmp_path,exporter);origin,_=pairs[0]
    archive=origin.with_name('other.zip');archive.write_bytes(b'synthetic archive')
    catalog['extractions']={str(origin.relative_to(dev/'01_DATA')):{'archive':str(archive.relative_to(dev/'01_DATA')),'archive_sha256':exporter.t.sha(archive),'sha256':exporter.t.sha(origin)}}
    exporter.t.write(dev/'01_DATA/CATALOG/RAW_DERIVATIVES.json',catalog)
    with pytest.raises(ValueError,match='DEPENDENCY_SCOPE_REVIEW'):exporter.export(dev,tmp_path/'out')


def test_final_zip_wrapper_and_long_names(tmp_path,exporter):
    dev,pairs,catalog=fixture(tmp_path,exporter)
    origin,pdf=pairs[0];stem='긴규정_'+'가'*65+'(20250101)'
    long_origin=origin.with_name(stem+'.doc');long_pdf=pdf.with_name(stem+'.pdf');origin.rename(long_origin);pdf.rename(long_pdf)
    old_meta=next(iter(catalog['files'].values()));old_meta['origin']=str(long_origin.relative_to(dev/'01_DATA'))
    catalog['files']={str(long_pdf.relative_to(dev/'01_DATA')):old_meta};exporter.t.write(dev/'01_DATA/CATALOG/RAW_DERIVATIVES.json',catalog)
    destination=tmp_path/'transfer'
    with zipfile.ZipFile(PACKAGE/'GENOS_RAW_EXPORT_20261023_R2.zip') as z:
        assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist());z.extractall(destination)
    root=destination/'GENOS_RAW_EXPORT_20261023_R2'
    out=tmp_path/'out'
    env={**os.environ,'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH',''),'PYTHONDONTWRITEBYTECODE':'1'}
    cmd=['bash',str(root/'GENOS_RAW_EXPORT_RUN_20261023_R2.txt'),'--dev',str(dev),'--output',str(out)]
    result=subprocess.run(cmd,cwd=destination,env=env,text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'RAW_EXPORT_EXIT=0' in result.stdout and 'EXPORTED' in result.stdout
    assert str(long_origin.relative_to(dev)) in members(out/'RAW_INPUT.zip')
    (root/'export_inputs.py').write_text('tampered')
    result=subprocess.run(cmd,cwd=destination,env=env,text=True,capture_output=True,timeout=30)
    assert result.returncode!=0 and 'EXPORT_CODE_CHANGED' in result.stdout
