import json,sys,importlib.util
from pathlib import Path
R=Path.cwd();A=R/'04_EXPERIMENTS/ADR/ADR-0522-scoped-reference-returns'
arm=sys.argv[1];prior='adr_0521' if arm=='baseline' else 'adr_0522'
spec=importlib.util.spec_from_file_location('chosen_bootstrap',R/'06_TOOLS/EXPERIMENTS'/prior/'bootstrap.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b);b.pin()
sys.path[:0]=[str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS'),str(R/'06_TOOLS/EXPERIMENTS/adr_0520')]
from test_returns import fixture
from test_contract import roots
from semantic_runtime.contracts import write,sha
for cid in ('narrow-return','independent-root','multi-target','recursive-links'):
 nav=fixture(multi=cid=='multi-target');rs=roots(nav,*(['a','c'] if cid=='independent-root' else ['a']));g=nav.walk(rs)
 path=A/'artifacts/run-001'/arm/(cid+'.json');path.parent.mkdir(parents=True,exist_ok=True)
 write(path,{'case_id':cid,'graph':g,'source_coordinates':{sid:{'doc_id':'d','node':int(s['unit_id'][1:])} for sid,s in nav.sources.items()},'fixture_sha256':sha(Path(__file__).with_name('test_returns.py'))})
 print(arm,cid,g['source_ids'],flush=True)
