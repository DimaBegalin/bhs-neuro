"""Динамика состояния по всей сессии: как менялись напряжение, включённость
и спокойствие от первой секунды до последней.

Это ядро профориентационного замера: не средние числа, а ход состояния
во времени с привязкой к фазам теста. Отсюда считаются усталость,
работоспособность, поток и восстановление в паузах.
"""
import numpy as np
from scipy.signal import welch

from analyzer.human_scale import to_scale
from analyzer.loader import load_session
from analyzer.preprocess import bandpass, epoch, notch, reject_epochs
from analyzer.spectra import band_power

EPOCH_S = 2.0
STEP_S = 1.0
SMOOTH = 5


def _indices(freqs, psd, bands) -> dict:
    alpha = float((band_power(freqs, psd, *bands["alpha_low"])
                   + band_power(freqs, psd, *bands["alpha_high"])).mean())
    theta = float(band_power(freqs, psd, *bands["theta"]).mean())
    beta = float(band_power(freqs, psd, *bands["beta"]).mean())
    total = float(band_power(freqs, psd, 1.0, 30.0).mean()) or 1.0
    return {
        "engage": beta / (alpha + theta) if (alpha + theta) > 0 else 0.0,
        "stress": beta / alpha if alpha > 0 else 0.0,
        "load": theta / alpha if alpha > 0 else 0.0,
        "calm": alpha / total,
    }


def _phases(events) -> list:
    out, starts = [], {}
    for e in events:
        kind = e["kind"]
        payload = e.get("payload") or {}
        if kind == "calibration_eyes_closed_start":
            starts["cc"] = e["t_s"]
        elif kind == "calibration_eyes_closed_end" and "cc" in starts:
            out.append({"kind": "calib", "label": "глаза закрыты",
                        "start": starts.pop("cc"), "end": e["t_s"]})
        elif kind == "calibration_eyes_open_start":
            starts["co"] = e["t_s"]
        elif kind == "calibration_eyes_open_end" and "co" in starts:
            out.append({"kind": "calib", "label": "глаза открыты",
                        "start": starts.pop("co"), "end": e["t_s"]})
        elif kind == "block_start":
            starts["b:" + payload.get("domain", "")] = e["t_s"]
        elif kind == "block_end":
            key = "b:" + payload.get("domain", "")
            if key in starts:
                out.append({"kind": "block", "domain": payload.get("domain"),
                            "start": starts.pop(key), "end": e["t_s"]})
        elif kind == "rest_start":
            starts["r"] = e["t_s"]
        elif kind == "rest_end" and "r" in starts:
            out.append({"kind": "rest", "label": "пауза",
                        "start": starts.pop("r"), "end": e["t_s"]})
    return sorted(out, key=lambda p: p["start"])


