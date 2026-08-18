/* 참조 연결 — 본문의 "제4조를 참고한다"가 세운 간선을 사람이 검수하는 화면.
 *
 * 세 켜로 보여준다.
 *   문서 사이   이름 대조·판정(LLM/사람)으로 확정된 것 — via 가 경위다
 *   보류        대용어(동법…)라 못 정한 것 — 원문과 닫힌 후보를 그대로 보여
 *               주고, 여기서 고르면 links.json 에 고정된다(질의마다 재판단 없음)
 *   문서 안     같은 문서의 가로 참조 — 결정론 전부, 고칠 것은 구조 쪽이다
 *
 * 좌표가 전부다: 모든 행에서 구조 뷰어 딥링크로 그 자리를 열 수 있어야
 * "어디가 어디를 가리키나"에 화면으로 답한 것이다. */
const API = "/v1/rag/links";
const S = { data: null, doc: null, q: "" };
const $ = (id) => document.getElementById(id);
const esc = (s) => (s || "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const COLORS = ["#60a5fa", "#4ade80", "#fbbf24", "#f472b6", "#a78bfa", "#22d3ee"];
const VIA_CLS = { "이름대조": "ok", "선언": "ok", "LLM": "accent", "사람": "warn",
                  "추정": "", "교정": "accent", "규칙": "warn" };
/* 관계 배지 — 간선의 의미(문면 술어에서 결정론 분류). 근거·인용은 대다수라
 * 배지를 접고(소음), 회수 정책이 갈리는 준용·배제·의제만 눈에 띄운다. */
const REL_CLS = { "준용": "accent", "배제": "bad", "의제": "warn", "수임": "ok" };
const relPill = (rel) =>
  REL_CLS[rel] ? `<span class="pill ${REL_CLS[rel]}">${rel}</span> ` : "";
/* 관계 정정 — 자동 분류(문면 술어)가 틀리면 사람이 여기서 덮는다.
 * links.json rel_fixes 에 남고, 비우면(자동값 재선택) 해제된다. */
const REL_OPTS = ["인용", "근거", "수임", "준용", "배제", "의제"];
const relSel = (r, i) => r.src_id == null ? "" :
  `<select class="relsel" data-r="${i}" title="관계 정정 — 자동 분류를 덮습니다">`
  + REL_OPTS.map((o) =>
      `<option${o === (r.rel || "인용") ? " selected" : ""}>${o}</option>`).join("")
  + `</select>`;

async function load() {
  const r = await fetch(API);
  S.data = await r.json();
  S.color = {};
  S.name = {};
  S.data.docs.forEach((d, i) => {
    S.color[d.doc_id] = COLORS[i % COLORS.length];
    S.name[d.doc_id] = d.doc;
  });
  // 딥링크 ①: ?doc=<doc_id> — 구조 검수의 "참조 →" 가 문서 하나를 짚어 보낸다
  const d0 = new URLSearchParams(location.search).get("doc");
  if (d0 && S.data.docs.some((x) => x.doc_id === d0)) S.doc = d0;
  render();
  // 딥링크 ②: #pending — 홈 할 일·상단바 배지가 보류 검수 자리로 바로 보낸다
  if (location.hash === "#pending") {
    setTab("list");
    $("pendTitle")?.scrollIntoView({ block: "start" });
  }
}

function render() {
  const d = S.data;
  const nIn = Object.values(d.in_doc).reduce((a, es) => a + es.length, 0);
  $("summary").textContent =
    `문서 ${d.docs.length} · 문서 안 ${nIn} · 문서 사이 ${d.cross.length}`
    + ` · 보류 ${d.pending.length}`;
  renderDocs();
  renderMap();
  renderCross();
  renderPending();
  renderInDoc();
  if (S.tab === "doc") renderDoc();
  LG.ready = false;                      // 데이터가 새로 왔다 — 그래프는 다시 세운다
  if (S.tab === "graph") { buildLinkGraph(); drawLinkGraph(); lgDetail(); }
}

function setTab(t) {
  S.tab = t;
  $("tabDoc").classList.toggle("on", t === "doc");
  $("tabList").classList.toggle("on", t === "list");
  $("tabGraph").classList.toggle("on", t === "graph");
  $("docview").classList.toggle("hidden", t !== "doc");
  $("mainscroll").classList.toggle("hidden", t !== "list");
  $("graphview").classList.toggle("hidden", t !== "graph");
  $("tabHint").textContent =
    t === "graph" ? "휠 확대 · 끌어 이동 · 마디 클릭 = 원문 · 원문 속 참조 클릭 = 이동"
    : t === "doc" ? "참조가 쓰인 자리 위에 링크 — 클릭하면 그 조문으로 갑니다" : "";
  if (t === "doc" && S.data) renderDoc();
  if (t === "graph" && S.data) {
    if (!LG.ready) buildLinkGraph();
    drawLinkGraph(); lgDetail();
  }
}

/* ------------------------------------------------------- 문서(PDF) 탭
 * 첫 화면 — PDF 페이지가 그대로 뜨고, 참조가 쓰인 블록 위에 연결 링크가
 * 얹힌다. 좌표는 서버가 준 정규화 rect(0~1) 그대로 비율로 쓴다 — 화면
 * 배율을 몰라도 자리가 맞는다. */
function docRefGroups(d) {
  const rows = [];
  for (const e of S.data.in_doc[d] || []) {
    rows.push({ kind: "in", surface: e.surface, block: e.block, geo: e.src_geo,
                src_path: e.src_path, rel: e.rel,
                src_doc: d, src_id: e.src, dst_doc: "", dst_id: e.dst,
                dst: { doc: d, name: S.name[d], path: e.dst_path, geo: e.dst_geo } });
  }
  for (const e of S.data.cross) {
    if (e.src_doc === d && e.block != null) {
      rows.push({ kind: "cross", surface: e.surface, block: e.block, geo: e.src_geo,
                  via: e.via, src_path: e.src_path, rel: e.rel,
                  src_doc: e.src_doc, src_id: e.src, dst_doc: e.dst_doc, dst_id: e.dst,
                  dst: { doc: e.dst_doc, name: e.dst_doc_name, path: e.dst_path,
                         geo: e.dst_geo } });
    }
  }
  for (const p of S.data.pending) {
    if (p.src_doc === d && p.block != null) {
      rows.push({ kind: "pend", surface: p.surface, block: p.block, geo: p.src_geo,
                  src_path: p.src_path, hint: p.hint, cands: p.candidates,
                  rel: p.rel });
    }
  }
  const by = new Map();                    // 같은 블록의 참조들은 상자 하나로
  for (const r of rows) {
    if (!r.geo || r.geo.page == null || !r.geo.rect) continue;
    by.set(r.block, by.get(r.block) || []);
    by.get(r.block).push(r);
  }
  return [...by.values()];
}

function renderDoc() {
  const d = S.doc || (S.data.docs.find((x) => x.n_in) || S.data.docs[0] || {}).doc_id;
  if (!d) { $("pages").innerHTML = "<p class='hint'>문서가 없습니다.</p>"; return; }
  S.docShown = d;
  const info = S.data.docs.find((x) => x.doc_id === d) || { pages: 1, doc: d };
  const groups = docRefGroups(d);
  const byPage = new Map();
  groups.forEach((g, i) => {
    const p = g[0].geo.page;
    byPage.set(p, byPage.get(p) || []);
    byPage.get(p).push(i);
  });
  const box = (g, i) => {
    const r = g[0].geo.rect;
    const conf = g.filter((x) => x.kind !== "pend");
    const cls = conf.length ? "" : " pend";
    const tag = conf.length
      ? `→ ${g[0].surface}${g.length > 1 ? ` 외 ${g.length - 1}` : ""}`
      : `보류 ${g[0].surface}`;
    return `<div class="refbox${cls}" data-g="${i}" style="left:${r.x * 100}%;`
      + `top:${r.y * 100}%;width:${r.w * 100}%;height:${r.h * 100}%">`
      + `<span class="reftag">${esc(tag)}</span></div>`;
  };
  let html = `<div class="docgroup" style="margin:0 0 8px">
      <span class="dot" style="background:${S.color[d]}"></span>
      ${esc(short(info.doc))} <span class="pill">참조 ${groups.length}자리</span></div>`;
  for (let p = 1; p <= info.pages; p++) {
    html += `<div class="pg" data-page="${p}">
      <img src="/v1/structure/${encodeURIComponent(d)}/page/${p}" loading="lazy" alt="p.${p}">
      <span class="pgnum">p.${p}</span>
      ${(byPage.get(p) || []).map((i) => box(groups[i], i)).join("")}
    </div>`;
  }
  $("pages").innerHTML = html;
  const tip = $("gtip");
  $("pages").querySelectorAll(".refbox").forEach((el) => {
    const g = groups[+el.dataset.g];
    el.onclick = (ev) => { ev.stopPropagation(); refMenu(g, ev); };
    el.onmouseenter = () => {
      tip.innerHTML = g.map((r) => r.kind === "pend"
        ? `<span class="pill warn">보류</span> ${relPill(r.rel)}${esc(r.surface)} — 후보 ${r.cands.length}`
        : `${relPill(r.rel)}<span class="chip">${esc(r.surface)}</span> ${esc(short(r.dst.name || ""))}`
          + ` ▸ ${esc(r.dst.path)}`).join("<br>");
      tip.classList.remove("hidden");
    };
    el.onmousemove = (ev) => {
      tip.style.left = `${ev.clientX + 14}px`;
      tip.style.top = `${ev.clientY + 10}px`;
    };
    el.onmouseleave = () => tip.classList.add("hidden");
  });
}

/* 링크 상자 클릭 — 하나면 바로 이동, 여럿·보류면 고르는 메뉴. */
function refMenu(g, ev) {
  const conf = g.filter((x) => x.kind !== "pend");
  if (conf.length === 1 && g.length === 1) { follow(g, conf[0].dst); return; }
  const menu = $("refmenu");
  const rows = [];
  g.forEach((r, i) => {
    if (r.kind !== "pend") {
      rows.push(`<div class="mi" data-r="${i}">${relPill(r.rel)}<span class="chip">${esc(r.surface)}</span>
        <span class="p">${esc(short(r.dst.name || ""))} ▸ ${esc(r.dst.path)}</span>${relSel(r, i)}</div>`);
    } else {
      r.cands.forEach((c, j) => rows.push(
        `<div class="mi" data-r="${i}" data-c="${j}"><span class="pill warn">보류</span>
          ${relPill(r.rel)}<span class="chip">${esc(r.surface)}</span>
          <span class="p">후보: ${esc(short(c.doc))} ▸ ${esc(c.path)}</span></div>`));
    }
  });
  menu.innerHTML = rows.join("");
  menu.classList.remove("hidden");
  menu.style.left = `${Math.min(ev.clientX, window.innerWidth - 460)}px`;
  menu.style.top = `${Math.min(ev.clientY + 8, window.innerHeight - 40 - rows.length * 28)}px`;
  menu.querySelectorAll(".mi").forEach((mi) => {
    mi.onclick = () => {
      const r = g[+mi.dataset.r];
      menu.classList.add("hidden");
      if (r.kind !== "pend") follow(g, r.dst);
      else {
        const c = r.cands[+mi.dataset.c];
        follow(g, { doc: c.doc_id, name: c.doc, path: c.path, geo: c.geo });
      }
    };
  });
  menu.querySelectorAll(".relsel").forEach((sel) => {
    sel.onclick = (ev) => ev.stopPropagation();     // 행 클릭(이동)과 분리
    sel.onchange = async (ev) => {
      ev.stopPropagation();
      const r = g[+sel.dataset.r];
      await fetch("/v1/rag/links/rel", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ src_doc: r.src_doc, src: r.src_id,
                               dst_doc: r.dst_doc || "", dst: r.dst_id,
                               rel: sel.value, surface: r.surface }),
      });
      menu.classList.add("hidden");
      load();                                       // 색인이 파일 변경을 보고 다시 선다
    };
  });
}

