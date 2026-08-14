"""Полная синтетическая сессия: файлы npz и events.json с известным ответом."""
import json
import os

import numpy as np

from tests.fixtures.synthetic import make_eeg

FS = 250
DOMAINS = ["numeric", "spatial", "verbal", "working_memory"]


def write_session(dir_path, iaf=10.3, strong_domain="spatial", session_id="synthetic"):
    """Пишет сессию, где strong_domain даёт высокую точность малой ценой.

    Возврат: (npz_path, events_path).
    """
    parts, events, t = [], [], 0.0

    def add(signal_seconds, alpha_amp):
        nonlocal t
        parts.append(make_eeg(duration_s=signal_seconds, fs=FS, alpha_hz=iaf,
                              alpha_amp=alpha_amp, seed=int(t) + 1))
        t += signal_seconds

    events.append({"kind": "session_start", "t_s": 0.0, "payload": {}})
    events.append({"kind": "calibration_eyes_closed_start", "t_s": t, "payload": {}})
    add(60.0, 20.0)
    events.append({"kind": "calibration_eyes_closed_end", "t_s": t, "payload": {}})
    events.append({"kind": "calibration_eyes_open_start", "t_s": t, "payload": {}})
    add(30.0, 12.0)
    events.append({"kind": "calibration_eyes_open_end", "t_s": t, "payload": {}})

    for domain in DOMAINS:
        events.append({"kind": "block_start", "t_s": t, "payload": {"domain": domain}})
        block_start = t
        # в сильном домене альфа падает слабо, значит цена усилия ниже
        add(70.0, 10.0 if domain == strong_domain else 4.0)
        for i in range(12):
            correct = True if domain == strong_domain else (i % 3 != 0)
            events.append({"kind": "trial",
                           "t_s": block_start + 2.0 + i * 5.0,
                           "payload": {"domain": domain, "index": i,
                                       "stimulus_id": f"{domain}-{i}",
                                       "correct": correct, "rt_ms": 1000 + i * 20}})
        events.append({"kind": "block_end", "t_s": t, "payload": {"domain": domain}})
        events.append({"kind": "rest_start", "t_s": t, "payload": {}})
        add(10.0, 16.0)
        events.append({"kind": "rest_end", "t_s": t, "payload": {}})

    events.append({"kind": "session_end", "t_s": t, "payload": {}})

    os.makedirs(dir_path, exist_ok=True)
    npz_path = os.path.join(str(dir_path), f"{session_id}.npz")
    events_path = os.path.join(str(dir_path), f"{session_id}.events.json")
    np.savez_compressed(npz_path, signal=np.concatenate(parts, axis=1),
                        fs=np.array(FS), t_start_s=np.array(0.0),
                        channels=np.array(["T3", "T4", "O1", "O2"]))
    with open(events_path, "w", encoding="utf-8") as fh:
        json.dump(events, fh, ensure_ascii=False, indent=2)
    return npz_path, events_path
