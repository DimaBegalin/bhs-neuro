from analyzer.main import analyze
from tests.fixtures.session import write_session


def test_profile_finds_planted_iaf_and_strong_domain(tmp_path):
    npz_path, events_path = write_session(tmp_path, iaf=10.3, strong_domain="spatial")
    profile = analyze(npz_path, events_path,
                      session_meta={"session_id": "synthetic", "lang": "ru"})
    assert profile["has_eeg"] is True
    assert abs(profile["iaf"] - 10.3) < 0.4
    best = max(profile["domains"], key=lambda c: c["efficiency"])
    assert best["domain"] == "spatial"
    assert profile["method_version"] == "1.0"


def test_profile_degrades_gracefully_without_alpha(tmp_path):
    npz_path, events_path = write_session(tmp_path, iaf=10.3, strong_domain="verbal",
                                          session_id="flat")
    import numpy as np
    data = dict(np.load(npz_path))
    rng = np.random.default_rng(0)
    data["signal"] = rng.normal(0, 8.0, size=data["signal"].shape)
    np.savez_compressed(npz_path, **data)
    profile = analyze(npz_path, events_path,
                      session_meta={"session_id": "flat", "lang": "ru"})
    assert profile["has_eeg"] is False
    assert profile["domains"][0]["efficiency"] is None
    assert profile["behavior"]["verbal"]["n_trials"] == 12


def test_block_drowned_in_artifacts_degrades_instead_of_crashing(tmp_path):
    """Боевой случай 13.08, визит Дианы: два блока целиком в артефактах.

    Один мёртвый блок не должен валить расчёт: сырьё сохранено, поведение
    живое, и профиль обязан выйти в режиме «только поведение», а причина
    попасть в вердикт качества.
    """
    import numpy as np
    npz_path, events_path = write_session(tmp_path, iaf=10.3, strong_domain="verbal",
                                          session_id="dirty")
    data = dict(np.load(npz_path))
    events = __import__("json").load(open(events_path))
    fs = int(data["fs"])
    start = next(e for e in events if e["kind"] == "block_start"
                 and e["payload"]["domain"] == "verbal")
    end = next(e for e in events if e["kind"] == "block_end"
               and e["payload"]["domain"] == "verbal")
    a, b = int(start["t_s"] * fs), int(end["t_s"] * fs)
    rng = np.random.default_rng(1)
    data["signal"][:, a:b] += rng.normal(0, 4000.0, size=(4, b - a))  # срыв контакта
    np.savez_compressed(npz_path, **data)

    profile = analyze(npz_path, events_path,
                      session_meta={"session_id": "dirty", "lang": "ru"})
    assert profile["has_eeg"] is False
    assert any("verbal" in r for r in profile["quality"]["reasons"])
    assert profile["behavior"]["verbal"]["n_trials"] == 12
