"""수집 플로우 — fetch → parse → upsert. (scripts/collect_once.py 진입점에서 호출)"""
from __future__ import annotations

import logging

from src.collectors import kpx
from src.storage import database

logger = logging.getLogger(__name__)


def run_collect() -> dict[str, int]:
    """KPX 수급 + 발전믹스 1회 수집 → DB 멱등 저장. 신규 저장 건수 dict 반환.

    발전믹스 수집이 실패해도 수급 수집은 보존한다 (graceful degradation).
    """
    sukub = database.upsert_records(kpx.fetch_sukub())

    try:
        gen = database.upsert_generation(kpx.fetch_generation())
    except Exception as e:  # noqa: BLE001
        logger.warning("발전믹스 수집 실패(수급은 저장됨): %s", e)
        gen = 0

    logger.info("수집 완료: 수급 %d건, 발전믹스 %d건", sukub, gen)
    return {"sukub": sukub, "generation": gen}
