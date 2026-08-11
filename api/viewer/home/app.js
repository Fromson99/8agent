/* 문서·데이터 관리 — 저장소의 첫 화면. 탐색기 방식이다.
 *
 * 이 시스템의 정본은 DB 가 아니라 파일이다. 그래서 첫 화면이 하는 일은 셋:
 *   1. 지금 무엇이 얼마나 있나 (현황 카드 — 각 관리 화면으로 가는 문)
 *   2. 새 문서 넣기 (올리면 바로 구조 해석까지 — 폴더 안이면 그 폴더로)
 *   3. 처리된 문서 관리 (폴더로 묶기 · 이름 · 재해석 · 삭제)
 *
 * 폴더는 두 겹이다: 문서 meta 의 folder 라벨(어디 속하나) + 서버 등록부
 * folders.json(빈 폴더도 존재하게). "폴더를 먼저 만들고 문서를 넣는" 손짓은
 * 등록부가 있어야 성립한다.
 *
 * 현황은 라우터가 빠져 있어도 죽지 않는다 — 슬림 이미지에서는 그 카드만 "—" 다. */
const S = { docs: [], folders: [], folder: null, q: "",
            // 구조화 틀 — routes: 등록된 형식, bind: {folders,docs} → doc_type
            formats: [], bind: { folders: {}, docs: {} } };
