"""Сводка пилота: качество сигнала и сходимость нейро-слоя с поведенческим.

Объём пилота 10-15 сессий, статистическая значимость на нём недостижима,
поэтому решение принимается по направлению связи и по разбросу.
P-значения на пилоте не считаются и в отчёты не выносятся.
"""
import argparse
import glob
import json

import numpy as np

MIN_QUALITY_SHARE = 0.70
DIRECTION_THRESHOLD = -0.3
DIRECTION_SHARE = 0.7


def convergence(profiles: list[dict]) -> dict:
    with_eeg = [p for p in profiles if p.get("has_eeg")]
    correlations = []
    for profile in with_eeg:
        accuracy = np.array([c["accuracy"] for c in profile["domains"]], dtype=float)
        cost = np.array([c["cost"] for c in profile["domains"]], dtype=float)
        if accuracy.std() == 0 or cost.std() == 0:
            continue
        correlations.append(float(np.corrcoef(cost, accuracy)[0, 1]))

    mean_r = float(np.mean(correlations)) if correlations else 0.0
    negative_share = (float(np.mean([r < 0 for r in correlations]))
                      if correlations else 0.0)
    quality_share = len(with_eeg) / len(profiles) if profiles else 0.0

    keep = (mean_r < DIRECTION_THRESHOLD and negative_share >= DIRECTION_SHARE
            and quality_share >= MIN_QUALITY_SHARE)
    return {
        "n_sessions": len(profiles),
        "n_with_eeg": len(with_eeg),
        "quality_share": round(quality_share, 3),
        "mean_within_child_correlation": round(mean_r, 3),
        "share_negative_direction": round(negative_share, 3),
        "verdict": "оставить нейро-слой" if keep else "отключить нейро-слой",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("profiles_glob", help="например data/*.profile.json")
    args = parser.parse_args()
    loaded = [json.load(open(p, encoding="utf-8"))
              for p in sorted(glob.glob(args.profiles_glob))]
    print(json.dumps(convergence(loaded), ensure_ascii=False, indent=2))
