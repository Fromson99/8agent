"""Audit actual frozen requests against native evidence; never open the corpus."""
import importlib.util
import json
import sys
from copy import deepcopy
from common import ROOT,ADR,ART,SOURCE,TOOLS,read,save,sha,rel,ro,canonical_digest as digest
from delivery_spans import audit_view,evidence_index,AuditError,Unknown,union


def verify_freeze(frozen):
    for group in ('inputs','tool_files','source_tools'):
        for path,expected in frozen[group].items():
            if sha(ROOT/path)!=expected:raise AuditError('FROZEN_FILE_CHANGED:'+path)
    if sha(ART/'implementation-plan.json')!=frozen['implementation_plan_sha256']:
        raise AuditError('FROZEN_CRITERIA_CHANGED')


def load_codecs(frozen):
    sys.dont_write_bytecode=True
    path=ROOT/'06_TOOLS/EXPERIMENTS/adr_1063/wire_audit.py'
    spec=importlib.util.spec_from_file_location('_adr1063_frozen_wire',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    codecs=module.load_frozen_codecs(frozen)
    from semantic_runtime.legal_agent.errors import ContractError
    codecs['contract_error']=ContractError
    return module,codecs


def restore_view(module,codecs,stored,request,events):
    # Retain the complete original native-request/codec hash checks, including
    # actual dictionary restoration. Missing old span accounting is not waived.
    original=module.reconstruct(stored,request,events,codecs)
    wire=module.request_view(request);expected=stored;refs=None
    records={event['kind']:event['payload'] for event in events}
    navigation=stored.get('input_projection')=='compact-selection-source-v3'
    if 'NUMBERED_REFERENCES' in records:
        refs=codecs['navigation' if navigation else 'numbered'](stored);expected=refs.view(stored)
    if 'WIRE_PROJECTION' in records:expected=codecs['compact'](expected,stored['phase'])
    if 'MODEL_INPUT_PROJECTION' in records:
        restored=codecs['restore'](expected,wire,records['MODEL_INPUT_PROJECTION'])
    else:restored=deepcopy(expected)
    if navigation:restored=codecs['expand'](restored)
    if refs is not None and navigation:restored=refs.restore(restored)
    if refs is not None and not navigation and any(stored.get(k) for k in ('sources','evidence_options','exact_evidence')):
        raise Unknown('NON_NAVIGATION_ID_RESTORATION_UNAVAILABLE')
    return restored,original


def native_rows(path, original_audit, allowed, generation):
    db=ro(path)
    try:
        records=[]
        for row in db.execute('SELECT * FROM evidence_unit ORDER BY created_seq'):
            record=dict(row);record['spans']=[dict(s) for s in db.execute(
                'SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY ordinal',(row['evidence_id'],))]
            records.append(record)
        index=evidence_index(records,original_audit['checks'],original_audit['acquired'],allowed,generation)
        events={}
        for row in db.execute("SELECT kind,payload_json,payload_hash FROM event WHERE kind IN ('NUMBERED_REFERENCES','WIRE_PROJECTION','MODEL_INPUT_PROJECTION')"):
            payload=json.loads(row['payload_json'])
            if digest(payload)!=row['payload_hash']:raise AuditError('CODEC_EVENT_HASH_MISMATCH')
            events.setdefault(payload.get('attempt_id'),[]).append({'kind':row['kind'],'payload':payload})
        rows=[]
        for row in db.execute('SELECT a.attempt_id,a.status,a.request_json,a.request_hash,a.created_seq,v.body_json,v.body_hash '
                'FROM model_attempt a JOIN model_view v USING(view_id) ORDER BY a.created_seq'):
            item=dict(row);item['request']=json.loads(item.pop('request_json'));item['stored']=json.loads(item.pop('body_json'))
            if digest(item['request'])!=item['request_hash'] or digest(item['stored'])!=item['body_hash']:
                raise AuditError('NATIVE_REQUEST_OR_VIEW_HASH_MISMATCH')
            item['events']=events.get(item['attempt_id'],[])
            item['index']={k:v for k,v in index.items() if v['created_seq']<item['created_seq']}
            rows.append(item)
        return rows
    finally:db.close()


def audit_cell(cell,frozen,module,codecs,source):
    folder=ROOT/cell['directory'];metrics=read(folder/'metrics.json');execution=read(folder/'execution-audit.json')
    integrity=metrics.get('source_integrity',{})
    if (integrity.get('mismatch_count')!=0 or integrity.get('failures')!=[]
            or execution.get('source_integrity_verified') is not True or metrics.get('request_acl_check')!='CHECKED'):
        return {'cell':cell['cell'],'status':'UNKNOWN','reason':'ORIGINAL_SOURCE_INTEGRITY_NOT_VERIFIED','calls':[]}
    req=read(folder/'request.json');allowed=set(req.get('json',req).get('document_ids',[]))
    original_audit=read(folder/'evidence-audit.json');attempts=[]
    for journal in cell['journals']:
        for row in native_rows(ROOT/journal,original_audit,allowed,source['source_generation_id']):
            row['journal']=journal;attempts.append(row)
    baseline={c['request_path']:c for c in metrics.get('wire_audit',{}).get('calls',[])}
    source_calls={c['request_path']:c for c in execution['calls']}
    paths=sorted((folder/'model').glob('call-*/request.json'))
    if len(paths)!=read(folder/'result.json')['model_calls']:raise AuditError('PHYSICAL_CALL_COUNT_MISMATCH')
    reports=[];all_rows=[]
    for path in paths:
        name=str(path.relative_to(folder));physical=read(path);request_hash=digest(physical)
        report={'request_path':rel(path),'request_sha256':sha(path),'baseline':baseline.get(name),
            'baseline_assessment_originals':len(source_calls.get(name,{}).get('assessment_originals',[]))}
        matching=[r for r in attempts if r['request_hash']==request_hash]
        if not matching:
            report.update(status='UNKNOWN',reason='EXACT_NATIVE_REQUEST_UNAVAILABLE');reports.append(report);continue
        results=[]
        for native in matching:
            try:
                restored,old=restore_view(module,codecs,native['stored'],native['request'],native['events'])
                result=audit_view(restored,native['stored'],native['index'],allowed)
                result['source_stage']=native['stored'].get('source_stage')
                result['attempt_status']=native['status'];result['attempt_id']=native['attempt_id']
                result['journal']=native['journal'];result['stored_view_sha256']=native['body_hash']
                result['baseline_recomputed_missing_text_spans']=old['missing_text_spans']
                results.append(result)
            except Unknown as error:results.append({'status':'UNKNOWN','reason':error.code,'attempt_id':native['attempt_id']})
            except (AuditError,ValueError,TypeError,KeyError,codecs['contract_error']) as error:
                results.append({'status':'REJECTED','reason':getattr(error,'code',type(error).__name__),
                    'attempt_id':native['attempt_id']})
        valid=[r for r in results if r['status']=='VERIFIED' and r.get('attempt_status')=='SUCCEEDED']
        if any(r['status']=='REJECTED' for r in results):status='REJECTED'
        elif any(r['status']=='UNKNOWN' for r in results) or not valid:status='UNKNOWN'
        else:status='VERIFIED'
        report.update(status=status,native_attempts=results,confirmed_successful_delivery=status=='VERIFIED')
        if status=='VERIFIED':
            if len({digest(r['occurrences']) for r in valid})!=1:raise AuditError('AMBIGUOUS_ACTUAL_REQUEST_DELIVERY')
            rows=valid[0]['occurrences'];all_rows.extend(rows)
            report['assessment_originals']=len(rows) if 'assess' in (valid[0]['source_stage'] or '') else 0
            report['unique_codepoints']=valid[0]['unique_codepoints']
        for result in results:
            if 'occurrences' in result:
                result['occurrences']=[{k:v for k,v in row.items() if k!='text'} for row in result['occurrences']]
        reports.append(report)
    counts=union(all_rows)
    return {'cell':cell['cell'],'status':'VERIFIED' if all(c['status']=='VERIFIED' for c in reports) else 'INCOMPLETE',
        'calls':reports,'source_integrity_basis':'Frozen original collector receipts plus independently hash-checked native evidence; source DB not reopened',
        'baseline_missing_text_spans':sum((c.get('missing_text_spans') or 0) for c in baseline.values()),
        'new_unknown_calls':sum(c['status']=='UNKNOWN' for c in reports),
        'new_rejected_calls':sum(c['status']=='REJECTED' for c in reports),**counts}


def main():
    frozen=read(ART/'design-freeze.json');verify_freeze(frozen)
    assert not (ART/'result.json').exists(),'completed audit cannot be overwritten'
    source=read(SOURCE/'design-freeze.json');module,codecs=load_codecs(source);cells=[]
    for cell in frozen['cells']:
        report=audit_cell(cell,frozen,module,codecs,source)
        name=PathName(cell['cell']);save(ART/'cells'/(name+'.json'),report)
        cells.append({'cell':cell['cell'],'status':report['status'],'report_path':rel(ART/'cells'/(name+'.json')),
            'report_sha256':sha(ART/'cells'/(name+'.json')),'baseline_missing_text_spans':report.get('baseline_missing_text_spans'),
            'unknown_calls':report.get('new_unknown_calls'),'rejected_calls':report.get('new_rejected_calls')})
        print(name,report['status'],flush=True)
    verify_freeze(frozen)
    save(ART/'result.json',{'schema_version':'native-delivery-reference-audit-v1','status':'complete',
        'design_freeze_sha256':sha(ART/'design-freeze.json'),'cells':cells,'live_model_calls':0,
        'source_database_access':False,'source_inputs_preserved':True,'semantic_regrade':False,
        'original_gate_changed':False,'gate_reevaluation_performed':False,'remaining_102_authorized':False,
        'all_calls_verified':all(c['status']=='VERIFIED' for c in cells)})


def PathName(cell):return f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}"


if __name__=='__main__':main()