/* 링크 따라가기 — 출발지를 궤적에 남기고 도착지로 뛴다. 출발지가 있어야
 * 궤적이 "어디서 왔나"에 답한다. */
function follow(g, dst) {
  trailPush({ tab: "doc", doc: S.docShown, geo: g[0].geo,
              label: lgLabel(g[0].src_path || "") || short(S.name[S.docShown] || ""),
              title: `${S.name[S.docShown] || ""} ▸ ${g[0].src_path || ""}` });
  jumpTo(dst.doc, dst.geo,
         { label: lgLabel(dst.path || "") || short(dst.name || ""),
           title: `${dst.name || ""} ▸ ${dst.path || ""}` });
}

function jumpTo(dstDoc, geo, meta) {
  const label = (meta && meta.label) || "";
  trailPush({ tab: "doc", doc: dstDoc, geo,
              label: label || short(S.name[dstDoc] || dstDoc),
              title: (meta && meta.title) || "" });
  const go = () => {
    const pg = document.querySelector(`.pg[data-page="${(geo && geo.page) || 1}"]`);
    if (!pg) return;
    // 도착 표시는 다음 이동까지 남는다 — 깜빡이고 사라지면 "어디였지"가 된다
    document.querySelectorAll("#pages .flash").forEach((f) => f.remove());
    const f = document.createElement("div");
    f.className = "flash";
    const r = (geo && geo.rect) || { x: 0.04, y: 0.02, w: 0.92, h: 0.04 };
    f.style.cssText = `left:${r.x * 100}%;top:${r.y * 100}%;`
      + `width:${r.w * 100}%;height:${r.h * 100}%`;
    if (label) f.innerHTML = `<span class="flashtag">▸ ${esc(label)}</span>`;
    pg.appendChild(f);
    // lazy 이미지가 아직 안 떴으면 페이지 높이가 잡히기 전이다 — 뜬 뒤에 스크롤
    const img = pg.querySelector("img");
    const scroll = () => f.scrollIntoView({ behavior: "smooth", block: "center" });
    if (img && !img.complete) {
      img.loading = "eager";
      img.addEventListener("load", scroll, { once: true });
    } else scroll();
  };
  if (S.docShown !== dstDoc) {
    S.doc = dstDoc;
    renderDocs(); renderDoc();
    setTimeout(go, 80);                    // 페이지 DOM 이 선 뒤에 스크롤
  } else go();
}

