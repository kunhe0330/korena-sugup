"""환경변수 기반 설정 로딩.

`.env` 파일이 있으면 자동 로드하고, 없으면 OS 환경변수만 사용.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _int_env(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("환경변수 %s=%r 는 정수가 아닙니다. 기본값 %s 사용", key, raw, default)
        return default


def _bool_env(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "y", "t")


# ---------------------------------------------------------------------------
# KIS (한국투자증권) OpenAPI
# ---------------------------------------------------------------------------
KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "")
KIS_BASE_URL = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")

# ---------------------------------------------------------------------------
# Flask 서버
# ---------------------------------------------------------------------------
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = _int_env("FLASK_PORT", 5000)
FLASK_DEBUG = _bool_env("FLASK_DEBUG", False)

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "korena.db"))

# ---------------------------------------------------------------------------
# 상장법인목록 파일
# ---------------------------------------------------------------------------
LISTED_COMPANIES_PATH = os.getenv(
    "LISTED_COMPANIES_PATH",
    str(DATA_DIR / "상장법인목록.xls"),
)

# ---------------------------------------------------------------------------
# 수급 동향 대시보드
# ---------------------------------------------------------------------------
SUPPLY_DEMAND_ENABLED = _bool_env("SUPPLY_DEMAND_ENABLED", True)
SUPPLY_DEMAND_COLLECT_HOUR = _int_env("SUPPLY_DEMAND_COLLECT_HOUR", 15)
SUPPLY_DEMAND_COLLECT_MINUTE = _int_env("SUPPLY_DEMAND_COLLECT_MINUTE", 40)
