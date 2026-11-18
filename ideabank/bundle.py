"""증명 파일(zip) 만들기와 검증하기 (PRD F8, F10)."""
from __future__ import annotations

import io
import json
import zipfile

from . import canonical as C
from . import tsa
from .store import Store, UserError

GUIDE = """아이디어뱅크 증명 파일
=====================

등록번호      {idea_no}
제목          {title}
작성자        {author}
등록 시각     {created_at} (UTC)
고유 지문     {content_hash}
공인 시각     {tsa_time}
시각 기관     {tsa_url}
원장 위치     {seq}번째 기록 (앞 고리 {prev_hash})
원장 고리값   {entry_hash}

들어 있는 파일
  canonical.json   증명 대상 원문 (이 파일의 SHA-256 = 고유 지문)
  idea.md          사람이 읽기 위한 사본
  attachments/     첨부파일 원본
  token.tsr        공인 시각 기관의 전자 서명 (RFC 3161)
  ledger.json      원장 고리 정보

이 앱 없이 직접 검증하는 방법
  1) 고유 지문 확인
       Windows : certutil -hashfile canonical.json SHA256
       macOS   : shasum -a 256 canonical.json
       Linux   : sha256sum canonical.json
     → 위 고유 지문과 같아야 합니다. 한 글자라도 바뀌면 완전히 다른 값이 나옵니다.
  2) 첨부파일 확인: 각 파일의 SHA-256 이 canonical.json 의 attachments 값과 같아야 합니다.
  3) 공인 시각 확인 (OpenSSL)
       openssl ts -reply -in token.tsr -text
     → "Message data" 가 고유 지문과 같고, "Time stamp" 가 공인 시각입니다.
  4) 서명 검증 (시각 기관의 루트 인증서 필요)
       openssl ts -verify -digest {content_hash} -in token.tsr -CAfile <기관_루트인증서.pem>

알아 두세요
  이 증명은 "위 시각에 이 내용이 존재했고, 그 뒤 바뀌지 않았다"는 사실을 보여 줍니다.
  최초 창안자임이나 아이디어의 독창성을 증명하지는 않습니다.
"""


def make(store: Store, seq: int) -> tuple[str, bytes]:
    d = store.get(seq)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("canonical.json", d["canonical"].encode("utf-8"))
        md = f"# {d['idea_no']} — {d['title']}\n\n- 작성자: {d['author'] or '-'}\n- 태그: {', '.join(d['tags']) or '-'}\n" \
             f"- 등록 시각(UTC): {d['created_at']}\n- 판: v{d['version']}\n\n## 내용\n\n{d['body']}\n"
        z.writestr("idea.md", md.encode("utf-8"))
        used = set()
        for a in d["attachments"]:
            name = a["name"]
            while name in used:
                name = "_" + name
            used.add(name)
            path, _ = store.file_path(seq, a["sha256"])
            z.writestr(f"attachments/{name}", path.read_bytes())
        row = store.db.execute("SELECT tsa_token FROM ideas WHERE seq=?", (seq,)).fetchone()
        if row["tsa_token"]:
            z.writestr("token.tsr", bytes(row["tsa_token"]))
        z.writestr("ledger.json", json.dumps({k: d[k] for k in ("seq", "idea_no", "prev_hash", "entry_hash", "content_hash")},
                                             ensure_ascii=False, indent=2).encode("utf-8"))
        z.writestr("VERIFY.txt", GUIDE.format(**{**d, "tsa_time": d["tsa_time"] or "(아직 없음)",
                                                  "tsa_url": d["tsa_url"] or "-"}).encode("utf-8"))
    return f"{d['idea_no']}-증명.zip", buf.getvalue()


def verify(store: Store, data: bytes) -> dict:
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UserError("zip 파일이 아닙니다. 아이디어뱅크에서 내려받은 증명 파일을 올려 주세요.")
    names = set(z.namelist())
    if "canonical.json" not in names:
        raise UserError("증명 파일 안에 canonical.json 이 없습니다.")
    raw = z.read("canonical.json")
    ch = C.sha256_hex(raw)
    try:
        doc = json.loads(raw)
    except ValueError:
        raise UserError("canonical.json 을 읽을 수 없습니다.")
    add("원문 형식", C.dumps(doc) == raw, "정규화 형식과 일치" if C.dumps(doc) == raw else "정규화 형식이 아닙니다 (다시 저장되었거나 편집됨)")

    for a in doc.get("attachments", []):
        cands = [n for n in names if n.startswith("attachments/") and n[len("attachments/"):].lstrip("_") == a["name"].lstrip("_")]
        hit = any(C.sha256_hex(z.read(n)) == a["sha256"] for n in cands)
        add(f"첨부 '{a['name']}'", hit, "원본과 일치" if hit else "없거나 바뀌었습니다")

    if "token.tsr" in names:
        try:
            t = tsa.token_time(z.read("token.tsr"), bytes.fromhex(ch))
            add("공인 시각", True, f"{t} (UTC) — 이 원문의 고유 지문에 서명됨")
        except Exception:
            add("공인 시각", False, "서명된 고유 지문이 이 원문과 다릅니다")
    else:
        add("공인 시각", False, "증명 파일에 공인 시각이 없습니다")

    row = store.db.execute("SELECT seq, idea_no FROM ideas WHERE content_hash=?", (ch,)).fetchone()
    add("이 보관함 원장", bool(row), f"{row['idea_no']} 으로 등록되어 있음" if row else "이 컴퓨터의 원장에는 없음 (다른 보관함의 기록일 수 있음)")

    core_ok = all(c["ok"] for c in checks if c["name"] != "이 보관함 원장")
    return {"ok": core_ok, "content_hash": ch, "title": doc.get("title"), "created_at": doc.get("created_at"),
            "author": doc.get("author"), "checks": checks}
