"""Tencent Docs background sync job runner.

Formal import/export uses async Job mode: frontend creates a job, backend
runs it in a background thread, and frontend polls for status.  This avoids
HTTP timeouts causing false failure reports during long-running patch writes.
"""

from __future__ import annotations

import json as _json
import threading
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from models import TencentDocsSyncJob
from services.sync_providers import (
    RealTencentDocsProvider,
    TencentDocsApiError,
    TencentDocsEndpointConfigError,
    log_export_result,
    log_import_result,
)
from services.sync_core import SyncImportResult
from utils.timezone import now_beijing


def _make_job_id() -> str:
    return uuid.uuid4().hex[:12]


# ── duplicate guard ──────────────────────────────────────────────


def _find_duplicate_job(
    db: Session,
    job_type: str,
    mode: str,
    year: int,
    month: int | None,
) -> TencentDocsSyncJob | None:
    stmt = select(TencentDocsSyncJob).where(
        TencentDocsSyncJob.job_type == job_type,
        TencentDocsSyncJob.mode == mode,
        TencentDocsSyncJob.year == year,
        TencentDocsSyncJob.status.in_(["queued", "running"]),
    )
    if month is not None:
        stmt = stmt.where(TencentDocsSyncJob.month == month)
    return db.execute(stmt.order_by(TencentDocsSyncJob.id.desc()).limit(1)).scalar_one_or_none()


# ── job creation ─────────────────────────────────────────────────


def create_import_job(
    db: Session,
    *,
    year: int,
    month: int | None = None,
    all_months: bool = False,
    operator_id: int | None = None,
) -> dict[str, Any]:
    mode = "all_months" if all_months else "single_month"
    existing = _find_duplicate_job(db, "tencent_docs_import", mode, year, month)
    if existing:
        return _job_to_dict(existing, message="该导入任务已在执行，请勿重复提交")

    job_id = _make_job_id()
    progress_total = 12 if all_months else 1
    job = TencentDocsSyncJob(
        job_id=job_id,
        job_type="tencent_docs_import",
        mode=mode,
        year=year,
        month=month if not all_months else None,
        status="queued",
        progress_total=progress_total,
        progress_done=0,
        created_by=operator_id,
    )
    db.add(job)
    db.flush()

    thread = threading.Thread(
        target=_run_import_job,
        args=(job_id, year, month, all_months, operator_id),
        daemon=True,
    )
    thread.start()

    return _job_to_dict(job, message="腾讯文档导入任务已创建，正在后台执行")


def create_export_job(
    db: Session,
    *,
    year: int,
    month: int | None = None,
    all_months: bool = False,
    force_skip_write_cell_check: bool = False,
    operator_id: int | None = None,
) -> dict[str, Any]:
    mode = "all_months" if all_months else "single_month"
    existing = _find_duplicate_job(db, "tencent_docs_export", mode, year, month)
    if existing:
        return _job_to_dict(existing, message="该同步任务已在执行，请勿重复提交")

    job_id = _make_job_id()
    progress_total = 12 if all_months else 1
    job = TencentDocsSyncJob(
        job_id=job_id,
        job_type="tencent_docs_export",
        mode=mode,
        year=year,
        month=month if not all_months else None,
        status="queued",
        progress_total=progress_total,
        progress_done=0,
        created_by=operator_id,
    )
    db.add(job)
    db.flush()

    thread = threading.Thread(
        target=_run_export_job,
        args=(job_id, year, month, all_months, force_skip_write_cell_check, operator_id),
        daemon=True,
    )
    thread.start()

    return _job_to_dict(job, message="腾讯文档同步任务已创建，正在后台执行")


# ── status query ─────────────────────────────────────────────────


def get_job_status(db: Session, job_id: str) -> dict[str, Any] | None:
    job = db.execute(
        select(TencentDocsSyncJob).where(TencentDocsSyncJob.job_id == job_id)
    ).scalar_one_or_none()
    if job is None:
        return None
    return _job_to_dict(job)


# ── helpers ──────────────────────────────────────────────────────


