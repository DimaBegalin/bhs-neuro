import json

import pytest

from app.cloud import auth as auth_mod
from app.cloud import sync as sync_mod
from app.cloud.http import HttpError, Offline
from app.cloud.updates import parse
from app.storage import atomic_write_json


@pytest.fixture
def cloud(home, monkeypatch):
    monkeypatch.setattr(auth_mod, "cloud_configured", lambda: True)
    monkeypatch.setattr(sync_mod, "cloud_configured", lambda: True)
    s = {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_ANON_KEY": "anon", "SITE_URL": "https://s"}
    monkeypatch.setattr(auth_mod, "settings", lambda: s)
    monkeypatch.setattr(sync_mod, "settings", lambda: s)
    calls = []

    def fake_request(url, method="GET", body=None, headers=None, timeout=15.0):
        calls.append({"url": url, "method": method, "body": body, "headers": headers})
        if "grant_type=password" in url:
            if body["password"] != "ok":
                raise HttpError(400, "invalid")
            return {"access_token": "A", "refresh_token": "R", "expires_in": 3600,
                    "user": {"id": "u1", "email": body["email"]}}
        if "grant_type=refresh_token" in url:
            return {"access_token": "A2", "refresh_token": "R2", "expires_in": 3600,
                    "user": {"id": "u1", "email": "m@bhs.kz"}}
        if fake_request.offline:
            raise Offline("нет сети")
        return None

    fake_request.offline = False
    monkeypatch.setattr(auth_mod, "request", fake_request)
    monkeypatch.setattr(sync_mod, "request", fake_request)
    return calls, fake_request


class Clock:
    t = 1_000_000.0

    def __call__(self):
        return self.t


def test_login_offline_window_and_refresh(cloud):
    calls, _ = cloud
    clock = Clock()
    auth = auth_mod.ManagerAuth(clock=clock)
    with pytest.raises(auth_mod.AuthError, match="неверная"):
        auth.login("m@bhs.kz", "bad")
    auth.login("m@bhs.kz", "ok")
    assert auth.state()["logged_in"] and auth.state()["name"] == "m"
    clock.t += 29 * 86400
    assert auth.state()["logged_in"]
    clock.t += 2 * 86400
    assert not auth.state()["logged_in"] and auth.state()["expired"]
    assert auth.token() == ("A2", "u1")  # токен истёк → обновлён
    assert auth.state()["logged_in"]  # удачное обращение продлевает офлайн-срок


def _session(root, sid="s1"):
    folder = root / sid
    atomic_write_json(folder / "meta.json", {"id": sid, "student": {"name": "Ученик", "grade": 9, "lang": "kk"},
                                             "with_headband": False, "started_at": "2026-10-01T10:00:00",
                                             "status": "finished"})
    atomic_write_json(folder / "result.json", {"interests": {"scores": {}}, "recommendation": {"top": [], "clusters": []}})
    (folder / "report.html").write_text("<html>ok</html>", encoding="utf-8")
    return folder


def test_visit_waits_without_login_and_network_then_is_sent(cloud, home):
    calls, fake = cloud
    auth = auth_mod.ManagerAuth()
    syncer = sync_mod.Syncer(auth, home / "sessions")
    syncer.enqueue(_session(home / "sessions"))
    assert syncer.flush() == {"sent": 0, "pending": 1} and "не вошёл" in syncer.last_error
    auth.login("m@bhs.kz", "ok")
    fake.offline = True
    assert syncer.flush()["pending"] == 1 and syncer.last_error == "нет сети"
    fake.offline = False
    assert syncer.flush() == {"sent": 1, "pending": 0}
    row = calls[-1]["body"][0]
    assert row["manager_id"] == "u1" and row["track"] == "kk" and row["grade"] == "9"
    assert row["report_html"] == "<html>ok</html>" and row["domains"]["methodology"] == "2.0"
    assert "on_conflict=session_id" in calls[-1]["url"]
    assert json.loads((home / "sessions" / "s1" / "meta.json").read_text(encoding="utf-8"))["synced_at"]


def test_version_parse():
    assert parse("2.0.1") > parse("2.0.0-dev") and parse("2.1") > parse("2.0.9")
