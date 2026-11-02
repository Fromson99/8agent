"""Read source definitions and build review artifacts; never connects to a DB.

Run from repository root with .venv/bin/python. This is a design inventory and
document generator, not a runtime adapter or a database migration tool.
"""
from pathlib import Path
import ast
import csv
import hashlib
import json
import re
from datetime import datetime, timezone

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
RUNTIME = '02_BACKEND/semantic_runtime/'
H = 'VARCHAR2(64 BYTE)'
N = 'NUMBER(18)'
T = 'TIMESTAMP(6) WITH TIME ZONE'
TABLES = []
EXPECTED_NEW_TABLE_COUNT = 7
DESIGN_LABEL = 'R1'


def table(key, name, title, responsibility, rows, pk, indexes=()):
    columns = []
    for row in rows:
        logical, physical, typ, nullable, meaning = row
        columns.append(dict(logical=logical, name=physical, type=typ,
                            nullable=nullable, description=meaning,
                            pk=physical in pk, default=None))
    TABLES.append(dict(key=key, name=name, title=title, layer='Agent',
                       status='PROPOSED_NOT_REGISTERED_NOT_CREATED',
                       responsibility=responsibility, columns=columns,
                       pk=list(pk), indexes=[list(i) for i in indexes]))


S = ('접근영역해시값', 'SCOPE_HASH_VAL', H, False,
     '안정적인 인증 namespace의 해시. 문서 판본과 분리하며 해시 자체는 접근권한이 아님')
C = ('생성일시', 'CRT_DTTM', T, False, 'DB 또는 검증된 원기록의 시각; 이관 원시 시각 문자열은 본문에도 보존')
U = ('변경일시', 'CHG_DTTM', T, False, '현재 투영의 마지막 커밋 시각')
B = ('본문해시값', 'BODY_HASH_VAL', H, False, '복원한 정확 원시 바이트 SHA256; 같은 영역의 본문 조각 참조')

table('session', 'LGL_AGT_SESS_A', '에이전트대화정보', '대화 식별·소유 주체와 목록 조회', [
    S, ('대화키해시값','SESS_KEY_HASH_VAL',H,False,'원 세션 ID와 주체를 결속한 버전 있는 키'),
    ('사용자키해시값','USER_KEY_HASH_VAL',H,False,'인증된 원 사용자 식별값의 키; 원문은 본문에 보존'),
    ('팀키해시값','TEAM_KEY_HASH_VAL',H,False,'인증된 원 팀 식별값의 키'),
    ('변경순번','CHG_SEQ_NO',N,False,'대화 메타데이터 CAS 순번'), B, C, U,
], ['SCOPE_HASH_VAL','SESS_KEY_HASH_VAL'], [
    ['SCOPE_HASH_VAL','USER_KEY_HASH_VAL','TEAM_KEY_HASH_VAL','CHG_DTTM','SESS_KEY_HASH_VAL']])

table('run', 'LGL_AGT_RUN_A', '에이전트실행정보', '실행·요청·부모 실행·복구 대상의 작은 현재 투영', [
    S, ('실행키해시값','RUN_KEY_HASH_VAL',H,False,'기존 run ID를 namespace와 결속; 원 ID 보존'),
    ('대화키해시값','SESS_KEY_HASH_VAL',H,True,'대화 없는 내부 workflow는 NULL'),
    ('요청키해시값','REQ_KEY_HASH_VAL',H,False,'주체·세션·request ID 결속; 같은 요청의 복수 과거 run을 허용'),
    ('부모실행키해시값','PRNT_RUN_KEY_HASH_VAL',H,True,'부모 workflow 실행; 없으면 NULL'),
    ('실행종류코드','RUN_KIND_CD','VARCHAR2(32 BYTE)',False,'NATIVE/WORKFLOW 등 등록된 저장 종류'),
    ('상태코드','ST_CD','VARCHAR2(32 BYTE)',False,'기존 RUNNING/COMMIT_READY/COMPLETED/INTERRUPTED/FAILED 보존'),
    ('단계코드','PHASE_CD','VARCHAR2(64 BYTE)',False,'현재 단계; 기록 종류의 명시 계약으로 검증'),
    ('변경순번','CHG_SEQ_NO',N,False,'실행 투영 CAS 순번'),
    ('실행결속해시값','BIND_HASH_VAL',H,False,'원래 코드·입력·원문·권한 binding hash'),
    ('요청본문해시값','REQ_BODY_HASH_VAL',H,False,'정확한 요청과 원 식별자·원 schema·binding 보존'),
    ('결과본문해시값','RSLT_BODY_HASH_VAL',H,True,'확정 발행 응답; 미완료이면 NULL'),
    ('시작일시','STRT_DTTM',T,False,'최초 실행 시작'),
    ('마감일시','DLN_DTTM',T,False,'최초 deadline 유지; 재개 시 연장 금지'),
    ('종료일시','END_DTTM',T,True,'미종료이면 NULL'), U,
], ['SCOPE_HASH_VAL','RUN_KEY_HASH_VAL'], [
    ['SCOPE_HASH_VAL','SESS_KEY_HASH_VAL','STRT_DTTM','RUN_KEY_HASH_VAL'],
    ['SCOPE_HASH_VAL','REQ_KEY_HASH_VAL','RUN_KEY_HASH_VAL'],
    ['SCOPE_HASH_VAL','ST_CD','CHG_DTTM','RUN_KEY_HASH_VAL'],
    ['SCOPE_HASH_VAL','PRNT_RUN_KEY_HASH_VAL','RUN_KEY_HASH_VAL']])

