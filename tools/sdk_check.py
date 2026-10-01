# -*- coding: utf-8 -*-
"""Проверка ободка через официальный SDK на Windows (этап 0 версии 2.0).

Подключается к ободку без Mind Tracker, меряет сопротивление электродов,
пишет 30 с с закрытыми и 30 с с открытыми глазами и сверяет сигнал с
эталоном записей на Mac. Результат: папка на рабочем столе с отчётом,
сырым сигналом и логом. Эту папку целиком присылают разработке.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eeg.signal_check import CHANNELS, check_recording, judge  # noqa: E402

PHASE_S = 33.0
SKIP_S = 3.0  # первые секунды после команды: человек ещё закрывает глаза

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _output_dir(base: Path | None) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    if base is None:
        desktop = Path.home() / "Desktop"
        base = desktop if desktop.exists() else Path.cwd()
    target = base / f"BHS-проверка-ободка_{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    return target


class Log:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines: list[str] = []

    def __call__(self, text: str = "") -> None:
        print(text, flush=True)
        self.lines.append(text)
        self.path.write_text("\n".join(self.lines), encoding="utf-8")


def _countdown(log: Log, seconds: float, label: str) -> None:
    end = time.monotonic() + seconds
    while (left := end - time.monotonic()) > 0:
        print(f"\r   {label}: осталось {left:4.0f} с ", end="", flush=True)
        time.sleep(0.5)
    print("\a")
    log(f"   {label}: готово")


def _resistance_raw(device, seconds: float = 5.0) -> dict:
    """Сопротивление в омах как отдаёт SDK, без перевода в качество 0–1."""
    readings: list = []
    from neurosdk.cmn_types import SensorCommand
    device._subscribe("resist", lambda _s, data: readings.append(data))
    device._command(SensorCommand.StartResist)
    time.sleep(seconds)
    device._command(SensorCommand.StopResist)
    device._sensor.unset_resist_callbacks()
    if not readings:
        return {}
    last = readings[-1]
    last = last[-1] if isinstance(last, list) else last
    return {name: float(getattr(last, name, float("nan"))) for name in CHANNELS}


def _record(device, log: Log, phase_s: float) -> tuple[np.ndarray, list[float], list[int], dict]:
    chunks: list[np.ndarray] = []
    arrivals: list[float] = []
    sizes: list[int] = []
    marks: dict[str, int] = {}

    def on_chunk(chunk: np.ndarray) -> None:
        chunks.append(chunk)
        arrivals.append(time.monotonic())
        sizes.append(chunk.shape[1])

    def samples() -> int:
        return int(sum(sizes))

    device.start(on_chunk)
    time.sleep(2.0)
    if not chunks:
        raise RuntimeError("поток не пошёл: за 2 с не пришло ни одного пакета")
    log("2. Закройте глаза и сидите спокойно. По сигналу откройте.")
    marks["closed_start"] = samples()
    _countdown(log, phase_s, "глаза закрыты")
    marks["closed_end"] = samples()
    log("3. Откройте глаза и смотрите в одну точку на экране.")
    marks["open_start"] = samples()
    _countdown(log, phase_s, "глаза открыты")
    marks["open_end"] = samples()
    device.stop()
    return np.concatenate(chunks, axis=1), arrivals, sizes, marks


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка ободка BHS через SDK")
    parser.add_argument("--fake", action="store_true",
                        help="имитатор вместо ободка: пробный прогон без прибора")
    parser.add_argument("--phase", type=float, default=PHASE_S,
                        help="длительность каждого отрезка, с")
    parser.add_argument("--no-wait", action="store_true",
                        help="не ждать Enter (для автоматического прогона)")
    parser.add_argument("--out", type=Path, default=None,
                        help="куда положить папку с результатом (по умолчанию рабочий стол)")
    args = parser.parse_args(argv)
    if args.phase < 6:
        parser.error("отрезок короче 6 с: не набирается эпох для анализа")
    ask = (lambda _text: None) if args.no_wait else input
    out = _output_dir(args.out)
    log = Log(out / "лог.txt")
    log("Проверка ободка BHS · этап 0 версии 2.0")
    log(f"Windows: {platform.platform()} · Python {platform.python_version()}")
    log(f"Папка с результатом: {out}")
    log()
    log("Перед началом: закройте Mind Tracker, наденьте ободок, нажмите кнопку на нём.")
    ask("Когда индикатор ободка мигает, нажмите Enter… ")

    report: dict = {"started": datetime.now().isoformat(timespec="seconds")}
    device = None
    try:
        log("1. Ищу ободок (до 30 с)…")
        if args.fake:
            from bridge.fake_device import FakeDevice
            device = FakeDevice()
        else:
            from bridge.device import BrainBitDevice
            device = BrainBitDevice(scan_seconds=30.0)
        info = getattr(device, "info", None)
        report["device"] = {key: str(getattr(info, key, "")) for key in
                            ("Name", "SerialNumber", "Address", "SensFamily", "SensModel")}
        report["device"]["fs"] = device.fs
        report["device"]["battery"] = _safe(device.battery)
        log(f"   найден: {report['device']}")

        report["resistance_ohm"] = ({} if args.fake
                                    else _safe(lambda: _resistance_raw(device)))
        log(f"   сопротивление, Ом: {report['resistance_ohm']}")

        signal, arrivals, sizes, marks = _record(device, log, args.phase)
        fs = device.fs
        duration = arrivals[-1] - arrivals[0]
        effective_fs = (sum(sizes) - sizes[0]) / duration if duration > 0 else 0.0
        max_gap = float(np.diff(arrivals).max()) if len(arrivals) > 1 else 0.0
        skip = int(min(SKIP_S, args.phase / 4) * fs)
        closed = signal[:, marks["closed_start"] + skip:marks["closed_end"]]
        opened = signal[:, marks["open_start"] + skip:marks["open_end"]]
        np.savez_compressed(out / "запись.npz", signal=signal, fs=fs,
                            channels=np.array(CHANNELS), **{f"mark_{k}": v for k, v in marks.items()})

        result = check_recording(closed, opened, fs)
        verdicts = judge(result, fs, effective_fs, max_gap)
        report.update({"effective_fs": effective_fs, "max_gap_s": max_gap,
                       "packets": len(sizes), "packet_sizes": sorted(set(sizes)),
                       "result": result, "verdicts": verdicts})
        log()
        log("Итог:")
        for item in verdicts:
            mark = "ОК " if item["ok"] else "НЕТ"
            log(f"  [{mark}] {item['name']}: {item['text']}")
            if not item["ok"]:
                log(f"         → {item['fix']}")
        passed = all(item["ok"] for item in verdicts)
        log()
        log("Ободок работает через SDK, сигнал совпадает с эталоном."
            if passed else "Есть замечания, см. выше.")
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
        log()
        log(f"ОШИБКА: {report['error']}")
        passed = False
    finally:
        if device is not None:
            _safe(getattr(device, "close", device.stop))
        (out / "отчёт.json").write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                    default=str), encoding="utf-8")
    log()
    log(f"Пришлите разработке папку целиком: {out}")
    ask("Нажмите Enter, чтобы закрыть окно… ")
    return 0 if passed else 1


def _safe(fn):
    try:
        return fn()
    except Exception as error:
        return f"ошибка: {error}"


if __name__ == "__main__":
    raise SystemExit(run())
