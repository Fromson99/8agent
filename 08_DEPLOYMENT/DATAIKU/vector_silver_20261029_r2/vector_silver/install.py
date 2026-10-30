"""Extend the existing Flow; installation never runs SQL or embedding calls."""
import hashlib
import json

from semantic_runtime.initial_vector import endpoint, profile

RECIPE='LEGAL_04_VECTOR_SILVER_R3'
RESULT='LEGAL_VECTOR_SILVER_RESULT_R3'
RESULT_PATH='/LEGAL_RAG/vector_silver_20261029_r2/results'

def install(project,bootstrap,*,landing_id='ehA8dpVm',load_id='',model='',revision='',dimensions=0,receipt_path=''):
    folders=project.list_managed_folders()
    def named(name,optional=False):
        found=[r['id'] for r in folders if r['name']==name]
        if not found and optional:return None
        if len(found)!=1:raise ValueError('FLOW_FOLDER_REQUIRED_OR_AMBIGUOUS: '+name)
        return found[0]
    load_id=load_id or named('LEGAL_LGL_LOAD_RESULT_R1')
    load=project.get_managed_folder(load_id)
    if load.get_settings().type!='S3':raise ValueError('FLOW_LOAD_RESULT_NOT_S3')
    recipes={r['name'] for r in project.list_recipes()}
    if 'LEGAL_03_LOAD_SILVER_R1' not in recipes or load_id not in project.get_recipe('LEGAL_03_LOAD_SILVER_R1').get_settings().get_flat_output_refs():
        raise ValueError('FLOW_03_OUTPUT_REQUIRED: load folder must be the existing 03 output')
    source=project.get_managed_folder(landing_id).get_settings()
    params=source.get_raw_params()
    if source.type!='S3':raise ValueError('FLOW_LANDING_NOT_S3')
    known=named(RESULT,optional=True)
    legacy=named('LEGAL_VECTOR_SILVER_RESULT_R2',optional=True) or named('LEGAL_VECTOR_RESULT_R1',optional=True)
    if known:
        folder=project.get_managed_folder(known)
        settings=folder.get_settings()
        current=settings.get_raw_params()
        if settings.type!='S3' or any(current.get(k)!=v for k,v in
                {'connection':params['connection'],'bucket':params.get('bucket'),'path':RESULT_PATH}.items()):
            raise ValueError('FLOW_EXISTING_FOLDER_CONFLICT')
    elif RECIPE in recipes:
        raise ValueError('FLOW_RECIPE_WITHOUT_EXPECTED_RESULT_FOLDER')
    variables=project.get_variables()
    standard=variables.setdefault('standard',{})
    if model or revision or dimensions:
        import dataiku
        env=dataiku.get_custom_variables()
        config=profile({'schema_version':'legal-vector-profile-v1','model':model,'revision':revision,
                        'dimensions':dimensions,'endpoint_sha256':hashlib.sha256(endpoint(env).encode()).hexdigest(),
                        'chunk_chars':800,'overlap_chars':100,'normalization':'l2','metric':'COSINE'})
        prior=standard.get('LEGAL_VECTOR_PROFILE')
        if isinstance(prior,str):prior=json.loads(prior)
        if prior not in (None,config):raise ValueError('FLOW_PROFILE_CONFLICT: preserve prior work; use separate reviewed profile change')
        standard['LEGAL_VECTOR_PROFILE']=config
    if receipt_path:
        standard['LEGAL_VECTOR_LOAD_RECEIPT']=receipt_path.lstrip('/')
    if not known:
        folder=project.create_managed_folder(RESULT,folder_type='S3',connection_name=params['connection'])
        settings=folder.get_settings()
        current=settings.get_raw_params()
        current['path']=RESULT_PATH
        if 'bucket' in params:current['bucket']=params['bucket']
        settings.save()
    cfg={'landing':landing_id,'load':load_id,'output':folder.id,'legacy':legacy}
    inputs=[landing_id,load_id]+([legacy] if legacy else [])
    code=bootstrap+'\nfrom vector_silver.runtime import run\nrun('+repr(cfg)+', action="build")\n'
    if RECIPE in recipes:
        settings=project.get_recipe(RECIPE).get_settings()
        if (settings.get_code()!=code or set(settings.get_flat_input_refs())!=set(inputs)
                or set(settings.get_flat_output_refs())!={folder.id}):
            raise ValueError('FLOW_EXISTING_RECIPE_CONFLICT: existing code preserved')
    else:
        builder=project.new_recipe('python',RECIPE)
        for item in inputs:builder.with_input(item)
        recipe=builder.with_output(folder.id,append=True).with_script(code).create()
        settings=recipe.get_settings()
        settings.set_code_env(inherit=True)
        settings.save()
    if variables!=project.get_variables():project.set_variables(variables)
    print('FLOW_INSTALLED',RECIPE,'; 03 completion -> 04 vector -> result folder. No DB/model execution.')
    if 'LEGAL_VECTOR_PROFILE' not in standard:
        print('임베딩 모델명·불변 버전·차원을 확인한 뒤 설치 셀의 EMBED_*를 채워 다시 실행하세요.')
    if legacy:print('이전 R1 레시피와 동시 실행하지 마세요. 같은 작업 상태·예산은 읽어서 이어갑니다.')
    return cfg
