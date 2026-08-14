"""Профиль по дорожке показаний прибора и меткам блоков теста.

Упрощённый путь: обработку сигнала делает штатное приложение, мы связываем
его показания с тем, что ребёнок в этот момент решал. Для разбора этого
достаточно: видно, какой тип задач чего ему стоил.
"""
import statistics

DOMAINS = ("numeric", "spatial", "verbal", "working_memory")
METRICS = ("focus", "load", "relax")
MIN_POINTS = 5


def _slice(track: list[dict], start_s: float, end_s: float) -> list[dict]:
    return [point for point in track if start_s <= point["t_s"] <= end_s]


def block_windows(events: list[dict]) -> dict[str, tuple[float, float]]:
    """Границы каждого блока по журналу событий."""
    windows: dict[str, tuple[float, float]] = {}
    starts: dict[str, float] = {}
    for event in events:
        domain = (event.get("payload") or {}).get("domain")
        if event["kind"] == "block_start" and domain:
            starts[domain] = event["t_s"]
        elif event["kind"] == "block_end" and domain and domain in starts:
            windows[domain] = (starts[domain], event["t_s"])
    return windows


def calibration_window(events: list[dict]) -> tuple[float, float] | None:
    start = next((e["t_s"] for e in events
                  if e["kind"] == "calibration_eyes_closed_start"), None)
    end = next((e["t_s"] for e in events
                if e["kind"] == "calibration_eyes_open_end"), None)
    return (start, end) if start is not None and end is not None else None


def build_mirror_profile(session_meta: dict, events: list[dict],
                         track: list[dict], behavior: dict) -> dict:
    """Сводит показания прибора и результаты задач по каждому домену."""
    windows = block_windows(events)
    rest = calibration_window(events)
    rest_values = {}
    if rest:
        points = _slice(track, *rest)
        if len(points) >= MIN_POINTS:
            rest_values = {m: statistics.mean(p[m] for p in points) for m in METRICS}

    cards = []
    for domain in DOMAINS:
        window = windows.get(domain)
        points = _slice(track, *window) if window else []
        card = {"domain": domain,
                "accuracy": float(behavior.get(domain, {}).get("accuracy", 0.0)),
                "median_rt_ms": float(behavior.get(domain, {}).get("median_rt_ms", 0.0)),
                "points": len(points)}
        for metric in METRICS:
            if len(points) >= MIN_POINTS:
                value = statistics.mean(p[metric] for p in points)
                card[metric] = round(value, 1)
                if rest_values:
                    card[f"{metric}_vs_rest"] = round(value - rest_values[metric], 1)
            else:
                card[metric] = None
        cards.append(card)

    measured = [c for c in cards if c["focus"] is not None]
    return {
        "session_id": session_meta["session_id"],
        "lang": session_meta.get("lang", "ru"),
        "source": "прибор через штатное приложение",
        "method_version": "mirror-1.0",
        "rest": {k: round(v, 1) for k, v in rest_values.items()} if rest_values else None,
        "has_device_data": len(measured) == len(DOMAINS),
        "domains": cards,
        "behavior": behavior,
    }
