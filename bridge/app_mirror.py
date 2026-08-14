"""Зеркало показаний штатного приложения.

Читает три числа с его экрана и отдаёт их как есть. Нужно, чтобы наш монитор
показывал ровно то же, что видит человек в приложении.

Ограничение осознанное: работает, только пока приложение открыто на вкладке
мониторинга. Свернули окно, сменили экран, и зеркало гаснет. Свои метрики
при этом продолжают считаться независимо, они идут в профиль.
"""
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

APP = "Mind Tracker BCI"
ORDER = ("load", "focus", "relax")   # порядок чисел на экране слева направо
PERIOD_S = 0.7
TMP = Path(tempfile.gettempdir()) / "bhs_mirror"
TMP.mkdir(exist_ok=True)


def window_id() -> int | None:
    """Идентификатор окна приложения.

    Снимаем окно по идентификатору, а не область экрана: иначе поверх него
    оказывается браузер и в кадр попадает не то.
    """
    from Quartz import (CGWindowListCopyWindowInfo, kCGWindowListOptionAll,
                        kCGNullWindowID)
    for window in CGWindowListCopyWindowInfo(kCGWindowListOptionAll, kCGNullWindowID):
        if window.get("kCGWindowOwnerName") == APP and window.get("kCGWindowNumber"):
            bounds = window.get("kCGWindowBounds") or {}
            if bounds.get("Height", 0) > 300:      # пропускаем служебные окна
                return int(window["kCGWindowNumber"])
    return None


def _numbers_from_tsv(path: Path) -> list[tuple[int, int, int]]:
    found = []
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        digits = re.sub(r"[^0-9]", "", parts[11])
        if not digits:
            continue
        value = int(digits)
        if 0 <= value <= 100:
            found.append((int(parts[6]), int(parts[7]), value))
    return found


def window_bounds() -> tuple[int, int, int, int] | None:
    """Положение окна приложения на экране.

    Снимок делаем по области, а не по идентификатору окна: захват чужого окна
    требует разрешения на запись экрана, которого у процесса нет. Значит окно
    приложения должно быть видно, его надо держать рядом с окном теста.
    """
    from Quartz import (CGWindowListCopyWindowInfo, kCGWindowListOptionAll,
                        kCGNullWindowID)
    for window in CGWindowListCopyWindowInfo(kCGWindowListOptionAll, kCGNullWindowID):
        if window.get("kCGWindowOwnerName") != APP:
            continue
        bounds = window.get("kCGWindowBounds") or {}
        if bounds.get("Height", 0) > 300:      # пропускаем служебные окна
            return (int(bounds["X"]), int(bounds["Y"]),
                    int(bounds["Width"]), int(bounds["Height"]))
    return None


def read_numbers() -> dict | None:
    bounds = window_bounds()
    if bounds is None:
        return None
    x, y, w, h = bounds
    shot, big, base = TMP / "w.png", TMP / "b.png", TMP / "o"
    subprocess.run(["screencapture", "-x", f"-R{x},{y},{w},{h}", str(shot)], check=False)
    subprocess.run(["sips", "-Z", "1500", str(shot), "--out", str(big)],
                   capture_output=True)
    subprocess.run(["tesseract", str(big), str(base), "tsv", "--psm", "11",
                    "-c", "tessedit_char_whitelist=0123456789%"], capture_output=True)
    rows = _numbers_from_tsv(base.with_suffix(".tsv"))
    by_row: dict[int, list[tuple[int, int]]] = {}
    for cx, cy, value in rows:
        by_row.setdefault(cy // 25, []).append((cx, value))
    for _, items in sorted(by_row.items()):
        if len(items) == 3:
            items.sort()
            return {name: value for name, (_, value) in zip(ORDER, items)}
    return None


class AppMirror:
    """Фоновое зеркало: держит последние числа приложения и всю их дорожку.

    Дорожка с метками времени это и есть материал для разбора: её режут
    по блокам теста и получают состояние ребёнка на каждом типе задач.
    """

    def __init__(self, clock=None) -> None:
        self.values: dict | None = None
        self.updated_at = 0.0
        self.track: list[dict] = []
        self._clock = clock
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                numbers = read_numbers()
                if numbers:
                    self.values = numbers
                    self.updated_at = time.time()
                    moment = (self._clock.now_s() if self._clock is not None
                              else time.time())
                    self.track.append({"t_s": round(moment, 2), **numbers})
            except Exception:
                pass
            time.sleep(PERIOD_S)

    def snapshot(self) -> dict:
        fresh = self.values is not None and (time.time() - self.updated_at) < 4.0
        return {"mirror": self.values if fresh else None,
                "mirror_fresh": fresh, "mirror_points": len(self.track)}

    def reset_track(self) -> None:
        self.track = []

    def stop(self) -> None:
        self._stop.set()