/* ---------------------------------------------------------------- 이동 궤적
 * 타고 다닌 링크를 사슬로 남긴다 — A → B → C, 맨 끝이 지금 자리다. 칩을
 * 누르면 그리로 돌아가고 **그 뒤는 잘린다** — 되돌아가 다른 길을 타면
 * 앞길은 없던 일이다(브라우저 히스토리와 같은 규율). */
S.trail = [];
S.trailNav = false;                        // 궤적으로 이동 중 — 다시 쌓지 않는다
const geoKey = (g) => (g && g.rect ? `${g.page}:${g.rect.x}:${g.rect.y}`
                                   : `${(g && g.page) || ""}`);

function trailPush(e) {
  if (S.trailNav) return;
  const last = S.trail[S.trail.length - 1];
  if (last && last.tab === e.tab && last.doc === e.doc && last.node === e.node
      && geoKey(last.geo) === geoKey(e.geo)) return;
  S.trail.push(e);
  if (S.trail.length > 40) S.trail.shift();
  renderTrail();
}

function renderTrail() {
  const bar = $("trail");
  if (!S.trail.length) { bar.classList.add("hidden"); return; }
  bar.classList.remove("hidden");
  $("trailBack").disabled = S.trail.length < 2;
  $("trailChips").innerHTML = S.trail.map((e, i) =>
    `${i ? '<span class="tarr">→</span>' : ""}
     <span class="tchip${i === S.trail.length - 1 ? " cur" : ""}" data-i="${i}"
           title="${esc(e.title || e.label)}">
       <span class="dot" style="background:${S.color[e.doc] || "var(--dim)"}"></span>
       ${esc(e.label)}</span>`).join("");
  $("trailChips").querySelectorAll(".tchip").forEach((el) => {
    el.onclick = () => trailGo(+el.dataset.i);
  });
  $("trailChips").scrollLeft = $("trailChips").scrollWidth;
}

