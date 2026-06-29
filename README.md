# ⚡ 실시간 전력수급 이상탐지 모니터링 시스템

> 한국 전력계통을 **제조 생산라인**에 빗대어, KPX 5분 단위 전력수급 데이터를
> 자동 수집하고 **다층 이상탐지(통계·ML·딥러닝)**로 분석하는 무중단·무비용 모니터링 시스템.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Tests](https://img.shields.io/badge/tests-pytest-green)
![License](https://img.shields.io/badge/license-MIT-green)

> 자매 프로젝트 [`chungbuk-air-quality-monitor`](https://github.com/robinho0329/chungbuk-air-quality-monitor)는 **SPC(통계적 공정관리)** 중심,
> 본 프로젝트는 **ML/DL 기반 이상탐지** 중심으로 기법을 차별화합니다.

---

## 🎯 프로젝트 목적

반도체 팹 등 대규모 제조설비는 **전력 안정성이 수율과 직결**됩니다.
"유틸리티 설비 실시간 감시"를 실데이터로 구현해 **생산관리 + 시계열 이상탐지** 역량을 입증합니다.

| 제조 공정 | 본 프로젝트 |
|---|---|
| 생산라인 부하 / throughput | 현재 전력수요(MW) |
| 안전재고 · 여유율 | 공급예비율(%) |
| 다중 설비 가동 상태 | 발전원별 발전량 |
| 규격 한계 USL/LSL | 예비율 임계선 |
| **공정 이상** | 수요 급변 · 예비율 급락 · 예측오차 폭증 |

## 🧠 다층 이상탐지 (핵심 차별점)

| 계층 | 방법 | 잡는 이상 | 상태 |
|---|---|---|---|
| **L1 통계** | EWMA / CUSUM | 점진적 변화·레벨 이동 (단변량) | ✅ Phase 1 |
| **L2 ML** | Isolation Forest | 조합의 이상 (다변량) | ✅ Phase 1 |
| **L3 딥러닝** | LSTM-AutoEncoder | 패턴 붕괴 (시계열 잔차) | 🟡 Phase 2 (데이터 누적 후) |

> L3를 Phase 2로 둔 이유: ① 충분한 정상 시계열이 쌓여야 학습 가능 ② TF 의존성이 무거움
> ③ "동작하는 MVP 먼저 → 반복 개선" 원칙. 같은 이벤트에 L1<L2<L3 탐지지연·거짓경보율 비교가 목표.

---

## 🏗️ 구조

```
src/
├─ config.py              # 경로·API·임계 상수
├─ collectors/kpx.py      # KPX 수급 API 수집 + 파싱(순수 함수)
├─ storage/               # SQLAlchemy ORM 모델 + 멱등 저장
├─ analysis/
│  ├─ ewma_cusum.py       # L1 통계 (EWMA + CUSUM)
│  ├─ isolation_forest.py # L2 ML (다변량)
│  ├─ demand_forecast.py  # 수요 예측 + 잔차 기반 이상탐지
│  └─ lstm_autoencoder.py # L3 딥러닝 (Phase 2)
└─ notifier/discord.py    # Discord 경보
flows/collect_flow.py     # 수집 오케스트레이션
scripts/collect_once.py   # 진입점 (CI cron)
dashboard/
├─ app.py                 # 메인 (수급 요약 KPI)
└─ pages/
   ├─ 1_🗺️_발전소_지도.py     # GIS 맥락 레이어
   ├─ 2_📊_실시간_모니터링.py  # 부하 곡선·예비율 게이지·경보
   ├─ 3_🚨_이상탐지_타임라인.py # L1/L2/L3 결과 중첩 시각화
   ├─ 4_🔋_발전믹스.py         # 원자력·LNG·석탄·신재생 스택
   ├─ 5_📈_탐지_비교.py        # 3계층 성능 비교 + 합성 이벤트 주입
   └─ 6_🔮_수요예측.py         # 계절 기준선 예측 + 잔차 이상탐지
tests/                    # pytest 15개 (파싱·L1·L2·저장·수요예측)
```

## 🚀 실행

```bash
# 환경 설정
py -3.12 -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # KPX_API_KEY 입력 (공공데이터포털 발급)

# 수집 & 대시보드
python -m scripts.collect_once     # 1회 수집
streamlit run dashboard/app.py     # 대시보드 (http://localhost:8501)

# 테스트
pytest -q                          # 15개 테스트
```

## 📡 데이터 출처
- 한국전력거래소(KPX) 오늘전력수급현황 / 발전원별 발전량 API (공공데이터포털, 개발단계 자동승인)

## 🔒 보안
- API Key는 `.env`에만 저장하고 `.gitignore`에 포함 — GitHub는 Secrets 사용.

## 🗺️ 로드맵
- [x] Phase 1: 수집 · L1/L2 이상탐지 · 발전소 지도 · CI 골격
- [x] Phase 1.5: **대시보드 5페이지** (모니터링·이상타임라인·발전믹스·탐지비교·수요예측) + **수요 예측 모듈** (`demand_forecast.py`)
- [ ] Phase 1.5(잔여): Discord 경보 연동, 외부 cron, KPX API 키 등록
- [ ] Phase 2: L3 LSTM-AE 학습·평가 + 3계층 거짓경보율·탐지지연 비교 표 + 포트폴리오 덱

> 🗺️ **지도에 대한 입장:** 실시간 수급은 전국 단일값이라 공간 차원이 없다.
> 지도는 발전소 **위치(정적)** 를 보여주는 **맥락·탐색 레이어**이며, 이상탐지는
> 전국 시계열에서 수행한다(공간 이상탐지가 아님).
