#!/usr/bin/env python3
"""Read-only, offline wording/reference audit. No model, network or product mutation."""
import argparse
from collections import Counter, OrderedDict
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import resource
import shutil
import sqlite3
import sys
import time

VERSION = 'internal-reference-wording-audit-v1'
PATTERNS = {
    '위임': r'위임', '준용': r'준용', '준하여': r'준하여|준한다',
    '따름': r'따른다|따라|따르는|따른', '정함': r'정한|정하는|정하여|정한다',
    '의함': r'의한다|의하여|의거', '갈음': r'갈음', '적용': r'적용한다|적용하며|적용되는',
    '참조': r'참조|명시된|기재된', '별도 정함': r'(?:별도(?:로)?|따로)[^.。;\n]{0,50}정[한하]',
    '불특정 규정': r'(?:관련|관계|해당|별도(?:의)?)\s*(?:법령|법률|준칙|규정|규칙|세칙|지침|기준)',
    '보충 규정': r'정하지\s*(?:아니한|않은)|규정하지\s*(?:아니한|않은)',
    '명시 좌표': r'제\s*\d+\s*(?:조(?:의\s*\d+)?|항|호)|별표\s*\d+|별지\s*제?\s*\d+',
}
RX = {k: re.compile(v) for k,v in PATTERNS.items()}
LABELS = {'NO_REFERENCE':'참조 레코드 없음 · 확인 필요', 'NEARBY_REFERENCE':'같은 문장에 연결 존재 · 대응 검토',
          'UNRESOLVED':'대상 미확정/부분 연결', 'BROKEN':'원문·구조·색인 불일치',
          'RESTRICTED':'대상 권한 범위 밖/분류 미확인', 'UNVERIFIED':'구형 계약 · 일부 검사 불가'}
CSS = '''body{font:15px/1.65 system-ui,sans-serif;margin:30px auto;max-width:1500px;padding:0 20px;color:#173047;background:#f5f7fa}h1{font-size:28px}header,.box{background:white;padding:22px;border-radius:12px;margin:16px 0}table{border-collapse:collapse;width:100%;background:white}th,td{border:1px solid #d8e0e7;padding:12px;vertical-align:top;text-align:left}th{background:#eaf0f7;position:sticky;top:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}small{color:#607284}input,select,button{padding:10px;margin:5px}a{color:#005ab5}.BAD{color:#b42318}.WARN{color:#a35c00}mark{background:#fff1a8}details{margin:8px 0}code{overflow-wrap:anywhere}.badge{border-radius:6px;background:#edf2f7;padding:5px}''' 
JS = '''<script>function filter(){let q=document.getElementById('q').value.toLowerCase(),s=document.getElementById('status').value,n=0;document.querySelectorAll('tr.hit').forEach(r=>{let show=(!s||r.dataset.status===s)&&r.textContent.toLowerCase().includes(q);r.hidden=!show;if(show)n++});document.getElementById('shown').textContent=n+'행 표시'}document.getElementById('q').addEventListener('input',filter);document.getElementById('status').addEventListener('change',filter);filter();</script>'''

def esc(v): return html.escape(str(v if v is not None else ''))
def dump(v): return json.dumps(v,ensure_ascii=False,sort_keys=True)
def sha_text(v): return hashlib.sha256(v.encode()).hexdigest()
def log(event, **v): print(dump({'time':datetime.now(timezone.utc).isoformat(),'event':event,**v}),flush=True)
def write_json(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def head(title): return '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'+esc(title)+'</title><style>'+CSS+'</style><body><h1>'+esc(title)+'</h1>'

def file_hash(p):
    h=hashlib.sha256(); total=0; last=time.monotonic()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):
            h.update(b);total+=len(b)
            if time.monotonic()-last>15: log('hash-progress',file=p.name,bytes=total);last=time.monotonic()
    return h.hexdigest()

def safe(root,name):
    p=root/name
    if p.is_symlink(): raise ValueError('Input symlink: '+str(p))
    p.resolve().relative_to(root.resolve())
    return p.resolve()

