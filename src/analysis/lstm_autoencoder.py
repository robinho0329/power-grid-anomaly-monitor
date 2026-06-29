"""L3 딥러닝 이상탐지 — LSTM-AutoEncoder (Phase 2).

시계열 시퀀스의 '정상 패턴'을 학습하고 재구성 오차(reconstruction error)로
패턴 붕괴형 이상을 잡는다. 충분한 정상 데이터가 누적된 뒤 활성화한다.

⚠️ TensorFlow 의존성이 무거우므로 import는 함수 내부에서 지연 로딩한다.
   (수집/L1/L2 테스트가 TF 없이도 돌도록)
"""
from __future__ import annotations

import numpy as np


def make_sequences(values: np.ndarray, window: int = 12) -> np.ndarray:
    """1D/2D 배열을 (n, window, n_features) 슬라이딩 윈도우로 변환."""
    arr = np.asarray(values, dtype="float32")
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    seqs = [arr[i : i + window] for i in range(len(arr) - window + 1)]
    return np.stack(seqs) if seqs else np.empty((0, window, arr.shape[1]), dtype="float32")


def build_model(window: int, n_features: int, latent: int = 16):
    """LSTM-AutoEncoder 케라스 모델 구성. (TF 지연 import)"""
    from tensorflow import keras
    from tensorflow.keras import layers

    inputs = keras.Input(shape=(window, n_features))
    x = layers.LSTM(latent, activation="tanh")(inputs)          # 인코더
    x = layers.RepeatVector(window)(x)
    x = layers.LSTM(latent, activation="tanh", return_sequences=True)(x)  # 디코더
    outputs = layers.TimeDistributed(layers.Dense(n_features))(x)
    model = keras.Model(inputs, outputs)
    model.compile(optimizer="adam", loss="mse")
    return model


def reconstruction_error(model, sequences: np.ndarray) -> np.ndarray:
    """시퀀스별 재구성 MSE 반환 (값이 클수록 이상)."""
    pred = model.predict(sequences, verbose=0)
    return np.mean(np.square(sequences - pred), axis=(1, 2))


# NOTE(Phase 2): train_and_score() — 정상구간 학습 → 임계(예: 평균+3σ) 설정 →
#   L1/L2와 탐지지연·거짓경보율 비교 표 산출. 데이터 누적 후 구현.
