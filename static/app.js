/* 아이디어뱅크 화면 — 해시 라우팅: #new #revise/N #list #idea/N #cert/N #verify #help */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};

async function api(path, opts = {}) {
  const res = await fetch("/api/" + path, {
    method: opts.method || "GET",
    headers: opts.body ? { "Content-Type": "application/json" } : {},
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const ct = res.headers.get("Content-Type") || "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.error) || "요청을 처리하지 못했습니다.");
  return data;
}

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 2600);
}

const KST = { timeZone: "Asia/Seoul", year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false };
const kst = iso => iso ? new Date(iso).toLocaleString("ko-KR", KST) : "";
const day = iso => iso ? new Date(iso).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" }) : "";
const size = n => n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(1) + " KB" : (n / 1048576).toFixed(1) + " MB";
const stampBadge = i => i.tsa_pending ? `<span class="badge wait">공인 시각 대기 중</span>` : `<span class="badge stamp">공인 시각 ${esc(day(i.tsa_time))}</span>`;

async function sha256(buf) {
  const h = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, "0")).join("");
}
function b64(buf) {
  let s = ""; const a = new Uint8Array(buf);
  for (let i = 0; i < a.length; i += 0x8000) s += String.fromCharCode.apply(null, a.subarray(i, i + 0x8000));
  return btoa(s);
}
function dropZone(el, input, onFiles) {
  el.addEventListener("click", () => input.click());
  el.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  el.addEventListener("dragover", e => { e.preventDefault(); el.classList.add("over"); });
  el.addEventListener("dragleave", () => el.classList.remove("over"));
  el.addEventListener("drop", e => { e.preventDefault(); el.classList.remove("over"); onFiles([...e.dataTransfer.files]); });
  input.addEventListener("change", () => { onFiles([...input.files]); input.value = ""; });
}

/* ---------- 상단 상태 ---------- */
async function refreshLedger() {
  try {
    const s = await api("status");
    const el = $("#ledger");
    el.className = "ledger ok";
    el.innerHTML = `<i></i> 기록 ${s.count}건${s.tsa_pending ? ` · 공인 시각 대기 ${s.tsa_pending}건` : ""}`;
  } catch { $("#ledger").textContent = "서버 연결 안 됨"; }
}

