"""Bind release preview to the actual qualified code, without activating it."""
from common import *
import sys,resource,xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'02_BACKEND'))
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
from semantic_runtime.control import prepare
suites=ET.parse(ART/'contracts-002.xml').getroot().findall('testsuite')
assert suites and all(int(s.get('failures',0))==int(s.get('errors',0))==0 for s in suites)
seal=read(ART/'stage.json');base=read(ROOT/seal['base_pointer']['manifest_path'])
save(ART/'preview-auth.json',{'purpose':'integration_preview'})
save(ART/'preview-validation.json',{'structural_checks_passed':True,'contracts':{'path':str((ART/'contracts-002.xml').relative_to(ROOT)),'sha256':sha(ART/'contracts-002.xml')}})
prepare(ROOT,ROOT/seal['roots']['candidate'],ROOT/base['data_path'],'law-name-preview-0966',ART/'preview-auth.json',ART/'preview-validation.json',ART/'integration-preview.json')
m=read(ADR/'실험/manifest.json');binding={k:v for k,v in m['design']['code_isolation']['candidates'][0].items() if k in ('manifest_path','manifest_sha256','revision_id','revision_sha256')}
integration=read(ART/'integration-preview.json');files=base['files'].copy()
for row in integration['changes']:
    if row['after'] is None:files.pop(row['path'])
    else:files[row['path']]=row['after']
candidate=read(ROOT/binding['manifest_path']);cp={r['target_path'] for r in candidate['files']}
assert {r['path'] for r in integration['changes']}<=cp
assert files==seal['files']['candidate']
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':seal['base_pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':{}}
save(ART/'release-rebase.json',rebase)
reference={'path':str((ART/'release-rebase.json').relative_to(ROOT)),'sha256':sha(ART/'release-rebase.json')}
integration.update(candidate=binding,rebase_receipt=reference)
feature=set(read(ROOT/'09_ARTIFACTS/AUDITS/20261021-law-name-recovery/before.json'))|{'02_BACKEND/semantic_runtime/legal_agent/law_name_recovery.py'}
for row in integration['changes']:
    row['reason']='Law-name recovery implementation and derived pins' if row['path'] in feature else 'Preserve current text-length removal, fixed in both experiment arms and independently contract-tested'
save(ART/'integration.json',integration)
m['design']['release_rebase']=reference;save(ADR/'실험/manifest.json',m)
print('Sealed',len(files),'serving files;',len(integration['changes']),'changes; no activation')
