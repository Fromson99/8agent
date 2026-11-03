"""pipeline — 법령·해석지식 자료의 수집→변환→인제스트→위키 트리아지 CLI 묶음.

전부 저장소 뿌리에서 `python -m lawrag.pipeline.<이름>` 으로 부른다. 어댑터는 sources/,
변환·인제스트 로직의 정본은 core/ 에 있고, 여기 있는 것은 그것을 명령줄로 여는
얇은 단계들이다.

    collect          규정 문서 수집 (--source kofia|fss|krx|law)     → 01_DATA/INBOX/AUTHORING/corpus/<source>/
    collect_expc     법제처 해석례                                    → 01_DATA/INBOX/AUTHORING/corpus/expc/
    collect_fsc      금융위 회신사례                                  → 01_DATA/INBOX/AUTHORING/corpus/fsc/
    collect_prec     판례                                             → 01_DATA/INBOX/AUTHORING/corpus/prec/
    collect_moleg    법제처 입안·심사 기준                            → 01_DATA/INBOX/AUTHORING/corpus/moleg/
    convert          HWP5 → md 사이드카 (core.hwp5_md)               → 01_DATA/INBOX/AUTHORING/corpus/**/*.md
    ingest_lawxml    law.go.kr XML → 구조 스토어                      → 01_DATA/INBOX/AUTHORING/structure/
    ingest_rulehtml  조문 HTML(KRX·KOFIA) → 구조 스토어               → 01_DATA/INBOX/AUTHORING/structure/
    ingest_naegyu    내규 docx → 구조 스토어 (유도 경로+내규 프로파일)  → 01_DATA/INBOX/AUTHORING/structure/
    ingest_files     문서 파일 묶음(hwp·docx·pdf) → 구조 스토어 (범용)   → 01_DATA/INBOX/AUTHORING/structure/
    ingest_expc      해석례 → 열람 색인 + 위키 raw                    → data/expc/, data/wiki/raw/expc/
    ingest_fsc       회신사례 → 위키 raw                              → data/wiki/raw/fsc/
    ingest_prec      판례 → 위키 raw                                  → data/wiki/raw/prec/
    wiki_triage      대화 → 위키 유입 판정                            → data/wiki/wiki/log.md
"""
