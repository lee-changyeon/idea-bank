"""비밀번호 해시(scrypt), 세션, CSRF, 로그인 시도 제한."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

from ideabank import canonical as C

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
SESSION_TTL = 8 * 3600


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${h.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, h = stored.split("$")
        assert algo == "scrypt"
        got = hashlib.scrypt(pw.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got.hex(), h)
    except Exception:
        return False


# 존재하지 않는 계정에도 같은 시간이 걸리도록 비교용 더미 해시
DUMMY_HASH = hash_password(secrets.token_hex(8))


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(db, kind: str, subject_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    db.exec("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
    db.exec("INSERT INTO sessions (token_hash, kind, subject_id, csrf, created_at, expires_at) VALUES (?,?,?,?,?,?)",
            (_th(token), kind, subject_id, csrf, C.now_iso(), time.time() + SESSION_TTL))
    return token, csrf


def get_session(db, kind: str, token: str | None):
    if not token:
        return None
    s = db.one("SELECT * FROM sessions WHERE token_hash=? AND kind=?", (_th(token), kind))
    if not s or s["expires_at"] < time.time():
        return None
    return s


def end_session(db, token: str | None):
    if token:
        db.exec("DELETE FROM sessions WHERE token_hash=?", (_th(token),))


def csrf_ok(session, header_value: str | None) -> bool:
    return bool(session and header_value) and hmac.compare_digest(session["csrf"], header_value)


class Throttle:
    """IP+계정별 로그인 실패 제한: 10분 안에 5번 실패하면 10분 잠금."""

    def __init__(self, limit=5, window=600):
        self.limit, self.window = limit, window
        self.fails: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def blocked(self, key: str) -> bool:
        with self.lock:
            now = time.time()
            xs = [t for t in self.fails.get(key, []) if now - t < self.window]
            self.fails[key] = xs
            return len(xs) >= self.limit

    def fail(self, key: str):
        with self.lock:
            self.fails.setdefault(key, []).append(time.time())

    def clear(self, key: str):
        with self.lock:
            self.fails.pop(key, None)
