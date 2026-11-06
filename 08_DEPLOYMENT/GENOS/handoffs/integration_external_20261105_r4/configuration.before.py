"""Operator-side settings, never user request fields. Secrets stay in environment."""
import os,json,sqlite3
from contextlib import contextmanager
from contextvars import ContextVar

_AUTHORING = ContextVar("ontology_authoring", default=None)
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
        from ..oracle_dp import enabled
        if enabled():raise ContractError('DP=oracle requires an Oracle ontology database; SQLite fallback is forbidden')
        if os.environ.get('GENOS_BACKEND') or cfg.get('environment')!='local':raise ContractError('SQLite ontology is local-only')
        path=Path(db['path']).resolve()
        # Never create a missing database from the serving reader.
        def connect():return sqlite3.connect('file:'+str(path)+'?mode=rw',uri=True,timeout=10)
        return _guarded_repository(Repository(connect),cfg)
    if kind!='oracle':raise ContractError('unsupported ontology database')
    import oracledb
    def connect():
        conn=oracledb.connect(dsn=os.environ[db['dsn_env']],user=os.environ[db['user_env']],password=os.environ[db['password_env']])
        conn.call_timeout=15000
        return conn
    return _guarded_repository(Repository(connect,dialect='oracle',owner=db.get('owner','SIDDA')),cfg)


def _guarded_repository(repo,cfg):
    from .wiki_contracts import scope_key
    repo.workspace_scopes=frozenset(scope_key(s) for s in cfg.get('workspace_runtime_scopes',[]))
    if cfg.get('domain_profile'):
        def verify(refs):
            port=glossary_binding(cfg)
            try:
                for ref in refs:
                    if ref!=port.restore(ref['source'],ref['node_id']):raise ContractError('published glossary snapshot changed')
            finally:port.reader.close()
        repo.glossary_validator=verify
    return repo

def source_reader(config,allowed_documents):
    allowed=frozenset(allowed_documents);src=config['source'];kind=src['kind']
    if kind=='sqlite-local':
        from ..oracle_dp import enabled
        if enabled():raise ContractError('DP=oracle requires Oracle ontology sources; SQLite fallback is forbidden')
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

def _ports(actor):
    bound = _AUTHORING.get()
    if bound is None:
        return {}
    if bound['actor'] != actor or bound['config'] != settings():
        raise ContractError('authoring context identity or configuration changed')
    return bound


@contextmanager
def authoring_context(*, actor, workflow, glossary_factory, config, runtime_probe=None):
    """Trusted host ports for one authenticated render; never browser arguments.

    The host owns its database connections. Each glossary factory call returns
    a fresh binding whose reader is closed by its consumer. No global caching.
    """
    from copy import deepcopy
    if config != settings() or actor not in config.get('operators', {}) or workflow.actor != actor:
        raise ContractError('authoring context identity or configuration mismatch')
    grant = config['operators'][actor]
    if not grant.get('document_ids') or not callable(glossary_factory):
        raise ContractError('authoring document scope and glossary factory required')
    selected = config.get('domain_profile')
    workspace = config.get('workspace') or selected
    if not selected or not workspace or any(workspace.get(k) != selected.get(k) for k in ('namespace','source_snapshot','acl_ref')):
        raise ContractError('authoring workspace and domain scope mismatch')
    if any(not selected.get(k) for k in ('namespace','source_snapshot','acl_ref')):
        raise ContractError('authoring namespace snapshot ACL required')
    token = _AUTHORING.set({'actor':actor, 'config':deepcopy(config), 'workflow':workflow,
        'glossary_factory':glossary_factory, 'runtime_probe':runtime_probe})
    try:
        yield
    finally:
        _AUTHORING.reset(token)


def connection_status(*, actor):
    """Report a checked reader separately from the operator's writer settings."""
    cfg = settings()
    if actor not in cfg.get('operators', {}):
        raise ContractError('operator is not authorized for ontology review')
    ports = _ports(actor)
    probe = ports.get('runtime_probe')
    if probe is None:
        return {'status':'UNVERIFIED', 'message':'관리 저장소 설정됨 · 현재 RAG 읽기 연결은 확인 전입니다.'}
    result = probe()
    if not isinstance(result, dict) or result.get('status') not in ('OFF','NO_SCOPE','EMPTY','READY'):
        raise ContractError('runtime readiness result invalid')
    messages = {'OFF':'현재 RAG의 온톨로지 사용이 꺼져 있습니다.',
        'NO_SCOPE':'현재 RAG에 이 작업공간의 읽기 범위가 등록되지 않았습니다.',
        'EMPTY':'현재 RAG 읽기 범위에 사용할 수 있는 게시본이 없습니다.',
        'READY':'현재 RAG의 게시본 읽기·원문 대조를 확인했습니다.'}
    return {'status':result['status'], 'message':messages[result['status']]}


