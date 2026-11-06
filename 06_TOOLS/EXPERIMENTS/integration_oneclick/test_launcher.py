import ast,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('oneclick',Path(__file__).with_name('launcher.py'));launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
def test_rendered_runner_is_current_strict_stream_and_full_suite(tmp_path):
    launcher.write_runner(tmp_path,9998,'fixture-no-model')
    for p in tmp_path.glob('*.py'):ast.parse(p.read_text())
    setup=(tmp_path/'setup.py').read_text();live=(tmp_path/'live_public.py').read_text()
    assert launcher.BASE.name in setup and 'ADR-1350-' not in setup
    assert launcher.BASE.name+'/artifacts/transport' in setup
    assert setup.index('builder.main()')<setup.index('ac.freeze(can)')
    assert 'candidate-matrix.json' in live and 'total>=1560' in live and 'total>=80' not in live
    assert "['plan']['cases']" not in live and "case['execution']=='PUBLIC_API'" in live
    assert "request_encoder=lambda body:{**provider_request(body),'stream':True}" in live
    assert "out['stream']=True" in (tmp_path/'audit.py').read_text()
    assert 'B03-03' in setup and 'B03-17' in setup
    assert 'MANUAL_REVIEW_REQUIRED' in (tmp_path/'review.py').read_text()
    assert '제공자 변경만으로' not in (tmp_path/'review.py').read_text()
