"""Полный расчёт профиля из файлов сессии."""
import argparse
import json

from analyzer.loader import load_session
from analyzer.preprocess import bandpass, notch, epoch, reject_epochs
from analyzer.spectra import psd_of_epochs
from analyzer.iaf import compute_iaf, bands_from_iaf
from analyzer.metrics import block_neuro_metrics
from analyzer.behavior import block_behavior
from analyzer.profile import build_profile, DOMAINS

FALLBACK_IAF = 10.0
# сухие электроды прибора дают сильный медленный дрейф, он искажает оценку
# фона 1/f и топит альфа-пик. Для поиска пика режем низкие частоты жёстче,
# для метрик по полосам оставляем мягкий срез, иначе потеряем тету.
IAF_HIGHPASS_HZ = 5.0
BANDS_HIGHPASS_HZ = 2.0


def _clean(signal, fs, low=BANDS_HIGHPASS_HZ):
    return bandpass(notch(signal, fs=fs), fs=fs, low=low)


def analyze(npz_path: str, events_path: str, session_meta: dict) -> dict:
    session = load_session(npz_path, events_path)
    fs = session.fs

    closed_raw = session.slice("calibration_eyes_closed_start",
                               "calibration_eyes_closed_end")
    closed = _clean(closed_raw, fs, low=IAF_HIGHPASS_HZ)
    opened = _clean(session.slice("calibration_eyes_open_start",
                                  "calibration_eyes_open_end"), fs)

    closed_eps = epoch(closed, fs=fs)
    closed_keep = reject_epochs(closed_eps, fs=fs)
    calibration_rejected = float((~closed_keep).mean())

    iaf, prominence = (None, 0.0)
    if closed_keep.any():
        freqs, psd = psd_of_epochs(closed_eps, fs=fs, keep=closed_keep)
        iaf, prominence = compute_iaf(freqs, psd)

    bands = bands_from_iaf(iaf if iaf is not None else FALLBACK_IAF)

    open_eps = epoch(opened, fs=fs)
    open_keep = reject_epochs(open_eps, fs=fs)
    base_pack = psd_of_epochs(open_eps, fs=fs,
                              keep=open_keep if open_keep.any() else None)

    trials = session.trials_by_domain
    blocks = {}
    for domain in DOMAINS:
        raw = session.slice("block_start", "block_end", payload_filter={"domain": domain})
        eps = epoch(_clean(raw, fs), fs=fs)
        keep = reject_epochs(eps, fs=fs)
        # блок может целиком утонуть в артефактах: ребёнок жевал, поправлял
        # ободок, тёр лицо. Считать по нему нечего, но валить весь профиль
        # нельзя: остальные блоки и поведение живые, а вердикт качества сам
        # переведёт профиль в режим «только поведение» по доле брака
        if keep.any():
            neuro = block_neuro_metrics(eps, base_pack, fs=fs, bands=bands, keep=keep)
        else:
            neuro = {"erd_alpha_high": None, "erd_alpha_low": None,
                     "theta_rise": None, "engagement": None,
                     "attention_slope": None,
                     "epochs_total": int(eps.shape[0]),
                     "epochs_rejected": int(eps.shape[0])}
        blocks[domain] = {"behavior": block_behavior(trials.get(domain, [])),
                          "neuro": neuro}

    meta = dict(session_meta)
    meta["calibration_rejected_share"] = calibration_rejected
    return build_profile(meta, iaf, prominence,
                         {k: list(v) for k, v in bands.items()}, blocks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("npz")
    parser.add_argument("events")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--lang", default="ru")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    result = analyze(args.npz, args.events,
                     {"session_id": args.session_id, "lang": args.lang})
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text)
    print(text)