/* ---------- 등록 / 개정 ---------- */
const TEMPLATE = "[무엇]  \n[왜]    \n[어떻게] \n[특징]  ";
async function viewNew(parentSeq) {
  let parent = null;
  if (parentSeq) parent = await api("ideas/" + parentSeq);
  const firstRun = !store.get("ib.intro.closed") && !parent;
  const nextV = parent ? Math.max(...parent.lineage.map(x => x.version)) + 1 : 1;
  view.innerHTML = `
    <h1>${parent ? "개정판 등록" : "아이디어 등록"}</h1>
    <p class="lead">${parent ? `<b>${esc(parent.idea_no)}</b> 「${esc(parent.title)}」의 v${nextV} 를 등록합니다. 처음 판은 그대로 남습니다.` : "적고 등록하면 끝입니다. 날짜 증명은 앱이 알아서 합니다."}</p>
    ${firstRun ? `<div class="note amber" id="intro" style="margin-bottom:18px">
      <div class="confirm"><b>처음 오셨나요? 1분 요약</b><button class="x" id="introX" aria-label="안내 닫기">닫기 ✕</button></div>
      <ol class="steps"><li>제목과 내용을 적고 <b>[등록]</b> → 고유 지문과 <b>공인 시각</b>이 자동으로 찍힙니다.</li>
      <li>등록한 내용은 고칠 수도 지울 수도 없습니다. 발전시키려면 <b>개정판</b>을 등록하세요.</li>
      <li><b>보관함</b>에서 확인서와 증명 파일을 받아 다른 곳에도 백업해 두세요.</li></ol>
      <p style="margin:6px 0 0">자세한 내용은 <a href="#help">도움말</a>을 보세요.</p></div>` : ""}
    <div class="grid2">
      <form class="card stack" id="form" novalidate>
        <div class="field"><label for="title">제목<span class="req">*</span></label>
          <input type="text" id="title" maxlength="200" placeholder="한 줄로 핵심을 요약하세요. 예) 자전거 거치대 겸용 우산꽂이" value="${esc(parent?.title || "")}"></div>
        <div class="field"><label for="body">내용<span class="req">*</span></label>
          <span class="hint">무엇을, 왜, 어떻게가 드러나게 적으면 증거로 쓰기 좋습니다. <button type="button" class="x" id="tpl" style="color:var(--focus)">양식 넣기</button></span>
          <textarea id="body">${esc(parent?.body || "")}</textarea></div>
        <div class="row2">
          <div class="field"><label for="author">작성자</label><input type="text" id="author" maxlength="100" placeholder="본인 이름 (팀이면 모두)" value="${esc(parent?.author || store.get("ib.author") || "")}"></div>
          <div class="field"><label for="tags">태그</label><input type="text" id="tags" placeholder="쉼표로 구분. 예) 생활용품, 자전거" value="${esc((parent?.tags || []).join(", "))}"></div>
        </div>
        <div class="field"><span class="lbl">첨부파일</span>
          <div class="drop" id="drop" tabindex="0" role="button">스케치·사진·기획서 등을 끌어다 놓거나 눌러서 고르세요 (파일당 20MB)</div>
          <input type="file" id="file" multiple hidden>
          <ul class="files" id="files"></ul></div>
        <label class="check"><input type="checkbox" id="stamp" checked><span><b>공인 시각 받기</b><br><span class="muted">외부 공인기관이 등록 시각을 보증합니다. 기관에는 고유 지문만 보내고 내용은 보내지 않습니다.</span></span></label>
        <div id="msg"></div>
        <div class="btns"><button class="btn primary" id="submit" type="submit">등록</button>${parent ? `<a class="btn" href="#idea/${parent.seq}">취소</a>` : ""}</div>
      </form>
      <aside class="stack">
        <div class="note"><b>등록하면 고칠 수 없습니다</b><br>그래야 증거가 됩니다. 등록 전에 한 번 더 읽어 보세요. 생각이 완성되지 않았어도 괜찮습니다. <b>일찍 등록할수록 날짜가 앞섭니다.</b></div>
        <div class="note"><b>증명하는 것</b><br>그 시각에 이 내용이 있었고, 그 뒤 바뀌지 않았다는 사실.<br><span class="muted">최초 창안자임이나 독창성은 증명하지 않습니다.</span></div>
      </aside>
    </div>`;
  $("#introX")?.addEventListener("click", () => { store.set("ib.intro.closed", "1"); $("#intro").remove(); });
  $("#tpl").addEventListener("click", () => { const b = $("#body"); if (!b.value.trim()) b.value = TEMPLATE; b.focus(); });

  const files = [];
  const renderFiles = () => {
    $("#files").innerHTML = files.map((f, i) => `<li><span>${esc(f.name)}</span><small class="muted">${size(f.size)}</small><button type="button" class="x" data-i="${i}" aria-label="${esc(f.name)} 빼기">✕</button></li>`).join("");
    $("#files").querySelectorAll("button").forEach(b => b.onclick = () => { files.splice(+b.dataset.i, 1); renderFiles(); });
  };
  dropZone($("#drop"), $("#file"), list => {
    for (const f of list) { if (f.size > 20 * 1048576) toast(`${f.name}: 20MB를 넘어 뺐습니다`); else files.push(f); }
    renderFiles();
  });

  let confirming = false;
  $("#form").addEventListener("submit", async e => {
    e.preventDefault();
    const title = $("#title").value.trim(), body = $("#body").value;
    const msg = $("#msg");
    if (!title || !body.trim() || body.trim() === TEMPLATE.trim()) {
      msg.innerHTML = `<div class="note bad">제목과 내용을 모두 적어 주세요.</div>`;
      (!title ? $("#title") : $("#body")).focus(); return;
    }
    if (!confirming) {
      confirming = true;
      msg.innerHTML = `<div class="note amber confirm"><span><b>이대로 등록할까요?</b> 등록 후에는 고칠 수 없습니다.</span><button type="button" class="x" id="back">다시 볼게요</button></div>`;
      $("#submit").textContent = "등록 확정";
      $("#back").onclick = () => { confirming = false; msg.innerHTML = ""; $("#submit").textContent = "등록"; };
      return;
    }
    const btn = $("#submit"); btn.disabled = true;
    btn.innerHTML = `<span class="spin"></span> ${$("#stamp").checked ? "등록하고 공인 시각 받는 중…" : "등록 중…"}`;
    try {
      const attachments = await Promise.all(files.map(async f => ({ name: f.name, mime: f.type, data_b64: b64(await f.arrayBuffer()) })));
      const author = $("#author").value.trim(); store.set("ib.author", author);
      const d = await api("ideas", { method: "POST", body: {
        title, body, author, tags: $("#tags").value.split(/[,，]/).map(s => s.trim()).filter(Boolean),
        parent_seq: parent ? parent.seq : null, attachments, timestamp: $("#stamp").checked } });
      toast(d.tsa_pending ? `${d.idea_no} 등록 완료 (공인 시각 대기 중)` : `${d.idea_no} 등록 완료`);
      location.hash = `#idea/${d.seq}`;
    } catch (err) {
      msg.innerHTML = `<div class="note bad">${esc(err.message)}</div>`;
      btn.disabled = false; btn.textContent = "등록 확정";
    }
  });
}

