"""Code-only timeout updates must open the existing pre-update glossary cache."""
import hashlib
import json

from fastapi.testclient import TestClient
from test_genos_team_selection import team_generation
from test_legal_agent_v5 import app_for, ROOT
from semantic_runtime.navigation_agent import glossary_assets

PRE_TIMEOUT_COMPILER_SHA256 = 'ba2c6ced8da72307934e627a7a7508fb29da45e35d09fc3e0a116884a0a5d058'


def test_pre_timeout_cache_remains_usable_with_thirty_minute_v5_budget(tmp_path, team_generation):
    compiler = ROOT / '02_BACKEND/semantic_runtime/full_glossary.py'
    assert hashlib.sha256(compiler.read_bytes()).hexdigest() == PRE_TIMEOUT_COMPILER_SHA256
    manifest = json.loads((team_generation / 'manifest.json').read_text())
    binding = manifest['glossary']
    receipt_path = team_generation / binding['cache'] / binding['cache_receipt']
    receipt = json.loads(receipt_path.read_text())
    assert receipt['binding']['compiler_sha256'] == PRE_TIMEOUT_COMPILER_SHA256
    files = [team_generation / 'manifest.json', receipt_path, *receipt_path.parent.glob('*.sqlite')]
    before = {p: p.read_bytes() for p in files}
    glossary = glossary_assets(team_generation, {})
    try:
        glossary.check_unchanged()
    finally:
        glossary.close()
    app = app_for(tmp_path, team_generation)
    with TestClient(app) as client:
        assert app.state.pipeline.term_agent.profile['wall_seconds'] == 1800
        response = client.post('/v1/rag/ask', json={
            'question': '자료 목록', 'team_id': 'risk_team', 'use_llm': False,
        })
        assert response.status_code == 200, response.text
    assert {p: p.read_bytes() for p in files} == before
