"""하나의 해시 체인 이벤트 원장 (TRD §10).

- 모든 이벤트(아이디어 등록, 열람, NDA 서명, 대출 신청·심사, 계약, 정산, 공개 단계 변경)를 같은 체인에 기록한다.
- content_hash = sha256(payload), entry_hash = sha256(prev:seq:content_hash)  ← v1 과 같은 규칙 (ideabank.canonical)
- 아이디어 등록 이벤트의 payload 는 v1 과 똑같은 ideabank/1 정규화 JSON 이다.
  → 아이디어의 고유 지문 = 그 등록 이벤트의 content_hash, 증명 파일도 v1 형식과 호환된다.
- 공인 시각(RFC 3161)은 content_hash 에 받는다. 외부로는 해시 32바이트만 나간다.
"""
from __future__ import annotations

import json
import threading
import time

from ideabank import canonical as C
from ideabank import tsa

from .db import DATA_DIR, DB

EVENT_SCHEMA = "ideabank-event/1"
MAX_TRIES = 8

KIND_LABEL = {
    "idea.register": "아이디어 등록",
    "idea.disclosure": "공개 단계 변경",
    "idea.hide": "공개 목록 숨김",
    "idea.unhide": "공개 목록 다시 표시",
    "view.summary": "요약 열람",
    "view.full": "전문 열람",
    "view.file": "첨부 열람",
    "nda.sign": "NDA 서명",
    "loan.request": "대출 신청",
    "loan.creator_response": "창안자 응답",
    "loan.review": "대출 심사",
    "contract.create": "계약 체결 기록",
    "settlement.create": "정산 기록",
}


def event_payload(kind: str, **fields) -> bytes:
    doc = {"schema": EVENT_SCHEMA, "kind": kind, "at": C.now_iso(), **fields}
    return C.dumps(doc)


