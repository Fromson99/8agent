/* 법령해석례 화면 — 위키(맥락)와 사례(원문) 두 판.
 *
 * 위키는 LLM 이 사례를 읽고 개념 단위로 컴파일한 층이고, 사례는 raw 층의
 * 열람이다. 두 판은 안건번호로 서로를 가리킨다: 위키 본문의 #case/<일련번호>
 * 링크가 사례 판을 열고, 사례 상세가 자기를 인용한 아티클을 되짚는다.
 * 검색은 부분일치뿐이다 — 의미 검색은 질의응답(/rag/)의 일이다.
 */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const S = {
  view: "wiki", articles: [], article: null,
  all: [], filters: { q: "", law: "", org: "", year: "" }, sel: null,
};

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error((await r.text()).slice(0, 300));
  return r.json();
}

/* ── 마크다운 소형 렌더러 — 위키는 우리가 쓰는 문서라 이 부분집합이면 된다.
 * 제목·구분선·인용·목록·문단 + 굵게·기울임·코드·링크. 원문은 전부 esc 를
 * 거친다. 링크 규약 (llm-wiki 정본 형태를 화면 이동으로 옮긴다):
 *   #case/<일련번호>            사례 판으로
 *   ../../raw/expc/…-<안건번호>.md  Raw 필드 — 안건번호로 사례를 찾아 사례 판으로
 *   <상대경로>.md               아티클 간 이동 — 현재 아티클의 주제 기준 해석 */
function inline(s) {
  return s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/\*([^*]+)\*/g, "<i>$1</i>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, t, href) => {
      if (href.startsWith("#case/")) return `<a href="${href}" class="caselink">${t}</a>`;
      let m;
      if (href.includes("raw/") && (m = href.match(/(\d{2}-\d{4})\.md$/))) {
        const c = S.all.find((x) => x.case_no === m[1]);
        return c ? `<a href="#case/${c.serial}" class="caselink">${t}</a>` : t;
      }
      if (href.endsWith(".md")) {
        const parts = (S.article || "").split("/").slice(0, -1);
        for (const seg of href.slice(0, -3).split("/")) {
          if (seg === "..") parts.pop();
          else if (seg !== ".") parts.push(seg);
        }
        return `<a href="#wiki/${parts.join("/")}" class="wikilink">${t}</a>`;
      }
      if (/^https?:/.test(href))
        return `<a href="${href}" target="_blank" rel="noopener">${t}</a>`;
      return t;
    });
}

