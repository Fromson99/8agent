/* 승인 용어 하이라이트 — 본문을 보여주는 화면들의 공용 도구.
 *
 * 입력은 **이미 이스케이프·마크업이 얹힌 HTML**이다 (참조 링크 <a>, 표면
 * 형광 <mark>, 마디 줄 <span class="olh">). 그래서 통짜 replace 를 하면
 * 태그 속성(title="…경로…") 안의 글자까지 형광이 들어가 HTML 이 깨진다.
 * 태그를 경계로 쪼개서 **글자 구간에만** 표시를 얹고, <a>·<mark> 안은
 * 건너뛴다 — 중첩 앵커·형광 위 형광을 만들지 않는다.
 *
 * terms 는 /v1/rag/section 의 [{surface, key}] — 승인(활성) 용어뿐이다.
 * 용어를 누르면 용어집의 그 용어로 간다.
 */
(function () {
  window.uiMarkTerms = function (html, terms) {
    if (!terms || !terms.length) return html;
    const parts = html.split(/(<[^>]+>)/);
    let skip = 0;                          // <a>·<mark> 깊이 — 안에서는 안 칠한다
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      if (p.startsWith("<")) {
        if (/^<(a|mark)\b/i.test(p)) skip++;
        else if (/^<\/(a|mark)\b/i.test(p)) skip = Math.max(0, skip - 1);
        continue;
      }
      if (skip || !p) continue;
      let t = p;
      for (const { surface, key } of terms) {
        if (!surface || !t.includes(surface)) continue;
        t = t.split(surface).join(
          `<a class="term" href="/glossary/#t=${encodeURIComponent(key)}"`
          + ` title="승인 용어 — 용어집에서 보기">${surface}</a>`);
      }
      parts[i] = t;
    }
    return parts.join("");
  };
})();