def compute_session_timeline(npz_path: str, events_path: str, bands: dict) -> dict:
    session = load_session(npz_path, events_path)
    fs = session.fs
    signal = bandpass(notch(session.signal, fs=fs), fs=fs, low=2.0)
    eps = epoch(signal, fs=fs, epoch_s=EPOCH_S, overlap=0.5)
    keep = reject_epochs(eps, fs=fs)
    times = [i * STEP_S + EPOCH_S / 2 for i in range(eps.shape[0])]

    raw: list = []
    for i in range(eps.shape[0]):
        if not keep[i]:
            raw.append(None)
            continue
        freqs, psd = welch(eps[i], fs=fs, window="hann",
                           nperseg=eps.shape[-1], axis=-1)
        raw.append(_indices(freqs, psd, bands))

    phases = _phases(session.events)
    blocks_ph = [p for p in phases if p["kind"] == "block"]
    rest_ph = [p for p in phases if p["kind"] == "rest"]

    open_ph = next((p for p in phases if p["kind"] == "calib"
                    and p["label"] == "глаза открыты"), None)
    if open_ph:
        rest_raw = [r for t, r in zip(times, raw)
                    if r and open_ph["start"] <= t <= open_ph["end"]]
    else:
        rest_raw = [r for r in raw if r][:10]
    restv = {k: max(float(np.mean([r[k] for r in rest_raw])), 1e-6)
             for k in ("engage", "stress", "load", "calm")} if rest_raw else \
            {k: 1e-6 for k in ("engage", "stress", "load", "calm")}

    def series(key):
        vals = [to_scale(r[key], restv[key]) if r else None for r in raw]
        out = []
        for i, v in enumerate(vals):
            if v is None:
                out.append(None)
                continue
            window = [vals[j] for j in
                      range(max(0, i - SMOOTH // 2),
                            min(len(vals), i + SMOOTH // 2 + 1))
                      if vals[j] is not None]
            out.append(round(float(np.mean(window)), 1))
        return out

    S = {k: series(k) for k in ("engage", "stress", "calm", "load")}

    def in_block(t):
        return any(p["start"] <= t <= p["end"] for p in blocks_ph)

    task_i = [i for i, t in enumerate(times) if raw[i] and in_block(t)]

    peak = None
    if task_i:
        pi = max(task_i, key=lambda i: S["stress"][i] or 0)
        ph = next((p for p in blocks_ph
                   if p["start"] <= times[pi] <= p["end"]), None)
        peak = {"t": round(times[pi], 1), "score": S["stress"][pi],
                "domain": ph["domain"] if ph else None}

    hold = (sum(1 for i in task_i if raw[i]["engage"] > restv["engage"])
            / len(task_i) * 100) if task_i else 0.0
    flow = (sum(1 for i in task_i
                if raw[i]["engage"] > restv["engage"] * 1.15
                and raw[i]["stress"] < restv["stress"] * 1.3)
            / len(task_i) * 100) if task_i else 0.0

    fatigue = None
    if len(task_i) >= 9:
        third = len(task_i) // 3
        first = float(np.mean([raw[i]["load"] for i in task_i[:third]]))
        last = float(np.mean([raw[i]["load"] for i in task_i[-third:]]))
        delta = (last - first) / first * 100 if first > 0 else 0.0
        if delta < 15:
            words = "усталость к концу не накопилась"
        elif delta < 40:
            words = "к концу появилась умеренная усталость"
        else:
            words = "к концу теста накопилась заметная усталость"
        fatigue = {"delta_pct": round(delta), "score": to_scale(last, first),
                   "verdict": words}

    workability = []
    for order, ph in enumerate(blocks_ph, 1):
        ids = [i for i in task_i if ph["start"] <= times[i] <= ph["end"]]
        vals = [S["engage"][i] for i in ids if S["engage"][i] is not None]
        if vals:
            workability.append({"order": order, "domain": ph["domain"],
                                "score": round(float(np.mean(vals)))})

    ratios = []
    for rp in rest_ph:
        prev = max((b for b in blocks_ph if b["end"] <= rp["start"] + 0.5),
                   default=None, key=lambda b: b["end"])
        if prev is None:
            continue
        in_rest = [raw[i]["calm"] for i, t in enumerate(times)
                   if raw[i] and rp["start"] <= t <= rp["end"]]
        in_prev = [raw[i]["calm"] for i, t in enumerate(times)
                   if raw[i] and prev["start"] <= t <= prev["end"]]
        if in_rest and in_prev and np.mean(in_prev) > 0:
            ratios.append(float(np.mean(in_rest) / np.mean(in_prev)))
    recovery = {"ratio": round(float(np.mean(ratios)), 2) if ratios else None}
    if recovery["ratio"] is not None:
        r = recovery["ratio"]
        recovery["verdict"] = ("в паузах хорошо восстанавливается" if r >= 1.15
                               else "в паузах восстанавливается частично" if r >= 1.0
                               else "в паузах не успевает восстановиться")
    else:
        recovery["verdict"] = "пауз для оценки не хватило"

    ticks = [{"t": round(e["t_s"], 1),
              "ok": bool((e.get("payload") or {}).get("correct"))}
             for e in session.events if e["kind"] == "trial"]

    # реакция на ошибку: напряжение в четыре секунды после неверного ответа
    # против такого же окна после верного
    def stress_after(moment):
        values = [S["stress"][i] for i, t in enumerate(times)
                  if raw[i] and moment + 0.3 <= t <= moment + 4.3
                  and S["stress"][i] is not None]
        return float(np.mean(values)) if values else None

    after_error = [v for v in (stress_after(k["t"]) for k in ticks if not k["ok"])
                   if v is not None]
    after_ok = [v for v in (stress_after(k["t"]) for k in ticks if k["ok"])
                if v is not None]
    error_reaction = None
    if len(after_error) >= 2 and len(after_ok) >= 5:
        delta = float(np.mean(after_error) - np.mean(after_ok))
        error_reaction = {"delta": round(delta, 1),
                          "errors": len(after_error),
                          "after_error": round(float(np.mean(after_error))),
                          "after_ok": round(float(np.mean(after_ok)))}

    # скорость включения: секунды от старта блока до включённости выше покоя
    def time_to_engage(block):
        for i in task_i:
            if block["start"] <= times[i] <= block["end"]:
                value = S["engage"][i]
                if value is not None and value >= 55:
                    return round(times[i] - block["start"], 1)
        return None
    warmups = [w for w in (time_to_engage(b) for b in blocks_ph) if w is not None]
    warmup = {"mean_s": round(float(np.mean(warmups)), 1),
              "per_block": warmups} if warmups else None

    def task_mean(key):
        vals = [S[key][i] for i in task_i if S[key][i] is not None]
        return round(float(np.mean(vals))) if vals else 50

    return {"times": [round(t, 1) for t in times], "series": S, "phases": phases,
            "peak": peak, "hold_pct": round(hold), "flow_pct": round(flow),
            "fatigue": fatigue, "workability": workability, "recovery": recovery,
            "ticks": ticks, "error_reaction": error_reaction, "warmup": warmup,
            "duration_s": round(times[-1] + 1, 1) if times else 0,
            "means": {k: task_mean(k) for k in ("engage", "stress", "calm", "load")}}
