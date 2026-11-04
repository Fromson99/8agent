"""Explicit AD boundary, validated SQL executor and faithful table rendering."""
import json
import re
from . import runtime_sqlite as sqlite3
import time
from .oracle_runtime_paths import Path
from .ad_store import Store, fingerprint, ident, table_exists, features
from .ad_backend import Backend
from .ad_jobs import enqueue, schedule_time, record_error, error_detail

ENTER='[AD모드 시작]'
EXIT='[AD모드 종료]'
HELP='''AD모드: shortcut·legal_wiki 관리 전용입니다. 법률 답변은 [AD모드 종료] 후 이용하세요.

| 기능 | 입력 예시 |
|---|---|
| 도움말·현황 | 도움말 / 현재 상태 / 기능 상태 |
| 정상 완료 목록·검색 | shortcut 전체 보여줘 / 위키 목록 / 위키 검색 상장 |
| 전체 내부 SQL 자료 | 전체 테이블 / 테이블 sw_event / 테이블 sw_artifact |
| 표 이동·상세 | 다음 / 이전 / V번호:행번호 자세히 / 2번 자세히 / 계속 |
| 선택 | 2번과 5번 선택 / 첫 표 2번 선택 / 전부 선택 |
| 승인·반려·게시 | 선택한 것 승인 / 2번 반려 / 1번 게시 (근거 현재성 검사, 법률 검증 별도) |
| 수정 | 2번 수정 / 제목을 새 제목으로 수정 / /edit title 새 제목 |
| 구조화 필드 수정 | /edit claims [JSON 배열] / /edit value 새 값 |
| 휴지통·복구 | 2번 버려 / 휴지통 / 방금 버린 것 복구 / 선택한 것 복구 |
| 위키 작업 | 야간작업 돌리기 / 진행상황 알려줘 / 야간작업 리포트 줘 |
| 작업 제어 | 작업 중지 / 작업 재개 / 작업 취소 / 실패 작업 재시도 |
| 예약 | 야간작업 시작 예약 저녁 12시 / 매일 자정 예약 / 예약 목록 / 2번 예약 취소 |
| 오류 | 오류 목록 / 1번 자세히 / 계속 |
| 기능 설정 | shortcut 꺼 / 위키 켜 / 둘 다 꺼 / 둘 다 켜 |
| 종료 | [AD모드 종료] |

shortcut 목록에는 최종 답변 게시까지 성공한 현재 기록만 표시합니다. 실패·진행 중 원장은 전체 테이블에서 조회할 수 있습니다.
숏컷 보여줘 / 1번 보여줘 / 그 사건의 사실도 보여줘 같은 자연어와 후속 대화를 LLM이 해석합니다.
대상이 모호하면 확인 질문에 답해 주세요. 번호는 표 전체에서 고정됩니다. 사용자 승인과 법률 검증은 별도입니다.
예약·실행 중인 작업은 AD모드를 종료해도 계속됩니다. 중단하려면 작업/예약 취소를 입력하세요.
'''


def cell(value):
    return str(value).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|','\\|').replace('\n','<br>')


def table(page):
    text=f"표 {page['view_id']} · {page['position']}/{page['total']}건 · {page['page_number']}/{page['page_count']}페이지\n\n| 번호 | 종류 | ID | 제목 | 상태 |\n|---|---|---|---|---|\n"
    for r in page['rows']:
        text+='| '+ ' | '.join(cell(v) for v in (page['view_id']+':'+str(r['ordinal']),r['kind'],r['entity'],r['title'][:160]+(' … [전체: 번호 자세히]' if len(r['title'])>160 else ''),r['status']))+' |\n'
    directions=[]
    if page['has_previous']:directions.append('이전 페이지: 채팅에 이전 입력')
    if page['has_more']:directions.append('다음 페이지: 채팅에 다음 입력')
    else:directions.append('목록 끝. 본문·이력은 번호로 자세히 조회할 수 있습니다.')
    return text+'\n'+' / '.join(directions)


