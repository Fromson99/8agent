"""Continue only with verified successful structures; retain the failed parent."""
import csv,json,sqlite3
from pathlib import Path
import transport as t

VERSION='dataiku-partial-structure-v1'
REASON='사용자 요청: 실패한 문서를 보류하고 검증된 성공 문서만 후속 색인·적재한다. 원래 실패 이력은 보존한다.'


def select(workspace,run,returncode):
    if returncode not in (0,2):raise ValueError('STRUCTURE_PROCESS_FAILED')
    from lawrag.pipeline import genos_status
    from lawrag.pipeline.structure_selection import select_completed
    data=Path(workspace)/'01_DATA';directory=data/'LOGS'/run
    report=genos_status.read_report(directory)
    if (not report.get('recorded') or report['attempt'].get('stage')!='structure'
        or report['attempt'].get('status') not in {'COMPLETED','FAILED','COMPLETED_WITH_FAILURES'}
        or report['attempt'].get('error')):raise ValueError('STRUCTURE_RUN_NOT_FINISHED')
    candidates=sorted(directory.glob('result-*.json'))
    if not candidates:raise ValueError('STRUCTURE_FINAL_RESULT_MISSING')
    result=t.read(candidates[-1])
    if (result.get('stage')!='structure' or result.get('source_errors')
        or (result.get('ok') is True)!=(returncode==0)):raise ValueError('STRUCTURE_RUN_LEVEL_FAILURE')
    failures=[r for r in report['documents'] if r['selection']=='INPUT_FAILED' or
              (r['selection']=='SELECTED' and r['phases']['structure']['state']=='FAILED')]
    # Integrity errors are not ordinary unsupported/failed documents.
    for row in failures:
        detail=json.dumps(row,ensure_ascii=False).lower()
        if any(x in detail for x in ('hash mismatch','source_changed','source changed','changed after','completed structure changed','symlink','해시 불일치','영수증 불일치','지문 불일치','원문이 입력 점검 이후 변경')):
            raise ValueError('STRUCTURE_INTEGRITY_FAILURE')
    selected_run=run+'-selected'
    selected=select_completed(data,run,selected_run,allow_incomplete=True,reason=REASON)
    origin=t.read(data/'LOGS'/selected_run/'selection-origin.json')
    if selected['selected']<1 or selected['omitted']!=len(failures):raise ValueError('STRUCTURE_COVERAGE_MISMATCH')
    coverage={'schema_version':VERSION,'coverage':origin['coverage'],'original_structure_ok':result['ok'],
        'parent_run_id':run,'selected_run_id':selected_run,'selected_document_ids':origin['selected_document_ids'],
        'selected_count':selected['selected'],'omitted_count':selected['omitted'],
        'attempted_count':selected['selected']+selected['omitted'],'omitted_documents':origin['omitted_documents'],
        'reason':REASON,'quality_certified':False,'active_changed':False,
        'parent_result_sha256':t.sha(candidates[-1]),'selection_origin_sha256':t.sha(data/'LOGS'/selected_run/'selection-origin.json')}
    output=Path(workspace).parent
    t.write(output/'pipeline-coverage.json',coverage)
    with (output/'excluded-documents.csv').open('w',encoding='utf-8-sig',newline='') as out:
        writer=csv.writer(out);writer.writerow(['document_id','source','name','selection','structure_status','error'])
        for row in coverage['omitted_documents']:
            phase=row['phases']['structure']
            values=[row.get('document_id',''),row.get('source',''),row.get('name',row.get('path','')),row['selection'],phase['state'],phase.get('error') or row.get('input_error','')]
            writer.writerow(["'"+str(x) if str(x).startswith(('=','+','-','@')) else x for x in values])
    print('STRUCTURE_COVERAGE',coverage['coverage'],'selected='+str(selected['selected']),'omitted='+str(selected['omitted']),flush=True)
    return coverage


def verify_generation(generation,coverage):
    path=Path(generation)/'store.sqlite'
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        ids={r[0] for r in db.execute('SELECT document_id FROM document')}
    if ids!=set(coverage['selected_document_ids']):raise ValueError('GENERATION_SELECTED_DOCUMENTS_MISMATCH')
    return len(ids)


def export_paths(folder):
    folder=Path(folder)
    return {'audit/'+name:folder/name for name in ('pipeline-coverage.json','excluded-documents.csv') if (folder/name).is_file()}
