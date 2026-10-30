"""Operator-side settings, never user request fields. Secrets stay in environment."""
import os,json,sqlite3
from pathlib import Path
from .repository import Repository,ident,value
from .store import LocalFolderStore,DataikuFolderStore
from ..legal_agent.errors import ContractError

def settings():
    path=os.environ.get('GENOS_RAG_ONTOLOGY_CONFIG','').strip()
    if not path:raise ContractError('ontology database settings missing')
    data=json.loads(Path(path).read_text())
    if data.get('version')!='ontology-connection-v1':raise ContractError('ontology connection version')
    return data

def repository(config=None):
    cfg=config or settings();db=cfg['database'];kind=db['kind']
    if kind=='sqlite-local':
        if os.environ.get('GENOS_BACKEND') or cfg.get('environment')!='local':raise ContractError('SQLite ontology is local-only')
        path=Path(db['path']).resolve()
        # Never create a missing database from the serving reader.
        def connect():return sqlite3.connect('file:'+str(path)+'?mode=rw',uri=True,timeout=10)
        return Repository(connect)
    if kind!='oracle':raise ContractError('unsupported ontology database')
    import oracledb
    def connect():
        conn=oracledb.connect(dsn=os.environ[db['dsn_env']],user=os.environ[db['user_env']],password=os.environ[db['password_env']])
        conn.call_timeout=15000
        return conn
    return Repository(connect,dialect='oracle',owner=db.get('owner','SIDDA'))

def source_reader(config,allowed_documents):
    allowed=frozenset(allowed_documents);src=config['source'];kind=src['kind']
    if kind=='sqlite-local':
        if config.get('environment')!='local':raise ContractError('local source reader is forbidden in GENOS')
        def read(anchor):
            if anchor['document_id'] not in allowed:raise ContractError('source outside operator scope')
            with sqlite3.connect('file:'+str(Path(src['path']).resolve())+'?mode=ro',uri=True) as db:
                row=db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(anchor['document_id'],)).fetchone()
                if not row or row[0]!=anchor['version']:raise ContractError('source version changed')
                rows=db.execute('SELECT text FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',(anchor['document_id'],anchor['unit_id'])).fetchmany(4097)
                if not rows or len(rows)>4096:raise ContractError('source extent missing or oversized')
                return '\n'.join(r[0] for r in rows)
        return read
    if kind!='oracle-silver':raise ContractError('unsupported ontology source reader')
    repo=repository(config);owner=ident(src.get('owner','SIDDS'));generation=src['dataset_version']
    def read(anchor):
        if anchor['document_id'] not in allowed:raise ContractError('source outside operator scope')
        with repo.session() as c:
            row=repo.execute(c,f'SELECT SRC_DATA_HASH_VAL FROM {owner}.LGL_DOC_VER_S WHERE DATA_VER_ID=:1 AND DOC_ID=:2',(generation,anchor['document_id'])).fetchone()
            if not row or row[0]!=anchor['version']:raise ContractError('source version changed')
            rows=repo.execute(c,f'SELECT BLK_TXT_CN FROM {owner}.LGL_DOC_BLK_S WHERE DATA_VER_ID=:1 AND DOC_ID=:2 AND UNIT_ID=:3 ORDER BY TO_NUMBER(BLK_ID)',(generation,anchor['document_id'],anchor['unit_id'])).fetchmany(4097)
            if not rows or len(rows)>4096:raise ContractError('source extent missing or oversized')
            text='\n'.join(value(r[0]) for r in rows)
            if len(text)>160000:raise ContractError('source text limit')
            return text
    return read

def workflow(*,actor):
    from .workflow import Workflow
    cfg=settings()
    # Actor is supplied by Dataiku authentication or deployment-managed local identity,
    # never a textbox or an uploaded JSON field.
    users=cfg.get('operators',{})
    if actor not in users:raise ContractError('operator is not authorized for ontology review')
    documents=users[actor]['document_ids'];store_cfg=cfg['work_store']
    if store_cfg['kind']=='dataiku':
        import dataiku
        store=DataikuFolderStore(dataiku.Folder(store_cfg['folder_id']))
    elif store_cfg['kind']=='local' and cfg.get('environment')=='local':store=LocalFolderStore(store_cfg['path'])
    else:raise ContractError('work JSON must use the configured Dataiku managed folder')
    generate=None
    if cfg.get('model',{}).get('kind')=='genos':
        # Runs in Dataiku; model is GENOS compute. Provider temporary receipts are
        # copied into managed-folder JSON and need no persistent GENOS work registry.
        def generate(prompt,context,schema):
            from dataclasses import replace
            from ..genos import from_env,advertised_model,request_json
            from ..provider import _structured_genos_value
            from .schema import now
            target,configured=from_env('llm')
            target=replace(target,max_retries=1)
            model=advertised_model(target,configured)
            request={'model':model,'messages':[{'role':'system','content':prompt},
                {'role':'user','content':json.dumps(context,ensure_ascii=False)}],
                'temperature':0,'stream':False,'chat_template_kwargs':{'enable_thinking':False},
                'response_format':{'type':'json_schema','json_schema':{'name':'ontology_recipe','strict':True,'schema':schema}}}
            request_key=store.put({'at':now(),'request':request,'status':'SENT_ONCE'})
            try:raw=request_json(target,'/chat/completions',request)
            except Exception as exc:
                store.put({'request_key':request_key,'status':'UNKNOWN','error_type':type(exc).__name__})
                raise
            key=store.put({'request_key':request_key,'response':raw,'status':'RESPONSE_RECEIVED'})
            return _structured_genos_value(raw),{'store_hash':key,'model':model}
    return Workflow(repository(cfg),store,actor=actor,source_reader=source_reader(cfg,documents),generate=generate)
