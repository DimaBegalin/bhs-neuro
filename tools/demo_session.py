"""Демонстрационный прогон: ведём сессию, собираем сырьё, ставим метки.

Инструкции проговариваются голосом, потому что часть фаз идёт с закрытыми
глазами. На выходе файл сессии, как после настоящего визита.
"""
import subprocess
import time
import urllib.request
import json

BRIDGE = "http://127.0.0.1:8765"
SESSION = "demo-" + time.strftime("%H%M%S")

PHASES = [
    ("calibration_eyes_closed", 45,
     "Закройте глаза и сидите спокойно.", {}),
    ("calibration_eyes_open", 20,
     "Откройте глаза и смотрите в одну точку.", {}),
    ("numeric", 40,
     "Считайте про себя. От трёхсот отнимайте по семь. Быстро.",
     {"domain": "numeric"}),
    ("spatial", 40,
     "Представьте свою квартиру. Мысленно пройдите по ней и поверните каждую "
     "комнату на девяносто градусов.", {"domain": "spatial"}),
    ("verbal", 40,
     "Придумывайте слова на букву эс. Как можно больше, про себя.",
     {"domain": "verbal"}),
    ("working_memory", 40,
     "Запомните числа: семь, два, девять, четыре, один. Повторяйте их в обратном "
     "порядке, снова и снова.", {"domain": "working_memory"}),
]


def say(text: str) -> None:
    subprocess.run(["say", "-v", "Milena", text], check=False)


def post(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode()
    request = urllib.request.Request(BRIDGE + path, data=data,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def status() -> dict:
    with urllib.request.urlopen(BRIDGE + "/status", timeout=5) as response:
        return json.load(response)


print(f"сессия {SESSION}", flush=True)
post("/session/start", {"session_id": SESSION, "out_dir": "data"})
post("/event", {"kind": "session_start", "payload": {"session_id": SESSION,
                                                     "lang": "ru"}})
say("Начинаем демонстрацию. Наденьте ободок и сядьте удобно.")
time.sleep(2)

for kind, seconds, instruction, payload in PHASES:
    is_block = "domain" in payload
    start_kind = "block_start" if is_block else f"{kind}_start"
    end_kind = "block_end" if is_block else f"{kind}_end"

    say(instruction)
    post("/event", {"kind": start_kind, "payload": payload})
    before = status()["packets"]
    time.sleep(seconds)
    post("/event", {"kind": end_kind, "payload": payload})
    after = status()["packets"]
    print(f"  {kind:>24}: {seconds} секунд, пакетов {after - before}", flush=True)

    if is_block and kind != PHASES[-1][0]:
        post("/event", {"kind": "rest_start", "payload": {}})
        say("Пауза. Просто расслабьтесь.")
        time.sleep(10)
        post("/event", {"kind": "rest_end", "payload": {}})

post("/event", {"kind": "session_end", "payload": {}})
say("Готово. Спасибо.")
result = post("/session/stop")
print(f"\nзапись: {result['npz']}", flush=True)
print(f"события: {result['events']}", flush=True)
if result.get("profile"):
    print(f"профиль: {result['profile']}", flush=True)
if result.get("profile_error"):
    print(f"профиль не посчитался: {result['profile_error']}", flush=True)
print(f"\nидентификатор сессии: {SESSION}")
