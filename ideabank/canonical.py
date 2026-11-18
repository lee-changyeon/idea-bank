"""정규화 JSON 과 해시 규칙 (TRD §4.3).

같은 내용이면 어느 컴퓨터에서든 같은 바이트, 같은 고유 지문(SHA-256)이 나와야 한다.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timezone

SCHEMA = "ideabank/1"
GENESIS = "0" * 64


def text(s: str | None) -> str:
    s = unicodedata.normalize("NFC", s or "")
    return s.replace("\r\n", "\n").replace("\r", "\n")


def clean_tags(tags) -> list[str]:
    out = {text(t).strip().lstrip("#") for t in (tags or [])}
    return sorted(t for t in out if t)


def now_iso() -> str:
    d = datetime.now(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


def build(*, title, body, tags, author, created_at, parent, attachments) -> dict:
    return {
        "schema": SCHEMA,
        "title": text(title).strip(),
        "body": text(body),
        "tags": clean_tags(tags),
        "author": text(author).strip(),
        "created_at": created_at,
        "parent": parent,
        "attachments": [
            {"name": text(a["name"]), "sha256": a["sha256"], "size": a["size"]} for a in attachments
        ],
    }


def dumps(doc: dict) -> bytes:
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def entry_hash(prev_hash: str, seq: int, content_hash: str) -> str:
    return sha256_hex(f"{prev_hash}:{seq}:{content_hash}".encode("ascii"))