def test_status_does_not_start_model_or_reserve(monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(launcher,'LATEST',tmp_path/'absent.json')
    monkeypatch.setattr(launcher,'BASE',tmp_path)
    monkeypatch.setattr(launcher.sys,'argv',['launcher','--status'])
    monkeypatch.setattr(launcher,'run',lambda *a,**k: (_ for _ in ()).throw(AssertionError('must not execute')))
    assert launcher.main()==0
    assert '진행 중' in capsys.readouterr().out

def test_new_preparation_reaches_all_commands_without_model(monkeypatch,tmp_path):
    import hashlib,types
    root=tmp_path;adrroot=root/'04_EXPERIMENTS/ADR';source=adrroot/'ADR-1351-template';base=adrroot/'ADR-1362-base'
    manifest={'results':{'status':'complete'},'reservation':{'status':'completed'}}
    for p in (source,base):
        (p/'artifacts/design').mkdir(parents=True);(p/'실험').mkdir();(p/'실험/manifest.json').write_text(json.dumps(manifest))
    (source/'artifacts/run-completed.json').write_text('{}')
    (base/'artifacts/design/candidate-repaired.json').write_text(json.dumps({'code_root':'pinned','selected_files':{'file':hashlib.sha256(b'verified').hexdigest()}}))
    (root/'pinned').mkdir();(root/'pinned/file').write_bytes(b'verified');(root/'file').write_bytes(b'concurrent')
    latest=root/'latest.json';commands=[]
    def run(cmd,**kwargs):
        commands.append(cmd)
        if Path(cmd[1]).name=='setup.py':
            config=adrroot/'ADR-1363-integration-oneclick-provider-repeat/artifacts/design/providers.json'
            config.parent.mkdir();config.write_text(json.dumps({'parasail':{}}))
        if 'new' in cmd:
            destination=adrroot/'ADR-1363-integration-oneclick-provider-repeat';(destination/'artifacts').mkdir(parents=True)
    for name,value in [('ROOT',root),('ADRROOT',adrroot),('SOURCE',source),('BASE',base),('LATEST',latest)]:monkeypatch.setattr(launcher,name,value)
    (root/'06_TOOLS/EXPERIMENTS').mkdir(parents=True)
    monkeypatch.setattr(launcher,'run',run)
    monkeypatch.setattr(launcher,'write_runner',lambda d,*args:[(d/n).write_text('') for n in ('setup.py','test_runner.py','live_public.py','freeze.py')])
    import httpx
    monkeypatch.setattr(httpx,'get',lambda *args,**kw:types.SimpleNamespace(raise_for_status=lambda:None,json=lambda:{}))
    monkeypatch.setattr(launcher.sys,'argv',['launcher','--new','--prepare-only'])
    assert launcher.main()==0
    assert [Path(c[1]).name for c in commands[1:]]==['setup.py','test_runner.py','live_public.py','freeze.py']
    assert commands[3][-1]=='--preflight'
    assert latest.exists() and (root/'file').read_bytes()==b'concurrent'


def test_provider_screen_requires_committed_full_answer(tmp_path,monkeypatch):
    import gzip
    import runpy
    launcher.write_runner(tmp_path,9999,'fixture-no-model')
    monkeypatch.syspath_prepend(str(tmp_path))
    classify=runpy.run_path(str(tmp_path/'matrix.py'))['classify']
    prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1366-assessment-question-scope-contract/artifacts/public-live'
    for case,expected in [('B03-03','PARTIAL_OR_UNVERIFIED'),('B03-17','EXPLANATION_REVIEW_REQUIRED')]:
        cell=prior/(case+'-parasail')
        result=json.loads((cell/'result.json').read_text())
        with gzip.open(cell/'turn-1/response.json.gz','rt') as stream:
            outcome=json.load(stream)['body']['assembly']['term_agent']['accepted_outcome']
        result['turns'][0]['accepted_outcome']=outcome
        assert classify(result,{'budget_matches':True})==expected


def test_offline_endpoint_does_not_block_other_profiles(tmp_path,monkeypatch):
    import runpy
    launcher.write_runner(tmp_path,9999,'fixture-no-model')
    admit=runpy.run_path(str(tmp_path/'provider_admission.py'))['admit']
    params=['response_format','structured_outputs','reasoning']
    profiles={name:{'tag':name} for name in ('a','b','c','d')}
    endpoints=[{'tag':'a','status':0,'supported_parameters':params},
               {'tag':'b','status':1,'supported_parameters':params},
               {'tag':'c','status':0,'supported_parameters':['reasoning']}]
    accepted,skipped=admit(profiles,endpoints)
    assert list(accepted)==['a'] and set(skipped)=={'b','c','d'}


def test_large_index_preserves_digest_size_and_detects_tampering(tmp_path,monkeypatch):
    import pytest
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    from artifact_index import seal,digest,verify_inventory,write_raw_json
    adr=tmp_path/'ADR-9999-fixture';art=adr/'artifacts';art.mkdir(parents=True)
    data=art/'answer.txt';data.write_text('모의 응답')
    log=art/'oneclick.log';log.write_text('prepared\n')
    rows=[{'path':str(f.relative_to(tmp_path)),'sha256':digest(f),'bytes':f.stat().st_size} for f in (data,log)]
    rows[0]['description']='x'*1100000
    full={'schema_version':'adr-artifacts-v1','adr_id':'ADR-9999','files':rows}
    ref=write_raw_json(art/'original-inventory.json.gz',full)
    (art/'manifest.json').write_text(json.dumps({'raw_json':ref}))
    with log.open('a') as stream:stream.write('completed\n')
    assert seal(tmp_path,adr)==2
    index=json.loads((art/'manifest.json').read_text())
    assert index['schema_version']=='adr-artifacts-v1' and index['verified_files']==2
    assert seal(tmp_path,adr)==2
    data.write_text('다른 응답')
    with pytest.raises(ValueError,match='Artifact changed'):verify_inventory(tmp_path,tmp_path/index['verified_inventory']['path'])

def test_review_counts_only_cited_complete_originals():
    from review_public import review_response
    body = {'assembly': {'term_agent': {
        'accepted_outcome': {'disposition':'ANSWER','answer_coverage':'COVERED'},
        'evidence_inventory': [
            {'source_id': source,'document_id':'doc','available_scopes':[
                {'delivered_complete': complete,'block_ids':[block]}]}
            for source, complete, block in [('A',True,1),('A',False,2),('B',True,3)]]}},
        'answer': {'claims': [{'text':'답변','source_ids':['A']}]}}
    result = review_response(body, [{'document_id':'doc','block_ids':[1,2,3]}])
    assert result['accepted_complete_answer']
    assert result['missing_blocks']==[('doc','2'),('doc','3')]

def test_resource_stop_counts_inflight_and_preserves_physical_call_log(tmp_path):
    from worker_exit import record_resource_exit
    cell=tmp_path/'B03-17-reka'
    cell.mkdir()
    def save(path,v):path.write_text(json.dumps(v))
    def load(path):return json.loads(path.read_text())
    save(cell/'binding.json',{})
    save(cell/'calls.json',[{'status':'responded'},{'status':'started'}])
    save(cell/'resource-stop.json',{'reason':'global swap growth'})
    original=(cell/'calls.json').read_bytes()
    record_resource_exit(tmp_path,cell,'B03-17','reka',125,load,save)
    outcome=load(cell/'result.json')
    assert outcome==load(tmp_path/'RESOURCE_STOP.json')
    assert outcome['unknown']==1 and outcome['physical_calls']==2 and outcome['turns']==[]
    assert (cell/'calls.json').read_bytes()==original
