"""The one-time metadata transplant must preserve source rows and both teams."""
import importlib.util
import json
from pathlib import Path
import sqlite3
from semantic_runtime.contracts import sha


SCRIPT = Path(__file__).resolve().parents[2] / '06_TOOLS/COMMANDS/genos_financial_union_migrate.py'


def test_metadata_transplant_does_not_duplicate_structure(tmp_path):
    spec = importlib.util.spec_from_file_location('financial_union_migration', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db_path = tmp_path / 'store.sqlite'
    db = sqlite3.connect(db_path)
    db.execute('CREATE TABLE document(document_id TEXT,name TEXT,json TEXT)')
    db.execute('CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,json TEXT)')
    db.execute('CREATE TABLE source_block(document_id TEXT,block_id TEXT,text TEXT)')
    payload = {'name': '공통법', 'source_artifact_sha256': 'a' * 64}
    db.execute('INSERT INTO document VALUES(?,?,?)', ('aaaaaaaaaaaaaaaa', '공통법', json.dumps(payload)))
    db.execute('INSERT INTO source_unit VALUES(?,?,?)', ('aaaaaaaaaaaaaaaa', '1', '{}'))
    db.execute('INSERT INTO source_block VALUES(?,?,?)', ('aaaaaaaaaaaaaaaa', '1', '원문'))
    db.commit()
    db.close()
    layout = {'files': {}}
    for team in ('risk_team', 'financial_team'):
        rel = f'RAW/external/{team}/law/공통법/공통법.xml'
        layout['files'][rel] = {'scope_document': '공통법', 'role': 'body',
                                'sha256': 'a' * 64, 'source': 'external', 'team': team}
    assert module.patch_store(db_path, [('공통법', 'aaaaaaaaaaaaaaaa', payload)], layout) == ['aaaaaaaaaaaaaaaa']
    module.verify_team_membership(db_path, [('공통법', 'aaaaaaaaaaaaaaaa', payload)], {'공통법'})
    db = sqlite3.connect(db_path)
    assert db.execute('SELECT count(*) FROM document').fetchone()[0] == 1
    assert db.execute('SELECT count(*) FROM source_unit').fetchone()[0] == 1
    assert db.execute('SELECT text FROM source_block').fetchone()[0] == '원문'
    metadata = json.loads(db.execute('SELECT json FROM document').fetchone()[0])['document_metadata']
    assert {metadata['team'], *(a['team'] for a in metadata['aliases'])} == {'risk_team', 'financial_team'}
    db.close()


def test_source_matches_pipeline_breadcrumb_name(tmp_path):
    spec = importlib.util.spec_from_file_location('financial_union_migration', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    generation = tmp_path / 'generation'
    generation.mkdir()
    db = sqlite3.connect(generation / 'store.sqlite')
    db.execute('CREATE TABLE document(document_id TEXT,name TEXT,json TEXT)')
    db.execute('CREATE TABLE source_block(document_id TEXT,block_id TEXT,text TEXT)')
    payload = {'document_metadata': {'document_title': '공통법'}}
    db.execute('INSERT INTO document VALUES(?,?,?)',
               ('aaaaaaaaaaaaaaaa', 'RAW > law > 공통법', json.dumps(payload)))
    db.execute('INSERT INTO source_block VALUES(?,?,?)', ('aaaaaaaaaaaaaaaa', '1', '원문'))
    db.commit()
    db.close()
    scope = [{'name': '공통법', 'files': [{'role': 'body', 'sha256': 'a' * 64}]}]
    assert module.source_matches(generation, scope) == [('공통법', 'aaaaaaaaaaaaaaaa', payload)]


def test_raw_admission_checks_files_when_layout_scope_differs(tmp_path, capsys):
    script = SCRIPT.parents[2] / '09_ARTIFACTS/AUDITS/20260930-financial-photo61-share/apply_shared_scope.py'
    spec = importlib.util.spec_from_file_location('financial_raw_admission', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = ['상법', *(f'문서{i}' for i in range(1, 60)), '상장회사 표준정관(2025)']
    documents, files = [], {}
    for i, name in enumerate(names):
        team = 'risk_team' if i == 0 else 'financial_team'
        rel = f'RAW/external/{team}/law/{name}/{name}.xml'
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
        identity = sha(path)
        documents.append({'name': name, 'files': [{'sha256': identity, 'role': 'body'}]})
        files[rel] = {'scope_document': name, 'sha256': identity, 'role': 'body',
                      'team': team, 'source': 'external', 'security_class': 'public'}
    scope = tmp_path / 'CATALOG/SCOPES/photo-required-80-hwpx-20260917.json'
    scope.parent.mkdir(parents=True)
    scope.write_text(json.dumps({'documents': documents}))
    layout = tmp_path / 'CATALOG/TEAM_LAYOUT.json'
    layout.write_text(json.dumps({'scope': {'path': 'different-scope.json', 'sha256': 'different'},
                                  'files': files}))
    module.ROOT, module.DATA, module.SCOPE, module.LAYOUT = tmp_path, tmp_path, scope, layout
    module.HISTORY, module.REPORT = tmp_path / 'history', tmp_path / 'receipt.json'
    module.main(False)
    assert '"shared_document_count": 1' in capsys.readouterr().out
