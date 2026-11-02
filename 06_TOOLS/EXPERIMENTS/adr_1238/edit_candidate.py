from common import *
import shutil
S=CAND/'snapshot';T=PORT/'snapshot'/GOLD.relative_to(ROOT)
# Preserve exact already verified Gold fixes, removing only deployment-time exec overlay.
for name in ('ontology_assessment.py','navigation_input.py'):
 shutil.copy2(GOLD/'runtime_patches'/name,S/'02_BACKEND/semantic_runtime/legal_agent'/name)
p=S/'02_BACKEND/semantic_runtime/legal_agent/read_judgment_final.py';s=p.read_text()
old="""        for row in receipt.get('prior_needs', []):
            material_open = True
            result['limitation_items'].append({'id':'L-'+row['id'], 'kind':'READ_JUDGMENT_UNRESOLVED',
                'issue_id':None, 'text':'검토 미완료 필요: '+row.get('text',row.get('reason',''))})
    result['limitations']"""
new="""        # A missing final review cannot silently dispose of either side of a
        # conflict, or turn an unreviewed source opinion into an adopted claim.
        for field, label in (('prior_needs', '검토 미완료 필요: '),
                             ('prior_conflicts', '검토 미완료 판단 충돌: '),
                             ('prior_judgments', '최종 검토 미완료 판단: ')):
            for row in receipt.get(field, []):
                material_open = True
                result['limitation_items'].append({'id':'L-'+row['id'], 'kind':'READ_JUDGMENT_UNRESOLVED',
                    'issue_id':None, 'text':label+row.get('text',row.get('reason',''))})
    result['limitation_items'] = list({r['id']:r for r in result['limitation_items']}.values())
    result['limitations']"""
assert old in s;p.write_text(s.replace(old,new))
p=S/'02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py';s=p.read_text()
s=s.replace("    st=record(inv,data,value,key);why=trigger(st,value)","""    st=state_for(inv,data)
    if st.get('pending'):
        # A persisted pending attempt has no confirmed outcome. It is not a
        # legal/shape rejection and must not authorize tools or finalization.
        failure=st.get('failure',{})
        error=TransportError(failure.get('reason','Unknown prior supervisor outcome'), unknown=True)
        error.code=failure.get('code',error.code);error.http_status=failure.get('http_status',error.http_status)
        raise error
    st=record(inv,data,value,key);why=trigger(st,value)""")
s=s.replace("""            st['pending']=None;st['failure']={'type':type(exc).__name__,'reason':str(exc)}
            stop(inv,st,'SUPERVISOR_UNRESOLVED:'+type(exc).__name__)""","""            st['failure']={'type':type(exc).__name__,'reason':str(exc)}
            if isinstance(exc,TransportError) and exc.unknown:
                st['failure'].update(unknown=True,code=exc.code,http_status=exc.http_status)
                save(inv,st)
                inv.s.repo.event('SUPERVISOR_UNKNOWN_STOP',{'reason':str(exc),'code':exc.code,
                    'originals_preserved':True,'legal_sufficiency_approved':False})
                raise
            st['pending']=None
            stop(inv,st,'SUPERVISOR_UNRESOLVED:'+type(exc).__name__)""")
p.write_text(s)
# Maintained adapter common: bind imports to the verified engine selected by connect.
b=read(GOLD/'binding.json');s=(ROOT/b['adapter_root']/'engine_common.py').read_text()
s=s.replace("R=Path('/home/jin/8-AGENT');", "R=Path(REPOSITORY_ROOT);")
s=s.replace("B=read(D/'baseline.json');C=R/B['release']['code_root'];DATA=R/B['release']['data_path']", "B=ENGINE_BINDING;C=R/B['engine_root'];DATA=R/B['data_path']")
(T/'engine_common.py').write_text('"""Gold adapter helpers using the engine verified by the local connector."""\n'+s)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.register_file(PORT,str(GOLD.relative_to(ROOT)/'engine_common.py'),upstream_state='absent')
p=T/'connect.py';s=p.read_text().replace('MAIN120 Gold data port with optional physical mapping. Use a dedicated process.','Selected MAIN Gold data port with verified physical mapping. Use a dedicated process.')
s=s.replace('PATCH_ROOT=HERE',"ACTIVE_POINTER=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'")
s=s.replace("value=read(ROOT/read(HERE/'binding.json')['engine_root']/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')", "value=read(ROOT/engine_binding()['engine_root']/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')")
a=s.index('def install_runtime_patches');z=s.index('def open_mapped_engine',a)
s=s[:a]+'''def engine_binding():
 """Require the independently qualified local MAIN and its exact serving bytes."""
 binding=read(HERE/'binding.json')
 if binding.get('schema_version')!='selected-main-gold-port-v2':raise RuntimeError('Gold selected MAIN binding required')
 active=read(ACTIVE_POINTER)
 if (active.get('deployment_basis')!='VALIDATED_ADR_PROMOTION' or
     active.get('release_id')!=binding['engine_release_id'] or
     active.get('release_manifest_sha256')!=binding['engine_manifest_sha256']):
  raise RuntimeError('Gold engine differs from selected MAIN; requalify connector binding')
 manifest_path=ROOT/active['manifest_path']
 if sha(manifest_path)!=binding['engine_manifest_sha256']:raise RuntimeError('Selected MAIN manifest changed')
 manifest=read(manifest_path)
 if manifest['code_root']!=binding['engine_root'] or manifest['files']!=binding['engine_files'] or manifest['data_path']!=binding['data_path']:
  raise RuntimeError('Gold engine inventory differs from selected MAIN')
 for path,expected in binding['files'].items():
  if sha(ROOT/path)!=expected:raise RuntimeError('Gold connector binding changed: '+path)
 for path,expected in binding['connector_files'].items():
  if sha(HERE/path)!=expected:raise RuntimeError('Gold maintained connector changed: '+path)
 code=ROOT/binding['engine_root']
 for path,expected in binding['engine_files'].items():
  if sha(code/path)!=expected:raise RuntimeError('Selected MAIN engine binding changed: '+path)
 return binding

def load_runtime():
 import importlib.util
 binding=engine_binding();code=ROOT/binding['engine_root']
 if any(n=='semantic_runtime' or n.startswith('semantic_runtime.') or n in ('engine_common','engine_runtime','gold_connection') for n in sys.modules):
  raise RuntimeError('Use a dedicated fresh process for this connector')
 os.environ.setdefault('PYTHONDONTWRITEBYTECODE','1');sys.dont_write_bytecode=True
 sys.path.insert(0,str(ROOT/binding['adapter_root']))
 spec=importlib.util.spec_from_file_location('engine_common',HERE/'engine_common.py')
 common=importlib.util.module_from_spec(spec)
 common.REPOSITORY_ROOT=ROOT;common.ENGINE_BINDING=binding
 sys.modules['engine_common']=common
 spec.loader.exec_module(common)
 import engine_runtime,semantic_runtime
 if Path(semantic_runtime.__file__).resolve()!=code/'02_BACKEND/semantic_runtime/__init__.py':
  raise RuntimeError('Gold loaded an unselected engine')
 return engine_runtime,binding

''' + s[z:]
s=s.replace("Yield the unchanged engine's Oracle Store", "Yield the selected engine's Oracle Store")
s=s.replace("description='R12 Gold connector for fixed MAIN120'", "description='Gold connector for qualified selected MAIN'")
s=s.replace("'engine':'fixed MAIN120'", "'engine':read(HERE/'binding.json')['engine_release_id']")
p.write_text(s)
print('Candidate product4 and maintained connector2 edited; production unchanged')