function trailGo(i) {
  const e = S.trail[i];
  if (!e) return;
  S.trail = S.trail.slice(0, i + 1);       // 뒤로 가면 그 앞은 날린다
  renderTrail();
  S.trailNav = true;
  try {
    if (e.tab === "graph") {
      if (S.tab !== "graph") setTab("graph");
      const id = `${e.doc}:${e.node}`;
      if (LG.byId.has(id)) selectNode(id, true);
      else loadSection({ doc: e.doc, node: e.node });
    } else {
      if (S.tab !== "doc") setTab("doc");
      jumpTo(e.doc, e.geo, e);
    }
  } finally { S.trailNav = false; }
}

const hit = (s) => !S.q || (s || "").replace(/\s/g, "").includes(S.q);
const short = (n) => (n || "").replace(/\.pdf$/i, "");
const clip = (s, n) => (s.length > n ? s.slice(0, n) + "…" : s);

function renderDocs() {
  $("docs").innerHTML = S.data.docs.map((d) => `
    <div class="doc ${S.doc === d.doc_id ? "on" : ""}" data-id="${esc(d.doc_id)}">
      <span class="dot" style="background:${S.color[d.doc_id]}"></span>
      <span class="name" title="${esc(d.doc)}">${esc(short(d.doc))}</span>
      <span class="pill">안 ${d.n_in}</span>
    </div>`).join("");
  $("docs").querySelectorAll(".doc").forEach((el) => {
    el.onclick = () => { S.doc = S.doc === el.dataset.id ? null : el.dataset.id; render(); };
  });
}

/* 문서 지도 — 왼쪽 이름 열(~158px)과 오른쪽 화살표 레인(196px~)을 가른다.
 * 라벨은 12자에서 접고 전체 이름은 hover(title)로 준다 — 겹치지 않는 것이
 * 다 보이는 것보다 먼저다. */
function renderMap() {
  const docs = S.data.docs;
  const ROW = 32, W = 312, LANE = 196, H = docs.length * ROW + 18;
  const y = (i) => 22 + i * ROW;
  const at = Object.fromEntries(docs.map((d, i) => [d.doc_id, i]));
  const agg = new Map();                       // (src|dst) -> n
  for (const e of S.data.cross) {
    if (e.src_doc === e.dst_doc) continue;     // 제 이름 부른 참조 — 지도에선 생략
    const k = `${e.src_doc}|${e.dst_doc}`;
    agg.set(k, (agg.get(k) || 0) + 1);
  }
  const arcs = [...agg].map(([k, n]) => {
    const [a, b] = k.split("|");
    const ya = y(at[a]), yb = y(at[b]);
    const bow = Math.min(84, 28 + Math.abs(ya - yb) * 0.2);
    return `<path class="arc" stroke="${S.color[a]}" marker-end="url(#arr)"
        d="M ${LANE},${ya} C ${LANE + bow},${ya} ${LANE + bow},${yb} ${LANE + 4},${yb}">
        <title>${esc(short(S.name[a]))} → ${esc(short(S.name[b]))} — ${n}건</title></path>
      <text class="cnt" x="${LANE + bow * 0.72}" y="${(ya + yb) / 2 + 3}">${n}</text>`;
  }).join("");
  $("map").innerHTML = `<div class="cap">문서 지도 — 화살표는 문서 사이 참조, 숫자는 간선 수</div>
  <svg viewBox="0 0 ${W} ${H}" style="height:${H + 8}px">
    <defs><marker id="arr" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
      <path d="M0,0 L7,3.5 L0,7" fill="none" stroke="context-stroke" stroke-width="1.3"/>
    </marker></defs>
    ${docs.map((d, i) => `<line class="rail" x1="164" y1="${y(i)}" x2="${LANE - 4}" y2="${y(i)}"/>`).join("")}
    ${arcs}
    ${docs.map((d, i) => `<g>
      <title>${esc(d.doc)}</title>
      <circle cx="14" cy="${y(i)}" r="5" fill="${S.color[d.doc_id]}"/>
      <text class="lbl" x="26" y="${y(i) + 4}">${esc(clip(short(d.doc), 12))}</text></g>`).join("")}
  </svg>`;
}

