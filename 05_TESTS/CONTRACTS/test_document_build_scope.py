import json
from pathlib import Path

import pytest

from lawrag.pipeline import document_scope as scope
from semantic_runtime.contracts import sha


def fixture_scope(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    documents = []
    for name, source, suffix in [('rule','external','.html'),('form','internal','.hwp')]:
        p = data / (name + suffix)
        p.write_text(name)
        documents.append({'name':name, 'files':[{'path':p.name,'sha256':sha(p),
            'role':'body','source':source,'external_source':'kofia' if source=='external' else 'forms',
            'kind':'kofia-rule' if source=='external' else 'internal'}]})
    p = data/'scope.json'
    p.write_text(json.dumps({'schema_version':'document-build-scope-v1','scope_id':'test','documents':documents}))
    return data,p


def test_explicit_scope_does_not_discover_other_documents(tmp_path):
    data,p = fixture_scope(tmp_path)
    (data/'unrequested.pdf').write_bytes(b'excluded')
    plan,report = scope.collect(data,p,emit=lambda _:None)
    assert {r['name'] for r in plan['files']} == {'rule','form'}
    assert not plan['all_corpus'] and report['ok']
    assert all(r['source_metadata']['export_allowed'] is False for r in plan['files'])
    # Explicit internal exclusion must not even read the restricted original.
    (data/'form.hwp').unlink()
    plan,report = scope.collect(data,p,exclude_internal=True,emit=lambda _:None)
    assert [r['name'] for r in plan['files']] == ['rule']
    assert report['excluded'][0]['reason'] == 'internal_excluded'


def test_changed_missing_original_and_pointer_fail_closed(tmp_path):
    data,p = fixture_scope(tmp_path)
    pointer = data/'CATALOG/BUILD_SCOPE.json'
    pointer.parent.mkdir()
    pointer.write_text(json.dumps({'path':p.name,'sha256':sha(p)}))
    assert scope.configured(data) == p
    (data/'rule.html').write_text('changed')
    with pytest.raises(ValueError,match='original changed'):
        scope.collect(data,p)
    (data/'rule.html').unlink()
    with pytest.raises(FileNotFoundError):
        scope.collect(data,p)
    p.write_text('{}')
    with pytest.raises(ValueError,match='pointer/hash mismatch'):
        scope.configured(data)


@pytest.mark.parametrize('path', ['../escape.hwp','/tmp/escape.hwp'])
def test_scope_cannot_escape_data_root(tmp_path,path):
    with pytest.raises(ValueError,match='relative'):
        scope.local_path(tmp_path,path)


def test_scope_selects_one_body_but_keeps_attachment(tmp_path):
    data,p=fixture_scope(tmp_path)
    value=json.loads(p.read_text())
    doc=value['documents'][0]
    for name,role in [('rule.hwp','body'),('annex.hwp','attachment')]:
        file=data/name;file.write_text(name)
        doc['files'].append({**doc['files'][0],'path':name,'sha256':sha(file),'role':role})
    p.write_text(json.dumps(value))
    plan,report=scope.collect(data,p,emit=lambda _:None)
    assert {Path(r['path']).name for r in plan['files']} == {'rule.html','form.hwp','annex.hwp'}
    assert any(r['reason']=='alternate_body_representation' for r in report['excluded'])


def test_maintained_cli_uses_default_scope(tmp_path,monkeypatch):
    import importlib.util
    from lawrag.pipeline import genos_stages,genos_corpus,genos_build
    data,p=fixture_scope(tmp_path)
    pointer=data/'CATALOG/BUILD_SCOPE.json';pointer.parent.mkdir()
    pointer.write_text(json.dumps({'path':p.name,'sha256':sha(p)}))
    monkeypatch.setattr(genos_stages,'offline_data_root',lambda root:data)
    monkeypatch.setattr(genos_corpus,'collect',lambda *a,**kw:pytest.fail('unscoped collection'))
    monkeypatch.setattr(genos_stages,'execute',lambda *a,**kw:pytest.fail('unexpected processing'))
    file=genos_build.ROOT/'06_TOOLS/COMMANDS/genos_data_stages.py'
    spec=importlib.util.spec_from_file_location('scoped_build_cli',file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.main(['--run-id','scoped','--check-only'])==0
    result=json.loads(next((data/'LOGS/scoped').glob('result-*.json')).read_text())
    assert result['ok'] and result['selected']==2
    with pytest.raises(SystemExit):
        module.main(['--run-id','conflict','--only-internal-pdf','--check-only'])
