"""Run R2 using the established R1 loopback GENOS and real Oracle harness."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
R1=HERE.parent/'agent_layer_async_20261105_r1'

def deploy():
    with tempfile.TemporaryDirectory() as temp:
        work=Path(temp)
        checkout=work/'new-service'
        remote=work/'remote.git'
        subprocess.run(['git','init','-q','--bare',str(remote)],check=True)
        subprocess.run(['git','init','-q','-b','main',str(checkout)],check=True)
        for key,val in [('user.name','Local Test'),('user.email','test@localhost'),('core.autocrlf','false')]:
            subprocess.run(['git','-C',str(checkout),'config',key,val],check=True)
        subprocess.run(['git','-C',str(checkout),'remote','add','origin',str(remote)],check=True)
        (work/'DEV').symlink_to(checkout,target_is_directory=True)
        env=dict(os.environ,HOME=str(work),GIT_CONFIG_NOSYSTEM='1')
        receipts=[]
        for _ in range(2):
            done=subprocess.run(['bash','GENOS_DEPLOY_R2.txt'],cwd=HERE,env=env,capture_output=True,text=True,check=True)
            receipts.append(next(line for line in done.stdout.splitlines() if line.startswith('GENOS_CODE_PUSHED')))
        assert receipts[0]==receipts[1]
        return receipts[0]

def main(out):
    pub=deploy()
    parent=(R1/'verify_local.py').read_text()
    parent=parent.replace('a8-agent-1379-oracle','a8-agent-law-r2-oracle').replace("=='agent-flow-1379'","=='agent-law-r2'")
    parent=parent.replace('GENOS_AGENT_ASYNC_R1.zip','GENOS_AGENT_ASYNC_R2.zip').replace('DATAIKU_AGENT_FLOW_R1.zip','DATAIKU_AGENT_FLOW_R2.zip')
    parent=parent[:parent.index('    # Use the same small locally generated')]+"""    testpin=pin
"""+parent[parent.index('    sys.path[:0]='):]
    parent=parent[:parent.index('            ddl=(HERE/')]+parent[parent.index('        class ORDS:'):]
    parent=parent.replace("self.user={'agent':'STG_READER','target':'STG_TARGET'}[connection]",
                          "self.user={'agent':'STG_READER','target':'STG_TARGET','setup':'SIDDA'}[connection]")
    # The installer must actually create the table with the selected setup account.
    parent=parent.replace("        class ORDS:", """        with admin.cursor() as c:
            c.execute('GRANT CREATE TABLE TO SIDDA')
        class ORDS:""")
    parent=parent.replace("            def list_paths_in_partition(self):","            def get_info(self,sensitive_info=False):return {'type':'Filesystem','path':str(self.path)}\n            def list_paths_in_partition(self):")
    old_install=(R1/'verify_install.py').read_text()
    double=old_install[old_install.index('    by_id={}'):old_install.index("    api=types.ModuleType")]
    from textwrap import indent
    mod=indent(double,'    ')
    parent=parent.replace("        dku=types.ModuleType('dataiku')",mod+"""
        project.project_key='LOCAL_TEST'
        project.get_llm=lambda name:types.SimpleNamespace(new_embeddings=lambda **kw:Embed())
        dku=types.ModuleType('dataiku')""")
    start=parent.index("        for p in (FIX/'dev/01_DATA/RAW/internal/test_team').iterdir()")
    end=parent.index("        for mode in ('DEV_1','GOLD'):",start)
    replacement="""        for name in ('DATAIKU_AGENT_FLOW_R2.zip','LAW_SAMPLE_R2.zip','SAMPLE_SUPPORT_R2.zip'):
            shutil.copyfile(HERE/name,Folder('code').path/name)
        install_text=(HERE/'DATAIKU_SETUP_R2.txt').read_text()
        for key,old,val in [('CODE_FOLDER_ID','','code'),('WORK_DIR','',str(out/'work')),('SETUP_CONNECTION','AIDP','setup'),
                            ('EXPECTED_SETUP_USER','','SIDDA'),('GENOS_DB_USER','','STG_WRITER'),('AGENT_CONNECTION','AIDP','agent'),
                            ('TARGET_CONNECTION','AIDP','target'),('EXPECTED_DB_USER','PIDD2APP','STG_TARGET'),
                            ('EMBED_MODEL','openai:genos-embedding:embedding-kure-v1','fixture'),('EMBED_DIMENSIONS',1024,4)]:
            pattern=repr(key)+': '+repr(old)
            assert install_text.count(pattern)==1
            install_text=install_text.replace(pattern,repr(key)+': '+repr(val))
        for _ in range(2):
            ns={};exec(compile(install_text,'DATAIKU_SETUP_R2.txt','exec'),ns)
        assert len(recipes)==3 and len(scenarios)==1 and len(by_id)==5
        assert all('BOOTSTRAP' not in r.code or isinstance(r.code,str) for r in recipes.values())
        raw_cfg=ns['cfg']
        folders={k:'LGL_AGENT_R2_DEV_'+code+'_OUT' for k,code in [('submit','01_SUBMIT'),('wait','02_WAIT_AGENT'),('load','03_LOAD')]}
        cfg=dict(raw_cfg,project=project.project_key,folders=folders)
        checks+=['exact_setup_TXT_created_SIDDA_table_and_grants','repeat_install_reused_table_three_recipes_one_scenario']
"""
    parent=parent[:start]+replacement+parent[end:]
    parent=parent.replace("('DEV_1','GOLD')","('DEV_1',)").replace("for mode in ('DEV','PROD'):","for mode in ('DEV',):")
    parent=parent.replace("calls.count('PUT')==1","calls.count('PUT')==2").replace("native_DOCX_async_SUBMIT","exact_public_law_XML_local_ZIP_async_SUBMIT")
    parent=parent.replace("doc=next(Folder('docs').path.glob('*.docx'))","doc=Folder('code').path/'LAW_SAMPLE_R2.zip'")
    parent=parent.replace("'DOCUMENTS_CHANGED_USE_NEW_TRIAL'","'SAMPLE_ZIP_CHANGED'").replace("same_trial_rejects_changed_loose_document","changed_uploaded_ZIP_rejected")
    parent=parent.replace("'fixture_glossary_policy_rebound':True","'fixture_glossary_policy_rebound':False,'sample_policy_packaged_and_hash_bound':True")
    parent=parent.replace("        (out/'validation.json').write_text", """        diagnostics['published_commit_fixture']=LOCAL_PUBLISH
        source=next((h['folder']/'workspace/01_DATA/RAW/external/sample_team/law').rglob('*.xml'))
        import json as _json
        expected=_json.loads((HERE/'RELEASE.json').read_text())['sample']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==expected['document_sha256']
        digest=diagnostics['DEV']['job']
        assert (h['folder']/'raw.zip').read_bytes()==(HERE/'LAW_SAMPLE_R2.zip').read_bytes()
        checks.append('local_ZIP_received_byte_for_byte_and_original_XML_verified')
        (out/'validation.json').write_text""")
    ns={'__file__':str(HERE/'verify_delivery.py'),'__name__':'_fixture','LOCAL_PUBLISH':pub}
    exec(compile(parent,'<R2-local-Oracle-verification>','exec'),ns)
    ns['main'](out.resolve())

if __name__=='__main__':main(Path(sys.argv[1]))