const goSrc = (doc, e) => `/structure/?doc=${encodeURIComponent(doc)}`
  + (e.block != null ? `&block=${e.block}` : `&node=${e.src}`);
const goDst = (doc, e) => `/structure/?doc=${encodeURIComponent(doc)}&node=${e.dst}`;

/* 간선 한쪽 끝 — 말줄임 + title. withDoc 이면 문서명을 앞에 단다. */
const end = (docId, docName, path, withDoc) => `
  <span class="end" title="${esc(docName)} ▸ ${esc(path)}">
    <span class="dot" style="background:${S.color[docId]}"></span>
    ${withDoc ? `<span class="dn">${esc(short(docName))}</span>` : ""}
    <span class="p">${esc(path)}</span>
  </span>`;

/* via 칩의 설명 — 형태마다 신뢰가 다르니 검수 순서도 다르다 */
const VIA_TIP = {
  "추정":   "이름 없이 부른 참조(법·동법…) — 그 조를 가진 문서가 하나뿐이라 그리 이은 것. 문서가 늘면 틀릴 수 있어 가장 먼저 훑을 대상",
  "이름대조": "문서 이름을 불러 결정론으로 확정 — 신뢰 높음",
  "LLM":     "LLM 판정으로 links.json 에 고정된 것",
  "사람":    "사람이 보류에서 직접 고른 것",
  "교정":    "백로그 재지정으로 도착이 옮겨 앉은 것",
  "규칙":    "일반 규칙(귀납층)이 착지를 옮긴 것 — pill 에 규칙 id. 끊거나 재교정하면 그 규칙의 반례로 원장에 기록된다",
  "저장":    "links.json 에 저장된 것 (경위 표기 없음)",
};
const PAGE = 300;          // 한 번에 세우는 행 수 — 4천 행을 다 세우면 화면이 죽는다

