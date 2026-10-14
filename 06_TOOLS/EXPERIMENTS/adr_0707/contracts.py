"""Test-only fixture access; candidate runtime packages take precedence."""
from pathlib import Path
import importlib,sys
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0707/title-entry/snapshot/02_BACKEND'
if '--baseline' in sys.argv:
 sys.argv.remove('--baseline');C=R/'02_BACKEND/lawrag/research/candidates/adr_0706/fused-entry/revisions/rev-001/snapshot/02_BACKEND'
sys.dont_write_bytecode=True
sys.path[:0]=[str(C),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS/REGRESSION/core')]
for p in sorted(C.rglob('__init__.py'),key=lambda p:len(p.parts)):
 parts=p.parent.relative_to(C).parts
 if not parts:continue
 mod=importlib.import_module('.'.join(parts));other=R/'02_BACKEND'/p.parent.relative_to(C)
 if other.is_dir():mod.__path__.append(str(other))
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
