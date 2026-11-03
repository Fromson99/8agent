from common import *
p=Path(__file__).parent/'oracle.py';old=p.read_text();saved=ART/'oracle-create/runner.py';assert not saved.exists();saved.write_text(old)
s=old.replace("glossary=domain.glossary.candidates(['주식']);domain.glossary.verify_candidates(glossary)\n    result['glossary_restored']=len(glossary['candidates'])", "if args.mode=='create':\n     glossary=domain.glossary.candidates(['주식']);domain.glossary.verify_candidates(glossary)\n     result['glossary_restored']=len(glossary['candidates'])\n    else:\n     domain.glossary.check();result['glossary_binding_verified']=True")
p.write_text(s)
put(ART/'oracle-create/design.json',{'runner':bind(saved),'frozen':bind(DES/'freeze.json'),'source':bind(ROOT/'04_EXPERIMENTS/ADR/ADR-1255-wiki-workspace-oracle-live/artifacts/design/originals.json'),'scope':'Local isolated synthetic contract; no operating scope addition; no model/DDL'})