/* ---------- 보관함 ---------- */
let listState = { q: "", tag: "" };
async function viewList() {
  view.innerHTML = `<h1>보관함</h1><p class="lead">등록한 아이디어를 찾아보고 확인서를 받으세요.</p>
    <div class="search"><input type="search" id="q" placeholder="제목·내용·태그·등록번호로 찾기" value="${esc(listState.q)}" aria-label="검색"></div>
    <div class="chips" id="chips"></div><div class="list" id="items"><p class="empty">불러오는 중…</p></div>`;
  const tags = await api("tags");
  const drawChips = () => {
    $("#chips").innerHTML = tags.map(t => `<button class="chip${t === listState.tag ? " on" : ""}" data-t="${esc(t)}">#${esc(t)}</button>`).join("");
    $("#chips").querySelectorAll(".chip").forEach(c => c.onclick = () => { listState.tag = listState.tag === c.dataset.t ? "" : c.dataset.t; drawChips(); load(); });
  };
  const load = async () => {
    const items = await api(`ideas?q=${encodeURIComponent(listState.q)}&tag=${encodeURIComponent(listState.tag)}`);
    $("#items").innerHTML = items.length ? items.map(i => `
      <a class="item" href="#idea/${i.seq}">
        <span class="no">${esc(i.idea_no)}${i.version > 1 ? ` · <span class="badge v">v${i.version}</span>` : ""}</span>
        <h3>${esc(i.title)}</h3>
        <span class="meta">${esc(i.author || "작성자 없음")} · ${esc(day(i.created_at))}${i.tags.length ? " · " + i.tags.map(t => "#" + esc(t)).join(" ") : ""}</span>
        <span class="side">${stampBadge(i)}</span>
      </a>`).join("")
      : `<div class="empty">${listState.q || listState.tag ? "찾는 아이디어가 없습니다." : `아직 등록한 아이디어가 없습니다.<br><a class="btn primary" href="#new" style="margin-top:12px">첫 아이디어 등록하기</a>`}</div>`;
  };
  drawChips();
  let t; $("#q").addEventListener("input", e => { clearTimeout(t); t = setTimeout(() => { listState.q = e.target.value.trim(); load(); }, 200); });
  await load();
}

