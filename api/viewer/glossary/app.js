/* 용어집 — 왼쪽에서 **문서를 먼저** 고르고(폴더 단위·전체 선택), 오른쪽은
 * 그 선택 안을 그린다.
 *
 *   고른 용어 없음 → 용어 × 문서 매트릭스 (행=용어, 열=선택한 문서)
 *   고른 용어 있음 → 그 용어의 출현 전부 — 문서별 그룹, 지면 순서,
 *                    출처 배지(제목/본문/표/그림/문서명/폴더), 원문 스니펫, 구조 뷰어 링크
 *
 * 네트워크 그래프는 걷어냈다(2026-08, 사용자 결정) — 관계는 '관계' 탭이
 * 후보(계층·공기·문서 참조)로 보여 준다. 대신 어휘를 **제목(특화) / 본문만
 * (범용)** 으로 가르는 필터를 뒀다 — 구역 제목·정의 자리에 오른 말이 곧
 * 문서가 다루는 특화 어휘다.
 *
 * 같은 용어를 묶는 규칙(공백 지운 정규형)은 서버가 정한다(api/routers/glossary.py).
 * 화면은 그 결과를 그린다 — 화면마다 따로 묶으면 규칙이 갈린다. */
const API = "/v1/glossary";
const S = { data: null, sel: null, selDoc: null, selDocs: null,
            filter: "all", level: 0, q: "", docColor: {}, review: false };
