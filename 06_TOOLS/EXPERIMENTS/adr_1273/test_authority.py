from pathlib import Path
import importlib.util,json,hashlib
import pytest
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1273-gold-user-directed-main-binding/artifacts'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False)+'\n')

def fixture(tmp_path,basis='USER_DIRECTED_CUTOVER',mutation=None):
 f=json.loads((A/'freeze.json').read_text());p=R/f['code_root']/f['target'];assert sha(p)==f['after']
 spec=importlib.util.spec_from_file_location('gold_authority_candidate',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.ROOT=tmp_path;m.HERE=tmp_path/'gold';m.HERE.mkdir();m.ACTIVE_POINTER=tmp_path/'ACTIVE.json'
 rel=tmp_path/'release';rel.mkdir();code=rel/'code';code.mkdir();(code/'engine.py').write_text('pinned')
 (m.HERE/'marker.txt').write_text('connector')
 auth={'authorized_by':'user','authorization_text':'지금까지 된거 메인에 싹다 반영해','quality_gate_override':True}
 validation={'structural_checks_passed':True}
 if mutation=='nonuser':auth['authorized_by']='agent'
 if mutation=='emptytext':auth['authorization_text']=' '
 if mutation=='waiver':auth['quality_gate_override']=False
 if mutation=='structural':validation['structural_checks_passed']=False
 write(rel/'authorization.json',auth);write(rel/'validation.json',validation)
 manifest={'deployment_basis':basis,'code_root':'release/code','files':{'engine.py':sha(code/'engine.py')},'data_path':'original-generation',
 'authorization_sha256':sha(rel/'authorization.json'),'validation_sha256':sha(rel/'validation.json')}
 if mutation=='basis':manifest['deployment_basis']='OTHER'
 write(rel/'release.json',manifest)
 active={'deployment_basis':basis,'release_id':'chosen','release_manifest_sha256':sha(rel/'release.json'),'manifest_path':'release/release.json'}
 binding={'schema_version':'selected-main-gold-port-v2','engine_release_id':'chosen','engine_manifest_sha256':sha(rel/'release.json'),
 'engine_root':'release/code','engine_files':manifest['files'],'data_path':'original-generation','files':{},'connector_files':{'marker.txt':sha(m.HERE/'marker.txt')},
 'main_authorization':{'release_id':'chosen','authorization_sha256':manifest['authorization_sha256'],'validation_sha256':manifest['validation_sha256']}}
 if mutation=='missing':binding.pop('main_authorization')
 if mutation=='grant_release':binding['main_authorization']['release_id']='other'
 if mutation=='grant_hash':binding['main_authorization']['authorization_sha256']='0'*64
 if mutation=='active_id':active['release_id']='other'
 if mutation=='authbytes':(rel/'authorization.json').write_text('{}')
 if mutation=='enginebytes':(code/'engine.py').write_text('changed')
 if mutation=='connectorbytes':(m.HERE/'marker.txt').write_text('changed')
 if mutation=='manifestbytes':(rel/'release.json').write_text('{}')
 write(m.ACTIVE_POINTER,active);write(m.HERE/'binding.json',binding)
 return m,binding

def test_explicit_official_user_cutover_keeps_exact_engine(tmp_path):
 m,b=fixture(tmp_path);assert m.engine_binding()==b

def test_existing_qualified_main_needs_no_new_grant(tmp_path):
 m,b=fixture(tmp_path,'VALIDATED_ADR_PROMOTION','missing');assert m.engine_binding()==b

@pytest.mark.parametrize('mutation',['nonuser','emptytext','waiver','structural','basis','missing','grant_release','grant_hash','active_id','authbytes','enginebytes','connectorbytes','manifestbytes'])
def test_unapproved_or_changed_release_rejected(tmp_path,mutation):
 m,b=fixture(tmp_path,mutation=mutation)
 with pytest.raises(RuntimeError):m.engine_binding()

def test_unknown_deployment_basis_rejected(tmp_path):
 m,b=fixture(tmp_path,'UNKNOWN')
 with pytest.raises(RuntimeError):m.engine_binding()
