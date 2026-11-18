"""RFC 3161 타임스탬프 클라이언트 (표준 라이브러리만 사용).

외부 TSA(Time Stamping Authority)에는 아이디어 내용이 아니라 SHA-256 해시값(32바이트)만 전송된다.
응답 토큰(.tsr)은 그대로 보관되며, 제3자는 openssl 로 독립 검증할 수 있다.
"""
from __future__ import annotations

import os
import urllib.request
from datetime import datetime, timezone

SHA256_OID = bytes.fromhex("0609608648016503040201")  # 2.16.840.1.101.3.4.2.1


def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _len(len(value)) + value


def _int(n: int) -> bytes:
    b = n.to_bytes((n.bit_length() + 8) // 8 or 1, "big")  # 부호 비트용 여유 바이트 포함
    return _tlv(0x02, b)


def build_request(digest: bytes, nonce: int) -> bytes:
    alg = _tlv(0x30, SHA256_OID + b"\x05\x00")
    imprint = _tlv(0x30, alg + _tlv(0x04, digest))
    return _tlv(0x30, _int(1) + imprint + _int(nonce) + _tlv(0x01, b"\xff"))


def _read_tlv(buf: bytes, pos: int) -> tuple[int, int, int]:
    """(tag, value_start, value_end) 반환."""
    tag = buf[pos]
    ln = buf[pos + 1]
    pos += 2
    if ln & 0x80:
        k = ln & 0x7F
        ln = int.from_bytes(buf[pos:pos + k], "big")
        pos += k
    return tag, pos, pos + ln


def parse_response(resp: bytes, digest: bytes) -> dict:
    """TimeStampResp 에서 상태, 토큰, genTime 을 추출하고 해시 일치 여부를 확인한다."""
    _, s, e = _read_tlv(resp, 0)                 # TimeStampResp SEQUENCE
    _, ss, se = _read_tlv(resp, s)               # PKIStatusInfo SEQUENCE
    _, vs, ve = _read_tlv(resp, ss)              # status INTEGER
    status = int.from_bytes(resp[vs:ve], "big")
    if status not in (0, 1):
        raise ValueError(f"TSA 거부 (PKIStatus={status})")
    token = resp[se:e]                           # TimeStampToken (ContentInfo)
    if not token:
        raise ValueError("응답에 타임스탬프 토큰이 없음")
    return {"token": token, "gen_time": token_time(token, digest)}


def token_time(token: bytes, digest: bytes) -> str:
    """토큰 안의 TSTInfo 에서 해시를 찾고, 그 뒤의 serialNumber 다음 genTime 을 읽는다."""
    marker = b"\x04\x20" + digest
    i = token.find(marker)
    if i < 0:
        raise ValueError("토큰의 해시가 요청 해시와 일치하지 않음")
    pos = i + len(marker)
    tag, _, end = _read_tlv(token, pos)          # serialNumber
    if tag != 0x02:
        raise ValueError("TSTInfo 구조를 해석할 수 없음")
    tag, vs, ve = _read_tlv(token, end)          # genTime
    if tag != 0x18:
        raise ValueError("genTime 을 찾을 수 없음")
    raw = token[vs:ve].decode("ascii").rstrip("Z")
    main, _, frac = raw.partition(".")
    dt = datetime.strptime(main, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
    return iso + (f".{frac}" if frac else "") + "Z"


def stamp(digest_hex: str, url: str, timeout: float = 15.0) -> dict:
    digest = bytes.fromhex(digest_hex)
    nonce = int.from_bytes(os.urandom(8), "big")
    req = urllib.request.Request(
        url,
        data=build_request(digest, nonce),
        headers={"Content-Type": "application/timestamp-query", "User-Agent": "idea-bank/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = r.read()
    out = parse_response(resp, digest)
    out["url"] = url
    out["response"] = resp  # openssl ts -reply 로 검증할 수 있는 원본 응답
    return out


def stamp_any(digest_hex: str, urls: list[str]) -> dict:
    errors = []
    for url in urls:
        try:
            return stamp(digest_hex, url)
        except Exception as ex:  # 다음 TSA 로 폴백
            errors.append(f"{url}: {ex}")
    raise RuntimeError("모든 TSA 요청 실패 — " + " | ".join(errors))
