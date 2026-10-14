"""Prepare validated R3 attachments for the explicitly requested Samsung mail."""
import base64, hashlib, json, subprocess, zipfile
from datetime import datetime, timezone
from pathlib import Path

OUT=Path(__file__).resolve().parent
NAME='GENOS_RAG_FOCUSED_RULES_20261013_R3'
FILES=[NAME+'.zip',NAME+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','SHA256SUMS.txt']
TO='hyungjininfocz.son@partner.samsung.com'
SUBJECT='[GENOS 수정 패치 R3] SELECT unit_keys 오류 보완 · R1·R2 적용본에 추가 적용'

def main():
    assert not (OUT/'EMAIL_SENT.json').exists(), 'Check existing sent receipt before sending again'
    hand=json.loads((OUT/'HANDOFF.json').read_bytes())
    assert hand['validation']['installed_contracts']==70
    assert hashlib.sha256((OUT/(NAME+'.zip')).read_bytes()).hexdigest()==hand['code_zip_sha256']
    assert hashlib.sha256((OUT/(NAME+'_RUN.txt')).read_bytes()).hexdigest()==hand['run_txt_sha256']
    subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
    with zipfile.ZipFile(OUT/(NAME+'.zip')) as z:
        assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
        assert z.read(NAME+'_RUN.txt')==(OUT/(NAME+'_RUN.txt')).read_bytes()
        for line in z.read('PACKAGE_SHA256SUMS.txt').decode().splitlines():
            pin,name=line.split('  ',1)
            assert hashlib.sha256(z.read(name)).hexdigest()==pin,name
    for line in (OUT/'SHA256SUMS.txt').read_text().splitlines():
        pin,name=line.split('  ',1)
        assert hashlib.sha256((OUT/name).read_bytes()).hexdigest()==pin,name
    body='''<p>사진에 나온 SELECT 단계의 <code>UnitFulltextIndex.article_groups_page() got an unexpected keyword argument 'unit_keys'</code> 오류를 보완한 R3입니다.</p>
<p>R1에서 범위 제한 검색 호출을 옮기면서 대응 색인 구현을 누락했습니다. R2는 초기화 검증 파일만 수정해 이 누락이 남았습니다. 이번 R3는 필요한 범위 필터와 페이지 커서 결속을 연결하면서 기존 캐시 구현을 보존합니다.</p>
<p><b>R1·R2가 적용된 기존 ~/DEV에 이번 R3를 이어 적용하세요.</b> R2가 아직 적용되지 않았다면 앞서 보낸 R2부터 적용합니다. 이전 캐시·CM·진행 화면 ZIP을 다시 덮어쓸 필요는 없습니다. 원문 재구축과 워크플로우 Python 편집기 교체도 필요하지 않습니다.</p>
<p><b>ZIP으로 반입:</b> 첨부 ZIP을 ~/DEV/TRANSFER에 올린 뒤 Linux/GENOS 코드스페이스에서 아래 명령을 실행합니다.</p>
<pre>python3 -m zipfile -e ~/DEV/TRANSFER/GENOS_RAG_FOCUSED_RULES_20261013_R3.zip ~/DEV/TRANSFER/rag-focused-rules-r3-delivery
cd ~/DEV/TRANSFER/rag-focused-rules-r3-delivery
sha256sum -c PACKAGE_SHA256SUMS.txt
bash GENOS_RAG_FOCUSED_RULES_20261013_R3_RUN.txt</pre>
<p>실행 TXT도 별도로 첨부했습니다. 독립 TXT를 ~/DEV/TRANSFER에 올린 경우에는 <code>bash ~/DEV/TRANSFER/GENOS_RAG_FOCUSED_RULES_20261013_R3_RUN.txt</code>로 실행할 수 있습니다. 두 방법 모두 기존 ~/DEV에 백업 후 적용하며 지속 로그를 남깁니다.</p>
<p>적용 후 같은 DEV에서 <b>commit → 현재 선택 generation으로 gate → push → 새 코드서빙 리비전 배포</b> 순서로 진행합니다. 필요한 BACKUP 경로와 현재 generation 절대경로를 지정하는 전체 명령, 재실행·원복 방법은 GUIDE_UTF8.txt를 따릅니다. 별도 SSE 서버도 기존 설정으로 재시작하고, 최종 확인은 워크플로우 테스트 화면에서 합니다.</p>
<p>대표 설치 3종에서 사진과 동일한 오류를 재현하고 R3 적용 후 실제 조문 조회 통과를 확인했습니다. 설치 코드의 구조 탐색·캐시 회귀 70개, 적용·재실행·변조 거부·원복, 같은 committed checkout의 모의 generation gate 3개가 통과했습니다. 실제 네트워크 및 모델 추론 호출은 0회입니다.</p>
<p>이번 결과는 WSL 로컬 검증입니다. GENOS 현장 적용·push·새 리비전·워크플로우 성공은 아직 확인하지 않았습니다. R3 undo는 오류가 남은 R2로 돌아가므로 원복 시 안내의 순서를 확인하세요.</p>'''
    parts=[{'mime_type':'text/html','charset':'utf-8','body':{'content':body}}]
    attachments=[]
    for name in FILES:
        raw=(OUT/name).read_bytes()
        parts.append({'mime_type':'application/zip' if name.endswith('.zip') else 'text/plain',
            'filename':name,'content_disposition':'attachment',
            'body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode().rstrip('=')}})
        attachments.append({'filename':name,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    args={'to':TO,'subject':SUBJECT,'reply_message_id':'1a132b15ca149f1e',
          'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
    path=Path('/tmp/genos-focused-rules-r3-mail.json')
    path.write_text(json.dumps(args,ensure_ascii=True,separators=(',',':')))
    record={'status':'PREPARED_NOT_SENT','to':TO,'subject':SUBJECT,
        'reply_message_id':args['reply_message_id'],'prepared_at_utc':datetime.now(timezone.utc).isoformat(),
        'attachments':attachments,'args_bytes':path.stat().st_size,'args_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (OUT/'EMAIL_PREPARED.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'path':str(path),**record},ensure_ascii=False))

if __name__=='__main__':main()
