# data/ — 컨테이너가 쓰는 자리 (바인드 마운트)

`docker-compose.yml` 이 `./data/structure` 를 컨테이너의 `/data/structure` 에 바인드한다.
화면에서 올린 PDF·해석 산출·페이지 캐시·등록한 규칙이 **여기 그대로 쌓인다.**

    data/structure/{doc_id}/
      source.pdf         올린 원본
      meta.json          파일명·업로드 시각·해석 옵션
      payload.json       검수 화면이 받는 것 (트리·블록·표·그림)
      pages/p{N}.png     페이지 렌더 캐시
      custom/            화면에서 등록한 표면 패턴

named volume 이 아니라 바인드인 이유: 올린 문서를 호스트에서 바로 열어 보고, 문제가
생긴 문서를 그대로 `first-agent/dataset/` 으로 옮겨 재현할 수 있어야 하기 때문이다.

경로를 바꾸려면 `STRUCTURE_DATA=/어딘가 docker compose up -d`.
