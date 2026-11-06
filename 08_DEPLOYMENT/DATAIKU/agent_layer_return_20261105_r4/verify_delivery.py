"""Exact delivered TXT/ZIP, loopback GENOS API and disposable Oracle integration.

The native worker and SQL are real. Only DSS APIs, HTTPS hosting and embeddings
are fixture adapters. ORDS is forbidden. Reuse the established Oracle harness.
"""
import json
from pathlib import Path
import sys
from textwrap import indent

HERE=Path(__file__).resolve().parent
R1=HERE.parent/'agent_layer_async_20261105_r1'

def substitute(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)

def main(out):
    parent=(R1/'verify_local.py').read_text()
    parent=parent.replace('a8-agent-1379-oracle','a8-agent-return-r4').replace("=='agent-flow-1379'","=='agent-return-r4'")
    parent=parent.replace('GENOS_AGENT_ASYNC_R1.zip','GENOS_AGENT_RETURN_R4.zip').replace('DATAIKU_AGENT_FLOW_R1.zip','DATAIKU_AGENT_FLOW_R4.zip')
    start=parent.index('    # Use the same small locally generated')
    end=parent.index('    sys.path[:0]=',start)
    parent=parent[:start]+'    testpin=pin\n'+parent[end:]
    parent=parent.replace("'STG_READER','STG_WRITER','STG_TARGET'","'PIDD2APP'")
    start=parent.index("            ddl=(HERE/")
    end=parent.index('        class ORDS:',start)
    parent=parent[:start]+"            c.execute('GRANT CREATE ANY TABLE, CREATE ANY INDEX, SELECT ANY TABLE, INSERT ANY TABLE TO PIDD2APP')\n"+parent[end:]
    start=parent.index('            def request(self,method,path,json):')
    end=parent.index("        genos=types.ModuleType",start)
    parent=parent[:start]+"            def request(self,*a,**kw):raise AssertionError('GENOS_MUST_NOT_ACCESS_ORACLE')\n"+parent[end:]
    parent=substitute(parent,"        os.environ.update(ORACLE_ORDS_SCHEMA='stage',ORACLE_ORDS_CLIENT_ID='fixture',ORACLE_ORDS_CLIENT_SECRET='fixture',HF_HUB_OFFLINE='1')", """        for key in list(os.environ):
            if key.startswith('ORACLE_ORDS_'):os.environ.pop(key)
        os.environ['HF_HUB_OFFLINE']='1'""")
    parent=substitute(parent,"self.user={'agent':'STG_READER','target':'STG_TARGET'}[connection]","assert connection=='AIDP';self.user='PIDD2APP'")
    parent=substitute(parent,"                    return frame", """                    if fail_ack[0] and any('INSERT INTO SIDDA.LGL_PIPE_RESULT_A' in s for s in pre_queries):
                        fail_ack[0]=False
                        raise OSError('FIXTURE_COMMITTED_STAGE_ACK_LOST')
                    return frame""")
    parent=substitute(parent,'        class Executor:', '        fail_ack=[False]\n        class Executor:')
    parent=substitute(parent,"[[1.,0.,0.,0.] for _ in self.texts]","[[1.]+[0.]*1023 for _ in self.texts]")
    parent=substitute(parent,'            def list_paths_in_partition(self):',"            def get_info(self,sensitive_info=False):return {'type':'Filesystem','path':str(self.path)}\n            def list_paths_in_partition(self):")
    old=(R1/'verify_install.py').read_text()
    double=old[old.index('    by_id={}'):old.index("    api=types.ModuleType")]
    parent=substitute(parent,"        dku=types.ModuleType('dataiku')",indent(double,'    ')+"""        project.project_key='LOCAL_TEST'
        project.get_llm=lambda name:types.SimpleNamespace(new_embeddings=lambda **kw:Embed())
        dku=types.ModuleType('dataiku')""")
    start=parent.index("        for p in (FIX/'dev/01_DATA/RAW/internal/test_team').iterdir()")
    end=parent.index("        for mode in ('DEV_1','GOLD'):",start)
    parent=parent[:start]+"""        variables['AGENT_FLOW_WORK_DIR']=str(out/'work')
        for name in ('DATAIKU_AGENT_FLOW_R4.zip','LAW_SAMPLE_R2.zip','SAMPLE_SUPPORT_R2.zip'):
            shutil.copyfile(HERE/name,Folder('code').path/name)
        text=(HERE/'DATAIKU_SETUP_R4.txt').read_text().replace("CODE_FOLDER_ID = ''","CODE_FOLDER_ID = 'code'")
        assert 'GENOS_DB_USER' not in text and 'EXPECTED_SETUP_USER' not in text
        for _ in range(2):
            ns={};exec(compile(text,'DATAIKU_SETUP_R4.txt','exec'),ns)
        assert len(recipes)==3 and len(scenarios)==1 and len(by_id)==5
        cfg=ns['cfg']
        folders=cfg['folders']
        for recipe in recipes.values():compile(recipe.code,recipe.name,'exec')
        assert not next(iter(scenarios.values())).active
        checks+=['exact_notebook_folder_id_only_created_SIDDA_with_AIDP_PIDD2APP',
                 'repeat_install_three_recipes_one_disabled_scenario']
        from stage_wire import Wire
        alias=runtime.wire({'LEGAL_PIPELINE_URL':variables['AGENT_PIPELINE_URL'],'LEGAL_PIPELINE_TOKEN':'fixture'})
        assert alias.url==runtime.wire(variables).url
        try:runtime.wire({'AGENT_PIPELINE_URL':variables['AGENT_PIPELINE_URL'],'LEGAL_PIPELINE_TOKEN':'fixture'})
        except ValueError:pass
        else:raise AssertionError('mixed credential pair accepted')
        assert api.handle({'API_TYPE':'HEALTH'})['oracle_access'] is False
        checks+=['existing_LEGAL_PIPELINE_variable_pair_supported','incomplete_credential_pair_rejected','GENOS_health_no_Oracle_access']
"""+parent[end:]
    parent=parent.replace("('DEV_1','GOLD')","('DEV_1',)").replace("TO STG_TARGET","TO PIDD2APP").replace("for mode in ('DEV','PROD'):","for mode in ('DEV',):")
    parent=parent.replace("calls.count('PUT')==1","calls.count('PUT')==2")
    start=parent.index("        try:runtime.run('wait',cfg)")
    end=parent.index("        # The real DSS load recipe",start)
    parent=parent[:start]+"""        fail_ack[0]=True
        try:runtime.run('wait',cfg)
        except OSError as exc:assert str(exc)=='FIXTURE_COMMITTED_STAGE_ACK_LOST'
        except BaseException:
            h=api.HANDLES[intent['job']]
            shutil.copyfile(h['folder']/'compute.log',out/'worker.log')
            raise
        else:raise AssertionError('ACK loss did not interrupt DSS write')
        query=runtime.layer_query('AIDP')
        assert not agent_stage.ready(query,intent['job'],intent['binding'])
        assert query('SELECT COUNT(*) AS N FROM SIDDA.LGL_PIPE_RESULT_A')[0]['N']>0
        h=api.HANDLES[intent['job']]
        shutil.copyfile(h['folder']/'compute.log',out/'worker.log')
        source=next((h['folder']/'workspace/01_DATA/RAW/external/sample_team/law').rglob('*.xml'))
        expected=json.loads((HERE/'RELEASE.json').read_text())['sample']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==expected['document_sha256']
        assert (h['folder']/'raw.zip').read_bytes()==(HERE/'LAW_SAMPLE_R2.zip').read_bytes()
        assert 'READ' in calls and calls.count('RUN')==1
        # An unconfirmed JDBC ACK is reconciled without a second model/worker job,
        # a new download, or access to the compute endpoint.
        http.shutdown();http.server_close()
        calls_before=list(calls)
        ready=runtime.run('wait',cfg)
        assert runtime.run('wait',cfg)==ready and calls==calls_before
        receipt=agent_stage.ready(query,intent['job'],intent['binding'])
        assert receipt and receipt['sha256']==h['result']['sha256']
        checks+=['exact_public_law_ZIP_async_compute_and_HTTP_result_READ',
                 'duplicate_submit_one_RUN','local_ZIP_byte_identical_and_original_XML_hash',
                 'DSS_AIDP_commit_ACK_loss_invisible_until_READY',
                 'DSS_resume_from_saved_result_without_GENOS_or_duplicate_compute',
                 'SIDDA_READY_readback_and_repeat_wait']
"""+parent[end:]
    parent=parent.replace("query=runtime.layer_query('agent')","query=runtime.layer_query('AIDP')")
    parent=parent.replace("doc=next(Folder('docs').path.glob('*.docx'))","doc=Folder('code').path/'LAW_SAMPLE_R2.zip'")
    parent=parent.replace("'DOCUMENTS_CHANGED_USE_NEW_TRIAL'","'SAMPLE_ZIP_CHANGED'")
    parent=parent.replace('same_trial_rejects_changed_loose_document','changed_uploaded_sample_ZIP_rejected')
    parent=parent.replace("'fixture_glossary_policy_rebound':True","'fixture_glossary_policy_rebound':False,'GENOS_Oracle_access':False,'ORDS_environment':False")
    parent=parent.replace("'dataiku_ords_sdks':'local substitutes'","'dataiku_sdk':'local API fixture','ords_sdk':'forbidden trap, never called'")
    parent=substitute(parent,"        (out/'validation.json').write_text", """        diagnostics['installed_recipe_names']=sorted(recipes)
        diagnostics['oracle_connections']=['AIDP']
        diagnostics['GENOS_env_has_ORDS']=any(k.startswith('ORACLE_ORDS_') for k in os.environ)
        (out/'validation.json').write_text""")
    out.parent.mkdir(parents=True,exist_ok=True)
    (out.parent/(out.name+'-harness.py')).write_text(parent)
    ns={'__file__':str(HERE/'verify_delivery.py'),'__name__':'_fixture'}
    exec(compile(parent,'<R4-local-Oracle-verification>','exec'),ns)
    ns['main'](out.resolve())

if __name__=='__main__':main(Path(sys.argv[1]))