function renderCross() {
  const all = S.data.cross.filter((e) =>
    (!S.doc || e.src_doc === S.doc || e.dst_doc === S.doc)
    && (hit(e.src_path) || hit(e.dst_path) || hit(e.surface)));

  // 연결 형태별 분리 — 칩에 수가 실리고, 고르면 그 형태만 남는다
  const counts = {};
  all.forEach((e) => { const v = e.via || "저장"; counts[v] = (counts[v] || 0) + 1; });
  const vias = ["추정", "이름대조", "LLM", "사람", "교정", "규칙", "저장"].filter((v) => counts[v]);
  if (S.via && !counts[S.via]) S.via = "";          // 필터 결과에 그 형태가 없어졌다
  $("viaSeg").innerHTML =
    `<button data-v="" class="${!S.via ? "on" : ""}">전체 ${all.length}</button>`
    + vias.map((v) => `<button data-v="${esc(v)}" class="${S.via === v ? "on" : ""}"
        title="${esc(VIA_TIP[v] || "")}">${esc(v)} ${counts[v]}</button>`).join("");
  $("viaSeg").querySelectorAll("button").forEach((b) => {
    b.onclick = () => { S.via = b.dataset.v; S.crossCap = PAGE; renderCross(); };
  });

  const rows = S.via ? all.filter((e) => (e.via || "저장") === S.via) : all;
  // 필터 맥락(문서·검색·형태)이 바뀌면 상한을 처음으로 되돌린다
  const sig = `${S.doc}|${S.q}|${S.via}`;
  if (S.crossSig !== sig) { S.crossSig = sig; S.crossCap = PAGE; }
  $("crossTitle").textContent = `문서 사이 참조 (${rows.length})`;
  // 모든 간선에 **끊기**가 있다 — 자동으로 선 간선이 대부분이므로 사람 몫은
  // 데이터 검수(틀린 것 발견 → 끊기)다. 끊기는 억제 규칙(edge_rules.json)에
  // 영구 기록돼 목록과 질의 확장 양쪽에서 빠진다 — 다시 서지 않는다.
  // 판정으로 저장된 간선(LLM·사람)에는 되돌리기(해제 — 보류로 복귀)도 남긴다.
  // links.json 에 실재하는 형태만 — 교정·규칙은 색인이 세운 오버레이라 해제할
  // 파일 행이 없다(해제 대신 끊기·재교정이 그들의 반례 경로다).
  const saved = (e) => ["LLM", "사람", "저장"].includes(e.via || "저장");
  const shown = rows.slice(0, S.crossCap);
  $("cross").innerHTML = shown.map((e, i) => `
    <div class="edge">
      <div class="line open" data-i="${i}"
           title="클릭하면 양쪽 본문이 펼쳐집니다 — 왜 이어졌는지 그 자리에서 확인">
        ${end(e.src_doc, e.src_doc_name, e.src_path, true)}
        <span class="chip">${esc(e.surface)}</span>
        ${end(e.dst_doc, e.dst_doc_name, e.dst_path, true)}
        <span class="pill ${VIA_CLS[e.via] || ""}" title="${esc(e.rule || VIA_TIP[e.via] || "")}">${esc(e.via || "저장")}${e.rule ? " " + esc(e.rule) : ""}</span>
      </div>
      <div class="edgeview hidden"></div>
      <div class="links">
        <a class="go" href="${goSrc(e.src_doc, e)}">참조가 쓰인 자리 →</a>
        <a class="go" href="${goDst(e.dst_doc, e)}">가리키는 구역 →</a>
        <button class="cut" data-i="${i}"
            title="이 연결은 틀렸다 — 억제 규칙으로 기록되고 목록·질의 확장에서 빠집니다">✂ 끊기</button>
        ${saved(e) ? `<button class="unlink" data-i="${i}"
            title="판정만 지운다 — 보류로 되돌아간다 (틀렸다는 기록은 안 남음)">해제</button>` : ""}
      </div>
    </div>`).join("") || "<p class='empty'>문서 사이 확정 간선이 없습니다.</p>";

  // 행 클릭 = 본문 펼침 — 경로만 보고는 "왜 이어졌나"를 판단할 수 없다.
  // 왼쪽엔 참조가 쓰인 자리(표면이 형광), 오른쪽엔 가리키는 구역 본문이 서고,
  // 둘을 잇는 선 위에 끊기가 있다 — 읽고 그 자리에서 자른다.
  $("cross").querySelectorAll(".line.open").forEach((el) => {
    el.onclick = () => toggleEdgeView(el, shown[+el.dataset.i]);
  });
  if (rows.length > shown.length) {
    const more = document.createElement("button");
    more.className = "more";
    more.textContent = `+ ${Math.min(PAGE, rows.length - shown.length)}개 더 보기 (남은 ${rows.length - shown.length})`;
    more.onclick = () => { S.crossCap += PAGE; renderCross(); };
    $("cross").appendChild(more);
  }

  // 끊기 — 백로그 승인과 같은 자리(억제 규칙)에 남는다. 사전 검수와 사후
  // 판정이 한 장부를 쓴다.
  $("cross").querySelectorAll(".cut").forEach((el) => {
    el.onclick = () => cutEdge(shown[+el.dataset.i], el);
  });

  $("cross").querySelectorAll(".unlink").forEach((el) => {
    el.onclick = async () => {
      const e = shown[+el.dataset.i];
      el.disabled = true;
      sessionStorage.removeItem("ui-queue-counts");   // 상단바 배지 갱신
      const r = await fetch(`${API}/remove`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ src_doc: e.src_doc, src: e.src,
                               dst_doc: e.dst_doc, dst: e.dst }) });
      if (!r.ok) { banner((await r.json()).detail || "실패"); el.disabled = false; return; }
      banner("간선을 해제했습니다 — 대용어였다면 보류 목록으로 돌아갑니다");
      load();
    };
  });
}

/* 끊기 — 목록 행의 ✂ 와 펼침 뷰의 연결선 버튼이 같은 길을 쓴다 */
async function cutEdge(e, btn) {
  btn.disabled = true;
  sessionStorage.removeItem("ui-queue-counts");   // 상단바 배지 갱신
  const r = await fetch("/v1/rag/verdicts/resolve", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ src_doc: e.src_doc, src: e.src,
                           dst_doc: e.dst_doc, dst: e.dst,
                           src_path: e.src_path || "", dst_path: e.dst_path || "",
                           action: "승인",
                           note: "참조 화면 데이터 검수에서 끊음" }) });
  if (!r.ok) { banner((await r.json()).detail || "실패"); btn.disabled = false; return; }
  banner("끊었습니다 — 목록과 질의 확장에서 빠집니다 (억제 규칙에 기록)");
  load();
}

/* ---------------------------------------------------- 간선 본문 펼침 뷰
 * 경로는 좌표일 뿐이다 — 판단은 본문으로 한다. 행을 누르면 그 자리에서
 * 양쪽 구역의 원문이 펼쳐지고, 참조 표면(제N조)이 형광으로 선다. */
const _secCache = {};
async function fetchSection(doc, node) {
  const k = `${doc}:${node}`;
  if (!_secCache[k]) {
    const r = await fetch(`/v1/rag/section?doc_id=${encodeURIComponent(doc)}&node=${node}`);
    _secCache[k] = r.ok ? await r.json() : { text: "(본문을 불러오지 못했습니다)" };
  }
  return _secCache[k];
}

