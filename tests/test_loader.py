from analyzer.loader import load_session
from tests.fixtures.session import write_session


def test_slices_have_expected_length(tmp_path):
    npz_path, events_path = write_session(tmp_path)
    session = load_session(npz_path, events_path)
    closed = session.slice("calibration_eyes_closed_start", "calibration_eyes_closed_end")
    opened = session.slice("calibration_eyes_open_start", "calibration_eyes_open_end")
    assert closed.shape == (4, 60 * 250)
    assert opened.shape == (4, 30 * 250)


def test_block_slice_is_filtered_by_domain(tmp_path):
    npz_path, events_path = write_session(tmp_path)
    session = load_session(npz_path, events_path)
    block = session.slice("block_start", "block_end", payload_filter={"domain": "verbal"})
    assert block.shape == (4, 70 * 250)


def test_trials_are_grouped_by_domain(tmp_path):
    npz_path, events_path = write_session(tmp_path)
    session = load_session(npz_path, events_path)
    trials = session.trials_by_domain
    assert set(trials) == {"numeric", "spatial", "verbal", "working_memory"}
    assert len(trials["numeric"]) == 12
    assert trials["numeric"][0]["rt_ms"] == 1000