table('event', 'LGL_AGT_EVT_A', '에이전트사건이력', '원기록·정정·트랜잭션 영수증을 순서대로 추가', [
    S, ('소유객체키해시값','OWNER_KEY_HASH_VAL',H,False,'run/session/goal/store namespace를 포함한 소유키'),
    ('사건순번','EVT_SEQ_NO',N,False,'소유 객체별 증가 순번; legacy 순번은 본문에도 보존'),
    ('사건키해시값','EVT_KEY_HASH_VAL',H,False,'멱등 사건/operation ID의 결속키'),
    ('사건종류코드','EVT_KIND_CD','VARCHAR2(96 BYTE)',False,'원래 event kind 또는 제안 영수증 종류'),
    ('변경전순번','PREV_SEQ_NO',N,True,'원래 상태 before; 없는 기록은 NULL'),
    ('변경후순번','NEXT_SEQ_NO',N,True,'원래 상태 after; 없는 기록은 NULL'), B, C,
], ['SCOPE_HASH_VAL','OWNER_KEY_HASH_VAL','EVT_SEQ_NO'], [
    ['SCOPE_HASH_VAL','OWNER_KEY_HASH_VAL','EVT_KEY_HASH_VAL'],
    ['SCOPE_HASH_VAL','OWNER_KEY_HASH_VAL','EVT_KIND_CD','EVT_SEQ_NO']])

table('record', 'LGL_AGT_REC_A', '에이전트판본기록', '판단·근거·view·작업 상태의 타입 있는 불변 판본', [
    S, ('소유객체키해시값','OWNER_KEY_HASH_VAL',H,False,'같은 영역의 run/session/goal/store별 소유키'),
    ('기록종류코드','REC_KIND_CD','VARCHAR2(64 BYTE)',False,'고정 registry의 ENTITY/EVIDENCE/SPAN/VIEW/GOAL/OUTBOX 등'),
    ('기록키해시값','REC_KEY_HASH_VAL',H,False,'원 PK tuple과 종류의 해시; 원 PK tuple을 본문에서 대조'),
    ('기록판본순번','REC_REV_NO',N,False,'불변 기록 판본. 수정은 새 판본+현재 head CAS'),
    ('상태코드','ST_CD','VARCHAR2(32 BYTE)',True,'현재 해당 판본의 원 상태; 상태 없는 종류는 NULL'),
    ('정렬순번','ORD_SEQ_NO',N,True,'질문 ordinal/span ordinal/우선순위 등 종류별 의미 고정'),
    ('참조키해시값','LOOKUP_HASH_VAL',H,True,'등록된 종류별 입력 hash/term/anchor 등 조회키; 임의 JSON path 아님'),
    ('생성사건키해시값','CRT_EVT_KEY_HASH_VAL',H,True,'판본을 만든 불변 사건; legacy 누락을 창작하지 않음'), B, C,
], ['SCOPE_HASH_VAL','OWNER_KEY_HASH_VAL','REC_KIND_CD','REC_KEY_HASH_VAL','REC_REV_NO'], [
    ['SCOPE_HASH_VAL','OWNER_KEY_HASH_VAL','REC_KIND_CD','ST_CD','ORD_SEQ_NO'],
    ['SCOPE_HASH_VAL','REC_KIND_CD','LOOKUP_HASH_VAL','REC_KEY_HASH_VAL']])

table('edge', 'LGL_AGT_REF_A', '에이전트기록연결정보', '근거·전달·의존·정정·부모자식·본문 구성 참조', [
    S, ('연결키해시값','REF_KEY_HASH_VAL',H,False,'종류·양끝점·순번 등 원 PK 전체 결속'),
    ('연결종류코드','REF_KIND_CD','VARCHAR2(64 BYTE)',False,'DEPENDENCY/PRESENTATION/CHILD_RUN/SPAN_OF 등 registry'),
    ('출발소유키해시값','FROM_OWNER_HASH_VAL',H,False,'출발 객체의 소유키'),
    ('출발종류코드','FROM_KIND_CD','VARCHAR2(64 BYTE)',False,'출발 기록 종류'),
    ('출발키해시값','FROM_KEY_HASH_VAL',H,False,'출발 객체키'),
    ('출발판본순번','FROM_REV_NO',N,False,'출발 판본'),
    ('도착소유키해시값','TO_OWNER_HASH_VAL',H,False,'도착 객체의 소유키; cross-run도 명시'),
    ('도착종류코드','TO_KIND_CD','VARCHAR2(64 BYTE)',False,'도착 기록 종류'),
    ('도착키해시값','TO_KEY_HASH_VAL',H,False,'도착 객체키'),
    ('도착판본순번','TO_REV_NO',N,False,'도착 판본'),
    ('순번','ORD_SEQ_NO',N,True,'출현·전달·구간 순서. 없으면 NULL'),
    B, C,
], ['SCOPE_HASH_VAL','REF_KEY_HASH_VAL'], [
    ['SCOPE_HASH_VAL','FROM_OWNER_HASH_VAL','FROM_KIND_CD','FROM_KEY_HASH_VAL','FROM_REV_NO','REF_KIND_CD'],
    ['SCOPE_HASH_VAL','TO_OWNER_HASH_VAL','TO_KIND_CD','TO_KEY_HASH_VAL','TO_REV_NO','REF_KIND_CD']])

