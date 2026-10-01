# -*- coding: utf-8 -*-
"""Сквозной прогон окна: имитатор, укороченные модули, клики через JS.

Проходит путь менеджера и ученика целиком и снимает экран на каждом шаге
(macOS: screencapture). Запуск: .venv/bin/python tools/v2/e2e_window.py ПАПКА
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import webview  # noqa: E402

from app.api import Api  # noqa: E402
from app.device.link import DeviceLink  # noqa: E402
from app.device.sim import SimDevice  # noqa: E402
from app.main import UI_INDEX  # noqa: E402
from app.session.session import SessionStore  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
sim = SimDevice(speed=1.0)
api = Api(DeviceLink(lambda: sim), SessionStore(out / "sessions"), manager="e2e",
          dev_controls={"on:background_closed_start": lambda _p: setattr(sim, "eyes_closed", True),
                        "on:background_closed_end": lambda _p: setattr(sim, "eyes_closed", False)},
          fast=True)
window = webview.create_window("Профориентация BHS", url=str(UI_INDEX), js_api=api,
                               width=1240, height=820)
log: list[str] = []


def js(code: str):
    return window.evaluate_js(code)


def click(text: str) -> None:
    found = js(f"""(() => {{ const b = [...document.querySelectorAll('button')]
        .find(x => x.textContent.trim() === {json.dumps(text)} && !x.disabled);
        if (b) {{ b.click(); return true; }} return false; }})()""")
    log.append(f"click {text!r}: {found}")
    if not found:
        raise RuntimeError(f"кнопка не найдена или недоступна: {text}")


def shot(name: str) -> None:
    time.sleep(0.6)
    subprocess.run(["screencapture", "-x", str(out / f"{name}.png")], check=False)
    log.append(f"shot {name}: " + js("document.querySelector('main').innerText.replace(/\\n+/g,' | ').slice(0,160)"))


def scenario() -> None:
    try:
        time.sleep(3)
        shot("1-home")
        click("Новый ученик")
        js("document.querySelector('input').value = 'Айгерим Нурланова'")
        click("9")
        click("Қазақша")
        chosen = js("[...document.querySelectorAll('.seg button[aria-pressed=true]')].map(b => b.textContent).join(',')")
        log.append(f"выбрано: {chosen}")
        if chosen != "9,Қазақша,С ободком":
            raise RuntimeError(f"переключатели не держат выбор: {chosen}")
        click("Далее")
        time.sleep(0.5)
        click("Подключить")
        time.sleep(3)
        shot("2-device")
        click("Ободок готов, дальше")
        shot("3-consent")
        click("Түсінікті, бастаймыз")
        time.sleep(1)
        shot("4-background-intro")
        click("Бастау")
        time.sleep(1.5)
        shot("5-eyes-closed")
        time.sleep(3)
        shot("6-cross")
        time.sleep(3)
        shot("7-student-done")
        click("Для менеджера: открыть итог")
        shot("8-summary")
        click("К списку сессий")
        shot("9-home-after")
        log.append("OK")
    except Exception as error:
        log.append(f"FAIL {error}")
    finally:
        (out / "e2e.log").write_text("\n".join(log), encoding="utf-8")
        window.destroy()


webview.start(scenario, http_server=True)
print("\n".join(log))
