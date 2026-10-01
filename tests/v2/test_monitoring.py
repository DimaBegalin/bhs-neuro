import numpy as np

from app.eeg.monitoring import monitoring

FS = 250
TYPES = ["R", "I", "A", "S", "E", "C"]


def build(reactive: bool = True, seed: int = 0):
    """Фон 30+30 с, затем 12 карточек по 10 с: у карточек типа A альфа подавлена сильнее."""
    rng = np.random.default_rng(seed)
    parts, events, cursor = [], [], 0

    def add(seconds, alpha_uv, kind=None, payload=None, end_kind=None):
        nonlocal cursor
        n = int(seconds * FS)
        t = (cursor + np.arange(n)) / FS
        chunk = rng.normal(0, 10, (4, n))
        chunk[2:] += alpha_uv * np.sin(2 * np.pi * 10 * t)
        if kind:
            events.append({"kind": kind, "sample": cursor, "payload": payload or {}})
        parts.append(chunk)
        cursor += n
        if end_kind:
            events.append({"kind": end_kind, "sample": cursor, "payload": payload or {}})

    add(30, 30 if reactive else 15, "background_closed_start", end_kind="background_closed_end")
    add(30, 15, "background_open_start", end_kind="background_open_end")
    events.append({"kind": "module_start", "sample": cursor, "payload": {"module": "cards"}})
    card_types = {}
    for i, kind in enumerate(TYPES * 2):
        card = f"{kind}{i // 6 + 1}"
        card_types[card] = kind
        add(10, 4 if kind == "A" else 12, "card_show", {"card": card})
    events.append({"kind": "module_end", "sample": cursor, "payload": {"module": "cards"}})
    events.append({"kind": "session_end", "sample": cursor, "payload": {}})
    return np.concatenate(parts, axis=1), events, card_types


def test_card_attention_ranks_the_suppressed_type_first():
    signal, events, card_types = build()
    m = monitoring(signal, FS, events, card_types)
    assert m["background"]["reactive"]
    assert m["cards"]["shown"] and m["cards"]["valid"] == 12
    assert m["cards"]["type_order"][0] == "A"
    assert m["modules"]["cards"]["quality"] > 0.9
    assert not m["state"]["movement"]


def test_card_attention_hidden_without_alpha_reactivity():
    signal, events, card_types = build(reactive=False)
    m = monitoring(signal, FS, events, card_types)
    assert not m["background"]["reactive"]
    assert m["cards"]["shown"] is False and "не реагирует" in m["cards"]["reason"]


def test_missing_background_is_reported():
    m = monitoring(np.zeros((4, 1000)), FS, [], {})
    assert m["background"] == {"ok": False, "reason": "нет фона"}
