/* 상단 이동 — 여덟 화면이 같은 묶음을 같은 순서로 쓴다.
 *
 * 화면마다 손으로 링크를 적어 두던 때는 어디서 어디로 갈 수 있는지가 화면마다
 * 달랐다(문서 화면엔 일곱, 참조 화면엔 넷, 로그 화면엔 셋). 목록은 여기 한 곳에만
 * 둔다 — 화면이 늘면 이 배열에 한 줄을 더한다.
 *
 * 지금 화면은 `data-nav` 로 **자기가 말한다**. 경로로 알아맞히지 않는 이유는
 * 문서 화면이 `/` 와 `/home/` 두 자리에 걸려 있어서다 (api.app 은 루트가 JSON).
 */
(function () {
  const NAV = [
    { key:"home",      href:"/home/",      label:"문서" },
    { key:"structure", href:"/structure/", label:"구조 검수" },
    { gap:true },
    { key:"bindings",  href:"/bindings/",  label:"틀 연결" },
    { key:"glossary",  href:"/glossary/",  label:"용어집" },
    { key:"links",     href:"/links/",     label:"참조" },
    { gap:true },
    { key:"rag",       href:"/rag/",       label:"질의응답" },
    { key:"rules",     href:"/rules/",     label:"공리" },
    { key:"agent6",    href:"/agent6/",    label:"점검" },
    { gap:true },
    { key:"lineage",   href:"/lineage/",   label:"원장" },
    { key:"logs",      href:"/logs/",      label:"로그" },
  ];

  /* 검수 대기 배지 — 사람 손을 기다리는 큐 셋을 어느 화면에서든 보이게 한다.
   *
   * 세 큐는 전부 "승인해야 검색이 바뀌는" 루프의 입구다:
   *   용어집   검수 큐   승인 = 질의 진입 앵커 등재
   *   참조     보류      확정 = 질의 확장(expand_refs)에 사용
   *   질의응답 백로그    승인 = 오참조 간선 억제
   * 배지를 누르면 목록이 아니라 **그 큐가 바로 열리는 자리**로 간다.
   * 수는 60초 sessionStorage 캐시 — 화면을 오갈 때마다 서버를 두드리지 않는다. */
  const QUEUES = [
    { key: "glossary", jump: "/glossary/#review",
      url: "/v1/glossary/review?limit=1",
      pick: (d) => d.total || 0,
      hint: "용어 검수 대기 — 승인하면 질의 진입 앵커가 됩니다" },
    // 참조는 승인형이 아니라 정리형이다 — 기본은 전부 연결(후보가 하나면
    // 자동), 사람은 목록을 훑어 틀린 것을 끊는다. 보류 = 여럿에 걸린 잔여뿐.
    { key: "links", jump: "/links/#pending",
      url: "/v1/rag/links/summary",
      pick: (d) => d.pending || 0,
      hint: "보류 참조 — 여럿에 걸린 것만 남았습니다. 원문 보고 고르세요" },
    { key: "rag", jump: "/rag/#backlog",
      url: "/v1/rag/verdicts",
      pick: (d) => (d.edges || []).length + (d.fixes || []).length
                 + (d.struct || []).length + (d.misses || []).length,
      hint: "판정 백로그 — 승인하면 잘못된 간선을 억제합니다" },
    // 공리 루프 — 승격 결정을 기다리는 규칙(잠정 + 정착 후보 권고).
    { key: "rules", jump: "/rules/",
      url: "/v1/rag/rules",
      pick: (d) => (d.rules || []).filter((r) => r.status === "잠정"
                 || (r["보고서"] || {})["권고"] === "정착 후보").length,
      hint: "규칙 승격 대기 — 잠정 승인·정착(공리) 결정은 사람 몫입니다" },
    // 오류는 성격이 다르다(빨강) — 대기가 아니라 사고다. 있을 때만 뜬다.
    { key: "logs", jump: "/logs/", tone: "err",
      url: "/v1/logs/app?level=ERROR&limit=50",
      pick: (d) => d.count || 0,
      hint: "최근 오류 — 로그에서 무엇이 터졌는지 확인" },
  ];
  const CACHE_KEY = "ui-queue-counts";
  const CACHE_MS = 60_000;

  async function counts() {
    try {
      const c = JSON.parse(sessionStorage.getItem(CACHE_KEY) || "null");
      if (c && Date.now() - c.t < CACHE_MS) return c.n;
    } catch { /* 캐시는 장식이다 */ }
    const n = {};
    await Promise.all(QUEUES.map(async (q) => {
      try {
        const r = await fetch(q.url);
        if (r.ok) n[q.key] = q.pick(await r.json());
      } catch { /* 라우터가 없는 배포도 있다 — 배지만 안 뜬다 */ }
    }));
    try { sessionStorage.setItem(CACHE_KEY, JSON.stringify({ t: Date.now(), n })); }
    catch { /* 시크릿 모드 등 */ }
    return n;
  }

  async function badges(host) {
    const n = await counts();
    for (const q of QUEUES) {
      if (!n[q.key]) continue;
      const a = host.querySelector(`a[data-key="${q.key}"]`);
      if (!a || a.querySelector(".qbadge")) continue;
      const b = document.createElement("span");
      b.className = "qbadge" + (q.tone ? ` ${q.tone}` : "");
      b.textContent = n[q.key] > 999 ? "999+" : String(n[q.key]);
      b.title = q.hint;
      // a 안의 a 는 안 된다 — span 이 자기 목적지로 간다
      b.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation();
        location.href = q.jump;
      });
      a.appendChild(b);
    }
  }

  /* 기록 모드 칩 — 로컬 미러(OPS_RECORD=1)에서만 뜬다. 쓰기 조작이 지금 몇 건
   * 아웃박스에 쌓였는지를 어느 화면에서든 보이게 한다 — 반출을 잊고 세션을
   * 닫는 사고를 막는 자리다. 캐시하지 않는다: 이 수는 방금 한 조작을 따라
   * 움직여야 믿을 수 있다. */
  async function opsChip(host) {
    try {
      const r = await fetch("/v1/ops/status");
      if (!r.ok) return;
      const s = await r.json();
      if (!s.record) return;
      const b = document.createElement("span");
      b.className = "ops-chip";
      b.textContent = `기록 ${s.outbox}건`;
      b.title = "기록 모드 — 화면에서 한 쓰기 조작이 아웃박스에 쌓입니다.\n"
              + "반출: curl -o outbox.tar.gz <이 서버>/v1/ops/outbox/export";
      host.appendChild(b);
    } catch { /* ops 가 없는 배포 — 칩만 안 뜬다 */ }
  }

  function mount() {
    const host = document.querySelector("[data-nav]");
    if (!host) return;
    const cur = host.getAttribute("data-nav")
      || (location.pathname.split("/")[1] || "home");

    // 표식은 상단바의 첫 칸 — 이동 묶음 밖에 둔다 (이동이 아니라 소속이다)
    const mark = document.createElement("a");
    mark.className = "ui-mark";
    mark.href = "/home/";
    mark.title = "문서·데이터 관리";
    mark.innerHTML = '<i>8</i><b>8-AGENT</b>';
    host.parentNode.insertBefore(mark, host);

    host.innerHTML = NAV.map((n) =>
      n.gap ? '<span class="gap"></span>'
            : `<a href="${n.href}" data-key="${n.key}"${n.key === cur
                ? ' class="on" aria-current="page"' : ""}>${n.label}</a>`
    ).join("");

    badges(host);
    opsChip(host);
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