const $ = (id) => document.getElementById(id);
const esc = (s) => (s || "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const fmtB = (n) => n == null ? "—"
  : n >= 1048576 ? `${(n / 1048576).toFixed(1)}MB`
  : n >= 1024 ? `${Math.round(n / 1024)}KB` : `${n}B`;
const fmtAt = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? "—" : d.toLocaleString("ko-KR", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};
const pct = (x) => x == null ? "—" : `${Math.round(x * 100)}%`;

async function jget(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

/* ------------------------------------------------------------------ 적재 */
async function load() {
  const [docs, folders, rules, glo, links, a6, fmts] = await Promise.allSettled([
    jget("/v1/structure/documents"),
    jget("/v1/structure/folders"),
    jget("/v1/structure/rules/custom"),
    jget("/v1/glossary"),
    jget("/v1/rag/links"),
    jget("/v1/agent6/graph"),
    jget("/v1/formats"),
  ]);
  S.docs = docs.status === "fulfilled" ? docs.value.documents : [];
  if (fmts.status === "fulfilled") {
    S.formats = fmts.value.routes || [];
    S.bind = fmts.value.bindings || { folders: {}, docs: {} };
  }
  S.folders = folders.status === "fulfilled" ? folders.value.folders
    : [...new Set(S.docs.map((d) => d.folder).filter(Boolean))]
        .map((n) => ({ name: n, docs: S.docs.filter((d) => d.folder === n).length }));
  if (S.folder && !S.folders.some((f) => f.name === S.folder)) S.folder = null;
  renderStats({ rules, glo, links, a6 });
  renderDocs();
  const total = S.docs.reduce((a, d) => a + (d.bytes || 0), 0);
  $("summary").textContent =
    `문서 ${S.docs.length} · ${fmtB(total)}`
    + (S.folders.length ? ` · 폴더 ${S.folders.length}` : "")
    + (glo.status === "fulfilled" ? ` · 용어 ${glo.value.stats.terms}` : "")
    + (links.status === "fulfilled"
       ? ` · 참조 ${links.value.cross.length}+보류 ${links.value.pending.length}` : "");
}

function renderStats({ rules, glo, links, a6 }) {
  const passed = S.docs.filter((d) => d.passed).length;
  const total = S.docs.reduce((a, d) => a + (d.bytes || 0), 0);
  const card = (href, k, v, d) =>
    `<a class="stat" href="${href}"><div class="k">${k}</div>
       <div class="v">${v}</div><div class="d">${d}</div></a>`;
  const off = "사용할 수 없음 — 라우터 없음";

  let html = card("/structure/", "문서 · 해석 결과", S.docs.length,
    `<span class="ok">통과 ${passed}</span> · `
    + `<span class="warn">격리 ${S.docs.length - passed}</span> · ${fmtB(total)}`
    + (S.folders.length ? ` · 폴더 ${S.folders.length}` : ""));
  html += glo.status === "fulfilled"
    ? card("/glossary/", "용어", glo.value.stats.terms,
        `여러 문서에 걸친 것 ${glo.value.stats.shared}`
        + ` · 출현 ${glo.value.stats.occurrences}`)
    : card("/glossary/", "용어", "—", off);
  html += links.status === "fulfilled"
    ? card("/links/", "조문 상호참조", links.value.cross.length,
        `<span class="warn">보류 ${links.value.pending.length}</span> · 문서 안 `
        + Object.values(links.value.in_doc).reduce((a, e) => a + e.length, 0))
    : card("/links/", "조문 상호참조", "—", off);
  html += rules.status === "fulfilled"
    ? card("/structure/", "등록한 표면 패턴", rules.value.rules.length,
        "검수 화면의 설정 · 규칙에서 등록")
    : card("/structure/", "등록한 표면 패턴", "—", off);
  html += a6.status === "fulfilled"
    ? card("/agent6/", "AGENT6 근거 연결",
        (a6.value.links || []).length,
        `체크리스트 ${(a6.value.items || []).length}항목 · 코퍼스 `
        + (a6.value.corpora || []).length)
    : card("/agent6/", "AGENT6 근거 연결", "—", off);
  $("stats").innerHTML = html;
}

/* ------------------------------------------------------------- 문서 목록 */
const HEAD = `<tr><th>이름</th><th>쪽</th><th>크기</th><th>게이트</th><th>올린 때</th>
    <th style="text-align:right">동작</th></tr>`;

const docRow = (d, withFolder) => `<tr data-id="${esc(d.doc_id)}" draggable="true"
  title="꾹 눌러 끌어서 폴더에 놓으면 옮겨집니다">
  <td class="name"><a href="/structure/?doc=${encodeURIComponent(d.doc_id)}"
       title="검수 화면에서 열기">${esc(d.name || d.doc_id)}</a><button class="pencil"
       title="이름 변경 — 해석 결과는 그대로">✎</button>
    ${withFolder && d.folder ? `<span class="pill">📁 ${esc(d.folder)}</span>` : ""}
    <span class="id">${esc(d.doc_id)}</span></td>
  <td class="num">${d.pages ?? "—"}</td>
  <td class="num">${fmtB(d.bytes)}</td>
  <td><span class="pill ${d.passed ? "ok" : "warn"}"
        title="적합도 ${pct(d.score)} · ${esc(d.tier || "")}">
        ${d.passed ? "통과" : "격리"} ${pct(d.score)}</span>
      ${d.used_llm ? '<span class="pill llm" title="잔여 해소에 LLM 사용">LLM</span>' : ""}</td>
  <td class="num">${fmtAt(d.at)}</td>
  <td><div class="acts">
    <button class="del danger" title="원본·해석 결과·페이지 캐시 삭제">삭제</button>
  </div></td>
</tr>`;

function renderDocs() {
  $("folderList").innerHTML =
    S.folders.map((f) => `<option value="${esc(f.name)}">`).join("");
  updateUpload();

  const n = S.q.replace(/\s/g, "").toLowerCase();
  let html = "";
  let bind = [];

  if (n) {
    // 찾기 — 폴더 경계를 무시하고 평평하게. 폴더 이름으로도 걸린다.
    const rs = S.docs.filter((d) =>
      `${d.name || d.doc_id} ${d.folder || ""}`.replace(/\s/g, "").toLowerCase().includes(n));
    $("docTitle").textContent = `찾기 결과 (${rs.length})`;
    html = rs.length
      ? `<table>${HEAD}${rs.map((d) => docRow(d, true)).join("")}</table>`
      : "<div class='empty'>일치하는 문서가 없습니다.</div>";
  } else if (S.folder === null) {
    // 맨 위 — 폴더들(빈 폴더 포함)과 미분류 문서. 탐색기의 루트다.
    const unfiled = S.docs.filter((d) => !d.folder);
    $("docTitle").textContent = `문서 (${S.docs.length})`;
    if (!S.docs.length && !S.folders.length) {
      html = `<div class="empty">아직 올린 문서가 없습니다.<br>
        위에 PDF·XML 을 끌어다 놓거나, ＋ 폴더 만들기로 자리를 먼저 만들어 두세요.</div>`;
    } else {
      html = `<table>${HEAD}`;
      html += S.folders.map((f) => `<tr class="fold openable" data-open="${esc(f.name)}"
          title="열기 — 안에서 올리면 이 폴더로 · 문서를 끌어다 놓으면 이 폴더로 옮겨집니다">
        <td colspan="6"><span class="ficon">📁</span><b>${esc(f.name)}</b>
          <span class="sub">${f.docs}개</span>
          ${S.bind.folders[f.name]
            ? `<span class="pill" title="이 폴더의 문서는 이 구조화 틀로 잘립니다">🧩 ${esc(S.bind.folders[f.name])}</span>`
            : ""}
          <span class="open-hint">열기 →</span></td></tr>`).join("");
      if (unfiled.length && S.folders.length)
        html += `<tr class="fold"><td colspan="6"><span class="ficon">·</span>
          <b>미분류</b> <span class="sub">${unfiled.length}개</span></td></tr>`;
      html += unfiled.map((d) => docRow(d, false)).join("") + "</table>";
    }
  } else {
    // 폴더 안 — 이 폴더의 문서만. 위 드롭존이 이 폴더를 향한다.
    const rs = S.docs.filter((d) => d.folder === S.folder);
    $("docTitle").textContent = `📁 ${S.folder} (${rs.length})`;
    html = `<div class="ftool">
      <button id="backAll">← 전체</button>
      <b>📁 ${esc(S.folder)}</b><span class="sub">${rs.length}개</span>
      <span class="grow"></span>
      <button id="fRename" title="이 폴더에 든 문서 전부의 라벨을 바꾼다">폴더 이름 변경</button>
      <button id="fDelete" class="danger"
              title="폴더만 지운다 — 문서는 미분류로 남는다">폴더 삭제</button>
    </div>`;
    html += formatBar(S.folder, rs.length);
    html += rs.length
      ? `<table>${HEAD}${rs.map((d) => docRow(d, false)).join("")}</table>`
      : `<div class="empty">이 폴더는 비어 있습니다.<br>
         위에 PDF·HWP·DOCX·XML 을 올리면 이 폴더로 들어갑니다.</div>`;
    bind.push(() => {
      $("backAll").onclick = () => { S.folder = null; renderDocs(); };
      $("fRename").onclick = () => renameFolder(S.folder);
      $("fDelete").onclick = () => deleteFolder(S.folder);
      bindFormatBar(S.folder);
    });
  }

  $("docs").innerHTML = html;
  bind.forEach((f) => f());

  $("docs").querySelectorAll("tr.openable").forEach((tr) => {
    tr.onclick = () => { S.folder = tr.dataset.open; renderDocs(); };
    dropTarget(tr, tr.dataset.open);        // 문서를 끌어다 놓으면 이 폴더로
  });
  $("docs").querySelectorAll("tr[data-id]").forEach((tr) => {
    const doc = S.docs.find((d) => d.doc_id === tr.dataset.id);
    tr.querySelector(".pencil").onclick = () => editName(tr, doc);
    tr.querySelector(".del").onclick = () => removeDoc(doc);
    // 꾹 눌러 끌기 — 놓을 곳(폴더 행)이 없으면 아무 일도 없다.
    tr.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", doc.doc_id);
      e.dataTransfer.effectAllowed = "move";
      tr.classList.add("dragging");
    });
    tr.addEventListener("dragend", () => tr.classList.remove("dragging"));
  });
  // 폴더 안에서는 도구줄(← 전체)이 "이 폴더에서 빼기" 받이가 된다.
  const ftool = $("docs").querySelector(".ftool");
  if (ftool) dropTarget(ftool, "", "폴더에서 빼기 — 미분류로");
}

