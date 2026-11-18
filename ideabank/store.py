"""저장소·원장 (TRD §4, §7).

- ideas 테이블은 추가 전용(append-only). 수정·삭제 함수는 일부러 만들지 않는다.
- 각 항목은 직전 항목의 entry_hash 를 물고 있어, 중간 변조·삭제가 생기면 체인이 끊긴다.
- tsa_token 에는 TSA 응답(TimeStampResp) 원본을 그대로 보관한다 → openssl ts -reply 로 바로 검증 가능.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import canonical as C
from . import tsa

MAX_FILE = 20 * 1024 * 1024
HEX64 = re.compile(r"^[0-9a-f]{64}$")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ideas (
  seq          INTEGER PRIMARY KEY,
  idea_no      TEXT UNIQUE NOT NULL,
  parent_seq   INTEGER,
  root_seq     INTEGER NOT NULL,
  version      INTEGER NOT NULL,
  title        TEXT NOT NULL,
  body         TEXT NOT NULL,
  tags         TEXT NOT NULL,
  author       TEXT NOT NULL,
  canonical    BLOB NOT NULL,
  content_hash TEXT NOT NULL,
  prev_hash    TEXT NOT NULL,
  entry_hash   TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  tsa_url      TEXT,
  tsa_time     TEXT,
  tsa_token    BLOB,
  tsa_error    TEXT
);
CREATE TABLE IF NOT EXISTS attachments (
  seq    INTEGER NOT NULL,
  name   TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size   INTEGER NOT NULL,
  mime   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_att_sha ON attachments(sha256);
CREATE INDEX IF NOT EXISTS ix_ideas_hash ON ideas(content_hash);
"""


class UserError(ValueError):
    """사용자에게 그대로 보여 줄 수 있는 오류."""


def safe_name(name: str) -> str:
    name = C.text(name).replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r'[\x00-\x1f<>:"|?*]', "_", name)
    return (name or "file")[:120]


