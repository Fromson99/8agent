"""Reuse only the existing read-only publication verifier; never its write actions."""
from pathlib import Path
import hashlib, importlib.util, json, logging, sys, time

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261103-rag-ontology-console-integration'
sys.dont_write_bytecode=True
logging.disable(logging.CRITICAL)
path=ROOT/'06_TOOLS/maintenance/publish_gold_ontology_samples.py'
spec=importlib.util.spec_from_file_location('readonly_publication_verifier',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
artifacts=[]
def write(name,value):
    if name=='verification.json':
        value.update(verifier_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                     seconds=time.monotonic()-start,diagnostic_only=True,data_writes=0,artifacts=artifacts)
        (OUT/'oracle-readonly.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    else:
        # Original source content stays in the existing publication records.
        raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
        artifacts.append({'name':name,'json_sha256':hashlib.sha256(raw).hexdigest(),'items':len(value)})
module.write=write
start=time.monotonic()
module.verify()
