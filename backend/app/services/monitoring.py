from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Node, utcnow
from app.services.incident_workflow import run_and_record_health_check

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
                if not node.last_check_at:
                    run_and_record_health_check(db, node)
                    continue
                elapsed = (now - _as_utc(node.last_check_at)).total_seconds()
                if elapsed >= node.check_interval_seconds:
                    run_and_record_health_check(db, node)
        finally:
            db.close()
