"""프로젝트 전역 설정 — 경로, KPX API 엔드포인트, 지표/임계값 상수."""
import os
from pathlib import Path

from dotenv import load_dotenv

# 기준 경로
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "src" / "storage" / "data.db"

load_dotenv(BASE_DIR / ".env")

# KPX OpenAPI (공공데이터포털)
KPX_API_KEY = os.getenv("KPX_API_KEY", "")
KPX_SUKUB_URL = "https://openapi.kpx.or.kr/openapi/sukub5mToday/getSukub5mToday"
KPX_GEN_URL = "https://openapi.kpx.or.kr/openapi/sumperfuel5m/getSumperfuel5m"

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# 모니터링 지표 (제조 메타포 매핑) — KPX sukub5mToday 실제 필드 기준
METRICS = {
    "current_load": "현재수요(부하, MW)",       # 생산라인 처리량
    "forecast_load": "최대예측수요(MW)",        # 당일 목표 부하(라인 캐파)
    "supply_capacity": "공급능력(MW)",
    "reserve_power": "공급예비력(MW)",
    "reserve_rate": "공급예비율(%)",            # 안전재고/여유율
    "oper_reserve_rate": "운영예비율(%)",
}

# 경보 임계 (예비율 낮을수록 위험 — 전력경보 단계 참고)
RESERVE_RATE_THRESHOLDS = {
    "관심": 100.0,  # 예비력 기준이지만 데모는 예비율(%)로 단순화
    "주의": 10.0,   # 예비율 10% 미만 주의
    "경계": 7.0,
    "심각": 5.0,
}