def _job_to_dict(job: TencentDocsSyncJob, message: str | None = None) -> dict[str, Any]:
    result = None
    if job.result_json:
        try:
            result = _json.loads(job.result_json)
        except (_json.JSONDecodeError, TypeError):
            result = {"raw": job.result_json}
    return {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "mode": job.mode,
        "year": job.year,
        "month": job.month,
        "status": job.status,
        "progress_total": job.progress_total,
        "progress_done": job.progress_done,
        "message": message or job.message,
        "result": result,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def _get_job_db() -> Session:
    """Return a fresh DB session for background thread use."""
    return SessionLocal()


def _update_job(session: Session, job_id: str, **kwargs: Any) -> None:
    job = session.execute(
        select(TencentDocsSyncJob).where(TencentDocsSyncJob.job_id == job_id)
    ).scalar_one_or_none()
    if job is None:
        return
    for key, value in kwargs.items():
        setattr(job, key, value)
    session.commit()


# ── background runners ───────────────────────────────────────────


def _run_import_job(
    job_id: str,
    year: int,
    month: int | None,
    all_months: bool,
    operator_id: int | None,
) -> None:
    session = _get_job_db()
    try:
        _update_job(session, job_id, status="running", started_at=now_beijing(),
                     message=f"正在导入 {year}" + (f" 年 {month} 月" if month else " 年全年"))
        provider = RealTencentDocsProvider(db=session)

        if all_months:
            all_result = provider.import_all_months(db=session, operator_id=operator_id or 0, year=year)
            msg = (
                f"全年导入完成：新增 {all_result['total_inserted']} 条，"
                f"跳过 {all_result['total_skipped']} 条，"
                f"失败 {all_result['total_failed']} 条"
            )
            _update_job(
                session, job_id,
                status=all_result["status"],
                progress_done=12,
                message=msg,
                result_json=_json.dumps(all_result, ensure_ascii=False),
                finished_at=now_beijing(),
            )
            log_import_result(
                db=session, provider_source=provider.source,
                sync_type="tencent_docs_import",
                result=SyncImportResult(
                    created=all_result["total_inserted"],
                    skipped=all_result["total_skipped"],
                    failed=all_result["total_failed"],
                    errors=[],
                ),
                message_prefix="腾讯文档全年导入",
            )
            session.commit()
        else:
            target_month = month or 1
            _update_job(session, job_id, message=f"正在导入 {year} 年 {target_month} 月")
            result = provider.import_records(db=session, operator_id=operator_id, year=year, month=target_month)
            msg = result.message
            _update_job(
                session, job_id,
                status="success" if result.failed == 0 else "partial_success",
                progress_done=1,
                message=msg,
                result_json=_json.dumps(
                    {
                        "year": year, "month": target_month,
                        "inserted_count": result.created,
                        "skipped_count": result.skipped,
                        "failed_count": result.failed,
                        **getattr(result, "extra_detail", {}),
                    },
                    ensure_ascii=False,
                ),
                finished_at=now_beijing(),
            )
            log_import_result(
                db=session, provider_source=provider.source,
                sync_type="tencent_docs_import",
                result=result,
                message_prefix="腾讯文档导入",
            )
            session.commit()
    except Exception as exc:
        try:
            session.rollback()
            _update_job(
                session, job_id,
                status="failed",
                message=f"导入失败：{exc}",
                error_message=str(exc)[:2000],
                finished_at=now_beijing(),
            )
        except Exception:
            pass
    finally:
        session.close()


def _run_export_job(
    job_id: str,
    year: int,
    month: int | None,
    all_months: bool,
    force_skip_write_cell_check: bool,
    operator_id: int | None,
) -> None:
    session = _get_job_db()
    try:
        _update_job(session, job_id, status="running", started_at=now_beijing(),
                     message=f"正在同步 {year}" + (f" 年 {month} 月" if month else " 年全年"))
        provider = RealTencentDocsProvider(db=session)

        if all_months:
            all_result = provider.export_all_months(
                db=session, year=year,
                force_skip_write_cell_check=force_skip_write_cell_check,
            )
            msg = (
                f"全年同步完成：写入 {all_result['total_written_patch_count']} 个小范围，"
                f"跳过重复 {all_result['total_skipped_duplicate_count']} 个，"
                f"失败 {all_result['total_failed_patch_count']} 个"
            )
            _update_job(
                session, job_id,
                status=all_result["status"],
                progress_done=12,
                message=msg,
                result_json=_json.dumps(all_result, ensure_ascii=False),
                finished_at=now_beijing(),
            )
            log_export_result(
                db=session, provider_source=provider.source,
                sync_type="tencent_docs_export",
                message=msg, detail=all_result,
                status_value=all_result["status"],
            )
            session.commit()
        else:
            target_month = month or 1
            result = provider.export_records(
                db=session, year=year, month=target_month,
                force_skip_write_cell_check=force_skip_write_cell_check,
            )
            status_val = result.get("status", "success")
            msg = result.get("message", "同步完成")
            _update_job(
                session, job_id,
                status=status_val,
                progress_done=1,
                message=msg,
                result_json=_json.dumps(
                    {k: v for k, v in result.items()
                     if k not in ("values", "write_values")},
                    ensure_ascii=False,
                ),
                finished_at=now_beijing(),
            )
            log_export_result(
                db=session, provider_source=provider.source,
                sync_type="tencent_docs_export",
                message=msg, detail=result,
                status_value=status_val,
            )
            session.commit()
    except Exception as exc:
        try:
            session.rollback()
            _update_job(
                session, job_id,
                status="failed",
                message=f"同步失败：{exc}",
                error_message=str(exc)[:2000],
                finished_at=now_beijing(),
            )
        except Exception:
            pass
    finally:
        session.close()
