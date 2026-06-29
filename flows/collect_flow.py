"""수집 플로우 — fetch → parse → upsert. (scripts/collect_once.py 진입점에서 호출)"""
from __future__ import annotations

import logging

from src.collectors import kpx
from src.storage import database

logger = logging.getLogger(__name__)


def run_collect() -> int:
    """KPX 수급 1회 수집 → DB 멱등 저장. 신규 저장 건수 반환."""
    records = kpx.fetch_sukub()
    inserted = database.upsert_records(records)
    logger.info("수집 완료: 신규 %d건 저장", inserted)
    return inserted
