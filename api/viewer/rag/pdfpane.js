/* PDF 앵커 패널 — 질의응답·디버깅 화면 공용. 근거·경로·본문 속 제N조를
 * 누르면(data-pp) 오른쪽에 원문 쪽이 뜨고 앵커 상자가 그 자리를 표시한다.
 * 타고 넘어간 길은 궤적 칩으로 남고, 이전 칩을 누르면 그 뒤는 잘린다.
 * 전역 $, esc, api 는 앞서 로드된 화면 스크립트가 정의한다. */
"use strict";

const ppTail = (p) => String(p || "").split(" ▸ ").filter(Boolean).slice(-2).join(" ▸ ");

/* ------------------------------------------------ 오른쪽 PDF 패널
 * 근거·회수 구역·본문 속 제N조를 누르면 그 구역의 원문 쪽이 뜨고 앵커 상자가
 * 표시된다. 위키처럼 계속 타고 넘어가고, 궤적 칩으로 되돌아온다(뒤는 잘림). */
const PP = { trail: [], nav: false };

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-pp]");
  if (!el) return;
  e.preventDefault();
  openSection(el.dataset.doc, +el.dataset.node, el.dataset.label || "",
              el.dataset.tone || "");
});

/* tone — 이 자리가 무엇인가를 색으로 말한다. "bad" 는 잘못된 연결의 끝(빨강),
 * "ok" 는 제안된 옳은 자리(초록), 기본은 그냥 근거(초록 앵커). */
function openSection(doc, node, label, tone) {
  if (!PP.nav) {
    const last = PP.trail[PP.trail.length - 1];
    if (!last || last.doc !== doc || last.node !== node) {
      PP.trail.push({ doc, node, label: label || `구역 ${node}`, tone });
      if (PP.trail.length > 30) PP.trail.shift();
    }
  }
  PP.tone = tone || "";
  renderPPTrail();
  loadPP(doc, node);
}

function ppGo(i) {
  const t = PP.trail[i];
  if (!t) return;
  PP.trail = PP.trail.slice(0, i + 1);       // 뒤로 가면 그 앞은 날린다
  renderPPTrail();
  PP.nav = true;
  PP.tone = t.tone || "";
  try { loadPP(t.doc, t.node); } finally { PP.nav = false; }
}

function renderPPTrail() {
  const bar = $("ppTrail");
  if (PP.trail.length < 2) { bar.classList.add("hidden"); return; }
  bar.classList.remove("hidden");
  bar.innerHTML = PP.trail.map((t, i) =>
    `${i ? '<span class="tarr">→</span>' : ""}
     <span class="tchip${i === PP.trail.length - 1 ? " cur" : ""}" data-i="${i}"
           title="${esc(t.label)}">${esc(t.label)}</span>`).join("");
  bar.querySelectorAll(".tchip").forEach((el) => {
    el.onclick = () => ppGo(+el.dataset.i);
  });
  bar.scrollLeft = bar.scrollWidth;
}