table('call', 'LGL_AGT_CALL_A', '에이전트호출정보', '모델·상태 변경 도구의 준비/전송/수신/불명 상태', [
    S, ('실행키해시값','RUN_KEY_HASH_VAL',H,False,'호출 소유 실행'),
    ('호출키해시값','CALL_KEY_HASH_VAL',H,False,'기존 attempt/call ID 결속'),
    ('논리호출키해시값','LGC_CALL_HASH_VAL',H,False,'같은 논리 요청의 시도 묶음'),
    ('시도순번','TRY_SEQ_NO',N,False,'최초 및 허용 보완 시도 순번'),
    ('호출종류코드','CALL_KIND_CD','VARCHAR2(32 BYTE)',False,'MODEL/TOOL/WORKFLOW. 종류별 상태 계약'),
    ('상태코드','ST_CD','VARCHAR2(32 BYTE)',False,'PREPARED/SENT/SUCCEEDED/FAILED/UNKNOWN/IGNORED_LATE 등 원 계약'),
    ('입력화면키해시값','VIEW_KEY_HASH_VAL',H,True,'정확히 전달한 model_view/presentation 결속'),
    ('입력본문해시값','IN_BODY_HASH_VAL',H,False,'원래 모델/도구 요청 바이트'),
    ('출력본문해시값','OUT_BODY_HASH_VAL',H,True,'미수신은 NULL; 부분/실패 출력도 보존'),
    ('영수증본문해시값','RCPT_BODY_HASH_VAL',H,True,'원래 전송·사용량·provider/시각/분류/원 hash'),
    ('입력토큰수','IN_TKN_CNT',N,True,'미보고는 NULL'),
    ('출력토큰수','OUT_TKN_CNT',N,True,'미보고는 NULL'),
    ('보고비용금액','COST_AMT','NUMBER(30,12)',True,'보고 비용의 조회용 투영; 원 단위·정밀도·표기는 영수증 보존'),
    ('시작일시','STRT_DTTM',T,True,'전송 전 원 계약의 시각'),
    ('종료일시','END_DTTM',T,True,'미종료/미보고는 NULL'),
], ['SCOPE_HASH_VAL','RUN_KEY_HASH_VAL','CALL_KEY_HASH_VAL'], [
    ['SCOPE_HASH_VAL','RUN_KEY_HASH_VAL','LGC_CALL_HASH_VAL','TRY_SEQ_NO'],
    ['SCOPE_HASH_VAL','ST_CD','RUN_KEY_HASH_VAL','CALL_KEY_HASH_VAL']])

table('body', 'LGL_AGT_BODY_A', '에이전트본문조각정보', '정확한 원기록 바이트를 무손실 분할·압축 보관', [
    S, ('본문해시값','BODY_HASH_VAL',H,False,'전체 복원 바이트 SHA256'),
    ('조각순번','PART_SEQ_NO',N,False,'0부터 시작하는 고정 분할 순번'),
    ('전체조각수','PART_CNT',N,False,'본문 조각 수; 모든 행에서 동일'),
    ('전체원본바이트수','TOT_BYTE_CNT',N,False,'전체 복원 크기; 모든 행에서 동일'),
    ('조각원본바이트수','ORG_BYTE_CNT',N,False,'현재 조각의 압축 전 크기'),
    ('조각원본해시값','PART_HASH_VAL',H,False,'현재 조각의 복원 바이트 SHA256'),
    ('저장문자해시값','STOR_HASH_VAL',H,False,'실제 CLOB ASCII 바이트 SHA256'),
    ('압축방식코드','CODEC_CD','VARCHAR2(32 BYTE)',False,'RAW_BASE64/ZLIB_BASE64. 원래 bytes를 exact 복원'),
    ('본문조각내용','PART_CN','CLOB',False,'ASCII base64. CLOB 전송 가능 경로를 재사용; native BLOB 필수 아님'), C,
], ['SCOPE_HASH_VAL','BODY_HASH_VAL','PART_SEQ_NO'])

STATE = dict(key='state', name='LGL_EXEC_ST_A', title='기존에이전트실행상태정보',
             layer='Agent', status='EXISTING_MAPPING_NO_DDL_CHANGE',
             responsibility='요청 멱등·누적 예산·현재 head·소유권 토큰의 작은 CAS 객체',
             columns=[dict(logical=a,name=b,type=c,nullable=False,description=d,pk=b in ('SCOPE_HASH_VAL','ST_KEY_ID'),default=None)
                      for a,b,c,d in [
                          ('범위해시값','SCOPE_HASH_VAL',H,'새 agent:v1 namespace는 legacy scope와 구분'),
                          ('상태키ID','ST_KEY_ID','VARCHAR2(128 BYTE)','a1:req/head/lease/budget/cursor:<64hex> 등의 제한된 키'),
                          ('변경순번','CHG_SEQ_NO',N,'원래 CAS 계약'),
                          ('상태해시값','ST_HASH_VAL',H,'원래 scope/key/revision/value hash 계약 유지'),
                          ('상태JSON내용','ST_JSON_CN','CLOB','작은 현재 포인터·소유권·예산. 큰 이력 본문 금지')]],
             pk=['SCOPE_HASH_VAL','ST_KEY_ID'], indexes=[])

