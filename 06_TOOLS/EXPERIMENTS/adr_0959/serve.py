"""Authenticated local viewer/editor. Completed run evidence stays immutable."""
from pathlib import Path
import argparse
import importlib.util
import json
import shutil
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('frozen_e2e_host',HERE/'e2e.py')
host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)


def make_app(directory=None):
    C=host.code_root()
    sys.path.insert(0,str(C/'02_BACKEND'))
    from lawrag.platform.workspace import load_layout
    directory=Path(directory) if directory else load_layout(host.R).path('runtime')/'legal-knowledge-e2e'/'ADR0959'
    directory.mkdir(parents=True,exist_ok=True)
    completed=host.A/'artifacts/run-001'
    if not (directory/'knowledge-lab.sqlite').exists():
        shutil.copyfile(completed/'knowledge-lab.sqlite',directory/'knowledge-lab.sqlite')
    app=host.make_app(directory)
    from semantic_runtime.legal_agent.errors import ContractError
    def no_model(**kwargs):
        raise ContractError('결과 화면은 모델을 호출하지 않습니다. 새 실행은 고정한 실험 명세를 사용하세요.')
    app.state.e2e['transport'].send_once=no_model
    # Original app ends with a legacy catch-all. Explicit E2E routes must precede it.
    app.router.routes[:]=[r for r in app.router.routes if getattr(r,'path',None) not in ('/e2e/','/e2e/results','/e2e/receipt/{case_id}')]
    from fastapi.responses import JSONResponse, HTMLResponse
    @app.get('/e2e/',response_class=HTMLResponse)
    def view(): return (HERE/'results.html').read_text()
    @app.get('/e2e/results')
    def results():
        rows=[]
        for case in host.read(host.D/'cases.json'):
            p=completed/case['case_id']/'result.json'
            result=host.read(p) if p.exists() else {'status':'NOT_RUN'}
            response=completed/case['case_id']/'response.json'
            if result['status']=='FAILED' and response.exists():
                failure=host.read(response)['body']
                result['error_code']=failure.get('error_code')
                result['error']=('모델 공급자 요청 제한(429)으로 답변이 발행되지 않았습니다.'
                    if result['error_code']=='429' else failure.get('message',result.get('error')))
            rows.append({**case,**result})
        return {'environment':'WSL local E2E · 원문28문서 · Oracle 미검증 · MAIN96 유지','cases':rows}
    @app.get('/e2e/receipt/{case_id}')
    def receipt(case_id:str):
        if case_id not in {c['case_id'] for c in host.read(host.D/'cases.json')}:
            return JSONResponse({'status':'NOT_FOUND'},status_code=404)
        p=completed/case_id/'response.json'
        return host.read(p) if p.exists() else {'status':'NOT_RUN'}
    app.router.routes.sort(key=lambda r:0 if getattr(r,'path','').startswith('/e2e') else 1)
    return app


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8768)
    args=parser.parse_args()
    app=make_app()
    print(f'http://127.0.0.1:{args.port}/e2e/login',flush=True)
    print('로컬 로그인 토큰: '+app.state.e2e_token,flush=True)
    print('화면 편집은 별도 로컬 작업 DB에 저장됩니다. 모델 호출은 차단됩니다.',flush=True)
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,workers=1)
