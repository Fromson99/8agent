import json,sys,time
from pathlib import Path
import pytest
from test_compute import env,module,opened,call


@pytest.mark.parametrize('old_mode',['existing-http','same-pod','wrong',''])
def test_health_requires_no_parser_environment(env,monkeypatch,old_mode):
    monkeypatch.setenv('LEGAL_PIPELINE_PARSER_MODE',old_mode)
    monkeypatch.setenv('GENOS_STRUCTURE_CONFIG','/absent/secret.yaml')
    monkeypatch.setenv('GENOS_PREPROCESSOR_URL','invalid secret URL')
    monkeypatch.setenv('GENOS_PREPROCESSOR_SHARED_ROOT','/absent/shared')
    monkeypatch.delenv('GENOS_LLM_URL',raising=False)
    actual=module('skip_config',env.root/'parser_config.py')
    monkeypatch.setattr(env.api,'parser_config',actual)
    h=env.api.handle({'API_TYPE':'HEALTH'})
    assert h['preprocessor']['ready'] and h['preprocessor']['preprocessor_enabled'] is False
    assert h['preprocessor']['required_environment']==[] and 'secret' not in json.dumps(h)
    a,_=opened(env)
    assert call(env,a,'CANCEL')['state']=='CANCELLED'
    assert actual.environment()[1]['GENOS_PDF_PARSER']=='skip'


def test_legacy_probe_disabled_without_config_lookup(env,monkeypatch):
    monkeypatch.setattr(env.api.probe_runtime,'inspect',lambda *a:pytest.fail('must not look for YAML'))
    assert not env.api.handle({'API_TYPE':'PROBE_HEALTH'})['preprocessor']['ready']
    h=env.api.handle({'API_TYPE':'HEALTH'});arc={'sha256':'a'*64,'bytes':1}
    with pytest.raises(ValueError,match='PROBE_DISABLED'):
        env.api.handle(dict(API_TYPE='OPEN',handle='a'*32,handle_token='b'*64,instance=h['instance'],code_sha256=h['code_sha256'],parser_config_sha256=h['preprocessor']['config_sha256'],archives={'raw':arc,'support':arc},deadline=time.time()+600,purpose='document-format-probe-v1'))
    assert not env.api.HANDLES


def test_pdf_local_fallback_blocked_before_file_or_model_access(env,monkeypatch):
    from lawrag.core import parse_adapter
    monkeypatch.setenv('GENOS_PDF_PARSER','skip')
    monkeypatch.setattr(parse_adapter,'is_born_digital',lambda *a:pytest.fail('no PDF inspection before bypass'))
    for fn in (parse_adapter.parse_pdf,parse_adapter.pdf_parser_identity):
        with pytest.raises(ValueError,match='BYPASSED_BY_USER'):fn(Path('/absent/file.pdf'))


def test_worker_disables_conversion_and_review_even_with_stale_environment(env,monkeypatch):
    actual=module('skip_config_contract',env.root/'parser_config.py')
    monkeypatch.setenv('GENOS_PREPROCESSOR_TRANSPORT','pod')
    mode,overrides=actual.environment()
    assert mode=='skip' and overrides['STRUCTURE_RECIPE_VLM']=='off' and overrides['GENOS_PDF_CONVERSION']=='off'
    command=env.w.stage_commands(env.root,'test')[0][1]
    assert command[command.index('--pdf-conversion')+1]=='off'
    assert command[command.index('--structure-vlm')+1]=='off'
