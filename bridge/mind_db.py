# -*- coding: utf-8 -*-
"""Чтение показаний прямо из базы штатного приложения Mind Tracker BCI.

Приложение (Flutter, ObjectBox поверх LMDB) складывает свои оценки состояния
в data.mdb внутри своего песочного контейнера. Записи типа PHYSIOLOGICAL_STATE
это готовый JSON с шестью долями, они в сумме дают единицу:
relaxation, fatigue, concentration, involvement, stress и none (остаток).

Почему так, а не распознаванием цифр с экрана: числа приходят точными,
приложению не нужно быть видимым, разрешение на запись экрана не требуется,
и берутся все поля, а не три, что помещаются в окно.

Ограничение честное: приложение пишет запись примерно раз в полторы минуты,
поэтому для блока теста в сорок пять секунд это ноль или одна точка. Быстрая
дорожка для живого монитора идёт отдельно, зеркалом окна.
"""
import json
import os
import re
import threading
import time
from datetime import datetime, timezone

# где приложение держит базу на разных системах. Это папка документов
# приложения по меркам Flutter: на macOS внутри песочного контейнера,
# на Windows обычные Документы пользователя. Путь для Windows не проверен
# на живой машине: если файла там нет, слой просто не включается
DB_CANDIDATES = (
    os.path.expanduser("~/Library/Containers/com.brainbit.MindTracker/Data/Documents/"
                       "mind_tracker_local_db/data.mdb"),
    os.path.expanduser("~/Documents/mind_tracker_local_db/data.mdb"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "com.brainbit", "mind_tracker",
                 "mind_tracker_local_db", "data.mdb"),
)


def find_db() -> str | None:
    """Первый существующий путь к базе приложения, иначе None."""
    for path in DB_CANDIDATES:
        if path and os.path.exists(path):
            return path
    return None


DB_PATH = find_db() or DB_CANDIDATES[0]
PERIOD_S = 5.0
# доли состояния, как их пишет приложение
FIELDS = ("relaxation", "fatigue", "concentration", "involvement", "stress", "none")
# запись лежит в странице LMDB как обычный JSON, следом идёт метка времени
STATE_RE = re.compile(rb'\{"relaxation":[^{}]*\}')
STAMP_RE = re.compile(rb'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')


def read_states(path: str = DB_PATH) -> list[dict]:
    """Все состояния из базы, по возрастанию времени, без повторов.

    Файл читаем целиком и байтами: LMDB держит несколько версий страницы,
    поэтому одна и та же запись встречается по нескольку раз, и разбор
    идёт через отсев по метке времени, а не через попытку понять формат.
    """
    if not os.path.exists(path):
        return []
    with open(path, "rb") as fh:
        blob = fh.read()

    found: dict[str, dict] = {}
    for match in STATE_RE.finditer(blob):
        try:
            values = json.loads(match.group().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        # метка времени пишется следом за телом записи, в пределах сотни байт
        tail = blob[match.end():match.end() + 120]
        stamp = STAMP_RE.search(tail)
        if stamp is None:
            continue
        moment = stamp.group().decode()
        row = {"at": moment, "at_local": _to_local(moment)}
        for field in FIELDS:
            value = values.get(field)
            row[field] = round(float(value) * 100, 1) if value is not None else None
        found[moment] = row
    return [found[key] for key in sorted(found)]


def _to_local(stamp: str) -> str:
    """Приложение пишет время по Гринвичу, показываем в часах ноутбука."""
    try:
        moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return stamp
    return moment.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


class MindDbMirror:
    """Фоновое чтение базы приложения: последнее состояние и вся дорожка.

    Тот же контракт, что у зеркала окна: snapshot и reset_track. Мост может
    держать оба источника сразу, они друг другу не мешают.
    """

    def __init__(self, clock=None, path: str = DB_PATH) -> None:
        self.path = path
        self.values: dict | None = None
        self.updated_at = 0.0
        self.track: list[dict] = []
        self._clock = clock
        self._seen: set[str] = set()
        self._session_start = time.time()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                for state in read_states(self.path):
                    if state["at"] in self._seen:
                        continue
                    self._seen.add(state["at"])
                    self.values = state
                    self.updated_at = time.time()
                    moment = (self._clock.now_s() if self._clock is not None
                              else time.time())
                    self.track.append({"t_s": round(moment, 2), **state})
            except Exception:
                pass
            self._stop.wait(PERIOD_S)

    def snapshot(self) -> dict:
        # приложение пишет раз в полторы минуты, поэтому свежим считаем
        # всё, что моложе четырёх минут
        fresh = self.values is not None and (time.time() - self.updated_at) < 240.0
        return {"app_state": self.values if fresh else None,
                "app_state_fresh": fresh,
                "app_state_points": len(self.track)}

    def reset_track(self) -> None:
        self.track = []
        self._seen = {s["at"] for s in read_states(self.path)}

    def stop(self) -> None:
        self._stop.set()


if __name__ == "__main__":
    states = read_states()
    print(f"база: {DB_PATH}")
    print(f"записей: {len(states)}\n")
    for state in states:
        print(state["at_local"], " ".join(
            f"{name}={state[name]}" for name in FIELDS if state.get(name) is not None))
