/* 로그 화면 — RAG 이벤트·앱 로그·파일 로그. 전부 읽기 전용 폴링이다.
   이벤트 행을 펼치면 사다리·출처·토큰·오류가 보인다 — "왜 이 답이 나왔나"를
   질의응답 화면 밖에서도 되짚을 수 있어야 관측이다. */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

const state = {
  open: new Set(),          // 펼친 이벤트 키 — 새로고침에도 유지
  files: [],
  timer: null,
};

// ---------------------------------------------------------------- fetch
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

// ---------------------------------------------------------------- 요약
function renderStats(st) {
  const chips = [
    { k: "질의", v: st.asks },
    { k: "검색", v: st.searches },
    { k: "피드백", v: st.feedbacks },
    { k: "오류", v: st.errors, cls: st.errors ? "bad" : "" },
    { k: "미회답", v: st.unanswerable, cls: st.unanswerable ? "warn" : "" },
    { k: "평균 응답", v: st.avg_ms ? `${(st.avg_ms / 1000).toFixed(1)}s` : "—" },
    { k: "최대 응답", v: st.max_ms ? `${(st.max_ms / 1000).toFixed(1)}s` : "—" },
    { k: "토큰 in/out", v: `${st.input_tokens.toLocaleString()} / ${st.output_tokens.toLocaleString()}` },
  ];
  $("stats").innerHTML = chips.map((c) =>
    `<div class="stat ${c.cls || ""}"><span class="v">${esc(c.v)}</span>` +
    `<span class="k">${esc(c.k)}</span></div>`).join("");
}

// ---------------------------------------------------------------- 이벤트
function evKey(e) { return `${e.ts}|${e.kind}|${e.qid || e.q || ""}`; }

function kindBadge(e) {
  if (e.kind === "ask") return `<span class="badge ask">질의</span>`;
  if (e.kind === "search") return `<span class="badge">검색</span>`;
  if (e.kind === "feedback")
    return `<span class="badge ${e.verdict === "정답" ? "ok" : "bad"}">피드백</span>`;
  return `<span class="badge">${esc(e.kind)}</span>`;
}

function flagBadges(e) {
  let out = "";
  if (e.error) out += `<span class="badge bad">오류</span>`;
  if (e.kind === "ask" && e.answerable === false)
    out += `<span class="badge warn">미회답</span>`;
  if (e.recovery && e.recovery.length)
    out += `<span class="badge warn">회복:${esc(e.recovery.join("·"))}</span>`;
  if (e.mode) out += `<span class="badge">${esc(e.mode)}</span>`;
  return out;
}

function evDetail(e) {
  const parts = [];
  const kv = [];
  if (e.qid) kv.push(`qid <b>${esc(e.qid)}</b>`);
  if (e.dur_ms != null) kv.push(`소요 <b>${esc(e.dur_ms)}ms</b>`);
  if (e.n_context != null) kv.push(`컨텍스트 <b>${esc(e.n_context)}</b>구역`);
  if (e.n_refs != null) kv.push(`인용 <b>${esc(e.n_refs)}</b>`);
  if (e.n_discards != null) kv.push(`판정 지문 <b>${esc(e.n_discards)}</b>`);
  if (e.n_hits != null) kv.push(`히트 <b>${esc(e.n_hits)}</b>`);
  if (e.usage)
    kv.push(`LLM <b>${esc(e.usage.calls)}</b>회 · 토큰 <b>${esc(e.usage.input_tokens)}</b>/<b>${esc(e.usage.output_tokens)}</b>`);
  if (e.verdict) kv.push(`판정 <b>${esc(e.verdict)}</b>`);
  if (e.expected_path) kv.push(`기대 <b>${esc(e.expected_path)}</b>`);
  if (kv.length) parts.push(`<div class="kv">${kv.join(" · ")}</div>`);

  if (e.ladder && e.ladder.length) {
    parts.push(`<h4>회수 사다리</h4><ol class="trail">` + e.ladder.map((l) =>
      `<li><span class="${l.count ? "hit" : ""}">${esc(l.stage)}</span> ` +
      `<span class="cnt">${esc(l.count)}건${l.note ? " — " + esc(l.note) : ""}</span></li>`
    ).join("") + `</ol>`);
  }
  if (e.filter && e.filter.applied)
    parts.push(`<div class="kv">필터 <b>${esc(e.filter.in)}</b> → <b>${esc(e.filter.out)}</b>구역` +
               (e.filter.reason ? ` — ${esc(e.filter.reason)}` : "") + `</div>`);
  if (e.refs && e.refs.length) {
    parts.push(`<h4>출처</h4><div class="reflist">` + e.refs.map((r) =>
      `<div class="r">${esc(r.doc)} ▸ ${esc(r.path)}${r.page ? ` (p.${esc(r.page)})` : ""}</div>`
    ).join("") + `</div>`);
  }
  if (e.answer) parts.push(`<h4>답변 (앞 400자)</h4><div class="answerbox">${esc(e.answer)}</div>`);
  if (e.note) parts.push(`<div class="kv">메모 — ${esc(e.note)}</div>`);
  if (e.error) parts.push(`<div class="errbox">${esc(e.error)}</div>`);
  parts.push(`<details class="raw"><summary>원본 JSON</summary>` +
             `<pre>${esc(JSON.stringify(e, null, 2))}</pre></details>`);
  return `<div class="evdetail">${parts.join("")}</div>`;
}