def ro(p):
    for suffix in ('-wal','-shm','-journal'):
        if Path(str(p)+suffix).exists(): raise ValueError('Database is not a sealed generation: '+str(p))
    c=sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    c.execute('pragma query_only=on');c.execute('pragma cache_size=-4096');return c

def meta(row):
    v=json.loads(row['metadata'] or '{}'); variants=[v]+(v.get('aliases') or [])
    categories={x.get('source_category') or x.get('kind') for x in variants}
    folders=[x.get('folder_names') or [] for x in variants]
    if not any(categories): categories={f[0] for f in folders if f}
    if not any(categories) and row['name'].startswith(('internal >','external >')): categories={row['name'].split(' >')[0]}
    teams={x.get('team') for x in variants if x.get('team')}
    teams.update(f[1] for f in folders if len(f)>1 and f[0]=='internal')
    if not teams and row['name'].startswith('internal > '): teams={row['name'].split(' > ')[1]}
    return {'id':row['document_id'],'name':row['name'],'category':'internal' if 'internal' in categories else 'external' if 'external' in categories else 'unknown',
            'teams':sorted(teams),'source_artifact_sha256':row['source_artifact_sha256'],
            'version':v.get('effective_date') or v.get('version') or v.get('revision') or '판본 메타데이터 없음 — 제목·원본 해시 대조'}

def allowed(doc,team): return doc['category']=='external' or (doc['category']=='internal' and team in doc['teams'])

def cue_sentences(text, keywords=()):
    for m in re.finditer(r'.+?(?:[。;\n]|[.](?=\s|$)|$)',text,re.S):
        # Periods in legal coordinates/decimals are kept; attribution remains a candidate.
        s=m.group(); hits=[]
        for label,rx in RX.items():
            for hit in rx.finditer(s):
                # A heading alone is not an explicit cross-reference.
                if label=='명시 좌표' and hit.start()==0 and not re.search(r'(?:에|의|을|를|과|와|부터|까지|준용|따라)',s[hit.end():]): continue
                hits.append({'kind':label,'text':hit[0],'start':m.start()+hit.start(),'end':m.start()+hit.end()})
        for word in keywords:
            for hit in re.finditer(re.escape(word),s):hits.append({'kind':'지정 용어','text':word,'start':m.start()+hit.start(),'end':m.start()+hit.end()})
        if hits: yield m.start(),m.end(),s,hits

