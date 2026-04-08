"""섹터(업종) 매핑 로더.

우선순위:
1. `LISTED_COMPANIES_PATH`의 xls 파일이 있으면 거기서 종목코드→업종 추출.
2. 파일이 없으면 sector_map.json의 sample_tickers 사용 (개발/테스트용).

업종 대분류 매핑은 항상 sector_map.json의 groups 섹션에서 가져옴.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)

_SECTOR_MAP_JSON = Path(__file__).resolve().parent / "sector_map.json"

# 런타임에 로드되는 캐시
_TICKER_TO_SECTOR: dict[str, str] = {}
_TICKER_TO_NAME: dict[str, str] = {}
_SECTOR_GROUPS: dict[str, str] = {}
_LOADED = False


def _load_sector_map_json() -> dict:
    try:
        with open(_SECTOR_MAP_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("sector_map.json 파일을 찾을 수 없음: %s", _SECTOR_MAP_JSON)
        return {"groups": {}, "sample_tickers": {}}
    except json.JSONDecodeError as e:
        logger.error("sector_map.json 파싱 실패: %s", e)
        return {"groups": {}, "sample_tickers": {}}


def _load_from_xls(path: str) -> dict[str, tuple[str, str]]:
    """상장법인목록.xls에서 {ticker: (name, sector)} 추출.

    파일은 실제로는 HTML 테이블(.xls 확장자만)이라 pandas.read_html로 읽음.
    """
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas가 설치되지 않아 xls 로드 불가")
        return {}

    try:
        tables = pd.read_html(path)
    except Exception as e:
        logger.error("xls 파일 읽기 실패 (%s): %s", path, e)
        return {}

    if not tables:
        logger.error("xls에서 테이블을 찾지 못함: %s", path)
        return {}

    df = tables[0]

    # 컬럼 이름 유연 대응
    col_code = None
    col_name = None
    col_sector = None
    for c in df.columns:
        col_str = str(c).strip()
        if col_str in ("종목코드", "종목 코드"):
            col_code = c
        elif col_str in ("회사명", "종목명", "한글명"):
            col_name = c
        elif col_str == "업종":
            col_sector = c

    if col_code is None or col_sector is None:
        logger.error(
            "xls에서 필수 컬럼을 찾지 못함. columns=%s", list(df.columns)
        )
        return {}

    result: dict[str, tuple[str, str]] = {}
    for _, row in df.iterrows():
        raw_code = row[col_code]
        if raw_code is None:
            continue
        ticker = str(raw_code).strip().zfill(6)
        if len(ticker) != 6 or not ticker.isdigit():
            continue
        name = str(row[col_name]).strip() if col_name is not None else ""
        sector = str(row[col_sector]).strip() if row[col_sector] is not None else ""
        result[ticker] = (name, sector)

    logger.info("xls에서 %d 종목 로드 완료: %s", len(result), path)
    return result


def load_sector_data(force: bool = False) -> None:
    """섹터 매핑 데이터를 메모리에 로드."""
    global _LOADED, _TICKER_TO_SECTOR, _TICKER_TO_NAME, _SECTOR_GROUPS

    if _LOADED and not force:
        return

    _TICKER_TO_SECTOR = {}
    _TICKER_TO_NAME = {}

    sector_map_data = _load_sector_map_json()
    _SECTOR_GROUPS = sector_map_data.get("groups", {})

    # 1. xls 파일 우선
    xls_path = config.LISTED_COMPANIES_PATH
    if xls_path and Path(xls_path).exists():
        loaded = _load_from_xls(xls_path)
        for ticker, (name, sector) in loaded.items():
            _TICKER_TO_NAME[ticker] = name
            _TICKER_TO_SECTOR[ticker] = sector
    else:
        logger.warning(
            "상장법인목록 파일 없음 (%s) — sample 데이터 사용", xls_path
        )

    # 2. fallback: sample_tickers 병합 (xls에 없는 종목 보충)
    samples = sector_map_data.get("sample_tickers", {})
    for ticker, info in samples.items():
        if ticker not in _TICKER_TO_SECTOR:
            _TICKER_TO_NAME[ticker] = info.get("name", "")
            _TICKER_TO_SECTOR[ticker] = info.get("sector", "")

    _LOADED = True
    logger.info(
        "섹터 매핑 로드 완료: %d 종목, %d 업종 그룹",
        len(_TICKER_TO_SECTOR),
        len(_SECTOR_GROUPS),
    )


def get_sector(ticker: str) -> str:
    """종목코드 → 업종(세분류)."""
    if not _LOADED:
        load_sector_data()
    return _TICKER_TO_SECTOR.get(ticker, "")


def get_sector_group(sector_name: str) -> str:
    """업종(세분류) → 대분류. 매핑 없으면 '기타'."""
    if not _LOADED:
        load_sector_data()
    if not sector_name:
        return "기타"
    return _SECTOR_GROUPS.get(sector_name, "기타")


def get_name_fallback(ticker: str) -> str:
    """종목코드 → 종목명 (xls/sample에서)."""
    if not _LOADED:
        load_sector_data()
    return _TICKER_TO_NAME.get(ticker, "")
