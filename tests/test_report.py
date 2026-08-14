from report.build_pdf import build_report, register_fonts


def _profile():
    return {
        "session_id": "s1", "has_eeg": True, "iaf": 10.2, "method_version": "1.0",
        "quality": {"reasons": []},
        "domains": [
            {"domain": "numeric", "accuracy": 0.7, "median_rt_ms": 1100.0,
             "cost": 0.2, "efficiency": 0.3, "attention_slope": -0.01},
            {"domain": "spatial", "accuracy": 0.95, "median_rt_ms": 900.0,
             "cost": -1.0, "efficiency": 1.7, "attention_slope": -0.002},
            {"domain": "verbal", "accuracy": 0.55, "median_rt_ms": 1600.0,
             "cost": 1.1, "efficiency": -1.6, "attention_slope": -0.05},
            {"domain": "working_memory", "accuracy": 0.75, "median_rt_ms": 1000.0,
             "cost": -0.3, "efficiency": 0.5, "attention_slope": -0.02},
        ],
    }


def test_cyrillic_font_is_available():
    regular, bold = register_fonts()
    assert regular != "Helvetica", "нет шрифта с кириллицей, PDF выйдет нечитаемым"


def test_pdf_is_created(tmp_path):
    out = build_report(_profile(), str(tmp_path / "report.pdf"))
    assert out.endswith(".pdf")
    data = open(out, "rb").read()
    assert data.startswith(b"%PDF")
    assert len(data) > 2000


def test_pdf_created_for_session_without_eeg(tmp_path):
    profile = _profile()
    profile["has_eeg"] = False
    for card in profile["domains"]:
        card["cost"] = None
        card["efficiency"] = None
    profile["quality"]["reasons"] = ["альфа-пик не выделен, нейро-слой не считается"]
    out = build_report(profile, str(tmp_path / "r2.pdf"))
    assert open(out, "rb").read().startswith(b"%PDF")
