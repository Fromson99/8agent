# 사람이 등록한 표면 패턴

파일 하나가 규칙 하나. 파일명 = `id`. 화면(`힌트 > 규칙`)이나 API 로 더할 수 있다.

```yaml
id: bwek
family: bwek
surface: "뷁N아"
pattern: '^뷁\s*(\d+)\s*아'
groups: [no]
ordinal_from: [no]
lang: any
note: "2026-08 A은행 약관에서 처음 관찰"
```

- `pattern` 은 반드시 `^` 로 시작한다. 앵커가 없으면 문장 한복판의 인용을 삼킨다.
- `level` · `rank` · `parent` 는 **넣을 수 없다**(등록 시 거부). 계층은 문서가 유도한다(SPEC §6).
- 서수 글자→정수 변환은 기존 어휘(`lexicon/numerals.yaml`)가 한다 — 아라비아·원문자·한글·로마 전부 이미 있다.
- 등록된 순간부터 연속 단위·들여쓰기·DP 가 그대로 적용된다.