function renderEvents(data) {
  const box = $("events");
  if (!data.events.length) {
    box.innerHTML = `<div class="empty">이벤트가 아직 없습니다 — /rag/ 에서 질의하면 여기 쌓입니다.</div>`;
    $("evStats").textContent = "";
    return;
  }
  $("evStats").textContent = `${data.count}건 (파일: ${data.file})`;
  box.innerHTML = data.events.map((e) => {
    const key = evKey(e);
    const open = state.open.has(key);
    const t = (e.ts || "").replace("T", " ").replace(/\+.*$/, "");
    const label = e.kind === "feedback"
      ? `${e.qid || ""} ${e.note || ""}` : (e.q || "");
    return `<div class="ev" data-key="${esc(key)}">` +
      `<div class="evrow"><span class="ts">${esc(t)}</span>${kindBadge(e)}` +
      `<span class="q">${esc(label)}</span>${flagBadges(e)}` +
      `<span class="ms">${e.dur_ms != null ? esc(e.dur_ms) + "ms" : ""}</span></div>` +
      (open ? evDetail(e) : "") + `</div>`;
  }).join("");
  box.querySelectorAll(".evrow").forEach((row) => {
    row.addEventListener("click", () => {
      const key = row.parentElement.dataset.key;
      state.open.has(key) ? state.open.delete(key) : state.open.add(key);
      refreshEvents();          // 다시 그린다 — 상태는 state.open 에 있다
    });
  });
}

async function refreshEvents() {
  const kind = $("evKind").value, q = $("evQ").value.trim();
  const p = new URLSearchParams({ limit: "100" });
  if (kind) p.set("kind", kind);
  if (q) p.set("q", q);
  try {
    const data = await getJSON(`/v1/logs/rag?${p}`);
    renderStats(data.stats);
    renderEvents(data);
    $("summary").textContent =
      `질의 ${data.stats.asks} · 오류 ${data.stats.errors} (최근 ${data.count}건 창)`;
  } catch (err) {
    $("summary").textContent = `이벤트 읽기 실패: ${err.message}`;
  }
}

// ---------------------------------------------------------------- 앱 로그
async function refreshAppLog() {
  const p = new URLSearchParams({ limit: "300", level: $("appLevel").value });
  const q = $("appQ").value.trim();
  if (q) p.set("q", q);
  try {
    const data = await getJSON(`/v1/logs/app?${p}`);
    $("appStats").textContent = `${data.count}건 — 이 프로세스만 (정본은 파일 로그)`;
    const box = $("applog");
    const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 8;
    // 링버퍼는 최신이 앞 — 화면은 시간순(오래된 것 위)으로 눕힌다
    box.innerHTML = data.records.slice().reverse().map((r) =>
      `<span class="ln ${esc(r.level)}">${esc(r.ts.replace("T", " ").replace(/\+.*$/, ""))} ` +
      `${esc(r.level.padEnd(7))} ${esc(r.logger)} — ${esc(r.msg)}</span>`
    ).join("") || `<span class="ln DEBUG">비어 있음</span>`;
    if (atBottom) box.scrollTop = box.scrollHeight;
  } catch (err) {
    $("appStats").textContent = `읽기 실패: ${err.message}`;
  }
}

// ---------------------------------------------------------------- 파일 로그
async function loadFileList() {
  try {
    const data = await getJSON("/v1/logs/files");
    state.files = data.files;
    $("fileStats").textContent = `${data.files.length}개 — ${data.dir}`;
    const sel = $("fileSel");
    const cur = sel.value;
    sel.innerHTML = `<option value="">파일 선택…</option>` + data.files.map((f) =>
      `<option value="${esc(f.name)}">${esc(f.name)} (${(f.size / 1024).toFixed(0)}KB)</option>`
    ).join("");
    if (cur && data.files.some((f) => f.name === cur)) sel.value = cur;
  } catch (err) {
    $("fileStats").textContent = `목록 실패: ${err.message}`;
  }
}

async function refreshFileTail() {
  const name = $("fileSel").value;
  const pre = $("filetail");
  if (!name) { pre.classList.add("hidden"); return; }
  try {
    const data = await getJSON(`/v1/logs/file?name=${encodeURIComponent(name)}&lines=200`);
    pre.classList.remove("hidden");
    pre.textContent = data.lines.join("\n") || "(비어 있음)";
    pre.scrollTop = pre.scrollHeight;
  } catch (err) {
    pre.classList.remove("hidden");
    pre.textContent = `읽기 실패: ${err.message}`;
  }
}

// ---------------------------------------------------------------- 회전
async function refreshAll() {
  await Promise.all([refreshEvents(), refreshAppLog(), refreshFileTail()]);
}

function schedule() {
  clearInterval(state.timer);
  if ($("optAuto").checked) state.timer = setInterval(refreshAll, 5000);
}

$("refreshBtn").addEventListener("click", refreshAll);
$("optAuto").addEventListener("change", schedule);
$("evKind").addEventListener("change", refreshEvents);
$("evQ").addEventListener("input", () => { clearTimeout(state._t1); state._t1 = setTimeout(refreshEvents, 300); });
$("appLevel").addEventListener("change", refreshAppLog);
$("appQ").addEventListener("input", () => { clearTimeout(state._t2); state._t2 = setTimeout(refreshAppLog, 300); });
$("fileSel").addEventListener("change", refreshFileTail);

loadFileList().then(refreshAll);
schedule();