/* ---------- 상세 ---------- */
async function viewIdea(seq) {
  const d = await api("ideas/" + seq);
  view.innerHTML = `
    <p class="muted mono" style="margin:0 0 4px">${esc(d.idea_no)} · v${d.version}</p>
    <h1>${esc(d.title)}</h1>
    <p class="lead">${esc(d.author || "작성자 없음")}${d.tags.length ? " · " + d.tags.map(t => "#" + esc(t)).join(" ") : ""}</p>
    <div class="grid2">
      <div class="stack">
        ${d.tsa_pending ? `<div class="note bad"><b>공인 시각이 아직 없습니다.</b> 아이디어는 안전하게 저장됐습니다. 인터넷 연결을 확인하고 다시 받으세요. 공인 시각은 버튼을 누른 그 시점으로 찍힙니다.
          ${d.tsa_error ? `<br><span class="muted" style="font-size:12.5px">사유: ${esc(d.tsa_error)}</span>` : ""}
          <div class="btns" style="margin-top:10px"><button class="btn amber" id="restamp">공인 시각 다시 받기</button></div></div>` : ""}
        <article class="card"><p class="body-text">${esc(d.body)}</p></article>
        ${d.attachments.length ? `<div class="card"><h2>첨부파일</h2><ul class="files">${d.attachments.map(a => `
          <li><span>${esc(a.name)}</span><small class="muted">${size(a.size)}</small><a class="btn" href="/api/ideas/${d.seq}/files/${a.sha256}">받기</a></li>`).join("")}</ul></div>` : ""}
        <div class="btns">
          <a class="btn primary" href="#cert/${d.seq}">확인서</a>
          <a class="btn" href="/api/ideas/${d.seq}/bundle">증명 파일 내려받기</a>
          <a class="btn" href="#revise/${d.seq}">개정판 등록</a>
        </div>
        <p class="muted" style="font-size:13px;margin:0">분쟁이나 제출이 필요하면 확인서(PDF)와 증명 파일(zip)을 함께 내세요. 증명 파일은 USB·클라우드 등 다른 곳에도 복사해 두세요.</p>
      </div>
      <aside class="stack">
        <div class="card"><dl class="facts">
          <div class="hl"><dt>공인 시각</dt><dd>${d.tsa_time ? `${esc(kst(d.tsa_time))}<br><span class="muted mono">${esc(d.tsa_time)} · ${esc(new URL(d.tsa_url).host)}</span>` : `<span class="badge wait">대기 중</span>`}</dd></div>
          <div><dt>등록 시각</dt><dd>${esc(kst(d.created_at))}</dd></div>
          <div><dt>고유 지문</dt><dd class="mono">${esc(d.content_hash)}</dd></div>
          <div><dt>원장 위치</dt><dd>${d.seq}번째 기록</dd></div>
        </dl></div>
        <div class="card"><h2>개정 이력</h2><ul class="timeline">${d.lineage.map(x => `
          <li class="${x.seq === d.seq ? "cur" : ""}"><a href="#idea/${x.seq}"><span class="v">v${x.version}</span><span>${esc(day(x.created_at))} · ${esc(x.title)}</span></a></li>`).join("")}</ul></div>
      </aside>
    </div>`;
  $("#restamp")?.addEventListener("click", async e => {
    e.target.disabled = true; e.target.innerHTML = `<span class="spin"></span> 받는 중…`;
    try { const r = await api(`ideas/${seq}/timestamp`, { method: "POST" }); toast(r.tsa_pending ? "공인 시각을 받지 못했습니다" : "공인 시각을 받았습니다"); }
    catch (err) { toast(err.message); }
    route(); refreshLedger();
  });
}

/* ---------- 확인서 ---------- */
async function viewCert(seq) {
  const d = await api("ideas/" + seq);
  const today = new Date().toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "long", day: "numeric" });
  view.innerHTML = `
    <div class="cert-tools"><a class="btn" href="#idea/${d.seq}">← 돌아가기</a>
      <div class="btns"><span class="muted" style="align-self:center;font-size:13px">인쇄 창에서 "PDF로 저장"을 고르면 파일로 보관됩니다</span><button class="btn primary" onclick="window.print()">인쇄 / PDF 저장</button></div></div>
    <section class="cert">
      <div class="head"><img src="logo.svg" alt="FirstPrint"><div class="org">아이디어뱅크 by FirstPrint<br>발급일 ${esc(today)}</div></div>
      <h1>아이디어 등록 확인서</h1>
      <p class="sub">${esc(d.idea_no)}</p>
      <table>
        <tr><th>등록번호</th><td>${esc(d.idea_no)} (v${d.version})</td></tr>
        <tr><th>제목</th><td>${esc(d.title)}</td></tr>
        <tr><th>작성자</th><td>${esc(d.author || "-")}</td></tr>
        <tr><th>등록 시각</th><td>${esc(kst(d.created_at))} (한국 시간)</td></tr>
        <tr><th>공인 시각</th><td>${d.tsa_time ? `<span class="stamp">${esc(kst(d.tsa_time))} (한국 시간)</span><br>${esc(d.tsa_time)} UTC · ${esc(new URL(d.tsa_url).host)} (RFC 3161)` : "아직 받지 않음"}</td></tr>
        <tr><th>고유 지문</th><td class="mono">${esc(d.content_hash)}</td></tr>
        <tr><th>원장</th><td>${d.seq}번째 기록 · 고리값 <span class="mono">${esc(d.entry_hash.slice(0, 16))}…</span></td></tr>
        ${d.attachments.length ? `<tr><th>첨부</th><td>${d.attachments.map(a => `${esc(a.name)} <span class="mono" style="color:#646B7E">(${esc(a.sha256.slice(0, 12))}…)</span>`).join("<br>")}</td></tr>` : ""}
      </table>
      <p class="statement">위 아이디어는 ${d.tsa_time ? "공인 시각 인증 기관이 서명한 시각" : "위 등록 시각"}에 아이디어뱅크에 기록되었으며, 그 내용의 고유 지문(SHA-256)은 위와 같습니다. 원문의 고유 지문을 다시 계산해 위 값과 같으면 그 뒤로 내용이 바뀌지 않았음을 확인할 수 있습니다.</p>
      ${d.tsa_time ? `<div class="seal">공인 시각<br>${esc(day(d.tsa_time))}</div>` : ""}
      <p class="limits">이 확인서는 위 시각에 해당 내용이 존재했고 그 뒤 바뀌지 않았다는 사실을 보여 줍니다. 최초 창안자임이나 아이디어의 독창성·가치, 특허와 같은 독점권을 증명하지 않습니다. 법적 증거력은 사안에 따라 다르므로 중요한 사안은 변리사·변호사와 상담하세요. 검증 방법은 증명 파일(zip)의 VERIFY.txt 에 있습니다.</p>
    </section>`;
}