/* 끌어다 놓기 받이 — folder 가 빈 문자열이면 미분류로 뺀다. */
function dropTarget(el, folder, hint) {
  if (hint) el.title = (el.title ? el.title + " · " : "") + hint;
  el.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    el.classList.add("dropover");
  });
  el.addEventListener("dragleave", () => el.classList.remove("dropover"));
  el.addEventListener("drop", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    el.classList.remove("dropover");
    const id = e.dataTransfer.getData("text/plain");
    const doc = S.docs.find((d) => d.doc_id === id);
    if (!doc || (doc.folder || "") === folder) return;
    const r = await fetch(`/v1/structure/${encodeURIComponent(id)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder }) });
    if (!r.ok) { banner(await errText(r)); return; }
    banner(folder ? `'${folder}' 폴더로 옮겼습니다 — ${doc.name}`
                  : `폴더에서 뺐습니다 — ${doc.name} (미분류)`);
    load();
  });
}

/* --------------------------------------------------- 구조화 틀 (형식) 연결
 *
 * "이 폴더는 이 틀로 자른다" 를 붙이는 자리. 붙은 폴더의 문서는 유도(S0~S6)가
 * 아니라 형식 파일의 마커로 잘린다 — 맞냐 틀리냐는 게이트 점수로 나온다.
 *
 * 틀이 없으면 이 폴더의 문서들로 **만들 수 있다**(컴파일). 샘플을 다시 올릴 필요는
 * 없다 — 이미 파싱해 둔 것을 쓴다. */
function formatBar(folder, nDocs) {
  const cur = S.bind.folders[folder] || "";
  const opts = S.formats.filter((f) => f.ready)
    .map((f) => `<option value="${esc(f.doc_type)}"${f.doc_type === cur ? " selected" : ""}>`
                + `${esc(f.doc_type)}</option>`).join("");
  return `<div class="ftool fmtbar">
    <span title="이 폴더의 문서를 자를 구조화 틀">🧩 구조화 틀</span>
    <select id="fFormat"><option value="">— 연결 없음 (문서에서 구조를 유도) —</option>
      ${opts}</select>
    <span id="fFmtMsg" class="sub">${cur
      ? "이 폴더의 문서는 이 틀로 잘립니다"
      : "연결하지 않으면 문서마다 구조를 유도합니다"}</span>
    <span class="grow"></span>
    <button id="fCompile" ${nDocs < 2 ? "disabled" : ""}
      title="${nDocs < 2 ? "샘플이 2개 이상 필요합니다"
                         : "이 폴더의 문서들로 마커 체계를 유도해 새 틀을 만듭니다"}">
      ＋ 이 폴더로 틀 만들기</button>
  </div>`;
}

function bindFormatBar(folder) {
  $("fFormat").onchange = async (e) => {
    const doc_type = e.target.value || null;
    const r = await fetch("/v1/formats/bindings", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope: "folder", key: folder, doc_type }) });
    if (!r.ok) { banner(await errText(r)); return; }
    banner(doc_type
      ? `'${folder}' 폴더를 틀 '${doc_type}' 에 연결했습니다 — 다시 해석하면 이 틀로 잘립니다`
      : `'${folder}' 폴더의 틀 연결을 풀었습니다 — 다시 구조를 유도합니다`);
    load();
  };
  $("fCompile").onclick = () => compileFormat(folder);
}

async function compileFormat(folder) {
  const nv = prompt(`'${folder}' 폴더의 문서들로 만들 구조화 틀의 이름`
    + "\n(예: 상장규정 — 같은 양식의 문서군에 붙일 이름입니다)", folder);
  if (nv === null) return;
  const doc_type = nv.trim();
  if (!doc_type) return;
  const useLlm = $("useLlm").checked;

  const row = document.createElement("div");
  row.className = "up";
  row.innerHTML = `<span class="spin"></span><b>틀 만들기 — ${esc(doc_type)}</b>
    <span class="sub">폴더의 문서로 마커 체계를 유도하고 검증합니다${
      useLlm ? " (LLM 유도)" : " (규칙 유도)"}…</span>`;
  $("uplist").appendChild(row);

  const r = await fetch("/v1/formats/compile", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_type, folders: [folder], use_llm: useLlm,
                           overwrite: false }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    row.classList.add("err");
    let msg = typeof j.detail === "string" ? j.detail : `실패 (${r.status})`;
    try {                                   // 홀드아웃 실패는 어느 문서가 왜 떨어졌는지 싣고 온다
      const d = JSON.parse(j.detail);
      msg = `${d.error} — ` + d.failed.map((f) => `${f.name} ${Math.round(f.score * 100)}%`).join(", ");
    } catch { /* 평문 detail */ }
    row.innerHTML = `<b>틀 만들기 실패 — ${esc(doc_type)}</b>
      <span class="sub">${esc(msg)}</span>
      <button onclick="this.parentElement.remove()">닫기</button>`;
    return;
  }
  // 결과를 숫자로 보여준다 — 마커가 몇 개고 샘플마다 몇 %로 맞았는지가 판단 재료다
  const rows = j.applied.map((a) => `${esc(a.name)} ${Math.round(a.score * 100)}%`
    + (a.held_out ? "(검증)" : "")).join(" · ");
  row.classList.remove("busy");
  row.innerHTML = `<b>틀을 만들었습니다 — ${esc(doc_type)}</b>
    <span class="pill">마커 ${j.markers.length}</span>
    <span class="pill ${j.holdout ? "ok" : "warn"}"
      title="${j.holdout ? "유도에 쓰지 않은 샘플로 검증했습니다"
                         : "샘플이 적어 홀드아웃 검증을 못 했습니다 — 신뢰도 낮음"}">
      ${j.holdout ? "홀드아웃 검증" : "신뢰도 낮음"}</span>
    <span class="sub">${esc(rows)}</span>
    <button onclick="this.parentElement.remove()">닫기</button>`;
  banner(`'${folder}' 폴더를 틀 '${doc_type}' 에 연결했습니다 — `
    + "이 폴더의 문서를 다시 해석하면 이 틀로 잘립니다");
  load();
}

/* ------------------------------------------------------------ 폴더 동작 */
async function makeFolder() {
  const nv = prompt("새 폴더 이름 (예: 법령문서)");
  if (nv === null) return;
  const name = nv.trim();
  if (!name) return;
  const r = await fetch("/v1/structure/folders", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }) });
  if (!r.ok) { banner(await errText(r)); return; }
  banner(`'${name}' 폴더를 만들었습니다 — 안에서 올리면 이 폴더로 들어갑니다`);
  S.folder = name;              // 바로 들어간다 — 다음 손짓이 "문서 넣기"라서
  load();
}

async function renameFolder(f) {
  const nv = prompt(`'${f}' 폴더의 새 이름`, f);
  if (nv === null) return;
  const name = nv.trim();
  if (!name || name === f) return;
  const r = await fetch(`/v1/structure/folders/${encodeURIComponent(f)}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }) });
  if (!r.ok) { banner(await errText(r)); return; }
  const j = await r.json();
  banner(`폴더 이름을 바꿨습니다 — ${f} → ${name} (문서 ${j.docs}개)`);
  if (S.folder === f) S.folder = name;
  load();
}

