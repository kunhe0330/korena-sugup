"""애플리케이션 엔트리 포인트.

사용법:
    python run.py                  # 서버 실행
    python run.py --collect        # 수급 1회 수집만 실행 (테스트용)
"""
from __future__ import annotations

import argparse
import logging
import sys

from app import config
from app.scheduler import shutdown_scheduler, start_scheduler
from app.supply_demand_collector import collect_daily_supply_demand
from app.webhook_server import create_app


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(config.LOG_DIR / "korena.log", encoding="utf-8"),
        ],
    )


def main() -> int:
    _setup_logging()

    parser = argparse.ArgumentParser(description="Korena 수급 동향 대시보드")
    parser.add_argument(
        "--collect", action="store_true",
        help="수급 데이터 1회 수집 후 종료 (스케줄러 없이)",
    )
    parser.add_argument(
        "--no-scheduler", action="store_true",
        help="스케줄러 비활성화하고 서버만 실행",
    )
    args = parser.parse_args()

    if args.collect:
        count = collect_daily_supply_demand()
        print(f"수집 완료: {count}건")
        return 0

    app = create_app()

    if not args.no_scheduler:
        start_scheduler()

    try:
        app.run(
            host=config.FLASK_HOST,
            port=config.FLASK_PORT,
            debug=config.FLASK_DEBUG,
            use_reloader=False,  # 스케줄러 중복 실행 방지
        )
    finally:
        shutdown_scheduler()

    return 0


if __name__ == "__main__":
    sys.exit(main())
