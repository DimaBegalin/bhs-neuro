# -*- coding: utf-8 -*-
"""Чтение показаний из базы штатного приложения."""
import json

from bridge.mind_db import read_states

STATE = (b'{"relaxation":0.0446,"fatigue":0.0573,"none":0.5791,'
         b'"concentration":0.1247,"involvement":0.1937,"stress":0.00032}')


def _page(state: bytes, stamp: bytes) -> bytes:
    """Кусок страницы базы: тело записи, служебный мусор, метка времени."""
    return b"\x00\x04j\xff" + state + b"PHYSIOLOGICAL_STATE\x00\x11" + stamp


def _write(tmp_path, blob: bytes):
    path = tmp_path / "data.mdb"
    path.write_bytes(blob)
    return str(path)


def test_reads_state_and_converts_to_percent(tmp_path):
    path = _write(tmp_path, _page(STATE, b"2026-08-13T10:54:06"))
    states = read_states(path)
    assert len(states) == 1
    assert states[0]["relaxation"] == 4.5
    assert states[0]["concentration"] == 12.5
    assert states[0]["at"] == "2026-08-13T10:54:06"


def test_repeated_pages_collapse_to_one_record(tmp_path):
    """База держит несколько версий страницы, запись встречается многократно."""
    blob = _page(STATE, b"2026-08-13T10:54:06") * 4
    assert len(read_states(_write(tmp_path, blob))) == 1


def test_records_come_in_time_order(tmp_path):
    blob = (_page(STATE, b"2026-08-13T10:57:31")
            + _page(STATE, b"2026-08-13T10:54:06")
            + _page(STATE, b"2026-08-13T10:55:51"))
    stamps = [s["at"] for s in read_states(_write(tmp_path, blob))]
    assert stamps == ["2026-08-13T10:54:06", "2026-08-13T10:55:51",
                      "2026-08-13T10:57:31"]


def test_record_without_timestamp_is_skipped(tmp_path):
    """Без метки времени точку некуда положить на дорожку сессии."""
    assert read_states(_write(tmp_path, b"junk" + STATE + b"tail")) == []


def test_missing_database_is_not_an_error(tmp_path):
    """Приложение может быть не установлено: мост обязан подняться."""
    assert read_states(str(tmp_path / "нет-такого.mdb")) == []


def test_broken_json_does_not_break_the_rest(tmp_path):
    blob = (b'{"relaxation":oops}' + _page(STATE, b"2026-08-13T10:54:06"))
    assert len(read_states(_write(tmp_path, blob))) == 1
