"""KIS (한국투자증권) OpenAPI 클라이언트.

- 토큰 발급/캐싱 (하루 1회 갱신)
- 공통 헤더 생성
- requests.Session 재사용
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from . import config

logger = logging.getLogger(__name__)

_TOKEN_CACHE_FILE = Path(config.DATA_DIR) / "kis_token.json"
_TOKEN_LOCK = threading.Lock()
_SESSION: requests.Session | None = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({
            "User-Agent": "korena-sugup/1.0",
            "Content-Type": "application/json; charset=utf-8",
        })
    return _SESSION


def _load_cached_token() -> dict | None:
    if not _TOKEN_CACHE_FILE.exists():
        return None
    try:
        with open(_TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("토큰 캐시 로드 실패: %s", e)
        return None

    # 만료 확인
    expires_at = data.get("expires_at")
    if not expires_at:
        return None
    try:
        expires_dt = datetime.fromisoformat(expires_at)
    except ValueError:
        return None
    # 만료 10분 전부터는 새로 발급
    if datetime.now() >= expires_dt - timedelta(minutes=10):
        return None
    return data


def _save_cached_token(token: str, expires_in_sec: int) -> None:
    expires_at = datetime.now() + timedelta(seconds=expires_in_sec)
    data = {
        "access_token": token,
        "expires_at": expires_at.isoformat(),
    }
    _TOKEN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _issue_token() -> str | None:
    if not config.KIS_APP_KEY or not config.KIS_APP_SECRET:
        logger.error("KIS_APP_KEY/KIS_APP_SECRET 환경변수가 설정되지 않음")
        return None

    url = f"{config.KIS_BASE_URL}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": config.KIS_APP_KEY,
        "appsecret": config.KIS_APP_SECRET,
    }
    try:
        resp = _get_session().post(url, json=body, timeout=10)
    except requests.RequestException as e:
        logger.error("토큰 발급 요청 실패: %s", e)
        return None

    if resp.status_code != 200:
        logger.error("토큰 발급 실패 (HTTP %s): %s", resp.status_code, resp.text)
        return None

    try:
        data = resp.json()
    except ValueError:
        logger.error("토큰 응답 파싱 실패: %s", resp.text)
        return None

    token = data.get("access_token")
    expires_in = int(data.get("expires_in", 86400))
    if not token:
        logger.error("토큰 응답에 access_token 없음: %s", data)
        return None

    _save_cached_token(token, expires_in)
    logger.info("KIS 토큰 발급 완료 (만료 %d초)", expires_in)
    return token


def get_access_token() -> str | None:
    """유효한 access token 반환. 캐시 우선, 없거나 만료되면 새로 발급."""
    with _TOKEN_LOCK:
        cached = _load_cached_token()
        if cached:
            return cached["access_token"]
        # KIS는 토큰 발급 직후 재발급 시 429 에러가 날 수 있어 약간의 대기
        time.sleep(0.5)
        return _issue_token()


def common_headers(tr_id: str, tr_cont: str = "") -> dict[str, str]:
    """KIS API 공통 헤더."""
    token = get_access_token()
    if not token:
        logger.warning("토큰 없이 요청 진행 — 실패 예상")
        token = ""
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": config.KIS_APP_KEY,
        "appsecret": config.KIS_APP_SECRET,
        "tr_id": tr_id,
        "tr_cont": tr_cont,
        "custtype": "P",  # 개인
    }
