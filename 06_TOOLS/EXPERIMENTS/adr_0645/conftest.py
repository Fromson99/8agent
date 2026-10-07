"""Explicit isolated imports for ordinary candidate contract development."""
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'02_BACKEND'))
import semantic_runtime.legal_agent
import lawrag.pipeline
candidate=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0645/procedure'
snapshot=candidate/os.environ.get('SHORTCUT_CANDIDATE_SNAPSHOT','snapshot')
semantic_runtime.legal_agent.__path__.insert(0,str(snapshot/'02_BACKEND/semantic_runtime/legal_agent'))
lawrag.pipeline.__path__.insert(0,str(snapshot/'02_BACKEND/lawrag/pipeline'))

import semantic_runtime
semantic_runtime.__path__.insert(0,str(snapshot/'02_BACKEND/semantic_runtime'))
sys.path.insert(0,str(ROOT/'05_TESTS/CONTRACTS'))
import runpy
_contract_fixtures=runpy.run_path(str(ROOT/'05_TESTS/conftest.py'))
term_glossary=_contract_fixtures['term_glossary']
from test_structure_first_search import structured_generation
