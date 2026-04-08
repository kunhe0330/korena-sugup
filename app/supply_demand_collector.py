"""수급 동향 데이터 수집 모듈.

- 국내기관_외국인 매매종목가집계 API (TR_ID: FHPTJ04400000) 호출
- 하루 2회 (코스피 1회 + 코스닥 1회) — 순매수상위로만 호출
- 결과를 supply_demand_daily 테이블에 UPSERT
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import requests

from . import config, database, sectors
from .kis_client import _get_session, common_headers

logger = logging.getLogger(__name__)


TR_ID_SUPPLY_DEMAND = "FHPTJ04400000"
_API_PATH = "/uapi/domestic-stock/v1/quotations/foreign-institution-total"

MARKET_MAP = {
    "0001": "KOSPI",
    "1001": "KOSDAQ",
}


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        s = str(value).strip().replace(",", "")
        if s == "":
            return default
        return int(float(s))
    except (ValueError, TypeError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        s = str(value).strip().replace(",", "")
        if s == "":
            return default
        return float(s)
    except (ValueError, TypeError):
        return default


def fetch_institution_foreign_top(
    market_code: str = "0001",
    sort_code: str = "0",
    cls_code: str = "0",
) -> list[dict]:
    """국내기관_외국인 매매종목가집계 API 호출.

    Args:
        market_code: 0000=전체, 0001=코스피, 1001=코스닥
        sort_code:   0=순매수상위, 1=순매도상위
        cls_code:    0=전체, 1=외국인, 2=기관계
    """
    url = f"{config.KIS_BASE_URL}{_API_PATH}"
    params = {
        "FID_COND_MRKT_DIV_CODE": "V",
        "FID_COND_SCR_DIV_CODE":  "16449",
        "FID_INPUT_ISCD":         market_code,
        "FID_DIV_CLS_CODE":       "1",   # 금액정렬
        "FID_RANK_SORT_CLS_CODE": sort_code,
        "FID_ETC_CLS_CODE":       cls_code,
    }

    try:
        resp = _get_session().get(
            url,
            headers=common_headers(TR_ID_SUPPLY_DEMAND),
            params=params,
            timeout=10,
        )
    except requests.RequestException as e:
        logger.error("수급 가집계 API 요청 실패: %s", e)
        return []

    if resp.status_code != 200:
        logger.error(
            "수급 가집계 API HTTP %s: %s", resp.status_code, resp.text[:500]
        )
        return []

    try:
        data = resp.json()
    except ValueError:
        logger.error("수급 가집계 API 응답 파싱 실패: %s", resp.text[:500])
        return []

    if data.get("rt_cd") != "0":
        logger.error(
            "수급 가집계 API 에러 rt_cd=%s msg_cd=%s msg1=%s",
            data.get("rt_cd"), data.get("msg_cd"), data.get("msg1"),
        )
        return []

    output = data.get("output", [])
    if not isinstance(output, list):
        logger.error("수급 가집계 output이 list가 아님: %r", type(output))
        return []

    logger.info(
        "수급 API 호출 성공: market=%s (%s), %d건",
        market_code, MARKET_MAP.get(market_code, "?"), len(output),
    )
    return output


def _build_record(item: dict, biz_date: str, market_name: str, now_iso: str) -> dict | None:
    ticker = (item.get("mksc_shrn_iscd") or "").strip()
    if not ticker:
        return None

    sector = sectors.get_sector(ticker)
    sector_group = sectors.get_sector_group(sector)
    name = (item.get("hts_kor_isnm") or "").strip() or sectors.get_name_fallback(ticker)

    return {
        "collected_at":     now_iso,
        "biz_date":         biz_date,
        "market":           market_name,
        "ticker":           ticker,
        "name":             name,
        "sector":           sector,
        "sector_group":     sector_group,
        "price":            _safe_int(item.get("stck_prpr")),
        "price_change_pct": _safe_float(item.get("prdy_ctrt")),
        "frgn_net_qty":     _safe_int(item.get("frgn_ntby_qty")),
        "orgn_net_qty":     _safe_int(item.get("orgn_ntby_qty")),
        "frgn_net_amt":     _safe_int(item.get("frgn_ntby_tr_pbmn")),
        "orgn_net_amt":     _safe_int(item.get("orgn_ntby_tr_pbmn")),
        "acml_vol":         _safe_int(item.get("acml_vol")),
    }


def collect_daily_supply_demand() -> int:
    """하루 수급 데이터 수집 — 코스피+코스닥 각 1회씩 호출."""
    if not config.SUPPLY_DEMAND_ENABLED:
        logger.info("[수급 수집] 비활성화됨 (SUPPLY_DEMAND_ENABLED=false)")
        return 0

    # 섹터 데이터 로드 (최초 1회)
    sectors.load_sector_data()

    database.init_db()

    now = datetime.now()
    biz_date = now.strftime("%Y%m%d")
    now_iso = now.isoformat(timespec="seconds")

    all_records: list[dict] = []
    for market_code, market_name in MARKET_MAP.items():
        items = fetch_institution_foreign_top(
            market_code=market_code,
            sort_code="0",   # 순매수상위만 호출 — 음수 데이터도 포함됨
            cls_code="0",
        )
        for item in items:
            rec = _build_record(item, biz_date, market_name, now_iso)
            if rec is not None:
                all_records.append(rec)
        time.sleep(1.0)  # API 호출 간격

    if not all_records:
        logger.warning("[수급 수집] %s — 수집된 레코드 없음", biz_date)
        return 0

    saved = database.upsert_supply_demand_records(all_records)
    logger.info("[수급 수집] %s — %d건 저장 완료", biz_date, saved)
    return len(all_records)