def append(conn, kind: str, payload: bytes, actor: str, idea_seq: int | None = None) -> dict:
    """반드시 db.tx() 안에서 호출. 원장에 이벤트 1건을 추가하고 seq 를 돌려준다."""
    last = conn.execute("SELECT seq, entry_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
    seq = (last["seq"] + 1) if last else 1
    prev = last["entry_hash"] if last else C.GENESIS
    ch = C.sha256_hex(payload)
    eh = C.entry_hash(prev, seq, ch)
    conn.execute(
        "INSERT INTO events (seq, kind, idea_seq, actor, payload, content_hash, prev_hash, entry_hash, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (seq, kind, idea_seq, actor, payload, ch, prev, eh, C.now_iso()),
    )
    return {"seq": seq, "content_hash": ch, "entry_hash": eh, "prev_hash": prev}


class Stamper:
    """공인 시각 받기. 등록은 즉시(동기) 시도하고, 나머지는 백그라운드 작업자가 처리한다."""

    def __init__(self, db: DB, urls: list[str]):
        self.db = db
        self.urls = urls
        self.wake = threading.Event()
        self._lock = threading.Lock()

    def stamp(self, seq: int) -> dict:
        r = self.db.one("SELECT content_hash, tsa_token FROM events WHERE seq=?", (seq,))
        if not r:
            raise KeyError(seq)
        if r["tsa_token"]:
            return {"ok": True, "already": True}
        try:
            out = tsa.stamp_any(r["content_hash"], self.urls)
        except Exception as ex:
            self.db.exec("UPDATE events SET tsa_error=?, tsa_tries=tsa_tries+1 WHERE seq=?", (str(ex)[:500], seq))
            return {"ok": False, "error": str(ex)}
        # TimeStampResp 원본을 보관 → openssl ts -reply 로 바로 검증 가능 (v1 과 동일)
        self.db.exec("UPDATE events SET tsa_url=?, tsa_time=?, tsa_token=?, tsa_error=NULL WHERE seq=? AND tsa_token IS NULL",
                      (out["url"], out["gen_time"], out["response"], seq))
        return {"ok": True, "tsa_time": out["gen_time"], "tsa_url": out["url"]}

    def pending(self, limit=20, max_tries=MAX_TRIES) -> list[int]:
        return [r[0] for r in self.db.q(
            "SELECT seq FROM events WHERE tsa_token IS NULL AND tsa_tries < ? ORDER BY seq LIMIT ?", (max_tries, limit))]

    def run_pending(self, max_tries=MAX_TRIES) -> dict:
        with self._lock:
            done = fail = 0
            for seq in self.pending(50, max_tries):
                if self.stamp(seq)["ok"]:
                    done += 1
                else:
                    fail += 1
            return {"stamped": done, "failed": fail}

    def start_worker(self):
        def loop():
            while True:
                self.wake.wait(timeout=20)
                self.wake.clear()
                time.sleep(0.3)  # 같은 요청에서 생긴 이벤트를 모아 처리
                try:
                    self.run_pending()
                except Exception as ex:  # 작업자는 죽지 않는다
                    print("[공인 시각 작업자] 오류:", ex)
        threading.Thread(target=loop, name="tsa-worker", daemon=True).start()
        self.wake.set()


def verify_chain(db: DB) -> dict:
    """원장 전체 검사 (TRD §7 을 이벤트 원장으로 일반화)."""
    broken = []
    prev = C.GENESIS
    expected = 1
    count = pending = 0
    ideas = {r["event_seq"]: r for r in db.q("SELECT * FROM ideas")}
    for r in db.q("SELECT * FROM events ORDER BY seq"):
        count += 1
        seq = r["seq"]
        if seq != expected:
            broken.append({"seq": seq, "reason": f"순번이 비어 있음 ({expected}번 기록이 없음)"})
            expected = seq
        payload = bytes(r["payload"])
        if C.sha256_hex(payload) != r["content_hash"]:
            broken.append({"seq": seq, "reason": "기록 내용이 바뀜 (고유 지문 불일치)"})
        if r["prev_hash"] != prev:
            broken.append({"seq": seq, "reason": "앞 고리값이 직전 기록과 다름"})
        if C.entry_hash(r["prev_hash"], seq, r["content_hash"]) != r["entry_hash"]:
            broken.append({"seq": seq, "reason": "고리값 계산 불일치"})
        if r["kind"] == "idea.register":
            idea = ideas.get(seq)
            if not idea:
                broken.append({"seq": seq, "reason": "등록 이벤트에 해당하는 아이디어가 없음"})
            else:
                if bytes(idea["canonical"]) != payload or idea["content_hash"] != r["content_hash"]:
                    broken.append({"seq": seq, "reason": f"{idea['idea_no']} 원문이 원장과 다름"})
                doc = json.loads(payload)
                for a in doc.get("attachments", []):
                    p = DATA_DIR / "files" / a["sha256"]
                    if not p.exists() or C.sha256_hex(p.read_bytes()) != a["sha256"]:
                        broken.append({"seq": seq, "reason": f"첨부 '{a['name']}' 파일이 없거나 바뀜"})
        if r["tsa_token"]:
            try:
                tsa.token_time(bytes(r["tsa_token"]), bytes.fromhex(r["content_hash"]))
            except Exception:
                broken.append({"seq": seq, "reason": "공인 시각 서명의 고유 지문이 기록과 다름"})
        else:
            pending += 1
        prev = r["entry_hash"]
        expected += 1
    return {"ok": not broken, "count": count, "head": prev, "pending": pending, "broken": broken, "checked_at": C.now_iso()}


def event_public(r) -> dict:
    return {
        "seq": r["seq"], "kind": r["kind"], "kind_label": KIND_LABEL.get(r["kind"], r["kind"]),
        "content_hash": r["content_hash"], "entry_hash": r["entry_hash"], "prev_hash": r["prev_hash"],
        "created_at": r["created_at"], "tsa_time": r["tsa_time"], "tsa_url": r["tsa_url"],
        "tsa_pending": r["tsa_token"] is None, "tsa_error": r["tsa_error"],
    }