/* ---------- 검증 ---------- */
async function viewVerify() {
  view.innerHTML = `<h1>검증</h1><p class="lead">기록이 바뀌지 않았는지, 언제 등록됐는지 확인합니다.</p>
    <div class="verify-grid">
      <section class="card stack"><div><h2>보관함 전체 점검</h2><p class="muted" style="margin:0">저장된 기록이 몰래 바뀌거나 지워지지 않았는지 확인합니다.</p></div>
        <div><button class="btn primary" id="chainBtn">전체 점검</button></div><div id="chainOut"></div></section>
      <section class="card stack"><div><h2>증명 파일 검증</h2><p class="muted" style="margin:0">누군가 제출한 증명 파일(zip)이 진짜인지 확인합니다.</p></div>
        <div class="drop" id="zipDrop" tabindex="0" role="button">증명 파일(.zip)을 끌어다 놓거나 눌러서 고르세요</div><input type="file" id="zipIn" accept=".zip" hidden><div id="zipOut"></div></section>
      <section class="card stack"><div><h2>파일로 등록일 찾기</h2><p class="muted" style="margin:0">파일을 서버로 보내지 않고, 브라우저에서 고유 지문만 계산해 찾습니다.</p></div>
        <div class="drop" id="fDrop" tabindex="0" role="button">파일을 끌어다 놓거나 눌러서 고르세요</div><input type="file" id="fIn" hidden><div id="fOut"></div></section>
    </div>`;
  $("#chainBtn").onclick = async () => {
    const out = $("#chainOut"); out.innerHTML = `<span class="spin"></span>`;
    try {
      const r = await api("verify/chain");
      out.innerHTML = r.ok
        ? `<div class="note ok"><b>정상</b> — 기록 ${r.count}건 모두 바뀌지 않았습니다.<br><span class="muted mono" style="font-size:12px">원장 끝 고리값 ${esc(r.head)}</span></div>`
        : `<div class="note bad"><b>이상 발견</b> — ${r.broken.length}건<ul class="results">${r.broken.map(b => `<li class="bad"><span class="ic">✕</span><span><b>${esc(b.idea_no)}</b><br>${b.problems.map(esc).join("<br>")}</span></li>`).join("")}</ul></div>`;
      refreshLedger();
    } catch (e) { out.innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
  };
  dropZone($("#zipDrop"), $("#zipIn"), async ([f]) => {
    if (!f) return;
    const out = $("#zipOut"); out.innerHTML = `<span class="spin"></span>`;
    try {
      const r = await api("verify/bundle", { method: "POST", body: { zip_b64: b64(await f.arrayBuffer()) } });
      out.innerHTML = `<div class="note ${r.ok ? "ok" : "bad"}"><b>${r.ok ? "진짜입니다" : "확인되지 않았습니다"}</b> — ${esc(r.title || "")}
        <ul class="results">${r.checks.map(c => `<li class="${c.ok ? "ok" : "bad"}"><span class="ic">${c.ok ? "✓" : "✕"}</span><span><b>${esc(c.name)}</b> ${esc(c.detail)}</span></li>`).join("")}</ul>
        <p class="mono muted" style="margin:8px 0 0;font-size:12px">${esc(r.content_hash)}</p></div>`;
    } catch (e) { out.innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
  });
  dropZone($("#fDrop"), $("#fIn"), async ([f]) => {
    if (!f) return;
    const out = $("#fOut"); out.innerHTML = `<span class="spin"></span>`;
    try {
      const h = await sha256(await f.arrayBuffer());
      const r = await api("lookup/" + h);
      const hits = [...r.ideas.map(i => ({ ...i, what: "원문" })), ...r.files.map(i => ({ ...i, what: `첨부 '${i.name}'` }))];
      out.innerHTML = hits.length
        ? `<div class="note ok"><b>등록된 파일입니다</b><ul class="results">${hits.map(i => `<li class="ok"><span class="ic">✓</span><span><a href="#idea/${i.seq}"><b>${esc(i.idea_no)}</b></a> ${esc(i.title)}<br>${esc(i.what)} · ${i.tsa_time ? "공인 시각 " + esc(kst(i.tsa_time)) : "등록 " + esc(kst(i.created_at))}</span></li>`).join("")}</ul></div>`
        : `<div class="note"><b>이 보관함에 없는 파일입니다.</b><br>내용이 한 글자라도 다르면 다른 파일로 봅니다.</div>`;
      out.insertAdjacentHTML("beforeend", `<p class="mono muted" style="font-size:12px;margin:8px 0 0">${esc(f.name)}: ${h}</p>`);
    } catch (e) { out.innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
  });
}

/* ---------- 도움말 (docs/USER_GUIDE.md 를 그대로 보여 줌) ---------- */
function md(src) {
  const inline = s => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, t, u) => /^https?:/.test(u) ? `<a href="${u}" target="_blank" rel="noopener">${t}</a>` : t);
  const lines = src.replace(/\r/g, "").split("\n"); let out = "", i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (l.startsWith("```")) { const buf = []; i++; while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]); i++; out += `<pre>${esc(buf.join("\n"))}</pre>`; continue; }
    const h = l.match(/^(#{1,3})\s+(.*)/); if (h) { out += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`; i++; continue; }
    if (/^---+\s*$/.test(l)) { out += "<hr>"; i++; continue; }
    if (l.startsWith("|")) {
      const rows = []; while (i < lines.length && lines[i].startsWith("|")) rows.push(lines[i++]);
      const cells = r => r.replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      out += `<div class="tbl"><table><tr>${cells(rows[0]).map(c => `<th>${inline(c)}</th>`).join("")}</tr>${rows.slice(2).map(r => `<tr>${cells(r).map(c => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</table></div>`; continue;
    }
    if (l.startsWith(">")) { const buf = []; while (i < lines.length && lines[i].startsWith(">")) buf.push(lines[i++].replace(/^>\s?/, "")); out += `<blockquote>${buf.filter(Boolean).map(b => `<p>${inline(b)}</p>`).join("")}</blockquote>`; continue; }
    if (/^\s*([-*]|\d+\.)\s/.test(l)) {
      const ord = /^\s*\d+\./.test(l); const buf = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s/.test(lines[i])) buf.push(lines[i++].replace(/^\s*([-*]|\d+\.)\s/, ""));
      out += `<${ord ? "ol" : "ul"}>${buf.map(b => `<li>${inline(b)}</li>`).join("")}</${ord ? "ol" : "ul"}>`; continue;
    }
    if (l.trim()) { const buf = []; while (i < lines.length && lines[i].trim() && !/^(#|\||>|```|\s*[-*]\s|\s*\d+\.\s|---)/.test(lines[i])) buf.push(lines[i++]); out += `<p>${buf.map(inline).join("<br>")}</p>`; continue; }
    i++;
  }
  return out;
}
async function viewHelp() {
  const src = await api("guide");
  view.innerHTML = `<article class="doc">${md(src)}</article>`;
}

/* ---------- 라우터 ---------- */
async function route() {
  const [name, arg] = (location.hash.slice(1) || "new").split("/");
  document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("on",
    a.dataset.nav === ({ idea: "list", cert: "list", revise: "new" }[name] || name)));
  try {
    if (name === "new") await viewNew();
    else if (name === "revise") await viewNew(+arg);
    else if (name === "list") await viewList();
    else if (name === "idea") await viewIdea(+arg);
    else if (name === "cert") await viewCert(+arg);
    else if (name === "verify") await viewVerify();
    else if (name === "help") await viewHelp();
    else location.hash = "#new";
  } catch (e) {
    view.innerHTML = `<div class="note bad"><b>화면을 열지 못했습니다.</b> ${esc(e.message)}<br><a href="#list">보관함으로</a></div>`;
  }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", () => { route(); refreshLedger(); });
route(); refreshLedger();
