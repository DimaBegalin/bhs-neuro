import pytest

from app.report.model import build_model
from app.report.roadmap import ROADMAP_PDF, _browser, make_roadmap, render_roadmap_html
from tests.v2.test_reports import META, _result


def _model(grade: int):
    return build_model(_result(), {**META, "student": {**META["student"], "grade": grade}})


@pytest.mark.parametrize("grade, stage", [(8, "EXPLORE"), (9, "BUILD"), (10, "STRENGTHEN")])
def test_roadmap_is_filled_from_the_result(grade, stage):
    html = render_roadmap_html(_model(grade))
    assert "Тест Ученик" in html and f"{grade} класс" in html and stage in html
    assert "<b>90</b> / 100" in html  # практический балл из итога
    assert "Инженерия" in html  # направление из рекомендации


def test_tenth_grade_has_sat_ielts_letters_and_essays():
    html = render_roadmap_html(_model(10))
    assert "SAT" in html and "IELTS" in html and "рекомендательные письма" in html and "с января" in html


def test_no_roadmap_for_eleventh_grade(tmp_path):
    assert make_roadmap(tmp_path, _model(11)) is None
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(_browser() is None, reason="нет Chrome или Edge")
def test_roadmap_pdf_is_printed(tmp_path):
    pdf = make_roadmap(tmp_path, _model(9))
    assert pdf == tmp_path / ROADMAP_PDF and pdf.read_bytes()[:4] == b"%PDF"
    assert not (tmp_path / ".browser").exists()
