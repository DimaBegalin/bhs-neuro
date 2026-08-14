"""Поведенческие метрики блока: что ребёнок сделал руками."""
import numpy as np

FAST_GUESS_MS = 400
STALL_MEDIAN_FACTOR = 3.0


def block_behavior(trials: list[dict]) -> dict:
    if not trials:
        return {"accuracy": 0.0, "median_rt_ms": 0.0, "rt_sd_ms": 0.0,
                "fast_guess_share": 0.0, "stall_share": 0.0, "n_trials": 0}
    rts = np.array([t["rt_ms"] for t in trials], dtype=float)
    correct = np.array([bool(t["correct"]) for t in trials])
    median = float(np.median(rts))
    return {
        "accuracy": float(correct.mean()),
        "median_rt_ms": median,
        "rt_sd_ms": float(rts.std(ddof=0)),
        "fast_guess_share": float((rts < FAST_GUESS_MS).mean()),
        "stall_share": float((rts > median * STALL_MEDIAN_FACTOR).mean()),
        "n_trials": int(len(trials)),
    }