async function loadPP(doc, node) {
  $("pdfpane").classList.remove("hidden");
  document.body.classList.add("haspp");
  $("ppBody").innerHTML = "<p class='sub' style='padding:10px'>원문 불러오는 중…</p>";
  let d;
  try {
    d = await api(`/v1/rag/section?doc_id=${encodeURIComponent(doc)}&node=${node}`);
  } catch (err) {
    $("ppBody").innerHTML = `<p class="sub" style="padding:10px">불러오지 못했습니다: ${esc(err.message)}</p>`;
    return;
  }
  $("ppDoc").textContent = (d.doc || "").replace(/\.pdf$/i, "");
  $("ppStruct").href = `/structure/?doc=${encodeURIComponent(doc)}&node=${node}`;
  const last = PP.trail[PP.trail.length - 1];
  if (last && last.doc === doc && last.node === node) {
    last.label = ppTail(d.path) || last.label;
    renderPPTrail();
  }
  const g = d.geo || {};
  const page = g.page || d.page || 1;
  // 페이지 넘김 상태 — 앵커(rect·page)는 고정이고 shown 만 움직인다.
  // 앵커 페이지로 돌아오면 하이라이트가 다시 그려진다. 계층 보기에서 층을
  // 고르면 그 층의 geo 가 새 앵커가 된다.
  PP.cur = { doc, node, page, rect: g.rect || null,
             pages: d.pages || page, shown: page,
             tree: d.children || [], root: { label: ppTail(d.path), page, rect: g.rect } };
  const tree = PP.cur.tree;
  $("ppBody").innerHTML = `
    <div class="pppath">${esc(d.path)} <span class="sub">p.${page}</span></div>
    <div class="ppnav">
      <button id="ppPrev" title="이전 페이지">◀</button>
      <span id="ppPageNum" class="sub"></span>
      <button id="ppNext" title="다음 페이지">▶</button>
      <button id="ppAnchor" title="앵커(하이라이트) 페이지로 돌아간다">⌖ 앵커로</button>
      <span class="grow"></span>
      <button id="ppVText" class="ppv on">원문</button>
      <button id="ppVTree" class="ppv ${tree.length ? "" : "hidden"}">계층 ${tree.length}</button>
    </div>
    <div class="pppage" id="ppPageBox"></div>
    <div id="ppText" class="pptxt">${ppLinkify(d.text, d.refs, d.doc_id)}</div>
    <div id="ppTree" class="pptree hidden">
      <div class="ptbar sub">층을 누르면 그 자리가 하이라이트됩니다. 계층이 잘못
        붙었으면 <b>⇥ 들여쓰기</b>(앞 형제 밑으로) · <b>⇤ 내어쓰기</b>(부모 밖으로)로
        고칩니다 — 재해석해도 남습니다.
        <button id="ppSuggest" class="ppv">✨ LLM 제안</button></div>
      <div id="ppSug" class="ppsug hidden"></div>
      <div class="ptrow cur" data-i="-1" title="이 구역 전체">
        <b>${esc(ppTail(d.path) || "이 구역")}</b> <span class="sub">전체</span></div>
      ${tree.map((c, i) => `
        <div class="ptrow" data-i="${i}" style="padding-left:${10 + c.depth * 16}px"
             title="p.${(c.geo || {}).page ?? "?"}">
          <b>${esc(c.label || "(라벨 없음)")}</b>
          <span class="sub">${esc(c.snippet || "")}</span>
          ${c.fixed ? `<span class="badge ok" title="사람이 옮긴 마디">교정</span>` : ""}
          <span class="ptact">
            <button class="ptin" data-i="${i}" title="들여쓰기 — 바로 앞 형제 밑으로">⇥</button>
            <button class="ptout" data-i="${i}" title="내어쓰기 — 부모 밖으로">⇤</button>
          </span>
        </div>`).join("")}
    </div>
    ${(d.cited_by || []).length ? `<div class="sub" style="margin-top:9px">이 구역을 가리키는 곳</div>`
      + d.cited_by.map((c) => `
        <div class="ctxrow">
          <a class="pplink" data-pp data-doc="${esc(c.src_doc)}" data-node="${c.src}"
             data-label="${esc(ppTail(c.src_path))}"
             title="${esc(c.src_path)}">${esc(ppTail(c.src_path) || c.src_doc)}</a>
          <span class="badge">${esc(c.surface)}</span>
        </div>`).join("") : ""}`;
  $("ppPrev").onclick = () => ppPage(PP.cur.shown - 1);
  $("ppNext").onclick = () => ppPage(PP.cur.shown + 1);
  $("ppAnchor").onclick = () => ppPage(PP.cur.page, true);
  ppWireView();
  if (PP.view === "tree" && tree.length) ppSetView("tree");
  ppPage(page, true);
}

/* 원문 ↔ 계층 보기. 계층에서 층을 고르면 그 층의 자리(geo)가 **새 앵커**가
 * 된다 — 하이라이트가 그 층으로 옮겨 앉고 페이지가 그리로 간다. */
function ppSetView(v) {
  PP.view = v;
  $("ppVText").classList.toggle("on", v === "text");
  $("ppVTree").classList.toggle("on", v === "tree");
  $("ppText").classList.toggle("hidden", v !== "text");
  $("ppTree").classList.toggle("hidden", v !== "tree");
}

