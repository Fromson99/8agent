import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
CODE=Path(os.environ.get('AD_TEST_CODE',ROOT/'02_BACKEND/lawrag/research/candidates/adr_0657/ad-sql/snapshot'))
sys.path.insert(0,str(ROOT/'02_BACKEND'))
import semantic_runtime
semantic_runtime.__path__.insert(0,str(CODE/'02_BACKEND/semantic_runtime'))
import semantic_runtime.legal_agent
semantic_runtime.legal_agent.__path__.insert(0,str(CODE/'02_BACKEND/semantic_runtime/legal_agent'))
import lawrag.pipeline
lawrag.pipeline.__path__.insert(0,str(CODE/'02_BACKEND/lawrag/pipeline'))

sys.path.insert(0,str(ROOT/'05_TESTS/CONTRACTS'))
import runpy
_contract_fixtures=runpy.run_path(str(ROOT/'05_TESTS/conftest.py'))
term_glossary=_contract_fixtures['term_glossary']
from test_structure_first_search import structured_generation