class Audit:
    def __init__(self,args,out):
        self.args,self.out=args,out;self.pins={};self.cache=OrderedDict();self.targets=set();self.started=time.monotonic();self.rows=0;self.counts=Counter();self.doc_counts=Counter();self.scanned=0
        self.summary={'schema_version':VERSION,'status':'INCOMPLETE','team':args.team,'runtime_serving_verified':False,'model_calls':0,
            'meaning_verified':False,'patterns':PATTERNS,'limits':{'rss_mib':args.max_rss_mib,'seconds':args.max_seconds,'output_mib':args.max_output_mib},
            'scope':'선택한 generation의 원문과 navigation 참조 색인. Oracle publication·동적 관계 원장·실제 배포 리비전 검사는 포함하지 않음.'}
    def guard(self):
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
        if rss>self.args.max_rss_mib or time.monotonic()-self.started>self.args.max_seconds: raise RuntimeError('RESOURCE_LIMIT: partial report preserved')
        if shutil.disk_usage(self.out).free<256*1024**2: raise RuntimeError('LOW_DISK: partial report preserved')
        size=sum(p.stat().st_size for p in self.out.rglob('*') if p.is_file())
        if size>self.args.max_output_mib*1024**2: raise RuntimeError('OUTPUT_LIMIT: partial report preserved')
    def pin(self,p,expected=None):
        before=p.stat();h=file_hash(p);after=p.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Input changed while hashing')
        if expected is not None and h!=expected:raise ValueError('HASH_MISMATCH: '+str(p))
        self.pins[str(p)]={'sha256':h,'bytes':after.st_size,'mtime_ns':after.st_mtime_ns};return h
    def load(self):
        a=self.args;root=Path(a.code_root).resolve();config=root/'00_SYSTEM/GENOS_SERVING_PATHS.json'
        if os.environ.get('DP','').lower() in ('oracle','true','1'):
            raise ValueError('Oracle mode: this audit requires a bound immutable generation; do not treat an old generation as live Oracle data')
        value=a.generation; binding={}
        if config.exists():
            if config.is_symlink():raise ValueError('Deployment config symlink')
            self.pin(config);binding=json.loads(config.read_text())
            if binding.get('schema_version')!='genos-serving-paths-v1' or binding.get('selection')!='operator-fixed':raise ValueError('Unsupported deployment config')
            if value and Path(value).resolve()!=Path(binding['generation']).resolve():raise ValueError('Explicit generation differs from DEV binding')
            value=value or binding.get('generation')
        value=value or os.environ.get('GENOS_GENERATION')
        if not value:raise ValueError('GENERATION_REQUIRED: use --generation /actual/selected/generation (no latest-directory guessing)')
        g=Path(value)
        if not g.is_absolute():raise ValueError('Absolute generation required')
        g=g.resolve(); self.generation=g
        if self.out==g or g in self.out.parents or self.out in g.parents:raise ValueError('Output overlaps generation')
        gm=safe(g,'manifest.json');self.pin(gm,binding.get('generation_manifest_sha256'));m=json.loads(gm.read_text())
        if m.get('schema_version') not in ('term-source-generation-v1','term-source-generation-v2'):raise ValueError('Unsupported source schema')
        nr=safe(g,m['navigation']['path']);nm=safe(nr,'manifest.json');self.pin(nm,m['navigation']['manifest_sha256']);n=json.loads(nm.read_text())
        if n.get('schema_version') not in {'term-navigation-index-v'+str(i) for i in range(2,8)}:raise ValueError('Unsupported navigation schema')
        canon={k:v for k,v in m.items() if k not in {'navigation','fulltext','fulltext_derivation'}}
        if n['generation_id']!=m['generation_id'] or n['source_store_sha256']!=m['store_sha256'] or n['source_manifest_sha256']!=sha_text(json.dumps(canon,ensure_ascii=False,sort_keys=True,separators=(',',':'))):raise ValueError('NAV_SOURCE_BINDING_MISMATCH')
        sp=safe(g,'store.sqlite');np=safe(nr,'navigation.sqlite');self.pin(sp,m['store_sha256']);self.pin(np,n['index_sha256'])
        self.sd,self.nd=ro(sp),ro(np)
        self.tables={r[0] for r in self.nd.execute("select name from sqlite_master where type in ('table','view')")}
        if not {'source','reference','reference_end'}<=self.tables:raise ValueError('Required navigation tables absent')
        self.docs={r['document_id']:meta(r) for r in self.sd.execute("select document_id,name,source_artifact_sha256,json_extract(json,'$.document_metadata') as metadata from document")}
        chosen=[d for d in self.docs.values() if d['category']=='internal' and a.team in d['teams'] and (not a.document_contains or a.document_contains in d['name'])]
        if not chosen:raise ValueError('No internal documents in the requested explicit team scope')
        self.chosen=chosen
        self.summary.update(generation=str(g),generation_id=m['generation_id'],selection_basis='DEV operator binding' if binding else 'explicit argument/environment; deployment not independently verified',documents_selected=len(chosen),documents_unknown_category=sum(d['category']=='unknown' for d in self.docs.values()),document_filter=a.document_contains)
        for p in (root/'service.py',root/'02_BACKEND/semantic_runtime/term_references.py'):
            if p.is_file():self.pin(p)
        self.pin(Path(__file__).resolve());write_json(self.out/'inputs.json',self.pins)
    def source(self,sid):
        if sid in self.cache:self.cache.move_to_end(sid);return self.cache[sid]
        row=self.nd.execute('select json from source where id=?',(sid,)).fetchone()
        v=json.loads(row[0]) if row else None
        self.cache[sid]=v
        if len(self.cache)>8:self.cache.popitem(last=False)
        return v
    def location(self,did,uid):
        result=[];seen=set()
        while uid is not None and str(uid) not in seen:
            uid=str(uid);seen.add(uid);r=self.sd.execute('select parent_id,json from source_unit where document_id=? and unit_id=?',(did,uid)).fetchone()
            if not r:return '구조 좌표 미확인 · '+uid
            u=json.loads(r['json']);result.append(u.get('title') or u.get('surface') or uid);uid=r['parent_id']
        return ' / '.join(reversed(result)) or '구조 미지정'
    def target(self,t):
        s=self.source(t['source_id'])
        if not s:return {'status':'BROKEN','reason':'TARGET_SOURCE_MISSING'}
        d=self.docs.get(s['document_id'])
        if not d or not allowed(d,self.args.team):return {'status':'RESTRICTED','reason':'TARGET_OUTSIDE_TEAM_OR_UNKNOWN'}
        issues=[];ids=list(map(str,t.get('block_ids') or [b['block_id'] for b in s['blocks']]))
        sb={str(b['block_id']):b['text'] for b in s['blocks']}; blocks=[]
        for bid in ids:
            r=self.sd.execute('select text from source_block where document_id=? and block_id=?',(d['id'],bid)).fetchone()
            if not r or bid not in sb or r['text']!=sb[bid]:issues.append('TARGET_BLOCK_MISMATCH:'+bid)
            elif r:blocks.append((bid,r['text']))
        selected=[]
        for span in t.get('spans') or []:
            bid=str(span.get('block_id'));body=sb.get(bid);x,y=span.get('start_cp'),span.get('end_cp')
            if bid not in ids or body is None or type(x)is not int or type(y)is not int or not 0<=x<y<=len(body):issues.append('TARGET_SPAN_RANGE');continue
            if (span.get('block_hash') and span['block_hash']!=sha_text(body)) or (span.get('span_hash') and span['span_hash']!=sha_text(body[x:y])):issues.append('TARGET_SPAN_HASH');continue
            selected.append((bid,x,y,body[x:y]))
        uid=t.get('unit_id')
        if uid is not None:
            if not self.sd.execute('select 1 from source_unit where document_id=? and unit_id=?',(d['id'],str(uid))).fetchone():issues.append('TARGET_UNIT_MISSING')
            if 'source_unit_map' in self.tables:
                u=self.nd.execute('select block_ids from source_unit_map where source_id=? and unit_id=?',(s['id'],str(uid))).fetchone()
                if not u or not set(ids)<=set(map(str,json.loads(u[0]))):issues.append('TARGET_UNIT_BLOCK_SCOPE')
            else:issues.append('TARGET_UNIT_SCOPE_UNVERIFIED')
        if not blocks:issues.append('TARGET_TEXT_EMPTY')
        key=sha_text(dump(t));name='target-'+key[:24]+'.html'
        if key not in self.targets:
            self.targets.add(key)
            text=head('연결 대상 원문')+'<a href="index.html">← 점검표</a><div class="box"><h2>'+esc(d['name'])+'</h2><p>'+esc(self.location(d['id'],uid or s.get('unit_id')))+'</p><p>문서 ID: '+esc(d['id'])+'<br>판본: '+esc(d['version'])+'<br>원본 SHA256: '+esc(d['source_artifact_sha256'])+'</p><p>'+esc(issues or '선택 generation에서 원문·구조 확인')+'</p>'
            for bid,x,y,body in selected:text+='<div class="box"><b>실제 선택 구간 · 블록 '+esc(bid)+' ['+str(x)+','+str(y)+')</b><pre>'+esc(body)+'</pre></div>'
            for bid,b in blocks:text+='<details open><summary>문맥 원문 · 블록 '+esc(bid)+'</summary><pre>'+esc(b)+'</pre></details>'
            (self.out/name).write_text(text+'</div></body></html>',encoding='utf-8')
        status='BROKEN' if issues and issues!=['TARGET_UNIT_SCOPE_UNVERIFIED'] else 'UNVERIFIED' if issues else 'OK'
        return {'status':status,'issues':issues,'document':d['name'],'source_id':s['id'],'unit_id':uid,'href':name}
    def check_ref(self,r,block,did):
        errors=[];unknown=[];text=block['text'];sid=r.get('source_id');s=self.source(sid)
        if not s or s.get('document_id')!=did or not any(str(b['block_id'])==str(block['block_id']) and b['text']==text for b in s.get('blocks',[])):errors.append('SOURCE_BINDING')
        if r.get('document_id')!=did or r.get('source_text')!=text or r.get('source_text_sha256')!=sha_text(text):errors.append('WITNESS_HASH_OR_TEXT')
        x,y=r.get('mention_start'),r.get('mention_end')
        if type(x)is not int or type(y)is not int or not 0<=x<=y<=len(text):unknown.append('MENTION_SPAN_UNVERIFIED')
        elif text[x:y]!=r.get('mention_text') or (r.get('mention_text_sha256') and sha_text(text[x:y])!=r['mention_text_sha256']):errors.append('MENTION_MISMATCH')
        targets=r.get('targets')
        if not isinstance(targets,list):
            targets=[{'source_id':z,'unit_id':r.get('target_unit_id'),'block_ids':r.get('target_block_ids') or []} for z in r.get('target_source_ids',[])];unknown.append('LEGACY_TARGET_CONTRACT')
        if set(r.get('target_source_ids') or [])!={t['source_id'] for t in targets}:errors.append('TARGET_IDS_DIFF')
        ends={x[0] for x in self.nd.execute('select source_id from reference_end where reference_id=?',(r['id'],))}
        if ends!={sid}|{t['source_id'] for t in targets}:errors.append('REVERSE_INDEX_DIFF')
        if 'reference_target' in self.tables:
            actual=[(x['source_id'],x['unit_id'],json.loads(x['block_ids']),json.loads(x['unit_path']),x['target_level']) for x in self.nd.execute('select * from reference_target where reference_id=? order by ordinal',(r['id'],))]
            expect=[(t['source_id'],t.get('unit_id'),t.get('block_ids') or [],t.get('unit_path') or [],t.get('target_level') or 'article') for t in targets]
            if actual!=expect:errors.append('TARGET_TABLE_DIFF')
        else:unknown.append('TARGET_TABLE_UNAVAILABLE')
        checked=[self.target(t) for t in targets]
        status='NEARBY_REFERENCE'
        if not targets or r.get('coverage_state') in ('PARTIAL','UNRESOLVED') or r.get('resolution')=='UNRESOLVED':status='UNRESOLVED'
        if unknown or any(t['status']=='UNVERIFIED' for t in checked):status='UNVERIFIED'
        if any(t['status']=='RESTRICTED' for t in checked):status='RESTRICTED'
        if errors or any(t['status']=='BROKEN' for t in checked):status='BROKEN'
        return {'id':r['id'],'status':status,'mention':r.get('mention_text'),'role':r.get('reference_role'),'reason':r.get('reason'),'coverage':r.get('coverage_state'),'errors':errors,'unverified':unknown,'targets':checked,'source_id':sid}
    def scan(self):
        out=self.out; h=(out/'index.html').open('w',encoding='utf-8');j=(out/'findings.jsonl').open('w',encoding='utf-8')
        h.write(head('내규 연결 표현 점검')+'<header><b id="runstate">미완료 — 파일 끝의 실행 결과를 확인하세요.</b><p>위임·준용·참조 표현 → 저장된 참조 → 대상 원문을 순서대로 확인합니다. 같은 문장/블록에 존재하는 연결은 의미상 대응의 증명이 아닙니다. “참조 없음”은 규정 부재 또는 법적 오류를 뜻하지 않습니다.</p><p>검사 범위: '+esc(self.args.team)+' · '+esc(self.summary['generation_id'])+'</p><p>실제 배포 리비전, Oracle·동적 관계 원장, LLM의 관계 해석은 미검증입니다.</p><a href="summary.json">실행 요약</a> · <a href="findings.jsonl">전체 점검 기록</a> · <a href="inputs.json">입력 해시</a></header><input id="q" placeholder="신상품 / 관련 준칙 / 문서명 검색"><select id="status"><option value="">전체 상태</option>'+''.join('<option value="'+k+'">'+v+'</option>' for k,v in LABELS.items())+'</select><span id="shown"></span><table><thead><tr><th>내규 출처</th><th>검색 표현과 실제 원문</th><th>연결 점검 / 대상 원문</th></tr></thead><tbody>')
        try:
            for d in self.chosen:
                self.guard();did=d['id'];log('document-start',document_id=did)
                # One document's references only; source bodies remain in the read-only DB.
                refs={}
                rt='reference_payload' if 'reference_payload' in self.tables else 'reference'
                for rr in self.nd.execute("select id,json_extract(json,'$.block_id'),json_extract(json,'$.mention_start'),json_extract(json,'$.mention_end') from "+rt+' where document_id=?',(did,)):
                    r={'id':rr[0],'mention_start':rr[2],'mention_end':rr[3]};refs.setdefault(str(rr[1]),[]).append(r)
                definitions={}
                if 'definition' in self.tables:
                    for rr in self.nd.execute('select json from definition where document_id=?',(did,)):
                        r=json.loads(rr[0]);definitions.setdefault(str(r.get('block_id')),[]).append({k:r.get(k) for k in ['id','key','term_ids','definition_status','source_text_sha256']})
                for block in self.sd.execute('select block_id,unit_id,text from source_block where document_id=?',(did,)):
                    self.scanned+=1;bid=str(block['block_id']);text=block['text']; cached={}
                    for a,b,sentence,hits in cue_sentences(text,self.args.keyword):
                        nearby=[]
                        for r in refs.get(bid,[]):
                            x,y=r.get('mention_start'),r.get('mention_end')
                            if type(x)is not int or type(y)is not int or (x<b and y>a):
                                if r['id'] not in cached:
                                    rr=self.nd.execute('select json from reference where id=?',(r['id'],)).fetchone()
                                    if rr is None:cached[r['id']]={'id':r['id'],'status':'BROKEN','mention':'공유 원문 미확보','role':None,'reason':'SHARED_REFERENCE_BODY_MISSING','errors':['SHARED_REFERENCE_BODY_MISSING'],'unverified':[],'targets':[]}
                                    else:cached[r['id']]=self.check_ref(json.loads(rr[0]),block,did)
                                nearby.append(cached[r['id']])
                        statuses={r['status'] for r in nearby}; status=next((s for s in ['BROKEN','RESTRICTED','UNVERIFIED','UNRESOLVED','NEARBY_REFERENCE'] if s in statuses),'NO_REFERENCE')
                        defs=definitions.get(bid,[])
                        if any(x['source_text_sha256']!=sha_text(text) for x in defs):status='BROKEN'
                        self.rows+=1;self.counts[status]+=1;self.doc_counts[did]+=1
                        location=self.location(did,block['unit_id']);value={'row':self.rows,'document':d,'location':location,'block_id':bid,'start':a,'end':b,'text':sentence,'block_sha256':sha_text(text),'cues':hits,'definitions':defs,'status':status,'references':nearby,'other_block_reference_count':len(refs.get(bid,[]))-len(nearby)}
                        j.write(dump(value)+'\n');h.write('<tr class="hit" data-status="'+status+'"><td>'+esc(d['name'])+'<p>'+esc(location)+'</p><small>'+esc(did)+' / 블록 '+esc(bid)+'<br>'+esc(d['version'])+'</small></td><td><b>'+esc(' · '.join(dict.fromkeys(x['kind']+': '+x['text'] for x in hits)))+'</b><pre>'+esc(sentence)+'</pre></td><td><b>'+LABELS[status]+'</b>')
                        if defs:h.write('<p>저장된 정의 용어: '+esc(' · '.join(str(x.get('key') or x['id']) for x in defs))+'</p>')
                        if not nearby:h.write('<p>이 표현 구간에서 대응 참조를 확인하지 못했습니다. 문서명 생략·정의/용어 연결·색인 누락 여부를 검토하세요.</p>')
                        for r in nearby:
                            h.write('<details open><summary>'+esc(r['mention'])+' · '+esc(r['role'])+'</summary><small>'+esc(r['id'])+'</small><p>'+esc(r['reason'] or '')+' '+esc(', '.join(r['errors']+r['unverified']))+'</p>')
                            for t in r['targets']:
                                h.write('<p>'+('<a href="'+t['href']+'">'+esc(t['document'])+' → 실제 원문</a>' if t.get('href') else esc(t.get('reason')))+' · '+esc(t['status'])+'</p>')
                            h.write('</details>')
                        h.write('</td></tr>')
                        if self.rows%50==0:h.flush();j.flush();self.guard();log('scan-progress',rows=self.rows,blocks=self.scanned)
                log('document-done',document_id=did,rows=self.doc_counts[did])
            # Re-hash input assets before certifying stable bytes, sequential streaming.
            for name,pin in self.pins.items():
                p=Path(name);now=p.stat()
                if now.st_size!=pin['bytes'] or now.st_mtime_ns!=pin['mtime_ns'] or file_hash(p)!=pin['sha256']:raise ValueError('INPUT_CHANGED: '+name)
            self.summary['status']='CHECKS_COMPLETED'
        finally:
            self.summary.update(rows=self.rows,counts=dict(self.counts),blocks_scanned=self.scanned,documents=[{'id':d['id'],'name':d['name'],'rows':self.doc_counts[d['id']]} for d in self.chosen],elapsed_seconds=round(time.monotonic()-self.started,2),max_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2))
            h.write('</tbody></table><footer class="box"><b>'+esc(self.summary['status'])+'</b><p>'+esc(dict(self.counts))+'</p><p>표현이 없는 문서도 summary.json의 문서별 0건 목록에 포함됩니다. 자동 점검 완료와 법적 연결의 정확성은 별도입니다.</p></footer>'+JS)
            if self.summary['status']=='CHECKS_COMPLETED':h.write('<script>document.getElementById("runstate").textContent="자동 점검 완료 · 의미 대응은 검토 필요";</script>')
            h.write('</body></html>');h.close();j.close()