function ppWireView() {
  $("ppVText").onclick = () => ppSetView("text");
  $("ppVTree").onclick = () => ppSetView("tree");
  $("ppTree").querySelectorAll(".ptrow").forEach((row) => {
    row.onclick = (ev) => {
      if (ev.target.closest("button")) return;
      $("ppTree").querySelectorAll(".ptrow").forEach((x) => x.classList.remove("cur"));
      row.classList.add("cur");
      const i = +row.dataset.i;
      const t = i < 0 ? PP.cur.root : PP.cur.tree[i];
      const geo = i < 0 ? { page: t.page, rect: t.rect } : (t.geo || {});
      if (geo.page == null) return;
      PP.cur.page = geo.page;               // 고른 층이 새 앵커다
      PP.cur.rect = geo.rect || null;
      ppPage(geo.page, true);
    };
  });
  $("ppTree").querySelectorAll(".ptin").forEach((b) => {
    b.onclick = () => ppReparent(+b.dataset.i, "in");
  });
  $("ppTree").querySelectorAll(".ptout").forEach((b) => {
    b.onclick = () => ppReparent(+b.dataset.i, "out");
  });
  if ($("ppSuggest")) $("ppSuggest").onclick = ppSuggest;
}

/* LLM 계층 제안 — 제안만 받아 온다(서버가 아무것도 안 바꾼다). 사람이 고른
 * 것만 적용되고, 적용된 교정은 한 건씩 되돌릴 수 있다. */
async function ppSuggest() {
  const btn = $("ppSuggest"), box = $("ppSug");
  btn.disabled = true; btn.textContent = "훑는 중…";
  box.classList.remove("hidden");
  box.innerHTML = `<span class="sub">LLM 이 이 구역의 계층을 읽고 있습니다…</span>`;
  let d;
  try {
    d = await api(`/v1/structure/${encodeURIComponent(PP.cur.doc)}/hierarchy/suggest`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ node: PP.cur.node }),
    });
  } catch (err) {
    box.innerHTML = `<span class="sub">제안 실패: ${esc(err.message)}</span>`;
    btn.disabled = false; btn.textContent = "✨ LLM 제안";
    return;
  }
  btn.disabled = false; btn.textContent = "✨ LLM 제안";
  const fx = d.fixes || [];
  box.innerHTML = `<div class="plabel">LLM 계층 제안 ${fx.length}건
      <span class="sub">(마디 ${d.scanned}개를 훑음 · 적용 전까지 아무것도 안 바뀝니다)</span></div>`
    + (fx.length ? fx.map((f, i) => `
      <div class="sugrow" data-i="${i}">
        <b>${esc(f.label || f.node)}</b>
        <span class="sub">${esc(f.now_parent_label || "(뿌리)")} →
          <b class="ok">${esc(f.parent_label || "(이 구역)")}</b></span>
        <span class="sub why">${esc(f.why)}</span>
        <button class="sugok" data-i="${i}">적용</button>
      </div>`).join("")
      : `<span class="sub">고칠 곳을 찾지 못했습니다 — 계층이 맞다는 판단입니다</span>`);
  box.querySelectorAll(".sugok").forEach((b) => {
    b.onclick = async () => {
      const f = fx[+b.dataset.i];
      b.disabled = true;
      try {
        await api(`/v1/structure/${encodeURIComponent(PP.cur.doc)}/hierarchy/fix`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ node: f.node, parent: f.parent,
                                 note: `LLM 제안: ${f.why}` }),
        });
      } catch (err) { alert("적용 실패: " + err.message); b.disabled = false; return; }
      PP.view = "tree";
      loadPP(PP.cur.doc, PP.cur.node);
    };
  });
}

/* 계층 교정 — 들여쓰기는 **바로 앞 형제** 밑으로, 내어쓰기는 **부모 밖**으로.
 * 목록 편집기와 같은 손짓이라 새 부모를 고르는 창이 필요 없다. 서버는 좌표
 * 수정으로 남기므로 재해석해도 살아남는다. */
async function ppReparent(i, dir) {
  const tree = PP.cur.tree, cur = tree[i];
  if (!cur) return;
  let parent;
  if (dir === "in") {
    const prev = [...tree.slice(0, i)].reverse()
      .find((x) => x.parent === cur.parent);      // 바로 앞 형제
    if (!prev) { alert("앞 형제가 없어 들여쓸 수 없습니다"); return; }
    parent = prev.node;
  } else {
    if (cur.parent === PP.cur.node) {
      alert("이미 이 구역의 첫 층입니다 — 더 내어쓸 수 없습니다");
      return;
    }
    const p = tree.find((x) => x.node === cur.parent);
    parent = p ? p.parent : PP.cur.node;          // 부모의 부모
  }
  try {
    await api(`/v1/structure/${encodeURIComponent(PP.cur.doc)}/hierarchy/fix`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ node: cur.node, parent,
                             note: `${dir === "in" ? "들여쓰기" : "내어쓰기"} — ${cur.label}` }),
    });
  } catch (err) { alert("계층 교정 실패: " + err.message); return; }
  PP.view = "tree";
  loadPP(PP.cur.doc, PP.cur.node);                // 고친 트리로 다시 그린다
}

