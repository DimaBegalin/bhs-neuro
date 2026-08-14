"""Расширенный набор показателей для отчёта.

Всё, что можно честно посчитать из четырёх каналов: полосы ритмов, индексы
состояния, спектр, ход внимания по времени, поведение на задачах.
Чего в приборе нет, того и в отчёте нет: пульс требует отдельного датчика.
"""
import numpy as np

from analyzer.iaf import bands_from_iaf, compute_iaf
from analyzer.loader import load_session
from analyzer.metrics import engagement_index
from analyzer.preprocess import bandpass, epoch, notch, reject_epochs
from analyzer.session_timeline import compute_session_timeline
from analyzer.spectra import band_power, psd_of_epochs

CHANNELS = ("T3", "T4", "O1", "O2")
DOMAINS = ("numeric", "spatial", "verbal", "working_memory")
CLASSIC_BANDS = {"delta": (1.0, 4.0), "theta": (4.0, 8.0), "alpha": (8.0, 13.0),
                 "beta": (13.0, 30.0), "gamma": (30.0, 40.0)}
IAF_HIGHPASS_HZ = 5.0
BANDS_HIGHPASS_HZ = 2.0


def _clean(signal, fs, low=BANDS_HIGHPASS_HZ):
    return bandpass(notch(signal, fs=fs), fs=fs, low=low)


def _relative_bands(freqs, psd) -> dict:
    """Доля каждого ритма в общей мощности, в процентах."""
    total = float(band_power(freqs, psd, 1.0, 40.0).mean())
    if total <= 0:
        return {name: 0.0 for name in CLASSIC_BANDS}
    return {name: round(float(band_power(freqs, psd, lo, hi).mean()) / total * 100, 1)
            for name, (lo, hi) in CLASSIC_BANDS.items()}


def _state_indices(freqs, psd, bands) -> dict:
    """Индексы состояния. Каждый считается из полос, ничего не выдумано."""
    alpha = float((band_power(freqs, psd, *bands["alpha_low"])
                   + band_power(freqs, psd, *bands["alpha_high"])).mean())
    theta = float(band_power(freqs, psd, *bands["theta"]).mean())
    beta = float(band_power(freqs, psd, *bands["beta"]).mean())
    total = float(band_power(freqs, psd, 1.0, 40.0).mean()) or 1.0
    # стресс как перевес быстрых ритмов над медленными: чем выше бета
    # относительно альфы, тем напряжённее состояние
    return {
        "focus": round(beta / (alpha + theta), 3) if (alpha + theta) > 0 else 0.0,
        "load": round(theta / alpha, 3) if alpha > 0 else 0.0,
        "relax": round(alpha / total, 3),
        "stress": round(beta / alpha, 3) if alpha > 0 else 0.0,
        "engagement": round(engagement_index(freqs, psd, bands), 3),
    }


def _trials_on_timeline(session, domain: str, window: tuple) -> list:
    """Ответы ребёнка с привязкой ко времени блока.

    Нужно, чтобы наложить их на ленту состояния и увидеть, что происходило
    с мозгом на конкретном задании.
    """
    start, end = window
    out = []
    for event in session.events:
        if event["kind"] != "trial":
            continue
        payload = event["payload"]
        if payload.get("domain") != domain:
            continue
        if not (start <= event["t_s"] <= end):
            continue
        out.append({"at": round(event["t_s"] - start, 2),
                    "correct": bool(payload.get("correct")),
                    "rt_ms": int(payload.get("rt_ms", 0))})
    return out


def _block_window(session, domain: str) -> tuple | None:
    start = end = None
    for event in session.events:
        payload = event.get("payload") or {}
        if payload.get("domain") != domain:
            continue
        if event["kind"] == "block_start":
            start = event["t_s"]
        elif event["kind"] == "block_end":
            end = event["t_s"]
    return (start, end) if start is not None and end is not None else None


def _timeline(epochs, keep, fs, bands) -> list:
    """Ход вовлечённости по эпохам: из этого рисуется линия на отчёте."""
    points = []
    for index in np.flatnonzero(keep):
        freqs, psd = psd_of_epochs(epochs[index:index + 1], fs=fs)
        points.append(round(engagement_index(freqs, psd, bands), 3))
    return points