/* 계층 결손 탐지 — 도착 경로에 표면(제22조)이 안 보이면, 그 마디가 구조에
 * 없어서 참조가 조상 구역에 앉았다는 신호다. 연결이 아니라 계층의 문제 —
 * 구조 검수로 보내는 통로를 그 자리에 띄운다. */
function edgeMisfit(e) {
  const flat = (s) => (s || "").replace(/\s+/g, "");
  const key = flat(e.surface).match(/제\d+조(의\d+)?/)?.[0];
  return key ? !flat(e.dst_path).includes(key) : false;
}

/* 본문 렌더 — 구조화 outline 을 기본으로 쓴다. 항(①)·호(1.)가 마디로 서
 * 있으면 들여쓰기가 계층 그대로고, `▸ ` 줄은 우리 해석이 세운 마디 제목이라
 * 본문과 눈으로 갈라 보이게 칠한다. 표면(제N조)은 형광. */
function bodyHtml(sec, surface) {
  let h = esc(sec.outline || sec.text || "");
  const s = esc(surface || "");
  if (s) h = h.split(s).join(`<mark class="hl">${s}</mark>`);
  // 마디 줄(들여쓰기 + ▸ 라벨)만 스타일 — esc 이후라 태그 주입 걱정이 없다
  h = h.replace(/^([ ]*)▸ (.*)$/gm,
    (_, ind, label) => `${ind}<span class="olh">▸ ${label}</span>`);
  // 승인 용어 — 초록 밑줄로 은은하게. 누르면 용어집의 그 용어로 간다
  return uiMarkTerms(h, sec.terms);
}

async function toggleEdgeView(lineEl, e) {
  const box = lineEl.parentElement.querySelector(".edgeview");
  if (!box.classList.contains("hidden")) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  box.innerHTML = "<p class='hint'>본문 불러오는 중…</p>";
  const [src, dst] = await Promise.all([
    fetchSection(e.src_doc, e.src), fetchSection(e.dst_doc, e.dst)]);
  box.innerHTML = `
    <div class="evpane src">
      <div class="evhead">참조가 쓰인 자리 —
        <b>${esc(short(e.src_doc_name))} ▸ ${esc(e.src_path)}</b></div>
      <div class="evbody">${bodyHtml(src, e.surface)}</div>
    </div>
    <div class="evlink">
      <span class="evwire"></span>
      <span class="evsurf">${esc(e.surface)}</span>
      <button class="evcut" title="이 연결은 틀렸다 — 억제 규칙으로 기록되고 목록·질의 확장에서 빠집니다">✂ 끊기</button>
      <span class="evwire arrow"></span>
    </div>
    <div class="evpane dst">
      <div class="evhead">가리키는 구역 —
        <b class="hl">${esc(short(e.dst_doc_name))} ▸ ${esc(e.dst_path)}</b></div>
      ${edgeMisfit(e) ? `<div class="evwarn">⚠ 도착 경로에 <b>${esc(e.surface)}</b>
        마디가 없습니다 — 대상 문서 구조에서 ${esc(e.surface)}가 계층으로 서지
        않아, 참조가 그 위 구역에 앉았습니다. <b>고칠 곳은 참조가 아니라
        계층입니다</b> — 구조 검수에서 마디를 세우고 다시 해석하면 이 참조는
        자동으로 옮겨 앉습니다.
        <a class="qlink" href="/structure/?doc=${encodeURIComponent(e.dst_doc)}&node=${e.dst}">구조 검수에서 열기 →</a></div>` : ""}
      <div class="evbody">${bodyHtml(dst, "")}</div>
    </div>`;
  box.querySelector(".evcut").onclick = (ev) => {
    ev.stopPropagation();
    cutEdge(e, ev.target);
  };
}

