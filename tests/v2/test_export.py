import zipfile

from app.api import Api
from app.device.link import DeviceLink
from app.device.sim import SimDevice
from app.report import ANSWERS_CSV, MANAGER_PDF, PARENT_PDF, export_session
from app.session.session import SessionStore


def test_export_zips_reports_and_readable_answers(tmp_path):
    api = Api(DeviceLink(lambda: SimDevice()), SessionStore(tmp_path / "sessions"), manager="Айжан")
    started = api.session_start({"name": "Тест/Ученик", "grade": 9, "lang": "ru", "with_headband": False})
    data = api.session_content()
    first = data["interests"]["items"][0]
    api.session_mark("interest_answer", {"item": first["id"], "value": 1, "rt_ms": 900})
    api.session_mark("interest_answer", {"item": first["id"], "value": 5, "rt_ms": 2500})  # «Назад» и новый ответ
    for item in data["bigfive"]["items"]:
        api.session_mark("bigfive_answer", {"item": item["id"], "value": 4, "rt_ms": 1200})
    api.session_finish()
    dest = export_session(tmp_path / "sessions" / started["id"], tmp_path / "out")
    assert dest.name.startswith("BHS Тест Ученик 9 класс") and "/" not in dest.name
    with zipfile.ZipFile(dest) as z:
        names = set(z.namelist())
        assert {PARENT_PDF, MANAGER_PDF, ANSWERS_CSV} <= names and "signal.npz" not in names
        table = z.read(ANSWERS_CSV).decode("utf-8-sig").splitlines()
    assert table[0].startswith("Блок;№;Утверждение")
    assert f"Интересы;1;{first['text']};5;Очень нравится;2,5" in table  # заменённый ответ
    assert sum(row.startswith("Стиль работы;") for row in table) == 20
