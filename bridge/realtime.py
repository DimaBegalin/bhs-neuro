"""Онлайн-метрики для живого экрана.

Три показателя, каждый со своим основанием:
- фокус, индекс вовлечённости beta/(alpha+theta): Pope, Bogart, Bartolome (1995),
  Biological Psychology 40(1-2), 187-195;
- когнитивная нагрузка, отношение theta к alpha;
- расслабление, доля альфы в суммарной мощности 1-30 Гц.

Всё считается в индивидуальных полосах, отсчитанных от IAF ребёнка, и делится
на его же значение в покое. Поэтому 50 процентов на экране это ровно личный
покой, выше и ниже это отклонение от себя самого.
"""
import time

import numpy as np

from analyzer.preprocess import bandpass, notch
from analyzer.spectra import band_power
from scipy.signal import welch

# пересчёт чаще, чем отправка на экран: иначе одно и то же значение уходит
# дважды подряд и линия идёт ступеньками
MIN_STEP_S = 0.1
# сглаживание показаний: без него линия рвётся, потому что спектр короткого
# окна прыгает от эпохи к эпохе. Чем меньше вес, тем плавнее ход
SMOOTHING = 0.35
# порог по размаху после фильтра: на сухих электродах прибора чистый сигнал
# укладывается в сотни микровольт, всё что выше это движение или срыв контакта
ARTIFACT_PTP_UV = 400.0
ARTIFACT_HF_RATIO = 0.35


# чувствительность шкалы: меньше значение, резче реакция на изменение.
# 1.2 подобрано так, чтобы двукратное изменение показателя давало около
# семидесяти процентов, а не пятидесяти шести, как при простом отношении
SCALE = 1.2


def _to_percent(ratio: float) -> float:
    """Отношение к покою в шкале 0-100, где покой это ровно 50.

    Простое ratio/(1+ratio) сжимает изменения так, что на экране почти ничего
    не происходит. Логарифм с гиперболическим тангенсом даёт симметричную
    шкалу: вдвое больше и вдвое меньше отклоняются от середины одинаково.
    """
    if ratio <= 0:
        return 0.0
    return float(50.0 * (1.0 + np.tanh(np.log(ratio) / SCALE)))


class RealtimeMetrics:
    def __init__(self, fs: int = 250, window_s: float = 3.0, buffer_s: float = 10.0) -> None:
        self.fs = fs
        self.window = int(window_s * fs)
        self.capacity = int(buffer_s * fs)
        self._buffer = np.zeros((4, 0))
        self._bands: dict | None = None
        self._baseline: dict | None = None
        self._baseline_kind = "none"
        self._last: dict = {"focus": None, "load": None, "relax": None,
                            "quality": 0.0, "stale": False, "t_s": 0.0,
                            "baseline": "none"}
        self._min_step = int(MIN_STEP_S * fs)
        self._samples_since_update = 0
        self._smoothed: dict[str, float] = {}
        self._t0 = time.monotonic()

    def set_bands(self, bands: dict) -> None:
        self._bands = bands

    def set_baseline(self, freqs: np.ndarray, psd: np.ndarray) -> None:
        """Запоминает покой ребёнка. Вызывается после калибровки."""
        self._baseline = self._raw_metrics(freqs, psd)
        self._baseline_kind = "calibrated"

    def push(self, chunk: np.ndarray) -> None:
        chunk = np.asarray(chunk, dtype=float)
        if chunk.size == 0:
            return
        self._buffer = np.concatenate([self._buffer, chunk], axis=1)
        self._samples_since_update += chunk.shape[1]
        if self._buffer.shape[1] > self.capacity:
            self._buffer = self._buffer[:, -self.capacity:]

    def _raw_metrics(self, freqs: np.ndarray, psd: np.ndarray) -> dict:
        alpha = float((band_power(freqs, psd, *self._bands["alpha_low"])
                       + band_power(freqs, psd, *self._bands["alpha_high"])).mean())
        theta = float(band_power(freqs, psd, *self._bands["theta"]).mean())
        beta = float(band_power(freqs, psd, *self._bands["beta"]).mean())
        total = float(band_power(freqs, psd, 1.0, 30.0).mean())
        return {
            "focus": beta / (alpha + theta) if (alpha + theta) > 0 else 0.0,
            "load": theta / alpha if alpha > 0 else 0.0,
            "relax": alpha / total if total > 0 else 0.0,
        }

    def _is_artifact(self, window: np.ndarray) -> bool:
        if float(np.ptp(window, axis=-1).max()) > ARTIFACT_PTP_UV:
            return True
        freqs, psd = welch(window, fs=self.fs, nperseg=min(256, window.shape[-1]), axis=-1)
        total = psd[:, (freqs >= 1) & (freqs <= 45)].sum(axis=-1)
        high = psd[:, (freqs > 30) & (freqs <= 45)].sum(axis=-1)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(total > 0, high / total, 1.0)
        return bool(np.nanmax(ratio) > ARTIFACT_HF_RATIO)

    def snapshot(self) -> dict:
        """Текущие метрики. Пересчёт идёт по приходу новых данных, а не по часам:
        так результат воспроизводим и не зависит от того, как часто дёргают экран."""
        self._last["t_s"] = time.monotonic() - self._t0
        if self._samples_since_update < self._min_step:
            return dict(self._last)
        self._samples_since_update = 0

        if self._bands is None or self._buffer.shape[1] < self.window:
            return dict(self._last)

        # фильтруем до проверки на артефакт: сухие электроды дают сильный
        # дрейф, и на сыром окне размах всегда за порогом, а сигнал при этом
        # нормальный
        window = self._buffer[:, -self.window:]
        clean = bandpass(notch(window, fs=self.fs), fs=self.fs, low=2.0)
        if self._is_artifact(clean):
            self._last["stale"] = True
            self._last["quality"] = 0.0
            return dict(self._last)

        freqs, psd = welch(clean, fs=self.fs, window="hann",
                           nperseg=clean.shape[-1], axis=-1)
        raw = self._raw_metrics(freqs, psd)

        if self._baseline is None:
            # покой ещё не снят: берём первое валидное окно как временную опору,
            # чтобы экран сразу жил. На разборе такая шкала не используется.
            self._baseline = dict(raw)
            self._baseline_kind = "auto"
        base = self._baseline
        self._last["baseline"] = self._baseline_kind
        for key in ("focus", "load", "relax"):
            reference = base.get(key, 0.0)
            ratio = raw[key] / reference if reference > 0 else 1.0
            value = _to_percent(ratio)
            previous = self._smoothed.get(key)
            self._smoothed[key] = (value if previous is None
                                   else previous + SMOOTHING * (value - previous))
            self._last[key] = round(self._smoothed[key], 1)
        self._last["stale"] = False
        self._last["quality"] = 1.0
        # сырые индексы отдаём наружу: по ним калибруется шкала
        self._last["raw"] = {k: round(v, 6) for k, v in raw.items()}
        return dict(self._last)
