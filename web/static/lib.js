// 공용 도우미 — 사용자 앱과 관리자 앱이 함께 쓴다.
"use strict";

// 비밀번호 칸 오른쪽에 "눈" 버튼: 눌러서 입력한 비밀번호를 보이기/가리기. 화면이 새로 그려질 때마다 자동으로 붙는다.
const EYE = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
const EYE_OFF = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.9 17.9A10.4 10.4 0 0 1 12 19c-6.4 0-10-7-10-7a18.5 18.5 0 0 1 5.1-5.9M9.9 5.2A9.7 9.7 0 0 1 12 5c6.4 0 10 7 10 7a18.6 18.6 0 0 1-2.2 3.2M14.1 14.1a3 3 0 1 1-4.2-4.2"/><path d="M2 2l20 20"/></svg>';
function addPasswordToggles(root = document) {
  root.querySelectorAll('input[type="password"]:not([data-eye])').forEach((inp) => {
    inp.dataset.eye = "1";
    const box = document.createElement("div");
    box.className = "pw-box";
    inp.replaceWith(box);
    box.append(inp);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pw-eye";
    const sync = () => {
      const shown = inp.type === "text";
      btn.innerHTML = shown ? EYE_OFF : EYE;
      btn.setAttribute("aria-label", shown ? "비밀번호 가리기" : "비밀번호 보기");
      btn.setAttribute("aria-pressed", String(shown));
      btn.title = shown ? "비밀번호 가리기" : "비밀번호 보기";
    };
    btn.onclick = () => { inp.type = inp.type === "password" ? "text" : "password"; sync(); inp.focus(); };
    // 제출할 때는 다시 가려 둔다 (브라우저 자동 저장·화면 노출 방지)
    if (inp.form) inp.form.addEventListener("submit", () => { inp.type = "password"; sync(); });
    sync();
    box.append(btn);
  });
}
new MutationObserver(() => addPasswordToggles()).observe(document.documentElement, { childList: true, subtree: true });
document.addEventListener("DOMContentLoaded", () => addPasswordToggles());
const IB = (() => {
  let csrf = null;
  const setCsrf = (t) => { csrf = t; };

  async function api(method, path, body) {
    const opt = { method, headers: {}, credentials: "same-origin" };
    if (method !== "GET") {
      opt.headers["Content-Type"] = "application/json";
      if (csrf) opt.headers["X-CSRF-Token"] = csrf;
      opt.body = JSON.stringify(body || {});
    }
    const r = await fetch(path, opt);
    const ct = r.headers.get("Content-Type") || "";
    const data = ct.includes("json") ? await r.json() : await r.blob();
    if (!r.ok) {
      const e = new Error((data && data.error) || `요청 실패 (${r.status})`);
      e.status = r.status;
      throw e;
    }
    if (data && data.csrf) csrf = data.csrf;
    return data;
  }

  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
  // 태그드 템플릿: 값은 자동 이스케이프, raw() 로 감싼 값만 그대로
  class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
  const raw = (s) => new Raw(s);
  function html(strings, ...vals) {
    let out = "";
    strings.forEach((s, i) => {
      out += s;
      if (i < vals.length) {
        const v = vals[i];
        if (v instanceof Raw) out += v.s;
        else if (Array.isArray(v)) out += v.map((x) => (x instanceof Raw ? x.s : esc(x))).join("");
        else if (v === null || v === undefined || v === false) out += "";
        else out += esc(v);
      }
    });
    return raw(out);
  }

  // 시각: 서버는 UTC ISO. 화면에는 한국 시간으로.
  function kst(iso, withSec = true) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    const k = new Date(d.getTime() + 9 * 3600e3);
    const p = (n) => String(n).padStart(2, "0");
    let s = `${k.getUTCFullYear()}-${p(k.getUTCMonth() + 1)}-${p(k.getUTCDate())} ${p(k.getUTCHours())}:${p(k.getUTCMinutes())}`;
    if (withSec) s += `:${p(k.getUTCSeconds())}`;
    return s;
  }
  const kstFull = (iso) => (iso ? `${kst(iso)} (한국 시간)` : "");
  const won = (n) => Number(n || 0).toLocaleString("ko-KR") + "원";

  function stampBadge(tsaTime) {
    return tsaTime
      ? html`<span class="badge stamp" title="공인 시각">공인 시각 ${kst(tsaTime, false)}</span>`
      : html`<span class="badge wait">공인 시각 대기</span>`;
  }

  let toastTimer;
  function toast(msg, bad = false) {
    let t = document.querySelector(".toast");
    if (!t) { t = document.createElement("div"); t.className = "toast"; t.setAttribute("role", "status"); document.body.append(t); }
    t.textContent = msg;
    t.classList.toggle("bad", bad);
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
  }

  function formData(form) {
    const o = {};
    new FormData(form).forEach((v, k) => { o[k] = typeof v === "string" ? v : v; });
    return o;
  }

  async function sha256Hex(buf) {
    const h = await crypto.subtle.digest("SHA-256", buf);
    return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  function b64(buf) {
    const bytes = new Uint8Array(buf);
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(s);
  }

  async function download(path) {
    const r = await fetch(path, { credentials: "same-origin" });
    if (!r.ok) {
      let msg = `내려받기 실패 (${r.status})`;
      try { msg = (await r.json()).error || msg; } catch (_) {}
      throw new Error(msg);
    }
    // 온라인 큰 파일: 서버가 Storage 서명 주소(5분)를 주면 브라우저가 그 주소에서 바로 받는다
    if ((r.headers.get("Content-Type") || "").includes("json")) {
      const j = await r.json();
      if (!j.download_url) throw new Error("내려받을 주소를 받지 못했습니다.");
      const a = document.createElement("a");
      a.href = j.download_url; a.rel = "noopener"; document.body.append(a); a.click(); a.remove();
      return;
    }
    const cd = r.headers.get("Content-Disposition") || "";
    const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
    const name = m ? decodeURIComponent(m[1]) : "download";
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url; a.download = name; document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  // 버튼을 누르는 동안 잠그고, 오류는 토스트로
  async function busy(btn, fn) {
    const old = btn ? btn.innerHTML : "";
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 처리 중'; }
    try { return await fn(); }
    catch (e) { toast(e.message, true); throw e; }
    finally { if (btn) { btn.disabled = false; btn.innerHTML = old; } }
  }

  return { api, setCsrf, esc, html, raw, kst, kstFull, won, stampBadge, toast, formData, sha256Hex, b64, download, busy };
})();
