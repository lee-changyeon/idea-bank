"""설정: web/config.json (없으면 기본값). TSA 목록은 v1 의 루트 config.json 을 읽어서 기본값으로 쓴다(읽기만)."""
import json

from . import ROOT, WEB_DIR

DEFAULTS = {
    "host": "127.0.0.1",
    "web_port": 8090,
    "admin_port": 8091,
    "tsa_urls": ["http://timestamp.digicert.com", "https://freetsa.org/tsr"],
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg["tsa_urls"] = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("tsa_urls") or cfg["tsa_urls"]
    except Exception:
        pass
    p = WEB_DIR / "config.json"
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg
