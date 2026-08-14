"""Калибровка нашей шкалы по штатному приложению.

Алгоритм у приложения закрытый, поэтому мы не угадываем формулу, а подгоняем
преобразование по парам «наш сырой индекс, их процент», снятым одновременно.
Числа с экрана приложения читаются распознаванием.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import urllib.request

BRIDGE = "http://127.0.0.1:8765/raw"
SHOTS = Path("/private/tmp/claude-501/-Users-edygetusupbekov-Obsidian/"
             "e5a0a754-eec5-472f-9255-4c8d2b1a053b/scratchpad")
SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 180
STEP_S = 2.0
# порядок чисел на экране приложения слева направо
APP_ORDER = ("load", "focus", "relax")


def window_bounds() -> tuple[int, int, int, int]:
    script = ('tell application "System Events" to tell process "Mind Tracker BCI" '
              'to get {position, size} of window 1')
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    numbers = [int(n) for n in re.findall(r"-?\d+", out.stdout)]
    if len(numbers) < 4:
        raise RuntimeError("окно приложения не найдено")
    return tuple(numbers[:4])


def read_app_numbers() -> dict | None:
    x, y, w, h = window_bounds()
    shot = SHOTS / "calib_win.png"
    big = SHOTS / "calib_big.png"
    subprocess.run(["screencapture", "-x", f"-R{x},{y},{w},{h}", str(shot)], check=False)
    subprocess.run(["sips", "-Z", "1500", str(shot), "--out", str(big)],
                   capture_output=True)
    base = SHOTS / "calib_out"
    subprocess.run(["tesseract", str(big), str(base), "tsv", "--psm", "11",
                    "-c", "tessedit_char_whitelist=0123456789%"],
                   capture_output=True)
    rows = []
    for line in (base.with_suffix(".tsv")).read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12 or not parts[11].strip():
            continue
        text = re.sub(r"[^0-9]", "", parts[11])
        if not text:
            continue
        rows.append((int(parts[6]), int(parts[7]), int(text)))
    # три больших числа лежат на одной строке в нижней половине карточки
    by_row = {}
    for cx, cy, value in rows:
        if value > 100:
            continue
        by_row.setdefault(cy // 20, []).append((cx, value))
    for _, items in sorted(by_row.items()):
        if len(items) == 3:
            items.sort()
            return {name: value for name, (_, value) in zip(APP_ORDER, items)}
    return None


def read_our_raw() -> dict | None:
    try:
        with urllib.request.urlopen(BRIDGE, timeout=3) as response:
            payload = json.load(response)
    except Exception:
        return None
    return payload.get("raw") if payload.get("ok") else None


def main() -> None:
    print(f"собираю пары {SECONDS} секунд. Меняйте состояние: посидите спокойно, "
          f"потом посчитайте в уме, потом снова расслабьтесь", flush=True)
    pairs = []
    end = time.time() + SECONDS
    while time.time() < end:
        app = read_app_numbers()
        ours = read_our_raw()
        if app and ours:
            pairs.append({"app": app, "raw": ours})
            print(f"  пара {len(pairs):>3}: приложение {app}, "
                  f"наши {({k: round(v, 3) for k, v in ours.items()})}", flush=True)
        time.sleep(STEP_S)

    if len(pairs) < 10:
        print("пар мало, калибровка не выйдет")
        return

    out = SHOTS / "calibration_pairs.json"
    out.write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nсобрано пар: {len(pairs)}, сохранено в {out}")

    print("\n=== подгонка ===")
    coefficients = {}
    for key in APP_ORDER:
        x = np.log(np.array([max(p["raw"][key], 1e-9) for p in pairs]))
        y = np.array([p["app"][key] for p in pairs], dtype=float)
        if x.std() < 1e-6:
            print(f"  {key}: наш индекс не менялся, подгонка невозможна")
            continue
        slope, intercept = np.polyfit(x, y, 1)
        predicted = slope * x + intercept
        error = float(np.mean(np.abs(predicted - y)))
        correlation = float(np.corrcoef(x, y)[0, 1])
        coefficients[key] = {"slope": float(slope), "intercept": float(intercept)}
        print(f"  {key:>6}: связь {correlation:+.2f}, средняя ошибка {error:.1f} "
              f"процента, формула {slope:.2f}*ln(индекс) {intercept:+.1f}")

    (SHOTS / "calibration.json").write_text(
        json.dumps(coefficients, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nкоэффициенты сохранены")


main()
