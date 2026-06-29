"""Discord 웹훅 경보 — 예비율 임계/이상 감지 시 알림."""
from __future__ import annotations

import logging

import requests

from src import config

logger = logging.getLogger(__name__)


def send_alert(message: str, webhook_url: str | None = None, timeout: int = 10) -> bool:
    """Discord로 경보 전송. 웹훅 미설정 시 조용히 False 반환(수집은 계속)."""
    url = webhook_url or config.DISCORD_WEBHOOK_URL
    if not url:
        logger.warning("DISCORD_WEBHOOK_URL 미설정 — 경보 스킵")
        return False
    resp = requests.post(url, json={"content": message}, timeout=timeout)
    resp.raise_for_status()
    return True


def format_reserve_alert(ts, reserve_rate: float, level: str) -> str:
    return f"⚠️ [{level}] 전력 공급예비율 {reserve_rate:.1f}% — {ts:%Y-%m-%d %H:%M}"
