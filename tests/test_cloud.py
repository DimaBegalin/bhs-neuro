# -*- coding: utf-8 -*-
"""Вход менеджера и выгрузка визита от его имени."""
import json
import os
import time

import pytest

from bridge import cloud


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "ENV_PATH", str(tmp_path / ".env"))
    monkeypatch.setattr(cloud, "SESSION_PATH", str(tmp_path / ".manager_session.json"))
    (tmp_path / ".env").write_text(
        "SUPABASE_URL=https://проект.supabase.co\nSUPABASE_ANON_KEY=anon\n",
        encoding="utf-8")
    return tmp_path


def _signed_in(session):
    return session.remember({
        "access_token": "живой", "refresh_token": "обновление",
        "manager_id": "11111111-2222-3333-4444-555555555555",
        "email": "anna@bhs.kz", "expires_at": time.time() + 3600})


def test_session_survives_restart(paths):
    """Ноутбук перезагружают каждый день, вход не должен теряться.

    Иначе визиты копились бы неотправленными, а менеджер узнавал бы об этом
    только когда карточка не появилась в панели.
    """
    _signed_in(cloud.ManagerSession())
    again = cloud.ManagerSession()
    assert again.snapshot()["signed_in"] is True
    assert again.snapshot()["email"] == "anna@bhs.kz"


def test_session_file_is_not_readable_by_others(paths):
    """В файле лежит доступ к записям менеджера."""
    _signed_in(cloud.ManagerSession())
    mode = os.stat(cloud.SESSION_PATH).st_mode & 0o777
    assert mode == 0o600, oct(mode)


def test_visit_carries_the_manager_id(paths, monkeypatch):
    """Принадлежность визита определяет вход, а не страница."""
    session = cloud.ManagerSession()
    _signed_in(session)
    sent = {}

    def fake_request(url, method="GET", body=None, headers=None):
        sent["url"] = url
        sent["row"] = body[0]
        sent["auth"] = headers.get("Authorization")
        return {}

    monkeypatch.setattr(cloud, "_request", fake_request)
    answer = cloud.push_visit(session, {"session_id": "v1", "student_name": "Ая"},
                              {"has_eeg": True, "iaf": 10.1}, {}, "")
    assert answer == "визит в облаке"
    assert sent["row"]["manager_id"] == "11111111-2222-3333-4444-555555555555"
    assert sent["row"]["student_name"] == "Ая"
    assert sent["auth"] == "Bearer живой"


def test_visit_without_sign_in_stays_on_the_laptop(paths):
    """Без входа выгружать некуда, но и падать нельзя: запись уже на диске."""
    answer = cloud.push_visit(cloud.ManagerSession(), {"session_id": "v1"},
                              {}, {}, "")
    assert "не вошёл" in answer


def test_expired_token_is_refreshed_before_use(paths, monkeypatch):
    session = cloud.ManagerSession()
    session.remember({"access_token": "старый", "refresh_token": "обновление",
                      "manager_id": "id", "email": "a@b.c",
                      "expires_at": time.time() - 10})

    def fake_request(url, method="GET", body=None, headers=None):
        assert "refresh_token" in url
        return {"access_token": "свежий", "refresh_token": "новое", "expires_in": 3600}

    monkeypatch.setattr(cloud, "_request", fake_request)
    assert session.token() == "свежий"
    assert cloud.ManagerSession().data["refresh_token"] == "новое"


def test_dead_session_is_forgotten(paths, monkeypatch):
    """Протухший вход надо забыть, иначе программа молча шлёт в пустоту."""
    import urllib.error
    session = cloud.ManagerSession()
    session.remember({"access_token": "с", "refresh_token": "мертво",
                      "manager_id": "id", "email": "a@b.c", "expires_at": 0})

    def fake_request(url, method="GET", body=None, headers=None):
        raise urllib.error.HTTPError(url, 400, "Bad", {}, None)

    monkeypatch.setattr(cloud, "_request", fake_request)
    with pytest.raises(RuntimeError):
        session.token()
    assert cloud.ManagerSession().snapshot()["signed_in"] is False