function renderMd(md) {
  const out = [];
  let list = null;                       // "ul" | "ol" | null
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const raw of md.split("\n")) {
    const line = esc(raw.trimEnd());
    let m;
    if ((m = line.match(/^(#{1,4}) (.*)$/))) {
      closeList();
      const h = m[1].length + 1;         // 화면 제목이 h2 부터라 한 단 내린다
      out.push(`<h${h}>${inline(m[2])}</h${h}>`);
    } else if (/^---+$/.test(line)) {
      closeList(); out.push("<hr>");
    } else if ((m = line.match(/^&gt; ?(.*)$/))) {
      closeList(); out.push(`<blockquote>${inline(m[1])}</blockquote>`);
    } else if ((m = line.match(/^- (.*)$/))) {
      if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = line.match(/^\d+\. (.*)$/))) {
      if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else if (line === "") {
      closeList();
    } else {
      closeList(); out.push(`<p>${inline(line)}</p>`);
    }
  }
  closeList();
  return out.join("\n");
}

/* ── 위키 판 ─────────────────────────────────────────────── */
/* 생애 — 아티클의 4기준 보고서(성숙·안정·하중·부검)와 권고.
 * 권고 톤: 분쟁 중 = 사고(빨강), 재컴파일·재검증 = 대기(노랑), 유지 = 조용히.
 * 규칙 카드(공리 화면)의 게이지 문법을 그대로 쓴다 — 정본은 서버 보고서고
 * 게이지는 그 시각 표현일 뿐이다. */
const RECO_TONE = { "분쟁 중": "err", "재컴파일 후보": "warn", "재검증 필요": "warn" };

function recoPill(reco) {
  if (!reco || reco === "유지") return "";
  return `<span class="reco ${RECO_TONE[reco] || "warn"}">${esc(reco)}</span>`;
}

function lifeBadge(a) {
  const l = a.life;
  if (!l) return "";
  const bits = [];
  if (recoPill(l["권고"])) bits.push(recoPill(l["권고"]));
  const 성 = l["성숙"] || {}, 하 = l["하중"] || {}, 부 = l["부검"] || {};
  const src = [성["해석례"] ? `해석례 ${성["해석례"]}` : "",
               성["회신"] ? `회신 ${성["회신"]}` : "",
               성["판례"] ? `판례 ${성["판례"]}` : "",
               성["교과서"] ? `교과서 ${성["교과서"]}` : "",
               성["문답"] ? `문답 ${성["문답"]}` : ""].filter(Boolean).join("·");
  if (src) bits.push(src);
  if (하["주입"]) {
    let t = `주입 ${하["주입"]}`;
    if (부["정답"] || 부["오답"]) t += ` (정 ${부["정답"]}/오 ${부["오답"]})`;
    bits.push(t);
  }
  return bits.length ? `<span class="life">${bits.join(" · ")}</span>` : "";
}

/* 상세 머리의 생애 카드 — 아티클을 열면 지금 이 지식이 어디쯤 서 있는지가
 * 본문보다 먼저 보인다. */
function lifeCard(a) {
  const l = a && a.life;
  if (!l) return "";
  const 성 = l["성숙"] || {}, 안 = l["안정"] || {},
        하 = l["하중"] || {}, 부 = l["부검"] || {};
  const bar = (label, v, hint) => v == null
    ? `<label>${label}</label><div class="bar none" title="${esc(hint || "실적 없음")}"></div>`
    : `<label>${label}</label><div class="bar ${v >= 1 ? "full" : ""}">
         <i style="width:${Math.round(v * 100)}%"></i></div>`;
  const facts = [
    `해석례 ${성["해석례"] || 0} · 문답 ${성["문답"] || 0}`,
    (안["disputed"] || 안["outdated"])
      ? `Disputed ${안["disputed"] || 0} · Outdated ${안["outdated"] || 0}` : "",
    `주입 ${하["주입"] || 0}`,
    (부["정답"] || 부["오답"]) ? `정답 ${부["정답"]} / 오답 ${부["오답"]}` : "",
  ].filter(Boolean).join(" · ");
  const stale = (l["재심_규칙"] || []).map((r) =>
    `<code>rule:${esc(r)}</code>`).join(" ");
  return `
  <div class="lifecard">
    <div class="top">
      ${recoPill(l["권고"]) || '<span class="reco ok">유지</span>'}
      <span class="facts">${esc(facts)}</span>
    </div>
    <div class="gauges">
      ${bar("성숙", 성["게이지"])}
      ${bar("안정", 안["게이지"])}
      ${bar("하중", 하["게이지"])}
      ${bar("부검", 부["게이지"], "부검 없음 — 주입된 질의에 피드백이 아직 없다")}
    </div>
    ${stale ? `<div class="stale">재심 — 강등·보류된 규칙을 인용 중: ${stale}</div>` : ""}
  </div>`;
}

function renderArticleList() {
  $("articleList").innerHTML = S.articles.map((a) => `
    <div class="item ${S.article === a.slug ? "sel" : ""}" data-slug="${esc(a.slug)}">
      <b>${esc(a.title)}</b>
      <span class="sub">${esc(a.summary)}</span>
      ${lifeBadge(a)}
    </div>`).join("") || `<p class="hint">위키가 아직 없습니다 —
      docs/expc.md §위키의 컴파일 절차를 보세요.</p>`;
  document.querySelectorAll("#articleList .item").forEach((el) => {
    el.onclick = () => { location.hash = `#wiki/${el.dataset.slug}`; };
  });
}

async function openArticle(slug) {
  S.article = slug;
  renderArticleList();
  try {
    // slug 는 주제/이름 — 빗금은 경로로 살려 보낸다 (%2F 로 뭉치면 라우팅이 갈린다)
    const path = slug.split("/").map(encodeURIComponent).join("/");
    const a = await api(`/v1/expc/wiki/${path}`);
    const meta = S.articles.find((x) => x.slug === slug);
    $("articleBody").innerHTML = lifeCard(meta) + renderMd(a.markdown);
    $("articleBody").scrollTop = 0;
  } catch (e) {
    $("articleBody").innerHTML = `<p class="hint">불러오기 실패: ${esc(e.message)}</p>`;
  }
}

/* ── 사례 판 ─────────────────────────────────────────────── */
function filtered() {
  const f = S.filters, needle = f.q.trim().toLowerCase();
  return S.all.filter((c) =>
    (!f.law || c.laws.includes(f.law)) &&
    (!f.org || c.req_org === f.org) &&
    (!f.year || c.decided.startsWith(f.year)) &&
    (!needle || c._text.includes(needle)));
}

function renderCaseList() {
  const rows = filtered();
  $("caseCount").textContent = `${rows.length}건 / 전체 ${S.all.length}건`;
  $("caseList").innerHTML = rows.map((c) => `
    <div class="item ${S.sel === c.serial ? "sel" : ""}" data-serial="${esc(c.serial)}">
      <span class="meta"><b>${esc(c.case_no)}</b> · ${esc(c.decided)} · ${esc(c.req_org || "—")}</span>
      <span class="label">${esc(c.label)}</span>
    </div>`).join("") || `<p class="hint">조건에 맞는 사례가 없습니다.</p>`;
  document.querySelectorAll("#caseList .item").forEach((el) => {
    el.onclick = () => { location.hash = `#case/${el.dataset.serial}`; };
  });
}

async function openCase(serial) {
  S.sel = serial;
  renderCaseList();
  const box = $("caseBody");
  box.innerHTML = `<p class="hint">불러오는 중…</p>`;
  let c;
  try { c = await api(`/v1/expc/cases/${encodeURIComponent(serial)}`); }
  catch (e) { box.innerHTML = `<p class="hint">불러오기 실패: ${esc(e.message)}</p>`; return; }

  const chips = c.laws.map((l) =>
    `<button class="chip" data-law="${esc(l)}">${esc(l)}</button>`).join("");
  const wiki = (c.articles || []).map((a) =>
    `<a href="#wiki/${esc(a.slug)}" class="wikilink">${esc(a.title)}</a>`).join(" ");
  const sect = (title, text) => text ? `
    <h3>${title}</h3><div class="body">${esc(text)}</div>` : "";
  box.innerHTML = `
    <h2>${esc(c.label)}</h2>
    <p class="meta">안건번호 <b>${esc(c.case_no)}</b> · 해석일 ${esc(c.decided)}
      · 질의 ${esc(c.req_org || "—")} → 회신 ${esc(c.ans_org)}
      · <a target="_blank" rel="noopener"
           href="https://www.law.go.kr/LSW/expcInfoP.do?expcSeq=${esc(c.serial)}">law.go.kr 원문</a></p>
    <p class="chips">${chips}</p>
    ${wiki ? `<p class="meta">이 사례를 다룬 위키 — ${wiki}</p>` : ""}
    ${sect("질의요지", c.issue)}
    ${sect("회답", c.answer)}
    ${sect("이유", c.reason)}`;
  box.scrollTop = 0;
  box.querySelectorAll(".chip").forEach((b) => {
    b.onclick = () => {
      S.filters.law = $("fLaw").value = b.dataset.law;
      renderCaseList();
    };
  });
}

/* ── 판 전환·해시 이동 ───────────────────────────────────── */
function show(view) {
  S.view = view;
  $("wikiView").classList.toggle("hidden", view !== "wiki");
  $("casesView").classList.toggle("hidden", view !== "cases");
  document.querySelectorAll("#viewTabs button").forEach((b) =>
    b.classList.toggle("on", b.dataset.v === view));
}

function route() {
  const h = location.hash;
  let m;
  if ((m = h.match(/^#wiki\/(.+)$/))) { show("wiki"); openArticle(decodeURIComponent(m[1])); }
  else if (h === "#wiki") show("wiki");
  else if ((m = h.match(/^#case\/(\d+)$/))) { show("cases"); openCase(m[1]); }
  else if (h === "#cases") show("cases");
  else show(S.articles.length ? "wiki" : "cases");
}

function options(sel, values) {
  for (const v of values) {
    const o = document.createElement("option");
    o.value = o.textContent = v;
    sel.appendChild(o);
  }
}

async function load() {
  // 목록 검색은 몸통까지 걸어야 쓸모가 있다 — full=1 로 한 번에 다 받아
  // 클라이언트에서 거른다 (67건·수백 KB 급이라 이게 가장 단순하다.
  // 수천 건이 되면 서버 필터로 옮긴다).
  const [sum, wiki, cs] = await Promise.all([
    api("/v1/expc/summary"), api("/v1/expc/wiki"),
    api("/v1/expc/cases?limit=2000&full=1"),
  ]);
  S.articles = wiki.articles;
  S.all = cs.cases.map((c) => ({ ...c,
    _text: `${c.label} ${c.issue} ${c.answer} ${c.reason}`.toLowerCase() }));

  const st = sum.stats || {};
  $("summary").textContent =
    `사례 ${st.cases ?? S.all.length} · 법령 ${(st.laws || []).length}` +
    ` · 위키 ${S.articles.length}` +
    (sum.wiki_pending ? ` (생애 대기 ${sum.wiki_pending})` : "") +
    ` · 색인 ${sum.built_at || "?"}`;
  options($("fLaw"), (st.laws || []).map((l) => `${l.name}`));
  options($("fOrg"), [...new Set(S.all.map((c) => c.req_org).filter(Boolean))].sort());
  options($("fYear"), [...new Set(S.all.map((c) => c.decided.slice(0, 4)))].sort().reverse());

  $("fQ").oninput = () => { S.filters.q = $("fQ").value; renderCaseList(); };
  for (const [id, key] of [["fLaw", "law"], ["fOrg", "org"], ["fYear", "year"]])
    $(id).onchange = () => { S.filters[key] = $(id).value; renderCaseList(); };
  document.querySelectorAll("#viewTabs button").forEach((b) => {
    b.onclick = () => { location.hash = b.dataset.v === "wiki" ? "#wiki" : "#cases"; };
  });

  renderArticleList();
  renderCaseList();
  window.addEventListener("hashchange", route);
  route();
}

load().catch((e) => {
  const b = $("banner");
  b.classList.remove("hidden");
  b.textContent = "불러오기 실패 — " + e.message +
    " (수집: python collect_expc.py · 색인: python ingest_expc.py)";
  $("summary").textContent = "색인 없음";
});