SOURCES = {
    'journal-v6': (RUNTIME+'legal_agent/journal-v6.sql', 'CURRENT_V6'),
    'case-base': (RUNTIME+'legal_agent/corrected_memory.py','CURRENT_V3_V4_BASE'),
    'case-v3': (RUNTIME+'legal_agent/case_repository.py','CURRENT_V3_V4_BASE'),
    'shortcut-v4': (RUNTIME+'legal_agent/shortcut_repository.py','CURRENT_CAPTURE_CONFIG_TRUE'),
    'shortcut-recall': (RUNTIME+'legal_agent/wiki_recall.py','CURRENT_RECALL_CONFIG_TRUE'),
    'procedure': (RUNTIME+'legal_agent/procedure_memory.py','CURRENT_V4_CONDITIONAL'),
    'workflow': ('02_BACKEND/workflow/repository.py','CURRENT_WORKFLOW_CONFIG_TRUE'),
    'workflow-bridge': (RUNTIME+'workflow_bridge.py','CURRENT_WORKFLOW_CONFIG_TRUE'),
    'workflow-child': (RUNTIME+'legal_agent/workflow_execution.py','CURRENT_WORKFLOW_CONFIG_TRUE'),
    'completion-budget': (RUNTIME+'legal_agent/completion_budget.py','CURRENT_CONDITIONAL'),
    'source-handoff': (RUNTIME+'legal_agent/source_handoff.py','CURRENT_CONDITIONAL'),
    'content-storage': (RUNTIME+'legal_agent/journal_storage.py','CURRENT_COMPACT_CONDITIONAL'),
    'task-policy': (RUNTIME+'task_policy.py','CURRENT_CONDITIONAL'),
    'relation-issues': (RUNTIME+'relation_issues.py','CURRENT_CONDITIONAL'),
    'ad': (RUNTIME+'ad_store.py','CONDITIONAL_FEATURE_AND_FIELD_USAGE'),
    'action-memory': (RUNTIME+'action_memory_store.py','LEGACY_OR_BATCH_INVENTORY'),
    'learning': (RUNTIME+'learning_store.py','LEGACY_OR_BATCH_INVENTORY'),
    'reference-resolution': (RUNTIME+'reference_resolution_repository.py','LEGACY_OR_BATCH_INVENTORY'),
}


def split_fields(s):
    out=[]; start=0; depth=0; quote=None; i=0
    while i<len(s):
        ch=s[i]
        if quote:
            if ch==quote:
                if i+1<len(s) and s[i+1]==quote: i+=1
                else: quote=None
        elif ch in "'\"": quote=ch
        elif ch=='(': depth+=1
        elif ch==')': depth-=1
        elif ch==',' and depth==0: out.append(s[start:i].strip()); start=i+1
        i+=1
    out.append(s[start:].strip())
    return out


