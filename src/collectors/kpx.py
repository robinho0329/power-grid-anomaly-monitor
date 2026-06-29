"""KPX(한국전력거래소) 전력수급 수집기.

오늘전력수급현황 API를 5분 주기로 호출해 레코드로 파싱한다.
파싱 로직(parse_sukub)은 순수 함수로 분리해 테스트 가능하게 한다.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import requests

from src import config

logger = logging.getLogger(__name__)


def parse_sukub(payload: dict[str, Any]) -> list[dict]:
    """KPX 수급 API 응답(JSON dict)을 표준 레코드 리스트로 변환.

    응답 형식 변동에 대비해 키를 방어적으로 매핑한다.
    기대 필드: baseDatetime, supplyCapacity, currentLoad, supplyReserve,
              supplyReserveRate, temperature
    """
    items = (
        payload.get("response", {})
        .get("body", {})
        .get("items", {})
        .get("item", [])
    )
    if isinstance(items, dict):  # 단일 건이면 dict로 올 수 있음
        items = [items]

    records: list[dict] = []
    for it in items:
        ts_raw = it.get("baseDatetime") or it.get("기준일시")
        records.append(
            {
                "ts": _parse_ts(ts_raw),
                "supply_capacity": _to_float(it.get("supplyCapacity") or it.get("공급능력")),
                "current_load": _to_float(it.get("currentLoad") or it.get("현재수요")),
                "reserve_power": _to_float(it.get("supplyReserve") or it.get("공급예비력")),
                "reserve_rate": _to_float(it.get("supplyReserveRate") or it.get("공급예비율")),
                "temperature": _to_float(it.get("temperature") or it.get("기온")),
            }
        )
    return [r for r in records if r["ts"] is not None]


def fetch_sukub(api_key: str | None = None, timeout: int = 10) -> list[dict]:
    """실제 KPX API 호출 → 파싱된 레코드 반환. (네트워크 필요)"""
    api_key = api_key or config.KPX_API_KEY
    if not api_key:
        raise RuntimeError("KPX_API_KEY 미설정 — .env를 확인하세요.")
    params = {"serviceKey": api_key, "returnType": "json"}
    resp = requests.get(config.KPX_SUKUB_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    records = parse_sukub(resp.json())
    logger.info("KPX 수급 %d건 수집", len(records))
    return records


# 발전원 키 정규화 (영문/한글 변형 → 표준 라벨)
_SOURCE_ALIASES = {
    "nuclear": "원자력", "원자력": "원자력",
    "coal": "석탄", "유연탄": "석탄", "무연탄": "석탄", "석탄": "석탄",
    "gas": "LNG", "lng": "LNG", "lng복합": "LNG", "가스": "LNG", "LNG": "LNG",
    "oil": "유류", "유류": "유류",
    "hydro": "수력", "수력": "수력",
    "pumped": "양수", "양수": "양수",
    "renewable": "신재생", "신재생": "신재생", "태양광": "신재생", "풍력": "신재생",
}
_NON_SOURCE_KEYS = {"basedatetime", "기준일시", "ts", "기준시각"}


def parse_generation(payload: dict[str, Any]) -> list[dict]:
    """발전원별 발전량 응답을 long 레코드 [{ts, source, generation_mw}]로 변환.

    두 가지 형태를 모두 지원한다.
    - long: item = {baseDatetime, fuel/발전원, generation/발전량}
    - wide: item = {baseDatetime, 원자력: .., 석탄: .., LNG: ..}
    """
    items = (
        payload.get("response", {})
        .get("body", {})
        .get("items", {})
        .get("item", [])
    )
    if isinstance(items, dict):
        items = [items]

    records: list[dict] = []
    for it in items:
        ts = _parse_ts(it.get("baseDatetime") or it.get("기준일시"))
        if ts is None:
            continue
        fuel = it.get("fuel") or it.get("발전원") or it.get("fuelType")
        if fuel is not None:  # long 형태
            records.append(
                {
                    "ts": ts,
                    "source": _norm_source(fuel),
                    "generation_mw": _to_float(it.get("generation") or it.get("발전량")),
                }
            )
        else:  # wide 형태 → 소스 컬럼 펼치기
            for key, val in it.items():
                if str(key).lower() in _NON_SOURCE_KEYS:
                    continue
                records.append(
                    {"ts": ts, "source": _norm_source(key), "generation_mw": _to_float(val)}
                )
    return [r for r in records if r["generation_mw"] is not None]


def fetch_generation(api_key: str | None = None, timeout: int = 10) -> list[dict]:
    """발전원별 발전량 API 호출 → long 레코드 반환. (네트워크 필요)"""
    api_key = api_key or config.KPX_API_KEY
    if not api_key:
        raise RuntimeError("KPX_API_KEY 미설정 — .env를 확인하세요.")
    params = {"serviceKey": api_key, "returnType": "json"}
    resp = requests.get(config.KPX_GEN_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    records = parse_generation(resp.json())
    logger.info("KPX 발전믹스 %d건 수집", len(records))
    return records


def _norm_source(raw: Any) -> str:
    key = str(raw).strip()
    return _SOURCE_ALIASES.get(key.lower(), _SOURCE_ALIASES.get(key, key))


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None