def parser():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--generation');p.add_argument('--keyword',action='append',default=['신상품']);p.add_argument('--code-root',default=str(Path.home()/'DEV'));p.add_argument('--output',required=True);p.add_argument('--team',default='risk_team');p.add_argument('--document-contains',default='');p.add_argument('--max-rss-mib',type=int,default=512);p.add_argument('--max-seconds',type=int,default=3600);p.add_argument('--max-output-mib',type=int,default=200);return p

def main():
    args=parser().parse_args();requested=Path(args.output).expanduser()
    if requested.exists() or requested.is_symlink():log('refused',error='Output must be a new directory');return 2
    out=requested.resolve()
    # Reject output/input overlap before creating a directory or log in it.
    bound=Path(args.code_root).expanduser().resolve()/'00_SYSTEM/GENOS_SERVING_PATHS.json'
    candidates=[args.generation,os.environ.get('GENOS_GENERATION')]
    if bound.exists():candidates.append(json.loads(bound.read_text()).get('generation'))
    for value in candidates:
        if value:
            g=Path(value).resolve()
            if out==g or g in out.parents or out in g.parents:log('refused',error='Output overlaps generation');return 2
    os.umask(0o077);out.mkdir(parents=True,mode=0o700);audit=Audit(args,out)
    try:
        resource.setrlimit(resource.RLIMIT_AS,(min(args.max_rss_mib*2,2048)*1024**2,)*2)
        audit.load();audit.guard();audit.scan();code=1 if audit.counts['BROKEN'] else 0
    except (Exception,KeyboardInterrupt) as e:
        audit.summary.update(status='INCOMPLETE',error_type=type(e).__name__,error=str(e));log('failed',error_type=type(e).__name__,error=str(e));code=130 if isinstance(e,KeyboardInterrupt) else 2
    finally:
        audit.summary.update(exit_code=locals().get('code',2),files=audit.pins)
        write_json(out/'summary.json',audit.summary)
        for name in ('sd','nd'):
            if hasattr(audit,name):getattr(audit,name).close()
    log('finished',status=audit.summary['status'],exit_code=code,report=str(out/'index.html'));return code
if __name__=='__main__':sys.exit(main())