const $ = (id) => document.getElementById(id);
const esc = (s) => (s || "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sh = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
const DOC_COLORS = ["#60a5fa", "#4ade80", "#fbbf24", "#f472b6", "#a78bfa", "#22d3ee"];
const VIA_COLOR = { "제목": "#4ade80", "본문": "#60a5fa", "표": "#fbbf24", "그림": "#f472b6",
                    "문서명": "#a78bfa", "폴더": "#22d3ee" };
const MAX_GROUP = 15;          // 문서 하나에 이보다 출현이 많으면 접는다

async function load() {
  const r = await fetch(API);
  S.data = await r.json();
  S.docColor = {};
  docNames().forEach((d, i) => (S.docColor[d] = DOC_COLORS[i % DOC_COLORS.length]));
  if (S.selDocs === null) S.selDocs = new Set(docNames());   // 처음엔 전부
  const m = location.hash.match(/t=([^&]+)/);
  if (m) S.sel = decodeURIComponent(m[1]);
  if (S.sel && !S.data.terms.some((t) => t.key === S.sel)) S.sel = null;
  render();
}

/* 문서 이름 — 목록에 없는 문서가 출현에만 있을 수 있다(지운 문서의 사용자 용어). */
function docNames() {
  const names = S.data.docs.map((d) => d.name);
  for (const t of S.data.terms)
    for (const o of t.occurrences)
      if (o.doc && !names.includes(o.doc)) names.push(o.doc);
  return names;
}

/* 폴더 → 문서들. 폴더 없는 문서는 마지막 그룹(라벨 null)으로. */
function folderGroups() {
  const meta = Object.fromEntries(S.data.docs.map((d) => [d.name, d]));
  const groups = new Map();
  for (const d of docNames()) {
    const f = (meta[d] && meta[d].folder) || null;
    if (!groups.has(f)) groups.set(f, []);
    groups.get(f).push(d);
  }
  const named = [...groups.entries()].filter(([f]) => f !== null);
  const rest = groups.get(null) ? [[null, groups.get(null)]] : [];
  return [...named, ...rest];
}

const docsIn = (r) => r.docs.filter((d) => S.selDocs.has(d));
const nIn = (r) => r.occurrences.reduce((a, o) => a + (S.selDocs.has(o.doc) ? 1 : 0), 0);
/* 제목(heading) 용어인가 — 이 말 **자체가** 어느 구역의 제목인가 (서버 판정).
 * 제목에 오른 말은 문서가 그 주제를 다룬다는 뜻(특화 어휘)이고, 본문에만
 * 나오는 말은 범용 어휘일 가능성이 크다. */
const isHeading = (r) => !!r.is_heading;

function rows() {
  let rs = S.data.terms.filter((r) => docsIn(r).length > 0);
  if (S.filter === "shared") rs = rs.filter((r) => docsIn(r).length > 1);
  if (S.filter === "user") rs = rs.filter((r) => r.user);
  if (S.filter === "heading") rs = rs.filter(isHeading);
  if (S.filter === "body") rs = rs.filter((r) => !isHeading(r));
  // 깊이 필터 — 제목 용어에만 뜻이 있다(레벨은 제목의 속성이므로).
  // L4+ 는 4 이상 전부: 깊은 세목은 수가 적어 묶는다.
  if (S.level)
    rs = rs.filter((r) => (r.heading_levels || []).some(
      (l) => (S.level === 4 ? l >= 4 : l === S.level)));
  if (S.q) {
    const n = S.q.replace(/\s/g, "");
    rs = rs.filter((r) => r.key.includes(n));
  }
  return rs;
}

function select(key, doc) {
  S.sel = key;
  S.selDoc = doc || null;
  history.replaceState(null, "",
    key ? `#t=${encodeURIComponent(key)}` : location.pathname);
  render();
}

function render() {
  const st = S.data.stats;
  $("summary").textContent =
    `용어 ${st.terms} · 출현 ${st.occurrences} · 문서 ${st.documents}`
    + ` · 문서를 잇는 용어 ${st.shared}`;
  renderDocs();
  renderList();
  renderMain();
}

/* ------------------------------------------------------ 왼쪽 · 문서 트리 */
function renderDocs() {
  const all = docNames();
  $("docCount").textContent = `${S.selDocs.size}/${all.length}`;
  const master = $("allDocs");
  master.checked = S.selDocs.size === all.length;
  master.indeterminate = S.selDocs.size > 0 && S.selDocs.size < all.length;

  const docRow = (d) => `
    <label class="docrow">
      <input type="checkbox" data-doc="${esc(d)}" ${S.selDocs.has(d) ? "checked" : ""}>
      <i style="background:${S.docColor[d] || "#888"}"></i>
      <span class="dn" title="${esc(d)}">${esc(d)}</span>
    </label>`;

  $("docTree").innerHTML = folderGroups().map(([f, ds]) => {
    if (f === null && !S.data.docs.some((d) => d.folder))
      return ds.map(docRow).join("");            // 폴더가 아예 없으면 평평하게
    const on = ds.filter((d) => S.selDocs.has(d)).length;
    return `<div class="fgroup">
      <label class="frow">
        <input type="checkbox" data-folder="${esc(f ?? "")}"
          ${on === ds.length ? "checked" : ""}>
        <span class="fname">${f === null ? "폴더 없음" : esc(f)}</span>
        <span class="sub">${on}/${ds.length}</span>
      </label>
      ${ds.map(docRow).join("")}
    </div>`;
  }).join("");

  $("docTree").querySelectorAll("[data-doc]").forEach((el) => {
    el.onchange = () => {
      el.checked ? S.selDocs.add(el.dataset.doc) : S.selDocs.delete(el.dataset.doc);
      render();
    };
  });
  $("docTree").querySelectorAll("[data-folder]").forEach((el) => {
    el.onchange = () => {
      const f = el.dataset.folder || null;
      const ds = (folderGroups().find(([g]) => g === f) || [null, []])[1];
      ds.forEach((d) => (el.checked ? S.selDocs.add(d) : S.selDocs.delete(d)));
      render();
    };
  });
}

$("allDocs").onchange = (e) => {
  S.selDocs = e.target.checked ? new Set(docNames()) : new Set();
  render();
};

/* 생애주기 뱃지 — 어디서 태어났고(source) 살아있는지(status). 잠정 용어는
 * 검수를 기다리는 것이라 화면에서 구별돼야 한다. */
function lifePills(r) {
  const src = { "수기": ["add", "추가"], "tier1": ["t1", "정의"],
                "통계": ["st", "통계"], "질의루프": ["lp", "질의"] }[r.source];
  let out = src ? `<span class="pill ${src[0]}" title="출처: ${esc(r.source)}">${src[1]}</span>` : "";
  if (r.status === "잠정")
    out += `<span class="pill prov" title="잠정 — 검수·실적을 기다린다">잠정</span>`;
  if (r.status === "tombstone")
    out += `<span class="pill dead" title="강등됨 — 색인에서 빠져 있다">강등</span>`;
  return out;
}

/* ------------------------------------------------------ 왼쪽 · 용어 목록 */
function renderList() {
  const box = $("terms");
  box.innerHTML = rows().map((r) => `
    <div class="term ${S.sel === r.key ? "on" : ""} ${docsIn(r).length > 1 ? "shared" : ""}"
         data-key="${esc(r.key)}">
      <span class="name">${esc(r.term)}</span>
      <span class="dots">${docsIn(r).map((d) =>
        `<i title="${esc(d)}" style="background:${S.docColor[d] || "#888"}"></i>`).join("")}</span>
      <span class="pill">${nIn(r)}회</span>
      ${isHeading(r) ? `<span class="pill hd"
        title="그 말 자체가 구역 제목이다 — 깊이 ${(r.heading_levels || []).join("·") || "?"}"
        >제목${r.heading_levels?.length ? " L" + r.heading_levels.join("·") : ""}</span>` : ""}
      ${lifePills(r)}
    </div>`).join("")
    || `<p class='hint'>${S.selDocs.size ? "일치하는 용어가 없습니다." : "문서를 선택하세요."}</p>`;
  box.querySelectorAll(".term").forEach((el) => {
    el.onclick = () => select(S.sel === el.dataset.key ? null : el.dataset.key);
  });
}

/* ------------------------------------------------------------ 오른쪽 */
function renderMain() {
  if (S.review) { renderReview(); return; }
  if (S.relations) { renderRelations(); return; }
  $("main").innerHTML = S.sel ? detailHtml() : overviewHtml();
  bindMain();
}

/* ----------------------------------------------- 관계 (후보 — 보여주기) */
/* 타이핑된 관계는 아직 없다 — 컴파일이 모은 후보(계층·공기)를 문서 관계와
 * 함께 그대로 보여 준다. 사람이 눈으로 간접 추론하는 용도다. */
async function renderRelations() {
  const box = $("main");
  box.innerHTML = "<p class='hint'>관계 후보 불러오는 중…</p>";
  const d = await (await fetch(`${API}/relations`)).json();
  const back = `<div class="dhead"><button data-back-review>← 전체</button>
    <h2>용어 관계 (후보)</h2><span class="sub">${esc(d.note || "")}</span></div>`;
  const hier = (d.hierarchy || []).map((e) => `
    <div class="relrow"><b>${esc(e.child)}</b> <span class="sub">—is-a→</span>
      <b>${esc(e.parent)}</b> <span class="pill">${esc(e.evidence)}</span>
      <span class="sub">${(e.docs || []).map((x) => esc(x.doc)).join(" · ")}</span></div>`).join("");
  const proto = (d.proto_rel || []).map((r) => `
    <div class="relrow"><b>${esc(r.a)}</b> <span class="sub">↔</span> <b>${esc(r.b)}</b>
      <span class="pill">${r.n_cooccur}회·${r.n_docs}문서·G²${r.g2}</span>
      <span class="sub">${(r.top_patterns || []).map((p) => `"${esc(p.pattern)}"`).join(" / ")}</span>
      <span class="sub">${(r.docs || []).map(esc).join(" · ")}</span></div>`).join("");
  const links = (d.doc_links || []).map((l) => `
    <div class="relrow">${esc(l.src)} <span class="sub">→</span> ${esc(l.dst)}
      <span class="pill">참조 ${l.n}건</span></div>`).join("");
  box.innerHTML = back
    + `<section class="rvitem"><div class="rvhead"><b>문서 간 확정 참조</b>
        <span class="sub">links.json — 관계 추론의 바닥판</span></div>${links
        || "<span class='sub'>없음</span>"}</section>`
    + `<section class="rvitem"><div class="rvhead"><b>계층 후보 (is-a)</b>
        <span class="sub">어휘포함·나열 — 승인 전</span></div>${hier
        || "<span class='sub'>없음</span>"}</section>`
    + `<section class="rvitem"><div class="rvhead"><b>공기 관계 후보 (PROTO_REL candidate)</b>
        <span class="sub">타입 없음 — 연결 패턴이 단서</span></div>${proto
        || "<span class='sub'>없음</span>"}</section>`;
  box.querySelector("[data-back-review]").onclick = () => {
    S.relations = false; location.hash = ""; render();
  };
}

/* --------------------------------------------------- 검수 큐 (잠정 용어) */
/* 통계·전사가 낳은 잠정 용어를 근거와 함께 보여 주고, 사람이 승인(활성)
 * 또는 반려(tombstone)한다 — 등재의 문(게이트)은 하나지만 확정은 사람이다. */
async function renderReview() {
  const box = $("main");
  box.innerHTML = "<p class='hint'>검수 큐 불러오는 중…</p>";
  const d = await (await fetch(`${API}/review`)).json();
  $("reviewN").textContent = d.total || "";
  if (!d.queue.length) {
    box.innerHTML = `<div class="dhead"><button data-back-review>← 전체</button>
      <h2>검수 큐</h2></div><p class="hint">잠정 용어가 없습니다 — 깨끗합니다.</p>`;
  } else {
    box.innerHTML = `
      <div class="dhead"><button data-back-review>← 전체</button>
        <h2>검수 큐</h2><span class="pill prov">잠정 ${d.total}</span>
        <span class="sub">승인하면 검색 신뢰가 오르고, 반려하면 같은 후보가 다시 올라오지 않습니다</span></div>
      ${d.queue.map((r) => `
        <section class="rvitem" data-rv="${esc(r.key)}">
          <div class="rvhead">
            <b>${esc(r.term)}</b>
            <span class="pill ${r.source === "tier1" ? "t1" : "st"}">${esc(r.source || "")}</span>
            <span class="pill">${esc(r.confidence || "")}</span>
            <span class="sub">${r.n_occ}회 · ${r.docs.length}문서</span>
            <span class="grow"></span>
            <button class="rvok" data-approve="${esc(r.key)}">승인</button>
            <button class="rvno" data-reject="${esc(r.key)}">반려</button>
            <button data-inspect="${esc(r.key)}" title="출현 전부 보기">자세히</button>
          </div>
          ${r.surfaces.length > 1 ? `<div class="sub">표기: ${r.surfaces.map(esc).join(" · ")}</div>` : ""}
          ${r.note ? `<div class="sub">${esc(sh(r.note, 140))}</div>` : ""}
          ${r.snippets.map((s) => `<div class="rvsnip">${esc(s)}</div>`).join("")}
        </section>`).join("")}`;
  }
  box.querySelector("[data-back-review]").onclick = () => {
    S.review = false; location.hash = ""; render();
  };
  box.querySelectorAll("[data-approve]").forEach((b) => {
    b.onclick = () => reviewAct(b.dataset.approve, "활성");
  });
  box.querySelectorAll("[data-reject]").forEach((b) => {
    b.onclick = () => reviewAct(b.dataset.reject, "tombstone");
  });
  box.querySelectorAll("[data-inspect]").forEach((b) => {
    b.onclick = () => { S.review = false; select(b.dataset.inspect); };
  });
}

async function reviewAct(key, status) {
  await fetch(`${API}/terms/${encodeURIComponent(key)}`, {
    method: "PATCH", headers: { "content-type": "application/json" },
    body: JSON.stringify({ status }),
  });
  await load();                       // 목록·배지 갱신 (review 모드 유지)
}

function bindMain() {
  const box = $("main");
  box.querySelectorAll("[data-sel]").forEach((el) => {
    el.onclick = () => select(el.dataset.sel, el.dataset.doc || null);
  });
  box.querySelectorAll("[data-back]").forEach((el) => {
    el.onclick = () => select(null);
  });
  box.querySelectorAll("[data-solo]").forEach((el) => {
    el.onclick = () => { S.selDocs = new Set([el.dataset.solo]); render(); };
  });
  box.querySelectorAll("[data-docfilter]").forEach((el) => {
    el.onclick = () => {
      const d = el.dataset.docfilter;
      S.selDoc = S.selDoc === d ? null : (d || null);
      render();
    };
  });
  box.querySelectorAll("[data-del]").forEach((el) => {
    el.onclick = async (ev) => {
      ev.stopPropagation();
      const key = el.dataset.del;
      if (!confirm(`더한 용어 '${key}' 를 지웁니다. 제목에서 거둔 출현은 남습니다.`)) return;
      const r = await fetch(`${API}/terms/${encodeURIComponent(key)}`, { method: "DELETE" });
      if (!r.ok) { $("addMsg").textContent = (await r.json()).detail || "실패"; return; }
      if (S.sel === key) S.sel = null;
      load();
    };
  });

  // 출현 미리보기 — 창을 넘기지 않고 그 자리에서 페이지를 편다
  box.querySelectorAll(".pvable").forEach((el) => {
    el.querySelector(".l1").onclick = () => {
      const pv = el.querySelector(".pv");
      const nowHidden = pv.classList.toggle("hidden");
      el.querySelector(".go").textContent = nowHidden ? "보기 ▾" : "닫기 ▴";
      if (pv.dataset.loaded) return;
      pv.dataset.loaded = "1";
      const [id, page, bx, block] = el.dataset.pv.split("|");
      const hl = bx ? (() => {
        const [x, y, w, h] = bx.split(",").map(Number);
        return `<i class="hl" style="left:${x * 100}%;top:${y * 100}%;`
          + `width:${w * 100}%;height:${h * 100}%"></i>`;
      })() : "";
      pv.innerHTML = `<div class="pvbox">
          <img src="/v1/structure/${encodeURIComponent(id)}/page/${page}" alt="p${page}">${hl}
        </div>
        <a class="go" href="/structure/?doc=${encodeURIComponent(id)}`
        + `${block ? `&block=${block}` : ""}" target="_blank">구조 해석에서 열기 ↗</a>`;
      const img = pv.querySelector("img");
      img.onload = () => {                       // 형광 자리가 보이게 스크롤
        const mark = pv.querySelector(".hl");
        if (mark) pv.scrollTo({ top: Math.max(0, mark.offsetTop - 90) });
      };
    };
  });

}

