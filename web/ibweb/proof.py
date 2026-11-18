"""증명 파일(zip) 만들기·검증하기 — v1(ideabank.bundle)과 같은 형식.

v1 의 bundle.make 는 로컬 Store 객체에 묶여 있어 그대로 쓸 수 없으므로, 같은 zip 구조를 만드는 얇은 어댑터를 둔다.
- 안내문(VERIFY.txt) 문구는 ideabank.bundle.GUIDE 를 그대로 가져다 쓴다.
- 검증은 ideabank.bundle.verify 를 그대로 호출한다. (이 DB 에도 v1 과 같은 ideas(seq, idea_no, content_hash) 열이 있다)
자세한 이유: web/NOTES_FOR_CORE.md
"""
from __future__ import annotations

import io
import json
import zipfile
from types import SimpleNamespace

from ideabank import bundle as core_bundle

from . import files as F


def make(db, idea: dict) -> tuple[str, bytes]:
    ev = db.one("SELECT * FROM events WHERE seq=?", (idea["event_seq"],))
    d = {**idea, "seq": ev["seq"], "prev_hash": ev["prev_hash"], "entry_hash": ev["entry_hash"],
         "tsa_time": ev["tsa_time"] or "(아직 없음)", "tsa_url": ev["tsa_url"] or "-"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("canonical.json", bytes(idea["canonical"]))
        md = (f"# {d['idea_no']} — {d['title']}\n\n- 작성자: {d['author'] or '-'}\n- 태그: {', '.join(d['tags']) or '-'}\n"
              f"- 등록 시각(UTC): {d['created_at']}\n- 판: v{d['version']}\n\n## 내용\n\n{d['body']}\n")
        z.writestr("idea.md", md.encode("utf-8"))
        used = set()
        for a in idea["attachments"]:
            name = a["name"]
            while name in used:
                name = "_" + name
            used.add(name)
            z.writestr(f"attachments/{name}", F.get(a["sha256"]))
        if ev["tsa_token"]:
            z.writestr("token.tsr", bytes(ev["tsa_token"]))
        z.writestr("ledger.json", json.dumps({
            "ledger": "아이디어뱅크 온라인 이벤트 원장", "seq": ev["seq"], "idea_no": d["idea_no"],
            "prev_hash": ev["prev_hash"], "entry_hash": ev["entry_hash"], "content_hash": ev["content_hash"],
        }, ensure_ascii=False, indent=2).encode("utf-8"))
        z.writestr("VERIFY.txt", core_bundle.GUIDE.format(**d).encode("utf-8"))
    return f"{d['idea_no']}-증명.zip", buf.getvalue()


def verify(db, data: bytes) -> dict:
    """v1 bundle.verify 를 그대로 사용. Store 대신 .db 속성만 가진 어댑터를 넘긴다."""
    with db.lock:  # SQLite 연결 또는 Postgres 어댑터 (둘 다 .execute(sql, args).fetchone())
        out = core_bundle.verify(SimpleNamespace(db=db.conn), data)
    for c in out["checks"]:
        if c["name"] == "이 보관함 원장":
            c["name"] = "아이디어뱅크 원장"
            if not c["ok"]:
                c["detail"] = "아이디어뱅크 온라인 원장에는 없음 (개인 보관함 v1 등 다른 원장의 기록일 수 있음)"
    return out
