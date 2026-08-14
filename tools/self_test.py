"""Автоматическое прохождение теста: ведём сессию и отвечаем за ребёнка.

Нужно, чтобы прогнать всю цепочку на реальных данных прибора, не занимая
человека на восемь минут. Сигнал при этом настоящий, ответы условные.
"""
import json
import random
import subprocess
import sys
import time
import urllib.request

BRIDGE = "http://127.0.0.1:8765"
FAST = "--fast" in sys.argv
CALIB_CLOSED = 30 if FAST else 45
CALIB_OPEN = 15 if FAST else 20
BLOCK_S = 30 if FAST else 45
REST_S = 8
DOMAINS = ("numeric", "spatial", "verbal", "working_memory")
# условная точность по доменам: пространственный сильный, вербальный слабый
ACCURACY = {"numeric": 0.72, "spatial": 0.93, "verbal": 0.55, "working_memory": 0.78}
INSTRUCTIONS = {
    "numeric": "Считайте про себя, от трёхсот отнимайте по семь.",
    "spatial": "Представляйте, как поворачиваются фигуры.",
    "verbal": "Придумывайте слова на букву эс.",
    "working_memory": "Запомните: семь, два, девять, четыре. Повторяйте наоборот.",
}


def say(text: str) -> None:
    subprocess.run(["say", "-v", "Milena", text], check=False)


def post(path: str, payload: dict | None = None) -> dict:
    if path == "/event":
        payload = dict(payload or {})
        payload["session_id"] = session_id
    data = json.dumps(payload or {}).encode()
    request = urllib.request.Request(BRIDGE + path, data=data,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


session_id = "self-" + time.strftime("%H%M%S")

print(f"сессия {session_id}, режим {'быстрый' if FAST else 'полный'}", flush=True)
post("/session/start", {"session_id": session_id, "out_dir": "data", "force": True})
post("/event", {"kind": "session_start", "payload": {"session_id": session_id,
                                                     "lang": "ru"}})

say("Начинаем. Закройте глаза и сидите спокойно.")
post("/event", {"kind": "calibration_eyes_closed_start", "payload": {}})
time.sleep(CALIB_CLOSED)
post("/event", {"kind": "calibration_eyes_closed_end", "payload": {}})
print(f"  калибровка, глаза закрыты: {CALIB_CLOSED} секунд", flush=True)

say("Откройте глаза и смотрите в одну точку.")
post("/event", {"kind": "calibration_eyes_open_start", "payload": {}})
time.sleep(CALIB_OPEN)
post("/event", {"kind": "calibration_eyes_open_end", "payload": {}})
print(f"  калибровка, глаза открыты: {CALIB_OPEN} секунд", flush=True)

rng = random.Random(7)
order = list(DOMAINS)
rng.shuffle(order)

for index, domain in enumerate(order):
    say(INSTRUCTIONS[domain])
    post("/event", {"kind": "block_start", "payload": {"domain": domain}})
    started = time.time()
    trial = 0
    while time.time() - started < BLOCK_S:
        # ответы условные, но с правдоподобным разбросом времени
        rt = int(rng.gauss(1200 if domain != "spatial" else 950, 220))
        rt = max(350, rt)
        correct = rng.random() < ACCURACY[domain]
        post("/event", {"kind": "trial", "payload": {
            "domain": domain, "index": trial, "stimulus_id": f"{domain}-{trial}",
            "correct": correct, "rt_ms": rt}})
        trial += 1
        time.sleep(min(rt / 1000.0, BLOCK_S - (time.time() - started)))
    post("/event", {"kind": "block_end", "payload": {"domain": domain}})
    print(f"  блок {domain:>15}: {BLOCK_S} секунд, заданий {trial}", flush=True)

    if index < len(order) - 1:
        post("/event", {"kind": "rest_start", "payload": {}})
        say("Пауза, расслабьтесь.")
        time.sleep(REST_S)
        post("/event", {"kind": "rest_end", "payload": {}})

post("/event", {"kind": "session_end", "payload": {}})
say("Готово, спасибо.")
result = post("/session/stop")
print(f"\nзапись:   {result['npz']}", flush=True)
print(f"профиль:  {result.get('profile') or 'не посчитался'}", flush=True)
if result.get("profile_error"):
    print(f"причина:  {result['profile_error']}", flush=True)
print(f"\nсессия: {session_id}")