/* 페이지 그리기 — shown 페이지의 이미지를 갈아 끼운다. 앵커 페이지일 때만
 * 하이라이트 상자를 얹는다(다른 쪽을 보다 돌아와도 상자는 그대로다). */
function ppPage(shown, scrollToBox) {
  const c = PP.cur;
  if (!c) return;
  c.shown = Math.min(Math.max(1, shown), Math.max(c.pages, 1));
  const onAnchor = c.shown === c.page;
  const tone = PP.tone === "bad" ? " bad" : PP.tone === "ok" ? " ok" : "";
  const tag = PP.tone === "bad" ? `<span class="ppboxtag">잘못된 연결</span>`
            : PP.tone === "ok" ? `<span class="ppboxtag">제안된 자리</span>` : "";
  const box = (onAnchor && c.rect)
    ? `<div class="ppbox${tone}" style="left:${c.rect.x * 100}%;top:${c.rect.y * 100}%;`
      + `width:${c.rect.w * 100}%;height:${c.rect.h * 100}%">${tag}</div>` : "";
  $("ppPageBox").innerHTML =
    `<img src="/v1/structure/${encodeURIComponent(c.doc)}/page/${c.shown}"
          alt="p.${c.shown}">${box}`;
  $("ppPageNum").textContent = `p.${c.shown} / ${c.pages}`
    + (onAnchor ? "" : ` (앵커 p.${c.page})`);
  $("ppPrev").disabled = c.shown <= 1;
  $("ppNext").disabled = c.shown >= c.pages;
  $("ppAnchor").classList.toggle("hidden", onAnchor);
  const bx = $("ppPageBox").querySelector(".ppbox");
  const img = $("ppPageBox").querySelector("img");
  const sc = () => {
    if (scrollToBox && bx) bx.scrollIntoView({ block: "center", behavior: "smooth" });
    else if (!scrollToBox) $("ppPageBox").scrollIntoView({ block: "start" });
  };
  if (img && !img.complete) img.addEventListener("load", sc, { once: true });
  else sc();
}

/* 본문 속 표면형 → 패널 링크. 긴 표면형 먼저(제4조가 제4조의2를 깨지 않게),
 * 문서-안 간선은 외부 힌트가 붙은 출현("법 제238조")을 물지 않는다 —
 * links 뷰어의 linkify 와 같은 규율이다. */
const PP_HINT = new RegExp(
  "(?:[가-힣A-Za-z0-9·]{0,20}(?:법|법률|령|규칙|세칙|규정|약관|조례|정관|지침|고시)"
  + "|」|(?<![가-힣])영)\\s*$");

function ppLinkify(text, refs, docId) {
  let html = esc(text || "");
  const sorted = [...(refs || [])].sort((a, b) => b.surface.length - a.surface.length);
  sorted.forEach((r, i) => {
    const s = esc(r.surface);
    if (!s) return;
    const guard = r.dst_doc === docId && !r.via;
    let out = "", p = 0;
    for (let j = html.indexOf(s); j >= 0; j = html.indexOf(s, p)) {
      const skip = guard && PP_HINT.test(html.slice(Math.max(0, j - 48), j));
      out += html.slice(p, j) + (skip ? s : `\u0000${i}\u0000`);
      p = j + s.length;
    }
    html = out + html.slice(p);
  });
  return html.replace(/\u0000(\d+)\u0000/g, (_, i) => {
    const r = sorted[+i];
    return `<a class="pplink" data-pp data-doc="${esc(r.dst_doc)}" data-node="${r.dst}"
      data-label="${esc(ppTail(r.dst_path))}" title="${esc(r.dst_path)}">${esc(r.surface)}</a>`;
  });
}

$("ppClose").onclick = () => {
  $("pdfpane").classList.add("hidden");
  document.body.classList.remove("haspp");
};

