"""One installation cell adds a single Python Flow recipe, not a new project."""
import json

def install(project,bootstrap,landing_id='ehA8dpVm'):
 name='LEGAL_VECTOR_RESULT_R1';recipe_name='LEGAL_04_VECTOR_INITIAL_R1'
 source=project.get_managed_folder(landing_id).get_settings();params=source.get_raw_params()
 if source.type!='S3':raise ValueError('Landing must be the existing Dataiku S3 folder')
 found=[r for r in project.list_managed_folders() if r['name']==name]
 if len(found)>1:raise ValueError('duplicate vector result folders')
 path='/LEGAL_RAG/vector_initial_20261028_r1/results'
 if found:
  folder=project.get_managed_folder(found[0]['id']);settings=folder.get_settings();current=settings.get_raw_params()
  if settings.type!='S3' or any(current.get(k)!=v for k,v in {'connection':params['connection'],'bucket':params.get('bucket'),'path':path}.items()):raise ValueError('existing vector folder differs; preserved')
 else:
  folder=project.create_managed_folder(name,folder_type='S3',connection_name=params['connection']);settings=folder.get_settings();v=settings.get_raw_params();v['path']=path
  if 'bucket' in params:v['bucket']=params['bucket']
  settings.save()
 code=bootstrap+'\nfrom run_recipe import run\nrun('+repr(folder.id)+')\n'
 recipes={r['name'] for r in project.list_recipes()}
 if recipe_name in recipes:
  settings=project.get_recipe(recipe_name).get_settings()
  if settings.get_code()!=code or set(settings.get_flat_input_refs())!={landing_id} or set(settings.get_flat_output_refs())!={folder.id}:raise ValueError('existing vector recipe differs; preserved')
 else:
  recipe=project.new_recipe('python',recipe_name).with_input(landing_id).with_output(folder.id,append=True).with_script(code).create();settings=recipe.get_settings();settings.set_code_env(inherit=True);settings.save()
 print('설치 완료: LEGAL_04_VECTOR_INITIAL_R1 Run. 구조화/실버 게시가 완료된 release만 읽습니다.')
 return {'recipe':recipe_name,'output':folder.id}
