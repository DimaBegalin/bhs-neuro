import json

import pytest

from app import content
from app.report import MANAGER_PDF, PARENT_HTML, PARENT_PDF, make_reports
from app.report.model import build_model
from app.report.texts import BANNED, NEXT_STEPS, T
from app.storage import atomic_write_json


def _walk(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk(v)


def test_no_banned_wording_in_any_report_or_content_text():
    texts = list(_walk(T)) + list(_walk(NEXT_STEPS))
    for name in ("interests", "cards", "bigfive", "spatial", "subjects"):
        texts += list(_walk(content.load(name)))
    for text in texts:
        low = text.lower()
        for bad in BANNED:
            assert bad not in low, f"запрещённое «{bad}» в: {text}"


def test_every_cluster_has_next_steps_in_both_languages():
    for cluster in content.clusters():
        assert len(NEXT_STEPS[cluster["id"]]["ru"]) >= 3 and len(NEXT_STEPS[cluster["id"]]["kk"]) >= 3


def _result(level="bright", top=("engineering", "it", "science"), flags=(), lang="ru"):
    clusters = [{"cluster": c["id"], "title": c["title"], "score": 0.8 if c["id"] in top else 0.1,
                 "professions": [{"id": "x", "title": {"ru": "Инженер", "kk": "Инженер"}, "similarity": 0.9}],
                 "all": []} for c in content.clusters()]
    return {"lang": lang,
            "interests": {"scores": {"R": 90, "I": 70, "A": 10, "S": 20, "E": 30, "C": 40},
                          "level": level, "spread": 80, "top": ["R", "I", "C"],
                          "answered": {k: 5 for k in "RIASEC"}, "expected": {k: 5 for k in "RIASEC"}},
            "recommendation": {"clusters": clusters, "top": list(top) if level != "flat" else []},
            "spatial": {"total": 12, "correct": 11, "share": 0.92, "level": "strong", "timeouts": 0,
                        "median_rt_ms": 5000, "chance": 0.5},
            "work_style": {"scores": {"E": 40, "A": 55, "C": 80, "N": 30, "I": 60}, "stability": 70, "answered": {}},
            "subjects": ["math"], "cards": [], "flags": list(flags),
            "discrepancies": [{"type": "A", "questionnaire": "low", "cards": "yes"}],
            "attention_discrepancies": [], "monitoring": None}


META = {"id": "s1", "student": {"name": "Тест Ученик", "grade": 9, "lang": "ru"},
        "with_headband": False, "started_at": "2026-10-01T10:00:00"}


@pytest.mark.parametrize("lang", ["ru", "kk"])
def test_summary_has_five_points(lang):
    model = build_model(_result(lang=lang), {**META, "student": {**META["student"], "lang": lang}})
    keys = [s["key"] for s in model["summary"]]
    assert keys == ["where", "strength", "gap", "state", "steps"]
    where = model["summary"][0]["text"]
    assert ("Инженерия" in where) if lang == "ru" else ("Инженерия" in where)
    assert len(model["summary"][4]["steps"]) == 4


def test_flat_profile_summary_offers_trials_not_directions():
    model = build_model(_result(level="flat"), META)
    assert "не выражены" in model["summary"][0]["text"]
    assert model["clusters"] == []


def test_flags_soften_state_point():
    model = build_model(_result(flags=["too_fast"]), META)
    assert "Осторожно" in model["summary"][3]["text"]


def test_reports_are_written(tmp_path):
    atomic_write_json(tmp_path / "meta.json", META)
    atomic_write_json(tmp_path / "result.json", _result())
    make_reports(tmp_path)
    for name in (PARENT_PDF, MANAGER_PDF):
        data = (tmp_path / name).read_bytes()
        assert data.startswith(b"%PDF") and len(data) > 5000
    html = (tmp_path / PARENT_HTML).read_text(encoding="utf-8")
    assert "Тест Ученик" in html and "O*NET" in html


def test_comment_goes_to_the_end_of_parent_report(tmp_path):
    from app.report import COMMENT, load_comment, save_comment
    atomic_write_json(tmp_path / "meta.json", META)
    atomic_write_json(tmp_path / "result.json", _result())
    save_comment(tmp_path, "Обсудили робототехнику.\nПопробовать кружок до декабря.", "Айжан")
    make_reports(tmp_path)
    html = (tmp_path / PARENT_HTML).read_text(encoding="utf-8")
    assert "Комментарий профориентолога" in html and "Попробовать кружок до декабря." in html
    assert "Обсудили робототехнику.<br>Попробовать" in html and "Айжан" in html
    # после «Как читать», но перед мелким текстом про методики
    assert html.index("Как читать") < html.index("Комментарий профориентолога") < html.index("Методики")
    assert (tmp_path / PARENT_PDF).read_bytes().startswith(b"%PDF")
    save_comment(tmp_path, "   ")
    assert load_comment(tmp_path) is None and not (tmp_path / COMMENT).exists()


def test_comment_is_escaped_in_html(tmp_path):
    from app.report import save_comment
    atomic_write_json(tmp_path / "meta.json", META)
    atomic_write_json(tmp_path / "result.json", _result())
    save_comment(tmp_path, "<script>alert(1)</script> & ok")
    make_reports(tmp_path)
    html = (tmp_path / PARENT_HTML).read_text(encoding="utf-8")
    assert "<script>" not in html and "&lt;script&gt;" in html