def definitions(text, base_line):
    for m in re.finditer(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w]*)\s*\(',text,re.I):
        start=m.end(); depth=1; quote=None; i=start
        while i<len(text) and depth:
            ch=text[i]
            if quote:
                if ch==quote:
                    if i+1<len(text) and text[i+1]==quote:i+=1
                    else:quote=None
            elif ch in "'\"":quote=ch
            elif ch=='(':depth+=1
            elif ch==')':depth-=1
            i+=1
        if depth: raise ValueError('Unclosed table '+m[1])
        fields=split_fields(text[start:i-1])
        columns=[]
        for f in fields:
            f=re.sub(r'--[^\n]*','',f).strip()
            match=re.match(r'([A-Za-z_]\w*)\s+(.+)',f,re.S)
            if match and match[1].upper() not in {'PRIMARY','UNIQUE','CHECK','FOREIGN','CONSTRAINT'}:
                columns.append(dict(name=match[1],definition=' '.join(match[2].split())))
        yield dict(table=m[1],line=base_line+text[:m.start()].count('\n'),columns=columns,
                   definition=text[m.start():i])


def inventory():
    result=[]
    for group,(file,scope) in SOURCES.items():
        text=(ROOT/file).read_text()
        if file.endswith('.sql'): chunks=[(text,1)]
        else:
            tree=ast.parse(text)
            chunks=[(x.value,x.lineno) for x in ast.walk(tree)
                    if isinstance(x,ast.Constant) and isinstance(x.value,str) and 'CREATE TABLE' in x.value.upper()]
        seen=set()
        for chunk,line in chunks:
            for item in definitions(chunk,line):
                sig=(item['table'],item['definition'])
                if sig in seen:continue
                seen.add(sig)
                result.append(dict(group=group,source=file,scope=scope,**item))
    return result


EDGES={'dependency','observation_evidence','evidence_dependency','presentation','candidate_route','read_coverage',
       'stage_progress_evidence','experience_dependency','workflow_child_run','completion_request_run',
       'sw_member','sw_claim','sw_dependency','sw_unit_relation','sw_view_member','sw_procedure_step',
       'sw_recall_term','ontology_edge'}
STATES={'budget','auto_budget','entity_head','head','workflow_active_tool','completion_request_budget',
        'sw_cursor','sw_worker','ad_worker','intake_cursor'}


def target(item):
    n,g=item['table'],item['group']
    if n=='journal_blob_v1':return 'body','既存参照を復元して元バイト/hashを検査。Oracle参照へ変換; SQLite参照tokenを残さない'
    if n=='session':return 'session','owner/team/原session IDを保存。権限hashだけで認証しない'
    if n=='run':return 'run,state,body','singletonはrun namespaceへ。全旧列を本文にも保存'
    if n=='event' or n.endswith('_event') or n in {'review_event','sw_trace'}:
        return 'event,body','旧event ID/seq/前後状態/本文hashを保持。最新headのみの移行は禁止'
    if n in STATES:return 'state,record,body','現在値はCAS、過去変更と元レコードは不変record/eventに保存'
    if n in EDGES:return 'edge,body','全元PK・両端の種類/owner/version・順序を保持し参照を検証'
    if n in {'model_attempt','workflow_call','ad_language_call'}:
        return 'call,event,body','呼出前後の永続境界、UNKNOWNと原入出力を保持'
    if n=='request':return 'state,record,body','同一request原入力hash/principal、応答、累積予算とdeadlineを保持'
    if n=='publication':return 'record,state,run,body','準備/公開を区別。ファイル発行をOracle receiptに置換'
    if n in {'evidence_unit','evidence_span'}:return 'record,edge,body','原文版・span順序・座標・hash・役割・保有証明を保持'
    if n in {'knowledge','ontology_node','wiki','sw_knowledge','sw_unit','sw_source','sw_source_version'}:
        return 'record,state,edge,body','個人経験/既存共通知識を区別。移行をGold承認・公開と扱わない; 種類別reader適合が必須'
    return 'record,state,edge,body','元の全列/NULL/PK/型/検証hashをrecordに保持。現在headと検索キー、関係を種類別registryに定義'


# Korean descriptions replace compact internal explanations used above.
def korean_note(item):
    n=item['table']
    special={
        'journal_blob_v1':'기존 무손실 reader로 복원 후 원 바이트/hash 대조. SQLite 내부 참조 토큰을 Oracle에 남기지 않음',
        'session':'원 사용자·팀·세션 식별값 보존. 해시만으로 인증하지 않음',
        'run':'파일별 singleton을 run namespace로 변경. 모든 원 컬럼과 결속·deadline 보존',
        'request':'동일 요청의 입력·주체·응답·최초 deadline·누적 예산을 유지; 복수 run과 요청 멱등을 분리',
        'publication':'COMMIT_READY/공개 완료를 구분. 파일 발행 대신 동일 결과 해시의 DB 발행 영수증',
    }
    if n in special:return special[n]
    if n in EDGES:return '원 PK·양끝점의 owner/종류/판본·순서와 원 상세 컬럼을 모두 보존; 권한·dangling 참조 검사'
    if n in STATES:return '현재 값은 CAS로, 과거 판본·변경 이유는 record/event로 보존; 소유권/예산을 초기화하지 않음'
    if n=='event' or n.endswith('_event') or n in {'review_event','sw_trace'}:return '원 ID·순번·전후 상태·정정·철회·본문 hash 보존; 최신 head만 가져오지 않음'
    if n in {'model_attempt','workflow_call','ad_language_call'}:return '준비→전송→수신의 확정 경계와 UNKNOWN 유지. 원 입출력·실패·사용량 미보고 NULL 보존'
    if n in {'evidence_unit','evidence_span'}:return '문서 판본·블록·Unicode 좌표·구간 순서·정확 인용·원 해시·역할과 확보 영수증 보존'
    if n in {'knowledge','ontology_node','wiki','sw_knowledge','sw_unit','sw_source','sw_source_version'}:
        return '개인 실행 경험과 기존 공통 승인 지식 분류 필수. 원 승인을 보존하되 이관만으로 새 Gold 지식 승인/게시 금지'
    return '모든 원 컬럼·NULL·원 PK·형식·검증 hash를 판본 본문에 보존. 현재 head/조회키/연결은 종류별 registry로 정의'


CHANGE_MAP=[
    ('service.py','_genos_v5_admission_profile / application','설정·진입점','Agent 저장 모드 명시; 현재 무제한 동시성은 별도 운영 결정, 자동 변경하지 않음'),
    (RUNTIME+'oracle_query_service.py','Factory.application / start_recovery','서빙','외부 runtime 필수 대신 AgentStore 주입; NFS 검사 제거는 모든 활성 소비자 전환 후'),
    (RUNTIME+'app.py','create_app / source / source-candidates','API','저장소 factory 주입; 경로 glob 대신 권한 있는 run 조회·원문 재검증'),
    (RUNTIME+'legal_agent_adapter.py','run/session ingress','세션 생성','파일 경로 기반 journal 생성·resume를 저장소 식별자로 바꿈'),
    (RUNTIME+'legal_agent/repository.py','WorkRepository','실행 원장','typed 저장 포트; SQLite PRAGMA/trigger/rowid/함수 직접 의존을 분리'),
    (RUNTIME+'legal_agent/unified_repository.py','UnifiedRepository','v6','기존 판단·근거 계약을 같은 포트 위에서 보존'),
    (RUNTIME+'legal_agent/corrected_memory.py','Memory','대화','session/goal/node/head/route/request를 Oracle transaction에 연결'),
    (RUNTIME+'legal_agent/case_repository.py','CaseRepository.owner / recover_requests','대화·재개','파일 lock→DB lease/fence; outbox·참조·요청 복구 보존'),
    (RUNTIME+'legal_agent/unified_runtime.py','open_cases / execute','v3/v4 분기','실제 capture·runtime feature·source-mode에 맞는 Oracle adapter 선택'),
    (RUNTIME+'legal_agent/shortcut_repository.py','ShortcutRepository','v4','sw_* 저장·현재 head·큐·공통/개인 ACL 보존; artifact 파일 저장도 전환'),
    (RUNTIME+'legal_agent/shortcut_cases.py','ShortcutCases','v4 대화','intake/investigation/branch·case와 원장 원자적 연결'),
    (RUNTIME+'legal_agent/wiki_recall.py','recall projection','v4 조회','카드/term 페이지 조회와 현재 권한·판본 검증'),
    (RUNTIME+'legal_agent/procedure_memory.py','procedure records','재사용','실행 기록을 새 판단 없이 재사용하는 조건·영수증 유지'),
    (RUNTIME+'legal_agent/publication.py','prepare / export / recover','발행','no-clobber JSON 파일을 동일 결과 해시/상태/영수증 DB transaction으로'),
    (RUNTIME+'legal_agent/unified_publication.py','validate_saved / validate_current','발행 검증','case_db path→논리 case store ID, 원 legacy binding 보존'),
    (RUNTIME+'legal_agent/deferred_publication.py','schedule / recover','지연 발행','메모리 큐는 알림만; durable outbox는 Oracle, 시작 시 pending 조회'),
    (RUNTIME+'legal_agent/completion_budget.py','request/run budget linkage','예산','재개 후 최초 마감·누적 예산·parent child 원자적 차감'),
    (RUNTIME+'legal_agent/workflow_execution.py','register / reserve','부모자식','journal path→run ref. 부모·자식 예산 및 호출 예약 동일 transaction'),
    ('02_BACKEND/workflow/repository.py','Repository / execution_lock','대사 workflow','상태/도구/call/trigger 효과를 명시 transaction으로'),
    (RUNTIME+'workflow_bridge.py','Services / evidence loading','대사 연결','부모·자식 원장 조회와 publication window를 DB에서 조회'),
    (RUNTIME+'workflow_rag.py','child journal readers','자식 결과','원장 파일 재개방 제거; 권한·binding 교차검증 유지'),
    (RUNTIME+'request_journals.py','paths / children / scope','공통 탐색','논리 실행 목록·부모자식 참조로 전환'),
    (RUNTIME+'progress.py','poll_journal','진행 표시','seq 이후 페이지 읽기; 표시만 실패해도 원기록 성공으로 조작하지 않음'),
    (RUNTIME+'request_report.py','raw/report file writers','진단','Oracle 원기록 참조형 보고서·다운로드; 서빙 파일 저장 필수 경로 제거'),
    (RUNTIME+'session_identity.py','session ownership lookup','인증','세션 소유 확인을 Oracle에서; scope hash가 auth를 대신하지 않음'),
    (RUNTIME+'legal_agent/source_handoff.py','journal binding','원문 인계','경로 대신 논리 참조로 인계·영수증 검증'),
    (RUNTIME+'legal_agent/successful_answer.py','capture / recover','성공 답변','저널 glob→발행 완료 run 조회; 실패를 지식 후보로 승격하지 않음'),
    (RUNTIME+'ontology_work/domain_cli.py','export-journal','온톨로지 입력','Oracle events_after 포트 사용; 정규화/누적/승인 로직 유지'),
    (RUNTIME+'ontology_work/observations.py','export_journal','이력 수집','전체 원장 ACL, 순번, 원 payload hash 유지; 파일 DB API 분리'),
    (RUNTIME+'oracle_query_state.py','StateSQL / State.put','CAS','legacy 단건 commit API를 반복 호출하지 않음. 새 operation transaction에 기존 state 행 포함'),
    (RUNTIME+'legal_agent/storage_admission.py','admission / checkpoint','용량','NFS 순회/파일 lease 대체; 저장 예산·미수신/실패 기록 여유 유지'),
    (RUNTIME+'task_policy.py','checkpoint/proposal','실행 지원','정의·검토·checkpoint의 활성 사용 여부 확인 후 동일 저장 포트'),
    (RUNTIME+'relation_issues.py','rejection storage','오류 기록','거절 이력 지속 저장·조회 연결'),
    (RUNTIME+'ad_store.py','AD operations','조건부 API','AD를 제공하는 배포이면 동등 전환 필수; 비활성이라는 이유로 자료 삭제 금지'),
]


def write_json(name, data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def write_csv(name, header, rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(header);w.writerows(rows)


def sheet(wb, name, headers, rows, widths):
    s=wb.create_sheet(name);s.append(headers)
    for row in rows:s.append(row)
    s.freeze_panes='A2';s.auto_filter.ref=s.dimensions
    for cell in s[1]:cell.font=Font(name='맑은 고딕',bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='17365D')
    for row in s.iter_rows(min_row=2):
        for c in row:c.font=Font(name='맑은 고딕',size=10);c.alignment=Alignment(vertical='top',wrap_text=True)
    for i,w in enumerate(widths,1):s.column_dimensions[get_column_letter(i)].width=w
    for i in range(2,s.max_row+1):s.row_dimensions[i].height=45
    s.sheet_properties.pageSetUpPr.fitToPage=True
    s.page_setup.orientation='landscape';s.page_setup.paperSize=s.PAPERSIZE_A3
    s.page_setup.fitToWidth=1;s.page_setup.fitToHeight=0
    s.print_title_rows='1:1'
    return s


def main():
    items=inventory()
    active=json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    release=json.loads((ROOT/active['manifest_path']).read_text())
    code_root=ROOT/release['code_root']
    pipeline=json.loads((code_root/'00_SYSTEM/PIPELINE.json').read_text())
    gold_root=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
    gp=json.loads((gold_root/'ACTIVE_MAPPING.json').read_text())
    gm=json.loads((gold_root/gp['mapping_file']).read_text())
    source_files=sorted({v[0] for v in SOURCES.values()}|{c[0] for c in CHANGE_MAP}|{
        '00_SYSTEM/ORACLE/physical_mapping.yaml','00_SYSTEM/PIPELINE.json',
        '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',active['manifest_path'],
        '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/ACTIVE_MAPPING.json',
        '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/'+gp['mapping_file'],
        '07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/MULTITURN_LEGAL_AGENT.md',
        '07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/CONTROLLED_KNOWLEDGE.md',
        '07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V3/SOURCE_ANCHORED_STORAGE.md'})
    hashes=[]
    for p in source_files:
        raw=(ROOT/p).read_bytes(); selected=code_root/p
        hashes.append(dict(path=p,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
                           selected_exists=selected.exists(),
                           selected_equal=(selected.read_bytes()==raw if selected.exists() else None)))
    snapshot=dict(captured_at=datetime.now(timezone.utc).isoformat(),active_release=active,
                  code_root=release['code_root'],
                  shortcut_features=pipeline['shortcut_v4']['features'],
                  workflows_enabled=pipeline['workflows']['enabled'],
                  gold_mapping=gp,gold_tables=len(gm['tables']),
                  gold_columns=sum(len(t['columns']) for t in gm['tables'].values()),sources=hashes)
    schema=dict(status='DESIGN_ONLY',new_table_count=len(TABLES),
                new_column_count=sum(len(t['columns']) for t in TABLES),
                reused_table_count=1,reused_column_count=5,gold_ddl_changes=0,
                owner='__AGENT_OWNER__',owner_note='개발계 SIDDA는 기존 지정값. 실제 대상·권한·물리명 등록은 미확인',
                tables=TABLES,existing_state=STATE,
                caveat='기존 의미 계약을 보존하기 위한 축소 제안; 절대 최소 표 수 증명 또는 Oracle 구현 완료가 아님')
    write_json('schema_proposal.json',schema);write_json('source_inventory.json',dict(snapshot=snapshot,tables=items))
    mappings=[];column_rows=[]
    for i in items:
        keys=target(i)[0]
        row=[i['group'],i['table'],i['scope'],keys,', '.join(c['name'] for c in i['columns']),korean_note(i),i['source'],i['line']]
        mappings.append(row)
        for c in i['columns']:
            column_rows.append([i['group'],i['table'],c['name'],c['definition'],keys,
                                '원 컬럼명·값·NULL·원 hash는 typed legacy row 본문에 보존. 검색·CAS용 값만 투영; 구현 변환표는 후속',i['source']])
    write_csv('existing_table_mapping.csv',['원장군','기존표','사용범위','목표역할','원컬럼전체','보존계약','근거파일','줄'],mappings)
    write_csv('existing_column_mapping.csv',['원장군','기존표','기존컬럼','기존정의','목표역할','원값보존방식','근거파일'],column_rows)
    write_csv('code_change_map.csv',['파일','함수·경계','책임','변경내용'],CHANGE_MAP)
    ddl=['-- DESIGN ONLY: no execution performed. Names/types require metadata review.',
         '-- Replace __AGENT_OWNER__ only in the approved deployment artifact.',
         '-- No Gold DDL. Existing LGL_EXEC_ST_A is not created or altered here.',
         '-- PK + ordinary indexes draft. Semantic/FK/uniqueness checks require the typed transaction adapter.',
         '-- Runtime startup must not run DDL.\n']
    for idx,t in enumerate(TABLES,1):
        ddl.append('-- '+t['title']+' / '+t['responsibility'])
        cs=[f"  {c['name']} {c['type']}"+('' if c['nullable'] else ' NOT NULL') for c in t['columns']]
        cs.append(f"  CONSTRAINT LGL_AR{idx:02d}_PK_A PRIMARY KEY ({', '.join(t['pk'])})")
        ddl.append(f"CREATE TABLE __AGENT_OWNER__.{t['name']} (\n"+',\n'.join(cs)+'\n);')
        for j,cols in enumerate(t['indexes'],1):
            ddl.append(f"CREATE INDEX __AGENT_OWNER__.LGL_AR{idx:02d}_I{j}_A ON __AGENT_OWNER__.{t['name']} ({', '.join(cols)});")
        ddl.append('')
    (OUT/'agent_schema_review.sql').write_text('\n'.join(ddl))
    wb=Workbook();wb.remove(wb.active)
    summary=[['문서 상태','설계 초안 / 미등록·미생성·미배포'],['제안 신규 표',len(TABLES)],
             ['제안 신규 컬럼',schema['new_column_count']],['기존 상태 표','LGL_EXEC_ST_A 1표·5컬럼 재사용, DDL 변경 없음'],
             ['Gold',f"기존 {snapshot['gold_tables']}표·{snapshot['gold_columns']}컬럼 유지 / DDL 0"],
             ['선택 코드',f"MAIN{active['generation']} / {active['release_id']}"],
             ['현재 설정','shortcut capture=true / workflow enabled=true; 실제 현장 분기 미확인'],
             ['원본 추출',f"{len(items)}개 표 정의 항목 / {len(column_rows)}개 컬럼 항목; 파일군별 중복명 포함, 실제 DB 행수 아님"],
             ['코드 변경 지도',f'{len(CHANGE_MAP)}개 직접 경계 파일. 전체 영향 파일 확정 수가 아님'],
             ['주의','숏컷 공통 지식/AD/구 버전 소비자 확인 전 전체 NFS 제거 완료로 처리하지 않음'],
             ['타입·이름','모두 후보. 표준사전 승인 전 등록명으로 사용 금지'],
             ['검증','정의·파일·대응표 정적 검사만. Oracle DDL 실행·실모델·성능 시험 없음']]
    sheet(wb,'안내',['항목','내용'],summary,[24,115])
    sheet(wb,'테이블목록',['역할','물리명 후보','논리명 후보','상태','컬럼수','책임'],
          [[t['key'],t['name'],t['title'],t['status'],len(t['columns']),t['responsibility']] for t in [*TABLES,STATE]],
          [16,28,25,38,10,65])
    for t in [*TABLES,STATE]:
        sheet(wb,t['key'],['논리명 후보','물리명 후보','PK','NULL 허용','타입 후보','기본값','설명'],
              [[c['logical'],c['name'],'Y' if c['pk'] else '','Y' if c['nullable'] else 'N',c['type'],'없음',c['description']] for c in t['columns']],
              [23,30,6,11,31,10,82])
    sheet(wb,'인덱스',['표','구분','컬럼'],
          [[t['name'],'PK',', '.join(t['pk'])] for t in [*TABLES,STATE]]+
          [[t['name'],'일반 인덱스',', '.join(i)] for t in TABLES for i in t['indexes']],[30,18,110])
    sheet(wb,'기존표대응',['원장군','기존표','사용범위','목표역할','원컬럼전체','보존계약','근거파일','줄'],mappings,[20,31,37,25,85,95,70,8])
    sheet(wb,'기존컬럼대응',['원장군','기존표','기존컬럼','기존정의','목표역할','원값보존방식','근거파일'],column_rows,[20,30,28,72,24,95,70])
    sheet(wb,'코드변경',['파일','함수·경계','책임','변경내용'],CHANGE_MAP,[75,45,20,100])
    workbook_name = 'Agent_테이블컬럼_및_기록대응_'+DESIGN_LABEL+'.xlsx'
    wb.save(OUT/workbook_name)
    validation=[]
    def check(name,ok,detail):
        validation.append(dict(name=name,passed=bool(ok),detail=detail))
        if not ok:raise AssertionError(name)
    check('gold_contract',snapshot['gold_tables']==13 and snapshot['gold_columns']==60,'활성 매핑 정의 확인; DB 조회 아님')
    check('new_tables',len(TABLES)==EXPECTED_NEW_TABLE_COUNT,'제안 신규 표 수; 기존 상태 별도')
    check('journal_v6_coverage',len([i for i in items if i['group']=='journal-v6'])==31,'v6 SQL CREATE TABLE 31개 추출')
    check('all_source_columns_preserved',all(i['columns'] for i in items) and len(column_rows)==sum(len(i['columns']) for i in items),'정적 컬럼 대응 누락 없음; 실제 데이터 이관 검증 아님')
    valid_keys={t['key'] for t in TABLES}|{'state'}
    check('mapped_targets_exist',all(set(row[3].split(','))<=valid_keys for row in mappings),'목표 역할 참조 대조')
    check('schema_names',all(len(t['name'].encode())<=30 and all(len(c['name'].encode())<=30 for c in t['columns']) for t in TABLES),'30바이트 이하 후보명; 표준사전 승인 아님')
    check('index_columns',all(set(i)<=set(c['name'] for c in t['columns']) for t in TABLES for i in [t['pk'],*t['indexes']]),'PK/인덱스의 미정의 컬럼 없음')
    check('no_gold_ddl','IDD_B03_' not in '\n'.join(ddl) and 'ALTER TABLE' not in '\n'.join(ddl),'DDL 초안은 신규 Agent CREATE만')
    book_file=OUT/workbook_name
    book=load_workbook(book_file,read_only=True)
    check('xlsx_tables',all(book[t['key']].max_row-1==len(t['columns']) for t in [*TABLES,STATE]),'JSON/Excel 컬럼 수 동일')
    check('xlsx_mapping',book['기존컬럼대응'].max_row-1==len(column_rows),'전체 컬럼 대응 시트 행수 동일');book.close()
    changed=[h['path'] for h in hashes if hashlib.sha256((ROOT/h['path']).read_bytes()).hexdigest()!=h['sha256']]
    check('source_unchanged_during_build',not changed,'생성기가 입력 소스에 쓰지 않음')
    write_json('validation.json',dict(status='STATIC_DOCUMENT_CHECKS_PASSED',checks=validation,
               counts=dict(new_tables=len(TABLES),new_columns=schema['new_column_count'],existing_tables=len(items),existing_columns=len(column_rows),change_map_files=len(CHANGE_MAP)),
               not_performed=['Oracle DDL execution','DB changes','runtime implementation','migration','live model','performance benchmark','GENOS deployment','independent review']))
    print(json.dumps(dict(new_tables=len(TABLES),new_columns=schema['new_column_count'],inventory_tables=len(items),inventory_columns=len(column_rows),checks=len(validation)),ensure_ascii=False))


if __name__=='__main__':main()
