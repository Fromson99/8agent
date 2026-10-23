"""Post-run records only. Never changes frozen inputs, outputs, or product code."""
from pathlib import Path
import json,hashlib,statistics
ROOT=Path(__file__).resolve().parents[3]
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
HEADS=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
QHEADS=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
def finish_documents(adr,title,parts,case_parts):
    m=read(adr/'실험/manifest.json')
    for q in m['questions']:
        body=case_parts[q['case_id']]
        file=adr/'실험'/q['file'];file.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(QHEADS,body),1))+'\n');q['sha256']=sha(file)
    put(adr/'실험/manifest.json',m)
    front=(adr/'README.md').read_text().split('---',2)[1]
    (adr/'README.md').write_text('---'+front+'---\n\n# '+title+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(HEADS,parts),1))+'\n')
    (adr/'실험/README.md').write_text('# 실행 기록\n\n[전체 결과](../README.md)\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
def seal(adr):
    art=adr/'artifacts';manifest=art/'manifest.json'
    put(manifest,{'schema_version':'adr-artifacts-v1','adr_id':read(adr/'실험/manifest.json')['adr_id'],
      'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Preserved frozen input, observed output, offline analysis or local research store',
         'contains_raw_prompts_and_outputs':p.suffix=='.gz' or p.name in ('request.json','response.json','output.json')}
         for p in sorted(art.rglob('*')) if p.is_file() and p!=manifest and not p.name.endswith(('-wal','-shm'))]})
