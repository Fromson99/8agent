from pathlib import Path
import shutil,json,hashlib,sys
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_1308/optimized';S=C/'snapshot'
old=Path('08_DEPLOYMENT/DATAIKU/gold_fresh_1_jdbc_fast_20261103_r6/package');new=Path('08_DEPLOYMENT/DATAIKU/gold_fresh_1_jdbc_seek_20261103_r7/package');P=S/new
shutil.copytree(S/old,P,ignore=shutil.ignore_patterns('__pycache__'))
p=P/'reduced_export.py';s=p.read_text();s=s.replace('def asset_rows(path, relative, *, excluded_tables=()):','def asset_rows(path, relative, *, excluded_tables=(), resume=None):').replace('yield from _asset_rows(db, relative, excluded_tables=excluded_tables)','yield from _asset_rows(db, relative, excluded_tables=excluded_tables, resume=resume)')
s=s.replace('def _asset_rows(db, relative, *, excluded_tables=()):','''class ResumeRow(dict):
    def __init__(self,row,cursor):super().__init__(row);self.producer_cursor=cursor


def _asset_rows(db, relative, *, excluded_tables=(), resume=None):
    stages={'table':0,'stats':1,'length':2,'content':3,'posting':4}
    def position(table,section):return (0 if section=='table' else 1,table,stages[section])
    def state(table,section):
        if resume is None:return True,None
        target=position(table,section);saved=position(resume['table'],resume['section'])
        return target>=saved,resume['after'] if target==saved else None
    def wrap(row,table,section,after):
        return ResumeRow(row,{'phase':'asset','table':table,'section':section,'after':after})''')
