"""APScheduler 기반 스케줄러 — 수급 수집 작업 등록."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config
from .supply_demand_collector import collect_daily_supply_demand

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    return _scheduler


def register_supply_demand_job() -> None:
    """평일 15:40에 수급 데이터 자동 수집."""
    if not config.SUPPLY_DEMAND_ENABLED:
        logger.info("[스케줄러] 수급 수집 비활성화됨")
        return

    sched = get_scheduler()
    sched.add_job(
        collect_daily_supply_demand,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=config.SUPPLY_DEMAND_COLLECT_HOUR,
            minute=config.SUPPLY_DEMAND_COLLECT_MINUTE,
        ),
        id="supply_demand_daily",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "[스케줄러] 수급 수집 작업 등록 — 평일 %02d:%02d",
        config.SUPPLY_DEMAND_COLLECT_HOUR,
        config.SUPPLY_DEMAND_COLLECT_MINUTE,
    )


def start_scheduler() -> None:
    sched = get_scheduler()
    register_supply_demand_job()
    if not sched.running:
        sched.start()
        logger.info("[스케줄러] 시작됨")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[스케줄러] 종료됨")