async function deleteFolder(f) {
  const docs = S.docs.filter((d) => d.folder === f).length;
  if (!confirm(`'${f}' 폴더를 지웁니다.\n`
    + (docs ? `든 문서 ${docs}개는 지워지지 않고 미분류로 나옵니다.` : "빈 폴더입니다."))) return;
  const r = await fetch(`/v1/structure/folders/${encodeURIComponent(f)}`,
                        { method: "DELETE" });
  if (!r.ok) { banner(await errText(r)); return; }
  banner(`'${f}' 폴더를 지웠습니다${docs ? ` — 문서 ${docs}개는 미분류로` : ""}`);
  if (S.folder === f) S.folder = null;
  load();
}

/* ------------------------------------------------------- 문서 행 동작 */
/* 이름 바꾸기 — 행 안에서 바로. Enter 저장, Esc 취소. */
function editName(tr, doc) {
  const cell = tr.querySelector(".name");
  const old = cell.innerHTML;
  cell.innerHTML = `<input value="${esc(doc.name || "")}" spellcheck="false">`;
  const inp = cell.querySelector("input");
  inp.focus(); inp.select();
  let done = false;
  const finish = () => { done = true; renderDocs(); };
  inp.onkeydown = async (e) => {
    if (e.key === "Escape") { finish(); return; }
    if (e.key !== "Enter") return;
    const name = inp.value.trim();
    if (!name || name === doc.name) { finish(); return; }
    const r = await fetch(`/v1/structure/${encodeURIComponent(doc.doc_id)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }) });
    if (!r.ok) { banner(await errText(r)); finish(); return; }
    doc.name = name;
    banner(`이름을 바꿨습니다 — ${name}`);
    finish();
  };
  inp.onblur = () => { if (!done) { done = true; cell.innerHTML = old; renderDocs(); } };
}

async function removeDoc(doc) {
  if (!confirm(`'${doc.name || doc.doc_id}' 를 지웁니다.\n`
    + "원본 PDF·해석 결과·페이지 캐시가 함께 지워지고 되돌릴 수 없습니다.")) return;
  const r = await fetch(`/v1/structure/${encodeURIComponent(doc.doc_id)}`,
                        { method: "DELETE" });
  if (!r.ok) banner(await errText(r));
  else banner(`지웠습니다 — ${doc.name || doc.doc_id}`);
  load();
}

/* ---------------------------------------------------------------- 올리기 */
/* 폴더 안이면 드롭존이 그 폴더를 향한다 — 입력란은 잠그고 향하는 곳을 보여준다. */
function updateUpload() {
  const inp = $("upFolder");
  if (S.folder) {
    inp.value = S.folder;
    inp.disabled = true;
    inp.title = "폴더 안에서는 올린 문서가 이 폴더로 들어갑니다";
  } else {
    if (inp.disabled) inp.value = "";
    inp.disabled = false;
    inp.title = "올리는 문서를 묶어 둘 폴더. 폴더 이름은 용어집에도 용어로 올라간다";
  }
}

async function uploadOne(file) {
  const target = S.folder || $("upFolder").value.trim();
  const row = document.createElement("div");
  row.className = "up";
  row.innerHTML = `<span class="spin"></span><b>${esc(file.name)}</b>
    ${target ? `<span class="pill">📁 ${esc(target)}</span>` : ""}
    <span class="sub">올려서 해석 중… (첫 파싱은 몇 분 걸릴 수 있습니다)</span>`;
  $("uplist").appendChild(row);

  const fd = new FormData();
  fd.set("file", file);
  fd.set("use_llm", $("useLlm").checked ? "true" : "false");
  if (target) fd.set("folder", target);
  try {
    const r = await fetch("/v1/structure/documents", { method: "POST", body: fd });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : r.status);
    row.innerHTML = `<b>${esc(file.name)}</b>
      ${j.folder ? `<span class="pill">📁 ${esc(j.folder)}</span>` : ""}
      <span class="pill ${j.passed ? "ok" : "warn"}">${j.passed ? "통과" : "격리"} ${pct(j.score)}</span>
      <span class="sub">${j.pages}쪽</span>
      <a class="navlink" href="/structure/?doc=${encodeURIComponent(j.doc_id)}">검수 열기 →</a>`;
    setTimeout(() => row.remove(), 12000);
    load();
  } catch (e) {
    row.classList.add("err");
    row.innerHTML = `<b>${esc(file.name)}</b>
      <span class="sub">실패 — ${esc(String(e.message || e))}</span>
      <button onclick="this.parentElement.remove()">닫기</button>`;
  }
}

function takeFiles(list) {
  [...list].filter((f) => /\.(pdf|xml|hwp|hwpx|docx)$/i.test(f.name)).forEach(uploadOne);
}

async function errText(r, j) {
  j = j || await r.json().catch(() => ({}));
  const d = j.detail;
  return typeof d === "string" ? d : (d && d.message) || `실패 (${r.status})`;
}

function banner(msg) {
  const b = $("banner");
  b.textContent = msg;
  b.classList.remove("hidden");
  clearTimeout(banner.t);
  banner.t = setTimeout(() => b.classList.add("hidden"), 6000);
}

$("file").onchange = (e) => { takeFiles(e.target.files); e.target.value = ""; };
const drop = $("drop");
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => {
  e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => {
  e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => takeFiles(e.dataTransfer.files));
$("mkFolder").onclick = makeFolder;
$("q").oninput = (e) => { S.q = e.target.value.trim(); renderDocs(); };
load();