class Store:
    def __init__(self, data_dir: str | Path, tsa_urls: list[str] | None = None, tz_hours: int = 9):
        self.dir = Path(data_dir)
        self.files = self.dir / "files"
        self.files.mkdir(parents=True, exist_ok=True)
        self.tsa_urls = tsa_urls or []
        self.tz = timezone(timedelta(hours=tz_hours))
        self.lock = threading.Lock()
        self.db = sqlite3.connect(self.dir / "ideabank.db", check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA_SQL)

    # ---------- 등록 ----------
    def _save_file(self, data: bytes) -> str:
        h = C.sha256_hex(data)
        p = self.files / h
        if not p.exists():
            p.write_bytes(data)
        return h

    def _idea_no(self, created_at: str, seq: int) -> str:
        d = datetime.strptime(created_at[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return f"IB-{d.astimezone(self.tz):%Y%m%d}-{seq:06d}"

    def create(self, *, title, body, tags=(), author="", parent_seq=None, attachments=(), timestamp=True) -> dict:
        if not C.text(title).strip():
            raise UserError("제목을 적어 주세요.")
        if not C.text(body).strip():
            raise UserError("내용을 적어 주세요.")
        atts = []
        for a in attachments:
            data = a["data"]
            if len(data) > MAX_FILE:
                raise UserError(f"첨부파일 '{a['name']}' 이(가) 20MB 를 넘습니다.")
            atts.append({"name": safe_name(a["name"]), "mime": a.get("mime") or "application/octet-stream",
                         "sha256": self._save_file(data), "size": len(data)})

        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                parent_hash, root_seq, version = None, None, 1
                if parent_seq is not None:
                    p = self.db.execute("SELECT seq, root_seq, content_hash FROM ideas WHERE seq=?", (parent_seq,)).fetchone()
                    if not p:
                        raise UserError("개정할 원본 아이디어를 찾을 수 없습니다.")
                    parent_hash, root_seq = p["content_hash"], p["root_seq"]
                    version = self.db.execute("SELECT MAX(version) FROM ideas WHERE root_seq=?", (root_seq,)).fetchone()[0] + 1
                last = self.db.execute("SELECT seq, entry_hash FROM ideas ORDER BY seq DESC LIMIT 1").fetchone()
                seq = (last["seq"] + 1) if last else 1
                prev = last["entry_hash"] if last else C.GENESIS
                created = C.now_iso()
                doc = C.build(title=title, body=body, tags=tags, author=author, created_at=created,
                              parent=parent_hash, attachments=atts)
                raw = C.dumps(doc)
                ch = C.sha256_hex(raw)
                self._insert(seq, doc, raw, ch, prev, parent_seq, root_seq or seq, version, atts)
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        if timestamp and self.tsa_urls:
            self.stamp(seq)
        return self.get(seq)

    def _insert(self, seq, doc, raw, ch, prev, parent_seq, root_seq, version, atts, idea_no=None):
        self.db.execute(
            "INSERT INTO ideas (seq, idea_no, parent_seq, root_seq, version, title, body, tags, author, canonical,"
            " content_hash, prev_hash, entry_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (seq, idea_no or self._idea_no(doc["created_at"], seq), parent_seq, root_seq, version, doc["title"],
             doc["body"], json.dumps(doc["tags"], ensure_ascii=False), doc["author"], raw, ch, prev,
             C.entry_hash(prev, seq, ch), doc["created_at"]))
        for a in atts:
            self.db.execute("INSERT INTO attachments (seq, name, sha256, size, mime) VALUES (?,?,?,?,?)",
                            (seq, a["name"], a["sha256"], a["size"], a.get("mime") or "application/octet-stream"))

    def import_record(self, raw: bytes, tsa_response: bytes | None, idea_no: str, tsa_url: str | None = None) -> dict:
        """이미 해시·공인 시각을 받은 기록(첨부 없는 원본)을 원장 맨 앞에 옮겨 담는다."""
        doc = json.loads(raw)
        ch = C.sha256_hex(raw)
        if C.dumps(doc) != raw:
            raise UserError("정규화 형식이 아닌 기록은 가져올 수 없습니다.")
        if doc.get("attachments") or doc.get("parent"):
            raise UserError("첨부·개정판이 있는 기록은 가져올 수 없습니다.")
        with self.lock:
            if self.db.execute("SELECT 1 FROM ideas WHERE content_hash=?", (ch,)).fetchone():
                raise UserError("이미 원장에 있는 기록입니다.")
            last = self.db.execute("SELECT seq, entry_hash FROM ideas ORDER BY seq DESC LIMIT 1").fetchone()
            seq = (last["seq"] + 1) if last else 1
            prev = last["entry_hash"] if last else C.GENESIS
            self.db.execute("BEGIN IMMEDIATE")
            self._insert(seq, doc, raw, ch, prev, None, seq, 1, [], idea_no=idea_no)
            if tsa_response:
                t = tsa.parse_response(tsa_response, bytes.fromhex(ch))
                self.db.execute("UPDATE ideas SET tsa_url=?, tsa_time=?, tsa_token=? WHERE seq=?",
                                (tsa_url, t["gen_time"], tsa_response, seq))
            self.db.execute("COMMIT")
        return self.get(seq)

    def stamp(self, seq: int) -> dict:
        row = self.db.execute("SELECT content_hash, tsa_token FROM ideas WHERE seq=?", (seq,)).fetchone()
        if not row:
            raise UserError("아이디어를 찾을 수 없습니다.")
        if row["tsa_token"]:
            raise UserError("이미 공인 시각을 받은 아이디어입니다.")
        try:
            r = tsa.stamp_any(row["content_hash"], self.tsa_urls)
        except Exception as ex:
            with self.lock:
                self.db.execute("UPDATE ideas SET tsa_error=? WHERE seq=?", (str(ex)[:500], seq))
        else:
            with self.lock:
                self.db.execute("UPDATE ideas SET tsa_url=?, tsa_time=?, tsa_token=?, tsa_error=NULL WHERE seq=?",
                                (r["url"], r["gen_time"], r["response"], seq))
        return self.get(seq)

    # ---------- 조회 ----------
    def _summary(self, r) -> dict:
        return {
            "seq": r["seq"], "idea_no": r["idea_no"], "title": r["title"], "author": r["author"],
            "tags": json.loads(r["tags"]), "created_at": r["created_at"], "version": r["version"],
            "root_seq": r["root_seq"], "tsa_time": r["tsa_time"], "tsa_pending": r["tsa_token"] is None,
            "content_hash": r["content_hash"],
        }

    def get(self, seq: int) -> dict:
        r = self.db.execute("SELECT * FROM ideas WHERE seq=?", (seq,)).fetchone()
        if not r:
            raise UserError("아이디어를 찾을 수 없습니다.")
        d = self._summary(r)
        d.update({
            "body": r["body"], "parent_seq": r["parent_seq"], "prev_hash": r["prev_hash"],
            "entry_hash": r["entry_hash"], "tsa_url": r["tsa_url"], "tsa_error": r["tsa_error"],
            "canonical": bytes(r["canonical"]).decode("utf-8"),
            "attachments": [dict(a) for a in self.db.execute(
                "SELECT name, sha256, size, mime FROM attachments WHERE seq=? ORDER BY rowid", (seq,))],
            "lineage": [self._summary(x) for x in self.db.execute(
                "SELECT * FROM ideas WHERE root_seq=? ORDER BY version", (r["root_seq"],))],
        })
        return d

    def list(self, q: str = "", tag: str = "") -> list[dict]:
        sql, args = "SELECT * FROM ideas", []
        conds = []
        if q:
            like = f"%{q}%"
            conds.append("(title LIKE ? OR body LIKE ? OR tags LIKE ? OR idea_no LIKE ? OR author LIKE ?)")
            args += [like] * 5
        if tag:
            conds.append("tags LIKE ?")
            args.append(f'%"{tag}"%')
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY seq DESC LIMIT 500"
        return [self._summary(r) for r in self.db.execute(sql, args)]

    def tags(self) -> list[str]:
        out = set()
        for (t,) in self.db.execute("SELECT tags FROM ideas"):
            out.update(json.loads(t))
        return sorted(out)

    def lookup(self, h: str) -> dict:
        h = h.strip().lower()
        if not HEX64.match(h):
            raise UserError("64자리 고유 지문(SHA-256)이 아닙니다.")
        ideas = [self._summary(r) for r in self.db.execute("SELECT * FROM ideas WHERE content_hash=?", (h,))]
        files = [dict(name=a["name"], **self._summary(a)) for a in self.db.execute(
            "SELECT i.*, a.name FROM attachments a JOIN ideas i ON i.seq=a.seq WHERE a.sha256=? ORDER BY i.seq", (h,))]
        return {"ideas": ideas, "files": files}

    def file_path(self, seq: int, sha: str) -> tuple[Path, dict]:
        a = self.db.execute("SELECT name, sha256, size, mime FROM attachments WHERE seq=? AND sha256=?", (seq, sha)).fetchone()
        if not a:
            raise UserError("첨부파일을 찾을 수 없습니다.")
        return self.files / a["sha256"], dict(a)

    def status(self) -> dict:
        last = self.db.execute("SELECT seq, entry_hash FROM ideas ORDER BY seq DESC LIMIT 1").fetchone()
        pending = self.db.execute("SELECT COUNT(*) FROM ideas WHERE tsa_token IS NULL").fetchone()[0]
        return {"count": last["seq"] if last else 0, "head": last["entry_hash"] if last else C.GENESIS,
                "tsa_pending": pending, "tsa_urls": self.tsa_urls}

    # ---------- 검증 ----------
    def verify_chain(self) -> dict:
        broken, prev, expect = [], C.GENESIS, 1
        rows = self.db.execute("SELECT * FROM ideas ORDER BY seq").fetchall()
        for r in rows:
            seq, problems = r["seq"], []
            if seq != expect:
                problems.append(f"{expect}번부터 {seq - 1}번 기록이 사라졌습니다.")
            raw = bytes(r["canonical"])
            if C.sha256_hex(raw) != r["content_hash"]:
                problems.append("원문이 바뀌었습니다 (고유 지문 불일치).")
            try:
                doc = json.loads(raw)
                if (doc.get("title"), doc.get("body"), doc.get("author")) != (r["title"], r["body"], r["author"]):
                    problems.append("표시용 제목·내용·작성자가 원문과 다릅니다.")
            except ValueError:
                problems.append("원문을 읽을 수 없습니다.")
                doc = {}
            if r["prev_hash"] != prev:
                problems.append("앞 기록과의 연결 고리가 맞지 않습니다.")
            if C.entry_hash(r["prev_hash"], seq, r["content_hash"]) != r["entry_hash"]:
                problems.append("원장 고리 값이 맞지 않습니다.")
            atts = [dict(a) for a in self.db.execute("SELECT name, sha256, size FROM attachments WHERE seq=? ORDER BY rowid", (seq,))]
            if [(a["name"], a["sha256"], a["size"]) for a in atts] != [(a["name"], a["sha256"], a["size"]) for a in doc.get("attachments", [])]:
                problems.append("첨부 목록이 원문과 다릅니다.")
            for a in atts:
                p = self.files / a["sha256"]
                if not p.exists():
                    problems.append(f"첨부 '{a['name']}' 파일이 없습니다.")
                elif C.sha256_hex(p.read_bytes()) != a["sha256"]:
                    problems.append(f"첨부 '{a['name']}' 파일이 바뀌었습니다.")
            if r["tsa_token"]:
                try:
                    t = tsa.token_time(bytes(r["tsa_token"]), bytes.fromhex(r["content_hash"]))
                    if t != r["tsa_time"]:
                        problems.append("공인 시각 기록이 서명된 시각과 다릅니다.")
                except Exception:
                    problems.append("공인 시각 서명이 이 내용과 맞지 않습니다.")
            if problems:
                broken.append({"seq": seq, "idea_no": r["idea_no"], "problems": problems})
            prev, expect = r["entry_hash"], seq + 1
        return {"ok": not broken, "count": len(rows), "head": prev, "broken": broken}
