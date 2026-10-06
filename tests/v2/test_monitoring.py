import numpy as np

from app.eeg.monitoring import monitoring

FS = 250


def build(noisy_module: str | None = None, minutes: float = 3.0, tired: bool = False, seed: int = 0):
    """Три модуля подряд без фона; noisy_module — с движениями, tired — альфа гаснет, тета растёт."""
    rng = np.random.default_rng(seed)
    names = ["interests", "cards", "spatial"]
    n = int(minutes * 60 * FS)
    t = np.arange(n) / FS
    signal = rng.normal(0, 8, (4, n))
    fade = np.linspace(1.0, 0.3, n) if tired else np.ones(n)
    signal[2:] += 15 * fade * np.sin(2 * np.pi * 10 * t)
    signal[2:] += 15 * (1.3 - fade) * np.sin(2 * np.pi * 5.5 * t) if tired else 0
    events, step = [], n // len(names)
    for i, name in enumerate(names):
        a, b = i * step, (i + 1) * step
        if name == noisy_module:
            signal[:, a:b] += rng.normal(0, 400, (4, b - a))
        events += [{"kind": "module_start", "sample": a, "payload": {"module": name}},
                   {"kind": "module_end", "sample": b, "payload": {"module": name}}]
    events.append({"kind": "session_end", "sample": n, "payload": {}})
    return signal, events


def test_quality_per_module_and_no_background_needed():
    signal, events = build()
    m = monitoring(signal, FS, events)
    assert set(m["modules"]) == {"interests", "cards", "spatial"}
    assert all(v["quality"] >= 0.6 for v in m["modules"].values())
    assert m["state"]["movement"] is False


def test_noisy_module_flags_movement():
    signal, events = build(noisy_module="cards")
    m = monitoring(signal, FS, events)
    assert m["modules"]["cards"]["quality"] < 0.6
    assert m["state"]["movement"] is True


def test_fatigue_signs_when_alpha_fades():
    signal, events = build(tired=True, minutes=6)
    m = monitoring(signal, FS, events)
    assert m["state"]["theta_alpha_change"] > 0.3 and m["state"]["fatigue_signs"]


def test_empty_recording():
    m = monitoring(np.zeros((4, 1000)), FS, [])
    assert m == {"modules": {}, "state": {"movement": False, "theta_alpha_change": None, "fatigue_signs": False}}
