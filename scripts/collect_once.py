"""1회 수집 진입점 — GitHub Actions cron / 로컬 실행 공용.

    python -m scripts.collect_once
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from flows.collect_flow import run_collect  # noqa: E402


def main() -> int:
    logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
    try:
        result = run_collect()
        print(f"OK: 수급 {result['sukub']}건, 발전믹스 {result['generation']}건 저장")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"수집 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