s=s.replace("        columns = [r[1]", "        active,after=state(table,'table')\n        if not active:continue\n        columns = [r[1]")
s=s.replace("rows = db.execute('SELECT '+','.join(_name(c) for c in columns)+' FROM '+_name(table))\n        for ordinal, row in enumerate(rows):", "offset=0 if after is None else after+1\n        rows = db.execute('SELECT '+','.join(_name(c) for c in columns)+' FROM '+_name(table)+' LIMIT -1 OFFSET ?', (offset,))\n        for ordinal, row in enumerate(rows,start=offset):")
s=s.replace('yield record(_kind(relative, table), value, key=[ordinal, value], **_lookups(value))',"yield wrap(record(_kind(relative, table), value, key=[ordinal, value], **_lookups(value)),table,'table',ordinal)")
s=s.replace('    for table in sorted(virtual):\n',"    for table in sorted(virtual):\n        if not state(table,'posting')[0]:continue\n")
a=s.index("        count = db.execute(");b=s.index("        if table=='words'",a);block=s[a:b]
# Only build global counts while those sections still need output.
block=block.replace("        count = db.execute", "        count = db.execute",1)
block=block.replace("        yield record(_kind(relative,table+'_stats'),{'documents':count,'tokens':tokens},key='stats',lookup_id='stats')", "        if state(table,'stats')[0] and state(table,'stats')[1] is None:\n            yield wrap(record(_kind(relative,table+'_stats'),{'documents':count,'tokens':tokens},key='stats',lookup_id='stats'),table,'stats',0)")
block=block.replace("        lengths = db.execute", "        after=state(table,'length')[1]\n        lengths = db.execute")
block=block.replace("'GROUP BY f.rowid", "('WHERE f.rowid>'+str(int(after))+' ' if after is not None else '')+'GROUP BY f.rowid")
block=block.replace("yield record(_kind(relative,table+'_length'),value,key=row['rowid'],lookup_id=str(row['logical_id']),\n                         document_id=row['document_id'],owner_id=row['source_id'])", "yield wrap(record(_kind(relative,table+'_length'),value,key=row['rowid'],lookup_id=str(row['logical_id']),\n                         document_id=row['document_id'],owner_id=row['source_id']),table,'length',row['rowid'])")
s=s[:a]+"        if state(table,'length')[0]:\n"+''.join('    '+line+'\n' for line in block.splitlines())+s[b:]
s=s.replace("        if table=='words' and any", "        if state(table,'content')[0] and table=='words' and any")
s=s.replace("            for row in db.execute('SELECT rowid AS fts_row_id,source,node_id FROM label ORDER BY rowid'):\n                yield record(_kind(relative,table+'_content'),dict(row),key=row['fts_row_id'],lookup_id=str(row['fts_row_id']))", "            after=state(table,'content')[1]\n            for row in db.execute('SELECT rowid AS fts_row_id,source,node_id FROM label WHERE rowid>? ORDER BY rowid',(after or 0,)):\n                yield wrap(record(_kind(relative,table+'_content'),dict(row),key=row['fts_row_id'],lookup_id=str(row['fts_row_id'])),table,'content',row['fts_row_id'])")
s=s.replace("        stream = db.execute('SELECT doc,col,term,offset FROM temp.query_export_vocab '\n                            'ORDER BY doc,col,term,offset')", "        after=state(table,'posting')[1]\n        stream = db.execute('SELECT doc,col,term,offset FROM temp.query_export_vocab '+\n            ('WHERE (doc,col,term)>(?,?,?) ' if after is not None else '')+\n            'ORDER BY doc,col,term,offset',tuple(after) if after is not None else ())")
s=s.replace("            return record(_kind(relative, table+'_posting'), value, key=[doc,column,token],\n                          document_id=did,lookup_id=token, owner_id=str(logical_id), target_id=column)", "            return wrap(record(_kind(relative, table+'_posting'), value, key=[doc,column,token],\n                          document_id=did,lookup_id=token, owner_id=str(logical_id), target_id=column),table,'posting',[doc,column,token])")
p.write_text(s)
p=P/'fast_export.py';s=p.read_text();i=s.index('def projected_rows(');s=s[:i]+'''def projected_rows(path,relative,source,*,mode,excluded_tables=(),resume=None):
    from itertools import islice
    from reduced_export import asset_rows,ResumeRow
    phase=resume.get('phase') if resume else None
    if phase not in (None,'asset','source','native'):raise ValueError('QUERY_PRODUCER_CURSOR_PHASE')
    if phase!='native':
        if relative=='store.sqlite':
            if phase not in (None,'source'):raise ValueError('QUERY_PRODUCER_CURSOR_ASSET')
            offset=resume['offset'] if resume else 0
            for n,row in enumerate(islice(source_records(path,source),offset,None),start=offset+1):
                yield ResumeRow(row,{'phase':'source','offset':n})
        else:
            if phase not in (None,'asset'):raise ValueError('QUERY_PRODUCER_CURSOR_SOURCE')
            yield from asset_rows(path,relative,excluded_tables=excluded_tables,resume=resume)
    from lawrag.pipeline.oracle_query_navigation_publish import records
    offset=resume['offset'] if phase=='native' else 0
    for n,row in enumerate(islice(records(path,relative,source),offset,None),start=offset+1):
        yield ResumeRow(row,{'phase':'native','offset':n})
''';p.write_text(s)
p=P/'fast_loader.py';s=p.read_text();s=s.replace("done = current_state.get('rows',0);current=0", "done = current_state.get('rows',0)\n        resume=current_state.get('producer_cursor')\n        current=done if resume else 0")
s=s.replace("source,mode=mode,**kwargs)","source,mode=mode,resume=resume,**kwargs)")
s=s.replace("next_progress={'rows':through},section='query'", "next_progress={'rows':through,'producer_cursor':batch[-1].producer_cursor},section='query'")
s=s.replace('"""R6 user-requested insert/commit/checkpoint path; no routine readback checks."""','"""R7 exact producer-cursor resume; existing insert acknowledgement contract."""');p.write_text(s)
# Accept an existing R6 checkpoint; keep every prior accepted code binding.
p=P/'RESUME_PARENTS.json';d=json.loads(p.read_text());sha=hashlib.sha256(json.dumps(json.loads((S/old/'CODE_MANIFEST.json').read_text()),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
for mode in ('full','reduced'):d['parents'].append({'mode':mode,'code_binding':sha,'source':'gold_fresh_1_jdbc_fast_20261103_r6'})
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
(P/'PLACEMENT_NOTE.txt').write_text('R7: 기존 R6 작업 상태를 유지하는 생산자 커서 재개. 새 DB/DDL 없음. 완료 배치 다음 행부터 재개. 기존 상태의 최초 재개는 호환 경로를 사용한다. source/native 단계는 기존 순회 후 건너뛰기를 유지한다. 현장 실행 미검증.\n')
# Package provenance; byte identities are refreshed after any further edits.
def seal():
 files={str(p.relative_to(P)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(P.rglob('*')) if p.is_file() and p.name!='CODE_MANIFEST.json'}
 (P/'CODE_MANIFEST.json').write_text(json.dumps(files,indent=2)+'\n')
seal()
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
for p in sorted(P.rglob('*')):
 if p.is_file():ac.register_file(C,str(p.relative_to(S)),upstream_state='absent')
print('R7 registered',len(list(P.rglob('*.py'))))