function renderPending() {
  const rows = S.data.pending.filter((p) =>
    (!S.doc || p.src_doc === S.doc)
    && (hit(p.surface) || hit(p.context) || hit(p.hint)));
  $("pendTitle").textContent = `보류 — 아직 못 정한 참조 (${rows.length})`;
  $("settleBtn").disabled = !S.data.pending.length;
  const psig = `${S.doc}|${S.q}`;
  if (S.pendSig !== psig) { S.pendSig = psig; S.pendCap = PAGE; }
  const shown = rows.slice(0, S.pendCap || (S.pendCap = PAGE));
  $("pending").innerHTML = shown.map((p, i) => `
    <div class="pend">
      <div class="head">
        <span class="dot" style="background:${S.color[p.src_doc]}"></span>
        <b title="${esc(p.src_doc_name)} ▸ ${esc(p.src_path)}">
          ${esc(short(p.src_doc_name))} ▸ ${esc(p.src_path)}</b>
        <span class="chip">${esc(p.surface)}</span>
        ${p.hint ? `<span class="pill warn">단서: ${esc(p.hint)}</span>` : ""}
      </div>
      <p class="quote">${esc(p.context).replace(esc(p.surface), `<b>${esc(p.surface)}</b>`)}</p>
      ${p.candidates.map((c) => `
        <div class="cand">
          <button class="pick" data-p="${i}"
                  data-doc="${esc(c.doc_id)}" data-node="${c.node}">이 구역으로 잇기</button>
          <span class="dot" style="background:${S.color[c.doc_id]}"></span>
          <span class="p" title="${esc(c.doc)} ▸ ${esc(c.path)}">
            ${esc(short(c.doc))} ▸ ${esc(c.path)}</span>
          <a class="go" href="/structure/?doc=${encodeURIComponent(c.doc_id)}&node=${c.node}">보기 →</a>
        </div>`).join("")}
    </div>`).join("") || "<p class='empty'>보류가 없습니다 — 전부 확정됐거나 참조가 없습니다.</p>";
  if (rows.length > shown.length) {
    const more = document.createElement("button");
    more.className = "more";
    more.textContent = `+ ${Math.min(PAGE, rows.length - shown.length)}개 더 보기 (남은 ${rows.length - shown.length})`;
    more.onclick = () => { S.pendCap += PAGE; renderPending(); };
    $("pending").appendChild(more);
  }

  $("pending").querySelectorAll(".pick").forEach((el) => {
    el.onclick = async () => {
      const p = shown[+el.dataset.p];
      el.disabled = true;
      sessionStorage.removeItem("ui-queue-counts");   // 상단바 배지 갱신
  const r = await fetch(`${API}/pick`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          src_doc: p.src_doc, src: p.src,
          dst_doc: el.dataset.doc, dst: +el.dataset.node,
          surface: p.surface, hint: p.hint, key: p.key, block: p.block }) });
      if (!r.ok) { banner((await r.json()).detail || "실패"); el.disabled = false; return; }
      load();                                  // links.json 이 바뀌면 색인도 다시 선다
    };
  });
}

function renderInDoc() {
  const ids = S.doc ? [S.doc] : Object.keys(S.data.in_doc);
  let total = 0;
  const parts = ids.map((d) => {
    const rows = (S.data.in_doc[d] || []).filter((e) =>
      hit(e.src_path) || hit(e.dst_path) || hit(e.surface));
    total += rows.length;
    if (!rows.length) return "";
    // 문서당 상한 — 전체 7,900행을 다 세우면 화면이 죽는다. 넘치면 검색·문서
    // 선택으로 좁히라고 말한다 (여긴 결정론 전부라 훑기보다 찾기가 맞다).
    const capped = rows.slice(0, 100);
    const rest = rows.length - capped.length;
    return `<div class="docgroup">
        <span class="dot" style="background:${S.color[d]}"></span>
        ${esc(short(S.name[d]))} <span class="pill">${rows.length}</span>
        ${rest > 0 ? `<span class="sub">앞 100개만 — 나머지 ${rest}개는 검색이나 왼쪽 문서 선택으로 좁혀 보세요</span>` : ""}</div>`
      + capped.map((e) => `
      <div class="edge">
        <div class="line nopill">
          ${end(d, S.name[d], e.src_path, false)}
          <span class="chip">${esc(e.surface)}</span>
          ${end(d, S.name[d], e.dst_path, false)}
        </div>
        <div class="links">
          <a class="go" href="${goSrc(d, e)}">참조가 쓰인 자리 →</a>
          <a class="go" href="${goDst(d, e)}">가리키는 구역 →</a>
        </div>
      </div>`).join("");
  });
  $("inTitle").textContent = `문서 안 참조 (${total})`;
  $("indoc").innerHTML = parts.join("")
    || "<p class='empty'>일치하는 간선이 없습니다.</p>";
}

function banner(msg) {
  const b = $("banner");
  b.textContent = msg;
  b.classList.remove("hidden");
  setTimeout(() => b.classList.add("hidden"), 5000);
}

$("settleBtn").onclick = async () => {
  $("settleBtn").disabled = true;
  $("settleMsg").textContent = "판정 중…";
  sessionStorage.removeItem("ui-queue-counts");   // 상단바 배지 갱신
  const r = await fetch(`${API}/settle`, { method: "POST" });
  const j = await r.json();
  if (!r.ok) { $("settleMsg").textContent = j.detail || "실패"; $("settleBtn").disabled = false; return; }
  $("settleMsg").textContent =
    `보류 ${j.pending}건 중 ${j.settled}건 확정 — 남은 것은 확신이 없어 보류입니다.`
    + ` 이제 이 잔여만 사람 몫입니다 (원문 보고 후보에서 고르세요)`;
  load();
};

$("trailBack").onclick = () => { if (S.trail.length > 1) trailGo(S.trail.length - 2); };
$("q").oninput = (e) => { S.q = e.target.value.trim().replace(/\s/g, ""); render(); };
$("tabDoc").onclick = () => setTab("doc");
$("tabList").onclick = () => setTab("list");
$("tabGraph").onclick = () => setTab("graph");
document.addEventListener("click", (e) => {
  if (!e.target.closest("#refmenu") && !e.target.closest(".refbox"))
    $("refmenu").classList.add("hidden");
});
S.tab = "doc";                           // 첫 화면 — 문서 그대로, 참조 자리에 링크
initLinkGraph();
load();
