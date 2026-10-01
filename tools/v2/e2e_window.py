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

import app.api as api_module  # noqa: E402

from app.api import Api  # noqa: E402
from app.device.link import DeviceLink  # noqa: E402
from app.device.sim import SimDevice  # noqa: E402
from app.main import UI_INDEX  # noqa: E402
from app.session.session import SessionStore  # noqa: E402

out = Path(sys.argv[1])
opened: list = []
api_module._open_path = lambda path: opened.append(str(path))  # не открывать PDF во время прогона
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


def has(selector: str) -> bool:
    return bool(js(f"!!document.querySelector({json.dumps(selector)})"))


def buttons() -> list[str]:
    return js("[...document.querySelectorAll('button')].filter(b => !b.disabled).map(b => b.textContent.trim())") or []


def drive_battery() -> None:
    """Проходит модули ученика до экрана «Готово», снимая по одному кадру каждого вида."""
    seen: set[str] = set()
    for _ in range(400):
        time.sleep(0.25)
        labels = buttons()
        if "Для менеджера: открыть итог" in labels:
            shot("7-student-done")
            return
        if has(".scale"):
            kind = "bigfive" if "про тебя" in (js("document.querySelector('main').innerText") or "") else "interests"
            if kind not in seen:
                seen.add(kind); shot(f"5-{kind}")
            js("document.querySelectorAll('.scale button')[3].click()")
        elif "Зеркальная" in labels:
            if "spatial" not in seen:
                seen.add("spatial"); shot("5-spatial")
            click("Зеркальная")
        elif "Интересно" in labels:
            if "card" not in seen:
                seen.add("card"); shot("5-card-rating")
            click("Интересно")
        elif has(".subjects"):
            shot("5-subjects")
            js("[...document.querySelectorAll('.subjects button')].slice(0, 2).forEach(b => b.click())")
            time.sleep(0.3)
            js("document.querySelectorAll('.subjects button')[1].click()")
            time.sleep(0.3)
            click("Готово")
        elif has(".card-show img") and "card-show" not in seen:
            seen.add("card-show"); shot("5-card-show")
        elif "Начать" in labels:
            click("Начать")
    raise RuntimeError("батарея не дошла до конца")


def scenario() -> None:
    try:
        time.sleep(3)
        shot("1-home")
        click("Новый ученик")
        js("document.querySelector('input').value = 'Айгерим Нурланова'")
        click("9")
        chosen = js("[...document.querySelectorAll('.seg button[aria-pressed=true]')].map(b => b.textContent).join(',')")
        log.append(f"выбрано: {chosen}")
        click("Далее")
        time.sleep(0.5)
        click("Подключить")
        time.sleep(3)
        shot("2-device")
        click("Ободок готов, дальше")
        shot("3-consent")
        click("Понятно, начинаем")
        time.sleep(1)
        click("Начать")  # фон
        time.sleep(7)
        drive_battery()
        click("Для менеджера: открыть итог")
        time.sleep(2)
        shot("8-summary")
        js("document.querySelector('textarea').value = 'Обсудили с родителями: пробуем кружок робототехники.'")
        click("Сформировать PDF для родителя")
        time.sleep(2)
        js("document.querySelector('textarea').scrollIntoView()")
        shot("9-comment")
        log.append(f"открыто: {opened}")
        log.append("OK")
    except Exception as error:
        log.append(f"FAIL {error}")
    finally:
        (out / "e2e.log").write_text("\n".join(log), encoding="utf-8")
        window.destroy()


webview.start(scenario, http_server=True)
print("\n".join(log))
import os
os._exit(0)
