"""Permanent-v2 pytest bootstrap.

The historical regression suite imports tool modules through the old ``scripts``
package name.  Keep that import surface test-only while resolving the modules
from the canonical tools root; production code must use ``06_TOOLS/run_tool.py``.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_TOOL_ROOT = WORKSPACE_ROOT / "06_TOOLS" / "EXPERIMENTS"
TOOL_ROOTS = (
    WORKSPACE_ROOT / "06_TOOLS" / "COMMANDS",
    *sorted(path for path in EXPERIMENT_TOOL_ROOT.rglob("*") if path.is_dir()),
)
REGRESSION_TESTS_ROOT = WORKSPACE_ROOT / "05_TESTS" / "REGRESSION"

os.environ.setdefault("LAWRAG_WORKSPACE_ROOT", str(WORKSPACE_ROOT))
os.environ.setdefault("LAWRAG_TOOL_WORKSPACE_ROOT", str(WORKSPACE_ROOT))

for tool_root in reversed(TOOL_ROOTS):
    if str(tool_root) not in sys.path:
        sys.path.insert(0, str(tool_root))

scripts = types.ModuleType("scripts")
scripts.__path__ = [str(path) for path in TOOL_ROOTS]
scripts.__package__ = "scripts"
sys.modules.setdefault("scripts", scripts)

tests = types.ModuleType("tests")
tests.__path__ = [str(REGRESSION_TESTS_ROOT)]
tests.__package__ = "tests"
sys.modules.setdefault("tests", tests)


# Shared small source-only serving fixture; never imports retired authoring runners.
import pytest
import json
import sqlite3
from semantic_runtime.contracts import sha, write
from lawrag.pipeline import glossary_assembly as assembly, glossary_v1 as v1

@pytest.fixture
def term_glossary(tmp_path):
    path = tmp_path / 'dictionary'; path.mkdir()
    with sqlite3.connect(path / 'dictionary.sqlite') as db:
        assembly.tables(db)
        v1.add_entry(db, 'fixture:day', 'econedu', '영업일', '영업일은 은행이 영업하는 날을 말한다.', english='Business Day')
    knowledge = tmp_path / 'knowledge'; knowledge.mkdir()
    schemas = {
        'graph': 'CREATE TABLE label(source,node_id,normalized); CREATE TABLE node(source,id,payload);',
        'lookup': 'CREATE TABLE surface(key,source,node_id,label,kind);',
        'translations': 'CREATE TABLE unit(source,node_id,kind,id,original_sha256,status,needs_review,origin_locator,original,translation_ko);',
        'identity': 'CREATE TABLE concept_mapping(id,source,node_id,entry_id,status,reason); CREATE TABLE uri_alias(source,alias_uri,canonical_uri,status,evidence_id);',
        'legal': 'CREATE TABLE entry(id,label,homonym); CREATE TABLE edge(id,source_id,target_id,code,status,reason);',
    }
    for name, schema in schemas.items():
        with sqlite3.connect(knowledge / (name + '.sqlite')) as db:
            db.executescript(schema)
    with sqlite3.connect(knowledge / 'lookup.sqlite') as db:
        db.execute('INSERT INTO surface VALUES (?,?,?,?,?)', ('자금지원', 'fibo', 'loan', '자금지원', 'TRANSLATION'))
    with sqlite3.connect(knowledge / 'graph.sqlite') as db:
        db.execute('INSERT INTO node VALUES (?,?,?)', ('fibo', 'loan', json.dumps({'definitions': ['가상 자금지원 정의']})))
    manifest = {'schema_version': 'glossary-knowledge-bundle-v1', 'dictionary_sha256': sha(path / 'dictionary.sqlite'), 'counts': {},
                'files': [{'path': p.name, 'sha256': sha(p), 'bytes': p.stat().st_size} for p in sorted(knowledge.glob('*.sqlite'))]}
    write(knowledge / 'manifest.json', manifest)
    write(path / 'report.json', {'schema_version': assembly.VERSION, 'dictionary_sha256': manifest['dictionary_sha256'],
                                'counts': {}, 'collection': {'complete': True},
                                'knowledge_binding': {'path': str(knowledge), 'manifest_sha256': sha(knowledge / 'manifest.json')}})
    return path