def detail_rows(value, path=''):
    """Render every stored field, including JSON payloads, without losing content."""
    rows=[]
    if isinstance(value,dict) and value:
        for key,item in value.items():rows.extend(detail_rows(item,path+'.'+str(key) if path else str(key)))
    elif isinstance(value,list) and value:
        for i,item in enumerate(value,1):rows.extend(detail_rows(item,f'{path}[{i}]'))
    else:
        if isinstance(value,str) and value[:1] in ('{','['):
            try:decoded=json.loads(value)
            except ValueError:decoded=None
            if isinstance(decoded,(dict,list)) and decoded:return detail_rows(decoded,path)
        text=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
        pieces=[text[i:i+2000] for i in range(0,len(text),2000)] or ['']
        rows.extend({'field':path+(f' ({i}/{len(pieces)})' if len(pieces)>1 else ''),'value':part} for i,part in enumerate(pieces,1))
    return rows


def fields_table(rows):
    return '| 항목 | 값 |\n|---|---|\n'+'\n'.join('| '+cell(r['field'])+' | '+cell(r['value'])+' |' for r in rows)


class Controller:
    def __init__(self,store,session):
        self.store,self.db,self.session=store,store.db,session
        self.sid=session['id'];self.workspace=session['workspace']
        self.backend=Backend(store,self.workspace)

    def respond(self,text,**fields):
        from .ad_table import render,REVISION
        html_table=render(text)
        display={'table_html':html_table,'table_display_revision':REVISION} if html_table else {}
        return {'response_schema':'ad-mode-v1','ad_mode':True,'answer_status':'administration','text':text,**display,**fields}

    def show(self,kind,query='',trash=False):
        rows=self.backend.list(kind,query,trash)
        for r in rows:
            if kind in ('shortcut','wiki'):r['revision']=self.backend.revision(kind,r['id'])
            elif kind.startswith('table:'):
                try:r['revision']=self.backend.targets([r])[0]['revision']
                except ValueError:pass
        view=self.store.view(self.sid,kind,rows)
        self.db.execute('UPDATE ad_session SET pending_action=NULL,pending_field=NULL WHERE id=?',(self.sid,))
        return self.list_page(view)

    def list_page(self,view=None,*,previous=False):
        page=self.store.page(self.sid,view,previous=previous)
        return self.respond(table(page),**{k:v for k,v in page.items() if k!='rows'})

    def selected(self):
        return [dict(r) for r in self.db.execute('SELECT kind,entity,revision FROM ad_selection WHERE session=? ORDER BY ordinal',(self.sid,))]

    def select(self,text):
        last=self.db.execute('SELECT active_view,last_operation FROM ad_session WHERE id=?',(self.sid,)).fetchone()
        if '방금' in text and any(x in text for x in ('버린','지운','삭제','복구')):
            last_trash=self.db.execute("SELECT o.id FROM ad_operation o JOIN ad_change c ON c.operation=o.id WHERE o.session=? AND c.action='trash' ORDER BY o.created_at DESC LIMIT 1",(self.sid,)).fetchone()
            rows=[dict(r) for r in self.db.execute('SELECT kind,entity,after_revision revision FROM ad_change WHERE operation=? ORDER BY ordinal',(last_trash[0] if last_trash else '',))]
            if any(x in text for x in ('첫 번째','첫번째')):rows=rows[:1]
        else:
            refs=re.findall(r'(V[a-f0-9]{16}):(\d+)',text)
            view=refs[0][0] if refs else last['active_view']
            if '첫 표' in text:
                row=self.db.execute('SELECT id FROM ad_view WHERE session=? ORDER BY created_at LIMIT 1',(self.sid,)).fetchone()
                view=row[0] if row else None
            if not self.db.execute('SELECT 1 FROM ad_view WHERE id=? AND session=?',(view,self.sid)).fetchone():
                if self.selected() and not re.search(r'\d+\s*번',text):return self.selected()
                raise ValueError('AD_TARGET: 먼저 목록을 조회하고 번호를 선택하세요.')
            ordinals=[int(v) for _,v in refs] if refs else [int(v) for v in re.findall(r'(\d+)\s*번',text)]
            # Korean conjunctions: "2, 5번", "2번과 5번".
            if not refs:
                group=re.search(r'(\d+(?:\s*[,와과]\s*\d+)+)\s*번',text)
                if group:ordinals=[int(x) for x in re.findall(r'\d+',group[1])]
            if refs and any(v!=view for v,_ in refs):raise ValueError('AD_TARGET: 한 번에 한 표의 항목을 지정하세요.')
            if ordinals:
                rows=[dict(r) for n in ordinals for r in self.db.execute('SELECT * FROM ad_view_row WHERE view=? AND ordinal=?',(view,n))]
                if len(rows)!=len(ordinals):raise ValueError('AD_TARGET: 표에 없는 번호입니다.')
            elif any(x in text for x in ('전부','전체')):
                rows=[dict(r) for r in self.db.execute('SELECT * FROM ad_view_row WHERE view=? ORDER BY ordinal',(view,))]
            else:return self.selected()
            # Preserve displayed revisions, not fresh versions from a new search.
            native=[]
            for r in rows:
                if r['kind'] in ('shortcut','wiki','job','schedule','error','table'):
                    native.append({'kind':r['kind'],'entity':r['entity'],'revision':r['revision']})
                elif r['kind'].startswith('table:'):
                    native.append({'kind':r['kind'],'entity':r['entity'],'revision':r['revision']})
                else:native.extend(self.backend.targets([r]))
            rows=native
        if not rows:raise ValueError('AD_TARGET: 선택된 항목이 없습니다.')
        self.db.execute('DELETE FROM ad_selection WHERE session=?',(self.sid,))
        self.db.executemany('INSERT INTO ad_selection VALUES(?,?,?,?,?)',[(self.sid,i+1,r['kind'],r['entity'],r['revision']) for i,r in enumerate(rows)])
        return rows

    def detail(self,targets):
        if not targets:raise ValueError('AD_TARGET: 조회할 번호를 선택하세요.')
        result=[self.backend.detail(t['kind'],t['entity']) for t in targets]
        content=json.dumps({'display_schema':'ad-detail-table-v1','rows':detail_rows(result)},ensure_ascii=False)
        key=ident('D');self.db.execute('INSERT INTO ad_detail VALUES(?,?,?,?,?,?)',(key,self.sid,','.join(t['entity'] for t in targets),content,0,time.time()))
        return self.detail_page(key)

    def detail_page(self,key=None):
        row=self.db.execute('SELECT * FROM ad_detail WHERE session=? '+('AND id=? ' if key else '')+'ORDER BY created_at DESC LIMIT 1', (self.sid,key) if key else (self.sid,)).fetchone()
        if not row:raise ValueError('AD_DETAIL: 자세히 조회할 항목을 먼저 선택하세요.')
        parsed=json.loads(row['content'])
        if isinstance(parsed,dict) and parsed.get('display_schema')=='ad-detail-table-v1':
            rows=parsed['rows'];start=row['position'];end=start;chars=0
            while end<len(rows) and (end==start or chars+len(rows[end]['value'])<=10000):
                chars+=len(rows[end]['value']);end+=1
            self.db.execute('UPDATE ad_detail SET position=? WHERE id=?',(end,row['id']))
            return self.respond(f"상세 {row['id']} · 항목 {start+1 if end>start else end}–{end}/{len(rows)}\n\n"+fields_table(rows[start:end])+'\n\n'+('다음 본문: 계속' if end<len(rows) else '본문 끝.'),detail_id=row['id'],has_more=end<len(rows))
        start=row['position'];end=min(len(row['content']),start+10000)
        chunk=row['content'][start:end]
        self.db.execute('UPDATE ad_detail SET position=? WHERE id=?',(end,row['id']))
        # A long fence prevents stored content from terminating the display block.
        fence='`'*(max([len(x) for x in re.findall(r'`+',chunk)]+[2])+1)
        return self.respond(f"상세 {row['id']} · 문자 {start+1 if end>start else end}–{end}/{len(row['content'])}\n\n{fence}text\n{chunk}\n{fence}\n\n"+('다음 본문: 계속' if end<len(row['content']) else '본문 끝.'),detail_id=row['id'],has_more=end<len(row['content']))

    def mutate(self,text,action,operation,field=None,value=None):
        targets=self.select(text)
        if not targets:raise ValueError('AD_TARGET: 번호나 선택 대상을 지정하세요.')
        resolved=[]
        for t in targets:
            if t['kind'].startswith('table:'):resolved.extend(self.backend.targets([t]))
            else:resolved.append(t)
        results=[]
        for i,t in enumerate(resolved,1):results.append(self.backend.change(t,action,operation,i,field,value))
        for result in results:
            self.db.execute('UPDATE ad_view_row SET revision=?,status=? WHERE kind=? AND entity=? AND revision=? AND view IN (SELECT id FROM ad_view WHERE session=?)',(result['after_revision'],action,result['kind'],result['id'],result['before_revision'],self.sid))
        self.db.execute('UPDATE ad_session SET last_operation=?,pending_action=NULL,pending_field=NULL WHERE id=?',(operation,self.sid))
        self.db.execute('DELETE FROM ad_selection WHERE session=?',(self.sid,))
        self.db.executemany('INSERT INTO ad_selection VALUES(?,?,?,?,?)',[(self.sid,i+1,r['kind'],r['id'],r['after_revision']) for i,r in enumerate(results)])
        return self.respond(f'{operation}: {action} {len(results)}건 처리했습니다. 원기록과 변경 이력은 보존합니다.\n\n'+fields_table(detail_rows(results)),operation_id=operation,results=results)

    def execute(self,text,operation):
        q=text.strip()
        pending=self.db.execute('SELECT pending_action,pending_field FROM ad_session WHERE id=?',(self.sid,)).fetchone()
        if pending['pending_action']=='schedule' and q in ('자정','정오'):
            q=re.sub(r'(?<!\d)12\s*시',q,pending['pending_field'] or '야간작업 예약 12시')
            self.db.execute('UPDATE ad_session SET pending_action=NULL,pending_field=NULL WHERE id=?',(self.sid,))
        if pending['pending_action']=='edit' and q.startswith(('제목은 ','제목을 ','주제는 ','질문은 ')) and not any(w in q for w in ('수정','바꿔','고쳐')):q+=' 수정'
        lower=q.lower();compact=re.sub(r'\s+','',lower)
        if q==EXIT:
            self.db.execute('UPDATE ad_session SET enabled=0,revision=revision+1,pending_action=NULL,pending_field=NULL WHERE id=?',(self.sid,))
            self.db.execute('DELETE FROM ad_selection WHERE session=?',(self.sid,))
            return self.respond('AD모드를 종료했습니다. 다음 입력부터 일반 법률 답변으로 돌아갑니다. 예약·실행 작업은 별도 취소 전까지 유지됩니다.',ad_mode=False)
        if q in (ENTER,'도움말','명령어','/help','help') or '어떤 명령' in q:return self.respond(HELP)
        if compact in ('다음','다음페이지','/next','이전','이전페이지','/previous'):
            return self.list_page(previous='이전' in compact or compact=='/previous')
        if compact in ('계속','계속보여줘','본문계속','/continue'):return self.detail_page()
        if any(x in compact for x in ('전체테이블','전체내부','스키마목록')) or lower=='/tables':return self.show('table')
        m=re.search(r'(?:테이블|/table)\s+((?:sw|ad)_[a-z_]+)',q)
        if m:return self.show('table:'+m[1])
        child=next((v for word,v in [('사실',('sw_fact','fact')),('쟁점',('sw_issue','issue')),('발언',('sw_event','event')),('도구',('sw_trace','trace')),('갈래',('sw_branch','table:sw_branch'))] if word in q),None)
        if child and any(w in q for w in ('보여','조회','목록')):
            targets=self.select(q)
            if len(targets)!=1 or targets[0]['kind']!='shortcut':raise ValueError('AD_TARGET: shortcut 사건 하나를 먼저 선택하세요.')
            case=self.backend.record('shortcut',targets[0]['entity']);table_name,child_kind=child
            column='aggregate_id' if table_name=='sw_event' else 'investigation'
            sql='SELECT rowid AS _rowid,* FROM '+table_name+' WHERE '+column+'=?'
            if table_name=='sw_fact':sql+=' AND revision=(SELECT revision FROM sw_fact_head WHERE id=sw_fact.id)'
            rows=[]
            for r in self.db.execute(sql+' ORDER BY rowid',(case['id'],)):
                entity=str(r['_rowid']) if child_kind.startswith('table:') else str(r['id'])
                revision=0 if child_kind.startswith('table:') else self.backend.revision(child_kind,entity)
                rows.append({'id':entity,'kind':child_kind,'revision':revision,'title':str(r['predicate'] if table_name=='sw_fact' else r['question'] if table_name in ('sw_issue','sw_branch') else r['kind']),'status':str(r['status'] if 'status' in r.keys() else '')})
            return self.list_page(self.store.view(self.sid,child_kind,rows))
        if any(x in q for x in ('자세히','내용 보여','내용 알려','상세','열어')) or lower.startswith('/show '):
            targets=self.select(q)
            if len(targets)==1 and targets[0]['kind']=='table' and '열어' in q:return self.show('table:'+targets[0]['entity'])
            return self.detail(targets)
        if ('예약' in q or lower.startswith('/schedule')):
            if any(x in q for x in ('취소','삭제','꺼')):
                targets=self.select(q)
                if not targets:raise ValueError('AD_TARGET: 예약 목록에서 취소할 번호를 선택하세요.')
                for t in targets:
                    if t['kind']!='schedule':raise ValueError('AD_TARGET: 예약 항목을 선택하세요.')
                    self.backend.record('schedule',t['entity'])
                    self.db.execute('UPDATE ad_schedule SET enabled=0 WHERE id=?',(t['entity'],))
                return self.respond(f'예약 {len(targets)}건을 취소했습니다. 실행 중인 작업은 별도 작업 취소로 중단할 수 있습니다.')
            if any(x in q for x in ('목록','보여','현황')) or lower=='/schedules':return self.show('schedule')
            try:due,repeat,when=schedule_time(q)
            except ValueError as exc:
                if 'AD_TIME_AMBIGUOUS' not in str(exc):raise
                self.db.execute("UPDATE ad_session SET pending_action='schedule',pending_field=? WHERE id=?",(q,self.sid))
                return self.respond(str(exc))
            key=ident('R');self.db.execute('INSERT INTO ad_schedule(id,workspace,session,due_at,repeat_seconds,created_at) VALUES(?,?,?,?,?,?)',(key,self.workspace,self.sid,due,repeat,time.time()))
            return self.respond(f'{key}: {when} (한국시간)부터 위키 작업을 시작하도록 '+('매일 ' if repeat else '')+'예약했습니다. 서버 중단 중 놓친 실행은 재가동 후 한 번 이어서 처리합니다.',schedule_id=key,due_at=due)
        if any(x in q for x in ('리포트','작업 목록','작업 이력')) or lower=='/reports':return self.show('job')
        if any(x in q for x in ('오류 목록','오류 보여','실패 내용','에러 목록')) or lower=='/errors':return self.show('error')
        if any(x in q for x in ('진행','얼마나','작업 상태','다 됐','멈춰','중지','재개','이어서 해','작업 취소','재시도')) or lower.startswith('/job'):
            key=self.db.execute('SELECT last_job FROM ad_session WHERE id=?',(self.sid,)).fetchone()[0]
            explicit=re.search(r'J[a-f0-9]{16}',q)
            if explicit:key=explicit[0]
            selected=self.select(q) if re.search(r'\d+\s*번',q) else []
            if selected:
                if len(selected)!=1 or selected[0]['kind']!='job':raise ValueError('AD_TARGET: 작업 하나를 선택하세요.')
                key=selected[0]['entity']
            if not key:return self.show('job')
            job=self.backend.record('job',key)
            if any(x in q for x in ('멈춰','중지','취소','재개','이어서 해','재시도')):
                desired='CANCEL' if '취소' in q else 'PAUSE' if '멈춰' in q or '중지' in q else 'RUN'
                state='CANCELLED' if desired=='CANCEL' else 'PAUSED' if desired=='PAUSE' else 'QUEUED'
                if '재시도' in q:
                    self.db.execute("UPDATE sw_queue SET status='PENDING',attempts=0,next_attempt=0,lease=NULL WHERE id IN (SELECT queue_id FROM ad_job_item WHERE job=? AND status='FAILED')",(key,))
                    self.db.execute("UPDATE ad_job_item SET status='PENDING' WHERE job=? AND status='FAILED'",(key,))
                    self.db.execute('UPDATE ad_job SET failed=0 WHERE id=?',(key,))
                self.db.execute("UPDATE ad_job SET desired=?,status=CASE WHEN status='RUNNING' THEN status ELSE ? END,finished_at=NULL WHERE id=?",(desired,state,key))
            self.db.execute('UPDATE ad_session SET last_job=? WHERE id=?',(key,self.sid))
            return self.detail([{'kind':'job','entity':key}])
        if any(x in q for x in ('돌리','돌려','실행','작업 시작')) and any(x in lower for x in ('야간','위키','wiki')) or lower=='/wiki build':
            if not features(self.db,self.workspace)['wiki']:raise ValueError('AD_DISABLED: 위키가 꺼져 있습니다. 위키 켜 입력 후 실행하세요.')
            key=enqueue(self.store,self.sid,self.workspace)
            return self.respond(f'{key}: 위키 구성 작업을 접수했습니다. 진행상황/리포트로 확인할 수 있습니다. 결과는 검토 전 초안입니다.',job_id=key)
        feature=re.search(r'(shortcut|쇼트컷|단축|wiki|위키|둘\s*다|전부).*?(끄기|켜기|꺼|켜|비활성|활성|\boff\b|\bon\b)',lower)
        if feature:
            name,word=feature.groups();enabled=word in ('켜기','켜','활성','on')
            names=['shortcut','wiki'] if name.replace(' ','') in ('둘다','전부') else ['shortcut' if name in ('shortcut','쇼트컷','단축') else 'wiki']
            for name in names:self.db.execute('UPDATE ad_feature SET '+name+'=?,revision=revision+1,changed_at=? WHERE workspace=?',(int(enabled),time.time(),self.workspace))
            if 'wiki' in names:
                if not enabled:self.db.execute("UPDATE ad_job SET desired='PAUSE',status=CASE WHEN status='QUEUED' THEN 'PAUSED' ELSE status END WHERE workspace=? AND status IN('QUEUED','RUNNING')",(self.workspace,))
            return self.respond('현재 업무 공간에 적용했습니다. '+', '.join(names)+' '+('ON' if enabled else 'OFF')+'. 자료는 삭제하지 않습니다. 관리·복구는 AD모드에서 계속 가능합니다.',features=features(self.db,self.workspace))
        if any(x in q for x in ('현재 상태','기능 상태','현황','/status')):
            return self.respond(json.dumps({'workspace':self.workspace,'workers':[dict(r) for r in self.db.execute('SELECT *, (? - heartbeat) AS heartbeat_age_seconds FROM ad_worker',(time.time(),))],'features':features(self.db,self.workspace),'jobs':self.backend.list('job'),'schedules':self.backend.list('schedule')},ensure_ascii=False,indent=2))
        if ('휴지통' in q and not any(w in q for w in ('복구','살려','승인','반려','수정','버려','삭제'))) or lower=='/trash':
            rows=self.backend.list('shortcut',trash=True)+self.backend.list('wiki',trash=True)
            for r in rows:r['revision']=self.backend.revision(r['kind'],r['id'])
            for r in self.db.execute("SELECT kind,entity FROM ad_object WHERE workspace=? AND trashed=1 AND kind NOT IN('shortcut','wiki')",(self.workspace,)):
                rows.append({'kind':r['kind'],'id':r['entity'],'title':r['entity'],'revision':self.backend.revision(r['kind'],r['entity']),'status':'TRASHED'})
            return self.list_page(self.store.view(self.sid,'trash',rows))
        # Mutation words only operate inside this controller. No legal-agent route.
        action=next((a for a,words in [('publish',('게시',)),('restore',('복구','살려','되살려')),('trash',('버려','지워','삭제')),('reject',('반려','승인취소')),('approve',('승인',)),('edit',('수정','바꿔','고쳐','/edit'))] if any(w in compact for w in words)),None)
        if action=='edit':
            if re.search(r'\d+\s*번',q):self.select(q)
            aliases={'제목':'title','주제':'topic','질문':'question','값':'value','조건':'claims','미해결':'unresolved','적용시점':'applicable_time'}
            m=re.search(r'/edit\s+([a-z_]+)\s+([\s\S]+)',q)
            if m:field,value=m[1],m[2]
            else:
                m=re.search(r'(제목|주제|질문|값|미해결|적용시점)(?:을|를|은|는)?\s+(.+?)(?:으로|로)?\s*(?:수정|바꿔|고쳐)(?:해|줘)?\s*$',q)
                field,value=(aliases[m[1]],m[2]) if m else (None,None)
            if field is None:
                self.db.execute("UPDATE ad_session SET pending_action='edit' WHERE id=?",(self.sid,))
                return self.respond('선택을 유지했습니다. 바꿀 필드와 값을 입력하세요. 예: 제목을 새 제목으로 수정 / /edit unresolved ["확인 필요"]')
            if value[:1] in ('[','{','"') or value in ('true','false','null'):
                try:value=json.loads(value)
                except json.JSONDecodeError as exc:raise ValueError('AD_SCHEMA: JSON 수정값 오류: '+str(exc)) from exc
            return self.mutate('선택한 것','edit',operation,field,value)
        if action:return self.mutate(q,action,operation)
        if q=='선택 내용':return self.detail(self.selected())
        if '선택' in q or lower.startswith('/select'):
            selected=self.select(q)
            return self.respond('선택했습니다.\n'+json.dumps(selected,ensure_ascii=False,indent=2))
        kind='shortcut' if any(w in lower for w in ('shortcut','쇼트컷')) else 'wiki' if any(w in lower for w in ('wiki','위키')) else None
        if kind:
            search=re.search(r'(?:검색|찾아)\s+(.+)',q)
            return self.show(kind,search[1] if search else '')
        if q=='선택 내용':return self.detail(self.selected())
        raise ValueError('AD_COMMAND: 관리 명령을 해석하지 못했습니다. 법률 agent에는 전달하지 않았습니다. 도움말을 입력하거나 대상 번호·필드·작업을 지정하세요.')


