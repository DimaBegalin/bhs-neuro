import json

from upload.supabase_sync import queue_session, flush


class FakeStorage:
    def __init__(self, sink):
        self.sink = sink

    def from_(self, bucket):
        self.sink.setdefault("buckets", []).append(bucket)
        return self

    def upload(self, name, data, options=None):
        self.sink.setdefault("files", []).append(name)


class FakeTable:
    def __init__(self, sink, name):
        self.sink, self.name = sink, name

    def upsert(self, rows):
        self.sink.setdefault(self.name, []).extend(
            rows if isinstance(rows, list) else [rows])
        return self

    def execute(self):
        return {"status": "ok"}


class FakeClient:
    def __init__(self, fail=False):
        self.sink, self.fail = {}, fail
        self.storage = FakeStorage(self.sink)

    def table(self, name):
        if self.fail:
            raise ConnectionError("сети нет")
        return FakeTable(self.sink, name)


def _profile(session_id="s1"):
    return {
        "session_id": session_id, "lang": "ru", "method_version": "1.0",
        "iaf": 10.2, "iaf_prominence": 3.1, "bands": {"theta": [4.2, 6.2]},
        "has_eeg": True,
        "quality": {"reasons": [], "rejected_by_block": {"numeric": 0.1},
                    "calibration_rejected_share": 0.1},
        "domains": [{"domain": "numeric", "accuracy": 0.7, "median_rt_ms": 1000.0,
                     "cost": 0.1, "efficiency": 0.4, "attention_slope": -0.01}],
        "behavior": {"numeric": {"accuracy": 0.7, "median_rt_ms": 1000.0,
                                 "rt_sd_ms": 90.0, "fast_guess_share": 0.0,
                                 "stall_share": 0.0, "n_trials": 12}},
        "neuro": {"numeric": {"erd_alpha_high": -30.0, "erd_alpha_low": -12.0,
                              "theta_rise": 15.0, "engagement": 0.5,
                              "attention_slope": -0.01, "epochs_total": 69,
                              "epochs_rejected": 4}},
    }


def test_queue_writes_job_file(tmp_path):
    path = queue_session(_profile(), "a.npz", "a.events.json", tmp_path)
    job = json.loads(open(path, encoding="utf-8").read())
    assert job["profile"]["session_id"] == "s1"
    assert job["npz_path"] == "a.npz"


def test_flush_sends_and_clears_queue(tmp_path):
    queue_session(_profile("s1"), "a.npz", "a.events.json", tmp_path)
    queue_session(_profile("s2"), "b.npz", "b.events.json", tmp_path)
    client = FakeClient()
    sent = flush(client, queue_dir=tmp_path)
    assert sorted(sent) == ["s1", "s2"]
    assert list(tmp_path.glob("*.job.json")) == []
    assert len(client.sink["neuro_sessions"]) == 2
    assert len(client.sink["neuro_profiles"]) == 2


def test_flush_keeps_queue_when_network_down(tmp_path):
    queue_session(_profile("s3"), "c.npz", "c.events.json", tmp_path)
    sent = flush(FakeClient(fail=True), queue_dir=tmp_path)
    assert sent == []
    assert len(list(tmp_path.glob("*.job.json"))) == 1


def test_flush_uploads_raw_files(tmp_path):
    npz = tmp_path / "s4.npz"
    npz.write_bytes(b"fake")
    events = tmp_path / "s4.events.json"
    events.write_text("[]", encoding="utf-8")
    queue_session(_profile("s4"), str(npz), str(events), tmp_path)
    client = FakeClient()
    flush(client, queue_dir=tmp_path)
    assert sorted(client.sink["files"]) == ["s4.events.json", "s4.npz"]
    assert client.sink["buckets"][0] == "neuro-raw"
