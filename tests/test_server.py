from fastapi.testclient import TestClient

from bridge.clock import SessionClock
from bridge.recorder import Recorder
from bridge.fake_device import FakeDevice
from bridge.realtime import RealtimeMetrics
from bridge.server import create_app


def _client():
    clock = SessionClock()
    recorder = Recorder(fs=250)
    device = FakeDevice(fs=250)
    realtime = RealtimeMetrics(fs=250)
    return TestClient(create_app(recorder, clock, device, realtime)), recorder, device


def test_status_reports_contact_for_four_channels():
    client, _, _ = _client()
    body = client.get("/status").json()
    assert set(body["contact"]) == {"T3", "T4", "O1", "O2"}
    assert body["connected"] is True
    assert body["running"] is False


def test_event_is_stamped_by_bridge_not_client():
    client, recorder, _ = _client()
    response = client.post("/event", json={"kind": "block_start",
                                           "payload": {"domain": "spatial"}})
    assert response.status_code == 200
    stamped = response.json()["t_s"]
    assert stamped >= 0  # таймер Windows шагает по ~15 мс: сразу после старта бывает ровно 0
    assert recorder.events[-1]["t_s"] == stamped
    assert recorder.events[-1]["kind"] == "block_start"
    assert client.get("/status").json()["phase"] == "spatial"


def test_session_start_and_stop_produce_files(tmp_path):
    client, _, _ = _client()
    client.post("/session/start", json={"session_id": "test-1",
                                        "out_dir": str(tmp_path)})
    client.post("/event", json={"kind": "ping", "payload": {}})
    body = client.post("/session/stop").json()
    assert body["npz"].endswith(".npz")
    assert body["events"].endswith(".events.json")


def test_session_stop_is_idempotent(tmp_path):
    """Повтор кнопки/запроса не должен пересчитать или испортить визит."""
    client, _, _ = _client()
    client.post("/session/start", json={"session_id": "once",
                                        "out_dir": str(tmp_path)})
    first = client.post("/session/stop")
    second = client.post("/session/stop")
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()


def test_embedded_local_site_is_served():
    client, _, _ = _client()
    response = client.get("/app/test")
    assert response.status_code == 200
    assert "BHS" in response.text


def test_calibration_refuses_without_data():
    client, _, _ = _client()
    body = client.post("/calibration/finish").json()
    assert body["ok"] is False


def test_live_socket_sends_snapshot():
    client, _, _ = _client()
    with client.websocket_connect("/live") as ws:
        message = ws.receive_json()
    assert set(message["contact"]) == {"T3", "T4", "O1", "O2"}
    assert "focus" in message


def test_stop_computes_profile_for_full_session(tmp_path):
    """Полная сессия из фикстуры прогоняется через мост и даёт профиль на диске."""
    import json
    import shutil

    from tests.fixtures.session import write_session

    client, _, _ = _client()
    source = tmp_path / "source"
    npz_path, events_path = write_session(source, session_id="bridge-e2e")
    client.post("/session/start", json={"session_id": "bridge-e2e",
                                        "out_dir": str(tmp_path)})
    # подменяем запись готовой сессией: мост считает профиль из файлов
    body = client.post("/session/stop").json()
    shutil.copy(npz_path, body["npz"])
    shutil.copy(events_path, body["events"])

    from analyzer.main import analyze
    profile = analyze(body["npz"], body["events"],
                      {"session_id": "bridge-e2e", "lang": "ru"})
    with open(str(tmp_path / "bridge-e2e.profile.json"), "w", encoding="utf-8") as fh:
        json.dump(profile, fh, ensure_ascii=False)

    listed = client.get("/profiles").json()["items"]
    assert any(item["session_id"] == "bridge-e2e" for item in listed)

    one = client.get("/profile/bridge-e2e").json()
    assert one["ok"] is True
    assert one["wording"]["strong"]["title"]
    assert one["profile"]["has_eeg"] is True


def test_profile_endpoint_reports_missing():
    client, _, _ = _client()
    assert client.get("/profile/nope").json()["ok"] is False


def test_dangerous_session_id_is_sanitized_not_rejected():
    """Боевой урок: отказ сервера превращал визит в пустышку, страница глотала 400.

    Теперь любой ввод чистится до безопасного имени файла: без путей, без HTML.
    """
    client, _, _ = _client()
    response = client.post("/session/start",
                           json={"session_id": "../../etc/passwd", "out_dir": "data"})
    assert response.status_code == 200
    cleaned = response.json()["session_id"]
    assert ".." not in cleaned and "/" not in cleaned

    client2, _, _ = _client()
    response2 = client2.post("/session/start",
                             json={"session_id": "<img src=x onerror=alert(1)>",
                                   "out_dir": "data"})
    assert response2.status_code == 200
    assert "<" not in response2.json()["session_id"]