def handle(path, workspace, channel, chat, question, request_id, *, interpret=None):
    """None means ordinary legal routing; never invent an AD session on a question."""
    path=Path(path);q=str(question or '').strip()
    if not path.exists() and q!=ENTER:return None
    key=fingerprint([workspace,channel,chat])
    if q!=ENTER:
        db=None
        try:
            db=sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True,timeout=5)
            if not table_exists(db,'ad_session'):return None
            row=db.execute('SELECT enabled FROM ad_session WHERE id=?',(key,)).fetchone()
            if not row or not row[0]:return None
        except sqlite3.Error as exc:
            # Never pass a potential active management turn to legal inference.
            return {'response_schema':'ad-mode-v1','ad_mode':None,'answer_status':'error','text':'AD_SESSION_SQL_ERROR: 대화 모드 확인 실패.\n'+error_detail(exc)}
        finally:
            if db:db.close()
    if interpret is not None and q not in (ENTER,EXIT):
        from .ad_language import handle_turn
        return handle_turn(path,workspace,channel,chat,q,request_id,interpret)
    store=None;operation=None;session=None
    try:
        store=Store(path)
        Backend(store,workspace)  # DDL outside the command transaction.
        with store.transaction():
            session=store.session(workspace,channel,chat)
            previous=store.db.execute('SELECT * FROM ad_operation WHERE session=? AND request=?',(session['id'],request_id)).fetchone()
            input_hash=fingerprint(q)
            if previous:
                if previous['input_hash']!=input_hash:raise ValueError('AD_IDEMPOTENCY: same request_id used with different input')
                if previous['response']:return json.loads(previous['response'])
            operation=ident('OP')
            store.db.execute('INSERT INTO ad_operation(id,session,request,input_hash,action,status,created_at) VALUES(?,?,?,?,?,?,?)',
                (operation,session['id'],request_id,input_hash,q,'RUNNING',time.time()))
            if q==ENTER:
                store.db.execute('UPDATE ad_session SET enabled=1,revision=revision+1 WHERE id=?',(session['id'],))
                result={'response_schema':'ad-mode-v1','ad_mode':True,'answer_status':'administration','text':'AD모드를 시작했습니다. shortcut·legal_wiki 관리 전용입니다.\n\n'+HELP}
            else:
                if not session['enabled']:raise ValueError('AD_REQUIRED: [AD모드 시작]을 단독 입력하세요.')
                # The legacy executor is also used for server-constructed commands
                # after a validated model decision. Never feed it raw chat as a
                # fallback when the management interpreter is unavailable.
                if q!=EXIT:raise ValueError('AD_MODEL_REQUIRED: 관리 명령 해석 모델이 연결되지 않았습니다. 요청을 실행하지 않았습니다.')
                result=Controller(store,session).execute(q,operation)
            store.db.execute("UPDATE ad_operation SET status='SUCCEEDED',finished_at=?,response=? WHERE id=?",(time.time(),json.dumps(result,ensure_ascii=False),operation))
            return result
    except Exception as exc:
        from .observability import _redact_secrets
        detail=error_detail(exc);error={'error_type':type(exc).__name__,'message':_redact_secrets(str(exc)),'detail':detail}
        if store and session:
            try:
                with store.transaction():
                    # Failed transaction contains no partial mutations. Persist a
                    # failure separately so the user can inspect the whole cause.
                    operation=ident('OP')
                    store.db.execute('INSERT OR IGNORE INTO ad_operation(id,session,request,input_hash,action,status,created_at) VALUES(?,?,?,?,?,?,?)',
                        (operation,session['id'],request_id,fingerprint(q),q,'FAILED',time.time()))
                    saved=store.db.execute('SELECT id FROM ad_operation WHERE session=? AND request=?',(session['id'],request_id)).fetchone()
                    operation=saved[0] if saved else None
                    error=record_error(store,exc,'ad.command',session=session['id'],operation=operation)
            except Exception:pass
        from .observability import _redact_secrets
        text='AD 작업 실패 — '+_redact_secrets(str(exc))+'\n\n'+detail
        return {'response_schema':'ad-mode-v1','ad_mode':True,'answer_status':'error','text':text,'error':error}
    finally:
        if store:store.close()
