"""Мелкий HTTP-клиент на urllib: без зависимостей, с понятными ошибками."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class Offline(RuntimeError):
    """Нет сети или сервер не ответил."""


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def request(url: str, method: str = "GET", body=None, headers: dict | None = None,
            timeout: float = 15.0):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise HttpError(error.code, error.read().decode("utf-8", "replace")) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise Offline(str(error)) from error
    return json.loads(raw) if raw.strip() else None