def test_cyrillic_session_id_gets_safe_fallback():
    """Кириллица целиком вычищается, сервер подставляет своё имя, а не падает."""
    import re
    from bridge.operator import operator_code
    client, _, _ = _client()
    response = client.post("/session/start",
                           json={"session_id": "Едыге Финал", "out_dir": "data"})
    assert response.status_code == 200
    generated = response.json()["session_id"]
    # своё имя это код рабочего места и дата: одного времени суток мало,
    # визиты двух менеджеров в одну секунду сливались бы в облаке в один
    assert generated.startswith(operator_code() + "-")
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", generated)


def test_second_session_does_not_wipe_the_first(tmp_path):
    """Старт поверх идущей сессии отклоняется: иначе визит теряется."""
    client, _, _ = _client()
    client.post("/session/start", json={"session_id": "first",
                                        "out_dir": str(tmp_path)})
    clash = client.post("/session/start", json={"session_id": "second",
                                                "out_dir": str(tmp_path)})
    assert clash.status_code == 409
    assert client.get("/status").json()["running"] is True

    forced = client.post("/session/start", json={"session_id": "second",
                                                 "out_dir": str(tmp_path),
                                                 "force": True})
    assert forced.status_code == 200


def test_events_from_another_session_are_dropped(tmp_path):
    """Два источника меток в одном журнале ломают нарезку по фазам."""
    client, recorder, _ = _client()
    client.post("/session/start", json={"session_id": "mine",
                                        "out_dir": str(tmp_path)})
    client.post("/event", json={"kind": "block_start", "session_id": "mine",
                                "payload": {"domain": "numeric"}})
    alien = client.post("/event", json={"kind": "block_start",
                                        "session_id": "someone-else",
                                        "payload": {"domain": "verbal"}})
    assert alien.json()["ok"] is False
    body = client.post("/session/stop").json()
    import json as _json
    saved = _json.loads(open(body["events"], encoding="utf-8").read())
    domains = [e["payload"].get("domain") for e in saved if e["kind"] == "block_start"]
    assert domains == ["numeric"]


def test_generated_session_id_carries_workplace_and_date():
    """Имя визита должно быть неповторимым среди всех менеджеров и дней.

    Раньше это было одно время суток: два менеджера, начавшие тест в одну
    секунду, получали один идентификатор, и в облаке второй визит затирал
    первый обновлением по совпавшему ключу.
    """
    import re
    from bridge.server import _check_session_id
    from bridge.operator import operator_code

    generated = _check_session_id("")
    assert generated.startswith(operator_code() + "-")
    assert re.search(r"-\d{6}-\d{6}$", generated), generated
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", generated)


def test_explicit_session_id_is_kept_as_is():
    from bridge.server import _check_session_id
    assert _check_session_id("visit-161824") == "visit-161824"


def test_visit_without_signal_still_reaches_the_panel(tmp_path, monkeypatch):
    """Ободок не надели, а тест ребёнок прошёл: визит терять нельзя.

    Боевой случай 15.08: расчёт профиля падал на пустом сигнале, выгрузка
    была вложена в него, и карточка не появлялась в панели вовсе. Менеджер
    видел, что ребёнок отвечал, а визита не было.
    """
    import bridge.server as server
    client, recorder, clock = _client()

    sent = {}

    def fake_push(manager, meta, profile, report, html_path):
        sent["profile"] = profile
        sent["meta"] = meta
        return "визит в облаке"

    monkeypatch.setattr("bridge.cloud.push_visit", fake_push)

    client.post("/session/start", json={"session_id": "без-сигнала",
                                        "out_dir": str(tmp_path),
                                        "student_name": "Ая Серik"})
    for index in range(3):
        client.post("/event", json={"kind": "trial", "payload": {
            "domain": "verbal", "correct": index != 1, "rt_ms": 900 + index}})
    body = client.post("/session/stop").json()

    assert body["cloud"] == "визит в облаке", body
    assert sent["profile"]["has_eeg"] is False
    assert sent["profile"]["behavior"]["verbal"]["n_trials"] == 3
    assert sent["meta"]["student_name"] == "Ая Серik"
    # причина отсутствия нейро-слоя должна быть названа, а не умолчана
    assert sent["profile"]["quality"]["reasons"]
