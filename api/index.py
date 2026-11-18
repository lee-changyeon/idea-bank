"""Vercel 파이썬 함수 입구: 아이디어뱅크 사용자 웹(web/server.py)을 그대로 띄운다.

vercel.json 이 모든 경로를 이 함수로 보낸다. 정적 파일(web/static)도 같은 Handler 가 보안 헤더와 함께 준다.
설계: web/DEPLOY_SUPABASE.md
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
for p in (str(ROOT), str(WEB)):
    if p not in sys.path:
        sys.path.insert(0, p)

# 루트의 server.py(v1 로컬 앱)와 이름이 겹치지 않도록 파일 경로로 불러온다
_spec = importlib.util.spec_from_file_location("ideabank_web_server", WEB / "server.py")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["ideabank_web_server"] = _mod
_spec.loader.exec_module(_mod)

handler = _mod.app.handler()
