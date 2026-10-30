"""Create compact Gold design documents only. No DB or application mutations."""
from pathlib import Path
from copy import deepcopy
import csv
import hashlib
import importlib.util
import json
import re
import zipfile
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
R11=OUT.parent/'DATAIKU_GOLD_REDESIGN_20261029_R11'
spec=importlib.util.spec_from_file_location('gold_r11_format',R11/'build_design.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
STATUS='R12 축소 설계 후보 · 표준 미승인 · DB/제품 미반영'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def design():
    old=json.loads((R11/'MODEL.json').read_text())
    base=prior.load_base();lookup={t['suffix']:t for t in old['tables']}
    for t in base:
        t['phase']='기존 골드 유지';t['change']='R10 컬럼 유지; 소프트 FK·일반 인덱스 적용'
        t['indexes']=deepcopy(lookup[t['suffix']]['indexes'])
    base[2]['indexes']=[['MNFST_HASH_VALU','DOC_ID','STRC_UNIT_ID','BODY_SLC_ID']]
    base[4]['indexes']=[]
    keeps={
      'VCTR_POST':['VCTR_POST_ID','VCTR_POST_IFMN_CTNT'],
      'VCTR_ITEM':['VCTR_POST_ID','VCTR_SEG_ID','DOC_ID','SRC_UNIT_ID','VCTR_META_CTNT','EMBD_VCTR_VALU'],
      'VCTR_HEAD':['RFRN_POST_HASH_VALU','VCTR_POST_ID','CHAN_NO']}
    for name,cols in keeps.items():
        t=deepcopy(lookup[name]);t['columns']=[c for c in t['columns'] if c['name'] in cols]
        t['phase']='벡터 신규';t['change']=f'R11 {len(lookup[name]["columns"])}열 → R12 {len(cols)}열'
        for c in t['columns']:c['change']='R12 신규 벡터 컬럼; R11 타입·정의 유지'
        if name=='VCTR_POST':
            t['indexes']=[]
            c=t['columns'][1]
            c['source']='R3 PAYLOAD_JSON.manifest + 완료 영수증; R12 완료 메타 envelope'
            c['rule']='중복 키 없는 JSON. manifest 전체·profile·판본·원문 범위 보존. count/chain/registered_at/profile_sha256은 완료 메타로 보존. digest(manifest)=PK. READY 봉인 후 불변.'
        if name=='VCTR_ITEM':
            next(c for c in t['columns'] if c['name']=='VCTR_META_CTNT')['rule']='기존 META_JSON 전체 보존: document_id/source_id/unit_id/block_id/start/end/source_sha256/block_sha256/input_sha256. 일반 문서/원문 ID와 일치. 입력 해시는 삭제하지 않고 JSON에서 검증.'
        base.append(t)
    names={t['suffix'] for t in base};by={t['suffix']:{c['name'] for c in t['columns']} for t in base}
    rels=[]
    for r in old['relationships']:
        if r['child'] in names and r['parent'] in names and set(r['child_columns'])<=by[r['child']] and set(r['parent_columns'])<=by[r['parent']]:
            r=deepcopy(r);r['id']=f'R{len(rels)+1:02}';rels.append(r)
    return base,rels

REDUCTIONS=[
 ['FTS_UNIT / FTS_POST / FTS_STAT',19,'전용 FTS 표 3개를 추가하지 않음','기존 SRCH_ROW의 unit / unit_fts_length / unit_fts_posting / unit_fts_stats와 manifest 유지','검색·토큰·위치·통계 데이터 삭제 없음. 일반 lookup/owner/target/doc 인덱스 유지.'],
 ['SRCH_POST',2,'원문 게시 ID·판본의 일반 컬럼 추가 취소','기존 RFRN_POST_IFMN_CTNT의 manifest.source_release_id / dataset_version','게시본 PK 조회 후 한 manifest에서 검증. JSON 조건으로 전체 게시본을 검색하지 않음.'],
 ['DOC_BLK',1,'BODY_SLC_ORD_NO 추가 취소','기존 원문 ID와 현재 범위/수치 정렬 계약 유지','판본·문서를 먼저 제한. 큰 단일 문서의 숫자 범위/정렬 최적화는 남음.'],
 ['VCTR_POST',5,'조회/판본/profile hash/count/등록일시의 별도 컬럼 제거','VCTR_POST_IFMN_CTNT의 기존 manifest 및 완료 메타','HEAD PK로 게시본을 찾고 게시 JSON 한 행 검증. 전체 JSON 스캔/함수 인덱스 불필요.'],
 ['VCTR_ITEM',1,'INPT_HASH_VALU 별도 컬럼 제거','VCTR_META_CTNT.input_sha256','선택 구간 PK 배치 조회 후 입력/모델 비교. 전체 입력 해시 검색용 인덱스는 두지 않음.'],
]

CONTRACTS=[
 ['게시 관계','SRCH_POST JSON→SRC_POST; VCTR_POST JSON→SRCH_POST','게시본 PK를 먼저 읽고 manifest.query_id/source_release_id/dataset_version을 원천과 대조. JSON에 들어갔어도 검증 유지.'],
 ['벡터 선택','VCTR_HEAD PK=query ID; 선택 pub+순번','HEAD의 query ID와 선택한 게시 manifest.query_id 일치. NULL 비활성, stale CAS 및 A→B→A 차단.'],
 ['벡터 원문','ITEM의 DOC_ID/SRC_UNIT_ID + META','manifest.documents·판본·현재 ACL, 구조/블록/span/원문·입력 해시 검증. 원문 ID와 구조 ID 혼용 금지.'],
 ['벡터 완료','POST JSON의 봉인된 manifest+completion','실제 ITEM count/chain·프로필·차원·유한값 검증. BUILDING/lease/fence는 Agent 제어. 봉인 전 읽기 금지.'],
 ['전문검색','기존 SRCH_ROW 종류별 논리 행','토큰 일반 lookup으로 좁힌 뒤 위치 JSON 확장. global phrase df/BM25·순위·total/cursor·권한 유지.'],
 ['연결 관계','SRCH_ROW의 lookup/owner/target/doc','행 종류별 대상과 후보/미해결 상태 보존. 범위 먼저 좁히고 배치 조회. 모든 target을 문서 FK로 간주하지 않음.'],
 ['원문 순서','현행 numeric BLOCK_ID 범위·정렬','일반 문서/판본 키 필터와 원천 순서 유지. 숫자10이2보다 먼저 오는 문자열 정렬로 교체 금지.'],
 ['적재·봉인','공유 PK 공간별 Agent writer 제어','배치마다 fencing 확인→쓰기 중지/전수 검증→완료 manifest→짧은 HEAD CAS. 완료 뒤 불변, 자동 삭제 없음.'],
 ['온톨로지','ONTL_POST/HEAD/ANC Gold; WORK/EVT Agent','동일 Oracle 트랜잭션 가능 여부 확인. 다른 트랜잭션이면 outbox 계약 선행.'],
]

CHANGES=[
 ['물리 계약','physical_mapping.py / physical_mapping.yaml','R10 10표와 벡터3표의 Gold 매핑·일반 인덱스·소프트 검증. dev_silver 검사는 유지.'],
 ['원문·조회','oracle_migration.py / oracle_query_publish.py / oracle_query_catalog.py','기존 generic FTS·manifest 논리 계약 보존. Gold 명명/타입/봉인과 소비자 연결.'],
 ['벡터','R3 payload의 initial_vector.py / vector_publish.py / vector_silver/schema.py·publisher.py','2표6열 검사를 Gold3표11열로 전환. 일반 DOC/SRC·별도 HEAD·완료 JSON·Agent 제어 연결.'],
 ['FTS/관계 성능','oracle_query_fulltext.py / oracle_query_db.py / oracle_query_index.py','페이지 반복 scoring과 IN/JOIN 범위 선제한을 실제 SQL에서 개선. 새 표 생성만으로 해결된다고 하지 않음.'],
 ['온톨로지·실행','ontology_work/repository.py·runtime.py / service.py / oracle_query_service.py','Gold/Agent 트랜잭션과 실제 매핑/code pin 전환·재개·롤백 확인.'],
]

def setup(ws,title,headers,widths):
    prior.setup(ws,title,STATUS,headers,widths)
    ws.oddFooter.center.text='R12 축소안 · &P / &N'

def workbook(ts,rels,agent):
    w=Workbook();s=w.active;s.title='00_축소요약'
    setup(s,'골드 축소 설계 R12',['항목','설계','주의'],[26,95,95])
    prior.add_rows(s,[
      ['등록 대상','13표·60컬럼 = 기존 10표49열 + 벡터 3표11열','전체 테이블의 컬럼 수 합계. R11 88열에서28열 축소(31.8%). 저장 용량/속도 개선율 아님.'],
      ['벡터 최소 구성','게시2열 / 구간벡터6열 / 선택3열','일반 문서ID·원문ID·벡터·선택순번을 남겨 실제 검색/경쟁 제어를 유지.'],
      ['전문검색','기존 SRCH_ROW·manifest 재사용; 별도 FTS3표 없음','토큰/위치/통계 데이터와 기존 검색 의미를 유지. 페이지 반복 계산 개선은 별도 코드 작업.'],
      ['메타 정보','profile·판본·건수·시각·입력 해시는 기존 JSON에 보존','PK로 조회한 제한된 행에서 복원·검증. 검색에 필요한 ID까지 JSON으로 밀지 않음.'],
      ['관계·제약','PK/NOT NULL·일반 인덱스 + 소프트 FK','물리 FK/업무 CHECK/PK 외 UNIQUE/함수 인덱스 없음. 코드 검증을 구현해야 함.'],
      ['B03 / B05','공통 모델의 명명안 두 파일','공통 데이터를 두 벌 생성하라는 뜻이 아님. owner·공유 권한·신규 용어 승인 미확정.'],
      ['현재 상태','문서 설계·정적 대조만 수행','DB/제품/MAIN/GENOS 변경 및 Oracle 성능 검증 없음. R11은 비교 이력으로 보존.'],
    ],75)
    s=w.create_sheet('01_테이블목록');setup(s,'테이블 목록',['번호','논리명','물리명 후보','컬럼 수','행 단위/정의','변경'],[8,27,35,10,95,65])
    for i,t in enumerate(ts,1):
        name=f'IDD_{agent}_LGL_'+t['suffix'];sheet=f'{i+1:02}_{t["short"]}'
        prior.add_rows(s,[[i,t['logical'],name,len(t['columns']),t['definition'],t['change']]],70)
        s.cell(i+4,2).hyperlink=f"#'{sheet}'!A1"
        detail=w.create_sheet(sheet);setup(detail,t['logical']+' | '+name,prior.BASE_HEADERS,[7,24,32,12,24,22,22,9,8,44,70,15])
        pk=[c['name'] for c in sorted(t['columns'],key=lambda c:c['pk']) if c['pk']]
        prior.add_rows(detail,[[j,c['logical'],c['name'],c['domain'],c['words'],c['dtype'],c['size'],c['pk'] or '—','Y' if c['required'] else 'N',prior.physical(c,pk),c['definition'],c['korean']] for j,c in enumerate(t['columns'],1)],78)
    s=w.create_sheet('15_인덱스');setup(s,'PK와 일반 인덱스',['테이블','인덱스','종류','열 순서'],[36,38,20,120])
    for t in ts:
        name=f'IDD_{agent}_LGL_'+t['suffix'];pk=[c['name'] for c in sorted(t['columns'],key=lambda c:c['pk']) if c['pk']]
        prior.add_rows(s,[[name,'X0_'+name,'PK',', '.join(pk)]]+[[name,f'X{i}_'+name,'일반 B-tree',', '.join(ix)] for i,ix in enumerate(t['indexes'],1)],50)
    s=w.create_sheet('16_소프트관계');setup(s,'직접 논리 관계와 JSON 관계',['ID','출발','대상','검증'],[10,75,75,100])
    prior.add_rows(s,[[r['id'],r['child']+'.('+','.join(r['child_columns'])+')',r['parent']+'.('+','.join(r['parent_columns'])+')',r['condition']+'; '+r['validation']] for r in rels],70)
    prior.add_rows(s,[['JSON','SRCH_POST.RFRN_POST_IFMN_CTNT','SRC_POST + 원문 판본','manifest.source_release_id/dataset_version 검증. 직접 열 관계와 구분.'],['JSON','VCTR_POST.VCTR_POST_IFMN_CTNT','SRCH_POST + 원문 게시·판본','manifest.query_id/source_release_id/dataset_version 검증. HEAD의 query와 동일.']],70)
    s=w.create_sheet('17_축소내역');setup(s,'R11 → R12 변경',['대상','줄인 열','변경','데이터를 보존하는 위치','동작/성능 경계'],[35,12,60,90,100]);prior.add_rows(s,REDUCTIONS,95)
    s=w.create_sheet('18_코드검증');setup(s,'보존할 검증·실행 경로',['구분','대상','필수 계약'],[26,65,130]);prior.add_rows(s,CONTRACTS,85)
    prior.add_rows(s,[['변경 지도',c[0]+': '+c[1],c[2]] for c in CHANGES],85)
    s=w.create_sheet('19_원천과정의');setup(s,'컬럼 원천과 코드 규칙',['테이블','컬럼','원천','코드 검증/생성식'],[34,34,90,120])
    prior.add_rows(s,[[t['suffix'],c['name'],c['source'],c['rule'] or '원천 그대로; 기존 타입/PK/필수 계약 유지. 별도 산식 해당 없음.'] for t in ts for c in t['columns']],80)
    w.properties.title=f'{agent} 골드 축소 설계 R12';w.properties.description=STATUS
    path=OUT/f'법률에이전트_{agent}_골드축소안_R12.xlsx';w.save(path);return path

def ddl(ts,agent):
    lines=['-- R12 REVIEW TEMPLATE ONLY. No DB execution.', '-- {{APPROVED_GOLD_OWNER}}: resolve approved schema first.', '-- Physical PK/NOT NULL; logical FK and business rules are code-validated.', '-- No physical FK, business CHECK, extra UNIQUE or function index.','']
    for t in ts:
        name=f'IDD_{agent}_LGL_'+t['suffix'];pk=[c['name'] for c in sorted(t['columns'],key=lambda c:c['pk']) if c['pk']]
        fields=['  '+c['name']+' '+c['type']+(' DEFAULT '+c['default'] if c.get('default') else '')+(' NOT NULL' if c['required'] else '') for c in t['columns']]
        fields.append('  CONSTRAINT X0_'+name+' PRIMARY KEY ('+', '.join(pk)+')')
        lines+=['-- '+t['logical'],'CREATE TABLE {{APPROVED_GOLD_OWNER}}.'+name+' (',',\n'.join(fields),');']
        for i,ix in enumerate(t['indexes'],1):lines.append(f'CREATE INDEX {{{{APPROVED_GOLD_OWNER}}}}.X{i}_{name} ON {{{{APPROVED_GOLD_OWNER}}}}.{name} ('+', '.join(ix)+');')
        lines.append('')
    (OUT/f'GOLD_{agent}_DDL_REVIEW.sql').write_text('\n'.join(lines),encoding='utf-8')

def validate(ts,rels,paths):
    assert len(ts)==13 and sum(len(t['columns']) for t in ts)==60
    assert sum(len(t['columns']) for t in ts[:10])==49
    assert [len(t['columns']) for t in ts[-3:]]==[2,6,3]
    assert sum(r[1] for r in REDUCTIONS)==88-60
    for before,after in zip(prior.load_base(),ts[:10],strict=True):
        assert before['columns']==after['columns']
    by={t['suffix']:t for t in ts}
    for t in ts:
        cs={c['name']:c for c in t['columns']};assert len(cs)==len(t['columns'])
        pk=sorted(c['pk'] for c in t['columns'] if c['pk']);assert pk==list(range(1,len(pk)+1)) and pk
        assert all(c['required'] for c in t['columns'] if c['pk'])
        for c in t['columns']:assert len(c['name'].encode())<=30
        for ix in t['indexes']:assert set(ix)<=cs.keys() and len(set(ix))==len(ix)
        assert len(('X0_IDD_B03_LGL_'+t['suffix']).encode())<=30
    for r in rels:
        cs={c['name']:c for c in by[r['child']]['columns']};ps={c['name']:c for c in by[r['parent']]['columns']}
        assert r['parent_columns']==[c['name'] for c in sorted(ps.values(),key=lambda c:c['pk']) if c['pk']]
        for a,b in zip(r['child_columns'],r['parent_columns'],strict=True):assert cs[a]['type']==ps[b]['type']
    old=json.loads((R11/'MODEL.json').read_text());entries=[]
    target={t['suffix']:{c['name'] for c in t['columns']} for t in ts}
    for t in old['tables']:
        for c in t['columns']:
            if c['name'] not in target.get(t['suffix'],set()):entries.append((t['suffix'],c['name']))
    assert len(entries)==28
    bookdata=[]
    for agent,path in zip(('B03','B05'),paths,strict=True):
        with zipfile.ZipFile(path) as z:assert z.testzip() is None
        w=load_workbook(path,data_only=False);assert len(w.worksheets)==20
        assert sum(s.max_row-4 for s in w.worksheets[2:15])==60
        for t,s in zip(ts,w.worksheets[2:15],strict=True):
            assert [s.cell(i,3).value for i in range(5,s.max_row+1)]==[c['name'] for c in t['columns']]
            assert not any(re.search(r'FOREIGN KEY|CHECK\s*\(|FK\s*→|UNIQUE\s*\(',str(s.cell(i,10).value),re.I) for i in range(5,s.max_row+1))
        assert not any(c.data_type=='f' for s in w for row in s for c in row)
        sql=(OUT/f'GOLD_{agent}_DDL_REVIEW.sql').read_text();body='\n'.join(x for x in sql.splitlines() if not x.startswith('--'))
        assert body.count('PRIMARY KEY')==13
        assert not re.search(r'FOREIGN KEY|\bREFERENCES\b|CHECK\s*\(|CREATE UNIQUE INDEX|JSON_VALUE\s*\(',body,re.I)
        parsed=re.findall(r'CREATE TABLE \{\{APPROVED_GOLD_OWNER\}\}\.([A-Z0-9_]+) \(\n(.*?)\n\);',body,re.S)
        assert len(parsed)==13
        for (name,definition),t in zip(parsed,ts,strict=True):
            assert name==f'IDD_{agent}_LGL_'+t['suffix']
            fields=definition.splitlines();assert len(fields)==len(t['columns'])+1
            for line,c in zip(fields[:-1],t['columns'],strict=True):
                expected=c['name']+' '+c['type']+(' DEFAULT '+c['default'] if c.get('default') else '')+(' NOT NULL' if c['required'] else '')
                assert line.strip().removesuffix(',')==expected
        bookdata.append({'file':path.name,'tables':13,'columns':60,'sheets':20,'sha256':sha(path)})
    books=[load_workbook(p,data_only=True) for p in paths]
    for a,b in zip(*books,strict=True):
        assert a.title==b.title and (a.max_row,a.max_column)==(b.max_row,b.max_column)
        for ar,br in zip(a.iter_rows(values_only=True),b.iter_rows(values_only=True),strict=True):
            normal=lambda v:v.replace('B03','BXX').replace('B05','BXX') if isinstance(v,str) else v
            assert [normal(v) for v in ar]==[normal(v) for v in br]
    unique={c['name'] for t in ts for c in t['columns']};oldunique={c['name'] for t in ts[:10] for c in t['columns']}
    return {'status':'PASS_STATIC_DESIGN_CONSISTENCY','tables':13,'columns':60,'baseline_columns':49,'vector_columns':11,'reduced_columns':28,'unique_column_names':len(unique),'new_unique_column_names':sorted(unique-oldunique),'direct_soft_relations':len(rels),'json_release_relations':2,'primary_keys':13,'ordinary_indexes':sum(len(t['indexes']) for t in ts),'physical_foreign_keys':0,'business_checks':0,'extra_unique':0,'function_indexes':0,'workbooks':bookdata,'oracle_ddl_executed':False,'performance_measured':False,'native_excel_render':False,'independent_review':False,'removed_physical_fields':entries}

def main():
    ts,rels=design();dump('MODEL.json',{'version':'gold-compact-r12','status':STATUS,'tables':ts,'relationships':rels,'json_contracts':CONTRACTS,'reduction':REDUCTIONS,'change_map':CHANGES})
    paths=[]
    for a in ('B03','B05'):paths.append(workbook(ts,rels,a));ddl(ts,a)
    for filename,headers,rows in [
      ('TABLES.csv',['table','logical','columns','source','change'],[[t['suffix'],t['logical'],len(t['columns']),t['source'],t['change']] for t in ts]),
      ('COLUMNS.csv',['table','column','logical','type','pk_order','required','source','code_rule'],[[t['suffix'],c['name'],c['logical'],c['type'],c['pk'],c['required'],c['source'],c['rule']] for t in ts for c in t['columns']])]:
        with (OUT/filename).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(headers);w.writerows(rows)
    result=validate(ts,rels,paths);dump('VALIDATION.json',result)
    sources=[R11/'MODEL.json',R11/'build_design.py',prior.R10/'법률에이전트_B03_골드등록용_테이블별_R10.xlsx',prior.R10/'법률에이전트_B05_골드등록용_테이블별_R10.xlsx',ROOT/'02_BACKEND/semantic_runtime/oracle_query_fulltext.py',ROOT/'02_BACKEND/semantic_runtime/oracle_query_catalog.py',ROOT/'02_BACKEND/semantic_runtime/oracle_query.py',ROOT/'08_DEPLOYMENT/DATAIKU/vector_silver_20261029_r3/payload/02_BACKEND/semantic_runtime/initial_vector.py',ROOT/'08_DEPLOYMENT/DATAIKU/vector_silver_20261029_r3/payload/02_BACKEND/semantic_runtime/vector_publish.py']
    dump('SOURCES.json',{'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in sources],'policy_photos':'../DATAIKU_GOLD_REDESIGN_20261029_R11/evidence/','scope':'Design revision only; product code and live DB unchanged.'})
    print(json.dumps({k:result[k] for k in ('status','tables','columns','reduced_columns','ordinary_indexes','new_unique_column_names')},ensure_ascii=False))

if __name__=='__main__':main()
