"""Explicit frozen release wiring contracts extending the completed storage arm."""
from pathlib import Path
import hashlib
import importlib.util
import json
import runpy
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'02_BACKEND'))
sys.path.insert(0,str(ROOT/'05_TESTS/CONTRACTS'))
sys.dont_write_bytecode=True
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0551-navigation-audit-release-wiring'


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    manifest=json.loads((ADR/'실험/manifest.json').read_text())
    parent=manifest['lineage']['parents'][0]
    assert sha(ROOT/parent['manifest_path'])==parent['manifest_sha256']
    saved=json.loads((ROOT/parent['manifest_path']).read_text())
    assert saved['results']['status']=='complete' and saved['reservation']['status']=='completed'
    original=runpy.run_path(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0550/run.py'))
    original['inject']()
    candidate=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0551/wired/candidate.json'
    value=json.loads(candidate.read_text())
    revision=next(r for r in value['revisions'] if r['revision_id']=='rev-001')
    assert not value['production_loadable']
    for row in revision['files']:
        assert sha(ROOT/row['frozen_path'])==row['snapshot_sha256']
    frozen=candidate.parent/'revisions/rev-001/snapshot'
    for module in ('reference_resolution','document_release'):
        original['load']('lawrag.pipeline.'+module,frozen/'02_BACKEND/lawrag/pipeline'/ (module+'.py'))
    import pytest
    common=original['load']('release_storage_fixtures',ROOT/'05_TESTS/conftest.py')
    class Fixtures:
        @pytest.fixture
        def term_glossary(self,tmp_path):return common.term_glossary.__wrapped__(tmp_path)
    class Report:
        def pytest_sessionfinish(self,session,exitstatus):
            stats=session.config.pluginmanager.get_plugin('terminalreporter').stats
            result={'schema_version':'navigation-audit-release-wiring-validation-v1',
                    'structural_checks_passed':exitstatus==0,
                    'tests':{k:len(stats.get(k,[])) for k in ('passed','failed','error','skipped')},
                    'parent_manifest_sha256':parent['manifest_sha256'],
                    'parent_storage_validation_sha256':sha(ROOT/saved['runs'][0]['artifact_path']),
                    'candidate_revision_sha256':revision['revision_sha256'],
                    'unchanged_storage_implementation':True,'live_llm_calls':0,
                    'legal_answer_quality_measured':False,'request_latency_measured':False}
            output=ADR/'artifacts/run-001/result.json';output.parent.mkdir(exist_ok=True)
            with output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    return pytest.main(['-q','-p','no:cacheprovider',
        str(frozen/'05_TESTS/CONTRACTS/test_navigation_release_audit.py'),
        str(frozen/'05_TESTS/CONTRACTS/test_reference_resolution.py'),
        str(ROOT/'05_TESTS/CONTRACTS/test_document_release_stages.py'),
        str(ROOT/'02_BACKEND/lawrag/research/candidates/adr_0550/compact/revisions/rev-002/snapshot/05_TESTS/CONTRACTS/test_navigation_storage.py')],
        plugins=[Fixtures(),Report()])


if __name__=='__main__':raise SystemExit(main())
