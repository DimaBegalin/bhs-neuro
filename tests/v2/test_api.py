import json
import time

import numpy as np

from app.api import Api
from app.device.link import DeviceLink
from app.device.replay import Fault, ReplayDevice
from app.device.sim import SimDevice
from app.session.session import SessionStore
from tests.v2.conftest import wait_until

STUDENT = {"name": "  Айгерим   Нурланова ", "grade": 9, "lang": "kk"}


def _api(tmp_path, speed=20.0):
    sim = SimDevice(speed=speed)
    link = DeviceLink(lambda: sim)
    api = Api(link, SessionStore(tmp_path / "sessions"), manager="Тест Менеджер",
              dev_controls={"on:background_closed_start": lambda _p: setattr(sim, "eyes_closed", True),
                            "on:background_open_start": lambda _p: setattr(sim, "eyes_closed", False)})
    return api, link


def test_full_session_with_headband(tmp_path):
    api, link = _api(tmp_path)
    api.device_connect()
    assert wait_until(lambda: api.device_state()["state"] == "streaming")
    started = api.session_start({**STUDENT, "with_headband": True})
    assert [m["id"] for m in started["plan"]] == ["background"]
    api.session_mark("background_closed_start")
    time.sleep(0.5)
    api.session_mark("background_open_start")
    time.sleep(0.5)
    done = api.session_finish()
    assert done["status"] == "finished" and done["samples"] > 0
    folder = tmp_path / "sessions" / started["id"]
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["student"] == {"name": "Айгерим Нурланова", "grade": 9, "lang": "kk"}
    assert started["id"].startswith("test-menedzher-") or started["id"].startswith("local-")
    events = json.loads((folder / "events.json").read_text())
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "session_start" and kinds[-1] == "session_end"
    assert np.load(folder / "signal.npz")["signal"].shape[0] == 4
    assert api.sessions_list()[0]["id"] == started["id"]
    link.disconnect()


def test_without_headband_needs_no_device(tmp_path):
    api, _ = _api(tmp_path)
    started = api.session_start({**STUDENT, "with_headband": False})
    assert started["with_headband"] is False and started["plan"] == []
    assert api.session_finish()["status"] == "finished"


def test_headband_session_refused_until_streaming(tmp_path):
    api, _ = _api(tmp_path)
    assert "error" in api.session_start({**STUDENT, "with_headband": True})


def test_bad_student_input_is_reported(tmp_path):
    api, _ = _api(tmp_path)
    assert "класс" in api.session_start({"name": "А", "grade": 7, "lang": "ru"})["error"]
    assert "имя" in api.session_start({"name": " ", "grade": 9, "lang": "ru"})["error"]


def test_second_session_needs_first_closed(tmp_path):
    api, _ = _api(tmp_path)
    api.session_start({**STUDENT, "with_headband": False})
    assert "error" in api.session_start({**STUDENT, "with_headband": False})
    api.session_abort("тест")
    assert "id" in api.session_start({**STUDENT, "with_headband": False})


def test_interrupted_session_is_recovered_on_next_start(tmp_path):
    api, link = _api(tmp_path)
    api.device_connect()
    assert wait_until(lambda: api.device_state()["state"] == "streaming")
    started = api.session_start({**STUDENT, "with_headband": True})
    time.sleep(0.6)  # имитатор ×20: за 0,6 с больше 5 с сигнала, был сброс на диск
    link.disconnect()  # программа «упала»: finish не вызван
    store = SessionStore(tmp_path / "sessions")
    assert store.recover_interrupted() == [started["id"]]
    meta = store.list()[0]
    assert meta["status"] == "interrupted"
    assert (tmp_path / "sessions" / started["id"] / "signal.npz").exists()


def test_replay_loops_and_simulates_lost_connection(tmp_path):
    path = tmp_path / "rec.npz"
    np.savez(path, signal=np.arange(4 * 500, dtype=float).reshape(4, 500), fs=250)
    device = ReplayDevice(path, faults=(Fault("lost", 1.0, 20.0),))
    chunks = [device.next_chunk() for _ in range(11)]  # 11 × 50 > 500: по кругу
    assert chunks[10][0, 0] == 0.0
    device.speed = 50.0
    got = []
    device.start(got.append)
    assert wait_until(lambda: not device.connected, 2.0)
    assert wait_until(lambda: device.connected, 2.0)
    device.close()
    assert got
