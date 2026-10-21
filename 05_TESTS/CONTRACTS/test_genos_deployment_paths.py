"""Operator defaults bind GENOS paths without changing unconfigured local runs."""
import hashlib
import json
from pathlib import Path
import pytest
from semantic_runtime import deployment_paths as paths

def configuration(root,generation):
    manifest=generation/'manifest.json';generation.mkdir();manifest.write_text('{"fixture":true}')
    value={'schema_version':paths.SCHEMA,'selection':'operator-fixed','generation':str(generation),
           'runtime':str(root/'runtime'),'state':None,'generation_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()}
    p=root/paths.CONFIG;p.parent.mkdir();p.write_text(json.dumps(value));return p,value

def test_no_config_preserves_existing_selection(tmp_path):
    env={'GENOS_GENERATION':'existing','GENOS_RUNTIME_DIR':'existing-runtime','GENOS_LLM_KEY':'test-secret'}
    before=dict(env);assert paths.install(tmp_path,environment=env) is None;assert env==before

def test_operator_paths_override_stale_selection_without_touching_model_settings(tmp_path):
    p,value=configuration(tmp_path,tmp_path/'generation')
    env={'GENOS_GENERATION':'stale','GENOS_RUNTIME_DIR':'stale','GENOS_STATE_DIR':'stale-state','GENOS_LLM_KEY':'fixture-key'}
    assert paths.install(tmp_path,environment=env)==value
    assert env=={'GENOS_GENERATION':value['generation'],'GENOS_RUNTIME_DIR':value['runtime'],'GENOS_LLM_KEY':'fixture-key'}
    paths.verify_generation(value,Path(value['generation']))

def test_mount_is_lazy_and_manifest_drift_is_rejected(tmp_path):
    p,value=configuration(tmp_path,tmp_path/'generation')
    manifest=Path(value['generation'])/'manifest.json';manifest.unlink()
    assert paths.install(tmp_path,environment={})==value
    manifest.write_text('changed')
    with pytest.raises(ValueError):paths.verify_generation(value,Path(value['generation']))

@pytest.mark.parametrize('key,bad',[('schema_version','wrong'),('generation','relative'),('runtime','relative'),('state','/another-state'),('generation_manifest_sha256','wrong')])
def test_invalid_binding_is_rejected_before_mutating_environment(tmp_path,key,bad):
    p,value=configuration(tmp_path,tmp_path/'generation');value[key]=bad;p.write_text(json.dumps(value))
    env={'GENOS_GENERATION':'preserve'}
    with pytest.raises(ValueError):paths.install(tmp_path,environment=env)
    assert env=={'GENOS_GENERATION':'preserve'}

def test_config_symlink_is_rejected(tmp_path):
    p,value=configuration(tmp_path,tmp_path/'generation');saved=p.with_name('original.json');p.rename(saved);p.symlink_to(saved)
    with pytest.raises(ValueError):paths.install(tmp_path,environment={})

@pytest.mark.parametrize('mode',['oracle','1','true'])
def test_oracle_preserves_explicit_external_runtime_and_ignores_stale_sqlite_binding(tmp_path,mode):
    p,value=configuration(tmp_path,tmp_path/'generation')
    Path(value['generation']).rename(tmp_path/'offline-sqlite-generation')
    env={'DP':mode,'GENOS_RUNTIME_DIR':'/external-nfs/oracle-runtime','GENOS_STATE_DIR':'/external-nfs/state'}
    before=dict(env)
    assert paths.install(tmp_path,environment=env) is None
    assert env==before
