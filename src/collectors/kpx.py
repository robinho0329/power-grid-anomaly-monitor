"""KPX(한국전력거래소) 전력수급/발전믹스 수집기.

실제 KPX OpenAPI는 XML(application/xml)을 반환한다.
파싱 로직(parse_sukub/parse_generation)은 XML 문자열을 받는 순수 함수로 분리해
네트워크 없이 테스트 가능하게 한다.
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

import requests

from src import config

logger = logging.getLogger(__name__)


# ── 수급(sukub5mToday) 실제 태그 매핑 ───────────────────────────────
# baseDatetime, suppAbility(공급능력), currPwrTot(현재수요),
# forecastLoad(최대예측수요), suppReservePwr(공급예비력),
# suppReserveRate(공급예비율), operReservePwr(운영예비력), operReserveRate(운영예비율)
_SUKUB_MAP = {
    "suppAbility": "supply_capacity",
    "currPwrTot": "current_load",
    "forecastLoad": "forecast_load",
    "suppReservePwr": "reserve_power",
    "suppReserveRate": "reserve_rate",
    "operReservePwr": "oper_reserve_power",
    "operReserveRate": "oper_reserve_rate",
}

# ── 발전믹스(sumperfuel5m) fuelPwr1~9 → 표준 발전원 ──────────────────
_FUEL_MAP = {
    "fuelPwr1": "수력", "fuelPwr2": "유류", "fuelPwr3": "석탄",  # 유연탄
    "fuelPwr4": "원자력", "fuelPwr5": "양수", "fuelPwr6": "LNG",  # 가스
    "fuelPwr7": "석탄",  # 국내탄
    "fuelPwr8": "신재생", "fuelPwr9": "신재생",  # 신재생/태양광
}


def _items(xml_text: str) -> list[dict[str, str]]:
    """XML 문자열에서 <item> 요소들을 {tag: text} dict 리스트로 추출."""
    root = ET.fromstring(xml_text)
    out: list[dict[str, str]] = []
    for item in root.iter("item"):
        out.append({child.tag: (child.text or "").strip() for child in item})
    return out


def parse_sukub(xml_text: str) -> list[dict]:
    """수급 XML → 표준 레코드 리스트."""
    records: list[dict] = []
    for it in _items(xml_text):
        ts = _parse_ts(it.get("baseDatetime"))
        if ts is None:
            continue
        rec = {"ts": ts}
        for src_tag, col in _SUKUB_MAP.items():
            rec[col] = _to_float(it.get(src_tag))
        records.append(rec)
    return records


def parse_generation(xml_text: str) -> list[dict]:
    """발전믹스 XML → long 레코드 [{ts, source, generation_mw}].

    fuelPwr1~9를 표준 발전원으로 매핑하고, 같은 발전원(유연탄+국내탄=석탄,
    신재생+태양광=신재생)은 합산한다. fuelPwrTot(총수요)는 제외.
    """
    records: list[dict] = []
    for it in _items(xml_text):
        ts = _parse_ts(it.get("baseDatetime"))
        if ts is None:
            continue
        agg: dict[str, float] = {}
        for tag, source in _FUEL_MAP.items():
            val = _to_float(it.get(tag))
            if val is not None:
                agg[source] = agg.get(source, 0.0) + val
        for source, mw in agg.items():
            records.append({"ts": ts, "source": source, "generation_mw": mw})
    return records


def fetch_sukub(api_key: str | None = None, timeout: int = 10) -> list[dict]:
    """수급 API 호출 → 파싱된 레코드. (네트워크 필요)"""
    return parse_sukub(_get(config.KPX_SUKUB_URL, api_key, timeout))


def fetch_generation(api_key: str | None = None, timeout: int = 10) -> list[dict]:
    """발전믹스 API 호출 → long 레코드. (네트워크 필요)"""
    return parse_generation(_get(config.KPX_GEN_URL, api_key, timeout))


def _get(url: str, api_key: str | None, timeout: int, retries: int = 3) -> str:
    """KPX 호출. 간헐적 5xx에 대비해 재시도하고, 에러에 serviceKey가 노출되지 않게 마스킹."""
    api_key = api_key or config.KPX_API_KEY
    if not api_key:
        raise RuntimeError("KPX_API_KEY 미설정 — .env를 확인하세요.")

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params={"serviceKey": api_key}, timeout=timeout)
            if resp.status_code >= 500:  # KPX 간헐적 500 → 재시도
                last_err = RuntimeError(f"KPX {resp.status_code} (일시적)")
                logger.warning("KPX %d, 재시도 %d/%d", resp.status_code, attempt, retries)
                time.sleep(1.5 * attempt)
                continue
            resp.raise_for_status()
            # data.go.kr 표준 에러(SERVICE ACCESS DENIED 등)는 HTTP 200으로 옴 → 본문 확인
            msg = _result_msg(resp.text)
            if msg and "OK" not in msg:
                raise RuntimeError(f"KPX API 거부: {msg}")
            return resp.text
        except requests.RequestException as e:
            last_err = RuntimeError(str(e).replace(api_key, "<KEY>"))
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"KPX 호출 실패({retries}회): {last_err}")


def _result_msg(xml_text: str) -> str | None:
    try:
        root = ET.fromstring(xml_text)
        el = root.find(".//resultMsg")
        return el.text.strip() if el is not None and el.text else None
    except ET.ParseError:
        return None


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