def workflow(*,actor):
    bound = _ports(actor)
    if bound:
        return bound['workflow']
    from .workflow import Workflow
    cfg=settings()
    # Actor is supplied by Dataiku authentication or deployment-managed local identity,
    # never a textbox or an uploaded JSON field.
    users=cfg.get('operators',{})
    if actor not in users:raise ContractError('operator is not authorized for ontology review')
    documents=users[actor]['document_ids']
    return _make_workflow(actor,cfg,repository(cfg),source_reader(cfg,documents))


def _make_workflow(actor,cfg,repo,reader):
    from .workflow import Workflow
    store_cfg=cfg['work_store']
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
            from ..legal_agent.wire_schema import project_request
            request,projection=project_request(request)
            request_key=store.put({'at':now(),'request':request,'schema_projection':projection,'status':'SENT_ONCE'})
            try:raw=request_json(target,'/chat/completions',request)
            except Exception as exc:
                store.put({'request_key':request_key,'status':'UNKNOWN','error_type':type(exc).__name__})
                raise
            key=store.put({'request_key':request_key,'response':raw,'status':'RESPONSE_RECEIVED'})
            return _structured_genos_value(raw),{'store_hash':key,'model':model,'schema_projection':projection}
    return Workflow(repo,store,actor=actor,source_reader=reader,generate=generate)


def glossary_binding(config):
    """Explicit selected snapshot only; never discover the newest dictionary."""
    bound = _AUTHORING.get()
    if bound:
        checked = _ports(bound['actor'])
        if config != checked['config']:
            raise ContractError('glossary authoring configuration mismatch')
        port = checked['glossary_factory']()
        if port.binding['snapshot'] != config['domain_profile']['source_snapshot']:
            port.reader.close()
            raise ContractError('glossary authoring snapshot mismatch')
        return port
    from ..full_glossary import Glossary
    from ..full_glossary_connections import ConnectionReader
    from .glossary_binding import GlossaryBinding
    cfg=config['domain_profile']['glossary']
    if cfg['kind']!='sqlite-local' or config.get('environment')!='local':
        raise ContractError('inject the authenticated Oracle glossary port for remote authoring')
    reader=Glossary(cfg['bundle'],cfg['dictionary'],cfg['cache'],manifest_sha256=cfg['manifest_sha256'],
                    connection_factory=ConnectionReader)
    return GlossaryBinding(reader,snapshot=config['domain_profile']['source_snapshot'])


def domain_workflow(*,actor,ports=None):
    from .domain_workflow import DomainWorkflow
    from .profile import digest
    from pathlib import Path
    cfg=settings();base=(ports or {}).get('workflow') or workflow(actor=actor);selected=cfg['domain_profile']
    if actor not in cfg.get('operators',{}) or base.actor!=actor:raise ContractError('authoring port actor mismatch')
    binding=digest({name:__import__('hashlib').sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                    for name in ('domain_workflow.py','observations.py','accumulation.py','glossary_binding.py','authoring_model.py')})
    generate=None
    if cfg.get('model',{}).get('kind')=='genos':
        from .authoring_model import generate as generate_once
        def generate(prompt,context,schema):
            return generate_once(base.store,prompt,context,schema)
    result=DomainWorkflow(base.repo,base.store,actor=actor,source_reader=base.source_reader,generate=generate,
        namespace=selected['namespace'],source_snapshot=selected['source_snapshot'],acl_ref=selected['acl_ref'],
        document_ids=cfg['operators'][actor]['document_ids'],glossary=(ports or {}).get('glossary') or glossary_binding(cfg),producer_binding=binding)
    result.can_publish_workspace=cfg['operators'][actor].get('workspace_publish') is True
    return result


def workspace_workflow(*,actor,ports=None):
    """No profile/glossary is opened until the user selects compilation."""
    from .wiki_workspace import Workspace
    from ..contracts import digest
    cfg=settings();base=(ports or {}).get('workflow') or workflow(actor=actor)
    if actor not in cfg.get('operators',{}) or base.actor!=actor:raise ContractError('workspace operator mismatch')
    selected=cfg.get('workspace') or cfg.get('domain_profile')
    if not selected:raise ContractError('operator-managed workspace namespace/snapshot/ACL required')
    names=('wiki_contracts.py','wiki_workspace.py','wiki_projection.py','wiki_index.py','wiki_repository.py','authoring_model.py')
    binding=digest({name:__import__('hashlib').sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in names})
    generate=None
    if cfg.get('model',{}).get('kind')=='genos':
        from .wiki_transport import generate as once
        def generate(prompt,context,schema):return once(base.store,actor,prompt,context,schema)
    return Workspace(base.repo,base.store,actor=actor,source_reader=base.source_reader,generate=generate,
        namespace=selected['namespace'],source_snapshot=selected['source_snapshot'],acl_ref=selected['acl_ref'],
        document_ids=cfg['operators'][actor]['document_ids'],producer_binding=binding,
        can_publish=cfg['operators'][actor].get('workspace_publish') is True)
