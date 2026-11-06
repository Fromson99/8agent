"""Read stored results and render them with the selected release, without another request."""
from common import *
import asyncio
import importlib.util
from bs4 import BeautifulSoup
from copy import deepcopy
sys.path.insert(0,str(ROOT/'06_TOOLS/EXPERIMENTS/integration_oneclick'))
from review_public import review_response
pin=read(DES/'candidate-selected.json');code=ROOT/pin['code_root']
workflow_path=code/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
assert sha(workflow_path)==pin['selected_files'][str(workflow_path.relative_to(code))]
spec=importlib.util.spec_from_file_location('selected_display',workflow_path)
view=importlib.util.module_from_spec(spec);spec.loader.exec_module(view)
grades={c['id']:c for c in read(DES/'grading-only.json')}
for cell in sorted((ART/'public-live').glob('*')):
    path=cell/'turn-1/response.json.gz'
    if not path.is_file():continue
    response=read(path)
    body=deepcopy(response['body']);code_http=response['http_status']
    if code_http>=400:body['_gateway_status']=code_http
    rendered=asyncio.run(view.workflow_display_result(body,[],request_id=body.get('request_id','')))
    html=rendered['text']
    assert sha(workflow_path)==pin['selected_files'][str(workflow_path.relative_to(code))]
    soup=BeautifulSoup(html,'html.parser')
    panels=[t.get_text(' ',strip=True)[:160] for t in soup.select('details > summary')]
    for section in soup.select('details:not([open])'):
        if section.parent is None:continue
        label=section.find('summary',recursive=False)
        section.replace_with(label.get_text(' ',strip=True) if label else '')
    for section in soup.select('svg,script,style,img'):section.decompose()
    front=soup.get_text('\n',strip=True)
    out=cell/'turn-1'
    (out/'사용자_답변.txt').write_text(front+'\n')
    put(out/'display-review-data.json',{**review_response(body,grades[cell.name.rsplit('-',1)[0]]['anchors']),
        'request_status':code_http,'source_response_sha256':sha(path),'workflow_renderer_sha256':sha(workflow_path),
        'collapsed_panel_labels':panels,'display_text_sha256':hashlib.sha256(html.encode()).hexdigest(),
        'full_rendered_response':write_raw_json(out/'rendered-display.json.gz',rendered) if not (out/'rendered-display.json.gz').exists() else {'path':str(out/'rendered-display.json.gz'),'sha256':sha(out/'rendered-display.json.gz')},
        'scope':'Offline release workflow rendering of the untouched API response, empty progress-event list; browser and live UI not exercised.'})
    print(cell.name,front[:900])
