"""Post-run reader correction; frozen runner/product/scripts remain untouched."""
from common import *
import importlib.util
f=read(DES/'freeze-live.json');sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
import semantic_runtime.legal_agent
name='semantic_runtime.legal_agent.journal_storage'
path=ROOT/'02_BACKEND/semantic_runtime/legal_agent/journal_storage.py'
spec=importlib.util.spec_from_file_location(name,path)
reader=importlib.util.module_from_spec(spec);sys.modules[name]=reader;spec.loader.exec_module(reader)
put(ART/'audit-preparation-correction.json',{
 'failed_command':'.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1203/audit_result.py cm-009',
 'observed_error':"ModuleNotFoundError: No module named 'semantic_runtime.legal_agent.journal_storage'",
 'reason':'Frozen candidate has plain journal reader; the later working compression reader is not among its 468 serving files.',
 'correction':'Load read-only compatible working journal reader by exact file and keep its restoring row factory. Execute audits after run; no change to frozen scripts or product.',
 'reader_path':str(path.relative_to(ROOT)),'reader_sha256':sha(path),
 'composition_audit_static_issue':'Frozen copied helper lacks journal_connect import in its completed-answer branch. Inject only post-run reader; no answer branch reached here.',
 'new_model_calls':0})
sys.argv=['audit_result.py','cm-009']
for script in ('audit_result.py','audit_storage.py','composition_audit.py'):
 p=Path(__file__).parent/script
 source=p.read_text().replace('j.row_factory=sqlite3.Row;','')
 exec(compile(source,str(p),'exec'),{'__name__':'__main__','__file__':str(p),'journal_connect':reader.connect})
