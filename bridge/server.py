"""HTTP и WebSocket интерфейс моста. Слушает только 127.0.0.1."""
import asyncio
import glob
import json
import os
import sys
import threading
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import re

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from analyzer.iaf import compute_iaf, bands_from_iaf
from analyzer.behavior import block_behavior
from analyzer.main import analyze
from analyzer.mirror_profile import build_mirror_profile, DOMAINS
from analyzer.wording import describe_profile
from analyzer.preprocess import bandpass, notch, epoch, reject_epochs
from analyzer.spectra import psd_of_epochs
from bridge.operator import (new_session_id, operator_code, operator_name,
                             save_operator)
from bridge.cloud import (ManagerSession, configured as cloud_configured,
                          pending_count)
from bridge.paths import (PUBLIC_DIR, REPORTS_DIR, data_dir, ensure_runtime_dirs,
                          settings as app_settings)
from bridge.recorder import Recorder
from bridge.storage import atomic_write_json, atomic_write_text

LIVE_PERIOD_S = 0.2   # пять обновлений в секунду, как в штатном приложении
FALLBACK_IAF = 10.0
# идентификатор сессии становится именем файла и попадает в интерфейс панели,
# поэтому допускаем только безопасный набор символов
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _check_session_id(session_id: str) -> str:
    """Чистит идентификатор до безопасного вида вместо отказа.

    Боевой урок 13.08: диагност ввёл идентификатор не латиницей, сервер
    ответил 400, страница проглотила ошибку, и пять минут теста прошли
    без записи. Сервер обязан принимать любой ввод и чинить его сам.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "-", session_id or "")
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")[:64]
    if not cleaned:
        # имя визита выдаёт мост: в нём код рабочего места и дата. Раньше было
        # одно время суток, и визиты двух менеджеров, начатые в одну секунду,
        # сливались в облаке в один: второй затирал первый
        cleaned = new_session_id()
    return cleaned


class EventIn(BaseModel):
    kind: str
    payload: dict = Field(default_factory=dict)
    session_id: str | None = None


class SessionIn(BaseModel):
    session_id: str = ""
    out_dir: str = "data"
    force: bool = False
    student_name: str = ""
    grade: str = ""
    track: str = "ru"


def _behaviour_only_profile(recorder, lang: str) -> dict:
    """Профиль по одним ответам, когда сигнала нет или он не разобрался.

    Визит с ответами это не пустой визит: точность и время по четырём типам
    задач сами по себе материал для разбора. Терять его из-за того, что
    ободок не надели, нельзя.
    """
    trials: dict[str, list] = {}
    for event in recorder.events:
        if event["kind"] == "trial":
            payload = event.get("payload") or {}
            domain = payload.get("domain")
            if domain:
                trials.setdefault(domain, []).append(payload)
    behavior = {d: block_behavior(trials.get(d, [])) for d in DOMAINS}
    return {
        "session_id": recorder.session_id,
        "lang": lang,
        "method_version": "поведение-1.0",
        "iaf": None,
        "has_eeg": False,
        "quality": {"reasons": ["сигнал не записан, разбор только по ответам"]},
        "domains": [{"domain": d, "accuracy": behavior[d]["accuracy"],
                     "median_rt_ms": behavior[d]["median_rt_ms"],
                     "cost": None, "efficiency": None,
                     "attention_slope": None} for d in DOMAINS],
        "behavior": behavior,
        "neuro": None,
    }


def _restart_process() -> None:
    """Перезапуск моста тем же процессом: работает и под launchd, и из окна.

    10.09 мост простоял сутки с мёртвым системным Bluetooth: 512 повисших
    потоков, «не удалось подключиться за 20 секунд» при включённом ободке,
    и никто, кроме перезапуска, ему не помог бы. Заменяем образ процесса
    на свежий: слушающий порт при этом освобождается, launchd ничего
    не замечает.
    """
    print("системный Bluetooth перестал отвечать, мост перезапускается",
          flush=True)
    if getattr(sys, "frozen", False):
        os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
    os.execv(sys.executable, [sys.executable, "-m", "bridge.main", *sys.argv[1:]])


def create_app(recorder, clock, device, realtime=None, mirror=None,
               app_db=None) -> FastAPI:
    ensure_runtime_dirs()
    state = {"recorder": recorder, "out_dir": str(data_dir()), "phase": None,
             "realtime": realtime, "running": False, "stopping": False,
             "lang": "ru", "streaming": False, "last_stop_result": None}
    manager = ManagerSession()
    session_lock = threading.RLock()

    async def watch_stream() -> None:
        """Следит за потоком даже когда страница мониторинга закрыта."""
        last, stall = -1, 0
        while True:
            await asyncio.sleep(1.0)
            current = int(getattr(device, "packets_received", 0))
            if current != last:
                last, stall = current, 0
                continue
            stall += 1
            if stall >= 10 and hasattr(device, "watchdog"):
                await asyncio.to_thread(device.watchdog)
                stall = 0
            if getattr(device, "bluetooth_dead", False) and not state["running"]:
                _restart_process()

    async def sync_cloud() -> None:
        from bridge.cloud import flush_pending
        while True:
            try:
                await asyncio.to_thread(flush_pending, manager)
            except Exception:
                pass
            await asyncio.sleep(30.0)

    @asynccontextmanager
    async def lifespan(_app):
        tasks = [asyncio.create_task(watch_stream()),
                 asyncio.create_task(sync_cloud())]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for source in (mirror, app_db, device):
                closer = getattr(source, "close", None) or getattr(source, "stop", None)
                if closer is not None:
                    try:
                        closer()
                    except Exception:
                        pass

    app = FastAPI(title="BHS neuro bridge", lifespan=lifespan)
    configured_url = app_settings().get("TEST_URL", "")
    origin = urlsplit(configured_url)
    allowed_origins = ["http://127.0.0.1:8765", "http://localhost:8765"]
    if origin.scheme in ("http", "https") and origin.netloc:
        allowed_origins.append(f"{origin.scheme}://{origin.netloc}")
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins,
                       allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type"], allow_credentials=False)

    @app.middleware("http")
    async def _allow_private_network(request, call_next):
        """Разрешение Chrome ходить с https-сайта к мосту на 127.0.0.1.

        Когда страница теста открыта с облачного адреса, браузер перед каждым
        запросом в локальную сеть спрашивает разрешения отдельным заголовком.
        Без ответа на него сайт до моста не достучится, и тест на облачной
        странице шёл бы без нейро-слоя.
        """
        try:
            response = await call_next(request)
        except Exception:
            if request.url.path == "/session/stop":
                # Разрешить повторить сохранение после временной ошибки диска.
                state["stopping"] = False
                state["running"] = True
            raise
        if request.url.path == "/session/stop" and response.status_code >= 500:
            state["stopping"] = False
            state["running"] = True
        if request.headers.get("access-control-request-private-network") == "true":
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response
    def _feed(chunk: np.ndarray) -> None:
        """Живые метрики считаются всегда, запись только во время сессии.

        Прибор стримит постоянно, поэтому монитор должен показывать состояние
        и до начала теста: диагносту это нужно, чтобы проверить посадку.
        """
        if state["running"]:
            state["recorder"].push_samples(chunk, clock.now_s())
        if state["realtime"] is not None:
            state["realtime"].push(chunk)

    # полосы нужны сразу: без них метрики не считаются и монитор пустой.
    # До калибровки берём средние, после неё они пересчитываются от личного пика
    if realtime is not None:
        realtime.set_bands(bands_from_iaf(FALLBACK_IAF))

    # подписываемся на поток сразу, не дожидаясь старта сессии
    try:
        device.start(_feed)
        state["streaming"] = True
    except Exception:
        state["streaming"] = False

    @app.get("/status")
    def status() -> dict:
        def safe(call, fallback):
            try:
                return call()
            except Exception:
                return fallback

        return {
            "connected": bool(device.connected),
            "contact": safe(device.contact, {name: 0.0 for name in
                                               ("T3", "T4", "O1", "O2")}),
            "battery": safe(device.battery, 0),
            "t_s": clock.now_s(),
            "samples": int(state["recorder"].signal().shape[1]),
            "running": state["running"],
            "phase": state["phase"],
            "packets": int(getattr(device, "packets_received", 0)),
            "streaming": bool(state.get("streaming")),
            # страница теста показывает менеджеру, к какому мосту подключилась
            "operator": operator_code(),
            "operator_name": operator_name(),
            # почему прибора нет: менеджеру это видно прямо на странице теста
            "device_error": getattr(device, "last_error", "") or "",
            "manager": manager.snapshot(),
            "cloud_pending": pending_count(),
        }

    @app.post("/event")
    def event(body: EventIn) -> dict:
        # метки чужой сессии отбрасываем: иначе два источника пишут в один
        # журнал, фазы перемешиваются и профиль посчитать нельзя
        if (body.session_id and state["running"]
                and body.session_id != state["recorder"].session_id):
            return {"ok": False, "reason": "метка не от текущей сессии"}
        # время ставит мост, клиентские часы не используются никогда
        if body.kind == "session_start":
            state["lang"] = body.payload.get("lang", "ru")
        if body.kind in ("block_start", "calibration_eyes_closed_start",
                         "calibration_eyes_open_start", "rest_start"):
            state["phase"] = body.payload.get("domain", body.kind)
        return state["recorder"].push_event(body.kind, body.payload, clock.now_s())

    @app.post("/session/start")
    def session_start(body: SessionIn) -> dict:
        body.session_id = _check_session_id(body.session_id)
        # вторая сессия поверх первой стирает запись: на визите это значит
        # потерянный визит, поэтому старт отклоняется, пока идёт другая
        with session_lock:
            if state["stopping"]:
                raise HTTPException(status_code=409,
                                    detail="предыдущая запись ещё сохраняется")
            if state["running"] and not body.force:
                raise HTTPException(status_code=409,
                                    detail="предыдущая запись ещё не закрыта")
            if state["running"] and body.force:
                # Принудительный старт больше не выбрасывает прошлую запись.
                old = state["recorder"]
                old.save(state["out_dir"])
                interrupted = dict(state.get("meta") or {})
                interrupted.update({"session_id": old.session_id,
                                    "interrupted": True})
                atomic_write_json(os.path.join(
                    state["out_dir"], f"{old.session_id}.meta.json"), interrupted)
        clock.reset()
        import time as _time
        state["mono_start"] = _time.monotonic()
        state["meta"] = {"session_id": body.session_id,
                         "student_name": body.student_name.strip()[:80],
                         "grade": body.grade.strip()[:16],
                         "track": "kk" if body.track == "kk" else "ru",
                         "started_at": _time.strftime("%Y-%m-%d %H:%M"),
                         # кто и на какой машине провёл: приборов много,
                         # облако одно, и на разборе это надо различать
                         "operator": operator_code(),
                         "operator_name": operator_name()}
        state["recorder"] = Recorder(fs=device.fs, session_id=body.session_id)
        state["out_dir"] = str(data_dir(body.out_dir))
        state["running"] = True
        state["stopping"] = False
        state["last_stop_result"] = None
        if mirror is not None:
            mirror.reset_track()
        if app_db is not None:
            app_db.reset_track()
        if state["realtime"] is not None:
            state["realtime"].set_bands(bands_from_iaf(FALLBACK_IAF))
        if not state.get("streaming"):
            try:
                device.start(_feed)
                state["streaming"] = True
            except Exception as error:
                state["streaming"] = False
                return {"ok": True, "session_id": body.session_id,
                        "warning": "запись начата без сигнала: " + str(error)[:120]}
        return {"ok": True, "session_id": body.session_id}  # id уже очищен

    @app.post("/session/stop")
    def session_stop() -> dict:
        """Останавливает запись и сразу считает профиль. Поток при этом
        продолжает идти, чтобы монитор оставался живым.

        Разбор с родителем начинается через несколько минут после сессии,
        поэтому расчёт идёт здесь же и его результат уже лежит на диске.
        """
        with session_lock:
            if state["stopping"]:
                raise HTTPException(status_code=409, detail="сессия уже сохраняется")
            if not state["running"]:
                if state.get("last_stop_result") is not None:
                    return state["last_stop_result"]
                raise HTTPException(status_code=409, detail="запись сессии не запущена")
            state["running"] = False
            state["stopping"] = True
            rec = state["recorder"]
        npz_path, events_path = rec.save(state["out_dir"])

        # анкета визита рядом с записью: панель собирает карточки по ней
        meta = dict(state.get("meta") or {})
        meta["session_id"] = rec.session_id
        meta_path = os.path.join(state["out_dir"], f"{rec.session_id}.meta.json")
        atomic_write_json(meta_path, meta)

        # побочные каналы за время сессии: пульс и сопротивление из моста
        import time as _time
        side_path = None
        if hasattr(device, "side_slice") and state.get("mono_start"):
            rows = device.side_slice(state["mono_start"], _time.monotonic())
            if rows:
                side_path = os.path.join(state["out_dir"],
                                         f"{rec.session_id}.side.jsonl")
                start = state["mono_start"]
                text = "".join(json.dumps({"t": round(t - start, 3),
                                            "uuid": channel,
                                            "data": raw.hex()}) + "\n"
                               for t, channel, raw in rows)
                atomic_write_text(side_path, text)
        result = {"npz": npz_path, "events": events_path, "profile": None,
                  "profile_error": None, "mirror_profile": None}

        # оценки штатного приложения за время сессии: свой слой рядом
        # с нашим, для сверки на разборе
        if app_db is not None and app_db.track:
            app_path = os.path.join(state["out_dir"],
                                    f"{rec.session_id}.app_state.json")
            atomic_write_json(app_path, list(app_db.track))
            result["app_state"] = app_path

        # упрощённый путь: показания прибора приходят из штатного приложения,
        # мы режем их дорожку по блокам теста
        if mirror is not None and mirror.track:
            trials: dict[str, list] = {}
            for event in rec.events:
                if event["kind"] == "trial":
                    payload = event["payload"]
                    trials.setdefault(payload["domain"], []).append(payload)
            behavior = {d: block_behavior(trials.get(d, [])) for d in DOMAINS}
            mirror_profile = build_mirror_profile(
                {"session_id": rec.session_id, "lang": state["lang"]},
                rec.events, list(mirror.track), behavior)
            mirror_path = os.path.join(state["out_dir"],
                                       f"{rec.session_id}.mirror.json")
            atomic_write_json(mirror_path, mirror_profile)
            result["mirror_profile"] = mirror_path
        # Профиль, отчёт и выгрузка идут тремя независимыми шагами.
        # Раньше выгрузка была вложена в расчёт профиля, и визит без сигнала
        # не доезжал до панели вовсе: менеджер видел, что ребёнок прошёл тест,
        # а карточки не было. Ответы при этом записаны и разбор по ним возможен.
        profile = None
        try:
            profile = analyze(npz_path, events_path,
                              {"session_id": rec.session_id, "lang": state["lang"]})
        except Exception as error:
            result["profile_error"] = str(error)
            profile = _behaviour_only_profile(rec, state["lang"])
        profile_path = os.path.join(state["out_dir"], f"{rec.session_id}.profile.json")
        atomic_write_json(profile_path, profile)
        result["profile"] = profile_path

        # полный отчёт для панели: считается здесь же, пока семья идёт
        # от теста к разбору
        report = {}
        report_html = ""
        if profile.get("has_eeg"):
            try:
                from analyzer.report_data import build_report_data
                from report.build_html import build as build_report_page
                report = build_report_data(npz_path, events_path, profile)
                if side_path:
                    from tools.side_decode import load as side_load, \
                        ppg_series, pulse_from_ppg
                    channels = side_load(side_path)
                    report["pulse"] = pulse_from_ppg(ppg_series(channels.get("08", [])))
                report_json = os.path.join(state["out_dir"],
                                           f"{rec.session_id}.report.json")
                atomic_write_json(report_json, report, indent=None)
                os.makedirs(REPORTS_DIR, exist_ok=True)
                caption = " · ".join(part for part in
                                     (meta.get("student_name"),
                                      meta.get("grade"),
                                      meta.get("started_at")) if part)
                report_html = str(REPORTS_DIR / f"{rec.session_id}.html")
                build_report_page(report, report_html, caption or rec.session_id)
                result["report"] = f"reports/{rec.session_id}.html"
            except Exception as report_error:
                result["report_error"] = str(report_error)
                report_html = ""

        # облачная копия: панель менеджера видит визит сразу. Идёт всегда,
        # даже без нейро-слоя: карточка с ответами лучше пропавшего визита
        try:
            from bridge.cloud import push_visit
            result["cloud"] = push_visit(manager, meta, profile, report, report_html)
        except Exception as cloud_error:
            result["cloud"] = "офлайн: " + str(cloud_error)[:120]
        with session_lock:
            state["stopping"] = False
            state["last_stop_result"] = result
        return result

    class ManagerIn(BaseModel):
        access_token: str = ""
        refresh_token: str = ""
        manager_id: str = ""
        email: str = ""
        expires_at: float = 0

    @app.post("/manager")
    def sign_in(body: ManagerIn) -> dict:
        """Передача входа со страницы в программу.

        Визит уходит в облако под учётной записью менеджера, поэтому
        программе нужен его вход. Иначе принадлежность визита пришлось бы
        объявлять со страницы, а такому объявлению верить нельзя.
        """
        if not body.manager_id or not body.access_token:
            raise HTTPException(status_code=400, detail="неполный вход")
        saved = manager.remember(body.model_dump())
        # имя рабочего места по почте: оно идёт в имя файлов визита
        save_operator(body.email.split("@")[0] or body.manager_id[:8])
        from bridge.cloud import flush_pending
        synced = flush_pending(manager)
        return {"ok": True, **saved, **synced}

    @app.get("/manager")
    def manager_state() -> dict:
        return {**manager.snapshot(), "cloud_configured": cloud_configured()}

    @app.delete("/manager")
    def sign_out() -> dict:
        manager.clear()
        return {"ok": True}

    @app.get("/report/{session_id}.pdf")
    def report_pdf(session_id: str):
        """Готовый PDF отчёта: печатается браузером, один в один с экраном.

        Печать занимает несколько секунд, поэтому готовый файл кладём рядом
        с отчётом и второй раз отдаём уже его: на разборе документ обычно
        просят не по одному разу.
        """
        session_id = _check_session_id(session_id)
        html_path = str(REPORTS_DIR / f"{session_id}.html")
        if not os.path.exists(html_path):
            raise HTTPException(status_code=404, detail="отчёт не найден")
        pdf_path = str(REPORTS_DIR / f"{session_id}.pdf")
        if (not os.path.exists(pdf_path)
                or os.path.getmtime(pdf_path) < os.path.getmtime(html_path)):
            from report.to_pdf import html_to_pdf, BrowserNotFound
            try:
                html_to_pdf(html_path, pdf_path)
            except BrowserNotFound:
                # В Windows всегда есть системный Arial, поэтому компактный
                # PDF можно собрать средствами, уже упакованными в EXE.
                profile_path = os.path.join(state["out_dir"],
                                            f"{session_id}.profile.json")
                if not os.path.exists(profile_path):
                    raise HTTPException(status_code=404, detail="профиль не найден")
                from report.build_pdf import build_report
                with open(profile_path, encoding="utf-8") as fh:
                    profile = json.load(fh)
                build_report(profile, pdf_path, profile.get("lang", "ru"))
            except Exception as error:
                raise HTTPException(status_code=500, detail=str(error))
        return FileResponse(pdf_path, media_type="application/pdf",
                            filename=f"{session_id}.pdf")

    @app.get("/report/{session_id}.html")
    def report_html(session_id: str):
        """Страница отчёта. Панель может жить на сайте, а отчёты здесь."""
        session_id = _check_session_id(session_id)
        path = str(REPORTS_DIR / f"{session_id}.html")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="отчёт не найден")
        return FileResponse(path, media_type="text/html; charset=utf-8")

    @app.get("/sessions")
    def sessions() -> dict:
        """Карточки всех визитов для админ-панели, свежие сверху."""
        cards = []
        for meta_path in glob.glob(os.path.join(state["out_dir"], "*.meta.json")):
            try:
                with open(meta_path, encoding="utf-8") as fh:
                    meta = json.load(fh)
            except Exception:
                continue
            sid = meta.get("session_id") or ""
            card = {"session_id": sid,
                    "student_name": meta.get("student_name") or "без имени",
                    "grade": meta.get("grade") or "",
                    "track": meta.get("track") or "ru",
                    "started_at": meta.get("started_at") or "",
                    "operator": meta.get("operator") or "",
                    "operator_name": meta.get("operator_name") or "",
                    "has_eeg": None, "iaf": None, "report": None}
            profile_path = os.path.join(state["out_dir"], f"{sid}.profile.json")
            if os.path.exists(profile_path):
                try:
                    with open(profile_path, encoding="utf-8") as fh:
                        profile = json.load(fh)
                    card["has_eeg"] = profile.get("has_eeg")
                    card["iaf"] = profile.get("iaf")
                except Exception:
                    pass
            if os.path.exists(REPORTS_DIR / f"{sid}.html"):
                card["report"] = f"reports/{sid}.html"
            cards.append(card)
        cards.sort(key=lambda c: c["started_at"], reverse=True)
        return {"items": cards}

    @app.get("/contact/raw")
    def contact_raw() -> dict:
        """Сырое сопротивление электродов: для проверки посадки и разбора.

        Порядок в пакете принят как O1 O2 T3 T4, и это допущение: сверять его
        надо с тем, что показывает штатное приложение на своей схеме головы.
        """
        raw = getattr(device, "last_resist_raw", None)
        if not raw:
            return {"ok": False, "reason": "поток сопротивления молчит"}
        return {"ok": True,
                "raw": raw,
                "kohm": [round(v / 1000.0, 1) for v in raw],
                "as_mapped": {name: round(value / 1000.0, 1) for name, value
                              in zip(("O1", "O2", "T3", "T4"), raw)},
                "contact": device.contact()}

    @app.get("/raw")
    def raw_metrics() -> dict:
        """Сырые индексы без нормировки. Нужны для калибровки шкалы."""
        if state["realtime"] is None:
            return {"ok": False}
        snapshot = state["realtime"].snapshot()
        return {"ok": True, "raw": snapshot.get("raw"),
                "percent": {k: snapshot.get(k) for k in ("focus", "load", "relax")}}

    @app.get("/profiles")
    def profiles() -> dict:
        """Список посчитанных профилей, свежие сверху."""
        paths = sorted(glob.glob(os.path.join(state["out_dir"], "*.profile.json")),
                       key=os.path.getmtime, reverse=True)
        items = []
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                profile = json.load(fh)
            items.append({"session_id": profile["session_id"],
                          "has_eeg": profile["has_eeg"],
                          "iaf": profile.get("iaf"),
                          "lang": profile.get("lang", "ru")})
        return {"items": items}

    @app.get("/mirror/{session_id}")
    def mirror_profile_one(session_id: str) -> dict:
        """Профиль по показаниям прибора из штатного приложения."""
        session_id = _check_session_id(session_id)
        path = os.path.join(state["out_dir"], f"{session_id}.mirror.json")
        if not os.path.exists(path):
            return {"ok": False, "reason": "профиль не найден"}
        with open(path, encoding="utf-8") as fh:
            return {"ok": True, "profile": json.load(fh)}

    @app.get("/profile/{session_id}")
    def profile_one(session_id: str) -> dict:
        session_id = _check_session_id(session_id)
        path = os.path.join(state["out_dir"], f"{session_id}.profile.json")
        if not os.path.exists(path):
            return {"ok": False, "reason": "профиль не найден"}
        with open(path, encoding="utf-8") as fh:
            profile = json.load(fh)
        return {"ok": True, "profile": profile,
                "wording": describe_profile(profile, profile.get("lang", "ru"))}

    @app.post("/calibration/finish")
    def calibration_finish() -> dict:
        """Считает личный альфа-пик и покой ребёнка, настраивает живые метрики.

        Вызывается тестом сразу после калибровки. Пока это не сделано, монитор
        показывает отклонение от текущего состояния, а не от личного покоя.
        """
        rec = state["recorder"]
        signal = rec.signal()
        if signal.shape[1] < device.fs * 10:
            return {"ok": False, "reason": "мало данных для калибровки"}

        def _slice(kind_start: str, kind_end: str):
            starts = [e for e in rec.events if e["kind"] == kind_start]
            ends = [e for e in rec.events if e["kind"] == kind_end]
            if not starts or not ends:
                return None
            a = int(starts[0]["t_s"] * device.fs)
            b = int(ends[0]["t_s"] * device.fs)
            return signal[:, a:b] if b - a > device.fs * 5 else None

        closed = _slice("calibration_eyes_closed_start", "calibration_eyes_closed_end")
        opened = _slice("calibration_eyes_open_start", "calibration_eyes_open_end")
        if closed is None or opened is None:
            return {"ok": False, "reason": "нет полных фаз калибровки"}

        closed_eps = epoch(bandpass(notch(closed, fs=device.fs), fs=device.fs), fs=device.fs)
        keep = reject_epochs(closed_eps, fs=device.fs)
        if not keep.any():
            return {"ok": False, "reason": "калибровка целиком в артефактах"}
        freqs, psd = psd_of_epochs(closed_eps, fs=device.fs, keep=keep)
        iaf, prominence = compute_iaf(freqs, psd)

        bands = bands_from_iaf(iaf if iaf is not None else FALLBACK_IAF)
        open_eps = epoch(bandpass(notch(opened, fs=device.fs), fs=device.fs), fs=device.fs)
        open_keep = reject_epochs(open_eps, fs=device.fs)
        base_freqs, base_psd = psd_of_epochs(open_eps, fs=device.fs,
                                             keep=open_keep if open_keep.any() else None)

        if state["realtime"] is not None:
            state["realtime"].set_bands(bands)
            state["realtime"].set_baseline(base_freqs, base_psd)

        return {"ok": True, "iaf": iaf, "prominence": round(prominence, 2),
                "bands": {k: [round(v[0], 2), round(v[1], 2)] for k, v in bands.items()},
                "rejected_share": round(float((~keep).mean()), 3)}

    @app.websocket("/live")
    async def live(ws: WebSocket) -> None:
        ws_origin = urlsplit(ws.headers.get("origin", ""))
        local_origin = ws_origin.hostname in ("127.0.0.1", "localhost")
        if ws_origin.netloc and not local_origin and ws.headers.get("origin") not in allowed_origins:
            await ws.close(code=1008, reason="origin is not allowed")
            return
        await ws.accept()
        try:
            while True:
                payload = {"contact": device.contact(), "phase": state["phase"],
                           "running": state["running"]}
                if state["realtime"] is not None:
                    payload.update(state["realtime"].snapshot())
                if mirror is not None:
                    payload.update(mirror.snapshot())
                if app_db is not None:
                    payload.update(app_db.snapshot())
                await ws.send_json(payload)
                await asyncio.sleep(LIVE_PERIOD_S)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.get("/app")
    def local_app_root():
        return RedirectResponse("/app/index")

    @app.get("/app/{name}")
    def local_app_file(name: str):
        """Встроенный сайт делает EXE пригодным для работы без интернета."""
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise HTTPException(status_code=404, detail="страница не найдена")
        candidate = PUBLIC_DIR / name
        if not candidate.suffix:
            candidate = candidate.with_suffix(".html")
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="страница не найдена")
        media = ("text/javascript; charset=utf-8" if candidate.suffix == ".js"
                 else "text/html; charset=utf-8")
        return FileResponse(candidate, media_type=media)

    return app
