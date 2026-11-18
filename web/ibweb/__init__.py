"""아이디어뱅크 온라인(v2) 공용 백엔드.

web/ (사용자 앱) 와 admin/ (관리자 앱) 이 함께 쓴다.
증명 로직(정규화 JSON, 해시, RFC 3161)은 프로젝트 루트의 ideabank 패키지를 그대로 가져다 쓴다.
"""
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent
ROOT = WEB_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
