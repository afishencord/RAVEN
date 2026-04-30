from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Node, utcnow
from app.services.incident_workflow import ensure_default_health_checks, process_health_result, run_and_record_health_check
from app.services.health_checks import run_health_check

logger = logging.getLogger(__name__)
settings = get_settings()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class MonitoringService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._task or not settings.embedded_monitoring:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.to_thread(self._tick)
            except Exception as exc:
                logger.exception("Monitoring loop error: %s", exc)
            await asyncio.sleep(settings.monitor_poll_seconds)

    def _tick(self) -> None:
        db: Session = SessionLocal()
        try:
            now = utcnow()
            nodes = db.query(Node).filter(Node.is_enabled.is_(True)).all()
            for node in nodes:
                checks = [check for check in ensure_default_health_checks(db, node) if check.is_enabled]
                if not checks:
                    run_and_record_health_check(db, node)
                    continue
                due_checks = [
                    check
                    for check in checks
                    if not check.last_run_at or (now - _as_utc(check.last_run_at)).total_seconds() >= check.interval_seconds
                ]
                if not due_checks:
                    continue
                if len(due_checks) == len(checks):
                    run_and_record_health_check(db, node)
                    continue
                for check in due_checks:
                    result = run_health_check(node, check, db=db)
                    process_health_result(db, node, result, health_check=check)
                db.commit()
        finally:
            db.close()
