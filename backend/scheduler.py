"""系统定时任务模块。

本模块只定义调度器和任务函数，不在导入时自动启动。后续可在 main.py 生命周期中调用
start_scheduler() / stop_scheduler()。
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.exc import SQLAlchemyError

from alerts import (
    ALERT_TYPE_EXPIRING,
    ALERT_TYPE_LOW_STOCK,
    build_expiring_alert,
    build_low_stock_alert,
    get_expiring_reagents,
    get_low_stock_reagents,
    unresolved_alert_exists,
)
from config import settings
from database import SessionLocal


logger = logging.getLogger(__name__)


# 全局调度器实例。不会在模块导入时启动。
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def check_alerts_job() -> None:
    """每天执行一次低库存和即将过期检查。"""

    db = SessionLocal()
    created_count = 0

    try:
        for reagent in get_low_stock_reagents(db):
            if unresolved_alert_exists(db, reagent.id, ALERT_TYPE_LOW_STOCK):
                continue
            db.add(build_low_stock_alert(reagent))
            created_count += 1

        for reagent in get_expiring_reagents(db, settings.EXPIRY_WARNING_DAYS):
            if unresolved_alert_exists(db, reagent.id, ALERT_TYPE_EXPIRING):
                continue
            db.add(build_expiring_alert(reagent))
            created_count += 1

        db.commit()
        logger.info("定时报警检查完成，新增报警 %s 条", created_count)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("定时报警检查失败")
    finally:
        db.close()


def sync_tencent_docs_job() -> None:
    """预留：每天执行腾讯文档同步任务。"""

    logger.info("腾讯文档同步定时任务占位：真实同步将在后续阶段接入")


def weekly_report_job() -> None:
    """预留：每周生成周报。"""

    logger.info("周报生成定时任务占位：后续可接入报表文件生成或通知")


def monthly_report_job() -> None:
    """预留：每月生成月报。"""

    logger.info("月报生成定时任务占位：后续可接入报表文件生成或通知")


def add_jobs() -> None:
    """注册所有系统定时任务，避免重复添加。"""

    if scheduler.get_job("daily_alert_check") is None:
        scheduler.add_job(
            check_alerts_job,
            CronTrigger(hour=8, minute=30),
            id="daily_alert_check",
            name="每天 08:30 检查低库存和即将过期试剂",
            replace_existing=True,
        )

    if scheduler.get_job("daily_tencent_docs_sync") is None:
        scheduler.add_job(
            sync_tencent_docs_job,
            CronTrigger(hour=23, minute=30),
            id="daily_tencent_docs_sync",
            name="每天 23:30 预留腾讯文档同步任务",
            replace_existing=True,
        )

    if scheduler.get_job("weekly_report") is None:
        scheduler.add_job(
            weekly_report_job,
            CronTrigger(day_of_week="mon", hour=9, minute=0),
            id="weekly_report",
            name="每周一 09:00 预留周报生成任务",
            replace_existing=True,
        )

    if scheduler.get_job("monthly_report") is None:
        scheduler.add_job(
            monthly_report_job,
            CronTrigger(day=1, hour=9, minute=0),
            id="monthly_report",
            name="每月 1 日 09:00 预留月报生成任务",
            replace_existing=True,
        )


def start_scheduler() -> None:
    """启动系统定时任务。"""

    add_jobs()
    if scheduler.running:
        logger.info("定时任务调度器已在运行")
        return

    scheduler.start()
    logger.info("定时任务调度器已启动")


def stop_scheduler() -> None:
    """停止系统定时任务。"""

    if not scheduler.running:
        logger.info("定时任务调度器未运行")
        return

    scheduler.shutdown(wait=False)
    logger.info("定时任务调度器已停止")
