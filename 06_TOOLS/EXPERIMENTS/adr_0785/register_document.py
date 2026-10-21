"""Register user-provided photo DOCX; no network/model or active-pointer change."""
from pathlib import Path
import hashlib,json,shutil,sys
R=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(R/'02_BACKEND'))
from lawrag.datasets.catalog import load_package,package_from_mapping,compose_source_set,lock_source_set
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        assert json.loads(p.read_text())==v, str(p)
        return
    with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
raw=R/'01_DATA/RAW/internal/risk_team/상위규정/그룹위험관리기준시행세칙/그룹 위험관리세칙_최종.docx'
h=sha(raw);assert h=='deb0727589aad3cc1587ffd39e8fb66ad9603b4d716f757a90c96d098a394770'
root=R/'01_DATA/PACKAGES/INTERNAL/risk-group-rules-photo-20180920/gen-20261015-r1'
root.mkdir(parents=True,exist_ok=True)
if (root/raw.name).exists():assert sha(root/raw.name)==h
else:shutil.copyfile(raw,root/raw.name)
p={'schema_version':'dataset-package-v2','package_id':'risk-group-rules-photo-20180920',
   'dataset_id':'risk-team-internal','version_id':'2018-09-20-photo-transcription',
   'variant_id':'native-docx','generation_id':'20261015-r1','source_origin':'restricted_internal',
   'security_class':'restricted','representation':'real','authority':'observation',
   'export_policy':{'allowed':False},'build':{'build_id':'risk-compare-native-20261015-r1',
      'execution_site':'outside','code_revision':sha(R/'02_BACKEND/lawrag/core/docx_ooxml.py'),
      'compiler_profile':'docx-ooxml-native-v1','capabilities':['native-docx','exact-source']},
   'artifacts':[{'logical_id':'group-risk-rules','role':'raw','path':raw.name,'sha256':h,
       'media_type':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','document_id':h[:16]}]}
p['manifest_sha256']=package_from_mapping(p).manifest_sha256
put(root/'manifest.json',p);package=load_package(root/'manifest.json')
source_set={'schema_version':'source-set-v1','source_set_id':'risk-compare-input-20261015-r1',
    'generation_id':'20261015-r1','conflict_policy':'error','members':[{'package_id':package.package_id,'priority':0}],
    'cross_dataset_relations':False}
view=compose_source_set(source_set,[package])
put(R/'01_DATA/SOURCE_SETS/risk-compare-input-20261015-r1.json',source_set)
scope={'schema_version':'document-build-scope-v1','scope_id':'risk-compare-docx-20261015-r1',
    'policy':'Explicit new input; original2018 edition and unknown current applicability retained. No external export.',
    'provenance':[{'path':str((root/'manifest.json').relative_to(R/'01_DATA')),'sha256':sha(root/'manifest.json')}],
    'documents':[{'name':'그룹 위험관리세칙','source_metadata':{
        'team':'risk_team','team_id':'risk_team','edition':'2018-09-20','current_validity':'unknown',
        'photo_transcription':True,'synthetic':False,'export_allowed':False,
        'provenance':'09_ARTIFACTS/AUDITS/20261015-risk-group-rules-photo-reconstruction/provenance.json'},
       'files':[{'path':str(raw.relative_to(R/'01_DATA')),'sha256':h,'role':'body','source':'internal',
          'external_source':'internal','kind':'internal','security_class':'restricted','export_allowed':False}]}]}
put(R/'01_DATA/CATALOG/SCOPES/risk-compare-docx-20261015-r1.json',scope)
put(R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow/artifacts/document-registration.json',
    {'package':package.receipt(),'raw_sha256':h,'document_id':h[:16],'current_validity':'unknown',
     'scope':'01_DATA/CATALOG/SCOPES/risk-compare-docx-20261015-r1.json','model_calls':0,
     'source_set_verified':True,'active_selection_changed':False})
print('Registered',h[:16], 'restricted; current validity unknown; no active selection')
