"""Validate design schemas/examples only. This does not certify controller behavior or legal accuracy."""
from pathlib import Path
from copy import deepcopy
import hashlib,json
from jsonschema import Draft202012Validator,FormatChecker
OUT=Path(__file__).resolve().parent
ROOT=Path('/home/jin/8-AGENT')
read=lambda p:json.loads(p.read_text())
schema=read(OUT/'contracts.schema.json')
Draft202012Validator.check_schema(schema)
validator=Draft202012Validator(schema,format_checker=FormatChecker())
current=read(ROOT/'00_SYSTEM/SCHEMAS/term-runtime-v1.schema.json')
outer=Draft202012Validator({'$ref':'#/$defs/Result','$defs':current['$defs']},format_checker=FormatChecker())
example=read(OUT/'examples.json')

def check_state(state):
    validator.validate(state)
    spans={s['span_id']:s for s in state['spans']}
    evidence={e['handle']:e for e in state['evidence']}
    searches={s['id']:s for s in state['searches']}
    assert len(spans)==len(state['spans'])
    assert len(evidence)==len(state['evidence'])
    assert len({i['issue_id'] for i in state['issues']})==len(state['issues'])
    assert len(searches)==len(state['searches'])
    for span in spans.values():
        assert span['start']<span['end']
        assert span['generation_id']==state['binding']['generation_id']
        assert span['source_store_sha256']==state['binding']['source_store_sha256']
        if span['valid_from'] and span['valid_to']:assert span['valid_from']<span['valid_to']
    for e in evidence.values():assert set(e['span_ids'])<=spans.keys()
    for i in state['issues']:
        assert set(i['evidence_refs'])<=evidence.keys()
        assert set(i['search_attempt_ids'])<=searches.keys()
        for sid in i['search_attempt_ids']:assert searches[sid]['issue_id']==i['issue_id']
    assert set(state['selected_source_ids'])<={s['source_id'] for s in spans.values()}
    budget=state['budget']
    assert budget['used_attempts']<=budget['max_attempts']
    assert budget['reserved_composition_attempts']<=budget['max_attempts']
    if state['response_class']=='complete':
        assert all(i['evidence_state'] in ('EVIDENCE_LINKED','NOT_APPLICABLE') and i['fact_state']!='unknown'
                   for i in state['issues'] if i['required'])

def check_result(result):
    outer.validate(result)
    ids={c['id'] for c in result['assembly']['context']}
    for claim in result['answer']['claims']:assert set(claim['source_ids'])<=ids
    assert result['answer']['query_id']==result['query']['id']
    assert result['answer']['generation_id']==result['query']['generation_id']
    check_state(result['retrieval']['term_agent']['legal_agent'])

check_state(example['state']);check_result(example['runtime_result'])
checks=[{'case':'valid_internal_state','passed':True},{'case':'valid_current_runtime_result','passed':True}]
def reject(name,mutate,which='state'):
    item=deepcopy(example[which]);mutate(item)
    try:(check_state if which=='state' else check_result)(item)
    except Exception as exc:checks.append({'case':name,'passed':True,'rejected_by':type(exc).__name__})
    else:raise AssertionError('negative example was accepted: '+name)
reject('global_absence_status_forbidden',lambda x:x['issues'][0].update(evidence_state='ABSENCE_CONFIRMED'))
reject('unknown_handle',lambda x:x['issues'][0].update(evidence_refs=['E999']))
reject('unknown_span',lambda x:x['evidence'][0].update(span_ids=['span:missing']))
reject('span_offset_reversed',lambda x:x['spans'][0].update(start=30,end=12))
reject('cross_generation',lambda x:x['spans'][0].update(generation_id='other'))
reject('unknown_facts_complete',lambda x:x.update(response_class='complete'))
reject('searched_without_attempt',lambda x:x['issues'][0].update(evidence_state='SEARCHED_UNRESOLVED'))
reject('evidence_without_reference',lambda x:x['issues'][0].update(evidence_refs=[]))
reject('attempt_budget_overrun',lambda x:x['budget'].update(used_attempts=9))
reject('duplicate_handle',lambda x:x['evidence'].append({**x['evidence'][0],'presented_call_ids':['call:other']}))
reject('current_answer_extra_citations',lambda x:x['answer'].update(citations=[]),'runtime_result')
reject('claim_outside_context',lambda x:x['answer']['claims'][0].update(source_ids=['article:missing']),'runtime_result')
report=(OUT/'DESIGN.md').read_text()
assert 'TODO' not in report
assert report.count('```')%2==0
for name in ('contracts.schema.json','examples.json','inspect_existing.py','existing-run-diagnostics.json'):assert (OUT/name).is_file()
checks.append({'case':'report_references_and_fences','passed':True})
result={'scope':'Schema, synthetic cross-reference rules and current Result compatibility only. No proposed runtime state machine, source hash verification, real model or legal quality certified.',
        'passed':len(checks),'failed':0,'checks':checks,
        'artifact_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [OUT/'DESIGN.md',OUT/'contracts.schema.json',OUT/'examples.json']}}
(OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':len(checks),'failed':0,'scope':result['scope']},ensure_ascii=False))
