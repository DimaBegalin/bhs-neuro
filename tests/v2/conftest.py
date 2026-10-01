import time

import pytest


def wait_until(predicate, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BHS_HOME", str(tmp_path))
    return tmp_path
