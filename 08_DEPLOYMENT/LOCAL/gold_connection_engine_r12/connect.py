"""MAIN120 Gold data port with optional physical mapping. Use a dedicated process."""
from pathlib import Path
from contextlib import contextmanager
import argparse,hashlib,json,sys,os

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def load_mapping(path,*,owner=None,expected_sha256=None):
 import importlib.util
 spec=importlib.util.spec_from_file_location('_gold_connection_physical_mapping',HERE/'physical_mapping.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module.GoldMapping.load(path,owner=owner,expected_sha256=expected_sha256)

def active_mapping(path=None):
 """Resolve the explicitly activated local physical schema; never guess names."""
 pointer=Path(path) if path is not None else HERE/'ACTIVE_MAPPING.json'
 if not pointer.exists():return None,None
 value=read(pointer)
 if set(value)!={'schema_version','mapping_file','sha256','migration_receipt'} or value['schema_version']!='gold-active-physical-map-v1':
  raise ValueError('Active Gold mapping pointer shape')
 target=(pointer.parent/value['mapping_file']).resolve()
 if target.parent!=pointer.parent.resolve() or not target.is_file():raise ValueError('Active Gold mapping path')
 if sha(target)!=value['sha256']:raise ValueError('Active Gold mapping hash changed')
 return target,value['sha256']

def load_runtime():
 binding=read(HERE/'binding.json')
 for path,expected in binding['files'].items():
  if sha(ROOT/path)!=expected:raise RuntimeError('Gold connector binding changed: '+path)
 code=ROOT/binding['engine_root']
 for path,expected in binding['engine_files'].items():
  if sha(code/path)!=expected:raise RuntimeError('MAIN120 engine binding changed: '+path)
 if 'semantic_runtime' in sys.modules:raise RuntimeError('Use a dedicated fresh process for this connector')
 os.environ.setdefault('PYTHONDONTWRITEBYTECODE','1');sys.dont_write_bytecode=True
 sys.path.insert(0,str(ROOT/binding['adapter_root']))
 import engine_runtime
 return engine_runtime,binding

def open_mapped_engine(runtime,connection,cfg,*,documents,release_id,channel,seconds,max_calls):
 """The same fixed engine entry with the physical mapping in the request pin."""
 import time
 config=runtime.Overlay(cfg);transport=runtime.TracedTransport(connection,config)
 class GoldSQL(runtime.QuerySQL):
  def query(self,statement,binds=(),*,limit=100):
   return runtime.SQL.query(self,runtime.rewrite_reads(statement,config),binds,limit=limit)
 sql=GoldSQL(transport,binding=runtime.digest({'owner':cfg.owner,'mode':'gold-engine-mapped-v1',
   'physical_mapping':cfg.target_sha256}),deadline=time.monotonic()+seconds,max_calls=max_calls)
 sql.gold_config=config
 selected=runtime.select_release(sql,release_id=release_id,channel=channel);manifest=selected['manifest']
 parent=runtime.read_release(sql,manifest['extension']['base_query_id'])
 config.bind(selected['release_id'],manifest,parent)
 snapshot=runtime.Snapshot.open(sql,manifest['source_release_id'])
 if snapshot.manifest!=manifest['source_manifest'] or snapshot.dataset_version!=manifest['dataset_version']:
  raise runtime.GoldError('ENGINE_SOURCE_BINDING')
 allowed=frozenset(documents)
 if not allowed or not allowed<=set(manifest['documents']):raise runtime.GoldError('ENGINE_SCOPE')
 return runtime._request(sql,selected['release_id'],selected['revision'],snapshot,manifest,allowed),transport

@contextmanager
def open_store(*,config=None,mapping=None,mapping_sha256=None,owner=None,credentials=None,documents=None,release_id=None,channel=None,seconds=1800,max_calls=10000):
 """Yield the unchanged engine's Oracle Store; scope can only be narrowed.

 Parameters are trusted host configuration, not an end-user authorization.
 The caller must supply its authenticated document scope when serving users.
 """
 runtime,binding=load_runtime()
 import oracledb
 oracledb.defaults.fetch_lobs=False
 if config and mapping:raise ValueError('Choose config or mapping')
 if (owner or mapping_sha256) and not mapping:raise ValueError('owner/mapping_sha256 requires mapping')
 if not config and not mapping:mapping,mapping_sha256=active_mapping()
 cfg=load_mapping(mapping,owner=owner,expected_sha256=mapping_sha256) if mapping else runtime.GoldConfig.load(config or HERE/'config_b03.json',ROOT)
 credential_path=Path(credentials).expanduser() if credentials else Path.home()/'.local/state/8-agent/gold-r12-1208/readonly-connection.json'
 if credential_path.stat().st_mode & 0o077:raise RuntimeError('Credentials must be owner-readable only')
 if release_id and channel:raise ValueError('Choose release_id or channel')
 release_id=release_id or (None if channel else binding['query_release_id'])
 allowed=runtime.docs() if documents is None else list(documents)
 if not allowed or not set(allowed)<=set(runtime.docs()):raise ValueError('Document scope outside verified Gold corpus')
 runtime.guard();restore=runtime.install_vector_port()
 try:
  with oracledb.connect(**read(credential_path)) as connection:
   connection.call_timeout=60000
   checked=cfg.preflight(connection) if mapping else None
   if mapping:
    request,transport=open_mapped_engine(runtime,connection,cfg,documents=allowed,release_id=release_id,channel=channel,seconds=seconds,max_calls=max_calls)
   else:
    request,transport=runtime.open_engine(connection,documents=allowed,release_id=release_id,channel=channel,seconds=seconds,max_calls=max_calls,gold_config=cfg)
   store=runtime.Store(request)
   restore_ontology=None
   try:
    if mapping:
     from semantic_runtime.ontology_work import runtime as ontology_runtime
     from semantic_runtime.legal_agent.errors import ContractError
     from types import SimpleNamespace
     repository=cfg.request_ontology_repository(request)
     def verify_glossary(refs):
      port=cfg.glossary_binding(request)
      try:
       for ref in refs:
        if ref!=port.restore(ref['source'],ref['node_id']):raise ContractError('published glossary snapshot changed')
      finally:port.reader.close()
     repository.glossary_validator=verify_glossary
     old_repository=ontology_runtime.repository
     ontology_runtime.repository=lambda:repository
     restore_ontology=lambda:setattr(ontology_runtime,'repository',old_repository)
     store.gold_ports=SimpleNamespace(mapping=cfg,preflight=checked,ontology=repository,
       source_reader=cfg.source_reader(store,request),glossary_binding=lambda:cfg.glossary_binding(request))
    yield store,request,transport
   finally:
    if restore_ontology:restore_ontology()
    store.close()
 finally:restore()

def main():
 p=argparse.ArgumentParser(description='R12 Gold connector for fixed MAIN120')
 p.add_argument('--config');p.add_argument('--mapping',help='Complete physical table/column mapping JSON')
 p.add_argument('--mapping-sha256');p.add_argument('--owner',help='Explicit owner override for a mapping')
 p.add_argument('--credentials');p.add_argument('--documents',help='JSON list of authorized document IDs')
 group=p.add_mutually_exclusive_group();group.add_argument('--release-id');group.add_argument('--channel')
 sub=p.add_subparsers(dest='action',required=True)
 sub.add_parser('health')
 s=sub.add_parser('source');s.add_argument('document_id');s.add_argument('block_id')
 t=sub.add_parser('terms');t.add_argument('text')
 args=p.parse_args()
 with open_store(config=args.config,mapping=args.mapping,mapping_sha256=args.mapping_sha256,owner=args.owner,credentials=args.credentials,documents=read(args.documents) if args.documents else None,release_id=args.release_id,channel=args.channel) as (store,request,transport):
  if args.action=='health':
   store.selection.require_latest();value={'data_port_ready':True,'engine':'fixed MAIN120','query_release_id':request.release_id,'documents':len(request.sources.allowed),'inference_status':read(HERE/'binding.json')['inference_status'],'quality_certified':False}
   if hasattr(store,'gold_ports'):value['physical_mapping']=store.gold_ports.preflight
  elif args.action=='source':value=store.source(args.document_id,args.block_id)
  else:
   from engine_glossary import Glossary
   glossary=Glossary(request,{})
   try:value=glossary.lookup(args.text,limit=10)
   finally:glossary.close()
  print(json.dumps(value,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