/* --- 선택 전: 매트릭스 (네트워크는 2026-08 걷어냄 — 관계는 '관계' 탭으로) --- */
function overviewHtml() {
  const rs = rows();
  const docs = docNames().filter((d) => S.selDocs.has(d));

  // 제목(heading) 용어 = 어느 구역이 그 말을 **다루는** 특화 어휘.
  // 본문에만 나오는 말은 범용 어휘일 가능성이 크다 — 왼쪽 필터가 가른다.
  const heads = rs.filter(isHeading);
  const perLv = [1, 2, 3, 4].map((lv) => heads.filter((r) =>
    (r.heading_levels || []).some((l) => (lv === 4 ? l >= 4 : l === lv))).length);
  const net = `<h2>용어 구성 <span class="sub">제목(특화) ${heads.length}
    (L1 ${perLv[0]} · L2 ${perLv[1]} · L3 ${perLv[2]} · L4+ ${perLv[3]}) ·
    본문만(범용) ${rs.length - heads.length}</span></h2>`;

  // 용어 × 문서 매트릭스. 셀 진하기 = 출현 수.
  const counts = new Map();                     // "key|doc" → n
  let maxN = 1;
  for (const r of rs)
    for (const o of r.occurrences) {
      if (!S.selDocs.has(o.doc)) continue;
      const k = `${r.key}|${o.doc}`;
      const n = (counts.get(k) || 0) + 1;
      counts.set(k, n);
      if (n > maxN) maxN = n;
    }
  const cell = (r, d) => {
    const n = counts.get(`${r.key}|${d}`) || 0;
    if (!n) return "<td></td>";
    const p = 8 + Math.round(32 * Math.log(1 + n) / Math.log(1 + maxN));
    return `<td class="hit" data-sel="${esc(r.key)}" data-doc="${esc(d)}"
      title="${esc(r.term)} · ${esc(d)} · ${n}회"
      style="background:color-mix(in srgb, var(--accent) ${p}%, transparent)">${n}</td>`;
  };
  const matrix = !rs.length || !docs.length ? "" : `
    <h2>용어 × 문서 <span class="sub">${rs.length}개 — 셀을 누르면 그 문서의 출현으로</span></h2>
    <table class="mx">
      <thead><tr><th class="corner"></th>${docs.map((d) => `
        <th title="${esc(d)}"><i style="background:${S.docColor[d]}"></i>`
        + `${esc(sh(d, 24))}</th>`).join("")}</tr></thead>
      <tbody>${rs.map((r) => `
        <tr class="${docsIn(r).length > 1 ? "shared" : ""}">
          <th class="rowhead" data-sel="${esc(r.key)}">${esc(r.term)}</th>
          ${docs.map((d) => cell(r, d)).join("")}
        </tr>`).join("")}</tbody>
    </table>`;

  return net + matrix;
}

