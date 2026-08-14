# -*- coding: utf-8 -*-
"""Рабочее место менеджера и неповторимость имени визита."""
import re
import time

import pytest

from bridge import operator as op


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Подменяем .env: настоящий трогать нельзя, в нём ключи облака."""
    path = tmp_path / ".env"
    monkeypatch.setattr(op, "ENV_PATH", str(path))
    return path


def test_operator_code_comes_from_env_when_set(env, monkeypatch):
    env.write_text("OPERATOR=anna-2\n", encoding="utf-8")
    monkeypatch.setattr(op, "_computer_name", lambda: "Mac Anna")
    assert op.operator_code() == "anna2"


def test_russian_name_becomes_readable_latin_code(env, monkeypatch):
    """Кириллица в коде недопустима: он идёт в имя файла визита и в облако.

    Выбрасывать её нельзя: русское имя целиком обнулялось, установщик
    подставлял хеш вида 7fe77581, и рабочее место в панели было не опознать.
    """
    monkeypatch.setattr(op, "_computer_name", lambda: "Mac Anna")
    env.write_text("OPERATOR=Анна Петрова\n", encoding="utf-8")
    assert op.operator_code() == "annapetrova"
    env.write_text("OPERATOR=Диана Серікқызы\n", encoding="utf-8")
    assert op.operator_code() == "dianaserikqy"


def test_operator_code_falls_back_to_computer_name(env, monkeypatch):
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(op, "_computer_name", lambda: "MacBook Ани")
    assert op.operator_code() == "macbookani"


def test_operator_code_never_empty(env, monkeypatch):
    """Мост обязан подняться даже без имени машины: иначе визит не начать."""
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(op, "_computer_name", lambda: "")
    assert op.operator_code() == op.FALLBACK


def test_session_id_is_safe_for_file_names_and_cloud(env, monkeypatch):
    env.write_text("OPERATOR=anna\n", encoding="utf-8")
    sid = op.new_session_id()
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", sid), sid
    assert sid.startswith("anna-")


def test_two_machines_at_the_same_second_do_not_collide(env, monkeypatch):
    """Боевой риск: два менеджера жмут «Начать» одновременно.

    Раньше имя было одним временем суток, и в облаке второй визит
    затирал первый обновлением по совпавшему ключу.
    """
    moment = time.localtime()
    env.write_text("OPERATOR=anna\n", encoding="utf-8")
    first = op.new_session_id(moment)
    env.write_text("OPERATOR=bolat\n", encoding="utf-8")
    second = op.new_session_id(moment)
    assert first != second


def test_same_time_on_different_days_does_not_collide(env):
    env.write_text("OPERATOR=anna\n", encoding="utf-8")
    day1 = time.strptime("2026-08-14 14:30:15", "%Y-%m-%d %H:%M:%S")
    day2 = time.strptime("2026-08-15 14:30:15", "%Y-%m-%d %H:%M:%S")
    assert op.new_session_id(day1) != op.new_session_id(day2)


def test_missing_env_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(op, "ENV_PATH", str(tmp_path / "нет-файла"))
    assert op.operator_code()
    assert op.operator_name() == ""
