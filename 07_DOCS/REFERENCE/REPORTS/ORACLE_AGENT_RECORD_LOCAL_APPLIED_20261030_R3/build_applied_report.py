"""Produce actual-installed column workbook from the saved Oracle metadata only."""
from pathlib import Path
import hashlib
import json
import importlib.util

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261030-agent-record-oracle-r2'
R2=OUT.parent/'ORACLE_AGENT_RECORD_DESIGN_20261030_R2'
BASE=OUT.parent/'ORACLE_AGENT_RECORD_DESIGN_20261030_R1/build_design.py'
sp=importlib.util.spec_from_file_location('sheet_tools',BASE)
m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    from openpyxl import Workbook,load_workbook
    metadata=read(AUDIT/'installed_metadata.json');post=read(AUDIT/'postflight.json')
    spec=read(R2/'schema_proposal.json'); tables=[*spec['tables'],spec['existing_state']]
    verify_paths=[p for p in AUDIT.glob('verification-*.json') if read(p)['status']=='LIVE_ORACLE_SCHEMA_CHECKS_PASSED']
    assert len(verify_paths)==1
    vp=verify_paths[0];v=read(vp)
    assert len(v['tests'])==19 and all(t['passed'] for t in v['tests'])
    wb=Workbook();wb.remove(wb.active)
    m.sheet(wb,'실제적용결과',['항목','확인 결과'],[
        ['상태','로컬 Oracle DB에 신규 Agent 3표 생성 완료 / runtime 소비자 연결은 아직'],
        ['실제 대상','기존 Docker FREEPDB1 / SIDDA; 원격 개발계·GENOS 적용 아님'],
        ['신규 사용자 컬럼','실행9 + 공통기록8 + 본문4 = 21'],
        ['기존 상태','LGL_EXEC_ST_A 5컬럼 재사용; 정의/원 내용 유지'],
        ['인덱스','신규 PK3 + 조회7; 시간대 조회 인덱스2의 내부 UTC 표현식 확인'],
        ['내부 객체','Oracle 생성 숨김 시간대 컬럼2·LOB 인덱스는 사용자 신청 컬럼과 구분'],
        ['실제 DB 검사','19개 통과; SELECT 예시11; 약99만 바이트/16조각 무손실 복원'],
        ['시험 범위','SYSTEM 유지보수 연결·합성 데이터. 앱 인증/ORDS/실제기록 이관/E2E 미검증'],
        ['최종 신규 표 행수','각0행; 성공/실패 시험 scope만 정리, 시험 기록 보존'],
        ['용량','SIDDA 기존300MiB 한도 유지, 사용 약16.06MiB; 한도 확장0'],
        ['Gold','13표 행수/객체/활성매핑 동일, DDL/DML0; 전체 CLOB 재해시 미실행'],
        ['선택 코드',f"적용 당시 MAIN{post['active_release']['generation']} / {post['active_release']['release_id']} 유지"],
        ['등록 상태','로컬 생성 완료. 표준사전 공식 승인·현장 DBA 승인 상태를 바꾼 것은 아님'],
        ['남은 작업','저장 adapter + journal/대화/workflow/발행/출처/온톨로지 consumer + 기존 이관 + NFS 제거 검증'],
    ],[28,122])
    m.sheet(wb,'테이블목록',['오너','물리명','논리명 후보','실제 사용자 컬럼수','상태'],
        [['SIDDA',t['name'],t['title'],len(t['columns']),'신규 생성' if t['key']!='state' else '기존 재사용'] for t in tables],
        [16,30,30,23,30])
    for t in tables:
        cols=[c for c in metadata['columns'] if c[0]==t['name']]
        assert len(cols)==len(t['columns'])
        annotations={c['name']:c for c in t['columns']}
        data=[]
        for _,position,name,typ,length,precision,scale,char_used,nullable in cols:
            a=annotations[name]
            actual=(f'VARCHAR2({length} BYTE)' if typ=='VARCHAR2' and char_used=='B' else
                    f'NUMBER({precision},{scale})' if typ=='NUMBER' else typ)
            data.append([position,a['logical'],name,'Y' if name in t['pk'] else '',nullable,actual,a['description']])
        m.sheet(wb,t['key'],['순서','논리명 후보','실제 물리명','PK','NULL 허용','실제 DB 타입','역할'],data,[10,24,31,7,12,36,95])
    m.sheet(wb,'실제인덱스',['표','인덱스','실제 종류','유일성','상태','Oracle 생성'],metadata['indexes'],[30,40,32,20,15,18])
    m.sheet(wb,'인덱스컬럼',['표','인덱스','순서','실제 컬럼'],metadata['index_columns'],[30,40,10,36])
    m.sheet(wb,'UTC내부표현식',['표','인덱스','순서','실제 표현식'],metadata['index_expressions'],[30,35,10,70])
    m.sheet(wb,'실제DB검사',['검사','결과','상세'],
        [[t['name'],'통과' if t['passed'] else '실패',json.dumps({k:v for k,v in t.items() if k not in ('name','passed')},ensure_ascii=False)] for t in v['tests']],
        [55,14,100])
    m.sheet(wb,'근거',['파일','SHA256'],[[str(p.relative_to(ROOT)),sha(p)] for p in
        [R2/'schema_proposal.json',AUDIT/'plan.json',AUDIT/'applied.json',AUDIT/'installed_metadata.json',AUDIT/'postflight.json',vp]],
        [110,70])
    target=OUT/'Agent_실제생성_테이블컬럼_R3.xlsx';wb.save(target)
    check=load_workbook(target,read_only=True)
    assert all(check[t['key']].max_row-1==len(t['columns']) for t in tables)
    assert check['실제DB검사'].max_row==20
    check.close()
    result={'status':'LOCAL_DB_INSTALLED_RUNTIME_NOT_CONNECTED','owner':'SIDDA','new_tables':3,'new_user_columns':21,
            'reused_tables':1,'reused_user_columns':5,'live_db_checks':19,'test_body_bytes':v['raw_body_bytes'],'test_body_parts':v['body_parts'],
            'schema_metadata_sha256':sha(AUDIT/'installed_metadata.json'),'workbook_sha256':sha(target),'verification':str(vp.relative_to(ROOT)),
            'runtime_connected':False,'migration_done':False,'gold_ddl_dml':0,'quota_changed':False}
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