/* --- 선택 후: 용어 하나의 출현 전부 ----------------------------------- */
function detailHtml() {
  const r = S.data.terms.find((t) => t.key === S.sel);
  if (!r) return "<p class='hint'>용어를 찾을 수 없습니다.</p>";

  // 문서별로 묶고 지면 순서로 — "어디에 있는가"가 이 화면의 전부다.
  const groups = new Map();
  for (const o of r.occurrences) {
    if (!groups.has(o.doc)) groups.set(o.doc, []);
    groups.get(o.doc).push(o);
  }
  const order = docNames().filter((d) => groups.has(d));
  const byPage = (a, b) =>
    (a.page ?? 1e9) - (b.page ?? 1e9) || (a.block ?? 1e9) - (b.block ?? 1e9);

  const occHtml = (o) => {
    const via = o.via || "본문";
    // 어느 자리인가 — 조상 경로가 있으면 그것이 맥락이다. 같은 제목이 여러 구역에
    // 반복되는 문서에서 경로 없이 표기만 보이면 전부 중복처럼 보인다.
    const where = via === "문서명" ? "문서 이름" : via === "폴더" ? "폴더 이름"
      : via === "제목" ? ([o.path, o.surface].filter(Boolean).join(" ▸ ") || "구역 제목")
      : (o.path || o.section || o.surface || "");
    // 창을 넘기지 않는다 — 누르면 그 자리(페이지 + 형광)를 여기서 바로 편다.
    const canPv = o.doc_id && o.page != null;
    const pv = canPv ? ` data-pv="${esc(o.doc_id)}|${o.page}|`
      + `${o.bbox ? [o.bbox.x, o.bbox.y, o.bbox.w, o.bbox.h].join(",") : ""}|`
      + `${o.block != null ? o.block : ""}"` : "";
    return `<div class="occr${canPv ? " pvable" : ""}"${pv}>
      <div class="l1">
        <span class="via" style="color:${VIA_COLOR[via] || "var(--dim)"}">${esc(via)}</span>
        <span class="pg">${o.page != null ? `p${o.page}` : ""}</span>
        <span class="sec">${esc(where)}</span>
        <span class="grow"></span>${canPv ? `<span class="go">보기 ▾</span>` : ""}
      </div>
      ${o.text ? `<div class="quote">${esc(o.text.slice(0, 200))}</div>` : ""}
      ${canPv ? `<div class="pv hidden"></div>` : ""}
    </div>`;
  };

  const groupHtml = (d) => {
    if (S.selDoc && d !== S.selDoc) return "";
    const os = groups.get(d).slice().sort(byPage);
    const head = os.slice(0, MAX_GROUP).map(occHtml).join("");
    const rest = os.slice(MAX_GROUP);
    return `<section class="dgroup">
      <h3><i style="background:${S.docColor[d] || "#888"}"></i>${esc(d)}
        <span class="sub">${os.length}회</span></h3>
      ${head}
      ${rest.length ? `<details><summary class="sub">${rest.length}개 더 보기</summary>
        ${rest.map(occHtml).join("")}</details>` : ""}
    </section>`;
  };

  return `
    <div class="dhead">
      <button data-back>← 전체</button>
      <h2>${esc(r.term)}</h2>
      <span class="pill">${r.n}회</span>
      <span class="pill ${r.n_docs > 1 ? "ok" : ""}">${r.n_docs}문서</span>
      ${lifePills(r)}
      ${(r.hits || r.misses) ? `<span class="pill"
        title="용어 진입 실적 — 답변에 인용됨 ✓ / 무관 지문 ✗">실적 ${r.hits || 0}✓ ${r.misses || 0}✗</span>` : ""}
      ${r.user ? `<button class="tdel" data-del="${esc(r.key)}"
          title="${r.source === "수기" ? "더한 용어를 지운다 — 제목에서 거둔 출현은 남는다"
                 : "강등한다(tombstone) — 색인에서 빠지고 기록은 남는다"}">✕ ${
                 r.source === "수기" ? "지우기" : "강등"}</button>` : ""}
    </div>
    ${r.surfaces.length > 1 ? `<div class="sub surf">표기: ${r.surfaces.map(esc).join(" · ")}</div>` : ""}
    ${r.note ? `<div class="sub surf">메모: ${esc(r.note)}</div>` : ""}
    <div class="docfilter">
      <span class="chip ${!S.selDoc ? "on" : ""}" data-docfilter="">전체</span>
      ${order.map((d) => `<span class="chip ${S.selDoc === d ? "on" : ""}"
        data-docfilter="${esc(d)}"><i style="background:${S.docColor[d] || "#888"}"></i>`
        + `${esc(sh(d, 24))}</span>`).join("")}
    </div>
    ${order.map(groupHtml).join("") || "<p class='hint'>출현이 없습니다.</p>"}`;
}

/* ------------------------------------------------------------ 조작 */
$("q").oninput = (e) => { S.q = e.target.value.trim(); render(); };
$("filterSeg").querySelectorAll("button").forEach((el) => {
  el.onclick = () => {
    S.filter = el.dataset.f;
    $("filterSeg").querySelectorAll("button").forEach((b) =>
      b.classList.toggle("on", b === el));
    render();
  };
});
$("levelSeg").querySelectorAll("button").forEach((el) => {
  el.onclick = () => {
    S.level = Number(el.dataset.l);
    $("levelSeg").querySelectorAll("button").forEach((b) =>
      b.classList.toggle("on", b === el));
    render();
  };
});

/* 용어 더하기 — 줄바꿈으로 여러 개. 서버가 모든 문서에서 찾아 잇는다. */
$("addBtn").onclick = async () => {
  const list = ($("addText").value || "").split(/[\n,]/).map((x) => x.trim()).filter(Boolean);
  if (!list.length) return;
  $("addMsg").textContent = "찾는 중…";
  const r = await fetch(`${API}/terms`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ terms: list }) });
  const j = await r.json();
  if (!r.ok) { $("addMsg").textContent = j.detail || "실패"; return; }
  $("addMsg").textContent =
    `${(j.added || []).length}개 추가 · ${(j.updated || []).length}개 갱신 — `
    + Object.entries(j.found || {}).map(([k, v]) => `${k} ${v}회`).join(", ");
  load();
};

/* 다시 훑기 — 문서를 새로 올린 뒤 더한 용어들의 출현을 전부 갱신한다. */
$("rescanBtn").onclick = async () => {
  $("rescanBtn").disabled = true;
  $("addMsg").textContent = "다시 훑는 중…";
  const r = await fetch(`${API}/rescan`, { method: "POST" });
  const j = await r.json();
  $("rescanBtn").disabled = false;
  if (!r.ok) { $("addMsg").textContent = j.detail || "실패"; return; }
  $("addMsg").textContent = `용어 ${j.terms}개 · 출현 ${j.occurrences}회로 갱신`;
  load();
};

/* 검수 큐·관계 — 헤더 링크로 여닫는다. 잠정 용어 수 배지는 로드 때마다 갱신. */
$("reviewLink").onclick = (e) => {
  e.preventDefault();
  S.relations = false;
  S.review = !S.review;
  render();
};
$("relLink").onclick = (e) => {
  e.preventDefault();
  S.review = false;
  S.relations = !S.relations;
  render();
};
async function refreshReviewBadge() {
  try {
    const d = await (await fetch(`${API}/review?limit=1`)).json();
    $("reviewN").textContent = d.total ? String(d.total) : "";
  } catch { /* 배지는 장식이다 — 실패해도 화면은 산다 */ }
}
const _load0 = load;
load = async function () { await _load0(); refreshReviewBadge(); };

load();
