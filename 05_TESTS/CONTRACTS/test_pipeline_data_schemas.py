"""Cross-stage invariants: provenance, generations and accounting for every card."""
import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('pipeline_data_contract',ROOT/'06_TOOLS/AUDIT/pipeline_data_contract.py')
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)
D=ROOT/'01_DATA/CONTRACTS/PIPELINE_STAGES'

def read(path):return json.loads(path.read_text())
def case(name):
 row=read(D/'examples.json')[name]
 return row['contract'],read(D/row['file']),read(D/row['context_file']) if 'context_file' in row else {}

def test_all_stage_examples_and_shared_semantics():
 results=V.check_examples();assert len(results)==15;assert not any(results.values()),results

@pytest.mark.parametrize('name,mutate,expected',[
 ('source',lambda v:v['blocks'][0].update(text='잘못된 내용'),'mapping'),
 ('correction',lambda v:v['corrections'][0].update(before='없는 표현'),'before differs'),
 ('correction',lambda v:v['blocks'][0]['mappings'][0].update(correction_id=None),'unrecorded'),
 ('correction',lambda v:v['blocks'][0]['mappings'][1].update(start=3),'gap or overlap'),
 ('correction',lambda v:v['corrections'][0].update(review_status='PROPOSED'),'unreviewed'),
 ('correction',lambda v:v['corrections'][0].update(review_receipt=None),'receipt missing'),
 ('source',lambda v:v['raw_blocks'].append(dict(v['raw_blocks'][0],id='raw:unaccounted')),'not fully accounted'),
 ('source',lambda v:v['units'][0].update(parent_id=v['units'][0]['id']),'parent cycle'),
 ('source',lambda v:v['units'][1].update(parent_id=v['units'][0]['id']),'outside parent'),
 ('correction',lambda v:v['references'][0].update(surface='다른 원문'),'surface differs'),
 ('source',lambda v:v['issues'].append({'id':'issue:x','code':'MISSING','message':'누락','unit_id':None,'block_id':None,'blocking':True}),'blocking source'),
 ('review',lambda v:v.update(subject_payload_sha256='0'*64),'payload mismatch'),
 ('review',lambda v:v['checks'][0].update(result='UNKNOWN'),'approval with failed'),
 ('review',lambda v:v.update(field_pointer='/missing'),'pointer missing'),
 ('generation',lambda v:v.update(generation_id='other-generation'),'generation mismatch'),
 ('generation',lambda v:v['review_artifacts'][0].update(sha256='0'*64),'review receipt not bound'),
 ('generation',lambda v:v.update(validation_receipt=None),'validation receipt'),
 ('projection',lambda v:v.update(canonical_payload_sha256='0'*64),'payload hash mismatch'),
 ('projection',lambda v:v['entries'][0].update(structural_unit_id='unit:2'),'coordinate mismatch'),
 ('hits',lambda v:v['cards'].pop(),'cards omitted'),
 ('hits',lambda v:v['cards'].append(v['cards'][0]),'duplicate query card'),
 ('hits',lambda v:v['cards'][0]['hits'][0].update(document_version_id='outside'),'outside scope'),
 ('cards',lambda v:v['cards'][0]['bundle'].update(template_id='template:unknown'),'template mismatch'),
 ('cards',lambda v:v['cards'][1].update(reason=None),'needs reason'),
 ('cards',lambda v:v['cards'][0]['bundle'].update(canonical_generation_id='other-generation'),'generation or payload mismatch'),
 ('answer',lambda v:v['unresolved'].clear(),'silently drops query card'),
 ('answer',lambda v:v['claims'][0].update(query_card_ids=['card:second']),'citation outside named cards'),
 ('answer',lambda v:v['claims'][0].update(evidence_ids=['evidence:absent']),'citation outside named cards'),
 ('feedback_event',lambda v:v.update(status='APPLIED'),'schema:'),
 ('feedback_proposal',lambda v:v.update(action='CHANGE_SCHEMA'),'concrete proposed artifact'),
 ('feedback_proposal',lambda v:v['target']['entity_ref'].update(id='proviso:missing'),'canonical entity missing'),
])
def test_cross_stage_corruption_rejected(name,mutate,expected):
 contract,value,context=case(name);mutate(value)
 errors=V.validate(contract,value,context=context)
 assert any(expected in error for error in errors),errors

def test_changed_projection_cannot_hide_behind_its_own_new_hash():
 contract,value,context=case('generation');ref=value['projection_artifacts'][0]
 row=read(D/'projection.json');row['canonical_payload_sha256']='0'*64
 raw=json.dumps(row);ref['sha256']=hashlib.sha256(raw.encode()).hexdigest()
 context['artifacts'][ref['id']]={'ref':copy.deepcopy(ref),'raw':raw}
 assert 'projection canonical payload not bound' in V.validate(contract,value,context=context)

def test_shape_success_is_not_reviewer_authentication():
 contract,value,context=case('review')
 assert value['reviewer']['id']=='synthetic-reviewer-not-authenticated'
 assert V.validate(contract,value,context=context)==[]
 # This tool has no admission/activation operation, regardless of the decision text.
 assert not hasattr(V,'approve') and not hasattr(V,'activate')

@pytest.fixture
def workspace(tmp_path):
 shutil.copytree(ROOT/'00_SYSTEM/SCHEMAS',tmp_path/'00_SYSTEM/SCHEMAS')
 for name in ('LEGAL_SCHEMA.json','PIPELINE.json'):
  shutil.copy(ROOT/'00_SYSTEM'/name,tmp_path/'00_SYSTEM'/name)
 return tmp_path,V.H.load(tmp_path)

def test_declared_shared_schema_hash_required(workspace):
 root,config=workspace;p=root/'00_SYSTEM/SCHEMAS/pipeline-common-v1.schema.json'
 p.write_text(p.read_text()+'\n')
 with pytest.raises(V.H.ContractError,match='hash drift'):
  V.H.validate_value(config,'rag.question',case('question')[1],root)

def test_undeclared_remote_schema_never_fetched(workspace,monkeypatch):
 root,config=workspace;p=root/'00_SYSTEM/SCHEMAS/remote-ref-test.json'
 p.write_text(json.dumps({'$schema':'https://json-schema.org/draft/2020-12/schema','$ref':'https://untrusted.invalid/schema.json'}))
 config['contracts']['test.remote']={'schema_path':str(p.relative_to(root)),'schema_sha256':V.H.sha(p)}
 calls=[]
 import urllib.request
 monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**k:calls.append(a))
 with pytest.raises(Exception,match='Unresolvable|Unretrievable'):
  V.H.validate_value(config,'test.remote',{},root)
 assert calls==[]

def test_missing_definition_does_not_fall_back_to_any_record(workspace):
 root,config=workspace;config['contracts']['rag.cards']['schema_definition']='DoesNotExist'
 with pytest.raises(V.H.ContractError,match='unknown schema definition'):
  V.H.contract_schema(config,'rag.cards',root)

@pytest.mark.parametrize('change',[
 lambda c:c['stage_schemas'].reverse(),
 lambda c:c['stage_schemas'][0]['contracts'].append('undefined'),
])
def test_stage_catalog_rejects_broken_selection(workspace,change):
 root,config=workspace;change(config)
 with pytest.raises(V.H.ContractError):V.H.inventory(config,root)