def _sync_pct(session, bands, fs) -> int | None:
    """Синхронность полушарий: связь одноимённых каналов слева и справа.

    Считается по личной верхней альфе: корреляция T3 с T4 и O1 с O2 по
    принятым эпохам, среднее по сессии. Высокая связь значит полушария
    работают слаженно; это честная и проверяемая мера, без эзотерики.
    """
    signal = bandpass(notch(session.signal, fs=fs), fs=fs,
                      low=max(bands["alpha_high"][0], 2.0),
                      high=bands["alpha_high"][1])
    eps = epoch(signal, fs=fs)
    keep = reject_epochs(epoch(_clean(session.signal, fs), fs=fs), fs=fs)
    keep = keep[:eps.shape[0]]
    values = []
    for i in np.flatnonzero(keep):
        block = eps[i]
        r_temporal = np.corrcoef(block[0], block[1])[0, 1]
        r_occipital = np.corrcoef(block[2], block[3])[0, 1]
        values.append((abs(r_temporal) + abs(r_occipital)) / 2)
    if len(values) < 10:
        return None
    return int(round(float(np.mean(values)) * 100))


def build_report_data(npz_path: str, events_path: str, profile: dict) -> dict:
    """Собирает всё, что нужно отчёту, поверх готового профиля."""
    session = load_session(npz_path, events_path)
    fs = session.fs

    closed = _clean(session.slice("calibration_eyes_closed_start",
                                  "calibration_eyes_closed_end"), fs, IAF_HIGHPASS_HZ)
    closed_epochs = epoch(closed, fs=fs)
    closed_keep = reject_epochs(closed_epochs, fs=fs)
    iaf, prominence = (None, 0.0)
    if closed_keep.any():
        freqs, psd = psd_of_epochs(closed_epochs, fs=fs, keep=closed_keep)
        iaf, prominence = compute_iaf(freqs, psd)
    bands = bands_from_iaf(iaf if iaf else 10.0)

    rest_raw = session.slice("calibration_eyes_open_start",
                             "calibration_eyes_open_end")
    rest_epochs = epoch(_clean(rest_raw, fs), fs=fs)
    rest_keep = reject_epochs(rest_epochs, fs=fs)
    rest_freqs, rest_psd = psd_of_epochs(
        rest_epochs, fs=fs, keep=rest_keep if rest_keep.any() else None)
    rest = {"bands": _relative_bands(rest_freqs, rest_psd),
            "state": _state_indices(rest_freqs, rest_psd, bands)}

    blocks = {}
    spectrum_ref = None
    for domain in DOMAINS:
        raw = session.slice("block_start", "block_end",
                            payload_filter={"domain": domain})
        epochs = epoch(_clean(raw, fs), fs=fs)
        keep = reject_epochs(epochs, fs=fs)
        if not keep.any():
            keep = np.ones(len(keep), dtype=bool)
        freqs, psd = psd_of_epochs(epochs, fs=fs, keep=keep)
        if spectrum_ref is None:
            mask = (freqs >= 1) & (freqs <= 40)
            spectrum_ref = {"freqs": [round(f, 2) for f in freqs[mask]]}
        mask = (freqs >= 1) & (freqs <= 40)
        window = _block_window(session, domain)
        blocks[domain] = {
            "duration_s": round(window[1] - window[0], 1) if window else 0.0,
            "trials": _trials_on_timeline(session, domain, window) if window else [],
            "bands": _relative_bands(freqs, psd),
            "state": _state_indices(freqs, psd, bands),
            "spectrum": [round(float(v), 4) for v in psd[:, mask].mean(axis=0)],
            "per_channel_alpha": [round(float(v), 2) for v in
                                  band_power(freqs, psd, *bands["alpha_high"])],
            "timeline": _timeline(epochs, keep, fs, bands),
            "quality": round(float(keep.mean()) * 100, 1),
        }

    behavior = profile.get("behavior", {})
    reaction = {d: round(behavior.get(d, {}).get("median_rt_ms", 0) / 1000.0, 2)
                for d in DOMAINS}

    timeline = compute_session_timeline(npz_path, events_path, bands)
    sync_pct = _sync_pct(session, bands, fs)

    return {
        "sync_pct": sync_pct,
        "timeline": timeline,
        "session_id": profile["session_id"],
        "iaf": round(iaf, 2) if iaf else None,
        "iaf_prominence": round(prominence, 2),
        "bands_hz": {k: [round(v[0], 1), round(v[1], 1)] for k, v in bands.items()},
        "channels": list(CHANNELS),
        "rest": rest,
        "blocks": blocks,
        "spectrum_freqs": spectrum_ref["freqs"] if spectrum_ref else [],
        "reaction_s": reaction,
        "profile": profile,
        "notes": {
            "pulse": "пульса нет: прибор снимает только электрическую активность, "
                     "для пульса нужен отдельный датчик",
        },
    }
