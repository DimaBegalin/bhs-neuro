from app.pilot import analyze, cronbach_alpha, render_markdown


def test_alpha_of_consistent_and_random_items():
    consistent = [[1, 1, 2], [3, 3, 3], [5, 4, 5], [2, 2, 1]]
    assert cronbach_alpha(consistent) > 0.9
    assert cronbach_alpha([[1, 5], [5, 2], [3, 3], [4, 1]]) < 0
    assert cronbach_alpha([[1, 2]]) is None


def test_pilot_report_on_real_app_sessions(tmp_path):
    from app.main import selftest
    import json
    import time
    for _ in range(3):
        selftest(tmp_path / "st.json", window=False, sessions_root=tmp_path / "sessions")
        time.sleep(1.1)  # id сессии с точностью до секунды
    assert json.loads((tmp_path / "st.json").read_text(encoding="utf-8"))["ok"]
    report = analyze([tmp_path])
    assert report["finished"] >= 3
    assert "Разбор пилота" in render_markdown(report)
