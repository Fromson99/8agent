from common import *
S=ROOT/read(DES/'candidate-path.json')['snapshot']
p=S/'05_TESTS/CONTRACTS/test_wiki_workspace.py';s=p.read_text().replace('import json\n','import json\nimport os\n').replace("root = Path(__file__).resolve().parents[2]", "root = Path(os.environ.get('LOOP_TEST_REPOSITORY_ROOT', Path(__file__).resolve().parents[2]))").replace("env.repo.publication(stage['publication_id'])","env.repo.publication(stage['publication_id'], {'fictional'})");p.write_text(s)
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1289/freeze.py').read_text();s=s.replace(" if '02_BACKEND/semantic_runtime/legal_agent/compact_model_input.py'", " if '02_BACKEND/semantic_runtime/ontology_work/configuration.py' in d.get('files',{}):\n  extra='02_BACKEND/semantic_runtime/ontology_work/mapped_authoring.py';d['files'][extra]=sha(S/extra);changed=True\n if '02_BACKEND/semantic_runtime/legal_agent/compact_model_input.py'")
(Path(__file__).parent/'freeze.py').write_text(s)
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1289/check.py').read_text();s=s.replace("WORKFLOW_TEST_CODE_ROOT=str(C)", "WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_ONTOLOGY_CODE_ROOT=str(C),LOOP_TEST_REPOSITORY_ROOT=str(ROOT)")
s=s.replace("sys.path[:0]=[str(C/'02_BACKEND'),str(C)]", "sys.path[:0]=[str(C/'02_BACKEND'),str(C/'03_FRONTEND/APPS/legal-knowledge-streamlit'),str(C/'05_TESTS/CONTRACTS'),str(ROOT/'90_RUNTIME/streamlit-knowledge-design/python'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1289'),str(C)]")
s=s.replace("[str(ROOT/n) for n in paths]", "[str(C/n if n.startswith(('05_TESTS/CONTRACTS/test_wiki_workspace.py','05_TESTS/CONTRACTS/test_genos_answer_reference_display.py','03_FRONTEND/')) else ROOT/n) for n in paths]")
s=s.replace("'tests':{str(p):sha(ROOT/p) for p in paths}", "'tests':{str(p):sha(C/p if (C/p).is_file() else ROOT/p) for p in paths}")
s=s.replace("paths=args.tests or ['06_TOOLS/EXPERIMENTS/adr_1289/test_server_computation.py']", "paths=args.tests or ['06_TOOLS/EXPERIMENTS/adr_1292/test_connections.py']")
(Path(__file__).parent/'check.py').write_text(s)
